import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.insert(0, str(ROOT / 'scripts'))
from breeze_pny.bank import load_bank, resolve, settings
from breeze_pny.files import acquire, unpack
from breeze_pny.router import Router, Server, handler
from breeze_pny.__main__ import smoke
from breeze_pny.service import check_port
from breeze_pny.playback import Playback125

PCM = b'\x01\x20' * 12000


class Native(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_POST(self):
        from urllib.parse import parse_qs
        body = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode(), keep_blank_values=True)
        self.server.requests.append(body)
        voice = body['voice_id'][0]
        if voice == 'busy': self.send_error(409); return
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('X-Sample-Format', 's16le'); self.send_header('X-Sample-Rate', '24000')
        adapter = 'wrong' if voice == 'bad_adapter' else body.get('lora', [''])[0] or 'base'
        self.send_header('X-Breeze-Adapter', adapter)
        size = len(PCM) + 10 if voice == 'truncated' else len(PCM)
        self.send_header('Content-Length', str(size)); self.end_headers()
        if voice == 'stall':
            self.wfile.write(PCM[:4096]); self.wfile.flush()
            self.connection.settimeout(3)
            try:
                if self.connection.recv(1) == b'': self.server.cancelled.set()
            except OSError: pass
            return
        try:
            for at in range(0, len(PCM), 3840):
                self.wfile.write(PCM[at:at + 3840]); self.wfile.flush(); time.sleep(.015)
        except OSError: pass


class RouterChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = ThreadingHTTPServer(('127.0.0.1', 0), Native)
        cls.native.requests = []; cls.native.cancelled = threading.Event()
        cls.native.daemon_threads = True
        cls.native_thread = threading.Thread(target=cls.native.serve_forever, daemon=True); cls.native_thread.start()
        rows = {name: {'id': name, 'route': 'breeze', 'voice_id': name,
                      'settings': settings({'lora': {'rainbow_dash':'rainbow', 'pinkie_pie':'pinkie', 'applejack':'applejack', 'fluttershy':'fluttershy', 'rarity':'rarity', 'twilight_sparkle':'twilight'}.get(name, '')})}
                for name in ['spike', 'rainbow_dash', 'pinkie_pie', 'applejack', 'fluttershy', 'rarity', 'twilight_sparkle', 'stall', 'busy', 'truncated', 'bad_adapter']}
        cls.bank = {'id': 'fixture', 'routes': rows, 'legacy_speakers': {'31': 'spike'}}
        cls.router = Router(cls.bank, cls.native.server_port)
        cls.server = Server(('127.0.0.1', 0), handler(cls.router))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        for server, thread in [(cls.server, cls.thread), (cls.native, cls.native_thread)]:
            server.shutdown(); server.server_close(); thread.join()

    def request(self, path, body):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=4)
        raw = json.dumps(body).encode()
        connection.request('POST', path, raw, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        return connection, response

    def test_health(self):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('GET', '/health'); response = connection.getresponse()
        data = json.loads(response.read()); connection.close()
        self.assertTrue(data['ready']); self.assertEqual(data['pcm_stream'], 'framed-v1')
        self.assertEqual(data['routes'], {'breeze': len(self.bank['routes'])})
        self.assertFalse(data['fallback'])

    def test_stream_and_adapter(self):
        for character, adapter in [('spike', 'base'), ('rainbow_dash', 'rainbow'), ('pinkie_pie', 'pinkie'),
                                   ('applejack', 'applejack'), ('fluttershy', 'fluttershy'), ('rarity', 'rarity'),
                                   ('twilight_sparkle', 'twilight')]:
            result = smoke(self.url, character)
            self.assertEqual(result['adapter'], adapter)
            self.assertEqual(result['audio_seconds'], .5)
            self.assertLess(result['first_response_s'], result['elapsed_s'])

    def test_buffered_breeze(self):
        connection, response = self.request('/tts', {'text': '[happy] Hello!', 'character_id': 'spike'})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader('X-Breeze-Adapter'), 'base')
        with wave.open(io.BytesIO(response.read())) as wav: self.assertEqual(wav.readframes(wav.getnframes()), PCM)
        connection.close()
        self.assertEqual(self.native.requests[-1]['text'], ['Hello!'])

    def test_reviewed_cues_reach_both_native_transports(self):
        for endpoint in ['/tts', '/tts/stream']:
            for source, expected in [('Gasp! Hello.', '(gasp) Hello.'),
                                     ('gasp ...a perfect day!', '(gasp) ...a perfect day!'),
                                     ('Teehee! Hello.', '(giggles) Hello.'),
                                     ('Hahahaha!', 'Hahahaha!'), ('Hmph! Hello.', 'Hmph! Hello.')]:
                connection, response = self.request(endpoint, {'text': source, 'character_id': 'spike'})
                self.assertEqual(response.status, 200); response.read(); connection.close()
                self.assertEqual(self.native.requests[-1]['text'], [expected])

    def test_slow_voice_playback_and_stream_receipt_match(self):
        row = self.bank['routes']['pinkie_pie']
        row['output_speed'] = 1.25
        try:
            expected = Playback125().process(PCM, final=True)
            connection, response = self.request('/tts', {'text': 'Gasp! Hello.', 'character_id': 'pinkie_pie'})
            self.assertEqual(response.status, 200)
            with wave.open(io.BytesIO(response.read())) as wav:
                self.assertEqual(wav.readframes(wav.getnframes()), expected)
            connection.close()
            connection, response = self.request('/tts/stream', {'text': '(gasp) Hello.', 'character_id': 'pinkie_pie'})
            self.assertEqual(response.status, 200)
            wire = response.read(); connection.close()
            at, chunks = 0, []
            while True:
                size, = struct.unpack_from('<I', wire, at); at += 4
                if not size: break
                chunks.append(wire[at:at + size]); at += size
            self.assertEqual(b''.join(chunks), expected)
            self.assertEqual(wire[at:], struct.pack('<I', len(expected)) + hashlib.sha256(expected).digest())
            self.assertEqual(self.native.requests[-1]['lora'], ['pinkie'])
            self.assertNotIn('output_speed', self.native.requests[-1])
        finally:
            row.pop('output_speed')

    def test_slow_voice_rejects_truncation_without_receipt(self):
        row = self.bank['routes']['truncated']; row['output_speed'] = 1.25
        try:
            connection, response = self.request('/tts/stream', {'text': 'Hello.', 'character_id': 'truncated'})
            wire = b''
            try:
                while data := response.read1(4096): wire += data
            except http.client.IncompleteRead: pass
            connection.close()
            expected = Playback125().process(PCM, final=True)
            self.assertNotIn(struct.pack('<II', 0, len(expected)) + hashlib.sha256(expected).digest(), wire)
        finally:
            row.pop('output_speed')

    def test_bad_inputs(self):
        for body in [{}, {'text': 'Hi', 'character_id': 'unknown'}, {'text': 'x' * 601}, {'text': '[happy]'}]:
            connection, response = self.request('/tts', body)
            self.assertEqual(response.status, 400); response.read(); connection.close()

    def test_adapter_mismatch_and_busy(self):
        for voice, code in [('bad_adapter', 502), ('busy', 503)]:
            connection, response = self.request('/tts/stream', {'text': 'Hi', 'character_id': voice})
            self.assertEqual(response.status, code); response.read(); connection.close()

    def test_truncated_stream_has_no_receipt(self):
        connection, response = self.request('/tts/stream', {'text': 'Hi', 'character_id': 'truncated'})
        self.assertEqual(response.status, 200)
        wire = b''
        try:
            while data := response.read1(4096): wire += data
        except http.client.IncompleteRead: pass
        connection.close()
        self.assertNotIn(struct.pack('<II', 0, len(PCM)) + hashlib.sha256(PCM).digest(), wire)

    def test_disconnect_cancels_stalled_native_and_releases_lock(self):
        connection, response = self.request('/tts/stream', {'text': 'Hi', 'character_id': 'stall'})
        self.assertEqual(response.status, 200); self.assertTrue(response.read1(20))
        other, busy = self.request('/tts', {'text': 'Hi', 'character_id': 'spike'})
        self.assertEqual(busy.status, 503); busy.read(); other.close()
        start = time.monotonic(); response.close(); connection.close()
        self.assertTrue(self.native.cancelled.wait(1), 'native socket was not cancelled promptly')
        while self.router.lock.locked() and time.monotonic() - start < 1: time.sleep(.01)
        self.assertFalse(self.router.lock.locked())
        self.assertEqual(smoke(self.url, 'spike')['audio_seconds'], .5)


