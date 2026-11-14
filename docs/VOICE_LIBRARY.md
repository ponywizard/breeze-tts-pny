# Voice library

Reference Management Utility version **0.1.0**, distributed as a separate prerelease compatible with companion **0.2.1**. Download the combined ZIP and its SHA-256 file from [the utility release](https://github.com/ponywizard/breeze-tts-pny/releases/tag/reference-manager-v0.1.0).

The local browser wizard lets you browse every character, listen to available reference recordings, generate speech previews, and replace a reference without editing JSON or checksums. It uses the installed Breeze model and runtime. No FFmpeg, pip packages, cloud service, or model training is required.

The **Reference Management Utility and Recordings** download includes the utility and all 139 original reference WAVs in one ZIP. Extract it once; the standalone launcher finds the included `reference-audio` folder automatically. On Windows, extract into the existing Breeze TTS PNY package folder beside its `python` and `companion` folders. On Linux, extract anywhere and run `sh voice-library.sh --config /path/to/companion/config.json`.

Stop the companion first. On Windows, run `voice-library.cmd` in the extracted package folder after setup. On Linux, run the installed launcher:

```bash
"${XDG_DATA_HOME:-$HOME/.local/share}/breeze-tts-pny/bin/breeze-pny" voice-library
```

For a source checkout and an existing installation:

```bash
PYTHONPATH=server python3 -m breeze_pny voice-library --config /path/to/companion/config.json
```

Keep the terminal open while using the library. It prints a local browser link; `--no-browser` prints the link without opening it. The library owns the installation lock and starts its own temporary native renderer when you first request speech. Close the library with its **Close library** button or Ctrl+C in the terminal, then start the companion to use saved changes.

## Replace a reference

1. Find a character. Listen to the current reference or generate a current voice preview.
2. Choose a clean audio recording. Select its start and end times, then choose **Prepare selection**. A reference must be between 0.25 and 30 seconds. Input files are limited to 64 MiB and five minutes; trim longer sources first.
3. Listen to the selected recording and enter its exact words. Add the episode, video link, performer, or other source notes if available.
4. Choose **Generate replacement preview**. The first preview loads Breeze and can take a few minutes. Preview speech uses the character's current inference settings and adapter.
5. Listen, then choose **Save reference**. Only the selected character switches to the new reference, including when several characters originally shared a voice.

The browser decodes supported formats, mixes channels equally to mono, resamples to 24 kHz, and writes a 16-bit PCM WAV. Browser format support varies; WAV is the most portable input. If the browser cannot open a recording, export it as WAV in an audio editor. No automatic normalization, denoising, pitch changes, or music removal is applied. The server validates the resulting WAV before registration. The saved WAV and its exact transcript remain with the personal pack.

## Reference recordings in older packs

The original curated release contains encoded `.breeze` voice caches, not playable source WAVs. For those entries the library shows the reference transcript and offers generated speech previews. Newly replaced references always have playable recordings.

The standalone utility also accepts a separate reference-audio ZIP. Extract its `reference-audio` folder alongside `voice-library.py`; the standalone launcher detects it automatically. Each recording is checked against the installed voice's reference hash, so a bundle from a different bank will not play an unrelated clip. Maintainers can build this download with `scripts/package_reference_audio.py --references references.json --output reference-audio.zip`.

Build the combined download with `python3 scripts/package_voice_library.py --reference-audio dist/breeze-reference-audio-preview.zip`. The packager checks every recording against the audio archive's manifest before including it. `reference-manager.json` records the utility version, source commit, whether the source tree was dirty, and the payload hashes. Release archives are built from the clean tagged commit. A small utility-only ZIP can also be built for code updates.

Pack maintainers can include original reference WAVs using `scripts/export_voice_pack.py --include-reference-audio`. This checks the original WAV's SHA-256 against the registered reference and adds `reference_file` to each voice's metadata. To browse an existing local collection without rebuilding a pack, use `--reference-directory /path/to/wavs`, containing `<voice_id>.wav` files. The library only offers a file whose hash matches that voice's registered reference. A generated speech sample is not a substitute for the original reference recording.

## Save, undo, and updates

Saving creates a separate pack under the installation's `assets/voice-packs/custom-*` folder and switches `config.json` only after the new pack passes validation. The previous pack is retained. **Undo last save** switches back to it; successive saves can be undone in order. Neither original release archives nor game files are modified. An interrupted conversion, failed registration, or failed preview does not activate a replacement.

The updated installer preserves personal references across `--update`, applying them to the new curated bank while retaining the new bank's inference settings. Updating to a different base model requires re-registering custom references. After an installer update, undo restores the new curated bank before personal references were reapplied. Keep the installation's custom packs if you want their reference recordings and undo history.

The wizard binds to `127.0.0.1` on an available port and uses a per-session access token. It reads local audio in the browser; audio and transcripts pass only to the local Python utility and native engine. Native logs are saved under `logs/voice-library-*.log` for troubleshooting.

## Preview validation

The companion regression suite and Chromium browser checks cover WAV conversion, MP3/FLAC import, reference playback, generated previews, saving, undo, and responsive layout. Real Linux Breeze validation registered Derpy's reference, generated speech, reloaded its saved cache, and restored the original pack in an isolated installation. Windows Python tests pass under Wine; the complete browser/native workflow still needs a native Windows check. All 139 bundled WAV hashes match the curated companion 0.2.1 pack.

The standalone utility does not upgrade the installed companion or its installer. Installers from the original 0.2.1 download can reset the configured personal pack during an update. The updated installer source preserves personal references; retain custom packs and their WAVs when using an older installer.
