extends "res://world/ai/tts_client.gd"
## Observe the choice of Ponese without depending on its audio renderer.
var chatter_calls := 0

func _start_chatter(_text: String, _profile: Dictionary, _emotion: String, done: Callable) -> bool:
	if busy: return false
	chatter_calls += 1
	busy = true
	_on_done = done
	_finish.call_deferred("fixture://ponese", "")
	return true
