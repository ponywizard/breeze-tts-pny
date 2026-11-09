# Companion validation

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
  --game /path/to/clean/HomeEquestria-0.3.0-maredev-linux
```

The output directory must be new. The check uses separate loopback test ports, owns its service and stops it afterward. Use `--port` and `--native-port` if its defaults are occupied. It does not change another running companion.

Runtime, voice-pack and model SHA-256 values are recorded in the matching release/build receipts. Local input/output logs and timing comparisons are retained under ignored `build/`; they are not shipped as end-user setup files. The evidence does not establish a latency guarantee or an independent listening review of every voice.
