"""Helpers embedded in the Home: Equestria Breeze Colab notebook.

Builds Breeze-TTS-2.cpp for the Colab GPU (CUDA) with this repository's
adapter patch, downloads the pinned model and curated voice pack, and serves
the game the companion's own router (GET /health, POST /tts and
POST /tts/stream with framed PCM) through a temporary trycloudflare.com link.

The router, voice-pack checks and native reader are the companion's
server/breeze_pny modules, fetched at the release commit and checked against
pinned SHA-256 hashes, so the game sees exactly the protocol of the local
companion. Only /health gains "prebuffer_ms", measured on this GPU.

Everything but setup()/build runs with Python's standard library and is tested
on a PC: python3 -m unittest discover -s colab -v
Regenerate the notebook after editing: python3 colab/build_notebook.py
"""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import wave


# Pinned sources.
ENGINE_URL = "https://github.com/HoppouAI/Breeze-TTS-2.cpp.git"
ENGINE_TAG = "v0.1.6"
ENGINE_REVISION = "87b43667ca5597f826441991e416a279ed7373b9"
PNY_COMMIT = "8b636164ed1600ea4bf80e77d4db556f3cc9b2ed"  # breeze-tts-pny 0.2.1 router source
PNY_RAW = f"https://raw.githubusercontent.com/ponywizard/breeze-tts-pny/{PNY_COMMIT}/"
PATCHES = {
    "breeze-native-lora.patch": "2761bd9fa240d772a0c593ee8a3243b6b201539ac162b801251d650ac79d59d9",
    "breeze-portable-build.patch": "3ee579187b867ad2bccd7a3966fc124378c7b9f3fceea2766a3b191e61ae37de",
}
ROUTER_FILES = {
    "__init__.py": "890b462b4a0d89e31e773b1252d29371b1d4d4a13c9fee1c86697f816f0e5c15",
    "bank.py": "ee745ac1a44085dbbdfee79ae1636f4c3fc84c3cebb72f61ef7cc0c8f9ca3732",
    "events.py": "4279bd5d4fb29ebfa4c946b482da810261f19b4aad1c35ee29d75de8346b0d4c",
    "files.py": "c70f4661c350662374e9603f2c05d8de166361425c13f501ce1759fbf94b232e",
    "native.py": "9bee05c540f8949dd203721fd3eb1deba9cee94c2cae67da4f9e809dd41cb9cd",
    "router.py": "c8b7a6dd4cc56e44087214e96581ad9704f096bc8a95ed329e8ca64f0acadf5c",
}
MODEL = {
    "file": "breeze-tts-2-q8_0.gguf",
    "url": "https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp/resolve/81b22bad9f05b99970e30c5ee5e4bbc52fedf2f8/breeze-tts-2-q8_0.gguf",
    "sha256": "a02bcc4b69b0601032727f8040c4942149b1b73aa0f69022fe5aaa6a8f0ef879",
}
VOICE_PACK = {
    "file": "breeze-pny-curated-voices-20261107.tar.gz",
    "url": "https://github.com/ponywizard/breeze-tts-pny/releases/download/v0.2.0/breeze-pny-curated-voices-20261107.tar.gz",
    "sha256": "be6f6f6a5c4f96166a06cae6916b0f77c29dab4897ded30ffef0b48523720345",
}
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

ROUTER_PORT = 18792
NATIVE_PORT = 18797
SAMPLE_RATE = 24000
FRAMED = "application/vnd.home-equestria.pcm-stream"
SAMPLE = ("twilight_sparkle", "Hello! Welcome to Ponyville. I hope you'll enjoy your stay here, and that we'll be good friends.")
# The game's own limits for "prebuffer_ms" (see docs/PROTOCOL.md).
PREBUFFER_MIN, PREBUFFER_MAX = 200, 4000
TUNNEL_MARGIN_MS = 400  # network jitter through Cloudflare, on top of the GPU's own need
LONG_LINE_S = 8.0  # a long grouped line; the prebuffer covers it on a GPU slower than real time


