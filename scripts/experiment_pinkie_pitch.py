#!/usr/bin/env python3
"""Audition lowered Pinkie references with inverse pitch shifts after synthesis.

Runs an isolated native server and saves audio/receipts without changing the
installed voice pack. Requires SoX and an installed companion with Pinkie's LoRA.
"""
import argparse
from array import array
import copy
import html
import http.client
import json
import math
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.files import sha
from breeze_pny.native import NativePCM
from breeze_pny.platforms import runtime_environment
from breeze_pny.service import get, inspect
from breeze_pny.voice_edit import pcm_wav

TEXTS = [
    "Hi! I'm Pinkie Pie. I made cupcakes for everypony, and saved an extra one for you!",
    "I know things have been difficult lately. You don't have to figure it all out today. I'll be right here with you.",
]


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def wav_data(path):
    with wave.open(str(path), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
            raise ValueError('Expected mono 24 kHz PCM16: ' + str(path))
        raw = wav.readframes(wav.getnframes())
    samples = array('h', raw)
    if sys.byteorder != 'little':
        samples.byteswap()
    return raw, samples


def audio_info(path):
    raw, samples = wav_data(path)
    if not samples:
        raise ValueError('Empty audio: ' + str(path))
    rms = math.sqrt(sum(float(s) ** 2 for s in samples) / len(samples))
    return {'sha256': sha(path), 'seconds': len(raw) / 48000,
            'peak_dbfs': 20 * math.log10(max(1, max(abs(s) for s in samples)) / 32768),
            'rms_dbfs': 20 * math.log10(max(1e-12, rms) / 32768),
            'clipped_samples': sum(abs(s) >= 32767 for s in samples)}


def shift(source, target, semitones):
    # SoX shifts the spectral envelope too; no separate formant preservation.
    command = ['sox', '-D', str(source), '-b', '16', str(target),
               'pitch', str(semitones * 100), 'rate', '-v', '24000']
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    before, after = audio_info(source), audio_info(target)
    if abs(before['seconds'] - after['seconds']) > .02:
        raise ValueError('Pitch shifting changed the audio duration')
    return {'command': command, 'stderr': result.stderr, **after}


def register(port, voice, reference, transcript, voices):
    boundary = 'pinkie-pitch-experiment-boundary'
    digest = sha(reference)
    body = bytearray()
    for name, value in {'name': voice, 'ref_text': transcript,
                        'metadata': json.dumps({'reference_sha256': digest})}.items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="ref_audio"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
    body.extend(reference.read_bytes())
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=180)
    try:
        connection.request('POST', '/v1/voices', bytes(body),
                           {'Content-Type': 'multipart/form-data; boundary=' + boundary})
        response = connection.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError('Reference registration failed: ' + str(result))
    finally:
        connection.close()
    if (result.get('id'), result.get('ref_text'), result.get('saved'),
        result.get('metadata', {}).get('reference_sha256')) != (voice, transcript, True, digest):
        raise ValueError('Reference registration acknowledgement mismatch')
    if not (voices / (voice + '.breeze')).is_file():
        raise ValueError('Reference cache was not saved')
    return result


def comparison(source_paths, destination):
    """Match each clip to -22 dBFS RMS with -2 dBFS peak headroom; no dynamics."""
    chunks, gains = [], []
    for path in source_paths:
        _, samples = wav_data(path)
        rms = math.sqrt(sum(float(s) ** 2 for s in samples) / len(samples))
        gain = min(32768 * 10 ** (-22 / 20) / max(1e-12, rms),
                   32768 * 10 ** (-2 / 20) / max(1, max(abs(s) for s in samples)))
        adjusted = array('h', (round(s * gain) for s in samples))
        if sys.byteorder != 'little':
            adjusted.byteswap()
        chunks.append(adjusted.tobytes())
        gains.append({'file': path.name, 'gain_db': 20 * math.log10(gain)})
    destination.write_bytes(pcm_wav((b'\0\0' * 18000).join(chunks)))
    return gains


