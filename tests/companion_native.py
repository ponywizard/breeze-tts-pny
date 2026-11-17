"""Opt-in real-model matrix for a disposable Companion installation."""
import argparse
import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.companion import Companion
from breeze_pny.files import write_json
from breeze_pny.models import CATALOG, model_path
from breeze_pny.router import Server, handler
from breeze_pny.web import create_server
from breeze_pny.__main__ import smoke

VOICES = ['applejack', 'fluttershy', 'pinkie_pie', 'rainbow_dash', 'rarity', 'twilight_sparkle', 'derpy_hooves']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Disposable installation; selected model will change')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models', nargs='+', default=list(CATALOG))
    parser.add_argument('--wait-downloads', type=int, default=0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = Companion(args.config)
    web, token = create_server(app, 0)
    api = Server(('127.0.0.1', 0), handler(app.router))
    threads = []
    for server in (web, api):
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start(); threads.append(t)
    report = {'complete': False, 'models': [], 'platform': sys.platform}
    def request(method, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', web.server_port, timeout=180)
        headers = {'X-Breeze-Token': token, 'Content-Type': 'application/json'}
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse(); raw = response.read(); code = response.status
        connection.close()
        if code >= 400: raise RuntimeError(f'{path}: {code}: {raw[:300]!r}')
        return raw
    try:
        for identity in args.models:
            path = model_path(app.prefix, CATALOG[identity])
            deadline = time.monotonic() + args.wait_downloads
            while not path.is_file() and time.monotonic() < deadline:
                time.sleep(2)
            print('Checking model:', identity, flush=True)
            request('POST', '/api/models', {'action':'load','model':identity})
            app.worker.join(360)
            if app.worker.is_alive() or app.job['status'] != 'complete': raise RuntimeError(str(app.job))
            result = {'id': identity, 'sha256': CATALOG[identity]['sha256'], 'voices': [], 'all_references_verified_at_load': len(app.bank['voices'])}
            report['models'].append(result)
            for voice in VOICES:
                text = 'Gasp! Hello there. Teehee! It is good to see you.' if voice == 'pinkie_pie' else 'Hello there! It is good to see you again.'
                # Warm native shape caches before recording WAV generation time.
                request('POST', '/tts', {'character_id':voice,'text':text})
                started = time.monotonic()
                raw = request('POST', '/tts', {'character_id':voice,'text':text})
                elapsed = time.monotonic() - started
                with wave.open(io.BytesIO(raw)) as wav:
                    assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) == (1,2,24000)
                    pcm = wav.readframes(wav.getnframes()); seconds = len(pcm)/48000
                    assert seconds > 0
                (args.output / (identity + '-' + voice + '.wav')).write_bytes(raw)
                streamed = smoke(f'http://127.0.0.1:{api.server_port}', voice)
                expected = app.bank['routes'][voice]['settings'].get('lora') or 'base'
                assert streamed['adapter'] == expected
                result['voices'].append({'character':voice,'adapter':expected,'wav_seconds':seconds,'generation_seconds':elapsed,
                                         'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'stream_seconds':streamed['audio_seconds']})
                write_json(args.output/'results.json',report)
                print(' ',identity,voice,expected,round(seconds,2),'seconds',flush=True)
            # Reference manager preview uses the same model and current voice settings.
            preview = request('POST', '/api/audition', {'character':'pinkie_pie','text':'Teehee! Hello there.'})
            assert preview[:4] == b'RIFF'
            request('POST','/api/models',{'action':'unload'}); app.worker.join(30)
            assert app.job['status'] == 'complete' and not app.healthy()
            assert json.loads(request('GET','/api/state'))['phase'] == 'unloaded'
            result['unload_and_ui'] = True
            write_json(args.output/'results.json',report)
        report['complete'] = True
    finally:
        for server,t in zip((web,api),threads): server.shutdown(); server.server_close(); t.join()
        app.close()
        write_json(args.output/'results.json',report)
    print('PASS: model matrix, six adapters, base voice, reference preview, WAV/stream, unload',flush=True)


if __name__ == '__main__': main()
