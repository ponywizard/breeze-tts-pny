"""Prepare a fresh Windows game folder with a separate Breeze playtest profile."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.files import sha, write_json
from breeze_pny.platforms import platform_id

PROFILE = 'home-equestria-breeze-windows-playtest'
MARKER = '; Breeze TTS PNY isolated Windows playtest'


def install_mod_pack(pack, mods):
    """Keep one active Breeze pack; preserve previous candidates outside mods/."""
    mods.mkdir(parents=True, exist_ok=True)
    target = mods / pack.name
    temporary = target.with_suffix('.pck.pending')
    old = list(mods.glob('breeze_tts_pny-*-windows-x86_64.pck'))
    try:
        shutil.copy2(pack, temporary)
        for previous in old:
            digest = sha(previous)
            if previous.name == pack.name and digest == sha(pack):
                continue
            backup = mods.parent / 'breeze-mod-backups' / digest / previous.name
            if backup.exists() and sha(backup) != digest:
                raise ValueError('Previous mod backup failed verification')
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(previous, backup)
        temporary.replace(target)
        for previous in old:
            if previous != target:
                previous.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def prepare(game):
    if platform_id() != 'windows-x86_64': raise ValueError('Run this helper on Windows')
    game = game.expanduser().resolve()
    executable = game / 'HomeEquestria.exe'
    if not all((game / name).is_file() for name in ('HomeEquestria.exe', 'HomeEquestria.pck', 'HomeEquestria-data.pck')):
        raise ValueError('Choose a fresh extracted Home: Equestria 0.3.0 Windows folder')
    override = game / 'override.cfg'
    if override.exists() and not override.read_text(encoding='utf-8').startswith(MARKER):
        raise ValueError('That game folder already has override.cfg; choose a fresh extraction')
    probe = game / 'breeze-playtest-profile-check.gd'
    if probe.exists(): raise ValueError('Playtest profile probe already exists')
    original = override.read_bytes() if override.exists() else None
    override.write_text(MARKER + '\n[application]\nconfig/use_custom_user_dir=true\n'
                        'config/custom_user_dir_name="' + PROFILE + '"\n', encoding='utf-8')
    probe.write_text('extends SceneTree\nfunc _initialize() -> void:\n'
                     '\tprint("BREEZE_PROFILE ",JSON.stringify({"user_path":OS.get_user_data_dir(),'
                     '"version":ProjectSettings.get_setting("application/config/version","")}))\n\tquit()\n', encoding='utf-8')
    prepared = False
    try:
        result = subprocess.run([str(executable), '--headless', '--xr-mode', 'off', '--script', str(probe)],
                                cwd=game, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        log = result.stdout + result.stderr
        (game / 'breeze-profile-check.log').write_text(log, encoding='utf-8')
        receipt = next((json.loads(line.split('BREEZE_PROFILE ', 1)[1]) for line in log.splitlines() if line.startswith('BREEZE_PROFILE ')), None)
        if result.returncode or not receipt or receipt['version'] != '0.3.0-maredev':
            raise ValueError('Game/profile verification failed; inspect breeze-profile-check.log')
        user = Path(receipt['user_path']).resolve()
        expected = (Path(os.environ['APPDATA']) / PROFILE).resolve()
        if user != expected:
            raise ValueError('Game did not select the isolated playtest profile; setup stopped')
        mods = user / 'mods'; mods.mkdir(parents=True, exist_ok=True)
        packs = sorted((ROOT / 'game-mod').glob('breeze_tts_pny-*-windows-x86_64.pck'))
        if len(packs) != 1:
            raise ValueError('Expected exactly one Breeze TTS PNY Windows pack in game-mod; setup stopped')
        pack = packs[0]
        install_mod_pack(pack, mods)
        config = user / 'ai_config.json'
        current = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        if config.exists() and not config.with_suffix('.before-breeze.json').exists():
            shutil.copy2(config, config.with_suffix('.before-breeze.json'))
        current.setdefault('tts', {}).update({'provider': 'moss', 'url': 'http://127.0.0.1:18792/tts', 'voice_mode': 'auto'})
        write_json(config, current)
        launcher = ('@echo off\nchcp 65001 >nul\nsetlocal DisableDelayedExpansion\n'
                    'pushd "%~dp0" || exit /b 1\n'
                    '"HomeEquestria.exe" --xr-mode off --log-file "breeze-windows-playtest.log" -- --verbose-log %*\n'
                    'set "result=%errorlevel%"\npopd\nexit /b %result%\n')
        (game / 'play-breeze-flat.cmd').write_bytes(launcher.replace('\n', '\r\n').encode('utf-8'))
        write_json(ROOT / 'playtest-location.json', {'game_directory': str(game), 'profile': PROFILE,
                                                   'mod_pack': pack.name, 'mod_sha256': sha(pack)})
        prepared = True
        print('Prepared isolated profile:', user)
        print('Start the companion, then run:', game / 'play-breeze-flat.cmd')
        print('Configure your LLM and optional STT in this separate profile before conversation testing.')
    finally:
        probe.unlink(missing_ok=True)
        if not prepared:
            if original is None: override.unlink(missing_ok=True)
            else: override.write_bytes(original)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', nargs='?', type=Path)
    args = parser.parse_args()
    try:
        game = args.game
        if game is None:
            print('Choose your separate Home: Equestria Windows PLAYTEST folder.')
            print('Open that folder in File Explorer, press Alt+D then Ctrl+C,')
            print('then paste the path here and press Enter. Your normal game folder stays separate.')
            value = input('Playtest game folder: ').strip().strip('"')
            if not value:
                raise ValueError('No game folder selected')
            game = Path(value)
        if game.name.lower() == 'homeequestria.exe':
            game = game.parent
        prepare(game)
    except (OSError, ValueError, EOFError, subprocess.SubprocessError) as error:
        print('Playtest setup failed:', error, file=sys.stderr)
        sys.exit(1)
