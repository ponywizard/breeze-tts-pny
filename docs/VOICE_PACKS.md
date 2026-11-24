# Portable voice packs and native runtime

Voice packs are separate, versioned `.tar.gz` assets. A pack contains `voice-pack.json`, selected `voices/<id>.breeze` caches, required `adapters/<id>.gguf` files and asset notices. The installer accepts local files or HTTPS downloads with a supplied SHA-256. Extraction rejects traversal, links, duplicate entries, oversized content and non-regular members. Every payload file has a SHA-256 inventory, checked on installation and server startup.

The `curated-ponies-20261107` snapshot contains all 139 active Breeze reference caches and six adapters: Applejack, Fluttershy, Pinkie, Rainbow, Rarity and Twilight. The export preserves the playtested character IDs, exact transcripts, reference hashes, source provenance, inference settings and legacy numbered-speaker mapping. It excludes trial voices, audition audio, captured conversations, endpoints and absolute lab paths.

Every route must be `breeze`; retired or unknown routes are rejected. Use `--id` and `--version` when exporting a new snapshot. Reference caches are encoded native assets; the original source recordings and model weights stay outside Git.

## Manifest

The companion accepts schema 1 and 2. Schema 2 is required when any route uses playback-speed conversion, and requires companion 0.2.2+. Required fields:

- `id`, `version`, `model_sha256`: identity and the compatible Breeze base. Companion 0.3.0 also accepts the explicitly pinned quantizations of that same base/codec family; each model file retains its own checksum. Earlier companions require the exact model hash. See [model management](COMPANION.md#models).
- `characters`: rows with `id`, optional `name`, and `route` (`breeze` only).
- `voices`: Breeze voice IDs mapped to `file`, `ref_text`, `reference_sha256`, and optional source provenance.
- `adapters`: adapter IDs mapped to relative `.gguf` paths.
- `legacy_speakers`: original numbered speaker IDs mapped explicitly to characters.
- `files`: every payload path mapped to its SHA-256.

A Breeze character selects `voice_id` and optional `settings`: `cfg_scale`, `temperature`, `depth_temperature`, `instruction`, `lora`. The server explicitly selects the stock base when `lora` is empty and rejects unacknowledged adapter selection. Inference defaults to seed 42, with an optional per-request seed in companion 0.3.1+ (see [PROTOCOL.md](PROTOCOL.md#speech-request)), no text splitting and a 60-second audio cap. Character identity wins over placeholder speaker numbers.

Companion 0.3.1+ also accepts per-request delivery `direction`, appended to a route's existing `instruction` for that synthesis only. An empty direction preserves the curated instruction, including an intentionally empty instruction on a trained adapter. Directions do not modify the voice pack or select another reference recording.

A schema-2 character may select `output_speed: 1.25`; this is a playback field, separate from native inference settings. The current `curated-ponies-20261115` export uses it only for the slow-trained Pinkie adapter/reference. Other rows default to normal playback. Cached-reference metadata records the matching `output_speed`. The pack advertises `minimum_companion_version`; its new schema makes older companions reject it safely. See [voice update details](VOICE_UPDATES.md).

For custom voices, register a reference and exact transcript with the compatible native engine to create its `.breeze` cache, then build a manifest and inventory. `scripts/export_voice_pack.py` adapts the existing lab manifest/reference format. The native engine's [voice documentation](https://github.com/HoppouAI/Breeze-TTS-2.cpp/blob/v0.1.6/docs/voices.md) describes cache registration. Arbitrary server-side file paths or per-voice network endpoints are not supported by this pack format.

For a guided local replacement, use the [voice library](VOICE_LIBRARY.md). Packs may also include `reference_file` for each voice: an inventoried WAV whose file hash equals `reference_sha256`. Export with `--include-reference-audio` to make original references playable in the library. Personal packs record selected overrides in `custom_voices`; the installer reapplies these during updates.

Companion 0.3.2 adds [named custom voices in Companion](COMPANION.md#add-a-custom-voice). Personal packs also record added character IDs in `custom_characters`, a unique list whose entries must have matching `custom_voices` mappings. These routes, names, caches and reference recordings are carried into updated curated packs. An ID collision with a new curated route stops the update. Added voices use the base model with no adapter; replacing a curated reference keeps its existing route settings.

## Queen Chrysalis

The `curated-ponies-20261123` pack adds Queen Chrysalis to the 139 voices in the November 15 pack. [Queen Chrysalis mod 0.2.12](https://mods.pones.top/mod/69) gives her profile ID `chrysalis` and legacy speaker number `7`. Its disguise profiles also use `chrysalis`, so they select the same Breeze voice.

The selected reference is take C, “The castle search”, from the /ppp/ special-source recording of S08E13 at 04:39. It uses 5.14 seconds of neutral dialogue and the Q8 audition's base-model settings. The transcript is “I assumed they were in Canterlot. My castle search proved otherwise.” [Source FLAC](https://mega.nz/folder/jkwimSTa#_xk0VnR30C8Ljsy4RCGSig/file/HkxxGKID) · [Archive transcript](https://mega.nz/folder/jkwimSTa#_xk0VnR30C8Ljsy4RCGSig/file/qtpDnSbY)

Companion 0.3.3 accepts the new archive on Linux and Windows. Pass `--voice-pack` with the new archive to the usual installer, plus `--update` for an existing installation. To reproduce the archive, use FFmpeg, the published November 15 pack, the source FLAC above and a stopped Q8 Companion installation. The build uses a temporary native voice cache.

```bash
python3 scripts/build_chrysalis_pack.py --base-pack "$base_pack" --flac "$source_flac" --config "$companion_config"
```

## Native patch and licensing

The selected runtime is [Breeze-TTS-2.cpp v0.1.6](https://github.com/HoppouAI/Breeze-TTS-2.cpp/tree/v0.1.6), revision `87b43667ca5597f826441991e416a279ed7373b9`, with the included per-request LoRA patch. The model stays resident and adapters are selected per utterance; the build uses one generation slot. The published stock binary alone does not provide this patch's adapter acknowledgement contract.

```bash
python3 native/breeze/build.py \
  --source build/breeze-source --build build/breeze-native
```

Requires a C++17 compiler, Git, CMake, Vulkan development files, `glslc` and SPIR-V headers. The build pins upstream source, applies the patch, initializes ggml, disables MP3, and runs its native CPU checks. `--cpu` is for development; this preview's game-ready package is validated with Vulkan. Preserve a runtime hash receipt when collecting the executable and its `libggml*.so*` dependencies for `package_runtime.py`.

Native runtime bundles include the exact source patch, build recipe and upstream/ggml licenses. The patch extends Apache-2.0 source; it is separate from this repository's original MIT server code. Model weights and reference/adapter assets retain their own terms. Voice-pack metadata records provenance and does not claim that the repository's MIT license grants rights over source recordings or performances.

Windows uses the same curated voice archive. See [WINDOWS-BUILD.md](WINDOWS-BUILD.md) for the Linux-hosted cross-build of the patched Windows runtime.