def report(out, receipt, filename='index.html'):
    def player(path):
        escaped = html.escape(path, quote=True)
        return f'<audio controls preload="none" src="{escaped}"></audio> <a href="{escaped}">WAV</a>'
    rows = []
    for ref in receipt['references']:
        rows.append(f'<tr><td>Reference {ref["semitones"]:+g} semitones</td><td>{player(ref["file"])}</td></tr>')
        if ref.get('roundtrip_file'):
            rows.append(f'<tr><td>Reference {ref["semitones"]:+g} then restored (DSP control)</td><td>{player(ref["roundtrip_file"])}</td></tr>')
    sections = ['<h2>Reference and pitch processing controls</h2><table>' + ''.join(rows) + '</table>']
    for index, text in enumerate(receipt['texts'], 1):
        rows = []
        for sample in receipt['samples']:
            if sample['text_index'] != index:
                continue
            shift_text = f'{sample["reference_semitones"]:+g}'
            rows.append(f'<tr><td>{html.escape(sample["adapter"])} / reference {shift_text} st</td>'
                        f'<td>{player(sample["raw_file"])}</td>'
                        f'<td>{player(sample["restored_file"])}</td></tr>')
        comparison_info = receipt['comparisons'][index - 1]
        order = '; '.join(item['condition'] for item in comparison_info['gain_adjustments'])
        sections.append(f'<h2>Line {index}</h2><p>{html.escape(text)}</p>'
                        f'<p>Comparison: {player(comparison_info["file"])}</p>'
                        f'<p>Order: {html.escape(order)}. '
                        'Comparison clips use static RMS matching with peak headroom; individual WAVs retain their original levels.</p>'
                        '<table><tr><th>Model / reference</th><th>Raw synthesis</th><th>Pitch restored</th></tr>'
                        + ''.join(rows) + '</table>')
    (out / filename).write_text('<!doctype html><meta charset="utf-8"><title>Pinkie pitch experiment</title>'
        '<style>body{font:16px system-ui;max-width:1200px;margin:2rem auto;padding:0 1rem;background:#faf8fb;color:#28202c}'
        'td,th{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}audio{width:290px;vertical-align:middle}'
        'table{border-collapse:collapse}a{color:#7a2864}</style>'
        '<h1>Pinkie pitch experiment</h1><p>Pitch down the exact curated reference, clone, then pitch the result up. '
        'SoX pitch processing preserves duration and shifts the spectral envelope; no separate formant preservation. '
        'Same Q8 model, text, seed 42 and inference settings for every condition. '
        'The current Pinkie LoRA was trained at the original pitch.</p>' + ''.join(sections)
        + '<script>document.addEventListener("play",e=>{document.querySelectorAll("audio").forEach(a=>{if(a!==e.target)a.pause()})},true)</script>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--shifts', type=int, nargs='+', default=[3, 6],
                        help='Semitones to lower the reference, and raise the output (default: 3 6)')
    args = parser.parse_args()
    if len(set(args.shifts)) != len(args.shifts) or any(not 0 < n <= 24 for n in args.shifts):
        parser.error('Pitch shifts must be distinct positive integers up to 24')
    if not shutil.which('sox'):
        parser.error('SoX is required')
    config, prefix, runtime, binary, model, bank_root, bank = inspect(args.config)
    pinkie = next(row for row in bank['characters'] if row['id'] == 'pinkie_pie')
    info = bank['voices'][pinkie['voice_id']]
    reference = args.reference.resolve()
    if sha(reference) != info['reference_sha256']:
        raise ValueError('Reference is not the exact recording used by the curated Pinkie cache')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    voices = out / 'voices'
    voices.mkdir()
    shutil.copy2(bank_root / info['file'], voices / (pinkie['voice_id'] + '.breeze'))
    shutil.copy2(reference, out / 'reference-original.wav')
    receipt = {'schema': 1, 'complete': False, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'config': str(args.config.resolve()), 'reference_source': str(reference),
               'reference_transcript': info['ref_text'], 'reference_sha256': info['reference_sha256'],
               'model_sha256': config['model_sha256'], 'runtime': runtime,
               'script_sha256': sha(Path(__file__)),
               'adapter_sha256': sha(bank_root / bank['adapters']['pinkie']),
               'sox_version': subprocess.check_output(['sox', '--version'], text=True).strip(),
               'seed': 42, 'settings': pinkie['settings'], 'texts': TEXTS,
               'references': [{'semitones': 0, 'file': 'reference-original.wav', **audio_info(reference)}],
               'samples': []}
    for semitones in args.shifts:
        shifted = out / f'reference-down-{semitones}.wav'
        shifted_info = shift(reference, shifted, -semitones)
        roundtrip = out / f'reference-down-{semitones}-restored.wav'
        roundtrip_info = shift(shifted, roundtrip, semitones)
        receipt['references'].append({'semitones': -semitones, 'file': shifted.name,
                                      'roundtrip_file': roundtrip.name,
                                      'roundtrip': roundtrip_info, **shifted_info})
    save_json(out / 'results.json', receipt)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = [str(binary), str(model), '--host', '127.0.0.1', '--port', str(port),
               '--ws-port', '-1', '--parallel', '1', '--voices-dir', str(voices),
               '--lora', 'pinkie=' + str(bank_root / bank['adapters']['pinkie'])]
    receipt['server_command'] = command
    child = None
    try:
        with (out / 'native.log').open('w') as log:
            child = subprocess.Popen(command, env=runtime_environment(binary), stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        while True:
            if child.poll() is not None:
                raise RuntimeError((out / 'native.log').read_text()[-6000:])
            try:
                if get(f'http://127.0.0.1:{port}/health')['status'] == 'ok':
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError('Native startup timed out; inspect native.log')
            time.sleep(.25)
        receipt['adapters'] = get(f'http://127.0.0.1:{port}/v1/adapters')
        print('Native engine ready; registering lowered references.', flush=True)
        for ref in receipt['references'][1:]:
            semitones = -ref['semitones']
            ref['registration'] = register(port, f'pinkie_down_{semitones}', out / ref['file'], info['ref_text'], voices)
            ref['cache_sha256'] = sha(voices / f'pinkie_down_{semitones}.breeze')
        for index, text in enumerate(TEXTS, 1):
            # Put the familiar current voice first in each listening comparison.
            conditions = [('pinkie', 0), ('base', 0)] + [
                (adapter, semitones) for adapter in ('base', 'pinkie') for semitones in args.shifts]
            restored_paths = []
            for adapter, semitones in conditions:
                row = copy.deepcopy(pinkie)
                row['settings']['lora'] = '' if adapter == 'base' else adapter
                if semitones:
                    row['voice_id'] = f'pinkie_down_{semitones}'
                raw_file = out / f'line-{index:02d}-{adapter}-down-{semitones}-raw.wav'
                started = time.monotonic()
                with NativePCM(port, row, text) as reader:
                    pcm = b''.join(reader.chunks())
                raw_file.write_bytes(pcm_wav(pcm))
                sample = {'text_index': index, 'adapter': adapter, 'reference_semitones': -semitones,
                          'voice_id': row['voice_id'], 'settings': row['settings'],
                          'raw_file': raw_file.name, 'raw': audio_info(raw_file),
                          'generation_seconds': time.monotonic() - started,
                          'acknowledged_adapter': reader.adapter}
                restored = out / f'line-{index:02d}-{adapter}-down-{semitones}-restored.wav'
                if semitones:
                    sample['restored'] = shift(raw_file, restored, semitones)
                else:
                    shutil.copy2(raw_file, restored)
                    sample['restored'] = audio_info(restored)
                sample['restored_file'] = restored.name
                restored_paths.append(restored)
                receipt['samples'].append(sample)
                save_json(out / 'results.json', receipt)
                print(f'Line {index}, {adapter}, reference {-semitones:+d} st: '
                      f'{sample["raw"]["seconds"]:.2f}s audio in {sample["generation_seconds"]:.2f}s', flush=True)
            gains = comparison(restored_paths, out / f'line-{index:02d}-comparison.wav')
            for gain, (adapter, semitones) in zip(gains, conditions):
                gain['condition'] = f'{adapter}, reference {-semitones:+d} st, restored'
            receipt.setdefault('comparisons', []).append({
                'file': f'line-{index:02d}-comparison.wav',
                'gain_adjustments': gains})
        report(out, receipt)
        receipt['complete'] = True
        print('Complete: ' + str(out / 'index.html'), flush=True)
    finally:
        if child is not None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        save_json(out / 'results.json', receipt)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    main()
