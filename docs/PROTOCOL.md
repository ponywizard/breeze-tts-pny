# Character router interface

This describes the interface used by the companion and development Breeze routers. See [SERVER.md](SERVER.md) for installation and operation. Game mod 0.1.3 targets Home: Equestria 0.3.1.2 and uses its built-in transport. The mod never launches a service or downloads TTS weights.

The configured TTS provider is the game's MOSS-compatible provider, with an HTTP or HTTPS URL ending in `/tts`. HTTPS verifies the server certificate against the system's trusted roots; it is meant for a remote router such as the Colab notebook's `trycloudflare.com` link (see [COLAB.md](COLAB.md)). The stream client does not implement IPv6 literals or an authorization header. Use a local endpoint, a trusted LAN, or a tunnel as appropriate to the deployment. Speech text and character identity are sent to the configured router; the mod adds no telemetry endpoint.

## Capability probe

For a configured URL `http://host:port/tts` (or `https://…/tts`), the client requests `GET /health` with a five-second timeout and 64 KiB response limit. The game enables streaming after HTTP 200 advertising `ready: true` and `pcm_stream: framed-v1`; the companion also advertises `native_backend: breeze` and a positive `characters` count:

```json
{"ready": true, "native_backend": "breeze", "pcm_stream": "framed-v1", "characters": 139}
```

An optional `"prebuffer_ms"` number asks the client to buffer that much audio before playback starts or resumes after an underrun (default and minimum 200, at most 4000). A router that generates slower than real time, or sits behind a tunnel, uses it to avoid stuttering.

The probe runs when the client starts or its configuration changes. Connection failures, timeouts, transient HTTP failures and a compatible router still loading are retried up to six times, with 1/2/4/8/10-second delays. Changing configuration or closing the client invalidates pending retries. Missing or incompatible capabilities leave the WAV transport selected. Character routing remains enabled on that transport. Once every attempt has failed, the next speech request probes again, at most every 30 seconds; that line still uses the WAV transport. With TTS debug logging enabled, probe failures log their attempt, request result and HTTP status.

## Speech request

Both `POST /tts` (WAV) and `POST /tts/stream` receive the game's existing JSON TTS request plus `character_id`, taken from the speaking pony's original profile. With the mod active on a supported game/platform and an HTTP(S) MOSS URL ending in `/tts`, character identity takes precedence over stock per-character Ponese modes, missing numbered speakers and shared-voice defaults, including before capability detection succeeds. This applies to the whole voice roster; no character JSON edits are needed. The router selects the Breeze reference and adapter using that identity. Global disabled-TTS and Ponese settings still take precedence, and failed synthesis retains the configured Ponese fallback. Other providers and endpoint formats retain the game's normal voice selection.

Companion 0.3.1+ accepts an optional integer `seed` from **0 to 2147483647** on both speech endpoints, for example `{"character_id":"spike","text":"Hello!","seed":12345}`. Omission uses **42**, preserving existing game/API behavior. Invalid seeds (including strings, booleans, fractions and null) return HTTP 400 before synthesis. Successful responses include the effective seed in `X-Breeze-Seed`. Companion 0.3.0 always uses 42. Repeating a take requires the same text, voice reference, model and settings as well as the seed. A fixed seed does not guarantee byte-identical audio: the native GPU renderer can still produce small waveform differences.

Companion 0.3.1+ accepts optional `direction`, a string of at most 600 characters. For example, `{"character_id":"spike","text":"Hello!","seed":42,"direction":"Speak softly, with a sad, hesitant tone."}` retains the selected voice/reference and adapter, appends the direction to any curated voice instruction, and sends the combined instruction separately from spoken text. Omission, an empty string or whitespace preserves the original instruction exactly. Invalid types (including null) or longer strings return HTTP 400 before synthesis. Directions apply only to that request and are not logged by the companion.

Existing leading `[emotion]` tags from game dialogue are still stripped, without selecting another reference or inferring a direction. Clients wanting explicit emotion control should use `direction`. The companion does not interpret `(angry)` or `(sad)` as reference selectors.

## Incremental response

HTTP 200, with headers:

```text
Content-Type: application/vnd.home-equestria.pcm-stream
X-Sample-Format: s16le
X-Sample-Rate: 24000
X-Channels: 1
```

The body is a sequence of application frames, independent of HTTP chunk boundaries:

1. A four-byte little-endian unsigned payload length, followed by that many mono PCM16 bytes.
2. Repeat for each audio chunk.
3. End with a zero length, a four-byte little-endian total PCM byte count, and the 32 raw bytes of the SHA-256 digest of all PCM payloads in order.

Each audio frame is at most 65,536 bytes and has an even payload length. The client accepts at most 60 seconds of PCM and at most 12 MiB for a buffered WAV response. Playback may begin before the final receipt. Truncated or corrupt receipts invalidate the live utterance. Disconnects and cancellation must release upstream work; the game does not wait for generation to finish before cancelling locally.

The companion always returns framed Breeze PCM on `/tts/stream`. For compatibility with other providers, the client also accepts HTTP 200 with `Content-Type: audio/wav` and a complete WAV body. The client routes it through the buffered playback path. `tests/fixture_server.py` implements deterministic streaming, WAV fallback, corruption and cancellation examples for integration tests; it is not a voice server.

Companion 0.2.2 applies the reviewed giggles/gasp substitutions to a synthesis-only copy. A speed-aware voice pack may also select 1.25× playback for a slow-trained route. WAV and framed PCM both contain the final converted playback, with receipt byte counts and hashes computed after conversion. Do not apply another speed change in the client. All native completion, cancellation and length checks remain required before a successful terminal receipt.
