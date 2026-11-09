# Building the Linux preview

Use Python 3.11+, a C++17 compiler, CMake 3.20+, Ninja, nlohmann-json development headers, and Git. The pack targets Home: Equestria `0.3.0-maredev` and Godot 4.5. The original 0.3.0 release uses Godot 4.5; some earlier integration fixtures used 4.5.2.

The matching game source supplies `project.godot`, `tools/modding/build_mod.gd`, `tools/build/packs.gd`, and `world/modding/mod_loader.gd`. Source data is needed for testing a source checkout; packaged tests below use the installed release's existing game/data packs instead.

## Native library

```bash
git clone https://github.com/godotengine/godot-cpp.git vendor/godot-cpp
git -C vendor/godot-cpp checkout e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77
python3 scripts/build_native.py --godot-cpp vendor/godot-cpp
```

The build script rejects a different bindings revision. The supplied model is already in `mods/breeze_tts_pny/native/`; no model download or Python inference environment is needed. Output: `build/native/bin/libtalking_avatar.so`.

The supplied Linux binary was built with no host-specific `-march=native` setting. Godot's bindings link the C++ runtime statically. Diagnostic source paths are remapped to repository-relative labels. Its remaining system dependencies require glibc 2.38 or newer, as determined from ELF version requirements. Building on an older glibc baseline is a future portability step, followed by validation on that baseline. This preview does not support musl Linux.

## Pack

```bash
python3 scripts/build.py \
  --game-source /path/to/matching/game-source \
  --engine /path/to/matching/game/HomeEquestria.x86_64 \
  --native-library build/native/bin/libtalking_avatar.so
```

The script checks game/engine versions, stages a minimal project under `build/pack/`, and calls the unmodified official mod builder. It copies the engine into an isolated directory so adjacent game or development packs cannot change the build. The selected native library is embedded as raw bytes; the runtime extracts and loads it on first use. None of these steps changes the supplied game/source tree or the player's mods folder.

The output filename follows the version in `mods/breeze_tts_pny/mod.json`, currently `dist/breeze_tts_pny-0.1.1-linux-x86_64.pck`. Keep `dist/SHA256SUMS` and the `.build.json` receipt with release artifacts. The receipt records packed source hashes, binary hash, model hash and official builder hash; it does not include private configuration or absolute build paths. Builds are not claimed to be byte-for-byte reproducible across compilers or engine versions.

## Checks

```bash
python3 scripts/verify.py --game-release /path/to/matching/game
python3 scripts/world_check.py
python3 scripts/audio_check.py --speech-pcm /path/to/local/speech.s16
python3 scripts/audio_check.py --actor spike --speech-pcm /path/to/local/speech.s16
```

Run `verify.py` first. It prepares a clean isolated release under `build/verify/game`, allowing only the game executable, its two main packs and native `.so` dependencies. Test game processes run from that directory, avoiding loose source files in the caller's working directory. They use separate `XDG_DATA_HOME` folders; personal saves and settings are not read or changed. The transport fixture binds only loopback and uses no external TTS service.

`world_check.py` creates and reloads a disposable world, verifies saved state and the real director's extended TTS client, and rejects a fallback to a fresh game.

`audio_check.py` requires `pactl` and a running PulseAudio-compatible server. It creates a temporary null sink and removes it afterward. Supply 1–4 seconds of voiced mono, signed 16-bit little-endian PCM at 24 kHz. Test audio stays under ignored `build/` and must not be added to the repository. The check uses the actual audio mixer, mouth rig and supplied speech; it is not a TTS latency benchmark.

The default actor is OpenPony. `--actor spike` instantiates Spike's actual exported model, voice, face and animation tree and verifies jaw blend-shape movement, speech lifecycle and scene-exit cleanup. Both actors run the same streaming, interruption, rebuffering and buffered-WAV checks. `verify.py` additionally checks the real director's request/callback handoff to Spike against a local protocol fixture.

Godot release templates strip GDScript `assert`. The checked-in tests use explicit failure branches instead.

## Manual Linux GPU memory capture

`scripts/capture_playtest.py` launches the exported game with XR disabled and an existing isolated profile. Start the local companion separately and wait for its ready event, then run:

```bash
python3 scripts/capture_playtest.py --config build/local-playtest.json
```

The private JSON file supplies absolute paths for `game_directory`, `user_data_home` (the directory above `home-equestria-public`), `mod_pack` and `output_directory`, plus `mod_sha256` and the loopback `companion_url`. `gpu_device` optionally selects an AMD sysfs device when more than one is present. The helper checks the staged mod hash and profile's TTS endpoint before launch.

Recording starts with that command and ends when its game exits, with no pre-launch countdown or F9 requirement. Each run saves game logs, 100 ms whole-card VRAM/GTT/utilization samples, the game exit code, and a receipt checking that samples span gameplay. A sampling failure stops only the game it launched. The companion remains under its original terminal's control. This captures GPU memory; it does not provide a full frame-time trace. The stock export may omit the script needed by its F9 profiler.

## Release artifact audit

Build/package outputs are allowlisted; installed configuration, local endpoints, playtest profiles, logs, captured audio and source checkouts are not release inputs. Keep model/reference assets outside Git and publish only the intended release files.

Before sharing artifacts, run:

```bash
python3 scripts/audit_release.py dist/*.pck dist/*.tar.gz dist/*.zip \
  --report build/release-audit.json
```

This scans bytes and nested archives for personal source paths, temporary build paths, credential patterns and private LAN addresses, and rejects nonportable ELF64 library search paths. Additional private strings can be supplied with `--forbid`. Reports omit matched credential values. The pinned compiler runtime's public upstream CI assertion paths are explicitly recognized. Known path/network constants in the SHA-verified CPython runtime are recognized by exact file hash; modified files lose that exemption. Project/workstation paths are not allowed. This is a heuristic audit, alongside the file/hash receipts and source review.

The native build recipes remap first-party/compiler-binding source labels. Linux runtime libraries resolve beside the executable with `$ORIGIN`; they do not fall back to a private build tree. Re-run native and installed-service checks after rebuilding.
