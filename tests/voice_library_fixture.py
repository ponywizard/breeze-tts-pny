"""Disposable browser-test installation with a real HTTP native-engine fixture."""
import json
from pathlib import Path
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / 'server'))
from test_voice_library import FakeNative, VoiceEditor, WAV, create_server, fixture, read_json, sha, write_json
from http.server import ThreadingHTTPServer


def interrupted(*_):
    raise KeyboardInterrupt


signal.signal(signal.SIGTERM, interrupted)
with tempfile.TemporaryDirectory(prefix='voice-library-browser-') as directory:
    root = Path(directory)
    pack = fixture(root)
    (pack / 'reference.wav').write_bytes(WAV)
    bank = read_json(pack / 'voice-pack.json')
    bank['voices']['shared']['reference_file'] = 'reference.wav'
    bank['files']['reference.wav'] = sha(pack / 'reference.wav')
    write_json(pack / 'voice-pack.json', bank)
    recording = root / 'reference café.wav'
    with wave.open(str(recording), 'wb') as wav:
        wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        wav.writeframes(struct.pack('<hh', 2000, 4000) * 48029)
    compressed = []
    if shutil.which('ffmpeg'):
        for suffix in ('.flac', '.mp3'):
            target = root / ('recording' + suffix)
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(recording), str(target)], check=True)
            compressed.append(str(target))
    editor = VoiceEditor(root / 'config.json')
    native = ThreadingHTTPServer(('127.0.0.1', 0), FakeNative)
    native.voices = editor.workspace / 'voices'
    thread = threading.Thread(target=native.serve_forever, daemon=True); thread.start()
    editor.native_port = native.server_port
    server, token = create_server(editor)
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}/#{token}',
                      'recording': str(recording), 'compressed': compressed, 'config': str(root / 'config.json')}), flush=True)
    try:
        with patch.object(editor, 'start_native'):
            server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        server.server_close()
        native.shutdown(); native.server_close(); thread.join()
        editor.close()
