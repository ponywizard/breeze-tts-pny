#!/usr/bin/env python3
"""CPU-only checks for the Colab notebook: python3 -m unittest discover -s colab -v

The companion's router modules are served from this checkout through a
stand-in opener (which also proves the pinned hashes match the release), and a
stand-in engine answers like Breeze-TTS-2.cpp's patched server (/health,
/v1/voices, POST /v1/audio/speech streaming s16le PCM). These checks don't
build the engine, measure a GPU or open a tunnel; the notebook does that.
"""

import hashlib
import http.client
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import build_notebook
import runtime as r

REPO = Path(__file__).resolve().parents[1]


class LocalResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


def repo_opener(url, timeout=None):
    """Serves PNY_RAW URLs from this checkout, as raw.githubusercontent.com would."""
    if not url.startswith(r.PNY_RAW):
        raise AssertionError("unexpected download " + url)
    return LocalResponse((REPO / url[len(r.PNY_RAW):]).read_bytes())


def make_pack(root: Path) -> Path:
    files = {"voices/aloe.breeze": b"aloe-cache", "voices/twilight.breeze": b"twi-cache", "adapters/twilight.gguf": b"lora"}
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    manifest = {
        "schema": 1, "id": "test-pack", "version": "1", "model_sha256": r.MODEL["sha256"],
        "characters": [
            {"id": "aloe", "name": "Aloe", "route": "breeze", "voice_id": "aloe"},
            {"id": "twilight_sparkle", "name": "Twilight Sparkle", "route": "breeze", "voice_id": "twilight",
             "settings": {"lora": "twilight", "temperature": 0.7}},
        ],
        "voices": {"aloe": {"file": "voices/aloe.breeze", "ref_text": "Hi.", "reference_sha256": "a" * 64},
                   "twilight": {"file": "voices/twilight.breeze", "ref_text": "Hello.", "reference_sha256": "b" * 64}},
        "adapters": {"twilight": "adapters/twilight.gguf"},
        "legacy_speakers": {"31": "twilight_sparkle", "6": "aloe"},
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    (root / "voice-pack.json").write_text(json.dumps(manifest))
    return root


class FakeEngine:
    """Answers like the patched breeze-server; streams PCM in small blocks."""

    def __init__(self):
        self.requests = []
        self.voices = [{"id": "aloe", "ref_text": "Hi.", "metadata": {"reference_sha256": "a" * 64}},
                       {"id": "twilight", "ref_text": "Hello.", "metadata": {"reference_sha256": "b" * 64}}]
        engine = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *_):
                pass

            def do_GET(self):
                payload = {"/health": {"status": "ok"}, "/v1/voices": engine.voices}.get(self.path)
                data = json.dumps(payload).encode()
                self.send_response(200 if payload is not None else 404)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                form = dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode()))
                engine.requests.append(form)
                self.send_response(200)
                self.send_header("X-Sample-Format", "s16le")
                self.send_header("X-Sample-Rate", "24000")
                self.send_header("X-Breeze-Adapter", form.get("lora") or "base")
                self.end_headers()
                for index in range(10):  # 0.5 s of audio in ten blocks
                    self.wfile.write(struct.pack("<h", index + 1) * 1200)
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Running:
    def running(self):
        return True

    def stop(self):
        pass


class ColabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)
        cls.pny = r.fetch_router(cls.work, repo_opener)
        cls.bank_root = make_pack(cls.work / "pack")
        cls.bank = cls.pny.bank.load_bank(cls.bank_root)
        cls.engine = FakeEngine()
        cls.session = r.BreezeSession(cls.work)
        cls.session.engine = Running()
        cls.restore = r.NATIVE_PORT
        r.NATIVE_PORT = cls.engine.port
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free = probe.getsockname()[1]
        cls.session.start_router(cls.pny, cls.bank, prebuffer_ms=650, port=free)
        cls.port = free

    @classmethod
    def tearDownClass(cls):
        cls.session.stop()
        cls.engine.close()
        r.NATIVE_PORT = cls.restore
        sys.path.remove(str(cls.work / "pny"))
        for name in [name for name in sys.modules if name == "breeze_pny" or name.startswith("breeze_pny.")]:
            del sys.modules[name]
        cls.tmp.cleanup()

    def post(self, path, body):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("POST", path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        response = connection.getresponse()
        return connection, response

    def test_pinned_router_files_match_the_release(self):
        for name, digest in r.ROUTER_FILES.items():
            self.assertEqual(hashlib.sha256((REPO / "server/breeze_pny" / name).read_bytes()).hexdigest(), digest, name)
        self.assertEqual(self.pny.__file__, str(self.work / "pny/breeze_pny/__init__.py"))

    def test_health_is_the_companions_plus_prebuffer(self):
        status = r.get_json(f"http://127.0.0.1:{self.port}/health")
        self.assertEqual((status["ready"], status["native_backend"], status["pcm_stream"]), (True, "breeze", "framed-v1"))
        self.assertEqual((status["prebuffer_ms"], status["server"], status["characters"]), (650, "breeze-tts-pny-colab", 2))

    def test_stream_is_framed_with_a_valid_receipt_and_the_pony_adapter(self):
        connection, response = self.post("/tts/stream", {"text": "[happy] Hello there!", "speaker_id": 6, "character_id": "twilight_sparkle"})
        try:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), r.FRAMED)
            pcm = r.read_framed(response)
        finally:
            connection.close()
        self.assertEqual(len(pcm), 24000)
        sent = self.engine.requests[-1]
        self.assertEqual((sent["text"], sent["voice_id"], sent["lora"]), ("Hello there!", "twilight", "twilight"))

    def test_buffered_tts_uses_the_legacy_speaker_without_a_character(self):
        connection, response = self.post("/tts", {"text": "Hi.", "speaker_id": 6})
        try:
            self.assertEqual((response.status, response.getheader("Content-Type")), (200, "audio/wav"))
            with wave.open(io.BytesIO(response.read())) as audio:
                self.assertEqual((audio.getframerate(), audio.getnchannels(), audio.getnframes()), (24000, 1, 12000))
        finally:
            connection.close()
        self.assertEqual((self.engine.requests[-1]["voice_id"], self.engine.requests[-1].get("lora", "")), ("aloe", ""))  # base voice

    def test_unknown_pony_is_refused(self):
        connection, response = self.post("/tts", {"text": "Hi.", "character_id": "nopony"})
        connection.close()
        self.assertEqual(response.status, 400)

    def test_sample_measures_speed(self):
        result = self.session.sample("aloe", "Hello.")
        self.assertAlmostEqual(result["audio_s"], 0.5)
        self.assertGreater(result["speed"], 0)
        with wave.open(str(result["path"])) as audio:
            self.assertEqual(audio.getnframes(), 12000)

    def test_check_voices_rejects_a_changed_reference(self):
        r.check_voices(self.engine.voices, self.bank)
        changed = [dict(self.engine.voices[0], metadata={"reference_sha256": "c" * 64}), self.engine.voices[1]]
        with self.assertRaises(RuntimeError):
            r.check_voices(changed, self.bank)


class StreamFormatTests(unittest.TestCase):
    @staticmethod
    def framed(*frames, total=None, digest=None):
        pcm = b"".join(frames)
        body = b"".join(struct.pack("<I", len(frame)) + frame for frame in frames)
        receipt = struct.pack("<II", 0, len(pcm) if total is None else total) + (digest or hashlib.sha256(pcm).digest())
        return io.BytesIO(body + receipt)

    def test_valid_stream(self):
        self.assertEqual(r.read_framed(self.framed(b"\x01\x00" * 3, b"\x02\x00")), b"\x01\x00" * 3 + b"\x02\x00")

    def test_bad_receipts_and_frames_fail(self):
        for stream in (self.framed(b"\x01\x00", total=4), self.framed(b"\x01\x00", digest=b"\x00" * 32),
                       io.BytesIO(struct.pack("<I", 3) + b"abc"), io.BytesIO(struct.pack("<I", 4) + b"ab"),
                       io.BytesIO(self.framed(b"\x01\x00").read() + b"x")):
            with self.assertRaises(RuntimeError):
                r.read_framed(stream)

    def test_prebuffer(self):
        self.assertEqual(r.prebuffer_for(10, 5), 400)  # twice real time: tunnel margin only
        self.assertEqual(r.prebuffer_for(8, 10), 2000)  # 0.8× real time: 400 + 0.2 × 8 s
        self.assertEqual(r.prebuffer_for(1, 10), r.PREBUFFER_MAX)


class TunnelTests(unittest.TestCase):
    def test_url_survives_later_diagnostics_and_a_failed_first_check(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            fake = work / "cloudflared"  # announces the link, then floods the log
            fake.write_text("#!/bin/sh\necho 'INF |  https://pony-test-link.trycloudflare.com  |'\n"
                            "i=0; while [ $i -lt 200 ]; do echo 'INF diagnostics line padding padding padding'; i=$((i+1)); done\nsleep 30\n")
            fake.chmod(0o755)
            answers = [OSError("not routed yet"), {"pcm_stream": "framed-v1"}]
            asked = []

            def fake_get_json(url, timeout=5):
                asked.append(url)
                answer = answers.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return answer

            original = r.get_json
            r.get_json = fake_get_json
            session = r.BreezeSession(work)
            try:
                self.assertEqual(session.expose(timeout=20), "https://pony-test-link.trycloudflare.com")
            finally:
                r.get_json = original
                session.stop()
            self.assertGreater((work / "tunnel.log").stat().st_size, 4000)
            self.assertEqual(asked, ["https://pony-test-link.trycloudflare.com/health"] * 2)


class NotebookTests(unittest.TestCase):
    def test_notebook_is_current_and_its_code_compiles(self):
        content = json.dumps(build_notebook.notebook(), ensure_ascii=False, indent=1) + "\n"
        self.assertEqual(build_notebook.TARGET.read_text(encoding="utf-8"), content, "run python3 colab/build_notebook.py")
        for cell in build_notebook.notebook()["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), cell["id"], "exec")


if __name__ == "__main__":
    unittest.main()
