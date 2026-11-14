extends Node
class Head extends "res://world/characters/openpony/openpony_mare.gd":
	func _ready() -> void: set_process(false)
	func _process(delta: float) -> void: _unprofiled_process(delta)
const UTTERANCE = preload("res://world/ai/pcm_utterance.gd")
const TRACK = preload("res://world/characters/lip_sync_native.gd")
var head: Node3D
var voice: AudioStreamPlayer3D
var mouth: Object
var spike := false
var jaw_moved := false
var capture: AudioEffectCapture
var pcm: PackedByteArray
var work := ""
var started := -1
var first_sound := -1
var began := 0
var ended := 0
var errors := 0
var request_ms := 0
var seen := {}
var results: Array = []
var last_time := 0.0
var phase := ""
func check(ok: bool,message: String) -> void:
	if not ok:printerr("FAIL ",message);OS.kill(OS.get_process_id())
func _ready() -> void:
	work=OS.get_cmdline_user_args()[0]
	spike="--spike" in OS.get_cmdline_user_args()
	pcm=FileAccess.get_file_as_bytes(work+"/voice.pcm")
	get_viewport().audio_listener_enable_3d=true
	var world:=Node3D.new();add_child(world)
	var camera:=Camera3D.new();world.add_child(camera);camera.make_current()
	var listener:=AudioListener3D.new();world.add_child(listener);listener.make_current()
	if spike:
		head=load("res://world/characters/spike/spike.gd").new();world.add_child(head)
		head.set_physics_process(false)
		voice=head._voice;mouth=head.expressions
		check(head.supports_pcm_speech() and mouth.has_shapes() and head.tree.active,"actual game-provided Spike body, face and speech ready")
	else:
		head=Head.new();world.add_child(head)
		voice=AudioStreamPlayer3D.new();head.add_child(voice);head.voice=voice
		mouth=load("res://world/characters/openpony/pony_mouth.gd").new();head.mouth=mouth
	head.position.z=-1;voice.unit_size=6.0
	capture=AudioEffectCapture.new();capture.buffer_length=1.0;AudioServer.add_bus_effect(0,capture)
	head.speech_started.connect(func():began+=1;started=Time.get_ticks_msec()-request_ms)
	head.speech_finished.connect(func():ended+=1)
	head.speech_failed.connect(func(message):errors+=1;printerr("EXPECTED_SPEECH_FAILURE ",message))
	call_deferred("run")
func _process(_delta: float) -> void:
	if capture==null:return
	var samples:=capture.get_buffer(capture.get_frames_available())
	if request_ms>0 and first_sound<0:
		for sample in samples:
			if absf(sample.x)>.001 or absf(sample.y)>.001:first_sound=Time.get_ticks_msec()-request_ms;break
	if is_instance_valid(head) and head._speech_time>=0:
		seen[viseme()]=true
		if spike:
			var jaw: int=mouth.mesh.find_blend_shape_by_name("jaw_open")
			if jaw>=0 and mouth.mesh.get_blend_shape_value(jaw)>.1:jaw_moved=true
		if is_instance_valid(head._pcm_player):
			check(head._speech_time+0.001>=last_time,"audible clock moved backwards "+phase+" "+str(last_time)+" -> "+str(head._speech_time))
		last_time=head._speech_time
func viseme() -> String:
	return mouth.viseme if spike else mouth.current_viseme
func speak(path: String) -> void:
	if spike:head.say(path,"speech fixture")
	else:head.speak(path,"speech fixture")
func setup() -> RefCounted:
	head.stop_speaking();request_ms=Time.get_ticks_msec();started=-1;first_sound=-1;seen.clear();last_time=0
	capture.clear_buffer()
	var source=UTTERANCE.new();source.request_ms=request_ms
	speak(source.publish())
	return source
func wait_end(timeout_ms:=6000) -> void:
	var until:=Time.get_ticks_msec()+timeout_ms
	while head.is_speaking() or is_instance_valid(head._pcm_player):
		check(Time.get_ticks_msec()<until,"playback timeout")
		await get_tree().process_frame
