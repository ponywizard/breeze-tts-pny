# Breeze voices on Google Colab

The experimental [Colab notebook](https://colab.research.google.com/github/ponywizard/breeze-tts-pny/blob/main/colab/Home_Equestria_Breeze_Voices.ipynb) runs the companion's speech service on a free Colab T4 GPU for players without a suitable graphics card. Its [source notebook](https://github.com/ponywizard/breeze-tts-pny/blob/main/colab/Home_Equestria_Breeze_Voices.ipynb) is on GitHub. It gives the game an `https://….trycloudflare.com/tts` link.

A complete T4/CUDA session through the public tunnel still needs validation. The automated checks use a stand-in engine. Game mod 0.1.1 is currently a source build; the published v0.2.0 release includes game mod 0.1.0.

## Use

1. Open the notebook in Colab (**File → Upload notebook**, or open it from GitHub), choose **Runtime → Change runtime type → T4 GPU**, then **Runtime → Run all**.
2. The first run builds Breeze-TTS-2.cpp for the GPU with CUDA (about 10–20 minutes) and downloads the 3.6 GB model and the voice pack. Reruns in the same session reuse them.
3. Copy the link printed under **BREEZE VOICES READY**. In the game: **Settings → AI Settings → Voices**: *Character voices via server*, Voice server *Local moss-tts*, and paste it as the **moss-tts URL**.

Game mod **0.1.1** or later streams from the link with lip-sync; 0.1.0 accepts only `http://` routers. Without the mod (for example on a standalone Quest) the game asks for whole WAV lines by numbered speaker: the 23 mapped characters keep their voices and other ponies share one.

## What runs

- **Engine:** Breeze-TTS-2.cpp `v0.1.6` at the pinned revision, with `native/breeze/breeze-native-lora.patch` and `breeze-portable-build.patch`, built with `-DBREEZE_CUDA=ON` for the GPU's compute capability. Its command line is the companion's (`--parallel 1`, voices directory, one `--lora` per adapter).
- **Router:** the companion's own `server/breeze_pny` modules (`router.py`, `bank.py`, `native.py`, `files.py`, `events.py`), fetched from this repository at the v0.2.0 commit with pinned SHA-256 hashes. The game therefore gets the same `/health`, `/tts` and framed `/tts/stream` as from the local companion, including legacy speaker numbers, receipts and cancellation on disconnect.
- **Checks:** the model, voice pack, patches and router files are verified against pinned hashes; the voice pack is unpacked and validated by the companion's code; the engine's loaded voices must match the pack's references, as `service.py` checks.
- **Prebuffer:** the notebook times one sample line through `/tts/stream` and adds `prebuffer_ms` to `/health`: 400 ms for network jitter, plus what an 8-second line needs when the GPU is slower than real time (at most 4000 ms). The notebook's `PREBUFFER_MS` setting overrides it. See [PROTOCOL.md](PROTOCOL.md).
- **Link:** a Cloudflare quick tunnel (`cloudflared tunnel --url`). The notebook waits until `/health` answers through it before printing the link.

## Privacy and limits

The text of each spoken line and the pony's identity pass through Google's Colab machine and Cloudflare's tunnel. The router logs one JSON line per utterance (pony, seconds, timings), never the text. Anyone with the link can use the session's voices; the link changes on every run. Colab limits free GPU time and may end sessions; this is not dependable hosting. Model, voice and adapter terms are in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Development

```bash
python3 -m unittest discover -s colab -v   # router, stream format, prebuffer, notebook freshness
python3 colab/build_notebook.py            # regenerate the notebook after editing colab/runtime.py
```

The tests serve the router modules from this checkout (which also proves the pinned hashes) and use a stand-in engine; they do not build the engine, use a GPU or open a tunnel.
