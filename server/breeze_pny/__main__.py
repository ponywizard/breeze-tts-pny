import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import time
import urllib.request
import wave
from .files import OPENER
from .native import CONTENT_TYPE, MAX_PCM
from .service import get, inspect, serve


def smoke(url, character, output=None):
    request = urllib.request.Request(url.rstrip('/') + '/tts/stream',
        json.dumps({'character_id': character, 'text': 'Hello! It is good to see you again.'}).encode(),
        {'Content-Type': 'application/json'})
    started, first = time.monotonic(), None
    with OPENER.open(request, timeout=120) as response:
        content_type = response.headers.get_content_type()
        if content_type == CONTENT_TYPE:
            wire, pcm, receipt = bytearray(), bytearray(), False
            while chunk := response.read1(4096):
                if first is None: first = time.monotonic() - started
                if receipt: raise ValueError('Data after final receipt')
                wire.extend(chunk)
                while len(wire) >= 4:
                    size = struct.unpack_from('<I', wire)[0]
                    if size == 0:
                        if len(wire) < 40: break
                        count = struct.unpack_from('<I', wire, 4)[0]
                        if count != len(pcm) or wire[8:40] != hashlib.sha256(pcm).digest(): raise ValueError('Bad stream receipt')
                        del wire[:40]; receipt = True
                        if wire: raise ValueError('Trailing stream data')
                        break
                    if size % 2 or size > 65536 or len(pcm) + size > MAX_PCM: raise ValueError('Invalid frame size')
                    if len(wire) < size + 4: break
                    pcm.extend(wire[4:size + 4]); del wire[:size + 4]
            if not receipt or wire or not pcm: raise ValueError('Incomplete speech')
            result = io.BytesIO()
            with wave.open(result, 'wb') as wav:
                wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); wav.writeframes(pcm)
            raw = result.getvalue()
        elif content_type == 'audio/wav': raw = response.read(12 * 1024**2 + 1)
        else: raise ValueError('Unexpected audio content type')
        adapter = response.headers.get('X-Breeze-Adapter')
    if len(raw) > 12 * 1024**2: raise ValueError('WAV too large')
    with wave.open(io.BytesIO(raw)) as wav:
        seconds = wav.getnframes() / wav.getframerate()
        if seconds <= 0: raise ValueError('Empty audio')
    if output: Path(output).write_bytes(raw)
    return {'character': character, 'transport': content_type, 'audio_seconds': seconds,
            'first_response_s': first, 'elapsed_s': time.monotonic() - started, 'adapter': adapter}


def main():
    parser = argparse.ArgumentParser(description='Breeze TTS PNY companion server')
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('serve', 'doctor', 'voices'):
        sub = commands.add_parser(name); sub.add_argument('--config', type=Path, default=os.environ.get('BREEZE_PNY_CONFIG'))
        if name == 'serve':
            sub.add_argument('--host'); sub.add_argument('--port', type=int); sub.add_argument('--native-port', type=int)
    sub = commands.add_parser('voice-library', help='Open the local reference browser and replacement wizard')
    from . import REFERENCE_MANAGER_VERSION
    sub.add_argument('--version', action='version', version='Reference Management Utility ' + REFERENCE_MANAGER_VERSION)
    sub.add_argument('--config', type=Path, default=os.environ.get('BREEZE_PNY_CONFIG'))
    sub.add_argument('--port', type=int, default=0, help='Local browser port (default: choose an available port)')
    sub.add_argument('--reference-directory', type=Path, help='Optional original <voice_id>.wav recordings; hashes must match the pack')
    sub.add_argument('--no-browser', action='store_true', help='Print the local link without opening a browser')
    sub = commands.add_parser('smoke')
    sub.add_argument('--url', default='http://127.0.0.1:18792')
    sub.add_argument('--character', default='twilight_sparkle'); sub.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action != 'smoke' and args.config is None: parser.error('Supply --config or use the installed launcher')
    try:
        if args.action == 'serve': serve(args.config, args.host, args.port, args.native_port)
        elif args.action == 'voice-library':
            from .voice_library import run
            run(args.config, args.port, args.reference_directory, not args.no_browser)
        elif args.action == 'smoke': print(json.dumps(smoke(args.url, args.character, args.output), indent=2))
        else:
            config, root, runtime, binary, model, bank_root, bank = inspect(args.config)
            if args.action == 'doctor':
                print(json.dumps({'ok': True, 'voice_pack': bank['id'], 'characters': len(bank['routes']),
                                  'runtime': runtime['id'], 'model_sha256': config['model_sha256'],
                                  'note': 'Files/dependencies checked; run serve and smoke to verify GPU synthesis.'}, indent=2))
            else:
                for identity, row in sorted(bank['routes'].items()): print(identity, row['route'])
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print('breeze-pny: ' + str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
