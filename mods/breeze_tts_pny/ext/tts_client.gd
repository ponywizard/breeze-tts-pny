extends "res://world/ai/tts_client.gd"
const UTTERANCE := preload("res://mods/breeze_tts_pny/runtime/pcm_utterance.gd")
const PCM_STREAM := preload("res://mods/breeze_tts_pny/runtime/pcm_voice_stream.gd")
const NATIVE := preload("res://mods/breeze_tts_pny/runtime/native_loader.gd")
signal live_render_finished
var _pcm_stream: Node
var _health: HTTPRequest
var _probe_serial := 0
var _probe_attempts := 0
const PROBE_ATTEMPTS := 6
const REPROBE_MS := 30000
var _probe_ms := -REPROBE_MS
var _breeze_url := ""
## Audio frames buffered before playback starts. A router may ask for more than
## 200 ms in /health ("prebuffer_ms"): one slower than real time, or far away.
const START_FRAMES := 4800
const MAX_START_FRAMES := 24000 * 4
var _start_frames := START_FRAMES
var _want_live := false
var _live: RefCounted
var _live_announced := false
var _breeze_character := ""

func _ready() -> void:
	super._ready()
	_pcm_stream = PCM_STREAM.new()
	_pcm_stream.name = "BreezePcmStream"
	add_child(_pcm_stream)
	_pcm_stream.response_completed.connect(_on_pcm_completed)
	_pcm_stream.pcm_chunk.connect(_on_pcm_chunk)
	_probe.call_deferred()

func configure(section: Dictionary) -> void:
	super.configure(section)
	_breeze_url = ""
	_start_frames = START_FRAMES
	_probe_attempts = 0
	_probe.call_deferred()

func _probe() -> void:
	_probe_serial += 1
	if is_instance_valid(_health):
		_health.cancel_request(); _health.queue_free(); _health = null
	if not is_inside_tree() or not NATIVE.supported() or provider != "moss" or not (url.begins_with("http://") or url.begins_with("https://")) or not url.rstrip("/").ends_with("/tts"): return
	_probe_attempts += 1
	_probe_ms = Time.get_ticks_msec()
	_health = HTTPRequest.new(); _health.timeout = 5.0; _health.body_size_limit = 65536
	add_child(_health)
	_health.request_completed.connect(_on_health.bind(url, _probe_serial))
	var error := _health.request(url.rstrip("/").trim_suffix("/tts") + "/health")
	if error != OK: _retry_probe(_probe_serial, error, 0)

func _on_health(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray, requested_url: String, serial: int) -> void:
	if serial != _probe_serial or requested_url != url: return
	if result != HTTPRequest.RESULT_SUCCESS or code in [408, 429, 500, 502, 503, 504]:
		_retry_probe(serial, result, code)
		return
	if code != 200: return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not data is Dictionary or data.get("pcm_stream") != "framed-v1" or data.get("native_backend") != "breeze": return
	if not data.get("ready", false):
		_retry_probe(serial, result, code)
		return
	_breeze_url = url
	var hint: Variant = data.get("prebuffer_ms", 0)
	_start_frames = clampi(int(hint) * 24, START_FRAMES, MAX_START_FRAMES) if hint is float or hint is int else START_FRAMES
	print("[breeze-tts-pny] Compatible character router detected; incremental speech enabled (prebuffer ", _start_frames / 24, " ms).")

func _retry_probe(serial: int, result: int, code: int) -> void:
	print("[breeze-tts-pny] capability probe attempt=", _probe_attempts, " result=", result, " HTTP=", code)
	if _probe_attempts >= PROBE_ATTEMPTS or not is_inside_tree(): return
	var delay := minf(pow(2.0, _probe_attempts - 1), 10.0)
	await get_tree().create_timer(delay).timeout
	if not is_inside_tree() or serial != _probe_serial or not _breeze_url.is_empty(): return
	_probe()

func can_stream() -> bool:
	return NATIVE.supported() and provider == "moss" and not _breeze_url.is_empty() and url == _breeze_url

