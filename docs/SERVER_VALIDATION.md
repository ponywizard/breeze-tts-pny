# Companion validation

## Breeze Companion 0.3.2

The 81-test Python suite passes on Linux and under the bundled Windows Python in Wine (five expected skips). New checks cover independent API/web CLI addresses, default/specific/wildcard listeners, per-interface Host/Origin checks, missing or wrong tokens, duplicate headers and address-discovery failure. Voice checks cover adding a named route, rejecting duplicate/invalid names and IDs, requiring a preview, immediate generation, model switching, restart, replacement, undo, update preservation and conflicts with new curated IDs. The installer test preserves both a curated reference replacement and an added voice.

The Chromium workflow passes through both loopback and this machine's LAN IPv4 address with the UI bound to all interfaces. It covers new voice name/ID entry, preview invalidation after edits, save, Generate, reload, undo and safe rendering of names, plus the existing reference, seed/direction, cancellation, model and mobile checks. Browser tests use fixture audio; these checks do not establish voice quality. The LAN check uses the host's own interface, not a second physical computer. Native Windows browser/firewall and GPU testing remain for release qualification.

The release archives pass the nested-archive audit with no findings. Disposable packaged installations upgrade from 0.3.1 on Linux and under embedded Windows Python/Wine, preserving configuration and reusing the verified Q8 model. Both installed launchers serve the authenticated UI through the LAN interface, including the Windows `breeze-companion.cmd --web-host 0.0.0.0` path. The packaged Linux renderer registers an added voice from a bundled reference, auditions it and generates valid Q8 speech through the game API; another packaged update and renderer restart retain the added voice and produce valid speech again. This checks functional registration and persistence, not subjective voice quality. The Windows launcher check keeps the renderer unloaded.

To repeat the LAN browser check, set `BREEZE_TEST_WEB_ADDRESS` to an IPv4 address assigned to the test machine before running `node tests/companion_browser.cjs`. The fixture binds a temporary wildcard web listener, prints its session link to the test driver and closes it afterward.

## Breeze Companion 0.3.1

Companion 0.3.1 passes 73 Python tests on Linux and the Chromium workflow checks, including randomized seeds, retaining the last seed, manual seed entry, invalid-input rejection, persistence after reload, delivery direction, cancellation recovery and mobile layout. Both speech transports forward explicit seeds, return `X-Breeze-Seed`, reject invalid seeds before native synthesis and retain the default of 42 when omitted. Direction checks cover Unicode and length/type validation, preserving curated instructions (including deliberately empty ones), keeping spoken text separate, restoring defaults after a directed request, and displaying the completed take's direction safely without changing it when the input is edited.

The same 73-test suite passes under the pinned embedded Windows Python in Wine, with the same five expected skips as 0.3.0. This does not replace native Windows browser/GPU or game/VR testing, which remains with community testers. The earlier all-model matrix below remains the coverage for models other than Q4; the runtime and model files are unchanged.

Real Q4 generation on the RX 6700 XT accepted seeds 0 and 2147483647. For identical text, Spike's 42 → 43 → 42 sequence returned different audio for 43 and byte-identical audio for the repeated 42. Pinkie's repeated 42 produced closely matching waveforms, but not identical bytes: correlation was approximately 0.9996, compared with approximately 0.044 for seed 43. A follow-up without playback correction confirmed that the differences were already present in native PCM; applying the playback converter with different chunk sizes produced identical bytes from the same input. Fixed seeds control sampling randomness but do not promise bit-exact GPU output. The diagnostics are retained under ignored `build/companion-0.3.0/seed-native/`. The 0.3.0 archives predate these controls.

Real Q4 direction checks generated default, sad and angry instructions for Spike, Pinkie and Octavia at seed 42 with identical spoken text. Each returned valid mono 24 kHz WAV with the expected adapter, distinct output, and unchanged stored voice settings. This covers a base voice, a trained adapter with an empty default instruction, and a curated accent instruction. These checks establish functional direction support, not emotional accuracy or voice similarity; a listening comparison page and all nine WAVs are retained under ignored `build/companion-0.3.0/direction-native/`.

