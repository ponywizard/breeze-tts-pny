extends SceneTree
## Exercise the actual exported game's forced-Ponese profiles on both transports.
var failures := 0
var client: Node
var utterances: GDScript
var source: RefCounted
var callbacks := 0
var result_path := ""
var result_error := ""

func _initialize() -> void: run.call_deferred()

func check(ok: bool, message: String) -> void:
	if not ok: failures += 1
	printerr("PASS " if ok else "FAIL ", message)

func received(path: String, error: String) -> void:
	callbacks += 1; result_path = path; result_error = error
	if path.begins_with("pcm://"): source = utterances.take(path)

func reset() -> void:
	source = null; callbacks = 0; result_path = ""; result_error = ""
	client.chatter_calls = 0

func settle() -> void:
	var deadline := Time.get_ticks_msec() + 6000
	while client.busy and Time.get_ticks_msec() < deadline: await process_frame
	check(not client.busy and callbacks == 1, "request finishes with exactly one callback")

func check_ponese(profile: Dictionary, message: String) -> void:
	reset()
	check(client.synthesize_profile_live("Hello, Ponyville.", profile, "neutral", received), message + " accepted")
	await settle()
	check(client.chatter_calls == 1 and result_path == "fixture://ponese", message)

func run() -> void:
	var endpoint := "http://127.0.0.1:" + OS.get_cmdline_user_args()[0]
	root.get_node("Settings").set_value("voice/tts", true)
	utterances = load("res://world/ai/pcm_utterance.gd")
	client = load(get_script().resource_path.get_base_dir().path_join("profile_routing_client.gd")).new()
	root.add_child(client)
	var profiles: Array[Dictionary] = []
	var identities: Array[String] = []
	var directory := "res://world/characters/background/ai/"
	for file: String in DirAccess.get_files_at(directory):
		if not file.ends_with(".json"): continue
		var profile: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(directory + file))
		if profile.get("voice_mode") != "ponese": continue
		profiles.append(profile); identities.append(str(profile.id))
	check(identities.has("dinky_doo") and identities.has("silver_spoon"), "discover affected profiles from the packaged game")
	if profiles.is_empty(): quit(1); return
	printerr("BREEZE_FORCED_PONESE_PROFILES ", JSON.stringify(identities))

	for transport: String in ["wav", "stream"]:
		var url := endpoint + ("/profiles-wav/tts" if transport == "wav" else "/profiles/tts")
		client.configure({"provider":"moss", "url":url, "voice_mode":"auto", "chatter_fallback":false})
		if transport == "wav":
			await create_timer(.15).timeout
			check(not client.can_stream(), "missing streaming capabilities leave WAV transport selected")
		else:
			var deadline := Time.get_ticks_msec() + 5000
			while not client.can_stream() and Time.get_ticks_msec() < deadline: await process_frame
			check(client.can_stream(), "compatible router enables PCM transport")
		for profile: Dictionary in profiles:
			reset()
			var original := JSON.stringify(profile)
			check(client.synthesize_profile_live("Hello, Ponyville.", profile, "neutral", received), transport + " request accepted: " + str(profile.id))
			await settle()
			var audio_ok: bool = result_path.ends_with(".wav") if transport == "wav" else source != null and source.done and source.error.is_empty()
			check(audio_ok and result_error.is_empty() and client.chatter_calls == 0, transport + " bypasses profile Ponese: " + str(profile.id))
			check(JSON.stringify(profile) == original, "original profile is preserved: " + str(profile.id))
		client.voice_mode = "ponese"
		await check_ponese(profiles[0], transport + " respects global Ponese")
		client.voice_mode = "auto"
		root.get_node("Settings").set_value("voice/tts", false)
		await check_ponese(profiles[0], transport + " respects disabled TTS")
		root.get_node("Settings").set_value("voice/tts", true)

	client.configure({"provider":"moss", "url":endpoint + "/profiles-error/tts", "voice_mode":"auto", "chatter_fallback":true})
	await check_ponese(profiles[0], "failed TTS still falls back to Ponese")
	client.configure({"provider":"remote", "url":endpoint + "/legacy/tts", "voice_mode":"auto", "chatter_fallback":false})
	await check_ponese(profiles[0], "other providers retain stock profile selection")
	client.configure({"provider":"moss", "url":endpoint + "/legacy/speech", "voice_mode":"auto", "chatter_fallback":false})
	await check_ponese(profiles[0], "other endpoint formats retain stock profile selection")
	client.queue_free(); await process_frame
	printerr("BREEZE_PROFILE_ROUTING_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
