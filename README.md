# Breeze TTS PNY

Breeze character voices and Talking Avatar lip-sync for **Home: Equestria 0.3.0-maredev (Godot 4.5)** on Linux and Windows x86_64. Speech starts while it is being generated, with mouth movement following playback.

The release has two parts: a game mod and a companion that generates speech. The curated voice pack contains 139 reference voices and six Mane Six LoRA adapters: Applejack, Fluttershy, Pinkie Pie, Rainbow Dash, Rarity and Twilight Sparkle. The companion provides TTS; keep using your normal LLM and speech-to-text setup.

## Downloads

Download the files for your operating system from the same [companion release](https://github.com/ponywizard/breeze-tts-pny/releases/tag/v0.2.1):

| Platform | Files to download |
| --- | --- |
| Windows | `breeze-tts-pny-0.2.1-windows-x86_64.zip` and `breeze-pny-curated-voices-20261107.tar.gz` |
| Linux | `breeze_tts_pny-0.1.1-linux-x86_64.pck`, `breeze-tts-pny-server-0.2.1-linux-x86_64.tar.gz` and `breeze-pny-curated-voices-20261107.tar.gz` |

The Windows ZIP includes the game mod, companion, native runtime and Python. The Linux companion archive includes its native runtime and uses your installed Python 3.11+. Game mod **0.1.1** and companion **0.2.1** are the matching versions in this release.

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
3. **Install the game mod.** In the game, open **Settings → Mods → Open mods folder**. Copy in the `.pck` for your platform: Windows includes it in the ZIP's `game-mod` folder; Linux provides it as a separate download. Replace the older Breeze pack so only one copy remains, then restart the game.
4. **Connect TTS.** Select the game's MOSS-compatible TTS provider, enable speech and automatic voices, and set the URL to **`http://127.0.0.1:18792/tts`**. Start the companion before loading a world. Your LLM/STT settings stay separate.
5. **Check a conversation.** Talk to a pony and check speech and mouth movement. Configure the settings in flatscreen first if that is easier before entering VR.

The MOSS label is the game's existing HTTP provider setting; the companion generates speech with Breeze.

Detailed instructions, offline installation, updates and troubleshooting: [Windows](docs/WINDOWS.md) · [Linux](docs/SERVER.md). To run the companion on a different computer, see [network setup](docs/SERVER.md#another-machine).

No suitable GPU? The experimental [Colab notebook](docs/COLAB.md) runs the same speech service on a free Colab GPU and gives an `https://` link (game mod 0.1.1 or later). A complete Colab session still needs validation.

A fresh game folder uses the game's usual saves. The optional Windows `prepare-playtest.cmd` helper creates a **separate disposable playtest profile**; it is not required for normal installation. See [isolated testing](docs/WINDOWS.md#optional-isolated-playtest).

## Compatibility and support

Use the supported game version and one copy of this mod. Remove earlier development PCM/playback/optimization packs before installing. Compatibility with other mods that replace speech or character scripts has not been established. Global Ponese and disabled-TTS settings still take precedence.

| Setup | Manual coverage |
| --- | --- |
| Linux flatscreen | Tested |
| Linux PCVR with WiVRn | Tested |
| Windows flatscreen | Tested |
| Windows PCVR | Untested; shipping with this limitation |

Windows PCVR issues will be investigated case by case. The native playtests used an RX 6700 XT; other GPUs and driver combinations have less coverage. [Validation notes](docs/VALIDATION.md) describe the automated checks and observed limitations.

For support, include your OS, GPU/driver, game/mod/companion versions, display mode and steps to reproduce. Companion logs are saved in its `logs` directory; include the matching `companion-*.jsonl` and `native-*.log`, plus the game's log when relevant. Review logs before posting: game logs can contain conversations and diagnostic logs can contain local file paths. Nothing is uploaded automatically.

## Disable or remove

Disable the mod in **Settings → Mods**, or remove its `.pck`, then restart the game. No save migration is required. Stop the companion with Ctrl+C; remove its installation folder to uninstall it. Cached mod libraries under `user://mods/data/breeze_tts_pny/` can be removed while the game is closed.

## Development and licenses

Builds and checks: [Linux](docs/BUILD.md) · [Windows cross-build](docs/WINDOWS-BUILD.md). Technical details: [architecture](docs/ARCHITECTURE.md) · [protocol](docs/PROTOCOL.md) · [voice packs](docs/VOICE_PACKS.md).

Original code is MIT licensed. Talking Avatar is by InterviewFlowAI. Breeze model weights, reference voices and adapters have separate terms; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
