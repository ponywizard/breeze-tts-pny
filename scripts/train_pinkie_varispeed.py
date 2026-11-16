#!/usr/bin/env python3
"""Run on vengeance: retime the installed Pinkie dataset and train a fresh LoRA."""
import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import wave

import numpy as np
import scipy
from scipy.signal import resample_poly


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write_json(path, value):
    partial = path.with_suffix(path.suffix + '.partial')
    partial.write_text(json.dumps(value, indent=2) + '\n')
    partial.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo, out = args.repo.resolve(), args.output.resolve()
    prior = repo / 'artifacts/pinkie-surprise-retrain'
    previous = json.loads((prior / 'lora-pilot/training-receipt.json').read_text())
    source = Path(previous['source']['repository'])
    model = Path(previous['source']['model_root'])
    config = previous['configuration']
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != previous['source']['revision']:
        raise ValueError('Pinned training source revision changed')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Pinned training source is dirty')
    for split in ('train', 'validation'):
        if sha(prior / (split + '.jsonl')) != config[split + '_manifest_sha256']:
            raise ValueError('Original manifest hash changed: ' + split)
    parent = prior / 'lora-pilot/checkpoint-step-000200/adapter.safetensors'
    parent_hash = sha(parent)
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, out / 'run.py')
    shutil.copy2(prior / 'check_adapter.py', out / 'check_adapter.py')
    receipt = {'status': 'preparing', 'started_utc': datetime.now(timezone.utc).isoformat(),
               'source_dataset': str(prior), 'source': previous['source'], 'configuration': config,
               'speed': .8, 'speed_fraction': '4/5', 'output_speed': 1.25,
               'fresh_from_base': True, 'parent_adapter_used_for_initialization': False,
               'parent_adapter_sha256': parent_hash, 'script_sha256': sha(__file__),
               'processing': 'scipy.signal.resample_poly up=5 down=4, Kaiser beta 10, PCM16',
               'numpy_version': np.__version__, 'scipy_version': scipy.__version__,
               'splits': {}, 'stages': []}
    write_json(out / 'experiment-receipt.json', receipt)
    env = dict(os.environ, PYTHONPATH=str(source), PYTHONUNBUFFERED='1', OMP_NUM_THREADS='8',
               MKL_NUM_THREADS='8', HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    try:
        for split in ('train', 'validation'):
            rows = [json.loads(line) for line in (prior / (split + '.jsonl')).read_text().splitlines() if line.strip()]
            converted, inventory = [], []
            audio_root = out / 'audio' / split
            audio_root.mkdir(parents=True)
            for index, row in enumerate(rows):
                original = Path(row['audio'])
                with wave.open(str(original)) as wav:
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                        raise ValueError('Expected mono 24 kHz PCM16: ' + str(original))
                    samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
                retimed = np.rint(resample_poly(samples.astype(np.float64), 5, 4, window=('kaiser', 10)))
                if np.any(retimed < -32768) or np.any(retimed > 32767):
                    raise ValueError('Retiming would clip: ' + str(original))
                target = audio_root / f'{index:04d}-{original.stem}.wav'
                with wave.open(str(target), 'wb') as wav:
                    wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
                    wav.writeframes(retimed.astype('<i2').tobytes())
                converted.append({**row, 'audio': str(target)})
                inventory.append({'source': str(original), 'source_sha256': sha(original),
                                  'audio': str(target), 'audio_sha256': sha(target),
                                  'original_seconds': len(samples) / 24000,
                                  'retimed_seconds': len(retimed) / 24000,
                                  'transcript_sha256': hashlib.sha256(row['text'].encode()).hexdigest()})
            manifest = out / (split + '.jsonl')
            manifest.write_text(''.join(json.dumps(row) + '\n' for row in converted))
            receipt['splits'][split] = {'count': len(rows), 'manifest_sha256': sha(manifest), 'files': inventory}
            print(f'Prepared {split}: {len(rows)} clips at 0.8x', flush=True)
        write_json(out / 'experiment-receipt.json', receipt)
        stages = [
            ('cache', [sys.executable, '-m', 'training.real_data', '--model-root', str(model),
                       '--train-manifest', str(out / 'train.jsonl'), '--validation-manifest', str(out / 'validation.jsonl'),
                       '--output-root', str(out / 'cache-v1'), '--train-limit', str(receipt['splits']['train']['count']),
                       '--validation-limit', str(receipt['splits']['validation']['count'])]),
            ('training', [sys.executable, '-m', 'training.real_lora', '--model-root', str(model),
                          '--cache-root', str(out / 'cache-v1'), '--output-root', str(out / 'lora-pilot'),
                          '--rank', str(config['rank']), '--alpha', str(config['alpha']),
                          '--max-steps', str(config['max_steps']), '--warmup-steps', str(config['warmup_steps']),
                          '--save-every', str(config['save_every']), '--gradient-accumulation', str(config['gradient_accumulation']),
                          '--validation-examples', str(receipt['splits']['validation']['count']),
                          '--learning-rate', str(config['learning_rate']), '--weight-decay', str(config['weight_decay']),
                          '--max-gradient-norm', str(config['max_gradient_norm']), '--seed', str(config['seed'])]),
            ('reload', [sys.executable, str(out / 'check_adapter.py'), str(out / 'lora-pilot')]),
            ('export', [str(repo / 'artifacts/rainbow-dash-live/convert-env/bin/python'),
                        str(repo / 'native_lora/export_adapter.py'), str(out / 'lora-pilot/checkpoint-step-000200'),
                        '--config', str(out / 'lora-pilot/run-config.json'),
                        '--output', str(out / 'pinkie-speed-080-step200.gguf'), '--base-revision',
                        '799624c0b4a1daa8db6d28bbd9850043c0270734']),
        ]
        for name, command in stages:
            write_json(out / 'status.json', {'stage': name, 'updated_utc': datetime.now(timezone.utc).isoformat()})
            print('Starting ' + name, flush=True)
            started = time.monotonic()
            with (out / (name + '.log')).open('x') as log:
                result = subprocess.run(command, env=env, cwd=source, stdout=log, stderr=subprocess.STDOUT)
            receipt['stages'].append({'stage': name, 'command': command, 'seconds': time.monotonic() - started,
                                      'exit_code': result.returncode})
            write_json(out / 'experiment-receipt.json', receipt)
            if result.returncode:
                raise RuntimeError(f'{name} failed with exit {result.returncode}; inspect {name}.log')
            print(f'Completed {name} in {receipt["stages"][-1]["seconds"]:.1f}s', flush=True)
        if sha(parent) != parent_hash:
            raise ValueError('Original adapter changed during experiment')
        for split in receipt['splits'].values():
            for row in split['files']:
                if sha(row['source']) != row['source_sha256']:
                    raise ValueError('Original audio changed during experiment')
        training = json.loads((out / 'lora-pilot/training-receipt.json').read_text())
        receipt.update(status='complete', completed_utc=datetime.now(timezone.utc).isoformat(),
                       initial_validation=training['initial_validation'], final_validation=training['final_validation'],
                       exported_adapter_sha256=sha(out / 'pinkie-speed-080-step200.gguf'))
        write_json(out / 'experiment-receipt.json', receipt)
        write_json(out / 'status.json', {'stage': 'complete', 'adapter': str(out / 'pinkie-speed-080-step200.gguf'),
                                        'sha256': receipt['exported_adapter_sha256']})
        print(json.dumps({'status': 'complete', 'adapter_sha256': receipt['exported_adapter_sha256']}), flush=True)
    except BaseException as error:
        write_json(out / 'status.json', {'stage': 'failed', 'error': str(error)})
        raise


if __name__ == '__main__':
    main()
