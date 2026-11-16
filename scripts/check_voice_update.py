#!/usr/bin/env python3
"""Compare a candidate companion with an existing lab without loading a model."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.bank import load_bank
from breeze_pny.router import Router, Server, handler

CASES = [('pinkie_pie', 'Gasp! A whole mountain of frosting!'),
         ('rainbow_dash', 'Gasp! Are you alright?'),
         ('derpy_hooves', 'Hehe! It was a very silly adventure!'),
         ('lemon_hearts', 'Teehee! You are thoughtful!')]


def request(url, character, text):
    body = json.dumps(dict(character_id=character, text=text)).encode()
    for attempt in range(20):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, {'Content-Type': 'application/json'}), timeout=120) as response:
                raw = response.read()
            break
        except urllib.error.HTTPError as error:
            code = error.code; error.close()
            if code != 503 or attempt == 19:
                raise
            # A response may arrive just before the prior worker releases its lock.
            time.sleep(.1)
    if url.endswith('/tts'):
        with wave.open(io.BytesIO(raw)) as wav:
            assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
            return wav.readframes(wav.getnframes())
    at, chunks = 0, []
    while True:
        length, = struct.unpack_from('<I', raw, at); at += 4
        if not length: break
        assert length % 2 == 0 and length <= 65536 and at + length <= len(raw)
        chunks.append(raw[at:at + length]); at += length
    pcm = b''.join(chunks)
    assert pcm and raw[at:] == struct.pack('<I', len(pcm)) + hashlib.sha256(pcm).digest()
    return pcm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voice-pack', type=Path, required=True, help='Verified extracted candidate pack')
    parser.add_argument('--native-port', type=int, default=18797)
    parser.add_argument('--lab-url', default='http://127.0.0.1:18792')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bank = load_bank(args.voice_pack)
    with urllib.request.urlopen(f'http://127.0.0.1:{args.native_port}/v1/voices') as response:
        voices = {v['id']: v for v in json.load(response)}
    for name, info in bank['voices'].items():
        assert voices[name]['metadata']['reference_sha256'] == info['reference_sha256'], name
        assert voices[name]['ref_text'] == info['ref_text'], name
    args.output.mkdir(parents=True, exist_ok=False)
    server = Server(('127.0.0.1', 0), handler(Router(bank, args.native_port)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    receipt = dict(complete=False, characters=len(bank['routes']), verified_references=len(bank['voices']), cases=[])
    try:
        for character, text in CASES:
            request(args.lab_url.rstrip('/') + '/tts', character, text)  # Warm native generation for this shape.
            wav = request(url + '/tts', character, text)
            stream = request(url + '/tts/stream', character, text)
            lab = request(args.lab_url.rstrip('/') + '/tts', character, text)
            assert wav == stream == lab, character + ' differs from deployed lab or transport'
            receipt['cases'].append(dict(character=character, pcm_sha256=hashlib.sha256(lab).hexdigest(),
                                         seconds=len(lab) / 48000, matches_live_lab=True))
            print('Matched deployed lab and WAV/PCM: ' + character, flush=True)
        receipt['complete'] = True
    finally:
        server.shutdown(); server.server_close(); thread.join()
        (args.output / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Complete: all cached references and four real voice paths verified.', flush=True)


if __name__ == '__main__':
    main()
