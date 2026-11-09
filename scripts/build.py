#!/usr/bin/env python3
"""Build the single-file mod using the matching game's official mod packer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MOD_VERSION = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())['version']


DECLARATION = re.compile(r'''(?m)^(?:@[A-Za-z_]\w*(?:\((?:[^()"'\n]|"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')*\))?\s*)*(?:static\s+)?(?:func|var|const|signal|enum|class)\s+([A-Za-z_]\w*)''')


def declared_chain(source, path):
    """Names declared by a game script and the game scripts it extends, and those scripts."""
    names, chain = set(), []
    while path and path not in chain:
        chain.append(path)
        text = (source/path.removeprefix('res://')).read_text()
        names |= set(DECLARATION.findall(text))
        parent = re.search(r'(?m)^extends "(res://[^"\n]+)"', text)
        path = parent[1] if parent else None
    return names, chain


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-source', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True, help='Godot 4.5.x or the matching game executable')
    parser.add_argument('--native-library', type=Path, required=True, help='Matching libtalking_avatar.so or talking_avatar.dll from this source')
    parser.add_argument('--platform', choices=['linux-x86_64', 'windows-x86_64'], default='linux-x86_64')
    args = parser.parse_args()
    source = args.game_source.resolve()
    version = re.search(r'config/version="([^"]+)"', (source/'project.godot').read_text())[1]
    if version != '0.3.0-maredev':
        raise RuntimeError('This preview targets 0.3.0-maredev; validate a new version before building')
    output = ROOT/f'dist/breeze_tts_pny-{MOD_VERSION}-{args.platform}.pck'
    output.parent.mkdir(exist_ok=True)
    work = ROOT/'build/pack'/args.platform
    work.mkdir(parents=True, exist_ok=True)
    engine = work/'engine/godot'
    engine.parent.mkdir(exist_ok=True)
    # An exported game executable needs isolation from its adjacent game packs.
    shutil.copy2(args.engine, engine)
    env = {**os.environ, 'XDG_DATA_HOME': str(work/'user')}
    result = subprocess.run([str(engine), '--version'], capture_output=True, text=True, env=env)
    if result.returncode or not result.stdout.startswith('4.5.'):
        raise RuntimeError('Use the matching Godot 4.5 engine, not another installed version')
    project = work/'project'
    project.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'project.godot', project/'project.godot')
    for relative in ['world/modding/mod_loader.gd', 'tools/build/packs.gd', 'tools/modding/build_mod.gd']:
        dest = project/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source/relative, dest)
    (project/'mods').mkdir(exist_ok=True)
    mod = project/'mods/breeze_tts_pny'
    if mod.exists(): shutil.rmtree(mod)
    shutil.copytree(ROOT/'mods/breeze_tts_pny', mod,
                    ignore=shutil.ignore_patterns('libtalking_avatar.*.bin', 'talking_avatar.*.bin', 'manifest.json'))
    windows = args.platform == 'windows-x86_64'
    key = 'windows.x86_64' if windows else 'linux.x86_64'
    binary = mod/'native'/('talking_avatar.windows.x86_64.dll.bin' if windows else 'libtalking_avatar.linux.x86_64.so.bin')
    shutil.copy2(args.native_library, binary)
    (mod/'native/manifest.json').write_text(json.dumps({key: {
        'file': binary.name, 'sha256': sha(binary)}}, indent=2)+'\n')
    defaults = mod/'merge/mods/breeze_tts_pny/defaults.json'
    config = json.loads(defaults.read_text()); config['platform'] = key
    defaults.write_text(json.dumps(config, indent=2)+'\n')
    info = mod/'mod.json'; config = json.loads(info.read_text())
    config['description'] = config['description'].replace('Linux x86_64', ('Windows' if windows else 'Linux')+' x86_64')
    info.write_text(json.dumps(config, indent=2)+'\n')
    # Members each extension adds to its game script, from the matching source.
    # Another mod's full replacement of that script may be the extension's parent
    # only if it declares none of them (install_extensions.gd).
    added = {}
    for extension in json.loads((mod/'mod.json').read_text())['script_extensions']:
        text = (mod/extension.removeprefix('res://mods/breeze_tts_pny/')).read_text()
        target = re.search(r'(?m)^extends "(res://[^"\n]+)"', text)[1]
        names, chain = declared_chain(source, target)
        added[target] = {'added': sorted(set(DECLARATION.findall(text)) - names), 'chain': chain}
    (mod/'added_members.json').write_text(json.dumps(added, indent=2, sort_keys=True)+'\n')
    # Ship the current complete notices instead of a stale development copy.
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md', mod/'licenses/THIRD_PARTY_NOTICES.md')
    command = [str(engine), '--headless', '--xr-mode', 'off', '--path', str(project),
               '--script', str(ROOT/'scripts/build_pack.gd'), '--',
               'res://tools/modding/build_mod.gd', str(output)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
    log = result.stdout+result.stderr
    (work/'build.log').write_text(log)
    if result.returncode or 'MOD_BUILT ' not in log or 'SCRIPT ERROR' in log:
        raise RuntimeError(log)
    receipt = {'version': MOD_VERSION, 'game_version': version, 'godot': '4.5', 'platform': args.platform,
               'pack_sha256': sha(output), 'bytes': output.stat().st_size,
               'files': {'mods/breeze_tts_pny/'+p.relative_to(mod).as_posix(): sha(p) for p in sorted(mod.rglob('*')) if p.is_file() and not p.name.endswith('.uid')},
               'official_builder_sha256': sha(source/'tools/modding/build_mod.gd')}
    output.with_suffix('.build.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (ROOT/'dist/SHA256SUMS').write_text(''.join(f'{sha(path)}  {path.name}\n' for path in sorted(output.parent.glob('breeze_tts_pny-*.pck'))))
    print(f'Built {output} ({output.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