func run() -> void:
	check(TRACK.available(),"prepare analyzer")
	await get_tree().create_timer(.1).timeout
	# Identical audio and arrival schedule, enabled vs disabled. No TTS/network calls.
	for enabled: bool in [true]:
		phase="normal "+str(enabled)
		var source=setup();var end_before:=ended
		var position:=0
		while position<pcm.size():
			await get_tree().create_timer(.08).timeout
			var end:=mini(position+3840,pcm.size());source.pcm.append_array(pcm.slice(position,end));position=end
			if position==pcm.size():source.done=true
		await wait_end()
		check(ended==end_before+1 and errors==0 and first_sound>=0,"normal stream completion")
		check(seen.size()>2 if enabled else seen.keys()==["X"],"mouth enable/disable behavior "+str(seen))
		if spike:check(jaw_moved,"Spike's real jaw blend shape moves during speech")
		results.append({"actor":"spike" if spike else "openpony","enabled":enabled,"play_ms":started,"first_mixer_ms":first_sound,"visemes":seen.keys()})
	phase="short"
	var source=setup();source.pcm=pcm.slice(14400,19200);source.done=true
	var expected:=ended+1;await wait_end();check(ended==expected,"short clip")
	phase="underrun"
	source=setup();source.pcm=pcm.slice(0,11520)
	await get_tree().create_timer(.7).timeout
	check(is_instance_valid(head._pcm_player) and head._pcm_player._underruns>0,"forced underrun")
	check(absf(head._speech_time-.24)<.025,"audible clock drains through pause "+str(head._speech_time))
	source.pcm.append_array(pcm.slice(11520,48000));source.done=true
	expected=ended+1;await wait_end();check(ended==expected,"rebuffer recovery")
	source=setup();source.pcm=pcm;await head.speech_started
	var old_track: RefCounted=head._pcm_player._track
	expected=ended;head.stop_speaking();await get_tree().create_timer(.1).timeout
	check(source.cancelled and not voice.playing and ended==expected and viseme()=="X" and (old_track == null or old_track._analyzer == null),"cancellation ownership")
	source=setup();source.pcm=pcm;await head.speech_started
	source.error="corrupt receipt";await wait_end()
	check(errors==1 and ended==expected,"partial corruption is failure, not completion")
	source=setup();source.pcm=pcm.slice(0,9600);source.done=true;await wait_end()
	check(ended==expected+1,"retry after error")
	# Immediate turn replacement: old producer cancelled; new utterance owns cues.
	source=setup();source.pcm=pcm;await head.speech_started
	var replacement=setup();replacement.pcm=pcm.slice(0,9600);replacement.done=true
	check(source.cancelled,"turn change cancels old producer")
	await wait_end()
	# A failed analyzer must leave audio independent and neutral.
	source=setup();source.pcm=pcm.slice(0,24000);source.done=true
	head._pcm_player._track.cancel();expected=ended+1;await wait_end()
	check(ended==expected and first_sound>=0 and seen.keys()==["X"],"audio survives analyzer failure")
	# Buffered WAV/prefetch path should use the same model without a full-analysis gate.
	for file: String in ["voice24.wav","voice48.wav"]:
		request_ms=Time.get_ticks_msec();first_sound=-1;seen.clear();last_time=0;capture.clear_buffer()
		speak(work+"/"+file)
		expected=ended+1;await wait_end()
		check(ended==expected and seen.size()>2 and first_sound>=0,"buffered WAV mouth motion "+file+" "+str(seen))
	# Cancelling before the first chunk must also release the producer/worker.
	source=setup();expected=ended
	old_track=head._pcm_player._track;head.stop_speaking()
	check(source.cancelled and ended==expected and (old_track == null or old_track._analyzer == null),"cancel before audio starts")
	if spike:
		# Scene teardown must cancel an active stream without reporting success.
		source=setup();source.pcm=pcm;await head.speech_started
		old_track=head._pcm_player._track;expected=ended
		head.queue_free();await get_tree().process_frame;await get_tree().process_frame
		check(source.cancelled and (old_track == null or old_track._analyzer == null) and ended==expected,"Spike scene exit cancels speech and analyzer")
	else:
		head.stop_speaking();mouth.free();head.mouth=null
	var f:=FileAccess.open(work+"/playback-results.json",FileAccess.WRITE);f.store_string(JSON.stringify(results,"\t"));f.close()
	printerr("TA_PLAYBACK_MIXER_SHORT_EOF_UNDERRUN_CANCEL_CORRUPTION_RETRY_TURN_WAV_PASS")
	get_tree().quit()
