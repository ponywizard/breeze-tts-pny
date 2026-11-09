#!/usr/bin/env python3
"""Create a portable server/installer archive with its verified native runtime."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny import __version__
from breeze_pny.files import sha
from release_files import PUBLIC_DOCUMENTS, PUBLIC_INSTALLER_FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-bundle', type=Path, required=True)
    parser.add_argument('--voice-pack', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / f'dist/breeze-tts-pny-server-{__version__}-linux-x86_64.tar.gz')
    args = parser.parse_args()
    files = {}
    for path in sorted((ROOT / 'server').rglob('*.py')):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in PUBLIC_INSTALLER_FILES + PUBLIC_DOCUMENTS:
        files[name] = (ROOT / name).read_bytes()
    for path in (ROOT / 'native/breeze').glob('LICENSE*'):
        files['licenses/' + path.name] = path.read_bytes()
    files[args.runtime_bundle.name] = args.runtime_bundle.read_bytes()
    release = {'version': __version__, 'platform': 'linux-x86_64',
               'runtime_bundle': {'file': args.runtime_bundle.name, 'sha256': sha(args.runtime_bundle)},
               'voice_pack': {'file': args.voice_pack.name, 'sha256': sha(args.voice_pack)}}
    files['release.json'] = (json.dumps(release, indent=2) + '\n').encode()
    files['README.txt'] = b'Start with docs/SERVER.md. Install with: python3 installer/install.py\nThe curated voice pack is a separate download; place it beside this folder.\n'
    output = args.output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    prefix = output.name.removesuffix('.tar.gz')
    with tarfile.open(output, 'w:gz') as archive:
        for name, raw in sorted(files.items()):
            item = tarfile.TarInfo(prefix + '/' + name); item.size = len(raw); item.mode = 0o644
            archive.addfile(item, io.BytesIO(raw))
    receipt = {**release, 'archive_sha256': sha(output), 'bytes': output.stat().st_size,
               'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    output.with_suffix('').with_suffix('.build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    sums = output.parent / 'SERVER-SHA256SUMS'
    sums.write_text(''.join(f'{sha(p)}  {p.name}\n' for p in (output, args.runtime_bundle, args.voice_pack)))
    print(output)


if __name__ == '__main__': main()
