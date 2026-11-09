extends SceneTree
var failures := 0
var client: Node
var source: RefCounted
var callbacks := 0
var result_path := ""
var result_error := ""
var early := false
var utterances: GDScript

func _initialize() -> void: run.call_deferred()
func check(ok: bool, message: String) -> void:
	if not ok: failures += 1
	printerr("PASS " if ok else "FAIL ", message)

func received(path: String, error: String) -> void:
	callbacks += 1; result_path = path; result_error = error
	if path.begins_with("pcm://"):
		source = utterances.take(path)
		early = source != null and not source.done and client.busy

func settle() -> void:
	var deadline := Time.get_ticks_msec() + 6000
	while client.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not client.busy, "transport finishes within deadline")

func reset() -> void:
	source = null; callbacks = 0; result_path = ""; result_error = ""; early = false

func run() -> void:
	var port := OS.get_cmdline_user_args()[0]
	var endpoint := "http://127.0.0.1:" + port
	root.get_node("Settings").set_value("voice/tts", true)
	utterances = load("res://mods/breeze_tts_pny/runtime/pcm_utterance.gd")
	client = load("res://world/ai/tts_client.gd").new(); root.add_child(client)
	client.configure({"provider":"moss", "url":endpoint + "/tts", "voice_mode":"tts", "chatter_fallback":false})
	var deadline := Time.get_ticks_msec() + 5000
	while not client.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
	check(client.can_stream(), "compatible router enables streaming without environment flags")
	for identity: String in ["stream_fixture", "wav_fixture", "corrupt_fixture"]:
		reset()
		check(client.synthesize_profile_live("Hello, Ponyville.", {"id":identity, "voice_mode":"tts"}, "neutral", received), "request accepted " + identity)
		await settle()
		check(callbacks == 1, "exactly one callback " + identity)
		if identity == "stream_fixture":
			check(early and source.done and source.error.is_empty(), "early PCM ownership and valid receipt")
		elif identity == "wav_fixture":
			check(result_path.ends_with(".wav") and result_error.is_empty(), "buffered WAV-compatible voice")
		else:
			check(early and not source.error.is_empty(), "bad late receipt fails the claimed stream")
	# Use the real director request and callback to hand live PCM to real Spike.
	var spike: Node3D = load("res://world/characters/spike/spike.gd").new()
	root.add_child(spike); spike.set_physics_process(false)
	var fixture: String = get_script().resource_path.get_base_dir().path_join("spike_director.gd")
	var director: Node = load(fixture).new(); root.add_child(director)
	director.tts = client
	director.characters = {"spike":{"node":spike}}
	director._current = "spike"; director.state = "rendering"
	director._pending_text = "Hello, Ponyville."
	check(director._synthesize_voice(director._pending_text, {"id":"spike", "voice_mode":"tts"},
		"neutral", Callable(director, "_on_tts")), "director accepts Spike speech request")
	await settle()
	check(director.received_live and director.state == "speaking" and is_instance_valid(spike._pcm_player),
		"real director hands Spike an early live stream")
	if is_instance_valid(spike._pcm_player):
		check(spike._pcm_player.source.claimed and spike._pcm_player.source.done and spike._pcm_player.source.error.is_empty(),
			"Spike owns the stream with a valid final receipt")
	spike.stop_speaking(); spike.queue_free(); director.queue_free(); await process_frame
	reset()
	client.synthesize_profile_live("A cancelled line.", {"id":"cancel_fixture", "voice_mode":"tts"}, "neutral", received)
	deadline = Time.get_ticks_msec() + 5000
	while source == null and Time.get_ticks_msec() < deadline: await process_frame
	check(source != null, "cancellation fixture claimed")
	var start := Time.get_ticks_msec(); client.cancel()
	check(Time.get_ticks_msec() - start < 100 and not client.busy and source.cancelled, "cancellation does not wait for upstream generation")
	reset()
	client.configure({"provider":"moss", "url":endpoint + "/legacy/tts", "voice_mode":"tts", "chatter_fallback":false})
	await create_timer(.15).timeout
	check(not client.can_stream(), "ordinary MOSS endpoint stays on original WAV path")
	check(client.synthesize("Legacy voice.", 31, "neutral", received), "legacy request accepted")
	await settle()
	check(callbacks == 1 and result_error.is_empty() and result_path.ends_with(".wav"), "legacy provider remains usable")
	reset()
	client.configure({"provider":"moss", "url":endpoint + "/warming/tts", "voice_mode":"auto", "chatter_fallback":false})
	await create_timer(.3).timeout
	check(not client.can_stream(), "warming router initially leaves original transport available")
	deadline = Time.get_ticks_msec() + 6000
	while not client.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
	check(client.can_stream(), "transient capability failure recovers without world reload")
	var lily := {"id":"lily_valley", "tts_speaker_id":-1, "voice_status":"temporary shared Cheerilee voice"}
	check(client.synthesize_profile_live("How lovely.", lily, "neutral", received), "background voice request accepted in auto mode")
	await settle()
	check(callbacks == 1 and early and source != null and source.done and source.error.is_empty(), "Lily uses identity-routed PCM despite missing numbered speaker")
	reset()
	client.configure({"provider":"moss", "url":endpoint + "/prebuffer/tts", "voice_mode":"tts", "chatter_fallback":false})
	deadline = Time.get_ticks_msec() + 5000
	while not client.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
	check(client.can_stream() and client._start_frames == 24000, "router's prebuffer_ms hint is read (1000 ms)")
	check(client.synthesize_profile_live("Far away.", {"id":"stream_fixture", "voice_mode":"tts"}, "neutral", received), "request accepted with a prebuffer hint")
	await settle()
	check(callbacks == 1 and source != null and source.start_frames == 24000 and source.done and source.error.is_empty(), "live utterance carries the prebuffer")
	client.queue_free(); await process_frame
	printerr("BREEZE_TRANSPORT_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
