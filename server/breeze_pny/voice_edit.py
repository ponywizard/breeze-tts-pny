"""Stage, audition and atomically activate personal reference voices."""
import copy
import hashlib
import http.client
import io
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import uuid
import wave

from .bank import ID, load_bank
from . import REFERENCE_MANAGER_VERSION
from .files import read_json, relative, sha, write_json
from .native import NativePCM
from .playback import RationalPCM
from .platforms import acquire_lock, runtime_environment
from .service import get, inspect

MAX_REFERENCE_BYTES = 24000 * 2 * 30 + 4096


def reference_wav(raw):
    """Validate the browser's conversion, and strip non-audio WAV chunks."""
    if not 44 <= len(raw) <= MAX_REFERENCE_BYTES:
        raise ValueError('Choose a reference between 0.25 and 30 seconds long')
    try:
        with wave.open(io.BytesIO(raw)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, 'NONE'):
                raise ValueError('The converted reference must be mono 24 kHz PCM16 WAV')
            frames = wav.getnframes()
            if not 6000 <= frames <= 720000:
                raise ValueError('Choose a reference between 0.25 and 30 seconds long')
            pcm = wav.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError('The reference WAV is truncated')
    except (wave.Error, EOFError) as error:
        raise ValueError('The reference could not be read as PCM WAV') from error
    if not any(pcm):
        raise ValueError('The reference contains only silence')
    return pcm_wav(pcm)


