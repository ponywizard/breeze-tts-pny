"""Opt-in real-model validation, using an isolated clone of a companion install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from breeze_pny.files import read_json, write_json
from breeze_pny.service import get
from breeze_pny.voice_edit import VoiceEditor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--character', default='derpy_hooves')
    args = parser.parse_args()
    original = args.config.resolve()
    work = ROOT / 'build/voice-library-validation' / uuid.uuid4().hex
    work.mkdir(parents=True)
    # Runtime/model files are read-only inputs. Links avoid copying model weights;
    # references and configuration are activated only inside this isolated clone.
    def clone(source, destination):
        try: return os.link(source, destination)
        except OSError: return shutil.copy2(source, destination)
    for directory in ('models', 'assets'):
        shutil.copytree(original.parent / directory, work / directory, copy_function=clone)
    config = read_json(original)
    write_json(work / 'config.json', config)
    editor = VoiceEditor(work / 'config.json')
    try:
        row = editor.bank['routes'][args.character]
        info = editor.bank['voices'][row['voice_id']]
        result = editor.prepare(args.character, info['ref_text'], args.reference.read_bytes(), 'Isolated validation of the existing accepted reference')
        preview = editor.audition(args.character, 'Hello there.', result['id'])
        (work / 'preview.wav').write_bytes(preview)
        editor.apply(result['id'])
        voice = editor.bank['routes'][args.character]['voice_id']
        expected = editor.bank['voices'][voice]
    finally:
        editor.close()
    editor = VoiceEditor(work / 'config.json')
    try:
        editor.start_native()
        actual = get(f'http://127.0.0.1:{editor.native_port}/v1/voices/{voice}')
        assert actual['ref_text'] == expected['ref_text']
        assert actual['metadata']['reference_sha256'] == expected['reference_sha256']
        assert actual['saved']
        restored = editor.audition(args.character, 'Hello there.')
        (work / 'reloaded-preview.wav').write_bytes(restored)
        editor.undo()
        assert editor.config['voice_pack'] == config['voice_pack']
    finally:
        editor.close()
    assert read_json(original) == config
    report = {'character': args.character, 'reference_registered': True, 'preview_generated': True,
              'custom_pack_validated': True, 'saved_cache_reloaded': True, 'undo_restored_original_pack': True,
              'original_configuration_unchanged': True, 'preview_bytes': len(preview),
              'preview_sha256': hashlib.sha256(preview).hexdigest()}
    write_json(work / 'result.json', report)
    print(json.dumps(report, indent=2))
    print('Evidence:', work.relative_to(ROOT))


if __name__ == '__main__': main()
