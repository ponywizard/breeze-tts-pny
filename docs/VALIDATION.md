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

## GPU memory measurements

On November 5, 2026, three Linux PCVR sessions compared remote speech, local Breeze loaded with speech still remote, and local Breeze actively generating speech. The RX 6700 XT exposed 11.984 GiB of usable VRAM. The setup used RADV Vulkan, WiVRn/OpenXR multiview at 1832 × 1919 per eye, Home: Equestria 0.3.0 with Godot 4.5.2, and native Talking Avatar lip-sync. Graphics settings and game pack hashes matched across the runs. LLM, STT and the earlier CPU voice routes stayed on another machine.

Whole-card VRAM counters were sampled every 100 ms across each session, alongside five-minute application frame captures. The session peaks were **7.026 GiB** for remote speech, **10.849 GiB** for loaded local Breeze, and **10.971 GiB** during local speech. Minimum free VRAM was **4.958**, **1.135** and **1.013 GiB**, respectively. These totals include the desktop, game and VR runtime; the engine's separate memory estimate must not be added to them. Brief peaks between samples can be missed.

The local setup used the pinned Q8 model and a Breeze v0.1.6 native-LoRA runtime with **one resident Rainbow adapter**. The current release loads six adapters; its flatscreen measurement below uses a different workload. During the active frame capture, five base-adapter voices produced about 1.60 seconds of audio per second of synthesis; Rainbow LoRA was checked during warmup. No playback underruns or failures were observed in these sessions.

The roughly 4 GiB difference between the earlier PCVR remote and local session peaks is a memory-planning estimate from those captures. Scenes evolved between runs, so it is not an isolated measurement of Breeze's allocation or rendering cost. Memory fit alone does not establish an acceptable frame rate: average application FPS was 33.21 with remote speech, 27.70 with local Breeze loaded, and 21.63 with active local speech, with scene and pipeline-compilation differences limiting attribution. Larger scenes, different settings/drivers and additional local models can need more capacity.

On November 9, a **Linux flatscreen** repeat used game mod **0.1.1**, the stock Godot 4.5 game, the pinned Q8 model and all **six adapters resident** on the same RX 6700 XT; LLM/STT remained remote. The launcher recorded the entire 340.3-second game process lifetime, with 3,378 whole-card samples at a requested 100 ms interval. Peak VRAM was **10.256 GiB**, with **1.728 GiB minimum free**. These extrema were verified against the raw samples within the game interval. Rarity and base voices were active in this repeat. This is a current-pack flatscreen measurement, not a matched comparison with the earlier PCVR runs or a full frame-time benchmark.

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

The November 9 Windows **0.1.1** smoke candidate passed exported Godot 4.5.2 checks under Wine: enabled/disabled loading, all 55 eye fields, replacement compatibility and atomic refusal, framed transport, identity routing, interruption, recovery and prebuffering. The offline Windows installer verified the model/runtime/voice assets, and the installed companion generated seven WAVs with the six expected adapter acknowledgements and Spike's base route. Bundled Windows Python ran 33 tests with the four Linux GPU-capture tests skipped. Profile upgrade and log collection helpers were also exercised under Wine. The candidate's native Windows manual smoke test remains pending; the earlier native Windows observations below concern the preceding build.

The release cleanup rebuilds native binaries with relative diagnostic source paths and portable Linux library search paths. Automated checks are repeated after rebuilding; the earlier manual listening sessions used the preceding builds. No voice/reference/model settings were changed by that cleanup.

The packaged sentence grouping matches the previously used local VR grouping and has automated exported-game coverage on Linux and Windows under Wine. A subsequent Linux flatscreen listening pass tested the updated packs with Pinkie Pie and Rainbow Dash. The earlier Windows and VR manual sessions preceded this grouping update.

## Manual observations

