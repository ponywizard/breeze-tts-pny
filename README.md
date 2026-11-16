# Breeze TTS PNY

Breeze character voices and Talking Avatar lip-sync for **Home: Equestria 0.3.1.2-maredev (Godot 4.5)** on Linux and Windows x86_64. Speech starts while it is being generated, with mouth movement following playback.

The release has two parts: a game mod and a companion that generates speech. The curated voice pack contains 139 reference voices and six Mane Six LoRA adapters: Applejack, Fluttershy, Pinkie Pie, Rainbow Dash, Rarity and Twilight Sparkle. The companion provides TTS; keep using your normal LLM and speech-to-text setup.

## Source update: companion 0.2.2

The current source adds the reviewed `(gasp)` and `(giggles)` synthesis substitutions and makes the tested slow-trained Pinkie setup the default in the new `curated-ponies-20261115` voice pack. Pinkie uses a LoRA trained on 0.8× audio, a matching 0.8× reference, and 1.25× playback. Other voices keep their existing settings. Both WAV and streaming playback use the same conversion, with no additional Python packages.

These are locally prepared updates; the published downloads below remain the previous releases. The new voice pack requires companion **0.2.2 or later**. See [the update notes](docs/VOICE_UPDATES.md) for validation, compatibility and upgrade details. Game mod 0.1.3 is unchanged.

## Downloads

Download **game mod 0.1.3** from the [current mod release](https://github.com/ponywizard/breeze-tts-pny/releases/tag/mod-v0.1.3):

| Platform | Game mod |
| --- | --- |
| Windows | `breeze_tts_pny-0.1.3-windows-x86_64.pck` |
| Linux | `breeze_tts_pny-0.1.3-linux-x86_64.pck` |

Existing companion users only need to replace the game `.pck` and restart. This update uses the game’s built-in streaming/lip-sync, fixes stock Ponese defaults across the Breeze roster and keeps the routing fix active when Watch Party preloads the conversation director. Companion **0.2.1**, reference voices and adapters are unchanged.

For a new installation, also download the companion and voice archive from [companion release 0.2.1](https://github.com/ponywizard/breeze-tts-pny/releases/tag/v0.2.1):

| Platform | Companion files |
| --- | --- |
| Windows | `breeze-tts-pny-0.2.1-windows-x86_64.zip` and `breeze-pny-curated-voices-20261107.tar.gz` |
| Linux | `breeze-tts-pny-server-0.2.1-linux-x86_64.tar.gz` and `breeze-pny-curated-voices-20261107.tar.gz` |

The Windows ZIP includes Python and the companion runtime, plus an older 0.1.1 game mod for game 0.3.0. Use the separate **0.1.3** `.pck` above for game 0.3.1.2. The Linux companion uses your installed Python 3.11+.

Optional: [Reference Management Utility and Recordings v0.1.0](https://github.com/ponywizard/breeze-tts-pny/releases/tag/reference-manager-v0.1.0) is a separate prerelease for existing companion installations. Its single ZIP includes a local browser wizard and all 139 original reference recordings. Browse and play references, trim a replacement, compare generated speech, and save or undo changes. It reuses the installed model/runtime; no FFmpeg or additional Python packages are needed. See the [voice library guide](docs/VOICE_LIBRARY.md) for setup and validation limits.

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
2. **Start speech generation.** On Windows, run `start-companion.cmd`. On Linux, use the `breeze-pny serve` command printed by setup. Wait for the `ready` event and leave that terminal open while playing.
3. **Install the game mod.** In the game, open **Settings → Mods → Open mods folder**. Copy in the downloaded 0.1.3 `.pck` for your platform. The published companion ZIP’s `game-mod` folder contains the older 0.1.1 pack. Replace the older Breeze pack so only one copy remains, then restart the game.
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

For support, include your OS, GPU/driver, game/mod/companion versions, display mode and steps to reproduce. Companion logs are saved in its `logs` directory; include the matching `companion-*.jsonl` and `native-*.log`, plus the game's log when relevant. Review logs before posting: game logs can contain conversations and diagnostic logs can contain local file paths. Nothing is uploaded automatically.

## Disable or remove

Disable the mod in **Settings → Mods**, or remove its `.pck`, then restart the game. No save migration is required. Stop the companion with Ctrl+C; remove its installation folder to uninstall it. Caches from older mod versions under `user://mods/data/breeze_tts_pny/` can be removed while the game is closed; 0.1.3 uses the game’s own native libraries.

## Development and licenses

Builds and checks: [Linux](docs/BUILD.md) · [Windows cross-build](docs/WINDOWS-BUILD.md). Technical details: [architecture](docs/ARCHITECTURE.md) · [protocol](docs/PROTOCOL.md) · [voice packs](docs/VOICE_PACKS.md).

Original code is MIT licensed. Talking Avatar is by InterviewFlowAI. Breeze model weights, reference voices and adapters have separate terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
