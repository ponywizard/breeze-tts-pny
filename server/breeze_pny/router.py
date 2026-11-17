"""Game-facing HTTP endpoint; no dialogue text or generated audio is logged."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import select
import socket
import struct
import threading
import time
import wave
from . import __version__
from .bank import resolve
from .native import NativePCM, BusyError, CONTENT_TYPE
from .events import event


class Router:
    def __init__(self, bank, port, healthy=lambda: True):
        self.bank, self.port, self.healthy = bank, port, healthy
        self.lock = threading.Lock()

    def health(self):
        return {'ready': bool(self.healthy()), 'native_backend': 'breeze', 'pcm_stream': 'framed-v1',
                'server': 'breeze-tts-pny', 'version': __version__, 'voice_pack': self.bank['id'],
                'characters': len(self.bank['routes']),
                'fallback': False, 'routes': {'breeze': len(self.bank['routes'])}}


def handler(router):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, *_): pass

        def json_reply(self, code, value):
            raw = json.dumps(value).encode()
            try:
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers(); self.wfile.write(raw)
            except OSError: pass

        def do_GET(self):
            if self.path != '/health': return self.json_reply(404, {'error': 'not found'})
            status = router.health()
            self.json_reply(200 if status['ready'] else 503, status)

        def watch_disconnect(self, stream, finished):
            while not finished.wait(.05):
                try:
                    ready, _, _ = select.select([self.connection], [], [], 0)
                    if ready and not self.connection.recv(1, socket.MSG_PEEK):
                        stream.cancel(); return
                except OSError:
                    stream.cancel(); return

        def do_POST(self):
            if self.path not in ('/tts', '/tts/stream'): return self.json_reply(404, {'error': 'not found'})
            sent, locked = False, False
            monitor, finished = None, threading.Event()
            started = time.monotonic()
            try:
                if self.headers.get('Transfer-Encoding'): raise ValueError('Supply Content-Length')
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 32768: raise ValueError('Expected a small JSON request')
                raw = self.rfile.read(length)
                if len(raw) != length: raise ValueError('Truncated request')
                locked = router.lock.acquire(blocking=False)
                if not locked: raise BusyError('Voice renderer is busy')
                row, text = resolve(router.bank, json.loads(raw))
                if not router.healthy(): return self.json_reply(503, {'error': 'Breeze is unavailable'})
                stream = NativePCM(router.port, row, text)
                monitor = threading.Thread(target=self.watch_disconnect, args=(stream, finished), daemon=True)
                monitor.start()
                with stream:
                    if self.path == '/tts/stream':
                        self.protocol_version = 'HTTP/1.1'; self.close_connection = True
                        self.send_response(200)
                        for key, value in [('Content-Type', CONTENT_TYPE), ('Transfer-Encoding', 'chunked'),
                                           ('Connection', 'close'), ('Cache-Control', 'no-store'),
                                           ('X-Sample-Rate', '24000'), ('X-Sample-Format', 's16le'),
                                           ('X-Channels', '1'), ('X-TTS-Backend', 'breeze'),
                                           ('X-Breeze-Adapter', stream.adapter)]: self.send_header(key, value)
                        self.end_headers(); sent = True
                        for pcm in stream.chunks(): self.chunk(struct.pack('<I', len(pcm)) + pcm)
                        self.chunk(stream.receipt()); self.wfile.write(b'0\r\n\r\n'); self.wfile.flush()
                        event('speech', character=row['id'], backend='breeze', transport='framed-v1',
                              seconds=stream.bytes / 48000, first_pcm_s=stream.first_pcm_s,
                              processing_s=time.monotonic() - started, adapter=stream.adapter)
                        return
                    pcm = b''.join(stream.chunks())
                    output = io.BytesIO()
                    with wave.open(output, 'wb') as wav:
                        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); wav.writeframes(pcm)
                    audio = output.getvalue()
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav'); self.send_header('Content-Length', str(len(audio)))
                self.send_header('X-TTS-Backend', 'breeze'); self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Breeze-Adapter', stream.adapter)
                self.end_headers(); sent = True; self.wfile.write(audio)
                event('speech', character=row['id'], backend=row['route'], transport='wav', processing_s=time.monotonic() - started)
            except BusyError as error:
                if not sent: self.json_reply(503, {'error': str(error)})
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                if not sent: self.json_reply(400, {'error': 'Invalid request or voice data'})
                else: event('speech_error', error=type(error).__name__)
                self.close_connection = True
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True
                event('speech_cancelled')
            except Exception as error:
                self.close_connection = True
                event('speech_error', error=type(error).__name__)
                if not sent: self.json_reply(502, {'error': 'Voice backend unavailable'})
            finally:
                finished.set()
                if monitor: monitor.join(timeout=.5)
                if locked: router.lock.release()

        def chunk(self, raw):
            self.wfile.write(f'{len(raw):X}\r\n'.encode() + raw + b'\r\n'); self.wfile.flush()
    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
