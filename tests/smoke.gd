extends SceneTree
var failures := 0

func _initialize() -> void: run.call_deferred()

func check(value: bool, message: String) -> void:
	if not value: failures += 1
	printerr("PASS " if value else "FAIL ", message)

func run() -> void:
	var disabled := "--disabled" in OS.get_cmdline_user_args()
	var version: GDScript = load("res://world/debug/version.gd")
	var patch: Dictionary = version.patch_info()
	var effective := str(patch.get("version", version.base_version()))
	printerr("BREEZE_GAME_VERSION ", effective)
	check(effective == "0.3.1.2-maredev", "current cumulative game update is mounted")
	var mods := root.get_node("Mods")
	check(mods.is_active("breeze_tts_pny") == not disabled, "mod enabled state")
	var tts: Node = load("res://world/ai/tts_client.gd").new(); root.add_child(tts)
	check(tts.has_method("_has_router_endpoint") == not disabled, "routing extension installed by the standard loader")
	check(tts.has_method("can_stream"), "built-in streaming available with either mod state")
	var body: Node3D = load("res://world/characters/hybrid_mare/hybrid_mare.gd").new()
	check(body.has_method("supports_pcm_speech"), "built-in hybrid streaming available")
	body.free()
	var spike: Node3D = load("res://world/characters/spike/spike.gd").new()
	check(spike.has_method("supports_pcm_speech"), "built-in Spike streaming available")
	spike.free()
	var director: GDScript = load("res://world/ai/conversation_director.gd")
	check(director.can_instantiate(), "current director compiles")
	var inner_tts: Node = director.get_script_constant_map().TTS.new()
	check(inner_tts.has_method("_has_router_endpoint") == not disabled, "director captured the selected routing implementation")
	inner_tts.free()
	var chunks: RefCounted = load(get_script().resource_path.get_base_dir().path_join("speech_chunks.gd")).new()
	failures += chunks.run(disabled)
	var later := GDScript.new()
	later.source_code = 'extends RefCounted\nconst TTS := preload("res://world/ai/tts_client.gd")\n'
	check(later.reload() == OK, "later preload compiles")
	var later_tts: Node = later.get_script_constant_map().TTS.new()
	check(later_tts.has_method("_has_router_endpoint") == not disabled, "later preload retains the selected routing implementation")
	later_tts.free()
	var head: Node3D = load("res://world/characters/openpony/openpony_mare.gd").new()
	root.add_child(head)
	check(head.has_method("_speak_pcm"), "built-in OpenPony streaming available")
	for mesh in head.model.find_children("*", "MeshInstance3D", true, false):
		if mesh.name != "Eye" and not str(mesh.name).begins_with("Pupil"): continue
		printerr("EYE_MESH ", mesh.name, " visible=", mesh.visible)
		for i in mesh.mesh.get_surface_count():
			var material: Material = mesh.get_active_material(i)
			if material is ShaderMaterial:
				printerr("EYE_SHADER ", material.shader.resource_path)
				for param in material.shader.get_shader_uniform_list():
					var value: Variant = material.get_shader_parameter(param.name)
					printerr("UNIFORM ", param.name, "=", value.resource_path if value is Resource else value)
	var track: GDScript = load("res://world/characters/lip_sync_native.gd")
	check(track.available(), "game-provided native lip-sync library and model are available")
	if track.available():
		var analyzer: RefCounted = ClassDB.instantiate("TalkingAvatarAnalyzer")
		check(analyzer.begin(FileAccess.get_file_as_bytes(track.MODEL), 24000), "game-provided analyzer begins")
		var pcm := PackedByteArray(); pcm.resize(48000)
		for i in 24000: pcm.encode_s16(i * 2, int(sin(float(i) * TAU * 220.0 / 24000.0) * 12000.0))
		check(analyzer.push_pcm(pcm), "game-provided analyzer accepts PCM")
		analyzer.finish()
		var deadline := Time.get_ticks_msec() + 5000
		while not analyzer.status().done and Time.get_ticks_msec() < deadline: await create_timer(.01).timeout
		check(analyzer.status().done and str(analyzer.status().error).is_empty(), "game-provided analyzer finishes")
		check(not analyzer.poll().is_empty(), "game-provided analyzer emits cues")
		analyzer.cancel()
	if not disabled:
		for item: Dictionary in mods.list():
			if item.id == "breeze_tts_pny": check(not mods.switch(item.file, false), "switching the routing extension requires restart")
	head.queue_free(); tts.queue_free(); await process_frame
	printerr("BREEZE_MOD_SMOKE_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
