# Reviewed voice updates included in companion 0.3.0

Breeze Companion 0.3.0 carries the behavior selected during the November 15 listening tests into the portable companion. Originally prepared as 0.2.2, these changes ship with the combined Breeze Companion release.

## Vocal expressions

Whole `Teehee!` interjections and standalone `giggle`/`giggles` cues render as `(giggles)`. `Gasp!` interjections and bare `gasp` next to ellipses render as `(gasp)`, including the lowercase forms observed in actual game lines. These substitutions affect only the text sent to native synthesis, on both WAV and PCM transports. Ordinary mentions, quoted gasp expressions and existing parenthetical cues remain intact.

The listener preferred the existing `Haha`/`Hahahaha`, `Hehe` and `Hmph!` forms. They remain unchanged. The `yawn` comparison was inconclusive because it blended into the following “Oooooh”; it remains unchanged too.

The game may already display `(giggles)` after its own earlier cleanup of `*giggle*` or `*giggles*`. The companion does not rewrite captions or conversation history, and this update does not change the game cleaner.

## Pinkie default

The new `curated-ponies-20261115` pack selects the approved slow-trained step-200 Pinkie adapter and matching slowed clear-skies reference:

- Adapter SHA-256: `4ce4839d13c95ba6241c0694f8e4ecd6e1c505fbb493ea161a45505a1700e452`.
- Reference SHA-256: `874acb2d308418d19c7186cc6c74ca5bc651bfe0abd3ed15ee9c2f558f13e30e`.
- The same 288 training and 29 validation clips/transcripts were retimed to 0.8×, with pitch and timing changing together. A fresh LoRA was trained from the base, using rank 8, alpha 16, 200 steps and learning rate 0.0001.
- Synthesis uses the 0.8× reference. Final playback is converted to 1.25× with the audition's Kaiser beta-10 rational filter. The returned PCM stays mono 24 kHz PCM16; byte counts and SHA-256 receipts describe the converted playback.

The standard-library converter uses the same fixed FIR coefficients as the lab's SciPy `resample_poly` reference. Streaming retains a bounded input history rather than buffering a whole utterance. No volume matching, compression, denoising or trimming is added. Other characters retain their existing references, adapters and playback speed.

## Pack compatibility and personal voices

Speed-aware packs use manifest schema 2 so older companions reject them instead of playing the slow synthesis at the wrong speed. Companion 0.2.2 also accepts the existing schema-1 packs at normal speed. The model/runtime and game mod are unchanged.

In the reference manager, a replacement recording for a slow-trained route is automatically retimed to 0.8× before native reference registration; preview and saved output retain the route's 1.25× playback. Trim such a source reference to 24 seconds or less so its slowed recording fits the 30-second reference budget. Other reference imports retain their prior conversion behavior.

A personal reference saved under a different playback profile cannot be silently carried into a new profile. That update is rejected before switching configuration; re-register and audition the personal recording against the new pack. Personal references on unchanged profiles continue to be preserved.

## Validation

The Python suite exercises cue preservation and idempotency, actual WAV/stream forwarding, playback receipts, truncation and cancellation, exact comparison with the SciPy lab filter, bounded buffering, reference editing, and export/schema compatibility. SciPy is an optional test oracle; it is not shipped or imported by the companion.

The source retains the training and audition scripts used for the Pinkie investigation. Training datasets, models, generated conversation audio and audition pages remain outside the release payload. Runtime/pack hashes and local artifact checks are recorded with the prepared release files. Real-model checks cover the new Pinkie route and unchanged voices; they do not establish Windows VR behavior or a new general performance guarantee.

`scripts/check_voice_update.py` can verify an extracted candidate pack against an already-running native service and lab router. It checks every registered reference and starts only a temporary loopback Python router, compares four real voice paths, then stops its own server. It does not load a second model or restart the lab. Bounded retries accommodate the service's documented busy response. Example:

```bash
python3 scripts/check_voice_update.py --voice-pack /path/to/extracted-pack --output build/voice-update-check
```

Use the companion 0.2.2 built-in `voice-library` command with the schema-2 pack. An older standalone reference utility may carry the previous companion code and reject the new pack; its earlier published ZIP is unchanged.
