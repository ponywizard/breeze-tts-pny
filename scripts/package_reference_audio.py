#!/usr/bin/env python3
"""Package verified reference WAVs without lab paths, models, or generated speech."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


def package(references, output):
    voices = json.loads(references.read_text())['voices']
    recordings = {}
    total = 0
    for voice, info in voices.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', voice):
            raise ValueError('Invalid reference voice ID')
        path = Path(info['audio'])
        if not path.is_absolute(): path = references.parent / path
        raw = path.read_bytes()
        total += len(raw)
        if total > 100 * 1024**2: raise ValueError('Reference bundle exceeds 100 MiB')
        if hashlib.sha256(raw).hexdigest() != info['sha256']:
            raise ValueError('Reference hash mismatch: ' + voice)
        recordings[voice] = (raw, info['sha256'])
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for voice, (raw, _) in sorted(recordings.items()):
            archive.writestr('reference-audio/' + voice + '.wav', raw)
        archive.writestr('reference-audio/manifest.json', json.dumps({
            'schema': 1, 'files': {voice + '.wav': digest for voice, (_, digest) in sorted(recordings.items())}}, indent=2) + '\n')
        archive.writestr('REFERENCE-AUDIO.txt',
            'Original reference WAVs for Breeze TTS PNY voice-library playback.\n'
            'Extract alongside voice-library.py. The library verifies each WAV\n'
            'against the installed pack before offering it for playback.\n'
            'Underlying recordings, performances and characters retain their own terms;\n'
            'these recordings are not covered by the utility code license.\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', required=True, help='ZIP path, or - for standard output')
    args = parser.parse_args()
    package(args.references, sys.stdout.buffer if args.output == '-' else args.output)
