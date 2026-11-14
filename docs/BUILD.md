# Building the current game mod

Game mod **0.1.2** targets Home: Equestria **0.3.1.2-maredev**, Godot **4.5**, on Linux and Windows x86_64. Use Python 3.11+, source from the matching upstream tag and the official release engine. The source project's base version remains `0.3.1-maredev`; the cumulative update supplies the `.2` build version.

The game now provides streaming, playback and native lip-sync. Building this routing-only mod needs no C++ compiler, extra native library, model download or Python inference packages. The earlier native sources remain in Git history/development tooling; they are not inputs to this mod pack.

```bash
python3 scripts/build.py \
  --game-source /path/to/home-equestria-at-0.3.1.2-maredev \
  --engine /path/to/HomeEquestria-0.3.1.2-maredev-linux/HomeEquestria.x86_64
```

Add `--platform windows-x86_64` to produce the Windows-named pack. Both packs contain the same portable GDScript; native game libraries come from the installed game. The builder uses the matching official mod packer and includes only the routing extension, manifest and notices. It does not change the game/source tree or a player's mods folder.

Outputs are `dist/breeze_tts_pny-0.1.2-linux-x86_64.pck` and `dist/breeze_tts_pny-0.1.2-windows-x86_64.pck`. Keep `dist/SHA256SUMS` and the `.build.json` receipts with them. Receipts record the effective target, base version, packed source hashes and official builder hash.

## Checks

```bash
python3 scripts/verify.py --game-release /path/to/HomeEquestria-0.3.1.2-maredev-linux
python3 scripts/world_check.py
python3 scripts/audio_check.py --speech-pcm /path/to/local/speech.s16
python3 scripts/audio_check.py --actor spike --speech-pcm /path/to/local/speech.s16
```

Run `verify.py` first. It prepares a clean isolated release under `build/verify/game` using the game executable, two main packs, cumulative update, stock bundled mods and native `.so` dependencies. It verifies the effective game version, standard extension loading, all stock forced-Ponese profiles on WAV and PCM, global voice settings and original game lip-sync. Test game processes run from that directory, avoiding loose source files in the caller's working directory. They use separate `XDG_DATA_HOME` folders; personal saves and settings are not read or changed. The transport fixture binds only loopback and uses no external TTS service.

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

## Publishing the mod update

`release/mod.json` records the tag, release notes, tested pack hash, pinned game SDK commit and pinned Godot download. A change to that file on `main` runs `.github/workflows/publish-mod.yml`; the workflow can also be started manually from GitHub Actions.

The workflow builds both platform packs from public pinned inputs, requires an exact match to the locally validated pack hash, audits the six release assets and publishes through the repository's scoped `GITHUB_TOKEN`. It creates a draft, uploads and verifies asset digests, then publishes it. Existing published artifacts are never replaced. This workflow publishes only the game mod; companion and voice archives retain their existing release.

A local preparation check, without publishing, is:

```bash
python3 scripts/release_mod.py prepare
```
