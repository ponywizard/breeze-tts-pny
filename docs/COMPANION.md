# Breeze Companion 0.3.3

Breeze Companion is a local browser interface for speech generation, personal voice references and model management. It works without Home: Equestria. A single native renderer supplies the browser and the game-compatible HTTP API, so the model is loaded only once.

## Start

Install the companion and `breeze-pny-curated-voices-20261115.tar.gz` using the [Linux setup](SERVER.md#install) or [Windows setup](WINDOWS.md#install-the-companion). Windows includes Python; Linux needs Python 3.11+. The native runtime and existing GPU/system requirements still apply.

- Windows: run `setup.cmd`, then `breeze-companion.cmd`.
- Linux: run the installed `bin/breeze-pny serve --web` launcher.
- Source: `PYTHONPATH=server python3 -m breeze_pny serve --config /path/to/config.json --web`.

The launcher opens a browser and prints the complete session link. Keep the terminal open. The UI uses loopback port **18793** by default and the TTS API uses **18792**. Use `--web-port 19093` for another UI port (`0` chooses an available port), or `--no-browser` to print the link without opening it. `--port` and `--native-port` continue to control the API and native renderer. All three ports must differ.

One process owns an installation. Stop a previously running API-only companion or standalone voice-library utility before starting the UI. Ctrl+C stops the service and its renderer. Closing the browser tab leaves the service running.

If startup exits with **Address already in use**, another service or SSH tunnel may own the API or web port. Use `serve --web --port 18794` to try another API port, or `--web-port 19093` for another web port. The UI opens only after both listeners start; use the complete session link the launcher prints. On Linux, `ss -ltnp '( sport = :18792 or sport = :18793 or sport = :18797 )'` identifies listeners on the default ports.

The browser listener defaults to `127.0.0.1`, validates Host/Origin and requires its per-session token for API operations. `--host` controls only the game API, which has no authentication or TLS. All browser assets are bundled; no frontend packages or CDNs are required.

## LAN hosting

On Windows, open PowerShell in the extracted companion folder and run:

```powershell
.\breeze-companion.cmd --web-host 0.0.0.0 --no-browser
```

On Linux, use `breeze-pny serve --web --web-host 0.0.0.0 --no-browser`. The new `--web-host` flag accepts an IPv4 address; `0.0.0.0` listens on all IPv4 interfaces. To limit it to one interface, supply that computer's LAN IPv4 address instead of `0.0.0.0`. Without this flag, the UI remains local. Companion 0.3.1 and earlier do not have this flag.

On the other computer, open the complete printed link with the server's LAN IP, port and `#token`: `http://<server-LAN-IP>:18793/#<token>`. With `0.0.0.0`, the launcher prints a local link and any addresses it discovers. If no suitable LAN link appears, find the server's IPv4 address with `ipconfig` on Windows and replace only `127.0.0.1` in the local link. Use a numeric IPv4 address, not the computer name. The token changes when Companion restarts.

Allow inbound TCP **18793** (or your `--web-port`) through the server's firewall for your private LAN. This grants holders of the session link access to Generate, Voices and Models, including model deletion. Use it only on a trusted network; the web connection is HTTP. Do not forward this port from the internet.

To also connect the game from another computer, add `--host 0.0.0.0`, allow TCP **18792**, and set the game's TTS URL to `http://<server-LAN-IP>:18792/tts`. Browser generation needs only the web port. The native renderer stays on loopback. These flags apply to that launch; for repeated Windows use, add them to a shortcut to `breeze-companion.cmd`.

## Add a custom voice

In **Voices**, select **Add voice**, enter a name, and keep or edit the suggested voice ID. Import a clean recording with one speaker, select 0.25–30 seconds, and enter its exact transcript. Load a model in **Models** first, then select **Generate voice preview**, listen, and **Save voice**.

The new name appears immediately in **Generate** and **Voices**. API clients use its displayed ID as `character_id`. Added voices use the base model without a pony LoRA adapter; adding one does not create a new character in the game. Existing character replacements still retain that character's adapter and playback settings.

New voices and their reference audio survive restarts and compatible companion/voice-pack updates. **Undo last change** restores the previous voice-pack snapshot. The original curated pack is kept. If a future curated pack introduces the same ID as an added voice, the update stops instead of overwriting it.

**Removing a specific voice:** select an added custom voice in **Voices**, choose **Remove voice**, then confirm. It disappears immediately from Voices, Generate and API routing, while later additions and reference edits stay intact. Removal also works with the model unloaded and persists across restarts and updates. **Undo last change** restores the removed voice. Stock characters, including ones with replacement references, cannot be removed. Saved pack snapshots and audio are retained for undo; this does not permanently erase recordings or reclaim their disk space. Companion 0.3.2 has only Undo, which restores whole pack snapshots in reverse order.

## Generate

Search the installed voices, select one, enter up to 600 characters, and select **Generate**. The result plays automatically when generation finishes; use the player to pause or replay it, or use **Download WAV**. Starting another generation pauses the previous clip. If your browser blocks automatic playback, press Play in the player. **Cancel** disconnects the request and cancels its native synthesis. Output is mono, 24 kHz, signed 16-bit WAV.

Generation uses the same route, adapter, cue substitutions and playback correction as the game API. Pinkie’s slow-trained profile is automatically corrected to 1.25× playback. Use `(gasp)` and `(giggles)` directly, or the reviewed textual substitutions described in [VOICE_UPDATES.md](VOICE_UPDATES.md).

**Randomize each generation** is on by default. Each generation chooses a new **Seed** and shows it beside the finished result. Uncheck the box to reuse the displayed seed, or type a seed to turn randomization off automatically. Seeds are whole numbers from 0 to 2147483647; the browser remembers your seed and checkbox setting. Reusing a seed helps repeat a take with the same text, voice reference, model and settings. The native GPU renderer can still produce small waveform differences, so a fixed seed does not guarantee byte-identical audio. Companion 0.3.0 used a fixed seed of 42; API requests without a seed still use 42.

**Delivery direction**, directly below the speech text box, is an optional instruction of up to 600 characters. Try “Speak softly, with a sad, hesitant tone” or “Speak sharply, with restrained anger.” This steers the existing reference voice using Breeze's [voice-direction support](https://github.com/HoppouAI/Breeze-TTS-2.cpp/blob/87b43667ca5597f826441991e416a279ed7373b9/README.md#cli). The companion adds your direction to any curated accent/identity instruction and sends it separately from the spoken text. Blank restores the voice's usual settings; the result records the direction used. Hold the seed fixed when comparing directions. Results vary by voice and model, including the trained pony adapters.

Use the direction field for emotions such as angry or sad, and the spoken-text box for supported vocal events such as `(gasp)` and `(giggles)`. A short cue hint appears below the text box. The companion does not select an angry/sad reference automatically: each character uses one selected recording, which can be replaced in **Voices**. An emotion-based reference pool would require additional labeled recordings and routing. Seed and direction controls were added in companion 0.3.1.

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

<a id="upgrade-from-030"></a>

## Upgrade from 0.3.0–0.3.2

Stop the running companion before updating. The game mod, native runtime, models and `breeze-pny-curated-voices-20261115.tar.gz` are unchanged; reuse your existing voice archive.

- **Linux:** extract the 0.3.3 archive, place the voice archive inside or beside it, and run `python3 installer/install.py --prefix /path/to/existing/installation --update` from the extracted folder.
- **Windows:** copy the contents of the extracted 0.3.3 package into your existing package folder (the one containing `setup.cmd` and `companion/`), keeping the `companion/` directory. Place the voice archive inside or beside that folder, then run `setup.cmd --update`.

Setup preserves the selected model, ports and personal references and reuses verified assets. Restart using the installed launcher, retaining any port overrides such as `--port 18794`, and open its new session link. The page header should show **0.3.3**; refreshing an old running process does not load the updated Python server.

## Upgrade from 0.2.1

Stop the companion, extract the new archive, supply the new voice archive, and run `setup.cmd --update` on Windows or `installer/install.py --prefix /path/to/installation --update` on Linux. The installer preserves the selected catalog model, host/ports and automatic-loading preference. Existing 0.2.1 installations select Q8. Compatible personal references are reapplied to the new curated pack. Verified model files are reused.

Pinkie’s new playback profile differs from the older pack. A personal Pinkie reference saved with the old profile needs to be registered and auditioned against the new profile. The installer refuses that incompatible migration before replacing the active configuration; it does not silently retime or discard the personal reference. Retain the old pack/WAV, restore a compatible curated pack selection, update, and then import that reference in Voices.

A different initial model can be selected with installer `--model f16`, `--model q4_k`, etc. `--model-file` supplies a matching local file for an offline install. The selected model's pinned checksum must match. The game mod remains independently versioned at 0.1.3.
