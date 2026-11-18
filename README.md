# Breeze TTS PNY

Breeze character voices and Talking Avatar lip-sync for **Home: Equestria 0.3.1.2-maredev (Godot 4.5)** on Linux and Windows x86_64. Speech starts while it is being generated, with mouth movement following playback.

The release has two parts: a game mod and a companion that generates speech. The curated voice pack contains 139 reference voices and six Mane Six LoRA adapters: Applejack, Fluttershy, Pinkie Pie, Rainbow Dash, Rarity and Twilight Sparkle. The companion provides TTS; keep using your normal LLM and speech-to-text setup.

## Breeze Companion 0.3.3

**Breeze Companion 0.3.3** provides a local browser interface with **Generate**, **Voices**, and **Models** tabs. Generate speech and download WAVs without the game, edit references, and download/load/unload/delete verified F16, Q8, Q6, Q4 and experimental depth-decoder variants. The browser and game API share one native renderer. The interface uses only bundled HTML/CSS/JavaScript and Python's standard library.

Version **0.3.3** adds **Remove voice** for any selected added custom voice. Other voices and reference edits stay intact, and **Undo last change** can restore the removal. Removal works with the model unloaded and persists across restarts and compatible updates. Saved pack snapshots and audio remain available for undo.

The **LAN browser hosting** and **Voices → Add voice** features from 0.3.2 remain available. On Windows, run `.\breeze-companion.cmd --web-host 0.0.0.0 --no-browser`; see [LAN hosting](docs/COMPANION.md#lan-hosting) for links and firewall setup. Localhost remains the default.

The seed and **Delivery direction** controls from 0.3.1 remain available. Both speech API endpoints accept optional `seed` and `direction`; existing game requests retain their defaults.

This release also includes the reviewed `(gasp)` / `(giggles)` substitutions and the slow-trained Pinkie LoRA in `curated-ponies-20261115`: a matching 0.8× reference with 1.25× output playback. The voice pack includes all 139 playable reference recordings. Game mod **0.1.3** remains compatible.

After setup, run **`breeze-companion.cmd`** on Windows, or **`breeze-pny serve --web`** using the installed Linux launcher. The UI opens on `http://127.0.0.1:18793` using the complete session link printed by the launcher; the game API remains on port 18792. [Companion guide](docs/COMPANION.md) · [voice update details](docs/VOICE_UPDATES.md).

## Downloads

Download the companion for your platform and the shared voice archive from [Breeze Companion 0.3.3](https://github.com/ponywizard/breeze-tts-pny/releases/tag/v0.3.3):

| Platform | Companion files |
| --- | --- |
| Windows | `breeze-tts-pny-0.3.3-windows-x86_64.zip` and `breeze-pny-curated-voices-20261115.tar.gz` |
| Linux | `breeze-tts-pny-server-0.3.3-linux-x86_64.tar.gz` and `breeze-pny-curated-voices-20261115.tar.gz` |

The Windows ZIP includes Python, the native runtime and game mod **0.1.3**. Linux includes the native runtime and uses your installed Python 3.11+. Both platforms use the same voice archive. `SHA256SUMS` and the build receipts identify the release files.

For Home: Equestria, also install **game mod 0.1.3**, available in the same release and the [mod release](https://github.com/ponywizard/breeze-tts-pny/releases/tag/mod-v0.1.3):

| Platform | Game mod |
| --- | --- |
| Windows | `breeze_tts_pny-0.1.3-windows-x86_64.pck` |
| Linux | `breeze_tts_pny-0.1.3-linux-x86_64.pck` |

The mod remains independently versioned at 0.1.3; existing 0.1.3 users keep their game pack. It uses the game's built-in streaming/lip-sync and includes the stock-Ponese and Watch Party routing fixes. Updating from companion 0.2.1 requires the new companion and voice archive; follow [the upgrade instructions](docs/COMPANION.md#upgrade-from-021) to preserve the selected model, ports and compatible personal references.

Updating from **companion 0.3.0–0.3.2** reuses the same voice archive, runtime and models. Stop the companion, run the new setup with `--update`, then restart it; see [the upgrade instructions](docs/COMPANION.md#upgrade-from-030).

Reference management and all 139 playable reference recordings are included in 0.3.0. The older [standalone Reference Management Utility](https://github.com/ponywizard/breeze-tts-pny/releases/tag/reference-manager-v0.1.0) remains available for older installations; it is not required for Breeze Companion.

You need an AVX2-capable x86_64 CPU and a working Vulkan GPU driver. Setup downloads a pinned model of about 3.6 GB; allow at least 6 GB of free space for the companion and its assets. Linux binaries require glibc 2.38+ and `GLIBCXX_3.4.32`. macOS and standalone Quest builds are not included.

## GPU memory

Measured on a **Radeon RX 6700 XT (12 GB, 11.98 GiB usable)** on Linux, with LLM/STT running on another machine.

**Current six-adapter pack, flatscreen (November 9):** the game and local Q8 Breeze peaked at **10.26 GiB total VRAM**, with **1.73 GiB minimum free** during active speech.

Earlier **PCVR with WiVRn** measurements:

| Setup | Sampled total VRAM peak | Minimum free VRAM |
| --- | --- | --- |
| Game, speech generated on another machine | 7.03 GiB | 4.96 GiB |
| Game + local Q8 Breeze loaded, speech still remote | 10.85 GiB | 1.14 GiB |
| Game + local Q8 Breeze generating speech | 10.97 GiB | 1.01 GiB |

These are whole-card measurements, including the desktop and VR runtime where used. The differences between the PCVR rows suggest budgeting **roughly 4 GiB beyond the game's own usage, plus spare capacity**, as a starting estimate for Q8 speech. Other local models, scenes and graphics settings also need room; rendering and speech share GPU compute time as well.

The November 5 PCVR captures used an earlier runtime with **one resident Rainbow LoRA**. The current-pack flatscreen result is a different workload, so the difference between those figures does not measure adapter overhead. [Measurement details and limits](docs/VALIDATION.md#gpu-memory-measurements) describe the test setup.

## Install

1. **Set up the companion.** Extract the companion archive, then place the downloaded voice-pack archive inside its extracted folder. Leave the voice pack compressed. On Windows, run `setup.cmd`; on Linux, follow [the Linux setup commands](docs/SERVER.md#install). Setup verifies the runtime, voices, adapters and model. Windows needs no separate Python installation.
2. **Start speech generation.** On Windows, run `breeze-companion.cmd`. On Linux, add `--web` to the installed `breeze-pny serve` command printed by setup. Wait for the model to be ready and leave the terminal open. API-only use remains available through `start-companion.cmd` or `breeze-pny serve`.
3. **Install the game mod, if using Home: Equestria.** In the game, open **Settings → Mods → Open mods folder**. Copy in the 0.1.3 `.pck` for your platform, available separately or in the Windows ZIP's `game-mod` folder. Replace the older Breeze pack so only one copy remains, then restart the game.
4. **Connect TTS.** Select the game's MOSS-compatible TTS provider, enable speech and automatic voices, and set the URL to **`http://127.0.0.1:18792/tts`**. Start the companion before loading a world. Your LLM/STT settings stay separate.
5. **Check a conversation.** Talk to a pony and check speech and mouth movement. Configure the settings in flatscreen first if that is easier before entering VR.

The MOSS label is the game's existing HTTP provider setting; the companion generates speech with Breeze.

Detailed instructions, offline installation, updates and troubleshooting: [Windows](docs/WINDOWS.md) · [Linux](docs/SERVER.md). To run the companion on a different computer, see [network setup](docs/SERVER.md#another-machine).

No suitable GPU? The experimental [Colab notebook](docs/COLAB.md) runs the same speech service on a free Colab GPU and gives an `https://` link (game mod 0.1.3 on the current game). A complete Colab session still needs validation.

A fresh game folder uses the game's usual saves. The optional Windows `prepare-playtest.cmd` helper creates a **separate disposable playtest profile**; it is not required for normal installation. See [isolated testing](docs/WINDOWS.md#optional-isolated-playtest).

## Compatibility and support

Use the supported game version and one copy of this mod. Remove earlier development PCM/playback/optimization packs before installing. Compatibility with other mods that replace speech or character scripts has not been established. Global Ponese and disabled-TTS settings still take precedence. Version 0.1.3 has automated coverage against the official Linux 0.3.1.2 build. Earlier manual observations and GPU measurements apply to 0.1.1 on game 0.3.0.

| Current update | Coverage |
| --- | --- |
| Linux release checks | Passed, including all 23 forced-Ponese profiles on WAV and PCM |
| Linux interactive flatscreen / PCVR | Earlier 0.1.1 tested; no new manual pass on this update |
| Windows flatscreen / PCVR | Released for user playtesting; not personally playtested on this update |

Windows reports will be investigated case by case. Earlier native playtests used an RX 6700 XT; other GPUs and driver combinations have less coverage. [Validation notes](docs/VALIDATION.md) distinguish current automated results from earlier manual observations.

Companion 0.3.3 passes the 85-test Python suite on Linux and under embedded Windows Python/Wine (five expected Windows skips), plus Chromium removal/confirmation/cancellation/reload/undo and existing workflow checks. Earlier releases established all-model Linux Vulkan, real Q4 seed/direction and LAN browser coverage. Native Windows browser/firewall/GPU testing is left to community reports. There is no new in-game or VR playtest claim for this companion update. See [companion validation](docs/SERVER_VALIDATION.md).

For support, include your OS, GPU/driver, game/mod/companion versions, display mode and steps to reproduce. Companion logs are saved in its `logs` directory; include the matching `companion-*.jsonl` and `native-*.log`, plus the game's log when relevant. Review logs before posting: game logs can contain conversations and diagnostic logs can contain local file paths. Nothing is uploaded automatically.

## Disable or remove

Disable the mod in **Settings → Mods**, or remove its `.pck`, then restart the game. No save migration is required. Stop the companion with Ctrl+C; remove its installation folder to uninstall it. Caches from older mod versions under `user://mods/data/breeze_tts_pny/` can be removed while the game is closed; 0.1.3 uses the game’s own native libraries.

## Development and licenses

Builds and checks: [Linux](docs/BUILD.md) · [Windows cross-build](docs/WINDOWS-BUILD.md). Technical details: [architecture](docs/ARCHITECTURE.md) · [protocol](docs/PROTOCOL.md) · [voice packs](docs/VOICE_PACKS.md).

Original code is MIT licensed. Talking Avatar is by InterviewFlowAI. Breeze model weights, reference voices and adapters have separate terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
