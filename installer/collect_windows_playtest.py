"""Collect this kit's playtest logs without copying saves or AI credentials."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'installer'))
from prepare_windows_playtest import PROFILE


def collect(root, appdata):
    location = root / 'playtest-location.json'
    if not location.exists():
        raise ValueError('Run prepare-playtest.cmd from this copy of the kit first')
    prepared = json.loads(location.read_text(encoding='utf-8'))
    if prepared.get('profile') != PROFILE:
        raise ValueError('This is not the isolated Breeze Windows playtest profile')
    game = Path(prepared['game_directory'])
    files = {}
    def add(path, name):
        if path.is_file():
            files[name] = path
    for name in ('breeze-windows-playtest.log', 'breeze-profile-check.log'):
        add(game / name, 'game/' + name)
    add(appdata / PROFILE / 'logs/godot.log', 'game/profile-godot.log')
    add(root / 'SMOKE-CHECKLIST.txt', 'SMOKE-CHECKLIST.txt')
    add(root / 'test-kit.json', 'test-kit.json')
    add(root / 'test-results/voice-check.txt', 'voice-check.txt')
    logs = root / 'companion/logs'
    latest = sorted(logs.glob('companion-*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    for path in latest:
        add(path, 'companion/' + path.name)
        native = path.with_name(path.name.replace('companion-', 'native-').replace('.jsonl', '.log'))
        add(native, 'companion/' + native.name)
    if not any(name.startswith('game/') for name in files):
        raise ValueError('No playtest game logs found; launch play-breeze-flat.cmd once first')
    destination = root / 'test-results'
    destination.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    output = destination / ('windows-smoke-' + stamp + '.zip')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(files.items()):
            archive.write(path, name)
        archive.writestr('collection.json', json.dumps({'platform': platform.platform(),
            'python': platform.python_version(), 'mod_pack': prepared.get('mod_pack'),
            'mod_sha256': prepared.get('mod_sha256'), 'files': sorted(files),
            'notes': ['No AI configuration, saves, model weights or private SSH keys are collected.',
                      'Game logs can contain conversations; review before sharing.']}, indent=2) + '\n')
    return output


if __name__ == '__main__':
    try:
        output = collect(ROOT, Path(os.environ['APPDATA']))
        print('Collected:', output)
        print('Copy the test-results folder back into BreezePNY on the thumb drive.')
    except (OSError, ValueError, KeyError) as error:
        print('Log collection failed:', error, file=sys.stderr)
        sys.exit(1)