#region Downloads and the companion's router modules

def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, sha256: str, label: str, opener=urllib.request.urlopen) -> Path:
    """Fetches url to target unless a verified copy is there; checks its SHA-256."""
    if target.exists() and sha256_of(target) == sha256:
        print(f"{label}: already downloaded and verified.", flush=True)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    print(f"Downloading {label}…", flush=True)
    with opener(url, timeout=60) as response, partial.open("wb") as stream:
        total = int(response.headers.get("Content-Length") or 0)
        done, shown = 0, -1
        for block in iter(lambda: response.read(1 << 20), b""):
            stream.write(block)
            done += len(block)
            percent = done * 100 // total if total else -1
            if percent >= 0 and percent // 10 != shown:
                shown = percent // 10
                print(f"  {label}: {percent}%", flush=True)
    actual = sha256_of(partial)
    if actual != sha256:
        partial.unlink()
        raise RuntimeError(f"{label} doesn't match its pinned SHA-256 ({actual}); not used.")
    partial.replace(target)
    return target


def fetch_router(work: Path, opener=urllib.request.urlopen):
    """The companion's breeze_pny package at the release commit, each file hash-checked."""
    package = work / "pny" / "breeze_pny"
    for name, digest in ROUTER_FILES.items():
        download(PNY_RAW + "server/breeze_pny/" + name, package / name, digest, "companion " + name, opener)
    if str(package.parent) not in sys.path:
        sys.path.insert(0, str(package.parent))
    import breeze_pny.bank, breeze_pny.files, breeze_pny.router  # noqa: E401
    return breeze_pny


def open_pack(pny, archive: Path, target: Path) -> dict:
    """Unpacks the voice pack with the companion's own checks, then validates it."""
    if not (target / "voice-pack.json").exists():
        shutil.rmtree(target, ignore_errors=True)
        pny.files.unpack(archive, target)
    bank = pny.bank.load_bank(target)
    if bank["model_sha256"] != MODEL["sha256"]:
        raise RuntimeError("This voice pack needs another Breeze model.")
    return bank

#endregion


#region Building the engine (Colab GPU)

def gpu_info() -> dict:
    try:
        line = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader"], text=True).splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError) as exc:
        raise RuntimeError("No GPU: choose Runtime → Change runtime type → T4 GPU, then Run all again.") from exc
    name, memory, capability = [part.strip() for part in line.split(",")]
    return {"name": name, "memory": memory, "arch": capability.replace(".", "")}