## Breeze Companion 0.3.0

The 0.3.0 release combines the browser interface and model manager with the previously prepared vocal-cue and slow-Pinkie changes. The game mod remains 0.1.3 and the native runtime remains the patched 0.1.6 build.

- **Python:** 69 tests pass on Linux. The pinned embedded Windows Python passes the same suite under Wine, with five expected skips: the optional SciPy oracle and four Linux GPU-capture tests. New checks cover model switching and recovery, verification before unloading, cancellation, concurrent downloads and speech, shared reference edits, HTTP authorization, deletion limits, and installer preference preservation.
- **Browser:** automated Chromium checks pass for generation, autoplay and WAV download, switching voices with identical text, pausing the previous clip when starting another generation, cancellation and subsequent generation, reference import/trim/prepare/audition/save/undo, original recording playback, provenance display, model unload/load, reload, and mobile layout. Voice-switch checks use distinct fixture audio and verify that both the player and download change. Screens were also inspected at desktop size. These workflow checks use a deterministic local fixture.
- **Real Vulkan models:** all seven pinned models (F16, Q8, Q6, Q4, Q8 DD4, Q8 DD2 and Q4 DD2) load on Linux with the RX 6700 XT. Every load verifies all 139 reference-cache transcripts and hashes. Each model generates valid 24 kHz mono PCM for all six Mane Six adapters and Derpy's base route over WAV and framed streaming; adapter acknowledgements match the selected routes. Pinkie also exercises the cue substitutions and shared reference-audition endpoint. Unloading leaves the browser responsive and the renderer stopped. This is functional coverage, not a listening comparison or a guarantee of memory headroom alongside the game.
- **Packages:** fresh installations from the Linux archive and Windows ZIP pass setup and `doctor` with Q4. The installed Linux launcher serves the authenticated UI and 139-voice state, reports the expected unavailable API while unloaded, and exits cleanly on SIGTERM. The Windows batch launcher accepts the new web flags under Wine. Release archives are checked with the existing nested-archive/path audit.

The maintainer exercised the Linux browser UI, including generation, voice selection and playback, and reported it working. A separate Q4 check alternated Lemon Hearts and Archer with identical text and reproduced each voice's own audio exactly; four further voices also returned distinct audio. A browser regression check reproduces the old clip continuing to play during the next generation and verifies that pressing Generate now pauses it.

The real-model matrix uses different text for WAV and framed requests and therefore does not establish byte parity between those transports. Earlier parity evidence for the cue/playback update is retained below. Native Windows browser/GPU testing is left to community reports; Wine results are not a substitute for it. A new in-game flatscreen/VR session has not been performed for this companion release.

Reproduce the additional checks from the repository:

```bash
python3 -m unittest discover -s tests/server
node tests/companion_browser.cjs
python3 tests/companion_native.py --config /path/to/disposable/config.json --output build/companion-native-check
```

The browser check needs Chromium. The native matrix changes the selected model and loading preference of its supplied installation; use a disposable installation with all catalog models already downloaded. It owns and stops its listeners and renderer. Local test logs, generated WAVs, screenshots and the model matrix receipt are retained under ignored `build/companion-0.3.0/`; they are not bundled into the release.

## Cue and Pinkie update included in 0.3.0

The reviewed vocal-cue and slow-Pinkie update passed 58 Python tests on Linux. The pinned embedded Windows Python passed the same suite under an isolated Wine prefix, with five expected skips: the optional SciPy oracle and four Linux GPU-capture tests. The portable converter also matched all 12 saved gasp-audition playback recordings byte for byte (67.01 seconds of audio).

The new 139-voice pack verifies all payload hashes. Its other 138 voice caches/reference hashes, their inference settings and the other five adapters match the published pack. The slow Pinkie adapter/reference hashes match the auditioned assets. All 139 cached references were checked against the loaded native service; real Pinkie, Rainbow, Derpy and Lemon Hearts output matched the deployed lab and each other across WAV and framed PCM.

