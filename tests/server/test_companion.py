"""Lifecycle and HTTP tests with real fixture HTTP/audio, no downloaded weights."""
import base64
import copy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
from breeze_pny.companion import Companion
from breeze_pny.files import acquire, read_json, sha, write_json
from breeze_pny.models import CATALOG, compatible, model_path
from breeze_pny.web import create_server
from test_voice_library import fixture, FakeNative, WAV


class CancellableNative(FakeNative):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        from urllib.parse import parse_qs
        if self.path == '/v1/audio/speech' and parse_qs(raw.decode()).get('text') == ['__cancel__']:
            self.send_response(200)
            for key, value in [('Content-Type','application/octet-stream'), ('X-Sample-Format','s16le'),
                               ('X-Sample-Rate','24000'), ('X-Breeze-Adapter','base'), ('Content-Length','48000')]:
                self.send_header(key,value)
            self.end_headers(); self.wfile.write(b'\x01\x20'*1000); self.wfile.flush()
            self.connection.settimeout(5)
            try: self.connection.recv(1)
            except OSError: pass
            return
        self.rfile = io.BytesIO(raw)
        super().do_POST()


class CompanionFixture:
    def __init__(self, root):
        self.root = root
        bank_root = fixture(root)
        catalog = {}
        self.raw = {}
        for identity, original in CATALOG.items():
            raw = ('fixture model ' + identity).encode()
            catalog[identity] = {**original, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            self.raw[identity] = raw
        self.catalog_patch = patch.dict(CATALOG, catalog, clear=True); self.catalog_patch.start()
        bank = read_json(bank_root / 'voice-pack.json')
        bank['model_sha256'] = catalog['q8_0']['sha256']
        (bank_root / 'reference.wav').write_bytes(WAV)
        bank['voices']['shared']['reference_file'] = 'reference.wav'
        bank['files']['reference.wav'] = sha(bank_root / 'reference.wav')
        write_json(bank_root / 'voice-pack.json', bank)
        self.put_model('q8_0'); self.put_model('q4_k')
        config = read_json(root / 'config.json')
        config.update(model_sha256=catalog['q8_0']['sha256'], model=model_path(root, catalog['q8_0']).relative_to(root).as_posix())
        write_json(root / 'config.json', config)
        self.inspect_patch = patch('breeze_pny.companion.inspect', side_effect=self.inspect); self.inspect_patch.start()
        self.app = Companion(root / 'config.json')
        self.native = ThreadingHTTPServer(('127.0.0.1', 0), CancellableNative)
        self.native.voices = self.app.workspace / 'voices'
        self.thread = threading.Thread(target=self.native.serve_forever, daemon=True); self.thread.start()
        self.app.native_port = self.app.router.port = self.native.server_port
        self.starts = []
        self.failed = set()
        self.start_patch = patch.object(self.app, '_start', side_effect=self.start); self.start_patch.start()
        self.app.load_model('q8_0')

    def put_model(self, identity):
        path = model_path(self.root, CATALOG[identity]); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.raw[identity])

    def inspect(self, path, **kwargs):
        config = kwargs.get('config') or read_json(path)
        if kwargs.get('model_required', True) and sha(self.root / config['model']) != config['model_sha256']:
            raise ValueError('Breeze model hash mismatch')

    def start(self, config):
        self.starts.append(config['model_sha256'])
        self.app.child = Mock()
        self.app.child.poll.return_value = None
        if config['model_sha256'] in self.failed:
            raise RuntimeError('Fixture could not load model')

    def close(self):
        self.app.close()
        self.native.shutdown(); self.native.server_close(); self.thread.join()
        self.start_patch.stop(); self.inspect_patch.stop(); self.catalog_patch.stop()


class CompanionChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = CompanionFixture(Path(self.temp.name)); self.app = self.fixture.app
        self.server, self.token = create_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.fixture.close(); self.temp.cleanup()

    def call(self, method, path, data=None, token=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'X-Breeze-Token': self.token if token is None else token, 'Content-Type': 'application/json'}
        if origin: headers['Origin'] = origin
        connection.request(method, path, None if data is None else json.dumps(data), headers)
        response = connection.getresponse(); raw = response.read(); code = response.status
        connection.close()
        return code, raw

    def job(self, action, identity=None):
        self.app.submit(action, identity); self.app.worker.join(5)
        self.assertFalse(self.app.worker.is_alive()); return self.app.job

    def test_ui_auth_and_generation_share_router(self):
        for path in ['/api/state', '/api/reference?voice=shared']:
            self.assertEqual(self.call('GET', path, token='wrong')[0], 403)
        self.assertEqual(self.call('POST', '/tts', {}, origin='https://elsewhere.invalid')[0], 403)
        code, raw = self.call('POST', '/tts', {'character_id': 'spike', 'text': 'Gasp! Hello.'})
        self.assertEqual(code, 200); self.assertEqual(raw[:4], b'RIFF')
        with self.app.router.lock:
            self.assertEqual(self.call('POST', '/tts', {'text': 'Hi', 'character_id': 'spike'})[0], 503)
            with self.assertRaisesRegex(ValueError, 'Finish or cancel'): self.app.submit('unload')
        self.assertEqual(self.call('GET', '/')[0], 200)

    def test_unload_keeps_ui_and_reference_playback_available(self):
        self.assertEqual(self.job('unload')['status'], 'complete')
        self.assertFalse(self.app.healthy()); self.assertFalse(read_json(self.app.config_path)['autoload'])
        code, raw = self.call('GET', '/api/state'); self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw)['phase'], 'unloaded')
        self.assertEqual(self.call('GET', '/api/reference?voice=shared'), (200, WAV))
        self.assertEqual(self.call('POST', '/tts', {'text': 'Hi', 'character_id': 'spike'})[0], 503)
        self.assertEqual(self.job('load', 'q4_k')['status'], 'complete')
        self.assertTrue(self.app.healthy()); self.assertTrue(read_json(self.app.config_path)['autoload'])

    def test_failed_switch_restores_previous_loaded_model_and_config(self):
        before = read_json(self.app.config_path)
        self.fixture.failed.add(CATALOG['q4_k']['sha256'])
        self.assertEqual(self.job('load', 'q4_k')['status'], 'failed')
        self.assertTrue(self.app.healthy()); self.assertEqual(self.app.config, before)
        self.assertEqual(read_json(self.app.config_path), before)
        self.assertEqual(self.app.loaded, CATALOG['q8_0']['sha256'])

    def test_corrupt_model_is_rejected_before_unloading_working_model(self):
        model_path(self.fixture.root, CATALOG['q4_k']).write_bytes(b'corrupt')
        previous = self.app.child
        self.assertEqual(self.job('load', 'q4_k')['status'], 'failed')
        previous.terminate.assert_not_called(); self.assertTrue(self.app.healthy())

    def test_active_deletion_protected_unloaded_deletion_persists(self):
        self.assertEqual(self.job('delete', 'q8_0')['status'], 'failed')
        self.job('unload'); self.assertEqual(self.job('delete', 'q8_0')['status'], 'complete')
        self.assertFalse(model_path(self.fixture.root, CATALOG['q8_0']).exists())
        self.assertFalse(read_json(self.app.config_path)['autoload'])
        self.assertEqual(self.call('GET', '/api/state')[0], 200)

    def test_reference_save_and_undo_immediately_change_api_voice_on_q4(self):
        self.job('load', 'q4_k')
        code, raw = self.call('POST', '/api/prepare', {'character': 'derpy_hooves', 'transcript': 'New words.', 'wav': base64.b64encode(WAV).decode()})
        self.assertEqual(code, 200); pending = json.loads(raw)['id']
        self.assertEqual(self.call('POST', '/api/audition', {'character': 'derpy_hooves', 'text': 'Hello.', 'pending_id': pending})[0], 200)
        self.assertEqual(self.call('POST', '/api/apply', {'pending_id': pending})[0], 200)
        custom = self.app.bank['routes']['derpy_hooves']['voice_id']
        self.call('POST', '/tts', {'character_id': 'derpy_hooves', 'text': 'Hello.'})
        self.assertEqual(self.fixture.native.last_voice, custom)
        self.assertEqual(self.call('POST', '/api/undo', {})[0], 200)
        self.call('POST', '/tts', {'character_id': 'derpy_hooves', 'text': 'Hello.'})
        self.assertEqual(self.fixture.native.last_voice, 'shared')

    def test_add_voice_over_http_makes_it_immediately_available_to_router(self):
        code, raw = self.call('POST', '/api/prepare', {'character': 'custom_narrator', 'name': 'My narrator',
            'transcript': 'New words.', 'wav': base64.b64encode(WAV).decode()})
        self.assertEqual(code, 200, raw); pending = json.loads(raw)['id']
        self.assertEqual(self.call('POST', '/api/audition', {'character': 'custom_narrator', 'text': 'Hello.', 'pending_id': pending})[0], 200)
        code, raw = self.call('POST', '/api/apply', {'pending_id': pending})
        self.assertEqual(code, 200, raw)
        self.assertIn('custom_narrator', [row['id'] for row in json.loads(raw)['characters']])
        self.assertIs(self.app.router.bank, self.app.bank)
        code, raw = self.call('POST', '/tts', {'character_id': 'custom_narrator', 'text': 'Hello.'})
        self.assertEqual(code, 200, raw); self.assertEqual(raw[:4], b'RIFF')
        self.assertEqual(self.fixture.native.last_voice, self.app.bank['routes']['custom_narrator']['voice_id'])
        self.assertTrue(self.app.router.lock.acquire(timeout=2)); self.app.router.lock.release()
        self.job('unload'); self.job('load', 'q4_k')
        self.assertEqual(self.call('POST', '/tts', {'character_id': 'custom_narrator', 'text': 'Hello again.'})[0], 200)
        self.assertTrue(self.app.router.lock.acquire(timeout=2)); self.app.router.lock.release()
        self.assertEqual(self.call('POST', '/api/undo', {})[0], 200)
        self.assertNotIn('custom_narrator', self.app.router.bank['routes'])
        self.assertEqual(self.call('POST', '/tts', {'character_id': 'custom_narrator', 'text': 'Hello.'})[0], 400)

    def test_download_can_run_alongside_speech_and_cancels_without_final_file(self):
        started = threading.Event()
        def download(*args, cancelled, **kwargs):
            started.set(); cancelled.wait(4); raise InterruptedError('Download cancelled')
        with patch('breeze_pny.companion.download', side_effect=download):
            self.app.submit('download', 'f16'); self.assertTrue(started.wait(1))
            self.assertEqual(self.call('POST', '/tts', {'character_id': 'spike', 'text': 'Hello.'})[0], 200)
            self.assertEqual(self.call('POST', '/api/download/cancel', {})[0], 200)
            self.app.worker.join(2)
        self.assertEqual(self.app.job['status'], 'cancelled')
        self.assertFalse(model_path(self.fixture.root, CATALOG['f16']).exists())

    def test_remove_voice_http_auth_busy_protection_live_routing_and_undo(self):
        for identity, name in [('custom_first', 'First voice'), ('custom_second', 'Second voice')]:
            prepared = self.app.prepare(identity, 'My words.', WAV, name=name)
            self.app.audition(identity, 'Hello.', prepared['id']); self.app.apply(prepared['id'])
        body = {'character': 'custom_first'}
        self.assertEqual(self.call('POST', '/api/remove-voice', body, token='wrong')[0], 403)
        self.assertEqual(self.call('POST', '/api/remove-voice', body, origin='https://elsewhere.invalid')[0], 403)
        with self.app.router.lock:
            self.assertEqual(self.call('POST', '/api/remove-voice', body)[0], 409)
        self.assertIn('custom_first', self.app.router.bank['routes'])
        self.assertEqual(self.call('POST', '/api/remove-voice', {'character': 'spike'})[0], 400)
        code, raw = self.call('POST', '/api/remove-voice', body)
        self.assertEqual(code, 200, raw)
        self.assertNotIn('custom_first', [row['id'] for row in json.loads(raw)['characters']])
        self.assertIs(self.app.router.bank, self.app.bank)
        self.assertNotIn('custom_first', self.app.router.bank['routes'])
        self.assertEqual(self.call('POST', '/tts', {'character_id': 'custom_first', 'text': 'Hello.'})[0], 400)
        self.assertEqual(self.call('POST', '/tts', {'character_id': 'custom_second', 'text': 'Hello.'})[0], 200)
        self.assertTrue(self.app.router.lock.acquire(timeout=2)); self.app.router.lock.release()
        self.assertEqual(self.call('POST', '/api/undo', {})[0], 200)
        self.assertEqual(self.call('POST', '/tts', {'character_id': 'custom_first', 'text': 'Hello.'})[0], 200)
        self.assertTrue(self.app.router.lock.acquire(timeout=2)); self.app.router.lock.release()
        self.job('unload')
        self.assertEqual(self.call('POST', '/api/remove-voice', body)[0], 200)
        self.assertEqual(self.app.phase, 'unloaded')