class StartupChecks(unittest.TestCase):
    def test_native_port_cooldown_waits_until_available(self):
        with socket.socket() as previous:
            previous.bind(('127.0.0.1', 0))
            port = previous.getsockname()[1]
            with patch('breeze_pny.service.time.sleep', side_effect=lambda _: previous.close()) as wait:
                check_port('127.0.0.1', port, 'Native Breeze', wait_seconds=1)
            self.assertTrue(wait.called)

    def test_recently_closed_native_connection_does_not_block_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            with socket.create_connection(('127.0.0.1', port)) as client:
                server, _ = listener.accept()
                with server:
                    server.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b'')
        check_port('127.0.0.1', port, 'Native Breeze')

    def test_live_native_listener_is_rejected_with_its_port(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(ValueError, f'Native Breeze port 127.0.0.1:{port}'):
                check_port('127.0.0.1', port, 'Native Breeze')


class BundleChecks(unittest.TestCase):
    def test_reject_traversal_links_duplicates_and_oversize(self):
        for kind in ('traversal', 'symlink', 'duplicate', 'oversize'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); archive = root / 'bad.tar.gz'
                with tarfile.open(archive, 'w:gz') as tar:
                    item = tarfile.TarInfo('../outside' if kind == 'traversal' else 'file')
                    item.size = 4
                    if kind == 'symlink': item.type = tarfile.SYMTYPE; item.linkname = '/tmp/outside'
                    tar.addfile(item, io.BytesIO(b'test'))
                    if kind == 'duplicate': tar.addfile(item, io.BytesIO(b'test'))
                with self.assertRaises(ValueError): unpack(archive, root / 'unpacked', max_bytes=3 if kind == 'oversize' else 100)
                self.assertFalse((root / 'unpacked').exists())
                self.assertFalse((root / 'outside').exists())

    def test_checksum_failure_preserves_previous_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; destination = root / 'destination'
            source.write_bytes(b'bad'); destination.write_bytes(b'previous')
            with self.assertRaises(ValueError): acquire(source, destination, '0' * 64)
            self.assertEqual(destination.read_bytes(), b'previous')
            self.assertFalse((root / 'destination.partial').exists())

    def test_unknown_identity_never_uses_placeholder_speaker(self):
        bank = {'routes': {'spike': {}}, 'legacy_speakers': {'31': 'spike'}}
        with self.assertRaises(ValueError): resolve(bank, {'text': 'Hello', 'character_id': 'unknown', 'speaker_id': 31})

    def test_only_breeze_routes_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'notice').write_bytes(b'fixture')
            bank = {'schema': 1, 'id': 'fixture',
                    'files': {'notice': hashlib.sha256(b'fixture').hexdigest()},
                    'characters': [{'id': 'fixture', 'route': 'retired'}]}
            (root / 'voice-pack.json').write_text(json.dumps(bank))
            with self.assertRaisesRegex(ValueError, 'Unsupported voice route'):
                load_bank(root)

    def test_no_paths_or_endpoints_in_voice_settings(self):
        for bad in [{'capture_dir': '/tmp/audio'}, {'endpoint': 'http://remote'}, {'lora': '../rainbow'}, {'cfg_scale': float('nan')}]:
            with self.assertRaises(ValueError): settings(bad)


if __name__ == '__main__': unittest.main()
