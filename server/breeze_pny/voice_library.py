"""A loopback-only browser interface for reference playback and replacement."""
import base64
import binascii
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

from .voice_edit import VoiceEditor

STATIC = Path(__file__).with_name('voice_library')


def create_server(editor, port=0):
    token = secrets.token_urlsafe(32)
    operation = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def send(self, status, raw, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def result(self, data, status=200):
            self.send(status, json.dumps(data).encode(), 'application/json')

        def authorized(self):
            origin = 'http://127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != origin[7:] or self.headers.get('Origin', origin) != origin:
                return False
            supplied = self.headers.get('X-Voice-Library-Token', '')
            return hmac.compare_digest(supplied.encode(), token.encode())

        def do_GET(self):
            route = urlsplit(self.path)
            public = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            try:
                if route.path in public:
                    name, kind = public[route.path]
                    self.send(200, (STATIC / name).read_bytes(), kind)
                    return
                if not self.authorized():
                    self.result({'error': 'Reopen the complete voice library link from the terminal'}, 403)
                    return
                if not operation.acquire(blocking=False):
                    self.result({'error': 'A voice operation is already running'}, 409)
                    return
                try:
                    if route.path == '/api/state':
                        self.result(editor.state())
                    elif route.path == '/api/reference':
                        voice = parse_qs(route.query).get('voice', [''])[0]
                        path = editor.reference(voice)
                        if path is None:
                            self.result({'error': 'This pack has no playable recording for this voice'}, 404)
                        else:
                            self.send(200, path.read_bytes(), 'audio/wav')
                    else:
                        self.result({'error': 'Not found'}, 404)
                finally:
                    operation.release()
            except (OSError, ValueError, KeyError) as error:
                self.result({'error': str(error)}, 400)

        def do_POST(self):
            if not self.authorized():
                self.result({'error': 'Reopen the complete voice library link from the terminal'}, 403)
                return
            if not operation.acquire(blocking=False):
                self.result({'error': 'A voice operation is already running'}, 409)
                return
            try:
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Expected a JSON request')
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 3 * 1024**2:
                    raise ValueError('Request is too large or empty')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Expected an object')
                route = urlsplit(self.path).path
                if route == '/api/prepare':
                    raw = base64.b64decode(body.get('wav', ''), validate=True)
                    self.result(editor.prepare(body.get('character'), body.get('transcript'), raw, body.get('source', '')))
                elif route == '/api/audition':
                    self.send(200, editor.audition(body.get('character'), body.get('text'), body.get('pending_id')), 'audio/wav')
                elif route == '/api/apply':
                    self.result(editor.apply(body.get('pending_id')))
                elif route == '/api/undo':
                    self.result(editor.undo())
                elif route == '/api/close':
                    self.result({'closed': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self.result({'error': 'Not found'}, 404)
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, binascii.Error) as error:
                self.result({'error': str(error)}, 400)
            finally:
                operation.release()

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server, token


def run(config_path, port=0, reference_directory=None, open_browser=True):
    editor = VoiceEditor(config_path, reference_directory)
    try:
        server, token = create_server(editor, port)
        url = f'http://127.0.0.1:{server.server_port}/#{token}'
        print('Voice library: ' + url, flush=True)
        print('Keep this terminal open. Close the library before restarting the companion.', flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=.25)
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        editor.close()
