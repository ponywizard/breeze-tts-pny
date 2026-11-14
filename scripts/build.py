#!/usr/bin/env python3
"""Build the routing mod with the matching game's official mod packer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())
MOD_VERSION = MANIFEST['version']
GAME_VERSION = MANIFEST['game_version']
BASE_VERSION = MANIFEST['game_base_version']


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-source', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True, help='Matching Godot 4.5 engine or game executable')
    parser.add_argument('--platform', choices=['linux-x86_64', 'windows-x86_64'], default='linux-x86_64')
    args = parser.parse_args()
    source = args.game_source.resolve()
    version = re.search(r'config/version="([^"\n]+)"', (source/'project.godot').read_text())[1]
    if version != BASE_VERSION:
        raise RuntimeError(f'Use the {GAME_VERSION} source (base project version {BASE_VERSION})')
    output = ROOT/f'dist/breeze_tts_pny-{MOD_VERSION}-{args.platform}.pck'
    output.parent.mkdir(exist_ok=True)
    work = ROOT/'build/pack'/args.platform
    work.mkdir(parents=True, exist_ok=True)
    engine = work/'engine/godot'
    engine.parent.mkdir(exist_ok=True)
    shutil.copy2(args.engine, engine)
    env = {**os.environ, 'XDG_DATA_HOME': str(work/'user')}
    result = subprocess.run([str(engine), '--version'], capture_output=True, text=True, env=env)
    if result.returncode or not result.stdout.startswith('4.5.'):
        raise RuntimeError('Use the matching Godot 4.5 engine')
    engine_version = result.stdout.strip()
    project = work/'project'
    if project.exists(): shutil.rmtree(project)
    project.mkdir()
    shutil.copy2(ROOT/'project.godot', project/'project.godot')
    for relative in ['world/modding/mod_loader.gd', 'world/modding/bundled_mods.gd',
                     'tools/build/packs.gd', 'tools/modding/build_mod.gd']:
        dest = project/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source/relative, dest)
    mod = project/'mods/breeze_tts_pny'
    mod.mkdir(parents=True)
    # Include only the routing extension and its notices. Playback, native libraries,
    # model weights and the extension loader now come from Home: Equestria itself.
    paths = [ROOT/'mods/breeze_tts_pny/mod.json']
    paths += [ROOT/path.removeprefix('res://') for path in MANIFEST['extends']]
    paths += sorted((ROOT/'mods/breeze_tts_pny/licenses').glob('*'))
    for path in paths:
        dest = mod/path.relative_to(ROOT/'mods/breeze_tts_pny')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', mod/'licenses/THIRD_PARTY_NOTICES.md')
    command = [str(engine), '--headless', '--xr-mode', 'off', '--path', str(project),
               '--script', str(ROOT/'scripts/build_pack.gd'), '--',
               'res://tools/modding/build_mod.gd', str(output)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    log = result.stdout+result.stderr
    (work/'build.log').write_text(log)
    if result.returncode or 'MOD_BUILT ' not in log or 'SCRIPT ERROR' in log:
        raise RuntimeError(log)
    upstream = source/'upstream-source.json'
    receipt = {'version': MOD_VERSION, 'game_version': GAME_VERSION, 'game_base_version': version,
               'godot': engine_version, 'engine_sha256': sha(engine), 'platform': args.platform,
               'pack_sha256': sha(output), 'bytes': output.stat().st_size,
               'files': {'mods/breeze_tts_pny/'+p.relative_to(mod).as_posix(): sha(p)
                         for p in sorted(mod.rglob('*')) if p.is_file()},
               'official_builder_sha256': sha(source/'tools/modding/build_mod.gd')}
    if upstream.exists(): receipt['upstream_source'] = json.loads(upstream.read_text())
    output.with_suffix('.build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (ROOT/'dist/SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in sorted(output.parent.glob('breeze_tts_pny-*.pck'))))
    print(f'Built {output} ({output.stat().st_size:,} bytes) for {GAME_VERSION}')


if __name__ == '__main__':
    main()
