#!/usr/bin/env python3
"""Clone slower Pinkie references, then apply the reciprocal playback speed.

Uses only rational sample-rate conversion (NumPy/SciPy), changing pitch and
duration together. Shares reference registration and audio helpers with the
pitch experiment; never uses its SoX pitch effect.
"""
import argparse
import copy
from fractions import Fraction
import html
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

import numpy as np
import scipy
from scipy.signal import resample_poly

from experiment_pinkie_pitch import (
    TEXTS, audio_info, comparison, register, save_json, wav_data,
)
from breeze_pny.files import sha
from breeze_pny.native import NativePCM
from breeze_pny.platforms import runtime_environment
from breeze_pny.service import get, inspect
from breeze_pny.voice_edit import pcm_wav


def varispeed(source, target, speed):
    """Render playback at `speed` into a 24 kHz WAV, with no time stretching."""
    speed = Fraction(speed)
    _, samples = wav_data(source)
    # Playback at speed p/q requires q/p times as many samples at fixed 24 kHz.
    rendered = resample_poly(np.asarray(samples, dtype=np.float64),
                             speed.denominator, speed.numerator,
                             window=('kaiser', 10.0))
    quantized = np.rint(rendered)
    if np.any(quantized < -32768) or np.any(quantized > 32767):
        raise ValueError('Resampling would clip: ' + str(target))
    target.write_bytes(pcm_wav(quantized.astype('<i2').tobytes()))
    result = audio_info(target)
    expected = len(samples) / (24000 * float(speed))
    if abs(result['seconds'] - expected) > 1 / 24000 + 1e-9:
        raise ValueError('Unexpected playback duration: ' + str(target))
    return {'speed_factor': float(speed), 'speed_fraction': str(speed),
            'resample_up': speed.denominator, 'resample_down': speed.numerator,
            **result}


def rate_label(rate):
    return 'Original reference' if rate == 1 else f'{(1-rate)*100:.0f}% slower reference'


