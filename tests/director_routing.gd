extends SceneTree
## Use the real director's _ready path, including clients captured by earlier mods.
var failures := 0
var director: Node
var source: RefCounted
var callbacks := 0
var result_path := ""
var result_error := ""
var utterances: GDScript
var initial_client_id := 0
var initial_routing := false
var render_finished := 0

func _initialize() -> void: run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok: failures += 1
	printerr("PASS " if ok else "FAIL ", message)

func _on_tts(path: String, error: String) -> void:
	callbacks += 1; result_path = path; result_error = error
	if path.begins_with("pcm://"): source = utterances.take(path)

func _observe_initial_client(node: Node) -> void:
	initial_client_id = node.tts.get_instance_id()
	initial_routing = node.tts.has_method("_has_router_endpoint")
	node.tts.live_render_finished.connect(_on_render_finished)

func _on_render_finished() -> void:
	render_finished += 1

func settle() -> void:
	var deadline := Time.get_ticks_msec() + 6000
	while director.tts.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not director.tts.busy and callbacks == 1, "director request finishes once")

func run() -> void:
	var endpoint := "http://127.0.0.1:" + OS.get_cmdline_user_args()[0]
	root.get_node("Settings").set_value("voice/tts", true)
	var file := FileAccess.open("user://ai_config.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"ai_usage":"talk", "debug":false,
		"llm":{"provider":"openai", "base_url":"", "model":""}, "stt":{"provider":"off"},
		"tts":{"provider":"moss", "url":endpoint + "/profiles-wav/tts", "voice_mode":"auto", "chatter_fallback":false}}))
	file.close()
	utterances = load("res://world/ai/pcm_utterance.gd")
	director = load("res://world/ai/conversation_director.gd").new()
	director.ready.connect(_observe_initial_client.bind(director), CONNECT_ONE_SHOT)
	root.add_child(director)
	director.set_process(false)
	check(director.tts.has_method("_has_router_endpoint"), "real director creates the Breeze routing client")
	if not director.tts.has_method("_has_router_endpoint"):
		director.queue_free(); await process_frame; quit(1); return
	check(director.tts.get_parent() == director and director.tts.name == "Tts", "routing client retains the director's lifecycle")
	var client: Node = director.tts
	root.get_node("Mods/breeze_tts_pny")._breeze_ensure_tts(director)
	check(director.tts == client, "client selection is idempotent")
	check(client.provider == "moss" and client.voice_mode == "auto" and client.url == endpoint + "/profiles-wav/tts" and not client.chatter_fallback, "director preserves configured voice settings")
	check(director.get_children().filter(func(child: Node) -> bool: return child.has_method("can_stream")).size() == 1, "director owns exactly one dialogue client")
	check(client.live_render_finished.is_connected(_on_render_finished), "earlier render-finished connections are preserved")
	var watch_party: bool = root.get_node("Mods").is_active("watch_party")
	printerr("BREEZE_DIRECTOR_WATCH_PARTY ", JSON.stringify(watch_party))
	check(initial_routing == not watch_party, "fixture exercises the earlier cached client only with Watch Party")
	check((client.get_instance_id() != initial_client_id) == watch_party, "replace a stale client and retain an already routed client")
	if watch_party:
		var inherited_watch_hook := false
		var script: Script = director.get_script()
		while script != null:
			if script.resource_path.contains("watch_party"): inherited_watch_hook = true
			script = script.get_base_script()
		check(inherited_watch_hook, "Watch Party director hook remains in the inheritance chain")
	var actor: Node3D = load("res://world/characters/spike/spike.gd").new()
	root.add_child(actor); actor.set_physics_process(false)
	var directory := "res://world/characters/background/ai/"
	var profiles: Array[Dictionary] = []
	var identities: Array[String] = []
	for name: String in DirAccess.get_files_at(directory):
		if not name.ends_with(".json"): continue
		var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + name))
		if profile.get("voice_mode") != "ponese": continue
		profiles.append(profile); identities.append(str(profile.id))
		director.characters[profile.id] = {"node":actor, "profile":profile}
	check(identities.has("silver_spoon") and identities.has("ruby_pinch") and identities.has("archer"), "real director covers reported Ponese profiles")
	printerr("BREEZE_DIRECTOR_PROFILES ", JSON.stringify(identities))
	for transport: String in ["wav", "stream"]:
		var section: Dictionary = director.config.section("tts").duplicate()
		section.url = endpoint + ("/profiles-wav/tts" if transport == "wav" else "/profiles/tts")
		director.tts.configure(section)
		if transport == "wav":
			await create_timer(.15).timeout
			check(not director.tts.can_stream(), "director retains WAV without stream capabilities")
		else:
			var deadline := Time.get_ticks_msec() + 5000
			while not director.tts.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
			check(director.tts.can_stream(), "director detects the streaming router")
		for profile: Dictionary in profiles:
			source = null; callbacks = 0; result_path = ""; result_error = ""
			var original := JSON.stringify(profile)
			check(director._synthesize_voice("Hello, Ponyville.", profile, "neutral", _on_tts), "real director accepts " + transport + ": " + str(profile.id))
			await settle()
			var audio_ok: bool = result_path.ends_with(".wav") and not result_path.get_file().begins_with("chatter_") if transport == "wav" else source != null and source.done and source.error.is_empty()
			check(audio_ok and result_error.is_empty(), "real director routes " + transport + ": " + str(profile.id))
			check(JSON.stringify(profile) == original, "director preserves profile: " + str(profile.id))
	await process_frame
	check(render_finished == profiles.size(), "preserved signal receives every completed live request")
	actor.queue_free(); director.queue_free(); await process_frame
	printerr("BREEZE_DIRECTOR_ROUTING_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
