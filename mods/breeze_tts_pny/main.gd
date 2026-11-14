extends Node
## Earlier mods can preload the director and its TTS constant before Breeze extends TTS.
## Use the game's ready-node hook to repair that client without replacing their director.
func _ready() -> void:
	get_parent().on_node("group:conversation_director", _breeze_ensure_tts)

func _breeze_ensure_tts(director: Node) -> void:
	var previous: Node = director.get("tts")
	if not is_instance_valid(previous) or previous.has_method("_has_router_endpoint"): return
	var selected: GDScript = load("res://world/ai/tts_client.gd")
	var replacement: Node = selected.new()
	replacement.name = previous.name
	replacement.output_dir = previous.output_dir
	replacement.configure(director.config.section("tts"))
	replacement.debug = previous.debug
	for connection: Dictionary in previous.get_signal_connection_list("live_render_finished"):
		replacement.connect("live_render_finished", connection.callable, connection.flags)
	director.tts = replacement
	previous.cancel()
	director.remove_child(previous)
	previous.queue_free()
	director.add_child(replacement)
	print("[breeze-tts-pny] Updated the director's cached TTS client; character routing enabled.")
