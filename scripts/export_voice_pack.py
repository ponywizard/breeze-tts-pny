#!/usr/bin/env python3
"""Export selected Breeze reference caches and adapters without private lab data."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.bank import settings, ID
from breeze_pny.files import read_json, sha


def write_bundle(path, files):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, 'w:gz') as archive:
        for name, raw in sorted(files.items()):
            item = tarfile.TarInfo(name); item.size = len(raw); item.mode = 0o644
            archive.addfile(item, io.BytesIO(raw))


def export(manifest, references, cache, adapters, output,
           pack_id='curated-ponies-20261107', version='1', include_reference_audio=False):
    if not ID.fullmatch(pack_id): raise ValueError('Invalid voice pack ID')
    source, refs = read_json(manifest), read_json(references)['voices']
    files, rows, voices, used = {}, [], {}, set()
    for original in source['characters']:
        row = {'id': original['id'], 'name': original.get('name', original['id']), 'route': original['route']}
        if not ID.fullmatch(row['id']): raise ValueError('Invalid character identity')
        if row['route'] == 'breeze':
            voice = original['voice_id']; ref = refs[voice]
            if not ID.fullmatch(voice): raise ValueError('Invalid voice ID')
            selected = source.get('breeze_voice_settings', {}).get(voice, {})
            row['voice_id'] = voice
            row['settings'] = settings({k: selected[k] for k in ('cfg_scale', 'temperature', 'depth_temperature', 'instruction', 'lora') if k in selected})
            if row['settings']['lora']: used.add(row['settings']['lora'])
            name = f'voices/{voice}.breeze'; raw = (cache / (voice + '.breeze')).read_bytes()
            if b'/home/' in raw or b'capture_dir' in raw: raise ValueError('Private lab path embedded in cached voice')
            files[name] = raw
            voices[voice] = {'file': name, 'ref_text': ref['transcript'], 'reference_sha256': ref['sha256'],
                             'source': {k: ref[k] for k in ('episode', 'source_url', 'annotation_url', 'processing') if k in ref}}
            if include_reference_audio:
                audio = Path(ref['audio'])
                if not audio.is_absolute(): audio = references.parent / audio
                if sha(audio) != ref['sha256']: raise ValueError('Reference WAV differs from cached voice: ' + voice)
                name = f'references/{voice}.wav'
                files[name] = audio.read_bytes()
                voices[voice]['reference_file'] = name
        else: raise ValueError('Unsupported curated route')
        rows.append(row)
    adapter_files = {}
    for name in sorted(used):
        if name not in adapters: raise ValueError('Supply adapter ' + name)
        filename = 'adapters/' + name + '.gguf'; files[filename] = adapters[name].read_bytes(); adapter_files[name] = filename
    files['VOICE_PACK_NOTICE.txt'] = (
        'Curated Home: Equestria voice pack. Contains selected native reference encodings,\n'
        'and selected adapters; no generated conversation recordings.\n'
        'Reference provenance is recorded per voice in voice-pack.json. These assets are\n'
        'separate from the MIT-licensed server code; that license does not grant rights\n'
        'in the underlying recordings, characters, performances, or Breeze model weights.\n'
        'These adapters depend on Breeze TTS 2, whose weights use the BreezeBlue Research\n'
        'and Non-Commercial License: https://huggingface.co/BreezeBlue/Breeze-TTS-2\n'
    ).encode()
    bank = {'schema': 1, 'id': pack_id, 'version': version,
            'model_sha256': 'a02bcc4b69b0601032727f8040c4942149b1b73aa0f69022fe5aaa6a8f0ef879',
            'characters': rows, 'voices': voices, 'adapters': adapter_files,
            'legacy_speakers': source.get('legacy_breeze_speakers', {}),
            'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    files['voice-pack.json'] = (json.dumps(bank, indent=2, sort_keys=True) + '\n').encode()
    write_bundle(output, files)
    print(json.dumps({'file': output.name, 'sha256': sha(output), 'bytes': output.stat().st_size,
                      'characters': len(rows), 'breeze': len(voices), 'adapters': sorted(adapter_files)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('manifest', 'references', 'cache', 'output'): parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--adapter', action='append', default=[], metavar='ID=FILE')
    parser.add_argument('--id', default='curated-ponies-20261107', help='Portable voice pack identity')
    parser.add_argument('--version', default='1', help='Voice pack version')
    parser.add_argument('--include-reference-audio', action='store_true', help='Include verified original WAVs for voice-library playback')
    args = parser.parse_args()
    adapters = {key: Path(value) for key, value in (a.split('=', 1) for a in args.adapter)}
    export(args.manifest, args.references, args.cache, adapters, args.output, args.id, args.version, args.include_reference_audio)
