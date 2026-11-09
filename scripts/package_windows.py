#!/usr/bin/env python3
"""Assemble the Windows preview on Linux with embedded Python and a native mod."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny import __version__
from breeze_pny.files import sha
from release_files import PUBLIC_DOCUMENTS, PUBLIC_INSTALLER_FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-bundle', type=Path, required=True)
    parser.add_argument('--voice-pack', type=Path, required=True)
    parser.add_argument('--python-bundle', type=Path, required=True)
    parser.add_argument('--python-sha256', required=True)
    parser.add_argument('--mod-pack', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if sha(args.python_bundle) != args.python_sha256:
        raise ValueError('Embedded Python checksum mismatch')
    output = args.output or ROOT / f'dist/breeze-tts-pny-{__version__}-windows-x86_64.zip'
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {}
    for path in sorted((ROOT / 'server').rglob('*.py')):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in PUBLIC_INSTALLER_FILES + PUBLIC_DOCUMENTS:
        files[name] = (ROOT / name).read_bytes()
    for path in (ROOT / 'native/breeze').glob('LICENSE*'):
        files['licenses/' + path.name] = path.read_bytes()
    files[args.runtime_bundle.name] = args.runtime_bundle.read_bytes()
    files['game-mod/' + args.mod_pack.name] = args.mod_pack.read_bytes()
    with zipfile.ZipFile(args.python_bundle) as archive:
        for item in archive.infolist():
            if item.is_dir(): continue
            name = Path(item.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in item.filename:
                raise ValueError('Unsafe embedded Python member')
            files['python/' + item.filename] = archive.read(item)
    release = {'version': __version__, 'platform': 'windows-x86_64',
               'runtime_bundle': {'file': args.runtime_bundle.name, 'sha256': sha(args.runtime_bundle)},
               'voice_pack': {'file': args.voice_pack.name, 'sha256': sha(args.voice_pack)},
               'embedded_python': {'file': args.python_bundle.name, 'sha256': args.python_sha256}}
    files['release.json'] = (json.dumps(release, indent=2) + '\n').encode()
    def batch(name, body):
        text = '@echo off\r\nchcp 65001 >nul\r\nsetlocal DisableDelayedExpansion\r\n' + body.replace('\n', '\r\n')
        files[name] = text.encode('utf-8')
    batch('setup.cmd', 'pushd "%~dp0" || exit /b 1\n"python\\python.exe" -X utf8 "installer\\install.py" --prefix "companion" %*\n'
          'set "result=%errorlevel%"\npopd\nif not "%BREEZE_PNY_NO_PAUSE%"=="1" pause\nexit /b %result%\n')
    batch('start-companion.cmd', 'pushd "%~dp0" || exit /b 1\nif not exist "companion\\bin\\breeze-pny.cmd" (\n'
          '  echo Run setup.cmd first.\n  pause\n  exit /b 1\n)\n'
          'call "companion\\bin\\breeze-pny.cmd" serve\n'
          'set "result=%errorlevel%"\npopd\nif not "%BREEZE_PNY_NO_PAUSE%"=="1" pause\nexit /b %result%\n')
    batch('check-voice.cmd', 'pushd "%~dp0" || exit /b 1\n"python\\python.exe" -X utf8 "check-voice.py" %*\n'
          'set "result=%errorlevel%"\npopd\nif not "%BREEZE_PNY_NO_PAUSE%"=="1" pause\nexit /b %result%\n')
    batch('prepare-playtest.cmd', 'pushd "%~dp0" || exit /b 1\n'
          '"python\\python.exe" -X utf8 "installer\\prepare_windows_playtest.py" %*\n'
          'set "result=%errorlevel%"\npopd\nif not "%BREEZE_PNY_NO_PAUSE%"=="1" pause\nexit /b %result%\n')
    files['check-voice.py'] = b'''import runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent / "server"))
sys.argv[1:1]=["smoke"]
runpy.run_module("breeze_pny",run_name="__main__")
'''
    files['START-HERE.txt'] = b'''Windows x86_64 preview; RX 6700 XT flatscreen playtest completed.
Windows PCVR is untested and ships with case-by-case support.
Read docs/WINDOWS.md for setup, requirements and test coverage.
Place the curated voice-pack archive beside this folder or inside it.
Run setup.cmd, then start-companion.cmd. Wait for the ready event.
Run check-voice.cmd --character pinkie_pie --output pinkie-test.wav
Copy the .pck from game-mod into Settings > Mods > Open mods folder, then restart.
Set MOSS-compatible TTS to http://127.0.0.1:18792/tts with automatic voices.
For a disposable profile, optionally use prepare-playtest.cmd; see docs/WINDOWS.md.
Model weights are separate; setup downloads the pinned model or accepts
--model-file "C:\\path\\to\\breeze-tts-2-q8_0.gguf" for offline installation.
'''
    prefix = output.stem
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, raw in sorted(files.items()): archive.writestr(prefix + '/' + name, raw)
    receipt = {**release, 'archive_sha256': sha(output), 'bytes': output.stat().st_size,
               'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    output.with_suffix('.build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    (output.parent / 'WINDOWS-SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in (output, args.runtime_bundle, args.voice_pack, args.mod_pack)))
    print(output)


if __name__ == '__main__': main()
