# Breeze Companion 0.3.0

Breeze Companion is a local browser interface for speech generation, personal voice references and model management. It works without Home: Equestria. A single native renderer supplies the browser and the game-compatible HTTP API, so the model is loaded only once.

## Start

Install the companion and `breeze-pny-curated-voices-20261115.tar.gz` using the [Linux setup](SERVER.md#install) or [Windows setup](WINDOWS.md#install-the-companion). Windows includes Python; Linux needs Python 3.11+. The native runtime and existing GPU/system requirements still apply.

- Windows: run `setup.cmd`, then `breeze-companion.cmd`.
- Linux: run the installed `bin/breeze-pny serve --web` launcher.
- Source: `PYTHONPATH=server python3 -m breeze_pny serve --config /path/to/config.json --web`.

The launcher opens a browser and prints the complete session link. Keep the terminal open. The UI uses loopback port **18793** by default and the TTS API uses **18792**. Use `--web-port 19093` for another UI port (`0` chooses an available port), or `--no-browser` to print the link without opening it. `--port` and `--native-port` continue to control the API and native renderer. All three ports must differ.

One process owns an installation. Stop a previously running API-only companion or standalone voice-library utility before starting the UI. Ctrl+C stops the service and its renderer. Closing the browser tab leaves the service running.

If startup exits with **Address already in use**, another service or SSH tunnel may own the API or web port. Use `serve --web --port 18794` to try another API port, or `--web-port 19093` for another web port. The UI opens only after both listeners start; use the complete session link the launcher prints. On Linux, `ss -ltnp '( sport = :18792 or sport = :18793 or sport = :18797 )'` identifies listeners on the default ports.

The browser listener always binds to `127.0.0.1`, validates Host/Origin and requires its per-session token for API operations. `--host` controls only the existing game API; it does not expose model downloads or file deletion over the LAN. The game API still has no authentication or TLS. For another machine, use the existing documented SSH forwarding setup. All browser assets are bundled; no frontend packages or CDNs are required.

## Generate

Search the installed voices, select one, enter up to 600 characters, and select **Generate**. The result plays automatically when generation finishes; use the player to pause or replay it, or use **Download WAV**. Starting another generation pauses the previous clip. If your browser blocks automatic playback, press Play in the player. **Cancel** disconnects the request and cancels its native synthesis. Output is mono, 24 kHz, signed 16-bit WAV.

Generation uses the same route, adapter, cue substitutions and playback correction as the game API. Pinkie’s slow-trained profile is automatically corrected to 1.25× playback. Use `(gasp)` and `(giggles)` directly, or the reviewed textual substitutions described in [VOICE_UPDATES.md](VOICE_UPDATES.md).

Open **Reference source** to see the selected voice's episode or source label, recording and annotation links when supplied, notes, and audio processing history. The same information appears beside the current reference in **Voices**. These details come from the installed pack or your saved reference notes; missing credits or links are not filled in automatically.

One request can use the renderer at a time. A simultaneous game/browser request receives a busy response. Model changes and reference edits also reserve this slot; finish or cancel speech before changing them. Downloads may run while speech is generated. The first version returns a complete WAV to the browser; the API retains both `/tts` and `/tts/stream`.

## Models

The catalog pins the seven upstream GGUF files at revision `81b22bad9f05b99970e30c5ee5e4bbc52fedf2f8`. Downloads have a known byte limit and SHA-256; partial or incorrect files cannot become installed models.

| Model | Download size (decimal GB) | Use |
| --- | ---: | --- |
| Q8 (`q8_0`) | 3.57 | Default balance |
| Q4 (`q4_k`) | 2.54 | Smallest standard variant |
| Q6 (`q6_k`) | 3.07 | Intermediate size |
| F16 (`f16`) | 6.28 | Full-precision reference |
| Q8 DD4 (`q8_0-dd4`) | 3.40 | Experimental |
| Q8 DD2 (`q8_0-dd2`) | 3.32 | Experimental |
| Q4 DD2 (`q4_k-dd2`) | 2.46 | Experimental |

These are disk sizes, not total GPU memory. Allow for inference buffers, all six adapters and other applications. Upstream describes Q8 as its recommended model and reports that experimental depth-decoder variants may improve speed but drift toward muffled output after roughly 45 seconds. See the [model card](https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp) and [pinned file metadata](https://huggingface.co/api/models/HoppouAI/Breeze-TTS-2.cpp/tree/81b22bad9f05b99970e30c5ee5e4bbc52fedf2f8). Do not assume F16 improves every voice or that the smallest experimental file is the best low-memory choice.

**Download** shows progress and supports cancellation. It does not switch the model. Interrupted downloads restart from the beginning on retry; there is no resume support. A stalled network operation may take up to its network timeout to respond to cancellation. Checksum verification finishes before activation.

**Load** verifies the selected file and runtime, unloads the previous renderer, loads the new model with the pack's adapters, and checks all voice caches. It activates the new configuration only after successful loading. If loading fails, the companion attempts to reload the previously running model and reports any recovery failure. The UI stays available throughout. The API reports unavailable while loading; API consumers should retry once ready.

**Unload** stops the renderer and releases its GPU allocation while keeping the browser and API listener open. It also disables automatic loading for the next UI launch. Loading a model re-enables automatic loading and remembers that model. API-only `serve` always attempts to load the selected model.

**Delete** removes only the chosen catalog model's managed download, after a browser confirmation. Loaded models must be unloaded first. Personal references and voice packs are retained. Deleting the selected unloaded model leaves automatic loading disabled; you can download it again or load another installed model.

Compatibility is an explicit list of these pinned quantizations of the same base and codec. Each still has its own verified hash. Arbitrary GGUF models are not accepted by the manager. Reference encodings and LoRA tensor shapes are compatible within this family; quantization can change the resulting sound. Runtime validation and listening coverage are documented in [SERVER_VALIDATION.md](SERVER_VALIDATION.md).

## Voices

The Voices tab contains the Reference Manager: search characters, play original recordings, import/trim audio, enter the exact transcript, audition, save and undo. Follow [VOICE_LIBRARY.md](VOICE_LIBRARY.md) for recording limits and personal pack behavior.

Saved voices immediately apply to both Generate and the game API. The curated archive includes all original WAVs, and personal packs retain replacement WAVs. Loading another model discards an unsaved prepared replacement; prepare and audition it again before saving. Unchanged reference caches can be reused within the pinned model family.

## Upgrade from 0.2.1

Stop the companion, extract the new archive, supply the new voice archive, and run `setup.cmd --update` on Windows or `installer/install.py --prefix /path/to/installation --update` on Linux. The installer preserves the selected catalog model, host/ports and automatic-loading preference. Existing 0.2.1 installations select Q8. Compatible personal references are reapplied to the new curated pack. Verified model files are reused.

Pinkie’s new playback profile differs from the older pack. A personal Pinkie reference saved with the old profile needs to be registered and auditioned against the new profile. The installer refuses that incompatible migration before replacing the active configuration; it does not silently retime or discard the personal reference. Retain the old pack/WAV, restore a compatible curated pack selection, update, and then import that reference in Voices.

A different initial model can be selected with installer `--model f16`, `--model q4_k`, etc. `--model-file` supplies a matching local file for an offline install. The selected model's pinned checksum must match. The game mod remains independently versioned at 0.1.3.
