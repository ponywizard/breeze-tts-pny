#!/usr/bin/env python3
"""Qualify an installed companion on isolated ports; always stop its owned process."""
import argparse
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
MOD_VERSION = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())['version']
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.service import get
from breeze_pny.__main__ import smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18882)
    parser.add_argument('--native-port', type=int, default=18887)
    parser.add_argument('--game', type=Path, help='Optional isolated exported game directory, prepared by verify.py')
    parser.add_argument('--mod-pack', type=Path, default=ROOT / f'dist/breeze_tts_pny-{MOD_VERSION}-linux-x86_64.pck')
    parser.add_argument('--save-audio', action='store_true')
    args = parser.parse_args()
    run = args.output.resolve(); run.mkdir(parents=True, exist_ok=False)
    launcher = str(args.launcher.resolve())
    url = 'http://127.0.0.1:' + str(args.port)
    results, child = {}, None
    try:
        with (run / 'service.log').open('w') as log:
            child = subprocess.Popen([launcher, 'serve', '--port', str(args.port), '--native-port', str(args.native_port)],
                                     stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        while True:
            if child.poll() is not None: raise RuntimeError((run / 'service.log').read_text()[-6000:])
            try:
                health = get(url + '/health')
                if health['ready']: break
            except (OSError, ValueError): pass
            if time.monotonic() > deadline: raise TimeoutError('Server startup timed out')
            time.sleep(.25)
        results['health'] = health
        print('READY', health, flush=True)
        duplicate = subprocess.run([launcher, 'serve'], capture_output=True, text=True, timeout=15)
        if duplicate.returncode == 0 or 'already running' not in duplicate.stderr:
            raise RuntimeError('Duplicate start was not rejected')
        results['duplicate_start_rejected'] = True
        results['speech'] = []
        for name in ['twilight_sparkle', 'rainbow_dash', 'pinkie_pie', 'applejack', 'fluttershy', 'rarity', 'spike', 'nurse_redheart', 'angel_wings', 'marble_pie']:
            result = smoke(url, name, run / (name + '.wav') if args.save_audio else None)
            expected = {'twilight_sparkle': 'twilight', 'rainbow_dash': 'rainbow', 'pinkie_pie': 'pinkie', 'applejack': 'applejack', 'fluttershy': 'fluttershy', 'rarity': 'rarity'}.get(name, 'base')
            if result['transport'] != 'application/vnd.home-equestria.pcm-stream': raise RuntimeError('Expected Breeze PCM: ' + name)
            if result['adapter'] != expected: raise RuntimeError('Unexpected adapter: ' + name)
            results['speech'].append(result); print(result, flush=True)
        connection = http.client.HTTPConnection('127.0.0.1', args.port, timeout=30)
        try:
            text = 'We have quite a lot to discuss today. ' + 'Let us take a walk around the village and talk about our plans. ' * 5
            connection.request('POST', '/tts/stream', json.dumps({'character_id': 'twilight_sparkle', 'text': text}),
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200 or not response.read1(256): raise RuntimeError('Cancellation sample did not start')
            start = time.monotonic(); response.close()
        finally: connection.close()
        while True:
            try:
                result = smoke(url, 'spike'); break
            except urllib.error.HTTPError as error:
                if error.code != 503 or time.monotonic() - start > 8: raise
                time.sleep(.1)
        results['cancel_then_retry_s'] = time.monotonic() - start
        results['retry'] = result
        if args.game:
            game = args.game.resolve()
            user = run / 'user'
            mods = user / 'home-equestria-public/mods'; mods.mkdir(parents=True)
            shutil.copy2(args.mod_pack, mods / args.mod_pack.name)
            env = {**os.environ, 'XDG_DATA_HOME': str(user)}
            for key in ('EQ_PCM_STREAM', 'EQ_PCM_PLAYBACK', 'EQ_TALKING_AVATAR'): env.pop(key, None)
            result = subprocess.run([str(game / 'HomeEquestria.x86_64'), '--headless', '--audio-driver', 'Dummy',
                                     '--xr-mode', 'off', '--script', str(ROOT / 'tests/live_server.gd'), '--', str(args.port)],
                                    cwd=game, env=env, capture_output=True, text=True, timeout=90)
            log = result.stdout + result.stderr; (run / 'game.log').write_text(log)
            if result.returncode or 'SCRIPT ERROR' in log or 'BREEZE_LIVE_SERVER_DONE failures=0' not in log:
                raise RuntimeError(log)
            results['packaged_game'] = True
        results['passed'] = True
    finally:
        if child is not None and child.poll() is None:
            child.send_signal(signal.SIGTERM)
            try: child.wait(timeout=20)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        if child: results['server_exit_code'] = child.returncode
        (run / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    if child.returncode: raise RuntimeError((run / 'service.log').read_text()[-6000:])
    print('PASS: installed companion, base/all six adapters/new reference voices, cancellation, duplicate guard and shutdown', flush=True)


if __name__ == '__main__': main()