func build_body(text: String, speaker_id: int, emotion: String) -> Dictionary:
	var body := super.build_body(text, speaker_id, emotion)
	if can_stream() and not _breeze_character.is_empty(): body["character_id"] = _breeze_character
	return body

## A router that came up after every probe attempt (a Colab link pasted while
## the notebook was still loading) is found again on a later line.
func _reprobe_if_given_up() -> void:
	if _breeze_url.is_empty() and _probe_attempts >= PROBE_ATTEMPTS and Time.get_ticks_msec() - _probe_ms >= REPROBE_MS:
		_probe_attempts = 0
		_probe()

func synthesize_profile(text: String, profile: Dictionary, emotion: String, on_done: Callable) -> bool:
	_reprobe_if_given_up()
	var settings := get_tree().root.get_node_or_null("Settings") if is_inside_tree() else null
	if not can_stream() or CHATTER.is_ponese_mode(voice_mode) or (settings != null and settings.has_method("tts_enabled") and not settings.tts_enabled()):
		return super.synthesize_profile(text, profile, emotion, on_done)
	if busy: return false
	var generation := _generation
	var finished := func(path: String, error: String) -> void:
		if generation != _generation or not on_done.is_valid(): return
		if error != "" and chatter_fallback and _start_chatter(text, profile, emotion, on_done): return
		on_done.call(path, error)
	_breeze_character = str(profile.get("id", ""))
	var accepted := synthesize(text, int(profile.get("tts_speaker_id", 31)), emotion, finished)
	_breeze_character = ""
	return accepted or busy

func cancel() -> void:
	if _live != null:
		_live.cancel_transport = Callable()
		_live.cancel(); _live = null
	if is_instance_valid(_pcm_stream): _pcm_stream.cancel()
	super.cancel()

func _dispatch_request(next_url: String, headers := PackedStringArray(), method := HTTPClient.METHOD_GET, body := "") -> Error:
	if can_stream() and next_url == url and is_instance_valid(_pcm_stream):
		_capture("request", {"method": method, "body": body})
		if _want_live:
			_live = UTTERANCE.new(); _live.cancel_transport = cancel; _live_announced = false
			_live.start_frames = _start_frames
		return _pcm_stream.start(url.rstrip("/") + "/stream", body, timeout)
	return super._dispatch_request(next_url, headers, method, body)

func synthesize_profile_live(text: String, profile: Dictionary, emotion: String, done: Callable) -> bool:
	if busy: return false
	_want_live = can_stream()
	var accepted := synthesize_profile(text, profile, emotion, done)
	_want_live = false
	return accepted

func _on_pcm_chunk(data: PackedByteArray) -> void:
	if _live == null or not busy: return
	_live.pcm.append_array(data)
	# Hand the line over once its prebuffer is here: the director gives playback
	# 12 seconds to start after the handoff, but stays in rendering for 90.
	if _live.pcm.size() >= maxi(9600, _live.start_frames * 2): _announce_live()

func _announce_live() -> void:
	if _live == null or _live_announced or not _on_done.is_valid(): return
	_live_announced = true
	var utterance: RefCounted = _live
	var done := _on_done; _on_done = Callable()
	var uri: String = utterance.publish()
	done.call(uri, "")
	if not utterance.claimed: utterance.cancel()

func _on_pcm_completed(result: int, code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	if _live == null:
		_on_completed(result, code, headers, body); return
	var utterance: RefCounted = _live
	if result == HTTPRequest.RESULT_SUCCESS and code == 200 and not utterance.pcm.is_empty():
		utterance.done = true
		_announce_live()
	elif _live_announced:
		utterance.error = "transport result %d, HTTP %d" % [result, code]
	else:
		utterance.release(); _live = null
		_on_completed(result, code, headers, body); return
	utterance.release()
	_live = null; _on_done = Callable(); busy = false; _stage = ""
	live_render_finished.emit.call_deferred()

func _exit_tree() -> void:
	_probe_serial += 1
	if is_instance_valid(_health): _health.cancel_request()
	super._exit_tree()