class CatalogChecks(unittest.TestCase):
    def test_only_pinned_family_is_compatible(self):
        self.assertTrue(compatible(CATALOG['q8_0']['sha256'], CATALOG['f16']['sha256']))
        self.assertFalse(compatible(CATALOG['q8_0']['sha256'], '0' * 64))
        self.assertTrue(compatible('0' * 64, '0' * 64))
        self.assertGreater(CATALOG['f16']['bytes'], 5 * 1024**3)

    def test_download_passes_catalog_bound_and_verifies(self):
        from breeze_pny.models import download
        with tempfile.TemporaryDirectory() as directory, patch('breeze_pny.models.acquire') as fetch:
            download(Path(directory), 'f16')
            self.assertEqual(fetch.call_args.args[3], CATALOG['f16']['bytes'])

    def test_cancelled_download_keeps_previous_file_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); source = root / 'source'; target = root / 'model'
            source.write_bytes(b'new'); target.write_bytes(b'previous')
            cancelled = threading.Event(); cancelled.set()
            with self.assertRaises(InterruptedError): acquire(source, target, sha(source), cancelled=cancelled)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertFalse((root / 'model.partial').exists())


class InstallerChecks(unittest.TestCase):
    def test_update_preserves_q4_personal_reference_and_ports(self):
        import argparse
        import importlib.util
        root = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location('companion_installer_test', root / 'installer/install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as directory:
            fixture = CompanionFixture(Path(directory))
            app = fixture.app
            try:
                app.load_model('q4_k')
                prepared = app.prepare('derpy_hooves', 'Personal reference.', WAV)
                app.audition('derpy_hooves', 'Hello.', prepared['id']); app.apply(prepared['id'])
                voice = app.bank['routes']['derpy_hooves']['voice_id']
                added = app.prepare('custom_narrator', 'My words.', WAV, name='My narrator')
                app.audition('custom_narrator', 'Hello.', added['id']); app.apply(added['id'])
                app.unload_model(); app.close()
                write_json(fixture.root / 'installation.json', {'schema':1, 'complete':True, 'version':'0.2.1'})
                runtime = fixture.root / 'runtime'; runtime.mkdir()
                (runtime/'native').write_bytes(b'fixture runtime')
                write_json(runtime/'runtime.json', {'schema':1,'id':'test','platform':installer.platform_id(),
                           'adapter_selection':True,'entrypoint':'native','files':{'native':sha(runtime/'native')}})
                args = argparse.Namespace(prefix=fixture.root, update=True, runtime_bundle='runtime',runtime_sha256=None,
                    voice_pack='bank',voice_pack_sha256=None,release_base_url=None,model=None,model_file=None,python=None)
                def read(path):
                    if path == root / 'installer/assets.json': return {'breeze_q8':CATALOG['q8_0']}
                    return read_json(path)
                with patch.object(installer,'read_json',side_effect=read), patch.object(installer,'bundle',side_effect=lambda src,digest,prefix,category: runtime if category=='runtimes' else fixture.root/'assets/voice-packs/stock'), patch.object(installer.subprocess,'run'):
                    installer.install(args)
                installed = read_json(app.config_path)
                self.assertEqual(installed['model_sha256'], CATALOG['q4_k']['sha256'])
                self.assertEqual((installed['port'],installed['native_port']),(18792,18797))
                self.assertFalse(installed['autoload'])
                bank = read_json(fixture.root / installed['voice_pack'] / 'voice-pack.json')
                self.assertEqual(bank['custom_voices']['derpy_hooves'], voice)
                self.assertEqual((fixture.root/installed['voice_pack']/bank['voices'][voice]['reference_file']).read_bytes(), WAV)
                self.assertEqual(bank['custom_characters'], ['custom_narrator'])
                self.assertEqual(next(row['name'] for row in bank['characters'] if row['id'] == 'custom_narrator'), 'My narrator')
                args.model = 'q8_0'
                with patch.object(installer,'read_json',side_effect=read), patch.object(installer,'bundle',side_effect=lambda src,digest,prefix,category: runtime if category=='runtimes' else fixture.root/'assets/voice-packs/stock'), patch.object(installer.subprocess,'run'):
                    installer.install(args)
                self.assertEqual(read_json(app.config_path)['model_sha256'], CATALOG['q8_0']['sha256'])
            finally: fixture.close()


if __name__ == '__main__': unittest.main()
