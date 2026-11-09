# Character router interface

This describes the interface used by the companion and development Breeze routers. See [SERVER.md](SERVER.md) for installation and operation. The mod never launches a service or downloads TTS weights.

The configured TTS provider is the game's MOSS-compatible provider, with an HTTP or HTTPS URL ending in `/tts`. HTTPS verifies the server certificate against the system's trusted roots; it is meant for a remote router such as the Colab notebook's `trycloudflare.com` link (see [COLAB.md](COLAB.md)). The stream client does not implement IPv6 literals or an authorization header. Use a local endpoint, a trusted LAN, or a tunnel as appropriate to the deployment. Speech text and character identity are sent to the configured router; the mod adds no telemetry endpoint.

## Capability probe

For a configured URL `http://host:port/tts` (or `https://…/tts`), the client requests `GET /health` with a five-second timeout and 64 KiB response limit. Enablement requires HTTP 200 and:

```json
{"ready": true, "native_backend": "breeze", "pcm_stream": "framed-v1"}
```

An optional `"prebuffer_ms"` number asks the client to buffer that much audio before playback starts or resumes after an underrun (default and minimum 200, at most 4000). A router that generates slower than real time, or sits behind a tunnel, uses it to avoid stuttering.

The probe runs when the client starts or its configuration changes. Connection failures, timeouts, transient HTTP failures and a compatible router still loading are retried up to six times, with 1/2/4/8/10-second delays. Changing configuration or closing the client invalidates pending retries. Missing or incompatible capabilities leave the existing WAV transport selected. Once every attempt has failed, the next speech request probes again, at most every 30 seconds; that line still uses the WAV transport. Probe failures log their attempt, request result and HTTP status.

## Speech request

`POST /tts/stream` receives the game's existing JSON TTS request plus `character_id`, taken from the speaking pony's original profile. The router selects the Breeze reference and adapter using that identity. Its ordinary `POST /tts` endpoint must remain available for buffered speech paths. Global disabled-TTS and Ponese settings take precedence in the game.

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