def report(out, receipt):
    def player(path):
        name = html.escape(path, quote=True)
        return f'<audio controls preload="none" src="{name}"></audio> <a href="{name}">WAV</a>'
    parts = ['<h2>Listening sweeps</h2><p>Each experimental output has the reciprocal '
             'playback speed applied. Static level matching; 0.75 seconds between clips.</p>']
    for item in receipt['sweeps']:
        text_index = item['text_index']
        order = ' → '.join(rate_label(g['reference_speed']) for g in item['gain_adjustments'])
        model_label = 'Base model (LoRA disabled)' if item['adapter'] == 'base' else 'Pinkie LoRA'
        parts.append(f'<p><strong>Line {text_index} — {model_label}</strong></p>'
                     f'<p>{html.escape(receipt["texts"][text_index - 1])}</p>'
                     f'<p>Order: {html.escape(order)}</p>' + player(item['file']))
    parts.append('<details><summary>Reference controls</summary><p>Round trips apply the inverse speed directly to '
                 'the slowed recording, without synthesis, to isolate resampling artifacts.</p>'
                 '<table><tr><th>Reference speed</th><th>Input to Breeze</th><th>Direct round trip</th></tr>')
    for ref in receipt['references']:
        if receipt['skip_baseline'] and ref['speed'] == 1:
            continue
        restored = player(ref['roundtrip_file']) if ref.get('roundtrip_file') else '—'
        parts.append(f'<tr><td>{html.escape(rate_label(ref["speed"]))} ({ref["speed"]:.1f}×)</td>'
                     f'<td>{player(ref["file"])}</td><td>{restored}</td></tr>')
    parts.append('</table></details>')
    for index, text in enumerate(receipt['texts'], 1):
        parts.append(f'<h2>Line {index}</h2><p>{html.escape(text)}</p>'
                     '<table><tr><th>Model</th><th>Reference / output speed</th>'
                     '<th>Raw synthesis</th><th>Reciprocal speed applied</th></tr>')
        for sample in receipt['samples']:
            if sample['text_index'] != index:
                continue
            parts.append(f'<tr><td>{sample["adapter"]}</td>'
                         f'<td>{sample["reference_speed"]:.1f}× / {sample["output_speed"]:.5f}×</td>'
                         f'<td>{player(sample["raw_file"])}</td><td>{player(sample["restored_file"])}</td></tr>')
        parts.append('</table>')
    (out / 'listen.html').write_text('<!doctype html><meta charset="utf-8">'
        '<title>Pinkie playback speed experiment</title>'
        '<style>body{font:16px system-ui;max-width:1250px;margin:2rem auto;padding:0 1rem;background:#faf8fb;color:#28202c}'
        'td,th{padding:.6rem;border-bottom:1px solid #ddd;text-align:left}audio{width:290px;vertical-align:middle}'
        'table{border-collapse:collapse}a{color:#7a2864}</style>'
        '<h1>Pinkie playback speed experiment</h1><p>Slow the exact curated reference, clone with Breeze, '
        'then speed the synthesis up. Uses rational sample-rate conversion; pitch and duration change together. '
        'Same Q8 model, seed 42 and inference settings across conditions.</p>'
        '<p>' + '; '.join(f'Reference {rate:.1f}× → output {1/rate:.5f}×' for rate in receipt['requested_speeds'])
        + '.</p>' + ''.join(parts)
        + '<script>document.addEventListener("play",e=>{document.querySelectorAll("audio").forEach(a=>{if(a!==e.target)a.pause()})},true)</script>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--speeds', type=Fraction, nargs='+',
                        default=[Fraction(9, 10), Fraction(4, 5), Fraction(7, 10)],
                        help='Reference playback speeds, e.g. 0.7 0.6 0.5')
    parser.add_argument('--adapters', choices=['base', 'pinkie'], nargs='+', default=['base', 'pinkie'])
    parser.add_argument('--no-baseline', action='store_true', help='Skip 1x synthesis comparisons')
    parser.add_argument('--text', action='append', help='Audition text; repeat for multiple lines')
    args = parser.parse_args()
    if len(set(args.speeds)) != len(args.speeds) or any(not 0 < r < 1 or r.denominator > 1000 for r in args.speeds):
        parser.error('Use distinct reference speeds between 0 and 1 with denominators up to 1000')
    texts = args.text or TEXTS
    if any(not text.strip() or len(text) > 600 for text in texts):
        parser.error('Audition lines must contain 1–600 characters')
    adapters = list(dict.fromkeys(args.adapters))
    config, _, runtime, binary, model, bank_root, bank = inspect(args.config)
    pinkie = next(row for row in bank['characters'] if row['id'] == 'pinkie_pie')
    info = bank['voices'][pinkie['voice_id']]
    reference = args.reference.resolve()
    if sha(reference) != info['reference_sha256']:
        raise ValueError('Reference is not the exact curated recording')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    voices = out / 'voices'
    voices.mkdir()
    shutil.copy2(bank_root / info['file'], voices / (pinkie['voice_id'] + '.breeze'))
    shutil.copy2(reference, out / 'reference-original.wav')
    receipt = {'schema': 1, 'complete': False,
               'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'config': str(args.config.resolve()), 'reference_source': str(reference),
               'reference_sha256': info['reference_sha256'], 'reference_transcript': info['ref_text'],
               'model_sha256': config['model_sha256'], 'runtime': runtime,
               'adapter_sha256': {'pinkie': sha(bank_root / bank['adapters']['pinkie'])} if 'pinkie' in adapters else {},
               'script_sha256': sha(Path(__file__)),
               'helper_sha256': sha(Path(__file__).with_name('experiment_pinkie_pitch.py')),
               'processing': 'scipy.signal.resample_poly; Kaiser beta 10; pitch and duration change together',
               'numpy_version': np.__version__,
               'scipy_version': scipy.__version__,
               'seed': 42, 'settings': {k: v for k, v in pinkie['settings'].items() if k != 'lora'}, 'texts': texts,
               'requested_speeds': [float(rate) for rate in args.speeds], 'requested_adapters': adapters,
               'skip_baseline': args.no_baseline,
               'references': [{'speed': 1, 'file': 'reference-original.wav', **audio_info(reference)}],
               'samples': [], 'sweeps': []}
    rates = args.speeds
    for rate in rates:
        percent = round((1-rate)*100)
        lowered = out / f'reference-slower-{percent}.wav'
        lowered_info = varispeed(reference, lowered, rate)
        restored = out / f'reference-slower-{percent}-roundtrip.wav'
        restored_info = varispeed(lowered, restored, 1/rate)
        receipt['references'].append({'speed': float(rate), 'file': lowered.name,
                                      'roundtrip_file': restored.name, 'roundtrip': restored_info,
                                      **lowered_info})
    save_json(out / 'results.json', receipt)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = [str(binary), str(model), '--host', '127.0.0.1', '--port', str(port),
               '--ws-port', '-1', '--parallel', '1', '--voices-dir', str(voices)]
    if 'pinkie' in adapters:
        command += ['--lora', 'pinkie=' + str(bank_root / bank['adapters']['pinkie'])]
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
        print('Native engine ready; registering slower references.', flush=True)
        for ref in receipt['references'][1:]:
            percent = round((1-ref['speed'])*100)
            voice = f'pinkie_slower_{percent}'
            ref['registration'] = register(port, voice, out / ref['file'], info['ref_text'], voices)
            ref['cache_sha256'] = sha(voices / (voice + '.breeze'))
        conditions = ([] if args.no_baseline else [(adapter, Fraction(1)) for adapter in adapters]) + [
            (adapter, rate) for adapter in adapters for rate in rates]
        for index, text in enumerate(texts, 1):
            for adapter, rate in conditions:
                percent = round((1-rate)*100)
                row = copy.deepcopy(pinkie)
                row['settings']['lora'] = '' if adapter == 'base' else adapter
                if rate != 1:
                    row['voice_id'] = f'pinkie_slower_{percent}'
                raw = out / f'line-{index:02d}-{adapter}-slower-{percent}-raw.wav'
                started = time.monotonic()
                with NativePCM(port, row, text) as reader:
                    pcm = b''.join(reader.chunks())
                raw.write_bytes(pcm_wav(pcm))
                sample = {'text_index': index, 'adapter': adapter, 'reference_speed': float(rate),
                          'output_speed': float(1/rate), 'voice_id': row['voice_id'],
                          'settings': row['settings'], 'raw_file': raw.name, 'raw': audio_info(raw),
                          'generation_seconds': time.monotonic() - started,
                          'acknowledged_adapter': reader.adapter}
                restored = out / f'line-{index:02d}-{adapter}-slower-{percent}-restored.wav'
                if rate == 1:
                    shutil.copy2(raw, restored)
                    sample['restored'] = audio_info(restored)
                else:
                    sample['restored'] = varispeed(raw, restored, 1/rate)
                sample['restored_file'] = restored.name
                receipt['samples'].append(sample)
                save_json(out / 'results.json', receipt)
                print(f'Line {index}, {adapter}, reference {float(rate):.1f}x: '
                      f'{sample["raw"]["seconds"]:.2f}s raw, {sample["restored"]["seconds"]:.2f}s restored', flush=True)
            for adapter in adapters:
                sweep_samples = [s for s in receipt['samples'] if s['text_index'] == index and s['adapter'] == adapter]
                name = f'line-{index:02d}-{adapter}-speed-sweep.wav'
                gains = comparison([out/s['restored_file'] for s in sweep_samples], out/name)
                for gain, sample in zip(gains, sweep_samples):
                    gain['condition'] = rate_label(sample['reference_speed']) + ', reciprocal output speed'
                    gain['reference_speed'] = sample['reference_speed']
                receipt['sweeps'].append({'file': name, 'text_index': index, 'adapter': adapter, 'gain_adjustments': gains})
        report(out, receipt)
        receipt['complete'] = True
        print('Complete: ' + str(out / 'listen.html'), flush=True)
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
