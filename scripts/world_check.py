#!/usr/bin/env python3
"""Create and reload an isolated test world with the packaged mod installed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
MOD_VERSION = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())['version']


def main():
    work = ROOT/'build'/('world-'+str(time.time_ns()))
    user = work/'user/home-equestria-public'
    (user/'mods').mkdir(parents=True)
    shutil.copy2(ROOT/f'dist/breeze_tts_pny-{MOD_VERSION}-linux-x86_64.pck', user/'mods')
    (user/'ai_config.json').write_text(json.dumps({'ai_usage':'talk',
        'llm':{'provider':'openai','base_url':'','model':''},
        'tts':{'provider':'none'},'stt':{'provider':'off'}}))
    release = ROOT/'build/verify/game'
    result = subprocess.run([str(release/'HomeEquestria.x86_64'),'--headless','--audio-driver','Dummy',
        '--xr-mode','off','--script',str(ROOT/'tests/world_cycle.gd')], cwd=release,
        env={**os.environ,'XDG_DATA_HOME':str(work/'user')}, capture_output=True,text=True,timeout=210)
    log = result.stdout+result.stderr
    (work/'world.log').write_text(log)
    if result.returncode or 'SCRIPT ERROR' in log or 'Could not resume' in log or 'BREEZE_WORLD_CYCLE_DONE' not in log:
        raise RuntimeError(log[-8000:])
    print('PASS: new world, real director/TTS extension, save, reload, restored day/world identity')
    print(work/'world.log')


if __name__ == '__main__':
    main()
