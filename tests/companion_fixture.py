"""Temporary Companion installation for browser checks; no model weights or GPU."""
import contextlib
import io
import json
import os
from pathlib import Path
import signal
import struct
import sys
import tempfile
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent / 'server'))
from test_companion import CompanionFixture
from breeze_pny.web import create_server


def stop(*_): raise KeyboardInterrupt
signal.signal(signal.SIGTERM, stop)
with tempfile.TemporaryDirectory(prefix='breeze-companion-browser-') as directory:
    root = Path(directory)
    with contextlib.redirect_stdout(io.StringIO()): fixture = CompanionFixture(root)
    # Give the curated and replacement references distinguishable output audio.
    fixture.native.voice_samples = {'shared': 1500}
    source = {'episode': 'fim_s02e14', 'source_url': 'https://example.org/recording#clip',
              'annotation_url': 'https://example.org/transcript', 'processing': 'Cut to dialogue; mono 24 kHz PCM16.'}
    pack_path = fixture.app.bank_root / 'voice-pack.json'
    pack = json.loads(pack_path.read_text())
    pack['voices']['shared']['source'] = source
    pack_path.write_text(json.dumps(pack))
    fixture.app.bank['voices']['shared']['source'] = source
    recording = root / 'reference café.wav'
    with wave.open(str(recording), 'wb') as wav:
        wav.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
        wav.writeframes(struct.pack('<hh', 2000, 4000) * 48029)
    address = os.environ.get('BREEZE_TEST_WEB_ADDRESS', '127.0.0.1')
    fixture.app.api_host = '0.0.0.0'
    server, token = create_server(fixture.app, 0, '0.0.0.0' if address != '127.0.0.1' else address)
    print(json.dumps({'url': f'http://{address}:{server.server_port}/#{token}', 'recording': str(recording),
                      'compressed': [], 'config': str(root / 'config.json')}), flush=True)
    try: server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt: pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        server.server_close(); fixture.close()