def pcm_wav(pcm):
    result = io.BytesIO()
    with wave.open(result, 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return result.getvalue()


def custom_pack(prefix, base_root, replacements, additions=(), *, removals=()):
    """Copy verified assets and publish a complete pack before changing config."""
    base = load_bank(base_root)
    bank = copy.deepcopy(base)
    bank.pop('routes', None)
    for character in removals:
        if character not in bank.get('custom_characters', []):
            raise ValueError('Only added custom voices can be removed')
        bank['characters'] = [row for row in bank['characters'] if row['id'] != character]
        bank['custom_characters'].remove(character)
        bank['custom_voices'].pop(character)
        bank['legacy_speakers'] = {speaker: identity for speaker, identity in bank.get('legacy_speakers', {}).items()
                                   if identity != character}
    if not bank['characters']:
        raise ValueError('Keep at least one voice in the voice pack')
    for row in additions:
        if any(existing['id'].casefold() == row['id'].casefold() for existing in bank['characters']):
            raise ValueError('The voice pack already has a character named ' + row['id'])
        bank['characters'].append(copy.deepcopy(row))
        bank.setdefault('custom_characters', []).append(row['id'])
    parent = prefix / 'assets/voice-packs'
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / ('custom-' + uuid.uuid4().hex)
    staging = Path(tempfile.mkdtemp(prefix='.voice-edit-', dir=parent))
    try:
        for name in base['files']:
            target = relative(staging, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(relative(base_root, name), target)
        for character, info, assets in replacements:
            row = next((r for r in bank['characters'] if r['id'] == character), None)
            if row is None:
                raise ValueError('The new voice pack has no character named ' + character)
            if info.get('output_speed', 1) != row.get('output_speed', 1):
                raise ValueError('The voice playback profile changed; re-register and audition the personal reference with this pack')
            voice = Path(info['file']).stem
            if not ID.fullmatch(voice):
                raise ValueError('Invalid custom voice ID')
            for name, raw in assets.items():
                target = relative(staging, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                bank['files'][name] = hashlib.sha256(raw).hexdigest()
            row['voice_id'] = voice
            bank['voices'][voice] = copy.deepcopy(info)
            bank.setdefault('custom_voices', {})[character] = voice
        bank['id'] = base['id'][:50].removesuffix('-custom') + '-custom'
        bank['version'] = 'personal-' + destination.name[7:19]
        write_json(staging / 'voice-edit.json', {
            'schema': 1, 'previous_voice_pack': base_root.relative_to(prefix).as_posix(),
            'characters': [r[0] for r in replacements] + list(removals),
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        })
        bank['files']['voice-edit.json'] = sha(staging / 'voice-edit.json')
        write_json(staging / 'voice-pack.json', bank)
        load_bank(staging)
        staging.rename(destination)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def preserve_custom_voices(prefix, previous, base_root):
    """Reapply personal references to a newly installed curated pack."""
    old = load_bank(previous)
    overrides = old.get('custom_voices', {})
    if not overrides:
        return base_root
    base = load_bank(base_root)
    if old['model_sha256'] != base['model_sha256']:
        raise ValueError('Personal voices require the previous model; re-register them before this update')
    replacements = []
    for character, voice in overrides.items():
        info = old['voices'][voice]
        names = [info['file']]
        if info.get('reference_file'):
            names.append(info['reference_file'])
        replacements.append((character, info, {name: relative(previous, name).read_bytes() for name in names}))
    additions = [row for row in old['characters'] if row['id'] in old.get('custom_characters', [])]
    return custom_pack(prefix, base_root, replacements, additions)


class VoiceEditor:
    def __init__(self, config_path, reference_directory=None):
        self.config_path = Path(config_path).resolve()
        self.prefix = self.config_path.parent
        self.lock = (self.prefix / 'service.lock').open('a+b')
        self.work = self.child = self.log = None
        try:
            try:
                acquire_lock(self.lock)
            except BlockingIOError:
                raise ValueError('Stop the companion, then open the voice library again') from None
            self.config = read_json(self.config_path)
            self.bank_root = relative(self.prefix, self.config['voice_pack'])
            self.bank = load_bank(self.bank_root)
            self.reference_directory = Path(reference_directory).expanduser().resolve() if reference_directory else None
            self.work = tempfile.TemporaryDirectory(prefix='breeze-voices-')
            self.workspace = Path(self.work.name)
            (self.workspace / 'voices').mkdir()
            for info in self.bank['voices'].values():
                shutil.copy2(relative(self.bank_root, info['file']), self.workspace / info['file'])
            self.pending = None
        except BaseException:
            self.close()
            raise

    def close(self):
        self.stop_native()
        if self.work is not None:
            self.work.cleanup()
            self.work = None
        self.lock.close()

    def stop_native(self):
        if self.child is not None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
            self.child = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def unchanged(self):
        if read_json(self.config_path) != self.config:
            raise ValueError('The companion configuration changed; close and reopen the voice library')

    def reference(self, voice):
        if voice not in self.bank['voices']:
            raise ValueError('Unknown voice')
        info = self.bank['voices'][voice]
        if info.get('reference_file'):
            return relative(self.bank_root, info['reference_file'])
        if self.reference_directory:
            candidate = self.reference_directory / (voice + '.wav')
            if candidate.is_file() and sha(candidate) == info['reference_sha256']:
                return candidate
        return None

    def state(self):
        rows = []
        for row in self.bank['characters']:
            voice = row['voice_id']
            info = self.bank['voices'][voice]
            rows.append({'id': row['id'], 'name': row.get('name', row['id']), 'voice_id': voice,
                         'transcript': info['ref_text'], 'reference_available': self.reference(voice) is not None,
                         'custom': row['id'] in self.bank.get('custom_voices', {}),
                         'added': row['id'] in self.bank.get('custom_characters', []), 'source': info.get('source', {})})
        return {'utility_version': REFERENCE_MANAGER_VERSION,
                'characters': sorted(rows, key=lambda row: row['name'].casefold()),
                'can_undo': (self.bank_root / 'voice-edit.json').is_file()}

    def start_native(self):
        if self.child is not None:
            if self.child.poll() is not None:
                raise RuntimeError('Breeze stopped; close and reopen the voice library. Check the voice-library native log.')
            return
        self.unchanged()
        config, root, runtime, binary, model, _, _ = inspect(
            self.config_path, config=getattr(self, 'runtime_config', None))
        if getattr(self, 'native_port_override', None):
            from .service import check_port
            self.native_port = self.native_port_override
            check_port('127.0.0.1', self.native_port, 'Native Breeze', wait_seconds=75,
                       stopping=getattr(self, 'stopping', None))
        else:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                self.native_port = probe.getsockname()[1]
        command = [str(binary), str(model), '--host', '127.0.0.1', '--port', str(self.native_port),
                   '--ws-port', '-1', '--parallel', '1', '--voices-dir', str(self.workspace / 'voices')]
        for adapter, filename in self.bank.get('adapters', {}).items():
            command += ['--lora', adapter + '=' + str(relative(self.bank_root, filename))]
        logs = root / 'logs'
        logs.mkdir(exist_ok=True)
        path = logs / (getattr(self, 'native_log_prefix', 'voice-library') + '-' + uuid.uuid4().hex + '.log')
        self.log = path.open('x')
        self.child = subprocess.Popen(command, cwd=root, env=runtime_environment(binary), stdin=subprocess.DEVNULL,
                                      stdout=self.log, stderr=subprocess.STDOUT)
        if getattr(self, 'native_log_prefix', None):
            from .events import event
            event('loading', native_log=str(path), native_pid=self.child.pid)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if getattr(self, 'stopping', None) and self.stopping.is_set():
                raise InterruptedError('Companion is stopping')
            if self.child.poll() is not None:
                raise RuntimeError('Breeze could not start; inspect ' + str(path))
            try:
                if get(f'http://127.0.0.1:{self.native_port}/health').get('status') == 'ok':
                    return
            except (OSError, ValueError):
                pass
            time.sleep(.25)
        raise TimeoutError('Breeze took too long to start; inspect ' + str(path))

    def new_character(self, character, name):
        if not isinstance(character, str) or not ID.fullmatch(character):
            raise ValueError('Use a voice ID of 1-64 letters, numbers, underscores or hyphens')
        if any(identity.casefold() == character.casefold() for identity in self.bank['routes']):
            raise ValueError('That voice ID already exists; choose another ID')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a voice name of 1-100 characters without control characters')
        name = name.strip()
        if any(row.get('name', row['id']).casefold() == name.casefold() for row in self.bank['characters']):
            raise ValueError('That voice name already exists; choose another name')
        if len(self.bank['characters']) >= 1000:
            raise ValueError('A voice pack can contain at most 1,000 voices')
        return {'id': character, 'name': name, 'route': 'breeze',
                'settings': {'cfg_scale': 1, 'temperature': .7, 'lora': ''}}

    def prepare(self, character, transcript, raw, source='', *, name=None):
        self.unchanged()
        addition = self.new_character(character, name) if name is not None else None
        if addition is None and (not isinstance(character, str) or character not in self.bank['routes']):
            raise ValueError('Choose a known character')
        if not isinstance(transcript, str) or not 1 <= len(transcript.strip()) <= 2000:
            raise ValueError('Enter the exact reference transcript (up to 2,000 characters)')
        if not isinstance(source, str) or len(source) > 2000:
            raise ValueError('Source notes must be at most 2,000 characters')
        raw = reference_wav(raw)
        row = addition if addition is not None else self.bank['routes'][character]
        output_speed = row.get('output_speed', 1)
        if output_speed == 1.25:
            with wave.open(io.BytesIO(raw)) as wav:
                converted = RationalPCM(5, 4).process(wav.readframes(wav.getnframes()), final=True)
            if len(converted) > 48000 * 30:
                raise ValueError('Trim this reference to at most 24 seconds before slowing it for this voice')
            raw = pcm_wav(converted)
        digest = hashlib.sha256(raw).hexdigest()
        voice = 'edit_' + character[:35] + '_' + uuid.uuid4().hex[:12]
        transcript = transcript.strip()
        self.start_native()
        boundary = 'breeze-' + uuid.uuid4().hex
        fields = {'name': voice, 'ref_text': transcript, 'metadata': json.dumps({'reference_sha256': digest})}
        body = bytearray()
        for name, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="ref_audio"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        body.extend(raw)
        body.extend(f'\r\n--{boundary}--\r\n'.encode())
        connection = http.client.HTTPConnection('127.0.0.1', self.native_port, timeout=180)
        try:
            connection.request('POST', '/v1/voices', bytes(body), {'Content-Type': 'multipart/form-data; boundary=' + boundary})
            response = connection.getresponse()
            result = json.loads(response.read(65536))
            if response.status != 200:
                raise RuntimeError('Breeze could not register the reference: ' + str(result.get('error', response.status)))
        finally:
            connection.close()
        if (result.get('id'), result.get('ref_text'), result.get('metadata', {}).get('reference_sha256'), result.get('saved')) != (voice, transcript, digest, True):
            raise ValueError('Breeze did not acknowledge the new reference correctly')
        cache = self.workspace / 'voices' / (voice + '.breeze')
        if not cache.is_file():
            raise ValueError('Breeze did not save the reference cache')
        self.pending = {'id': uuid.uuid4().hex, 'character': character, 'voice': voice, 'raw': raw,
                        'transcript': transcript, 'sha256': digest, 'cache_sha256': sha(cache),
                        'source': source.strip(), 'auditioned': False, 'output_speed': output_speed,
                        'new_character': addition}
        return {'id': self.pending['id'], 'character': character, 'seconds': (len(raw) - 44) / 48000, 'transcript': transcript}

    def audition(self, character, text, pending_id=None, watch=None):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 600:
            raise ValueError('Enter a preview line (up to 600 characters)')
        if not isinstance(character, str): raise ValueError('Choose a known character')
        row = self.bank['routes'].get(character)
        if pending_id:
            pending = self.pending
            if not pending or pending['id'] != pending_id or pending['character'] != character:
                raise ValueError('Prepare this replacement again before previewing')
            row = pending['new_character'] or row
        if row is None: raise ValueError('Choose a known character')
        row = copy.deepcopy(row)
        if pending_id:
            row['voice_id'] = pending['voice']
        self.start_native()
        reader = NativePCM(self.native_port, row, text.strip())
        cleanup = watch(reader) if watch else lambda: None
        try:
            with reader:
                pcm = b''.join(reader.chunks())
        finally:
            cleanup()
        if pending_id:
            pending['auditioned'] = True
        return pcm_wav(pcm)

    def apply(self, pending_id):
        self.unchanged()
        pending = self.pending
        if not pending or pending['id'] != pending_id or not pending['auditioned']:
            raise ValueError('Generate a replacement preview before saving')
        voice = pending['voice']
        name = f'voices/{voice}.breeze'
        cache = self.workspace / name
        if sha(cache) != pending['cache_sha256']:
            raise ValueError('The staged reference changed; prepare it again')
        reference = f'references/{voice}.wav'
        info = {'file': name, 'ref_text': pending['transcript'], 'reference_sha256': pending['sha256'],
                'output_speed': pending['output_speed'],
                'reference_file': reference, 'source': {'notes': pending['source'],
                'processing': ('Browser conversion to mono 24 kHz PCM16; no automatic normalization or denoising.'
                    + (' Reference retimed to 0.8x for the slow-trained adapter.' if pending['output_speed'] == 1.25 else ''))}}
        additions = [pending['new_character']] if pending['new_character'] else []
        destination = custom_pack(self.prefix, self.bank_root, [
            (pending['character'], info, {name: cache.read_bytes(), reference: pending['raw']})], additions)
        return self._activate(destination)

    def remove_voice(self, character):
        self.unchanged()
        if not isinstance(character, str) or character not in self.bank.get('custom_characters', []):
            raise ValueError('Only added custom voices can be removed')
        destination = custom_pack(self.prefix, self.bank_root, [], removals=(character,))
        return self._activate(destination)

    def _activate(self, destination):
        config = {**self.config, 'voice_pack': destination.relative_to(self.prefix).as_posix()}
        write_json(self.config_path, config)
        self.config, self.bank_root = config, destination
        self.bank = load_bank(destination)
        self.pending = None
        return self.state()

    def undo(self):
        self.unchanged()
        path = self.bank_root / 'voice-edit.json'
        if not path.is_file():
            raise ValueError('There is no previous voice-pack change to restore')
        receipt = read_json(path)
        previous = relative(self.prefix, receipt['previous_voice_pack'])
        bank = load_bank(previous)
        from .models import compatible
        if not compatible(bank['model_sha256'], self.config['model_sha256']):
            raise ValueError('The previous voice pack requires a different model')
        config = {**self.config, 'voice_pack': previous.relative_to(self.prefix).as_posix()}
        write_json(self.config_path, config)
        self.config, self.bank_root, self.bank = config, previous, bank
        self.pending = None
        return self.state()
