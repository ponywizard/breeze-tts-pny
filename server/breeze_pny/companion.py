"""One installation owner for generation, reference editing and model lifecycle."""
import copy
import threading

from . import __version__
from .events import event
from .files import write_json
from .models import CATALOG, by_digest, choose, compatible, download, model_path
from .router import Router
from .service import get, inspect
from .voice_edit import VoiceEditor


class Companion(VoiceEditor):
    def __init__(self, config_path, reference_directory=None, native_port=None):
        super().__init__(config_path, reference_directory)
        try:
            inspect(config_path, dependencies=False, model_required=False)
        except BaseException:
            self.close()
            raise
        self.native_port_override = native_port or self.config['native_port']
        self.native_port = self.native_port_override
        self.api_port = self.config['port']
        self.api_host = self.config.get('host', '127.0.0.1')
        self.native_log_prefix = 'native'
        self.stopping = threading.Event()
        self.cancel_download = threading.Event()
        self._metadata = threading.RLock()
        self._jobs = threading.Lock()
        self.worker = None
        self.job = None
        self.loaded = None
        self.phase = 'unloaded'
        self.error = None
        self.router = Router(self.bank, self.native_port, self.healthy)

    def healthy(self):
        return not self.stopping.is_set() and self.phase == 'ready' and self.child is not None and self.child.poll() is None

    def start_native(self):
        # Reference operations share the explicitly loaded model; Unload stays unloaded.
        if not self.healthy():
            raise ValueError('Load a model in Models before generating or preparing a reference')

    def _start(self, config):
        self.runtime_config = config
        try:
            VoiceEditor.start_native(self)
            cached = {row['id']: row for row in get(f'http://127.0.0.1:{self.native_port}/v1/voices')}
            for voice, info in self.bank['voices'].items():
                actual = cached.get(voice, {})
                if (actual.get('metadata', {}).get('reference_sha256') != info['reference_sha256']
                        or actual.get('ref_text') != info['ref_text']):
                    raise ValueError('Native voice cache differs from pack: ' + voice)
        finally:
            self.runtime_config = None

    def load_model(self, identity=None):
        self.unchanged()
        previous = dict(self.config)
        was_ready = self.healthy()
        candidate = dict(previous)
        if identity is not None:
            item = choose(identity)
            if not compatible(self.bank['model_sha256'], item['sha256']):
                raise ValueError('This voice pack is not compatible with the selected model')
            path = model_path(self.prefix, item)
            candidate.update(model=path.relative_to(self.prefix).as_posix(), model_sha256=item['sha256'])
        # Validate before releasing the working model, including files and runtime dependencies.
        inspect(self.config_path, config=candidate)
        self.phase, self.error = 'loading', None
        self.pending = None
        self.stop_native()
        self.loaded = None
        try:
            self._start(candidate)
            candidate['autoload'] = True
            write_json(self.config_path, candidate)
            with self._metadata:
                self.config = candidate
                self.loaded = candidate['model_sha256']
                self.phase = 'ready'
            event('ready', **self.router.health(), model=(by_digest(self.loaded) or {}).get('id', 'custom'))
        except Exception as error:
            self.stop_native()
            self.phase, self.error = 'error', str(error)
            if was_ready and not self.stopping.is_set():
                try:
                    self._start(previous)
                    self.loaded, self.phase = previous['model_sha256'], 'ready'
                except Exception as recovery:
                    self.stop_native()
                    self.error += '; previous model could not restart: ' + str(recovery)
            raise

    def unload_model(self):
        self.unchanged()
        config = {**self.config, 'autoload': False}
        write_json(self.config_path, config)
        self.config = config
        self.phase = 'unloading'
        self.stop_native()
        self.loaded, self.phase, self.error = None, 'unloaded', None

    def delete_model(self, identity):
        item = choose(identity)
        if item['sha256'] == self.loaded:
            raise ValueError('Unload this model before deleting its download')
        with self._metadata:
            if item['sha256'] == self.config['model_sha256']:
                self.unchanged()
                config = {**self.config, 'autoload': False}
                write_json(self.config_path, config)
                self.config = config
            model_path(self.prefix, item).unlink(missing_ok=True)

    def state(self):
        with self._metadata:
            data = super().state()
            models = []
            for item in CATALOG.values():
                path = model_path(self.prefix, item)
                models.append({**item, 'installed': path.is_file() and path.stat().st_size == item['bytes'],
                               'selected': item['sha256'] == self.config['model_sha256'],
                               'loaded': item['sha256'] == self.loaded and self.healthy(),
                               'compatible': compatible(self.bank['model_sha256'], item['sha256'])})
            return {**data, 'version': __version__, 'models': models, 'ready': self.healthy(),
                    'phase': self.phase, 'error': self.error, 'job': copy.deepcopy(self.job),
                    'voice_pack': self.bank['id'], 'autoload': self.config.get('autoload', True),
                    'api_host': self.api_host, 'api_port': self.api_port, 'speech_busy': self.router.lock.locked()}

    def apply(self, pending_id):
        with self._metadata:
            result = super().apply(pending_id)
            self.router.bank = self.bank
            return result

    def undo(self):
        with self._metadata:
            result = super().undo()
            self.router.bank = self.bank
            return result

    def remove_voice(self, character):
        with self._metadata:
            result = super().remove_voice(character)
            self.router.bank = self.bank
            return result

    def submit(self, action, identity=None):
        if action not in ('download', 'load', 'unload', 'delete'):
            raise ValueError('Unknown model operation')
        if action in ('download', 'delete') or identity is not None:
            choose(identity)
        with self._jobs:
            if self.stopping.is_set():
                raise ValueError('Companion is stopping')
            if self.worker and self.worker.is_alive():
                raise ValueError('A model operation is already running')
            locked = action != 'download'
            if locked and not self.router.lock.acquire(blocking=False):
                raise ValueError('Finish or cancel the current speech/reference operation first')
            self.cancel_download.clear()
            self.job = {'action': action, 'model': identity, 'status': 'running', 'phase': 'starting', 'done': 0, 'total': 0}
            def progress(phase, done, total):
                with self._metadata:
                    self.job.update(phase=phase, done=done, total=total)
            def work():
                try:
                    if action == 'download':
                        download(self.prefix, identity, progress=progress, cancelled=self.cancel_download)
                    elif action == 'load': self.load_model(identity)
                    elif action == 'unload': self.unload_model()
                    else: self.delete_model(identity)
                    with self._metadata: self.job['status'] = 'complete'
                except Exception as error:
                    with self._metadata:
                        self.job.update(status='cancelled' if isinstance(error, InterruptedError) else 'failed', error=str(error))
                    event('model_operation', action=action, status=self.job['status'], error=type(error).__name__)
                finally:
                    if locked: self.router.lock.release()
            self.worker = threading.Thread(target=work, name='breeze-model-operation', daemon=True)
            self.worker.start()
        return {'accepted': True}

    def close(self):
        if hasattr(self, 'stopping'):
            self.stopping.set()
            self.cancel_download.set()
            if self.worker: self.worker.join()
            self.stop_native()
            # Active HTTP workers finish before their reference workspace is removed.
            with self.router.lock:
                super().close()
        else:
            super().close()
