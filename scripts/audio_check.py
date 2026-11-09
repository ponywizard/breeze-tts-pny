#!/usr/bin/env python3
"""Exercise packaged playback on a private PulseAudio sink using supplied PCM."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
MOD_VERSION = json.loads((ROOT/'mods/breeze_tts_pny/mod.json').read_text())['version']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--speech-pcm', type=Path, required=True, help='1-4 seconds, mono s16le at 24 kHz; not distributed')
    parser.add_argument('--actor', choices=['openpony', 'spike'], default='openpony')
    args = parser.parse_args()
    pcm = args.speech_pcm.read_bytes()
    if not 48000 <= len(pcm) <= 192000 or len(pcm) % 2:
        raise ValueError('Supply 1-4 seconds of mono 24 kHz s16le speech')
    work = ROOT/'build'/('audio-'+str(time.time_ns()))
    work.mkdir(parents=True)
    (work/'voice.pcm').write_bytes(pcm)
    for rate in (24000, 48000):
        with wave.open(str(work/f'voice{rate//1000}.wav'), 'wb') as wav:
            wav.setparams((1,2,rate,0,'NONE','not compressed'))
            wav.writeframes(pcm if rate == 24000 else b''.join(pcm[i:i+2]*2 for i in range(0,len(pcm),2)))
    mods = work/'user/home-equestria-public/mods'
    mods.mkdir(parents=True)
    pack = ROOT/f'dist/breeze_tts_pny-{MOD_VERSION}-linux-x86_64.pck'
    shutil.copy2(pack, mods/pack.name)
    release = ROOT/'build/verify/game'
    if not release.exists(): raise RuntimeError('Run verify.py first to prepare the isolated game')
    name = f'breeze_pny_test_{os.getpid()}'
    module = subprocess.check_output(['pactl','load-module','module-null-sink',f'sink_name={name}'], text=True).strip()
    try:
        env = {**os.environ, 'XDG_DATA_HOME':str(work/'user'), 'PULSE_SINK':name}
        for key in ('EQ_PCM_STREAM','EQ_PCM_PLAYBACK','EQ_TALKING_AVATAR'): env.pop(key,None)
        command = [str(release/'HomeEquestria.x86_64'),'--headless','--audio-driver','PulseAudio',
            '--xr-mode','off','--script',str(ROOT/'tests/run_playback.gd'),'--',str(work),str(ROOT/'tests/playback.gd')]
        if args.actor == 'spike': command.append('--spike')
        result = subprocess.run(command,
            cwd=release,env=env,capture_output=True,text=True,timeout=90)
        log = result.stdout+result.stderr
        (work/'test.log').write_text(log)
        if result.returncode or 'SCRIPT ERROR' in log or 'TA_PLAYBACK_MIXER_SHORT_EOF_UNDERRUN_CANCEL_CORRUPTION_RETRY_TURN_WAV_PASS' not in log:
            raise RuntimeError(log)
        print((work/'playback-results.json').read_text())
        print(f'PASS: {args.actor} packaged real mixer playback, lip-sync, EOF, rebuffer, cancellation, corruption, retry and WAV')
    finally:
        subprocess.run(['pactl','unload-module',module],check=True)


if __name__ == '__main__':
    main()
