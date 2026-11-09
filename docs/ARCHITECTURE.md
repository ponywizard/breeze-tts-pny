# Runtime design

The standard mod loader discovers `mods/breeze_tts_pny/mod.json` and starts its entry node before the title screen. Six narrow subclasses extend sentence grouping, TTS, conversation speech handoff, OpenPony speech, hybrid-pony speech capability and Spike speech. Base-game appearance and unrelated behavior stay in their original implementations through inheritance.

## Exported script inheritance

The tested 0.3.0 release exports base scripts as `.gdc`. Its standard `extends` installer copies these compiled bases into `user://mods/.bases/` but does not create the `.gd.remap` aliases required for inheritance. Therefore this mod uses the manifest's private `script_extensions` list and installs subclasses from its entry node.

`runtime/install_extensions.gd` reads each original installed base, caches an alias and remap under `user://mods/data/breeze_tts_pny/script-bases/`, loads the subclass, and takes over the corresponding resource path before game scenes load. The original script also moves to a private cache path so later source preloads resolve to the subclass. Script references are retained for the process lifetime. Original base-game scripts and bytecode are read from the installed game rather than bundled, and no game file or loader is changed on disk. Source replacements are accepted only when their readable inheritance chain declares none of the members the mod adds. The scan masks comments and strings before reading declarations; collisions and unreadable forms are refused before any extension is installed. Earlier development packs still conflict. This workaround is deliberately limited to the tested game version and should be revisited when the game fixes its exported extension loader.

A real defaults JSON merge makes the game's Mods panel require a restart for changes to this mod. Disabling/removing it and restarting leaves the original scripts in control. It adds no world-save fields.

## Speech and mouth motion

The sentence helper groups adjacent sentences within each speaker's contribution toward a soft target of 160 characters. An opening shorter than 48 characters stays with the following sentence, and long chunks split at spaces around 400 characters without splitting a word. Both solo and group dialogue use this helper. Actions remain on the first clip, impressions on the final clip, and the game's face mapping, display paging and word timing remain in use. The helper installs before the director captures its script references. Disabling the mod and restarting restores the original sentence-per-request behavior.

The TTS subclass probes the configured router's `/health` and enables the incremental transport only for the advertised Breeze protocol. It forwards the original character identity alongside the game's existing request fields. After roughly 200 ms of PCM has accumulated, the director can hand ownership to the pony while rendering continues. Buffered requests and ordinary providers retain WAV support.

`pcm_utterance.gd` owns stream lifetime. `pcm_speech_player.gd` handles buffering, mixer drainage and cancellation. `pcm_audible_clock.gd` aligns visemes with speech that has reached the audio output queue, including pauses for rebuffering. A late stream-integrity failure stops the partial line without replaying it as a new Ponese utterance.

Talking Avatar runs on CPU worker threads with shared model weights and bounded queues. Analyzer failures do not block audio playback. No CUDA/ONNX/Python environment or extra GPU model is required for lip-sync. Buffered analysis supports mono PCM16 WAV at 24 or 48 kHz; unsupported formats retain the original game path.

Spike uses his original spatial voice node and A–H/X facial blend-shape mapping. His subclass supplies the current cue before running the original body/face animation pass and restores the audible speech clock afterward. It suppresses the stock stop method's completion signal for interrupted mod speech: only valid, drained playback emits completion. Cancellation, failure and scene exit stop both the producer and analyzer. His existing gaze, blinking, gestures and facial expressions continue through the base implementation.

## Native library in one pack

Godot cannot load a native library directly from a packed resource. The native library is therefore stored as `.so.bin` on Linux or `.dll.bin` on Windows, verified against the embedded SHA-256 manifest, and extracted under `user://mods/data/breeze_tts_pny/native/<hash>/`. A generated local GDExtension descriptor loads that exact file. This requires no separate client-side installer. The hash checks detect corruption; they are not a publisher signature.

The platform guard accepts Linux/Windows x86_64 and game version `0.3.0-maredev`, with a platform-specific manifest entry and hash-checked library. Windows is a separate preview with native flatscreen coverage on the RX 6700 XT; Windows PCVR is untested and ships with case-by-case support; wider hardware coverage is limited. The preview has not been tested with mods that also replace the TTS/director/pony scripts, with another loaded Talking Avatar native extension, or with newer game builds. Install into a clean release for evaluation.
