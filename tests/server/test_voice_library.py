import base64
from email.parser import BytesParser
from email.policy import default
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.insert(0, str(ROOT / 'scripts'))
from breeze_pny.bank import load_bank
from breeze_pny.files import read_json, sha, write_json
from breeze_pny.voice_edit import VoiceEditor, pcm_wav, preserve_custom_voices, reference_wav
from breeze_pny.voice_library import create_server
from release_files import server_files
from export_voice_pack import export
from package_reference_audio import package as package_reference_audio

WAV = pcm_wav(struct.pack('<h', 2000) * 24000)


def fixture(root):
    pack = root / 'assets/voice-packs/stock'
    (pack / 'voices').mkdir(parents=True)
    (pack / 'voices/shared.breeze').write_bytes(b'fixture cache')
    bank = {'schema': 1, 'id': 'fixture', 'version': '1', 'model_sha256': '0' * 64,
            'characters': [{'id': identity, 'name': name, 'route': 'breeze', 'voice_id': 'shared',
                            'settings': {'cfg_scale': 1, 'temperature': .7, 'lora': ''}}
                           for identity, name in [('derpy_hooves', 'Derpy Hooves'), ('spike', 'Spike')]],
            'voices': {'shared': {'file': 'voices/shared.breeze', 'ref_text': 'Original words.',
                                 'reference_sha256': hashlib.sha256(WAV).hexdigest()}},
            'files': {'voices/shared.breeze': sha(pack / 'voices/shared.breeze')},
            'legacy_speakers': {'1': 'derpy_hooves'}, 'adapters': {}}
    write_json(pack / 'voice-pack.json', bank)
    config = {'schema': 1, 'host': '127.0.0.1', 'port': 18792, 'native_port': 18797,
              'voice_pack': pack.relative_to(root).as_posix(), 'model_sha256': '0' * 64}
    write_json(root / 'config.json', config)
    return pack