The November 9 Linux flatscreen source-candidate test used game mod **0.1.1** with the local Q8 companion and all six adapters resident; LLM/STT stayed remote. All **29 completed PCM streams** succeeded, and their durations matched the companion records in order. Pinkie, Rarity, Scootaloo, Archer and Sweetie Belle spoke. All **14 observed live playback starts finished**, with no observed underruns or playback failures; one transport cancellation was recorded. Median request-to-player-start time was **459 ms** (range 330–495 ms), excluding LLM/STT and physical speaker latency. Autosave on quit completed in 700 ms. The tester reported that speech and lip-sync looked and sounded good.

Performance measurement for that run is incomplete. The external GPU recorder reached its 30-minute limit before the game launched, and the stock game's F9 handler failed to load the omitted `res://tools/runtime_profile.gd`, producing three related engine errors. No complete frame trace or concurrent game/TTS VRAM peak was captured. The game also logged its existing 14-channel PulseAudio input warnings. This functional pass does not replace the earlier GPU memory measurements above.

A subsequent November 9 repeat captured the current-pack flatscreen VRAM figures above. All **17 PCM streams** succeeded and matched companion durations in order; all **seven live playback starts finished**, with no observed underruns or playback failures. Sweetie Belle, Rarity and Minuette spoke. Median request-to-player-start time was **423 ms** (range 353–614 ms). The game exited with code 0 and autosaved in 686 ms. Four Window `focus_entered`/`tree_exited` signal-disconnect engine errors were logged; the same error signatures occur in earlier 0.1.0 playtest logs. The existing 14-channel PulseAudio input warnings remained. No TTS/PCM failure or Vulkan device/memory error was observed. This run intentionally omitted F9 and full frame tracing.

The earlier Linux flatscreen grouping check recorded 51 successful stream completions: 34 Pinkie, 13 Rainbow and four Starlight, all with the expected adapter acknowledgements. Of 31 live playback starts, 29 finished and two were cancelled. Two lines briefly rebuffered, resumed and finished. No TTS, GDScript or engine errors were logged, and autosave completed in 703 ms. Existing PulseAudio input-channel warnings and two navigation approach failures were also recorded. The tester reported that the conversations seemed good.

The Linux flatscreen session covered all six adapters and Angel Wings. One Rarity line rebuffered and recovered. The Linux VR session recorded 360 successful stream completions and 95 live playback starts; three lines rebuffered, resumed and finished. Both sessions autosaved successfully. Some engine warnings/errors were recorded, including input-channel warnings and errors around VR scene shutdown.

The native Windows flatscreen session recorded 486 successful stream completions and 92 live playback starts/finishes, with no underruns, TTS failures, GDScript errors or engine errors. An early STT transport failure and two startup capability probes were followed by normal conversation/streaming; those logs do not independently prove microphone operation. Windows autosaved successfully. Common-controls and deprecated physics-interpolation warnings were present.

Typical TTS startup was lower in the Windows session. Scenes, speakers, native builds and drivers differed, so these sessions do not isolate an OS performance difference. Godot's reported output latency is a driver estimate; it is not a physical speaker measurement. LLM/STT request durations were not captured.

Not every reference voice has received an independent listening review. The known interruption/history edge case is unchanged: replying before a pony finishes can cancel the line and roll its unfinished dialogue out of the conversation history.

## Reproduce checks

[BUILD.md](BUILD.md) covers Linux game/mixer/save checks. [WINDOWS-BUILD.md](WINDOWS-BUILD.md) covers cross-building and Wine checks. [SERVER_VALIDATION.md](SERVER_VALIDATION.md) covers installed-companion checks. For a disposable Windows world, use the optional isolated-profile helper described in [WINDOWS.md](WINDOWS.md#optional-isolated-playtest).

Logs, captured test data and machine-specific receipts stay in ignored `build/`, outside release source and end-user archives. Release artifact hashes and packed-file inventories are in `dist/`. These are corruption/inventory checks, not a publisher signature or a reproducible-build guarantee.
