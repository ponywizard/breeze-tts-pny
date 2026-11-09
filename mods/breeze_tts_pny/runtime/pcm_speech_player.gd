extends Node
## Incremental mono PCM through the actor's existing spatial voice player.
signal started
signal finished
signal failed(message: String)
const RATE := 24000
const START_FRAMES := 4800 # 200 ms of audio; not 200 ms of wall-clock waiting.
var _start_frames := START_FRAMES # the utterance may ask for more
var source: RefCounted
var voice: AudioStreamPlayer3D
var playback: AudioStreamGeneratorPlayback
var active := false
var began := false
var consumed_frames := 0
var _capacity := 0
var _sent := 0
var _pushed := 0
var _last_skips := 0
var _underruns := 0
var _rebuffering := false
var _drain_ms := -1
var _last_data_ms := 0
var _seen := 0

func _init() -> void: set_process(false)

func begin(utterance: RefCounted, player: AudioStreamPlayer3D) -> void:
	source = utterance; voice = player; active = true
	_start_frames = maxi(START_FRAMES, int(utterance.get("start_frames")) if utterance.get("start_frames") != null else START_FRAMES)
	_last_data_ms = Time.get_ticks_msec()
	set_process(true)

func cancel() -> void:
	if not active: return
	active = false; set_process(false)
	if is_instance_valid(voice): voice.stop(); voice.stream_paused = false
	if source != null: source.cancel()
	_log("cancel")

func _exit_tree() -> void: cancel()

func _process(_delta: float) -> void:
	if not active: return
	if source.cancelled: _fail("PCM speech cancelled"); return
	if not source.error.is_empty(): _fail("PCM stream failed: " + source.error); return
	var frames: int = source.pcm.size() / 2
	if frames != _seen: _seen = frames; _last_data_ms = Time.get_ticks_msec()
	if not source.done and Time.get_ticks_msec() - _last_data_ms > 10000:
		_fail("PCM stream stalled"); return
	if not began:
		if frames < _start_frames and not source.done: return
		if frames == 0: _fail("Empty PCM speech"); return
		var generator := AudioStreamGenerator.new()
		generator.mix_rate = RATE; generator.buffer_length = 0.5
		voice.stream = generator; voice.stream_paused = false; voice.play()
		playback = voice.get_stream_playback() as AudioStreamGeneratorPlayback
		if playback == null: _fail("PCM playback unavailable"); return
		_capacity = playback.get_frames_available()
		_fill(frames)
		_last_skips = playback.get_skips()
		began = true
		_log("start", {"request_to_play_ms":Time.get_ticks_msec()-source.request_ms,
			"output_latency_ms":AudioServer.get_output_latency()*1000.0,
			"buffer_ms":frames*1000.0/RATE})
		started.emit()
		return
	if not voice.playing and not _rebuffering: _fail("PCM playback stopped early"); return
	var skips := playback.get_skips()
	if skips > _last_skips and (not source.done or _sent < frames):
		_underruns += skips - _last_skips
		voice.stream_paused = true; _rebuffering = true
		_log("underrun", {"skips":skips-_last_skips})
	_last_skips = skips
	if _rebuffering:
		if frames - _sent < _start_frames and not source.done: return
		_fill(frames); voice.stream_paused = false; _rebuffering = false
		_log("resume")
	_fill(frames)
	var queued := _capacity - playback.get_frames_available()
	consumed_frames = mini(_sent, maxi(consumed_frames, _pushed - queued))
	if source.done and _sent == frames:
		# Keep the generator alive with silence while final speech drains through
		# the mixer/output queue. These frames never advance the speech timeline.
		var count := playback.get_frames_available()
		if count > 0:
			var silence := PackedVector2Array(); silence.resize(count)
			if playback.push_buffer(silence): _pushed += count
		if consumed_frames >= frames:
			if _drain_ms < 0: _drain_ms = Time.get_ticks_msec()
			if Time.get_ticks_msec()-_drain_ms >= AudioServer.get_output_latency()*1000.0 + 40.0:
				active = false; set_process(false); voice.stop()
				_log("finished", {"audio_ms":frames*1000.0/RATE})
				source.release(); finished.emit()

func _fill(frames: int) -> void:
	var count := mini(playback.get_frames_available(), frames - _sent)
	if count <= 0: return
	var samples := PackedVector2Array(); samples.resize(count)
	for i in count:
		var value := float(source.pcm.decode_s16((_sent+i)*2))/32768.0
		samples[i] = Vector2(value,value)
	if playback.push_buffer(samples): _sent += count; _pushed += count

func _fail(message: String) -> void:
	_log("failed", {"message":message})
	cancel()
	failed.emit(message)

func _log(event: String, extra: Dictionary = {}) -> void:
	extra.merge({"event":event,"utterance":source.uri,"underruns":_underruns,"consumed_frames":consumed_frames})
	print("[pcm-playback] ",JSON.stringify(extra))
