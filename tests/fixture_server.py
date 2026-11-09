"""Deterministic protocol fixtures; no voice model, personal data, or external calls."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
import struct
import time
import wave

PCM = b''.join(struct.pack('<h', int(math.sin(i * 2 * math.pi * 220 / 24000) * 12000)) for i in range(24000))
buffer = io.BytesIO()
with wave.open(buffer, 'wb') as wav:
    wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
    wav.writeframes(PCM)
WAV = buffer.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.health_requests.append(self.path)
        data = {'ready': True}
        if self.path == '/warming/health':
            self.server.warming_probes += 1
            data.update(pcm_stream='framed-v1', native_backend='breeze')
            if self.server.warming_probes == 1:
                raw = json.dumps({**data, 'ready': False}).encode()
                self.send_response(503)
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
                return
        elif self.path == '/health':
            data.update(pcm_stream='framed-v1', native_backend='breeze')
        elif self.path == '/prebuffer/health':
            data.update(pcm_stream='framed-v1', native_backend='breeze', prebuffer_ms=1000)
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append({'path': self.path, 'character_id': body.get('character_id')})
        identity = body.get('character_id')
        try:
            if self.path == '/legacy/tts' or identity == 'wav_fixture':
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', str(len(WAV)))
                self.end_headers()
                self.wfile.write(WAV)
                return
            if self.path not in {'/tts/stream', '/warming/tts/stream', '/prebuffer/tts/stream'} or identity not in {'stream_fixture', 'corrupt_fixture', 'cancel_fixture', 'spike', 'lily_valley'}:
                self.send_error(400)
                return
            frames = [struct.pack('<I', len(PCM[i:i+3840])) + PCM[i:i+3840] for i in range(0, len(PCM), 3840)]
            digest = hashlib.sha256(PCM).digest() if identity != 'corrupt_fixture' else bytes(32)
            frames.append(struct.pack('<II', 0, len(PCM)) + digest)
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.home-equestria.pcm-stream')
            self.send_header('Content-Length', str(sum(map(len, frames))))
            for key, value in [('X-Sample-Format', 's16le'), ('X-Sample-Rate', '24000'), ('X-Channels', '1')]:
                self.send_header(key, value)
            self.end_headers()
            for frame in frames:
                self.wfile.write(frame); self.wfile.flush()
                time.sleep(.04)
        except (BrokenPipeError, ConnectionResetError):
            pass


def create():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.requests = []
    server.health_requests = []
    server.warming_probes = 0
    return server
