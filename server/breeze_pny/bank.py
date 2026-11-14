"""Validate portable character routing, inference settings and cached voices."""
import math
import re
from .files import read_json, relative, verify_files

ID = re.compile(r'[A-Za-z0-9_-]{1,64}')
EMOTION = re.compile(r'^\[(?:neutral|happy|sad|angry|annoyed|fearful|surprised|calm|disgusted|whispering|nonverbal|shouting)\]\s*', re.I)


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def settings(value):
    if not isinstance(value, dict) or set(value) - {'cfg_scale', 'temperature', 'depth_temperature', 'instruction', 'lora'}:
        raise ValueError('Unsupported voice inference setting')
    if not number(value.get('cfg_scale', 1), 1, 4): raise ValueError('Invalid guidance')
    for key in ('temperature', 'depth_temperature'):
        if key in value and not number(value[key], .001, 2): raise ValueError('Invalid temperature')
    if not isinstance(value.get('instruction', ''), str) or len(value.get('instruction', '')) > 600:
        raise ValueError('Invalid voice instruction')
    adapter = value.get('lora', '')
    if not isinstance(adapter, str) or (adapter and not ID.fullmatch(adapter)):
        raise ValueError('Invalid adapter ID')
    return {'cfg_scale': 1, 'lora': '', **value}


def load_bank(root):
    data = read_json(root / 'voice-pack.json')
    if data.get('schema') != 1 or not ID.fullmatch(data.get('id', '')):
        raise ValueError('Unsupported voice pack')
    verify_files(root, data.get('files'))
    rows = data.get('characters', [])
    if not 1 <= len(rows) <= 1000: raise ValueError('Expected 1-1000 character routes')
    characters = {}
    for row in rows:
        identity = row.get('id', '')
        if not ID.fullmatch(identity) or identity in characters: raise ValueError('Invalid/duplicate character')
        row = dict(row)
        if row.get('route') == 'breeze':
            voice = row.get('voice_id', '')
            if not ID.fullmatch(voice) or voice not in data.get('voices', {}): raise ValueError('Missing cached voice')
            row['settings'] = settings(row.get('settings', {}))
            if row['settings']['lora'] and row['settings']['lora'] not in data.get('adapters', {}):
                raise ValueError('Missing required adapter')
        else: raise ValueError('Unsupported voice route')
        characters[identity] = row
    for voice, info in data.get('voices', {}).items():
        if not ID.fullmatch(voice) or info.get('file') != f'voices/{voice}.breeze' or info['file'] not in data['files']:
            raise ValueError('Invalid cached voice file')
        if not isinstance(info.get('ref_text'), str) or not re.fullmatch('[0-9a-f]{64}', info.get('reference_sha256', '')):
            raise ValueError('Missing voice provenance')
        reference = info.get('reference_file')
        if reference is not None:
            if not isinstance(reference, str) or data['files'].get(reference) != info['reference_sha256']:
                raise ValueError('Reference recording must match the registered WAV hash')
            relative(root, reference)
    for adapter, name in data.get('adapters', {}).items():
        if not ID.fullmatch(adapter) or name not in data['files']: raise ValueError('Invalid adapter file')
        relative(root, name)
    for speaker, identity in data.get('legacy_speakers', {}).items():
        if not speaker.isdecimal() or identity not in characters: raise ValueError('Invalid legacy speaker map')
    overrides = data.get('custom_voices', {})
    if not isinstance(overrides, dict): raise ValueError('Invalid personal voice mapping')
    for character, voice in overrides.items():
        if character not in characters or characters[character]['voice_id'] != voice:
            raise ValueError('Personal voice mapping differs from character routing')
    data['routes'] = characters
    return data


def resolve(bank, body):
    if not isinstance(body, dict): raise ValueError('Expected a speech object')
    text = body.get('text')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600: raise ValueError('Expected 1-600 characters')
    identity = body.get('character_id', '')
    if not isinstance(identity, str): raise ValueError('Invalid character ID')
    if not identity:
        speaker = body.get('speaker_id', 31)
        if type(speaker) is not int: raise ValueError('Invalid speaker ID')
        identity = bank.get('legacy_speakers', {}).get(str(speaker), '')
    if identity not in bank['routes']: raise ValueError('Unknown character ID')
    text = EMOTION.sub('', text.strip(), count=1).strip()
    if not text: raise ValueError('No spoken text')
    return bank['routes'][identity], text
