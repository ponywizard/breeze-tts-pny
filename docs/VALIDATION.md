# Validation and support scope

This release targets Home: Equestria **0.3.0-maredev**, Godot **4.5**, with game mod **0.1.0** and companion **0.2.0**. Native manual coverage used an AMD Radeon RX 6700 XT.

| Configuration | Coverage |
| --- | --- |
| Linux x86_64 flatscreen | Extended manual play, including all Mane Six and Angel Wings |
| Linux PCVR with WiVRn | Normal manual play, 11 speaking identities |
| Windows x86_64 flatscreen | Normal manual play, including Twilight, Rarity and Noi |
| Windows PCVR | Not personally playtested; shipping with this limitation |
| Other GPUs/driver combinations | Not comprehensively qualified |
| macOS, standalone Quest, other game versions | No supported build in this release |

Windows PCVR issues will be investigated case by case. Another Windows VR playtest is not a release prerequisite.

## Automated checks

The checks cover:

- Actual exported game mod loading with the mod enabled and disabled; later preloads retain the extended speech classes.
- Source replacement compatibility: enum comments, semicolon-separated declarations, annotations, quoted delimiters, multiline strings and inherited collisions; a conflict refuses the entire installation before any extension is installed.
- Sentence grouping in captured solo/group helpers; short reactions, long sentences, punctuation, speaker boundaries, action/impression placement, facial expressions and unchanged display paging. Disabling the mod restores stock splitting.
- All 55 inspected OpenPony eye mesh/shader fields match the unmodified game.
- Native lip-sync library extraction, model loading, worker inference and cancellation.
- Automatic capability detection/recovery and original character identity routing.
- Live framed PCM and completion receipts; buffered speech; short/corrupt streams; cancellation and immediate next requests.
- OpenPony and Spike mixer playback, viseme timing, rebuffering, scene exit and real director handoff.
- New-world save/reload with an isolated profile.
- Companion asset hashes, all six adapter acknowledgements, real synthesis, duplicate-start protection and owned shutdown.
- Installer update locking, checksum failures and preservation of existing verified assets/configuration.
- Linux and Windows Python transport/platform/diagnostic tests. Windows tests run under Wine in addition to native Windows manual play.

Native LoRA numerical, adapter selection/base-restoration and depth-cache/CFG/SwiGLU regression tests also pass. Build and functional-check receipts identify the corresponding local artifacts under ignored `build/`.

The release cleanup rebuilds native binaries with relative diagnostic source paths and portable Linux library search paths. Automated checks are repeated after rebuilding; the earlier manual listening sessions used the preceding builds. No voice/reference/model settings were changed by that cleanup.

The packaged sentence grouping matches the previously used local VR grouping and has automated exported-game coverage on Linux and Windows under Wine. A subsequent Linux flatscreen listening pass tested the updated packs with Pinkie Pie and Rainbow Dash. The earlier Windows and VR manual sessions preceded this grouping update.

## Manual observations

The subsequent Linux flatscreen grouping check recorded 51 successful stream completions: 34 Pinkie, 13 Rainbow and four Starlight, all with the expected adapter acknowledgements. Of 31 live playback starts, 29 finished and two were cancelled. Two lines briefly rebuffered, resumed and finished. No TTS, GDScript or engine errors were logged, and autosave completed in 703 ms. Existing PulseAudio input-channel warnings and two navigation approach failures were also recorded. The tester reported that the conversations seemed good.

The Linux flatscreen session covered all six adapters and Angel Wings. One Rarity line rebuffered and recovered. The Linux VR session recorded 360 successful stream completions and 95 live playback starts; three lines rebuffered, resumed and finished. Both sessions autosaved successfully. Some engine warnings/errors were recorded, including input-channel warnings and errors around VR scene shutdown.

The native Windows flatscreen session recorded 486 successful stream completions and 92 live playback starts/finishes, with no underruns, TTS failures, GDScript errors or engine errors. An early STT transport failure and two startup capability probes were followed by normal conversation/streaming; those logs do not independently prove microphone operation. Windows autosaved successfully. Common-controls and deprecated physics-interpolation warnings were present.

Typical TTS startup was lower in the Windows session. Scenes, speakers, native builds and drivers differed, so these sessions do not isolate an OS performance difference. Godot's reported output latency is a driver estimate; it is not a physical speaker measurement. LLM/STT request durations were not captured.

Not every reference voice has received an independent listening review. The known interruption/history edge case is unchanged: replying before a pony finishes can cancel the line and roll its unfinished dialogue out of the conversation history.

## Reproduce checks

[BUILD.md](BUILD.md) covers Linux game/mixer/save checks. [WINDOWS-BUILD.md](WINDOWS-BUILD.md) covers cross-building and Wine checks. [SERVER_VALIDATION.md](SERVER_VALIDATION.md) covers installed-companion checks. For a disposable Windows world, use the optional isolated-profile helper described in [WINDOWS.md](WINDOWS.md#optional-isolated-playtest).

Logs, captured test data and machine-specific receipts stay in ignored `build/`, outside release source and end-user archives. Release artifact hashes and packed-file inventories are in `dist/`. These are corruption/inventory checks, not a publisher signature or a reproducible-build guarantee.
