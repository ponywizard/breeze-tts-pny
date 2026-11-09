extends RefCounted
## One live utterance; claimed once by the actor, cancelled by either owner.
static var pending: Dictionary = {}
static var serial := 0
var pcm := PackedByteArray()
var done := false
var error := ""
var cancelled := false
var claimed := false
var request_ms := Time.get_ticks_msec()
var start_frames := 4800 # buffered before playback starts or resumes
var uri := ""
var cancel_transport := Callable()

func publish() -> String:
	serial += 1
	uri = "pcm://utterance/%d" % serial
	pending[uri] = self
	return uri

static func take(path: String) -> RefCounted:
	var value: RefCounted = pending.get(path)
	pending.erase(path)
	if value != null: value.claimed = true
	return value

func cancel() -> void:
	if cancelled: return
	cancelled = true
	pending.erase(uri)
	if cancel_transport.is_valid(): cancel_transport.call()

func release() -> void:
	pending.erase(uri)
	cancel_transport = Callable()
