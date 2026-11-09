#!/usr/bin/env python3
"""Test the actual mod loader against a clean, isolated copy of the exported game."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
MOD_VERSION = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())['version']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-release', type=Path, required=True)
    args = parser.parse_args()
    source = args.game_release.resolve()
    work = ROOT/'build/verify'
    release = work/'game'
    release.mkdir(parents=True, exist_ok=True)
    # Deliberate allowlist: exclude the experimental playback/optimization packs.
    allowed = ['HomeEquestria.x86_64', 'HomeEquestria.pck', 'HomeEquestria-data.pck']
    allowed += [p.name for p in source.glob('*.so')]
    for name in allowed:
        dest = release/name
        if dest.exists(): continue
        if name.endswith('.pck'): dest.symlink_to(source/name)
        else: shutil.copy2(source/name, dest)
    pack = ROOT/f'dist/breeze_tts_pny-{MOD_VERSION}-linux-x86_64.pck'
    eyes = []
    for mode in ['enabled', 'disabled']:
        user = work/(mode+'-'+str(time.time_ns()))
        mods = user/'home-equestria-public/mods'
        mods.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pack, mods/pack.name)
        config = mods/'mods.cfg'
        if mode == 'disabled':
            config.write_text(f'[mods]\ndisabled=PackedStringArray("{pack.name}")\n')
        elif config.exists():
            config.unlink()
        env = {**os.environ, 'XDG_DATA_HOME': str(user)}
        for key in ('EQ_PCM_STREAM', 'EQ_PCM_PLAYBACK', 'EQ_TALKING_AVATAR'):
            env.pop(key, None)
        command = [str(release/'HomeEquestria.x86_64'), '--headless', '--audio-driver', 'Dummy',
                   '--xr-mode', 'off', '--script', str(ROOT/'tests/smoke.gd'), '--']
        if mode == 'disabled': command.append('--disabled')
        result = subprocess.run(command, cwd=release, env=env, capture_output=True, text=True, timeout=90)
        log = result.stdout+result.stderr
        (work/f'{mode}.log').write_text(log)
        if result.returncode or 'SCRIPT ERROR' in log or 'BREEZE_MOD_SMOKE_DONE failures=0' not in log:
            raise RuntimeError(log)
        eyes.append([line for line in log.splitlines() if line.startswith(('EYE_MESH ', 'EYE_SHADER ', 'UNIFORM '))])
        print(f'PASS: {mode}, actual exported game mod loader')
    if len(eyes[0]) != 55 or eyes[0] != eyes[1]:
        raise RuntimeError('Original and modded eye appearance differ')
    user = work/('replacement-compat-'+str(time.time_ns()))
    mods = user/'home-equestria-public/mods'; mods.mkdir(parents=True)
    shutil.copy2(pack, mods/pack.name)
    env = {**os.environ, 'XDG_DATA_HOME': str(user)}
    result = subprocess.run([str(release/'HomeEquestria.x86_64'), '--headless', '--audio-driver', 'Dummy',
        '--xr-mode', 'off', '--script', str(ROOT/'tests/replacement_compat.gd')],
        cwd=release, env=env, capture_output=True, text=True, timeout=45)
    log = result.stdout+result.stderr
    (work/'replacement-compat.log').write_text(log)
    if result.returncode or 'SCRIPT ERROR' in log or 'BREEZE_REPLACEMENT_COMPAT_DONE failures=0' not in log:
        raise RuntimeError(log)
    print('PASS: replacement declarations, inherited collisions, and refusal before any extension is installed')
    sys.path.insert(0, str(ROOT/'tests'))
    from fixture_server import create
    server = create()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        user = work/('transport-'+str(time.time_ns()))
        mods = user/'home-equestria-public/mods'; mods.mkdir(parents=True)
        shutil.copy2(pack, mods/pack.name)
        env = {**os.environ, 'XDG_DATA_HOME': str(user)}
        for key in ('EQ_PCM_STREAM', 'EQ_PCM_PLAYBACK', 'EQ_TALKING_AVATAR'): env.pop(key, None)
        result = subprocess.run([str(release/'HomeEquestria.x86_64'), '--headless', '--audio-driver', 'Dummy',
            '--xr-mode', 'off', '--script', str(ROOT/'tests/transport.gd'), '--', str(server.server_port)],
            cwd=release, env=env, capture_output=True, text=True, timeout=45)
        log = result.stdout+result.stderr
        (work/'transport.log').write_text(log)
        if result.returncode or 'SCRIPT ERROR' in log or 'BREEZE_TRANSPORT_DONE failures=0' not in log:
            raise RuntimeError(log)
        expected = ['stream_fixture', 'wav_fixture', 'corrupt_fixture', 'spike', 'cancel_fixture', None, 'lily_valley', 'stream_fixture']
        if [r['character_id'] for r in server.requests] != expected:
            raise RuntimeError('Identity routing mismatch: '+str(server.requests))
        if server.warming_probes != 2:
            raise RuntimeError('Capability retry did not recover from the warming router')
        print('PASS: capability detection/recovery, Lily identity routing, live PCM, Spike director handoff, WAV fallback, corruption, cancellation, legacy server, prebuffer hint')
    finally:
        server.shutdown(); server.server_close(); thread.join()
    (work/'result.json').write_text(json.dumps({'enabled': True, 'disabled': True,
        'transport': True, 'replacement_compat': True, 'eye_fields_match': len(eyes[0]), 'game_release': str(source)}, indent=2)+'\n')
    print('PASS: all 55 eye mesh/shader fields match the unmodified game')


if __name__ == '__main__':
    main()
