#!/usr/bin/env python3
"""Install the companion into a user-owned directory; no sudo or game edits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny import __version__
from breeze_pny.bank import load_bank
from breeze_pny.files import acquire, read_json, relative, sha, unpack, verify_files, write_json
from breeze_pny.platforms import acquire_lock, default_prefix, platform_id
from breeze_pny.voice_edit import preserve_custom_voices


def progress(label):
    def report(phase, done, total):
        if phase == 'cached':
            print('Using verified cached ' + label + '.', flush=True)
        elif phase == 'verifying':
            print('Verifying ' + label + ' SHA-256...', flush=True)
        elif phase == 'ready':
            print(label.capitalize() + ' ready.', flush=True)
        else:
            amount = f'{done / 1024**2:.1f} MiB'
            if total: amount += f' / {total / 1024**2:.1f} MiB ({done * 100 / total:.0f}%)'
            print(phase.capitalize() + ' ' + label + ': ' + amount, flush=True)
    return report


def bundle(source, digest, prefix, category):
    if not digest:
        if str(source).startswith('https://'): raise ValueError('Remote bundles require a release SHA-256')
        digest = sha(source)
    archive = acquire(source, prefix / 'cache' / (digest + '.tar.gz'), digest, 512 * 1024**2,
                      progress=progress('native runtime' if category == 'runtimes' else 'voice pack'))
    destination = prefix / 'assets' / category / digest
    if not destination.exists(): unpack(archive, destination)
    return destination


def install(args):
    target = platform_id()
    prefix = args.prefix.expanduser().resolve()
    if prefix.exists() and any(prefix.iterdir()) and not (prefix / 'installation.json').exists():
        raise ValueError('Choose an empty installation directory')
    prefix.mkdir(parents=True, exist_ok=True)
    lock = (prefix / 'service.lock').open('a+b')
    try: acquire_lock(lock)
    except BlockingIOError: raise ValueError('Stop the companion before installing/updating')
    old = read_json(prefix / 'config.json') if (prefix / 'config.json').exists() else None
    if old and not args.update: raise ValueError('Already installed; use --update to preserve configuration and update assets')
    if not (prefix / 'installation.json').exists(): write_json(prefix / 'installation.json', {'schema': 1, 'complete': False})
    release = read_json(ROOT / 'release.json') if (ROOT / 'release.json').exists() else {}
    def choose(name, supplied, digest):
        if supplied: return supplied, digest
        item = release.get(name)
        if not item: raise ValueError('Supply --' + name.replace('_', '-') + ' when installing from source')
        for directory in (ROOT, ROOT.parent):
            candidate = directory / item['file']
            if candidate.exists(): return str(candidate), item['sha256']
        if args.release_base_url: return args.release_base_url.rstrip('/') + '/' + item['file'], item['sha256']
        raise ValueError('Place ' + item['file'] + ' beside the extracted server folder, or supply --release-base-url')
    runtime_source, runtime_sha = choose('runtime_bundle', args.runtime_bundle, args.runtime_sha256)
    bank_source, bank_sha = choose('voice_pack', args.voice_pack, args.voice_pack_sha256)
    runtime_root = bundle(runtime_source, runtime_sha, prefix, 'runtimes')
    runtime = read_json(runtime_root / 'runtime.json'); verify_files(runtime_root, runtime['files'])
    if runtime.get('platform') != target or not runtime.get('adapter_selection'): raise ValueError('Incompatible native runtime')
    binary = relative(runtime_root, runtime['entrypoint'])
    if runtime['entrypoint'] not in runtime['files']: raise ValueError('Unverified runtime executable')
    binary.chmod(0o755)
    bank_root = bundle(bank_source, bank_sha, prefix, 'voice-packs'); bank = load_bank(bank_root)
    assets = read_json(ROOT / 'installer/assets.json')
    if bank['model_sha256'] != assets['breeze_q8']['sha256']: raise ValueError('Voice pack needs an unsupported base model')
    if old:
        bank_root = preserve_custom_voices(prefix, relative(prefix, old['voice_pack']), bank_root)
        bank = load_bank(bank_root)
    item = assets['breeze_q8']; print('Preparing ' + item['file'], flush=True)
    model = acquire(args.model_file or item['url'], prefix / 'models' / item['sha256'] / item['file'], item['sha256'],
                    progress=progress('model'))
    python = Path(args.python or sys.executable).expanduser().resolve()
    subprocess.run([str(python), '-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "Python 3.11+ is required")'], check=True)
    source_files = sorted(p for p in (ROOT / 'server/breeze_pny').rglob('*') if p.suffix in ('.py', '.html', '.js', '.css'))
    identity = hashlib.sha256(b''.join(p.relative_to(ROOT / 'server').as_posix().encode() + b'\0' + p.read_bytes() for p in source_files)).hexdigest()[:16]
    app = prefix / 'apps' / identity
    shutil.copytree(ROOT / 'server', app / 'server', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    def rel(path): return path.relative_to(prefix).as_posix()
    config = {'schema': 1, 'host': (old or {}).get('host', '127.0.0.1'),
              'port': (old or {}).get('port', 18792), 'native_port': (old or {}).get('native_port', 18797),
              'runtime': rel(runtime_root), 'voice_pack': rel(bank_root),
              'model': rel(model), 'model_sha256': assets['breeze_q8']['sha256']}
    pending = prefix / 'config.pending.json'; write_json(pending, config)
    # Embedded Windows Python ignores PYTHONPATH; supply the app directory explicitly.
    bootstrap = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("breeze_pny",run_name="__main__")'
    subprocess.run([str(python), '-c', bootstrap, str(app / 'server'), 'doctor', '--config', str(pending)], check=True)
    if old: shutil.copy2(prefix / 'config.json', prefix / 'config.previous.json')
    pending.replace(prefix / 'config.json')
    launcher = prefix / ('bin/breeze-pny.cmd' if target == 'windows-x86_64' else 'bin/breeze-pny')
    launcher.parent.mkdir(exist_ok=True)
    if target == 'windows-x86_64':
        # Keep the interpreter path relative when possible and disable delayed expansion.
        def batch(value):
            value = str(value)
            if any(char in value for char in '\r\n"'): raise ValueError('Unsupported character in launcher path')
            return value.replace('%', '%%')
        entry = launcher.with_suffix('.py')
        entry.write_text('import os,runpy,sys\nfrom pathlib import Path\n'
                        'root=Path(__file__).resolve().parents[1]\n'
                        'sys.path.insert(0,str(root / ' + repr(rel(app / 'server')) + '))\n'
                        'os.environ["BREEZE_PNY_CONFIG"]=str(root / "config.json")\n'
                        'runpy.run_module("breeze_pny",run_name="__main__")\n', encoding='utf-8')
        try: interpreter = os.path.relpath(python, launcher.parent)
        except ValueError: interpreter = str(python)
        text = ('@echo off\nchcp 65001 >nul\nsetlocal DisableDelayedExpansion\npushd "%~dp0"\n'
                '"' + batch(interpreter) + '" -X utf8 "breeze-pny.py" %*\n'
                'set "result=%errorlevel%"\npopd\nexit /b %result%\n')
    else:
        text = ('#!/bin/sh\nexport PYTHONPATH=' + shlex.quote(str(app / 'server')) + '\n'
                'export BREEZE_PNY_CONFIG=' + shlex.quote(str(prefix / 'config.json')) + '\n'
                'exec ' + shlex.quote(str(python)) + ' -m breeze_pny "$@"\n')
    launcher.write_text(text, encoding='utf-8'); launcher.chmod(0o755)
    write_json(prefix / 'installation.json', {'schema': 1, 'complete': True, 'version': __version__,
                'voice_pack': bank['id'], 'runtime': runtime['id'], 'app': rel(app), 'python': str(python)})
    start = subprocess.list2cmdline([str(launcher), 'serve']) if target == 'windows-x86_64' else shlex.quote(str(launcher)) + ' serve'
    print('Installed. Start with: ' + start)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=default_prefix())
    for name in ('runtime-bundle', 'runtime-sha256', 'voice-pack', 'voice-pack-sha256', 'release-base-url', 'python'):
        parser.add_argument('--' + name)
    parser.add_argument('--model-file', type=Path)
    parser.add_argument('--update', action='store_true')
    args = parser.parse_args()
    try: install(args)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print('Setup failed: ' + str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__': sys.exit(main())
