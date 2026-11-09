#!/usr/bin/env python3
"""Record whole-card AMD GPU usage for an isolated Linux flatscreen playtest."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def health(url):
    with OPENER.open(url.rstrip('/') + '/health', timeout=3) as response:
        return json.loads(response.read(65536))


def gpu_sample(device):
    values = {name: int((device / name).read_text().strip())
              for name in ('mem_info_vram_total', 'mem_info_vram_used')}
    if values['mem_info_vram_total'] <= 0 or values['mem_info_vram_used'] < 0:
        raise ValueError('Invalid GPU memory counters')
    values['vram_free_bytes'] = max(0, values['mem_info_vram_total'] - values['mem_info_vram_used'])
    for name in ('mem_info_gtt_used', 'gpu_busy_percent'):
        try:
            values[name] = int((device / name).read_text().strip())
        except (OSError, ValueError):
            values[name] = None
    return {'epoch_s': time.time(), **values}


def stop_owned(child):
    if child is None or child.poll() is not None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)


def validate(config):
    game = Path(config['game_directory']).resolve() / 'HomeEquestria.x86_64'
    if not game.is_file() or not os.access(game, os.X_OK):
        raise ValueError('Missing executable: ' + str(game))
    with Path(config['mod_pack']).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != config['mod_sha256']:
            raise ValueError('Staged mod differs from the validated candidate')
    profile = Path(config['user_data_home']).resolve() / 'home-equestria-public'
    settings = json.loads((profile / 'ai_config.json').read_text())
    url = config['companion_url'].rstrip('/')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('This playtest requires a local companion')
    if settings.get('tts', {}).get('provider') != 'moss' or settings['tts'].get('url') != url + '/tts':
        raise ValueError('Isolated profile does not select this local companion')
    status = health(url)
    if not status.get('ready') or status.get('native_backend') != 'breeze':
        raise ValueError('Start local Breeze and wait for its ready event')
    devices = [p for p in Path('/sys/class/drm').glob('card[0-9]*/device')
               if (p / 'mem_info_vram_total').exists()]
    if config.get('gpu_device'):
        device = Path(config['gpu_device'])
    elif len(devices) == 1:
        device = devices[0]
    else:
        raise ValueError('Set gpu_device to the AMD sysfs device to record')
    gpu_sample(device)  # Refuse unreadable counters before launching the game.
    return game, profile, status, device


def run(config):
    game, profile, status, device = validate(config)
    with (profile / 'breeze-capture.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
        folder = Path(config['output_directory']).resolve() / (stamp + '-' + str(os.getpid()))
        folder.mkdir(parents=True, exist_ok=False)
        metadata = {'mode': 'Linux flatscreen', 'mod_sha256': config['mod_sha256'],
                    'health': status, 'frame_trace_requested': False, 'sample_interval_s': .1,
                    'sysfs_device': str(device.resolve()),
                    'notes': ['Whole-card counters include the desktop, game and local inference.',
                              'Brief peaks between 100 ms samples can be missed.',
                              'No F9 step, full frame trace or pre-launch recording timeout.',
                              'The separately managed companion is left running.']}
        print('Playtest logs:', folder, flush=True)
        environment = {**os.environ, 'XDG_DATA_HOME': str(Path(config['user_data_home']).resolve())}
        for key in ('EQ_PCM_STREAM', 'EQ_PCM_PLAYBACK', 'EQ_TALKING_AVATAR', 'EQ_STREAM_VOICE', 'HOME_EQ_REQUIRE_VR'):
            environment.pop(key, None)
        child = None
        try:
            with (folder / 'console.log').open('x') as output, (folder / 'gpu.jsonl').open('x', buffering=1) as gpu:
                first = gpu_sample(device)
                gpu.write(json.dumps(first) + '\n')
                metadata['capture_started_epoch_s'] = first['epoch_s']
                command = [str(game), '--xr-mode', 'off', '--log-file', str(folder / 'godot.log'),
                           '--', '--verbose-log', '--perf-ticker']
                metadata['game_started_epoch_s'] = time.time()
                child = subprocess.Popen(command, cwd=game.parent, env=environment, stdout=output,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
                metadata['game_pid'] = child.pid
                print('Recording GPU memory until you quit the game. No F9 step is needed.', flush=True)
                while child.poll() is None:
                    gpu.write(json.dumps(gpu_sample(device)) + '\n')
                    time.sleep(.1)
                metadata['game_finished_epoch_s'] = time.time()
                metadata['game_exit_code'] = child.returncode
                last = gpu_sample(device)
                gpu.write(json.dumps(last) + '\n')
                metadata['capture_finished_epoch_s'] = last['epoch_s']
        except BaseException as error:
            metadata['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            stop_owned(child)
            metadata['game_exit_code'] = child.returncode if child else None
            (folder / 'playtest.json').write_text(json.dumps(metadata, indent=2) + '\n')
        samples = [json.loads(line) for line in (folder / 'gpu.jsonl').read_text().splitlines()]
        metadata['gpu_capture_covers_game'] = (samples[0]['epoch_s'] <= metadata['game_started_epoch_s']
            < metadata['game_finished_epoch_s'] <= samples[-1]['epoch_s'])
        metadata['gpu_samples'] = len(samples)
        metadata['whole_card_peak_vram_gib'] = max(s['mem_info_vram_used'] for s in samples) / 2**30
        metadata['whole_card_minimum_free_vram_gib'] = min(s['vram_free_bytes'] for s in samples) / 2**30
        (folder / 'playtest.json').write_text(json.dumps(metadata, indent=2) + '\n')
        if not metadata['gpu_capture_covers_game']:
            raise RuntimeError('GPU recording did not cover the whole game session')
        print('Capture complete:', folder / 'playtest.json', flush=True)
        return child.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Private JSON paths for the isolated playtest')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        return run(json.loads(args.config.read_text()))
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Playtest: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
