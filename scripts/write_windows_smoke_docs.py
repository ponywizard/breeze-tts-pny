#!/usr/bin/env python3
"""Render the offline Windows smoke kit's text guides and double-click helpers."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--ssh-target', required=True)
    parser.add_argument('--host-key', required=True)
    parser.add_argument('--llm-model', required=True)
    parser.add_argument('--stt-model', required=True)
    parser.add_argument('--wine-checked', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+', args.ssh_target):
        parser.error('Use a simple user@host SSH target')
    args.kit.mkdir(parents=True, exist_ok=True)
    version = json.loads((ROOT / 'mods/breeze_tts_pny/mod.json').read_text())['version']
    release = json.loads((args.kit / 'release.json').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    values = {'MOD_VERSION':version,'COMPANION_VERSION':release['version'],
              'DATE':datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'SOURCE_COMMIT':commit,
              'SSH_TARGET':args.ssh_target,'HOST_KEY':args.host_key,
              'LLM_MODEL':args.llm_model,'STT_MODEL':args.stt_model}
    for path in sorted((ROOT / 'installer/windows-smoke').iterdir()):
        text = path.read_text(encoding='utf-8')
        for key, value in values.items():
            text = text.replace('@' + key + '@', value)
        if re.search(r'@[A-Z_]+@', text):
            raise ValueError('Unresolved template field: ' + path.name)
        (args.kit / path.name).write_bytes(text.replace('\n', '\r\n').encode('utf-8'))
    (args.kit / 'test-kit.json').write_text(json.dumps({'schema':1,'type':'unreleased-windows-smoke',
        'source_commit':commit,'game_mod_version':version,'companion_version':release['version'],
        'automated_wine_checks_passed':args.wine_checked,'native_windows_smoke':'pending',
        'runtime_sha256':release['runtime_bundle']['sha256'],
        'voice_pack_sha256':release['voice_pack']['sha256']},indent=2)+'\n')
    print('Wrote Windows smoke guides and helpers:', args.kit)


if __name__ == '__main__':
    main()