These checks were performed while the voice update was planned as 0.2.2; it is now included in 0.3.0. They validate the portable voice update and do not establish Windows native/VR gameplay coverage. The game mod, native runtimes and pinned Q8 file are unchanged. See [the update notes](VOICE_UPDATES.md). The remaining sections describe the earlier 0.2.1 coverage.

Companion 0.2.1 uses Python 3.11+ and its standard library. The selected `curated-ponies-20261107` bank contains 139 Breeze reference caches and six Mane Six adapters. Cache transcripts and reference hashes were compared with the native engine before export. The pack excludes private endpoints, capture settings, absolute development paths and trial voices.

## Installed service

The packaged server was installed into empty user-owned directories on Linux and Windows/Wine with the pinned Q8 model. The Linux install also ran with `python3 -S`, which excludes site packages. No pip packages, private environment or alternate inference models were needed. The native executable, dependencies, caches and model were verified by `doctor` and startup.

Checks cover:

- Health reports all 139 routes, framed PCM capability and no inference fallback.
- Real synthesis acknowledges all six selected adapters; Spike, Angel Wings, Marble and other base references return valid PCM.
- The actual game client receives early PCM before generation completes; Spike's real conversation director hands him the live utterance.
- Duplicate startup and updates to an active installation are rejected. Disconnect cancellation releases the renderer for another request. Ordinary interruption is logged as cancellation; an unrequested truncated stream remains an error and has no successful receipt.
- Shutdown stops the owned native process. Each run records companion JSON diagnostics alongside its native log.
- Invalid checksums and active-install locks preserve the prior installation. Updates retain host/ports and save the previous configuration; obsolete backend settings are omitted.
- A recently closed native port is allowed up to 75 seconds to clear. Active listeners are rejected without being stopped, with the address reported.

The shared Python unit suite also covers buffered WAV, busy/error handling, original/legacy character identity, unsafe archives, checksum preservation, logging cleanup and platform locking. Linux and Windows/Wine runs are checked after release changes.

## Native manual coverage

Linux flatscreen play included all six adapter voices and Angel Wings. Linux PCVR with WiVRn included 11 speaking identities. Both sessions saved successfully; a few live lines rebuffered and recovered, with engine warnings/errors noted in [VALIDATION.md](VALIDATION.md).

Earlier native Windows flatscreen play with mod 0.1.0 used the matching cross-built executable/mod on the RX 6700 XT with AMD's Vulkan driver. All 486 completed PCM streams succeeded; all 92 live playback starts finished without underruns. Twilight, Rarity and Noi spoke, and autosave succeeded. One early STT transport warning was separate from the TTS transport. Router stdout was not captured in that session; native adapter acknowledgement is required by the verified companion code before PCM is returned.

The November 9 mod 0.1.1 Windows smoke pass verified all seven standalone voice routes, 28 game streams and 17 live playback starts/finishes; one line rebuffered and recovered. The detailed observations and manual coverage gaps are in [VALIDATION.md](VALIDATION.md).

Windows PCVR is untested and ships with that limitation; support is handled case by case. Other hardware, Windows/driver versions, game versions and every voice have not been comprehensively qualified. See [VALIDATION.md](VALIDATION.md) for the support matrix and the distinction between manual sessions and cleanup rebuilds.

## Reproduce the installed check

On Linux, after installing the release:

```bash
python3 scripts/check_server.py \
  --launcher /path/to/installation/bin/breeze-pny \
  --output build/server-check-new \
  --game /path/to/clean/HomeEquestria-0.3.1.2-maredev-linux
```

The output directory must be new. The check uses separate loopback test ports, owns its service and stops it afterward. Use `--port` and `--native-port` if its defaults are occupied. It does not change another running companion.

Runtime, voice-pack and model SHA-256 values are recorded in the matching release/build receipts. Local input/output logs and timing comparisons are retained under ignored `build/`; they are not shipped as end-user setup files. The evidence does not establish a latency guarantee or an independent listening review of every voice.
