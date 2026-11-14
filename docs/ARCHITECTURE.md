# Runtime design

Game mod 0.1.2 targets Home: Equestria **0.3.1.2-maredev**. This game release already supplies framed PCM streaming, sentence grouping, live speech handoff, playback and Talking Avatar lip-sync. The mod uses those implementations and ships one narrow TTS subclass for Breeze character routing.

## Script installation

The manifest's standard `extends` list installs `ext/tts_client.gd` over the game's TTS client. The current game loader handles compiled bases, remaps, later preloads and failed-extension rollback. The old private extension installer and character/playback backports have been retired. The pack includes no replacement game scripts, native library or lip-sync model.

Disabling/removing the mod and restarting restores the game's own voice selection. Streaming and lip-sync remain available because they are game features. The mod adds no world-save fields and never edits character JSON files on disk.

## Character routing

For an HTTP(S) MOSS URL ending in `/tts`, the subclass copies the speaking profile, selects TTS for that request and adds the original `character_id` to the request body. This overrides stock per-character Ponese modes, missing numbered voices and shared-speaker defaults for the full Breeze roster. It works on ordinary WAV requests before `/health` succeeds as well as on streamed requests. The original profile remains unchanged.

Global Ponese and disabled-TTS settings still take precedence. Other providers and endpoint formats retain stock voice selection. Synthesis, cancellation, error fallback, stream ownership, sentence grouping, playback and mouth analysis run through the game's original code.

## Release versions

The full game archive reports base project version `0.3.1-maredev`; its cumulative patch reports `0.3.1.2-maredev` through `world/debug/version.gd`. Validation and the optional Windows playtest helper check that effective version. Validation stages both official packs and the cumulative update, so an older base cannot silently stand in for the targeted release.

The companion protocol, model, curated voice pack and LoRA adapters are unchanged. This is a game-mod update; the existing companion 0.2.1 installation remains usable.
