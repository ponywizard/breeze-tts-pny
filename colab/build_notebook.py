#!/usr/bin/env python3
"""Build the self-contained Breeze Colab notebook. No repo checkout is needed in Colab."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "Home_Equestria_Breeze_Voices.ipynb"


def cell(kind, identifier, source, **metadata):
    result = {"cell_type": kind, "id": identifier, "metadata": {"id": identifier, **metadata}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def notebook():
    return {
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"name": TARGET.name, "provenance": [], "gpuType": "T4"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            cell("markdown", "welcome", """# Home: Equestria — Breeze pony voices on Colab

Runs [Breeze TTS 2](https://huggingface.co/BreezeBlue/Breeze-TTS-2) with the 139 pony voices of Breeze TTS PNY (the Mane Six with their own adapters) on a Colab GPU, for players without a suitable graphics card. The game talks to it exactly as to the PC companion.

**Experimental:** the automated checks use a stand-in engine; a complete T4/CUDA session through the public tunnel still needs validation. HTTPS streaming needs game mod 0.1.1, included in release v0.2.1.

1. Choose **Runtime → Change runtime type → T4 GPU**.
2. Choose **Runtime → Run all**. The first run builds the voice engine for this GPU (about 10–20 minutes) and downloads the model (3.6 GB) and the voices (112 MB). Keep this tab open.
3. When **BREEZE VOICES READY** appears, copy its link (it ends in `/tts`).
4. In the game: **Settings → AI Settings → Voices**: *Character voices via server*, Voice server *Local moss-tts*, and paste the link as the **moss-tts URL**.

With the **Breeze TTS PNY** game mod (0.1.1 or later; 0.1.0 only accepts `http://` links) speech streams as it is made, with lip-sync, and every pony gets her own voice. Without the mod the game still plays whole lines, but only 23 main characters have their own voice; the other ponies share one.

Listen to the sample below the start cell to check the voice. Each Colab run gives a new link: paste the new one in the game.

The engine is [Breeze-TTS-2.cpp](https://github.com/HoppouAI/Breeze-TTS-2.cpp) at a pinned revision with Breeze TTS PNY's adapter patch; the game-facing server is the companion's own router code at the v0.2.0 release commit. The model, voices, patches and router files are checked against pinned SHA-256 hashes before use. The Breeze TTS 2 weights are under the BreezeBlue Research and Non-Commercial License, and the voices come from the show: for personal, non-commercial use.

The link lets anyone who has it use this session's voices, and the lines the game speaks pass through Google's and Cloudflare's servers; don't share it. Colab sessions are temporary and Google limits free GPU time, so this isn't dependable hosting. See [Colab's FAQ](https://research.google.com/colaboratory/faq.html).
"""),
            cell("code", "options", '''# @title 1. Settings
CREATE_GAME_LINK = True # @param {type:"boolean"}
# @markdown Speech the game holds before playing a line, in milliseconds. 0 measures it on this GPU; raise it if voices stutter.
PREBUFFER_MS = 0 # @param {type:"integer"}
''', cellView="form"),
            cell("code", "helpers", "# @title 2. Load the notebook helpers\n" + (ROOT / "runtime.py").read_text(encoding="utf-8"), cellView="form"),
            cell("code", "start", '''# @title 3. Build, download and start
# Rerunning stops only what this notebook started, then starts again.
if "breeze_session" in globals():
    breeze_session.stop()
work = Path("/content/he-breeze")
breeze_ready = setup(work)
breeze_session = BreezeSession(work)
game_url = start(breeze_session, breeze_ready, public_link=CREATE_GAME_LINK, prebuffer_ms=PREBUFFER_MS)

from IPython.display import Audio, display
display(Audio(filename=str(work / "sample.wav")))
''', cellView="form"),
            cell("markdown", "help", """## If something goes wrong

- **No GPU:** choose a GPU runtime, then Run all again.
- **The build fails:** the end of its log is shown; the whole log is `/content/he-breeze/build.log`. Reruns in the same session reuse what's built and downloaded.
- **The engine stops while loading:** see `/content/he-breeze/engine.log`.
- **No link:** see `/content/he-breeze/tunnel.log`, or turn off Create game link to try the voices inside the notebook only.
- **The game stays on whole lines, without lip-sync:** check the mod is 0.1.1 or later and the URL ends in `/tts`. The game checks the link when it is set and again on a later line, so a link pasted before the notebook was ready is picked up within about 30 seconds of speech.
- **Voices stutter:** set PREBUFFER_MS higher (for example 2000) and run cell 3 again; the link changes, so paste it again.
- **The game says the server is busy:** Breeze makes one line at a time; the game waits its turn.

The notebook prints one line per spoken line (pony, seconds of audio, time to first audio); it never logs what was said.
"""),
            cell("code", "stop", '''# @title 4. Stop the voices when finished
STOP_NOW = False # @param {type:"boolean"}
if STOP_NOW and "breeze_session" in globals():
    breeze_session.stop()
    print("Breeze and its link stopped.")
''', cellView="form"),
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the checked-in notebook needs regeneration.")
    args = parser.parse_args()
    content = json.dumps(notebook(), ensure_ascii=False, indent=1) + "\n"
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            raise SystemExit("Notebook is stale: run python3 colab/build_notebook.py")
        print("Notebook matches its source.")
    else:
        TARGET.write_text(content, encoding="utf-8")
        print(TARGET)