class FakeNative(BaseHTTPRequestHandler):
    def log_message(self, *_): pass

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        if self.path == '/v1/voices':
            message = BytesParser(policy=default).parsebytes(
                ('Content-Type: ' + self.headers['Content-Type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
            fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True)
                      for part in message.iter_parts()}
            name = fields['name'].decode()
            result = {'id': name, 'ref_text': fields['ref_text'].decode(),
                      'metadata': json.loads(fields['metadata']), 'saved': True}
            (self.server.voices / (name + '.breeze')).write_bytes(json.dumps(result).encode())
            self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(result).encode())
        else:
            fields = parse_qs(raw.decode(), keep_blank_values=True)
            self.server.last_voice = fields['voice_id'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('X-Sample-Format', 's16le'); self.send_header('X-Sample-Rate', '24000')
            self.send_header('X-Breeze-Adapter', fields.get('lora', [''])[0] or 'base')
            self.send_header('Content-Length', '24000'); self.end_headers()
            self.wfile.write(struct.pack('<h', 3000) * 12000)


class VoiceLibraryChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.original = fixture(self.root)
        self.editor = VoiceEditor(self.root / 'config.json')
        self.native = ThreadingHTTPServer(('127.0.0.1', 0), FakeNative)
        self.native.voices = self.editor.workspace / 'voices'
        self.thread = threading.Thread(target=self.native.serve_forever, daemon=True); self.thread.start()
        self.editor.native_port = self.native.server_port
        self.patch = patch.object(self.editor, 'start_native'); self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.native.shutdown(); self.native.server_close(); self.thread.join()
        self.editor.close(); self.folder.cleanup()

    def prepared(self):
        result = self.editor.prepare('derpy_hooves', 'Replacement words. é', WAV, 'My own recording')
        self.editor.audition('derpy_hooves', 'Hello.', result['id'])
        return result

    def test_prepare_preview_apply_undo_and_shared_voice_isolation(self):
        config_before = (self.root / 'config.json').read_bytes()
        bank_before = (self.original / 'voice-pack.json').read_bytes()
        result = self.prepared()
        self.assertEqual((self.root / 'config.json').read_bytes(), config_before)
        self.assertEqual((self.original / 'voice-pack.json').read_bytes(), bank_before)
        voice = self.native.last_voice
        self.assertTrue(voice.startswith('edit_derpy_hooves_'))
        self.assertEqual(self.editor.pending['sha256'], hashlib.sha256(WAV).hexdigest())
        self.editor.apply(result['id'])
        installed = load_bank(self.editor.bank_root)
        self.assertEqual(installed['routes']['derpy_hooves']['voice_id'], voice)
        self.assertEqual(installed['routes']['spike']['voice_id'], 'shared')
        self.assertEqual(installed['legacy_speakers'], {'1': 'derpy_hooves'})
        self.assertEqual(installed['voices'][voice]['ref_text'], 'Replacement words. é')
        self.assertEqual(self.editor.reference(voice).read_bytes(), WAV)
        self.assertTrue(self.editor.state()['can_undo'])
        self.editor.undo()
        self.assertEqual(self.editor.bank_root, self.original)
        self.assertEqual(read_json(self.root / 'config.json'), json.loads(config_before))
        self.assertEqual((self.original / 'voice-pack.json').read_bytes(), bank_before)

    def test_preview_and_unchanged_staging_required(self):
        prepared = self.editor.prepare('derpy_hooves', 'New words.', WAV)
        with self.assertRaisesRegex(ValueError, 'preview'):
            self.editor.apply(prepared['id'])
        with self.assertRaisesRegex(ValueError, 'again'):
            self.editor.audition('derpy_hooves', 'Hello.', 'stale')
        self.editor.audition('derpy_hooves', 'Hello.', prepared['id'])
        (self.editor.workspace / 'voices' / (self.editor.pending['voice'] + '.breeze')).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'staged reference changed'):
            self.editor.apply(prepared['id'])
        self.assertEqual(read_json(self.root / 'config.json')['voice_pack'], self.original.relative_to(self.root).as_posix())

    def test_manifest_write_failure_keeps_active_config(self):
        prepared = self.prepared()
        config_before = (self.root / 'config.json').read_bytes()
        with patch('breeze_pny.voice_edit.write_json', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                self.editor.apply(prepared['id'])
        self.assertEqual((self.root / 'config.json').read_bytes(), config_before)
        self.assertEqual(list((self.root / 'assets/voice-packs').glob('.voice-edit-*')), [])

    def test_config_activation_failure_keeps_valid_previous_installation(self):
        prepared = self.prepared()
        config_before = (self.root / 'config.json').read_bytes()
        def write(path, value):
            if path == self.root / 'config.json': raise OSError('read only config')
            return write_json(path, value)
        with patch('breeze_pny.voice_edit.write_json', side_effect=write):
            with self.assertRaisesRegex(OSError, 'read only'):
                self.editor.apply(prepared['id'])
        self.assertEqual((self.root / 'config.json').read_bytes(), config_before)
        load_bank(self.original)

    def test_reference_integrity_and_configuration_conflict(self):
        prepared = self.prepared(); self.editor.apply(prepared['id'])
        voice = self.editor.bank['custom_voices']['derpy_hooves']
        self.editor.reference(voice).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed asset'):
            load_bank(self.editor.bank_root)
        config = read_json(self.root / 'config.json'); config['port'] += 1
        write_json(self.root / 'config.json', config)
        with self.assertRaisesRegex(ValueError, 'configuration changed'):
            self.editor.undo()

    def test_updates_preserve_custom_recordings_and_new_stock_settings(self):
        prepared = self.prepared(); self.editor.apply(prepared['id'])
        base = self.root / 'assets/voice-packs/updated'
        import shutil
        shutil.copytree(self.original, base)
        manifest = read_json(base / 'voice-pack.json')
        manifest['characters'][0]['settings']['cfg_scale'] = 2
        write_json(base / 'voice-pack.json', manifest)
        merged = preserve_custom_voices(self.root, self.editor.bank_root, base)
        bank = load_bank(merged)
        voice = bank['routes']['derpy_hooves']['voice_id']
        self.assertTrue(voice.startswith('edit_'))
        self.assertEqual(bank['routes']['derpy_hooves']['settings']['cfg_scale'], 2)
        self.assertEqual((merged / bank['voices'][voice]['reference_file']).read_bytes(), WAV)
        manifest['model_sha256'] = '1' * 64
        write_json(base / 'voice-pack.json', manifest)
        with self.assertRaisesRegex(ValueError, 'previous model'):
            preserve_custom_voices(self.root, self.editor.bank_root, base)

    def test_external_reference_directory_requires_exact_hash(self):
        self.editor.reference_directory = self.root
        path = self.root / 'shared.wav'; path.write_bytes(WAV)
        self.assertEqual(self.editor.reference('shared'), path)
        path.write_bytes(pcm_wav(b'\x01\x00' * 24000))
        self.assertIsNone(self.editor.reference('shared'))

    def test_second_editor_cannot_open_an_active_installation(self):
        with self.assertRaisesRegex(ValueError, 'Stop the companion'):
            VoiceEditor(self.root / 'config.json')

    def test_http_authorization_and_end_to_end_replacement(self):
        server, token = create_server(self.editor)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def call(method, path, data=None, auth=token, origin=None):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            headers = {'X-Voice-Library-Token': auth}
            if origin: headers['Origin'] = origin
            if data is not None: headers['Content-Type'] = 'application/json'
            connection.request(method, path, json.dumps(data) if data is not None else None, headers)
            response = connection.getresponse(); status = response.status; raw = response.read(); connection.close()
            return status, raw
        try:
            self.assertEqual(call('GET', '/api/state', auth='wrong')[0], 403)
            self.assertEqual(call('POST', '/api/undo', {}, origin='https://example.invalid')[0], 403)
            self.assertEqual(call('GET', '/api/state')[0], 200)
            status, raw = call('POST', '/api/prepare', {'character': 'derpy_hooves', 'transcript': 'New words.',
                                                      'wav': base64.b64encode(WAV).decode()})
            self.assertEqual(status, 200, raw)
            pending = json.loads(raw)['id']
            self.assertEqual(call('POST', '/api/audition', {'character': 'derpy_hooves', 'text': 'Hello.', 'pending_id': pending})[0], 200)
            self.assertEqual(call('POST', '/api/apply', {'pending_id': pending})[0], 200)
            voice = self.editor.bank['routes']['derpy_hooves']['voice_id']
            self.assertEqual(call('GET', '/api/reference?voice=' + voice), (200, WAV))
            self.assertEqual(call('POST', '/api/undo', {})[0], 200)
            self.assertEqual(call('POST', '/api/prepare', {'wav': 'bad base64!'} )[0], 400)
        finally:
            server.shutdown(); server.server_close(); thread.join()


class ReferenceChecks(unittest.TestCase):
    def test_rejects_silence_truncation_compressed_and_wrong_format(self):
        self.assertEqual(reference_wav(WAV), WAV)
        for raw in [b'not a wav', WAV[:-2], pcm_wav(b'\0\0' * 24000), pcm_wav(b'\x01\0' * 10)]:
            with self.subTest(raw_length=len(raw)), self.assertRaises(ValueError): reference_wav(raw)
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed')); wav.writeframes(b'\1\0' * 96000)
        with self.assertRaisesRegex(ValueError, 'mono 24 kHz'): reference_wav(output.getvalue())

    def test_pack_export_includes_verified_playable_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); pack = fixture(root)
            (root / 'reference.wav').write_bytes(WAV)
            (root / 'refs.json').write_text(json.dumps({'voices': {'shared': {
                'audio': 'reference.wav', 'transcript': 'Original words.', 'sha256': hashlib.sha256(WAV).hexdigest()}}}))
            export(pack / 'voice-pack.json', root / 'refs.json', pack / 'voices', {}, root / 'voices.tar.gz',
                   include_reference_audio=True)
            from breeze_pny.files import unpack
            unpack(root / 'voices.tar.gz', root / 'exported')
            bank = load_bank(root / 'exported')
            self.assertEqual(bank['voices']['shared']['reference_file'], 'references/shared.wav')
            (root / 'reference.wav').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'differs'):
                export(pack / 'voice-pack.json', root / 'refs.json', pack / 'voices', {}, root / 'bad.tar.gz',
                       include_reference_audio=True)

    def test_release_packaging_includes_browser_assets(self):
        paths = {p.relative_to(ROOT).as_posix() for p in server_files(ROOT)}
        self.assertTrue({'server/breeze_pny/voice_library/' + name for name in ('index.html', 'app.js', 'style.css')} <= paths)
        self.assertFalse(any('__pycache__' in path for path in paths))

    def test_reference_audio_bundle_contains_only_verified_recordings(self):
        import zipfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'source.wav'; audio.write_bytes(WAV)
            refs = root / 'references.json'
            refs.write_text(json.dumps({'voices': {'derpy_hooves': {
                'audio': str(audio), 'sha256': hashlib.sha256(WAV).hexdigest(),
                'transcript': 'Words.', 'private_lab_field': 'not for export'}}}))
            output = io.BytesIO()
            package_reference_audio(refs, output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read('reference-audio/derpy_hooves.wav'), WAV)
                self.assertNotIn(str(audio), archive.read('reference-audio/manifest.json').decode())
                self.assertNotIn(b'private_lab_field', b''.join(archive.read(name) for name in archive.namelist()))
            audio.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                package_reference_audio(refs, io.BytesIO())


if __name__ == '__main__': unittest.main()
