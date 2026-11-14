extends SceneTree
## Real packaged client against the installed companion; isolated user data.
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
	var deadline := Time.get_ticks_msec() + 30000
	while client.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not client.busy, "transport finishes within deadline")

func run() -> void:
	var port := OS.get_cmdline_user_args()[0]
	root.get_node("Settings").set_value("voice/tts", true)
	utterances = load("res://world/ai/pcm_utterance.gd")
	client = load("res://world/ai/tts_client.gd").new(); root.add_child(client)
	client.configure({"provider":"moss", "url":"http://127.0.0.1:" + port + "/tts", "voice_mode":"tts", "chatter_fallback":false})
	var deadline := Time.get_ticks_msec() + 5000
	while not client.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
	check(client.can_stream(), "installed companion enables streaming")
	for identity: String in ["twilight_sparkle", "rainbow_dash", "pinkie_pie", "applejack", "fluttershy", "rarity", "angel_wings", "marble_pie"]:
		source = null; callbacks = 0; result_path = ""; result_error = ""; early = false
		check(client.synthesize_profile_live("Hello! It is good to see you again.", {"id":identity, "voice_mode":"tts"}, "neutral", received), "request accepted " + identity)
		await settle()
		check(callbacks == 1, "exactly one callback " + identity)
		check(early and source != null and source.done and source.error.is_empty(), "early PCM ownership and valid receipt " + identity)
	var spike: Node3D = load("res://world/characters/spike/spike.gd").new()
	root.add_child(spike); spike.set_physics_process(false)
	var fixture: String = get_script().resource_path.get_base_dir().path_join("spike_director.gd")
	var director: Node = load(fixture).new(); root.add_child(director)
	director.tts = client; director.characters = {"spike":{"node":spike}}
	director._current = "spike"; director.state = "rendering"
	director._pending_text = "Hello! It is good to see you again."
	check(director._synthesize_voice(director._pending_text, {"id":"spike", "voice_mode":"tts"},
		"neutral", Callable(director, "_on_tts")), "director accepts real Spike speech")
	await settle()
	check(director.received_live and director.state == "speaking" and is_instance_valid(spike._pcm_player), "director hands real speech to Spike's streaming player")
	if is_instance_valid(spike._pcm_player):
		check(spike._pcm_player.source.claimed and spike._pcm_player.source.done and spike._pcm_player.source.error.is_empty(), "Spike owns complete valid speech")
	spike.stop_speaking(); spike.queue_free(); director.queue_free(); client.queue_free(); await process_frame
	printerr("BREEZE_LIVE_SERVER_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
