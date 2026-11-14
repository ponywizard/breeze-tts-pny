#!/usr/bin/env python3
"""Package the browser utility for existing Windows and Linux installations."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.files import sha
from breeze_pny import REFERENCE_MANAGER_VERSION
from release_files import server_files


def package(output, reference_audio=None):
    files = {'voice-library-code/' + path.relative_to(ROOT / 'server').as_posix(): path.read_bytes()
             for path in server_files(ROOT)}
    files['voice-library.py'] = (ROOT / 'scripts/voice_library_launcher.py').read_bytes()
    files['VOICE-LIBRARY.md'] = (ROOT / 'docs/VOICE_LIBRARY.md').read_bytes()
    files['voice-library-code/LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    if reference_audio:
        with zipfile.ZipFile(reference_audio) as recordings:
            entries = recordings.infolist()
            names = [item.filename for item in entries]
            if len(names) != len(set(names)) or sum(item.file_size for item in entries) > 100 * 1024**2:
                raise ValueError('Reference archive has duplicate entries or exceeds 100 MiB')
            manifest = json.loads(recordings.read('reference-audio/manifest.json'))
            inventory = manifest.get('files')
            if manifest.get('schema') != 1 or not isinstance(inventory, dict) or not 1 <= len(inventory) <= 1000:
                raise ValueError('Invalid reference-audio manifest')
            expected = {'reference-audio/manifest.json', 'REFERENCE-AUDIO.txt'}
            for name, digest in inventory.items():
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}\.wav', name):
                    raise ValueError('Invalid reference recording name')
                member = 'reference-audio/' + name
                raw = recordings.read(member)
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError('Reference hash mismatch: ' + name)
                files[member] = raw
                expected.add(member)
            if set(names) != expected:
                raise ValueError('Unexpected or missing reference archive files')
            for name in ('reference-audio/manifest.json', 'REFERENCE-AUDIO.txt'):
                files[name] = recordings.read(name)
    files['voice-library.cmd'] = b'''@echo off\r
chcp 65001 >nul\r
setlocal DisableDelayedExpansion\r
pushd "%~dp0" || exit /b 1\r
if not exist "python\\python.exe" (\r
  echo Extract this utility into your existing Breeze TTS PNY package folder, next to its python folder.\r
  pause\r
  exit /b 1\r
)\r
"python\\python.exe" -X utf8 "voice-library.py" %*\r
set "result=%errorlevel%"\r
popd\r
if not "%BREEZE_PNY_NO_PAUSE%"=="1" pause\r
exit /b %result%\r
'''
    files['voice-library.sh'] = b'#!/bin/sh\nexec python3 "$(dirname "$0")/voice-library.py" "$@"\n'
    title = 'Reference Management Utility and Recordings' if reference_audio else 'Reference Management Utility'
    recordings_note = (
        'The included reference-audio folder is detected automatically.\n'
        'Matching original recordings are ready to play; no separate download is needed.\n'
        if reference_audio else
        'To play original recordings, extract the optional reference-audio ZIP beside\n'
        'voice-library.py. Newly saved references are always playable.\n')
    files['VOICE-LIBRARY-START.txt'] = (title + ' ' + REFERENCE_MANAGER_VERSION + '\n\n' + '''Stop the companion before opening this utility.
Windows: extract into your existing Breeze TTS PNY package folder, alongside
its python and companion folders. Run voice-library.cmd.
Linux: extract anywhere and run: sh voice-library.sh --config /path/to/companion/config.json
The browser opens locally. Keep the terminal open while using the library.
Close the library before restarting the companion. Read VOICE-LIBRARY.md.
This utility reuses your installed model/runtime; no ffmpeg or pip is needed.
''' + recordings_note + '''
Use the updated companion installer to preserve personal voices across updates;
older installers replace the configured pack. Original packs remain for undo.
''').encode('utf-8')
    source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source_dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    files['reference-manager.json'] = (json.dumps({
        'schema': 1, 'version': REFERENCE_MANAGER_VERSION,
        'source_commit': source_commit, 'source_dirty': source_dirty,
        'compatible_companion_versions': ['0.2.1'],
        'reference_recordings': sum(name.startswith('reference-audio/') and name.endswith('.wav') for name in files),
        'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(files.items())},
    }, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(files.items()):
            item = zipfile.ZipInfo(name)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            archive.writestr(item, raw)
    output.with_suffix('.sha256').write_text(sha(output) + '  ' + output.name + '\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-audio', type=Path, help='Include the verified reference-audio ZIP in the same download')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    name = (f'breeze-reference-management-utility-and-recordings-{REFERENCE_MANAGER_VERSION}.zip' if args.reference_audio
            else f'breeze-voice-library-{REFERENCE_MANAGER_VERSION}.zip')
    print(package(args.output or ROOT / 'dist' / name, args.reference_audio))
