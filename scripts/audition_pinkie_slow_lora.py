#!/usr/bin/env python3
"""Compare the current Pinkie LoRA with a 0.8x-trained LoRA at 1.25x playback."""
import argparse
import copy
from fractions import Fraction
import html
import json
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

from experiment_pinkie_pitch import audio_info, comparison, register, save_json
from experiment_pinkie_speed import varispeed
from breeze_pny.files import sha
from breeze_pny.native import NativePCM
from breeze_pny.platforms import runtime_environment
from breeze_pny.service import get, inspect
from breeze_pny.voice_edit import pcm_wav

TEXTS = [
    "Surprise! I knew you were coming, so I baked your favorite cupcakes!",
    "Ooh! Ooh! I have an idea! Let's throw a party for everypony in Ponyville!",
    "Surprise! Happy birthday! Wait, is it actually your birthday? Oh well, we can celebrate anyway!",
    "Ooh! Ooh! Pick me! I know the answer! At least, I think I do.",
    "Hi! I'm Pinkie Pie. I made cupcakes for everypony, and saved an extra one for you!",
    "I know things have been difficult lately. You don't have to figure it all out today. I'll be right here with you.",
]


def report(out, receipt):
    def player(path):
        escaped = html.escape(path, quote=True)
        return f'<audio controls preload="none" src="{escaped}"></audio> <a href="{escaped}">WAV</a>'
    sections = []
    for index, text in enumerate(receipt['texts'], 1):
        samples = [s for s in receipt['samples'] if s['text_index'] == index]
        pair = next(c for c in receipt['comparisons'] if c['text_index'] == index)
        sections.append(f'<section><h2>Line {index}</h2><p>{html.escape(text)}</p>'
                        '<p><strong>A → B</strong>: ' + player(pair['file']) + '</p>'
                        '<table><tr><th>Condition</th><th>Listen</th></tr>')
        for sample in samples:
            sections.append(f'<tr><td>{html.escape(sample["label"])}</td><td>{player(sample["file"])}</td></tr>')
        sections.append('</table>')
        slow = next(s for s in samples if s['adapter'] == 'slow080')
        sections.append('<details><summary>Unsped experimental synthesis</summary>'
                        + player(slow['raw_file']) + '</details></section>')
    (out / 'listen.html').write_text('<!doctype html><meta charset="utf-8">'
        '<title>Pinkie: current vs 0.8× LoRA</title><style>'
        'body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#faf8fb;color:#28202c}'
        'section{padding:1rem 0;border-top:1px solid #ddd}td,th{padding:.5rem;text-align:left}'
        'audio{width:340px;vertical-align:middle}a{color:#7a2864}details{margin-top:1rem}</style>'
        '<h1>Pinkie: current vs 0.8× LoRA</h1><p><strong>A:</strong> Current LoRA, original reference, normal output speed. '
        '<strong>B:</strong> Fresh LoRA trained on 0.8× audio, 0.8× reference, output played at 1.25×.</p>'
        '<p>Each A/B WAV plays A first, then B, with a 0.75-second gap. '
        'Static level matching is applied to A/B WAVs; individual files retain original levels. '
        'Same Q8 base model, seed 42, cfg 1, temperature and depth temperature 0.7.</p>'
        '<p>The new adapter uses the current adapter’s 288 training / 29 validation clips, '
        'with audio slowed to 0.8× and a freshly rebuilt cache. Rank 8, alpha 16, 200 steps, learning rate 1e-4.</p>'
        + ''.join(sections)
        + '<script>document.addEventListener("play",e=>{document.querySelectorAll("audio").forEach(a=>{if(a!==e.target)a.pause()})},true)</script>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--slow-adapter', type=Path, required=True)
    parser.add_argument('--training-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config, _, runtime, binary, model, bank_root, bank = inspect(args.config)
    row = next(r for r in bank['characters'] if r['id'] == 'pinkie_pie')
    voice = bank['voices'][row['voice_id']]
    reference, slow_adapter = args.reference.resolve(), args.slow_adapter.resolve()
    training = json.loads(args.training_receipt.read_text())
    if training['status'] != 'complete' or training['speed'] != .8:
        raise ValueError('Expected a completed 0.8x training run')
    if sha(slow_adapter) != training['exported_adapter_sha256']:
        raise ValueError('Experimental adapter hash mismatch')
    if sha(reference) != voice['reference_sha256']:
        raise ValueError('Expected the exact current Pinkie reference')
    current = bank_root / bank['adapters']['pinkie']
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    voices = out / 'voices'
    voices.mkdir()
    shutil.copy2(bank_root / voice['file'], voices / (row['voice_id'] + '.breeze'))
    shutil.copy2(reference, out / 'reference-original.wav')
    slower = out / 'reference-speed-080.wav'
    slowed_info = varispeed(reference, slower, Fraction(4, 5))
    receipt = {'schema': 1, 'complete': False, 'texts': TEXTS, 'seed': 42,
               'script_sha256': sha(__file__), 'model_sha256': config['model_sha256'], 'runtime': runtime,
               'training_receipt': str(args.training_receipt.resolve()), 'training_receipt_sha256': sha(args.training_receipt),
               'adapters': {'current': {'path': str(current), 'sha256': sha(current)},
                            'slow080': {'path': str(slow_adapter), 'sha256': sha(slow_adapter)}},
               'references': {'current': {'sha256': sha(reference), **audio_info(reference)}, 'slow080': slowed_info},
               'samples': [], 'comparisons': []}
    save_json(out / 'results.json', receipt)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    command = [str(binary), str(model), '--host', '127.0.0.1', '--port', str(port), '--ws-port', '-1',
               '--parallel', '1', '--voices-dir', str(voices),
               '--lora', 'current=' + str(current), '--lora', 'slow080=' + str(slow_adapter)]
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
            if time.monotonic() > deadline:
                raise TimeoutError('Native startup timed out')
            time.sleep(.25)
        receipt['native_adapters'] = get(f'http://127.0.0.1:{port}/v1/adapters')
        receipt['registration'] = register(port, 'pinkie_speed080', slower, voice['ref_text'], voices)
        for index, text in enumerate(TEXTS, 1):
            paths = []
            for adapter in ('current', 'slow080'):
                selected = copy.deepcopy(row)
                selected['settings']['lora'] = adapter
                if adapter == 'slow080':
                    selected['voice_id'] = 'pinkie_speed080'
                started = time.monotonic()
                with NativePCM(port, selected, text) as reader:
                    pcm = b''.join(reader.chunks())
                raw = out / f'line-{index:02d}-{adapter}-raw.wav'
                raw.write_bytes(pcm_wav(pcm))
                sample = {'text_index': index, 'adapter': adapter, 'settings': selected['settings'],
                          'voice_id': selected['voice_id'], 'acknowledged_adapter': reader.adapter,
                          'raw_file': raw.name, 'raw': audio_info(raw), 'generation_seconds': time.monotonic() - started}
                if adapter == 'current':
                    final = raw
                    sample.update(label='A: Current Pinkie LoRA, normal speed', reference_speed=1, output_speed=1,
                                  audio=sample['raw'])
                else:
                    final = out / f'line-{index:02d}-slow080-output125.wav'
                    sample.update(label='B: 0.8× trained LoRA → 1.25× output speed', reference_speed=.8, output_speed=1.25,
                                  audio=varispeed(raw, final, Fraction(5, 4)))
                sample['file'] = final.name
                paths.append(final)
                receipt['samples'].append(sample)
                save_json(out / 'results.json', receipt)
                print(f'Line {index}, {adapter}: {sample["audio"]["seconds"]:.2f}s final audio', flush=True)
            name = f'line-{index:02d}-current-vs-slow080.wav'
            receipt['comparisons'].append({'text_index': index, 'file': name,
                                          'gain_adjustments': comparison(paths, out / name)})
        if sha(current) != receipt['adapters']['current']['sha256']:
            raise ValueError('Current adapter changed during auditions')
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
