"""Bounded native PCM reader shared by streaming and buffered WAV requests."""
import hashlib
import http.client
import socket
import struct
import threading
import time
from urllib.parse import urlencode
from .speech import breeze_text
from .playback import Playback125

MAX_PCM = 24000 * 2 * 60
CONTENT_TYPE = 'application/vnd.home-equestria.pcm-stream'


class BusyError(Exception): pass


class NativePCM:
    def __init__(self, port, row, text):
        self.port, self.row, self.text = port, row, text
        self.socket = None
        self.connection = None
        self.cancelled = threading.Event()
        self.bytes = 0
        self.native_bytes = 0
        self.digest = hashlib.sha256()
        self.adapter = None
        self.first_pcm_s = None
        self.completed = False

    def cancel(self):
        self.cancelled.set()
        if self.socket:
            try: self.socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass

    def __enter__(self):
        self.started = time.monotonic()
        self.connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=30)
        try:
            self.connection.connect()
            self.socket = self.connection.sock
            if self.cancelled.is_set(): raise ConnectionAbortedError('Cancelled')
            params = {'text': breeze_text(self.text), 'voice_id': self.row['voice_id'], 'seed': 42,
                      'split_chars': 0, 'max_new_tokens': 750, **self.row['settings']}
            self.connection.request('POST', '/v1/audio/speech', urlencode(params),
                                    {'Content-Type': 'application/x-www-form-urlencoded'})
            self.response = self.connection.getresponse()
            if self.response.status in (409, 503): raise BusyError('Breeze is finishing another request')
            if self.response.status != 200: raise RuntimeError('Native synthesis failed')
            if self.response.getheader('X-Sample-Format') != 's16le' or self.response.getheader('X-Sample-Rate') != '24000':
                raise RuntimeError('Unexpected native audio format')
            self.adapter = self.response.getheader('X-Breeze-Adapter')
            if self.adapter != (params.get('lora') or 'base'):
                raise RuntimeError('Native adapter selection was not acknowledged')
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def chunks(self):
        carry = b''
        converter = Playback125() if self.row.get('output_speed', 1) == 1.25 else None

        def playback(raw):
            self.bytes += len(raw)
            if self.bytes > MAX_PCM: raise RuntimeError('Playback audio exceeds 60 seconds')
            if self.first_pcm_s is None: self.first_pcm_s = time.monotonic() - self.started
            self.digest.update(raw)
            return raw

        while True:
            if self.cancelled.is_set(): raise ConnectionAbortedError('Cancelled')
            if time.monotonic() - self.started > 120: raise TimeoutError('Speech generation timed out')
            try:
                raw = self.response.read1(4096)
            except (OSError, http.client.HTTPException):
                if self.cancelled.is_set():
                    raise ConnectionAbortedError('Cancelled') from None
                raise
            if not raw: break
            carry += raw
            size = len(carry) & ~1
            if not size: continue
            raw, carry = carry[:size], carry[size:]
            self.native_bytes += len(raw)
            if self.native_bytes > MAX_PCM: raise RuntimeError('Native audio exceeds 60 seconds')
            converted = converter.process(raw) if converter else raw
            if converted:
                yield playback(converted)
        declared = self.response.getheader('Content-Length')
        if self.cancelled.is_set(): raise ConnectionAbortedError('Cancelled')
        if carry or not self.native_bytes or (declared is not None and int(declared) != self.native_bytes):
            raise RuntimeError('Truncated or invalid native PCM')
        if converter:
            tail = converter.process(b'', final=True)
            if tail:
                yield playback(tail)
        if self.cancelled.is_set(): raise ConnectionAbortedError('Cancelled')
        self.completed = True

    def receipt(self):
        if not self.completed: raise RuntimeError('Cannot acknowledge incomplete speech')
        return struct.pack('<II', 0, self.bytes) + self.digest.digest()

    def __exit__(self, *_):
        if self.connection: self.connection.close()
        if self.socket: self.socket.close()
