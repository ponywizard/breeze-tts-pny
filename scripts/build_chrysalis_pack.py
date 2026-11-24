#!/usr/bin/env python3
"""Add Queen Chrysalis's selected PPP recording to the November 15 curated pack."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from export_voice_pack import write_bundle
from experiment_pinkie_pitch import register
from breeze_pny.files import sha
from breeze_pny.voice_edit import VoiceEditor, reference_wav


BASE_SHA256 = '12de6d13c9ba48c50eeece34a00974504f86a77d81ba767c44ba31aabfad5a04'
FLAC_SHA256 = '490043998307767c62b00c9fd581c294f25235a9b539b800a014b2c558c3277d'
# Hash after stripping optional WAV chunks, to check the auditioned PCM across muxer versions.
PCM_WAV_SHA256 = '9d341a443bdf87ed0d18684a7143a28d4ecc19b9bb62f8ab420b0cb5e4dc87d2'
TRANSCRIPT = 'I assumed they were in Canterlot. My castle search proved otherwise.'
SOURCE = {
    'episode': 'fim_s08e13',
    'source_url': 'https://mega.nz/folder/jkwimSTa#_xk0VnR30C8Ljsy4RCGSig/file/HkxxGKID',
    'annotation_url': 'https://mega.nz/folder/jkwimSTa#_xk0VnR30C8Ljsy4RCGSig/file/qtpDnSbY',
    'notes': 'PPP Sliced Dialogue, Special source, 00:04:39. Neutral. Selected take C, “The castle search”.',
    'processing': 'Converted the full 5.14-second FLAC to mono 24 kHz PCM16.',
}


def build(base_pack, flac, config, output_dir):
    if sha(base_pack) != BASE_SHA256 or sha(flac) != FLAC_SHA256:
        raise ValueError('Expected the published 20261115 pack and the selected S08E13 source FLAC')
    with tarfile.open(base_pack, 'r:gz') as archive:
        files = {entry.name: archive.extractfile(entry).read() for entry in archive}
    bank = json.loads(files['voice-pack.json'])
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / 'breeze-pny-curated-voices-20261123.tar.gz'
    with tempfile.TemporaryDirectory(dir=output_dir) as temporary:
        work = Path(temporary)
        reference = work / 'chrysalis.wav'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(flac), '-ac', '1',
                        '-ar', '24000', '-c:a', 'pcm_s16le', str(reference)], check=True)
        raw = reference.read_bytes()
        if hashlib.sha256(reference_wav(raw)).hexdigest() != PCM_WAV_SHA256:
            raise ValueError('Converted PCM differs from the selected audition')
        cache_name = 'voices/chrysalis.breeze'
        reference_name = 'references/chrysalis.wav'
        with closing(VoiceEditor(config)) as editor:
            if editor.config['model_sha256'] != bank['model_sha256']:
                raise ValueError('Select the Q8 base model used for the audition')
            editor.start_native()
            register(editor.native_port, 'chrysalis', reference, TRANSCRIPT, editor.workspace / 'voices')
            files[cache_name] = (editor.workspace / cache_name).read_bytes()
        files[reference_name] = raw
        for name in (cache_name, reference_name):
            bank['files'][name] = hashlib.sha256(files[name]).hexdigest()
        bank['voices']['chrysalis'] = {
            'file': cache_name, 'reference_file': reference_name, 'ref_text': TRANSCRIPT,
            'reference_sha256': bank['files'][reference_name], 'source': SOURCE,
        }
        bank['characters'].append({
            'id': 'chrysalis', 'name': 'Queen Chrysalis', 'route': 'breeze', 'voice_id': 'chrysalis',
            'settings': {'cfg_scale': 1, 'temperature': 0.7, 'depth_temperature': 0.7, 'lora': ''},
        })
        bank['legacy_speakers']['7'] = 'chrysalis'
        bank.update(id='curated-ponies-20261123', version='3')
        files['voice-pack.json'] = (json.dumps(bank, indent=2, sort_keys=True) + '\n').encode()
        staged = work / output.name
        write_bundle(staged, files)
        staged.replace(output)
    print(f'{sha(output)}  {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-pack', required=True, type=Path)
    parser.add_argument('--flac', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path, help='Local Companion installation with Q8 selected')
    parser.add_argument('--output-dir', type=Path, default=Path('dist'))
    args = parser.parse_args()
    build(args.base_pack, args.flac, args.config, args.output_dir)
