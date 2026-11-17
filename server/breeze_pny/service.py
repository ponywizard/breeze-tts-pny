"""Own one native process and the game router; configuration stays out of game saves."""
import ctypes.util
import errno
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import threading
import time
from .bank import load_bank
from .files import OPENER, read_json, relative, sha, verify_files
from .router import Router, Server, event, handler
from .platforms import acquire_lock, platform_id, runtime_environment
from .events import capture_events


def get(url, timeout=3):
    with OPENER.open(url, timeout=timeout) as response:
        return json.loads(response.read(4 * 1024**2))


def check_port(host, port, name, wait_seconds=0, stopping=None):
    deadline = time.monotonic() + wait_seconds
    announced = False
    while True:
        if stopping is not None and stopping.is_set():
            raise InterruptedError('Companion is stopping')
        # Windows SO_REUSEADDR can bind over a live listener. Check it before
        # the reusable bind probe; never claim an existing service is free.
        if os.name == 'nt':
            with socket.socket() as connection:
                connection.settimeout(.25)
                if connection.connect_ex((host, port)) == 0:
                    raise ValueError(f'{name} port {host}:{port} is unavailable: a service is listening')
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind((host, port))
            return
        except OSError as error:
            if (error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) in (10013, 10048)) and time.monotonic() < deadline:
                with socket.socket() as connection:
                    connection.settimeout(.25)
                    # No listener: a previous non-reusable native socket may
                    # still be in TIME_WAIT. Do not wait on a live service.
                    if connection.connect_ex((host, port)) in (errno.ECONNREFUSED, 10061):
                        if not announced:
                            event('waiting_for_port', port_kind=name, host=host, port=port)
                            announced = True
                        time.sleep(.25)
                        continue
            raise ValueError(f'{name} port {host}:{port} is unavailable: {error}') from error


def inspect(config_path, dependencies=True, *, config=None, model_required=True):
    config_path = Path(config_path).resolve()
    config = read_json(config_path) if config is None else dict(config)
    if config.get('schema') != 1: raise ValueError('Unsupported server configuration')
    target = platform_id()
    root = config_path.parent
    for key in ('port', 'native_port'):
        if type(config.get(key)) is not int or not 1024 <= config[key] <= 65535: raise ValueError('Invalid ' + key)
    if config['port'] == config['native_port']: raise ValueError('Router/native ports must differ')
    if ipaddress.ip_address(config.get('host', '127.0.0.1')).version != 4: raise ValueError('Use an IPv4 bind address')
    runtime_root = relative(root, config['runtime'])
    runtime = read_json(runtime_root / 'runtime.json')
    if runtime.get('schema') != 1 or runtime.get('platform') != target or not runtime.get('adapter_selection'):
        raise ValueError('Expected the ' + target + ' runtime with per-request adapter acknowledgement')
    verify_files(runtime_root, runtime['files'])
    if runtime['entrypoint'] not in runtime['files']: raise ValueError('Unverified runtime executable')
    binary = relative(runtime_root, runtime['entrypoint'])
    if not os.access(binary, os.X_OK): raise ValueError('Runtime executable is not executable')
    if dependencies:
        probe = subprocess.run([str(binary), '--help'], capture_output=True, text=True, timeout=15,
                               env=runtime_environment(binary))
        if probe.returncode or '--lora' not in probe.stdout + probe.stderr:
            raise ValueError('Native runtime cannot start on this system: ' + (probe.stderr or probe.stdout)[-2000:])
    model = relative(root, config['model'])
    if model_required and sha(model) != config['model_sha256']: raise ValueError('Breeze model hash mismatch')
    bank_root = relative(root, config['voice_pack'])
    bank = load_bank(bank_root)
    from .models import compatible
    if not compatible(bank['model_sha256'], config['model_sha256']):
        raise ValueError('Voice pack requires a different base model')
    if dependencies and not ctypes.util.find_library('vulkan-1' if os.name == 'nt' else 'vulkan'):
        raise ValueError('Install the Vulkan loader and GPU driver')
    return config, root, runtime, binary, model, bank_root, bank