def build_engine(work: Path, arch: str, opener=urllib.request.urlopen) -> Path:
    """breeze-server for this GPU, CUDA, with the adapter patch. Reused on reruns."""
    source, build = work / "engine-src", work / f"engine-build-{arch}"
    built = [path for path in build.rglob("breeze-server") if path.is_file()] if build.exists() else []
    if built:
        print("Breeze engine: already built.", flush=True)
        return built[0]
    nvcc = shutil.which("nvcc") or "/usr/local/cuda/bin/nvcc"
    if not Path(nvcc).exists():
        raise RuntimeError("The CUDA compiler (nvcc) isn't here: use a Colab GPU runtime.")
    if not source.exists():
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", ENGINE_TAG, ENGINE_URL, str(source)], check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if revision != ENGINE_REVISION:
        raise RuntimeError(f"Unexpected Breeze engine revision {revision}.")
    for name, digest in PATCHES.items():
        patch = download(PNY_RAW + "native/breeze/" + name, work / "patches" / name, digest, name, opener)
        applied = subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=source, capture_output=True).returncode == 0
        if not applied:
            subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
    subprocess.run(["git", "submodule", "update", "--init", "--depth", "1", "third_party/ggml"], cwd=source, check=True)
    print(f"Building the Breeze engine for this GPU (CUDA, sm_{arch}). This takes about 10–20 minutes the first time…", flush=True)
    started = time.monotonic()
    environment = {**os.environ, "CUDACXX": nvcc, "PATH": str(Path(nvcc).parent) + os.pathsep + os.environ.get("PATH", "")}
    generator = ["-G", "Ninja"] if shutil.which("ninja") else []
    subprocess.run([
        "cmake", "-S", str(source), "-B", str(build), *generator, "-DCMAKE_BUILD_TYPE=Release",
        "-DBREEZE_VULKAN=OFF", "-DBREEZE_CUDA=ON", "-DBREEZE_MP3=OFF", "-DBREEZE_BUILD_CLI=OFF",
        "-DBREEZE_BUILD_SHARED=OFF", f"-DCMAKE_CUDA_ARCHITECTURES={arch}",
    ], check=True, env=environment, stdout=subprocess.DEVNULL)
    log = work / "build.log"
    with log.open("w") as stream:
        result = subprocess.run(["cmake", "--build", str(build), "--target", "breeze-server", "-j", str(os.cpu_count() or 2)],
                                env=environment, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise RuntimeError("The engine build failed:\n" + log.read_text(errors="replace")[-4000:])
    found = [path for path in build.rglob("breeze-server") if path.is_file()]
    if not found:
        raise RuntimeError(f"The build made no breeze-server. See {log}.")
    print(f"Built in {(time.monotonic() - started) / 60:.1f} minutes.", flush=True)
    return found[0]

#endregion


#region The engine, the router and the stream format

class Process:
    """Owns only the child it starts; logs to a file so no pipe fills up."""

    def __init__(self, command: list[str], log: Path, cwd: Path | None = None):
        self.log = log
        with log.open("w") as stream:
            self.child = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    def tail(self) -> str:
        data = self.log.read_bytes()
        return data[-4000:].decode("utf-8", errors="replace")

    def running(self) -> bool:
        return self.child.poll() is None

    def stop(self) -> None:
        if self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()


def engine_command(binary: Path, model: Path, bank_root: Path, bank: dict, port: int = NATIVE_PORT) -> list[str]:
    """The companion's own native command line (service.py)."""
    command = [str(binary), str(model), "--host", "127.0.0.1", "--port", str(port), "--ws-port", "-1",
               "--parallel", "1", "--voices-dir", str(bank_root / "voices")]
    for name, filename in sorted(bank.get("adapters", {}).items()):
        command += ["--lora", f"{name}={bank_root / filename}"]
    return command


def get_json(url: str, timeout: float = 5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read(4 << 20))


def check_voices(cached: list, bank: dict) -> None:
    """Every pack voice is loaded with its reference, as the companion checks."""
    by_id = {voice.get("id"): voice for voice in cached}
    for voice, expected in bank["voices"].items():
        actual = by_id.get(voice, {})
        if actual.get("metadata", {}).get("reference_sha256") != expected["reference_sha256"] or actual.get("ref_text") != expected["ref_text"]:
            raise RuntimeError(f"The engine's voice {voice} differs from the voice pack.")


def read_framed(stream) -> bytes:
    """A /tts/stream body: length-prefixed PCM frames, then the zero-length receipt.
    Checks it as the game does (even frames up to 64 KiB, byte count and SHA-256)."""
    pcm, digest = bytearray(), hashlib.sha256()

    def exactly(count: int) -> bytes:
        data = b""
        while len(data) < count:
            block = stream.read(count - len(data))
            if not block:
                raise RuntimeError("The speech stream ended early")
            data += block
        return data

    while True:
        size = struct.unpack("<I", exactly(4))[0]
        if size == 0:
            total = struct.unpack("<I", exactly(4))[0]
            if total != len(pcm) or not pcm or exactly(32) != digest.digest():
                raise RuntimeError("The speech stream's receipt doesn't match its audio")
            if stream.read(1):
                raise RuntimeError("Data after the speech stream's receipt")
            return bytes(pcm)
        if size > 65536 or size % 2:
            raise RuntimeError("Invalid speech stream frame")
        frame = exactly(size)
        digest.update(frame)
        pcm += frame


def wav_of(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        stream.writeframes(pcm)
    return out.getvalue()


def prebuffer_for(audio_s: float, generation_s: float) -> int:
    """Audio the game should hold before playing: tunnel jitter, plus what a long
    line needs to finish without underrunning when generation is slower than real time."""
    speed = audio_s / generation_s if generation_s > 0 else 1.0
    need = TUNNEL_MARGIN_MS + max(0.0, 1.0 - speed) * LONG_LINE_S * 1000.0
    return int(min(PREBUFFER_MAX, max(PREBUFFER_MIN, round(need / 50.0) * 50)))


def colab_router(pny, bank: dict, native_port: int, healthy, prebuffer_ms: int = 0):
    """The companion's Router; /health also names this server and its prebuffer."""

    class ColabRouter(pny.router.Router):
        prebuffer = prebuffer_ms

        def health(self):
            status = super().health()
            status["server"] = "breeze-tts-pny-colab"
            if self.prebuffer:
                status["prebuffer_ms"] = self.prebuffer
            return status

    return ColabRouter(bank, native_port, healthy=healthy)

#endregion


#region The session

class BreezeSession:
    """Engine, router and tunnel for one Colab run. stop() ends all three."""

    def __init__(self, work: Path):
        self.work = work
        self.engine: Process | None = None
        self.tunnel: Process | None = None
        self.server = None
        self.router = None
        self.port = ROUTER_PORT
        self.url = ""

    def start_engine(self, binary: Path, model: Path, bank_root: Path, bank: dict, timeout: float = 300) -> None:
        self.stop()
        self.engine = Process(engine_command(binary, model, bank_root, bank), self.work / "engine.log", cwd=self.work)
        started = time.monotonic()
        print("Loading the model on the GPU…", flush=True)
        while time.monotonic() - started < timeout:
            if not self.engine.running():
                raise RuntimeError("The Breeze engine stopped:\n" + self.engine.tail())
            try:
                if get_json(f"http://127.0.0.1:{NATIVE_PORT}/health").get("status") == "ok":
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("The Breeze engine didn't get ready in time:\n" + self.engine.tail())
        check_voices(get_json(f"http://127.0.0.1:{NATIVE_PORT}/v1/voices"), bank)
        print(f"Engine ready with {len(bank['voices'])} voices ({time.monotonic() - started:.0f} s).", flush=True)

    def start_router(self, pny, bank: dict, prebuffer_ms: int = 0, port: int | None = None) -> None:
        engine = self.engine
        self.port = port or ROUTER_PORT
        self.router = colab_router(pny, bank, NATIVE_PORT, lambda: engine is not None and engine.running(), prebuffer_ms)
        self.server = pny.router.Server(("127.0.0.1", self.port), pny.router.handler(self.router))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def sample(self, character: str = SAMPLE[0], text: str = SAMPLE[1]) -> dict:
        """One line through /tts/stream, as the game asks: speed and first-audio delay."""
        body = json.dumps({"text": text, "speaker_id": 31, "character_id": character}).encode()
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=150)
        started = time.monotonic()
        try:
            connection.request("POST", "/tts/stream", body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            if response.status != 200 or response.getheader("Content-Type") != FRAMED:
                raise RuntimeError(f"The router answered {response.status}: {response.read(500)!r}")
            first = [None]
            original = response.read

            def timed(count):
                data = original(count)
                if first[0] is None and data:
                    first[0] = time.monotonic() - started
                return data

            response.read = timed
            pcm = read_framed(response)
        finally:
            connection.close()
        took = time.monotonic() - started
        seconds = len(pcm) / (2 * SAMPLE_RATE)
        path = self.work / "sample.wav"
        path.write_bytes(wav_of(pcm))
        result = {"path": path, "audio_s": seconds, "took_s": took, "first_s": first[0] or took, "speed": seconds / took}
        print(f"Sample: {seconds:.1f} s of speech in {took:.1f} s ({result['speed']:.2f}× real time), "
              f"first audio after {result['first_s']:.2f} s.", flush=True)
        return result

    def expose(self, timeout: float = 90) -> str:
        if platform.machine() not in ("x86_64", "AMD64"):
            raise RuntimeError("The tunnel download expects a Colab x86-64 runtime.")
        binary = self.work / "cloudflared"
        if not binary.exists():
            partial = binary.with_suffix(".download")
            with urllib.request.urlopen(CLOUDFLARED_URL, timeout=120) as response:
                partial.write_bytes(response.read())
            partial.chmod(0o755)
            partial.replace(binary)
        self.tunnel = Process([str(binary), "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"], self.work / "tunnel.log")
        started, found = time.monotonic(), ""
        while time.monotonic() - started < timeout:
            if not self.tunnel.running():
                raise RuntimeError("The tunnel stopped:\n" + self.tunnel.tail())
            if not found:  # read the whole log: later diagnostics push the URL out of tail()
                match = TUNNEL_URL.search(self.tunnel.log.read_text(errors="replace"))
                found = match.group(0) if match else ""
            if found:
                try:
                    if get_json(found + "/health", timeout=5).get("pcm_stream") == "framed-v1":
                        self.url = found
                        return self.url
                except (OSError, ValueError):
                    pass
            time.sleep(1)
        raise RuntimeError(f"The tunnel didn't become reachable. See {self.work / 'tunnel.log'}.")

    def stop(self) -> None:
        for process in (self.tunnel, self.engine):
            if process is not None:
                process.stop()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        self.tunnel = self.engine = self.server = self.router = None
        self.url = ""


def setup(work: Path) -> dict:
    """GPU check, engine build, router modules, model and voices: what start() needs."""
    work.mkdir(parents=True, exist_ok=True)
    gpu = gpu_info()
    print(f"GPU: {gpu['name']} ({gpu['memory']}).", flush=True)
    binary = build_engine(work, gpu["arch"])
    pny = fetch_router(work)
    model = download(MODEL["url"], work / "models" / MODEL["file"], MODEL["sha256"], "Breeze model (3.6 GB)")
    archive = download(VOICE_PACK["url"], work / VOICE_PACK["file"], VOICE_PACK["sha256"], "pony voice pack (112 MB)")
    bank_root = work / "voice-pack"
    bank = open_pack(pny, archive, bank_root)
    print(f"Voice pack {bank['id']}: {len(bank['routes'])} ponies, {len(bank.get('adapters', {}))} adapters.", flush=True)
    return {"binary": binary, "model": model, "pny": pny, "bank": bank, "bank_root": bank_root, "gpu": gpu}


def start(session: BreezeSession, ready: dict, public_link: bool = True, prebuffer_ms: int = 0) -> str:
    """prebuffer_ms 0 measures it from the sample line."""
    session.start_engine(ready["binary"], ready["model"], ready["bank_root"], ready["bank"])
    session.start_router(ready["pny"], ready["bank"])
    measured = session.sample()
    chosen = int(min(PREBUFFER_MAX, max(PREBUFFER_MIN, prebuffer_ms))) if prebuffer_ms else prebuffer_for(measured["audio_s"], measured["took_s"])
    session.router.prebuffer = chosen
    print(f"The game will buffer {chosen} ms of speech before playing it.", flush=True)
    if not public_link:
        print("Voices ready inside the notebook. The game link is off.", flush=True)
        return ""
    url = session.expose()
    print(f"\nBREEZE VOICES READY\n{url}/tts\n\n"
          "In the game: Settings → AI Settings → Voices: \"Character voices via server\", "
          "Voice server \"Local moss-tts\", and paste this link (with its /tts) as the moss-tts URL.", flush=True)
    return url + "/tts"

#endregion
