# Runtime design

Game mod 0.1.3 targets Home: Equestria **0.3.1.2-maredev**. This game release already supplies framed PCM streaming, sentence grouping, live speech handoff, playback and Talking Avatar lip-sync. The mod uses those implementations and ships one narrow TTS subclass plus a client-selection entry hook for Breeze character routing.

## Script installation

The manifest's standard `extends` list installs `ext/tts_client.gd` over the game's TTS client. The current game loader handles compiled bases, remaps, later preloads and failed-extension rollback. The old private extension installer and character/playback backports have been retired.

Some earlier mods, including Watch Party, preload the conversation director before Breeze extends TTS. Its cached `TTS` constant then keeps the stock class even though later loads find the Breeze subclass. The entry node uses the game’s `Mods.on_node("group:conversation_director", ...)` hook after each director is ready. If its actual client is stale, the hook replaces that idle client with the current subclass, preserving configuration, output directory, debug state and render-finished signal connections. It cancels/removes the old client and leaves every earlier director hook in place. An already routed client is retained. This also runs when a world creates a new director after loading. The pack includes no replacement game scripts, native library or lip-sync model.

Disabling/removing the mod and restarting restores the game's own voice selection. Streaming and lip-sync remain available because they are game features. The mod adds no world-save fields and never edits character JSON files on disk.

## Character routing

For an HTTP(S) MOSS URL ending in `/tts`, the subclass copies the speaking profile, selects TTS for that request and adds the original `character_id` to the request body. This overrides stock per-character Ponese modes, missing numbered voices and shared-speaker defaults for the full Breeze roster. It works on ordinary WAV requests before `/health` succeeds as well as on streamed requests. The original profile remains unchanged.

Global Ponese and disabled-TTS settings still take precedence. Other providers and endpoint formats retain stock voice selection. Synthesis, cancellation, error fallback, stream ownership, sentence grouping, playback and mouth analysis run through the game's original code.

## Release versions

The full game archive reports base project version `0.3.1-maredev`; its cumulative patch reports `0.3.1.2-maredev` through `world/debug/version.gd`. Validation and the optional Windows playtest helper check that effective version. Validation stages both official packs and the cumulative update, so an older base cannot silently stand in for the targeted release.

The mod and companion have independent versions. Game mod 0.1.3 continues to work with the published companion 0.2.1 and with Breeze Companion 0.3.2. The companion includes the browser UI, model management, reviewed cues and new Pinkie profile introduced in 0.3.0; 0.3.1 adds seed and delivery-direction controls; 0.3.2 adds opt-in LAN browser hosting and named custom voices.

## Companion UI and model ownership

`serve --web` holds one installation lock through `Companion`, which extends the reference editor's staging/undo workflow. The game API listener and a separate loopback-only management listener share one `Router` and one native renderer. The management listener uses Host/Origin checks and a session token; its privileged endpoints are not added to the game-facing listener.

Generation, reference preparation/preview/activation and model load/unload/delete use the router's single operation lock. Model downloads run independently and expose job progress. Loading validates the catalog hash and dependencies before unloading the working model, then checks all native voice metadata before saving the selected model. Failure attempts to restart the previous model. Management and health listeners remain up while the native process changes.

`models.py` pins all seven hashes, byte sizes and one upstream revision. Voice-pack compatibility accepts exact legacy model pins or the explicitly enumerated quantizations of the same base/codec family. This is separate from checking the selected model's file integrity. The installer preserves the selected catalog variant, ports and auto-load setting across updates, and reuses the existing personal-reference migration checks.

The browser uses the same `/tts` implementation as API clients. Its Cancel button aborts that HTTP request, allowing the existing disconnect watcher to cancel native synthesis. Reference previews use the same native PCM reader and playback conversion. Applying or undoing a reference updates the shared router's bank immediately.
