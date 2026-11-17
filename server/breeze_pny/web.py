"""Loopback management UI; the game API remains on its separate listener."""
import base64
import binascii
import hmac
import ipaddress
import json
from pathlib import Path
import secrets
import signal
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .companion import Companion
from .events import capture_events, event
from .router import Server, handler

STATIC = Path(__file__).with_name('web')


def create_server(companion, port=18793):
    token = secrets.token_urlsafe(32)
    base = handler(companion.router)

    class Handler(base):
        def send(self, code, raw, kind):
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            return (self.headers.get('Host') == origin[7:]
                    and self.headers.get('Origin', origin) == origin
                    and hmac.compare_digest(self.headers.get('X-Breeze-Token', '').encode(), token.encode()))

        def do_GET(self):
            route = urlsplit(self.path)
            public = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            try:
                if route.path in public:
                    name, kind = public[route.path]
                    return self.send(200, (STATIC / name).read_bytes(), kind)
                if not self.authorized():
                    return self.json_reply(403, {'error': 'Reopen the complete Companion link from the terminal'})
                if route.path == '/api/state':
                    return self.json_reply(200, companion.state())
                if route.path == '/api/reference':
                    with companion._metadata:
                        path = companion.reference(parse_qs(route.query).get('voice', [''])[0])
                        if path is None: return self.json_reply(404, {'error': 'No reference recording is included for this voice'})
                        return self.send(200, path.read_bytes(), 'audio/wav')
                self.json_reply(404, {'error': 'Not found'})
            except (OSError, ValueError, KeyError) as error:
                self.json_reply(400, {'error': str(error)})

        def do_POST(self):
            if not self.authorized():
                return self.json_reply(403, {'error': 'Reopen the complete Companion link from the terminal'})
            if companion.stopping.is_set():
                return self.json_reply(503, {'error': 'Companion is stopping'})
            if self.path == '/tts':
                return super().do_POST()
            locked = False
            try:
                if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Expected JSON with Content-Length')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 3 * 1024**2: raise ValueError('Request is too large or empty')
                raw = self.rfile.read(length)
                if len(raw) != length: raise ValueError('Truncated request')
                body = json.loads(raw)
                if not isinstance(body, dict): raise ValueError('Expected an object')
                if self.path == '/api/models':
                    return self.json_reply(202, companion.submit(body.get('action'), body.get('model')))
                if self.path == '/api/download/cancel':
                    companion.cancel_download.set()
                    return self.json_reply(200, {'cancelling': True})
                locked = companion.router.lock.acquire(blocking=False)
                if not locked:
                    return self.json_reply(409, {'error': 'Finish or cancel the current speech/model operation first'})
                if companion.stopping.is_set():
                    return self.json_reply(503, {'error': 'Companion is stopping'})
                if self.path == '/api/prepare':
                    wav = base64.b64decode(body.get('wav', ''), validate=True)
                    result = companion.prepare(body.get('character'), body.get('transcript'), wav, body.get('source', ''))
                elif self.path == '/api/audition':
                    def watch(stream):
                        finished = threading.Event()
                        monitor = threading.Thread(target=self.watch_disconnect, args=(stream, finished), daemon=True)
                        monitor.start()
                        def cleanup():
                            finished.set(); monitor.join(timeout=.5)
                        return cleanup
                    return self.send(200, companion.audition(body.get('character'), body.get('text'), body.get('pending_id'), watch), 'audio/wav')
                elif self.path == '/api/apply': result = companion.apply(body.get('pending_id'))
                elif self.path == '/api/undo': result = companion.undo()
                else: return self.json_reply(404, {'error': 'Not found'})
                self.json_reply(200, result)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True
            except (ValueError, TypeError, KeyError, OSError, RuntimeError, binascii.Error) as error:
                self.json_reply(400, {'error': str(error)})
            finally:
                if locked: companion.router.lock.release()

    server = Server(('127.0.0.1', port), Handler)
    return server, token


def run(config_path, host=None, port=None, native_port=None, web_port=18793, open_browser=True, reference_directory=None):
    companion = Companion(config_path, reference_directory, native_port)
    servers, threads, previous = [], [], {}
    logs = companion.prefix / 'logs'; logs.mkdir(exist_ok=True)
    try:
        api_host = str(ipaddress.IPv4Address(host or companion.config.get('host', '127.0.0.1')))
        api_port = port if port is not None else companion.config['port']
        if not 1024 <= api_port <= 65535 or not 0 <= web_port <= 65535:
            raise ValueError('Invalid API or web port')
        if native_port is not None and not 1024 <= native_port <= 65535:
            raise ValueError('Invalid native port')
        if api_port == companion.native_port or (web_port and web_port in (api_port, companion.native_port)):
            raise ValueError('API, web and native ports must differ')
        api = Server((api_host, api_port), handler(companion.router)); servers.append(api)
        companion.api_port = api.server_port
        web, token = create_server(companion, web_port); servers.append(web)
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start(); threads.append(thread)
        signals = [signal.SIGINT, signal.SIGTERM]
        if hasattr(signal, 'SIGBREAK'): signals.append(signal.SIGBREAK)
        for sig in signals:
            previous[sig] = signal.signal(sig, lambda *_: companion.stopping.set())
        url = f'http://127.0.0.1:{web.server_port}/#{token}'
        print('Breeze Companion: ' + url, flush=True)
        print(f'TTS API: http://{api_host}:{api.server_port}/tts', flush=True)
        print('Keep this terminal open. Ctrl+C stops the companion.', flush=True)
        with capture_events(logs / ('companion-web-' + str(time.time_ns()) + '.jsonl')):
            if companion.config.get('autoload', True): companion.submit('load')
            if open_browser: webbrowser.open(url)
            while not companion.stopping.wait(.25):
                if companion.phase == 'ready' and not companion.healthy():
                    companion.phase, companion.error = 'error', 'The renderer stopped. Load a model again to recover.'
                    event('renderer_stopped')
    finally:
        companion.stopping.set()
        # Stop accepting requests before releasing the renderer and installation lock.
        for server, thread in zip(servers, threads):
            server.shutdown(); server.server_close(); thread.join(timeout=2)
        for server in servers[len(threads):]: server.server_close()
        companion.close()
        for sig, previous_handler in previous.items(): signal.signal(sig, previous_handler)
