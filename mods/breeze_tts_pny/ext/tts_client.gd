extends "res://world/ai/tts_client.gd"
## 0.3.1.2 supplies streaming, playback and lip-sync. Only override stock voice routing.
var _breeze_character := ""

func _has_router_endpoint() -> bool:
	return provider == "moss" and (url.begins_with("http://") or url.begins_with("https://")) and url.rstrip("/").ends_with("/tts")

func build_body(text: String, speaker_id: int, emotion: String) -> Dictionary:
	var body := super.build_body(text, speaker_id, emotion)
	if not _breeze_character.is_empty(): body["character_id"] = _breeze_character
	return body

func synthesize_profile(text: String, profile: Dictionary, emotion: String, on_done: Callable) -> bool:
	var settings := get_tree().root.get_node_or_null("Settings") if is_inside_tree() else null
	if not _has_router_endpoint() or CHATTER.is_ponese_mode(voice_mode) or (settings != null and settings.has_method("tts_enabled") and not settings.tts_enabled()):
		return super.synthesize_profile(text, profile, emotion, on_done)
	# The companion supplies the whole roster. Keep the original profile intact for saves,
	# global Ponese and fallback, while routing both WAV and PCM requests by character ID.
	var routed := profile.duplicate()
	routed["voice_mode"] = "tts"
	_breeze_character = str(profile.get("id", ""))
	var accepted := super.synthesize_profile(text, routed, emotion, on_done)
	_breeze_character = ""
	return accepted