def serve(config_path, host=None, port=None, native_port=None):
    logs = Path(config_path).resolve().parent / 'logs'
    logs.mkdir(exist_ok=True)
    run = time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()) + '-' + str(time.time_ns() % 1_000_000_000)
    with capture_events(logs / ('companion-' + run + '.jsonl')):
        try:
            return _serve(config_path, host, port, native_port, run)
        except Exception as error:
            event('service_error', error=type(error).__name__, message=str(error))
            raise


def _serve(config_path, host, port, native_port, run):
    owner = (Path(config_path).resolve().parent / 'service.lock').open('a+b')
    try: acquire_lock(owner)
    except BlockingIOError: raise ValueError('This companion installation is already running or being updated')
    config, root, runtime, binary, model, bank_root, bank = inspect(config_path)
    if host is not None: config['host'] = str(ipaddress.IPv4Address(host))
    for key, value in [('port', port), ('native_port', native_port)]:
        if value is not None:
            if not 1024 <= value <= 65535: raise ValueError('Invalid port override')
            config[key] = value
    if config['port'] == config['native_port']: raise ValueError('Ports must differ')
    check_port('127.0.0.1', config['native_port'], 'Native Breeze', wait_seconds=75)
    ready, stopping = threading.Event(), threading.Event()
    child = None
    router = Router(bank, config['native_port'], healthy=lambda: ready.is_set() and child is not None and child.poll() is None)
    try:
        server = Server((config.get('host', '127.0.0.1'), config['port']), handler(router))
    except OSError as error:
        raise ValueError(f"Router port {config.get('host', '127.0.0.1')}:{config['port']} is unavailable: {error}") from error
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    signals = [signal.SIGINT, signal.SIGTERM]
    if os.name == 'nt': signals.append(signal.SIGBREAK)
    previous = {sig: signal.getsignal(sig) for sig in signals}
    for sig in previous: signal.signal(sig, lambda *_: stopping.set())
    logs = root / 'logs'; logs.mkdir(exist_ok=True)
    log_path = logs / ('native-' + run + '.log')
    try:
        command = [str(binary), str(model), '--host', '127.0.0.1', '--port', str(config['native_port']),
                   '--ws-port', '-1', '--parallel', '1', '--voices-dir', str(bank_root / 'voices')]
        for adapter, filename in bank.get('adapters', {}).items():
            command += ['--lora', adapter + '=' + str(relative(bank_root, filename))]
        environment = runtime_environment(binary)
        with log_path.open('x') as log:
            child = subprocess.Popen(command, cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT)
        event('loading', native_log=str(log_path), native_pid=child.pid)
        deadline = time.monotonic() + 240
        url = 'http://127.0.0.1:' + str(config['native_port'])
        while not stopping.is_set():
            if child.poll() is not None: raise RuntimeError(f'Breeze exited ({child.returncode}); inspect {log_path}')
            try:
                if get(url + '/health').get('status') == 'ok': break
            except (OSError, ValueError): pass
            if time.monotonic() > deadline: raise TimeoutError('Breeze startup timed out')
            stopping.wait(.25)
        if stopping.is_set(): return
        cached = {v['id']: v for v in get(url + '/v1/voices')}
        for voice, expected in bank['voices'].items():
            actual = cached.get(voice, {})
            if actual.get('metadata', {}).get('reference_sha256') != expected['reference_sha256'] or actual.get('ref_text') != expected['ref_text']:
                raise ValueError('Native voice cache differs from pack: ' + voice)
        # Native adapter IDs are also acknowledged on every speech response.
        if stopping.is_set(): return
        ready.set()
        event('ready', **router.health(), tts_url=f"http://{config.get('host', '127.0.0.1')}:{config['port']}/tts")
        while not stopping.wait(.25):
            if child.poll() is not None: raise RuntimeError('Native Breeze exited; inspect ' + str(log_path))
    finally:
        ready.clear()
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=10)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
        server.shutdown(); server.server_close(); thread.join(timeout=2)
        for sig, previous_handler in previous.items(): signal.signal(sig, previous_handler)
        event('stopped', native_exit_code=child.returncode if child else None)
