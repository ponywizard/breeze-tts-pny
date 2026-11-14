extends RefCounted
## Run through the helper actually captured by the exported game's consumers.
var failures := 0

func check(ok: bool, message: String) -> void:
	if not ok: failures += 1
	printerr("PASS " if ok else "FAIL ", "speech grouping: ", message)

func run(_disabled: bool) -> int:
	var helper: Script = load("res://world/ai/speech_sentences.gd")
	var original: Script = helper
	helper.note_stream_client(-1, true)
	var short := "Oh! A cape! That sounds wonderful!"
	var expected: Array = [short]
	check(helper.audio_parts(short) == expected, "built-in streaming groups short reactions")
	var director: Script = load("res://world/ai/conversation_director.gd")
	var solo: Script = director.get_script_constant_map().SENTENCES
	var group: Script = load("res://world/ai/director_group.gd").get_script_constant_map().SENTENCES
	check(solo == helper and solo.audio_parts(short) == expected, "solo director captured the selected helper")
	check(group == helper and group.audio_parts(short) == expected, "group controller captured the selected helper")
	var later := GDScript.new()
	later.source_code = 'extends RefCounted\nconst SENTENCES := preload("res://world/ai/speech_sentences.gd")\n'
	var late_error := later.reload()
	var late: Script = later.get_script_constant_map().SENTENCES
	check(late_error == OK and late == helper and late.audio_parts(short) == expected, "later preloads retain the selected helper")

	var long_text := "Oh! " + "A fairly long sentence with every word preserved intact and clear. ".repeat(12)
	var parts: Array = helper.audio_parts(long_text)
	check(parts.size() == 6, "long contribution request count")
	check(" ".join(parts) == " ".join(original.split(long_text)), "all words and punctuation preserved")
	var long_sentence := "A " + "longer word sequence ".repeat(60) + "ends here."
	var bounded: Array = helper.audio_parts(long_sentence)
	check(bounded.all(func(part: String) -> bool: return part.length() <= 400), "long single sentence splits at word boundaries")
	check(" ".join(bounded) == long_sentence, "long single sentence survives intact")
	var long_word := "x".repeat(450)
	check(helper.audio_parts(long_word) == [long_word], "individual words are never split")
	check(helper.audio_parts("").is_empty() and helper.audio_parts("   ").is_empty(), "empty input stays silent")
	var punctuation := 'Dr. Hooves paid 3.14 bits. "Really?!" Yes… Of course.'
	check(helper.split(punctuation) == original.split(punctuation), "abbreviations, decimals, quotes and ellipses use the stock splitter")
	check(" ".join(helper.audio_parts(punctuation)) == " ".join(original.split(punctuation)), "punctuation survives grouping")
	var tiny := "Oh! " + "This very long opening sentence has plenty of words for everyone to hear and stays with the short reaction that introduces it even when the combined phrase passes the usual synthesis target."
	check(helper.audio_parts(tiny) == [tiny], "tiny opener stays with a sentence beyond the soft target")

	var beats := [
		{"speaker_id":"pinkie_pie", "listener_id":"rainbow_dash", "speech":long_text,
		"actions":[{"type":"look_at", "target":"rainbow_dash"}], "impression":{"mood":"happy"}},
		{"speaker_id":"rainbow_dash", "listener_id":"pinkie_pie", "speech":"Yeah! Looking good!",
		"actions":[{"type":"look_at", "target":"pinkie_pie"}]},
		{"speaker_id":"rainbow_dash", "listener_id":"player", "speech":"See you there.", "actions":[]},
		{"speaker_id":"pinkie_pie", "silent_travel":true, "speech":"", "actions":[{"type":"follow"}]}]
	var before := beats.duplicate(true)
	var expanded: Array = helper.expand(beats)
	check(expanded.size() == parts.size() + 3, "group expansion uses the same synthesis chunks")
	var pinkie: Array = expanded.slice(0, parts.size())
	check(pinkie.map(func(beat: Dictionary) -> String: return beat.speech) == parts, "expanded solo continuation text matches requests")
	check(pinkie[0].actions == beats[0].actions and pinkie.slice(1).all(func(beat: Dictionary) -> bool: return beat.actions.is_empty()), "actions occur once on the first clip")
	check(not pinkie[0].continuation and pinkie.slice(1).all(func(beat: Dictionary) -> bool: return beat.continuation), "continuation flags preserve the contribution boundary")
	check(pinkie[-1].impression == beats[0].impression and pinkie.slice(0, -1).all(func(beat: Dictionary) -> bool: return not beat.has("impression")), "impression occurs on the final clip")
	check(expanded[parts.size()].speaker_id == "rainbow_dash" and expanded[parts.size()].listener_id == "pinkie_pie" and expanded[parts.size()].actions == beats[1].actions, "speaker, listener and next speaker actions preserved")
	check(expanded[-2].speech == "See you there." and not expanded[-2].continuation, "separate contributions from the same speaker stay separate")
	check(expanded[-1] == beats[-1] and beats == before, "silent travel and input data remain intact")

	var tagged_beats := [{"speaker_id":"pinkie_pie", "speech":"[happy] " + long_text, "actions":[]}]
	var tagged: Array = helper.expand(tagged_beats)
	check(tagged.size() > 1 and tagged.all(func(beat: Dictionary) -> bool: return beat.speech.begins_with("[happy] ") and beat.speech.count("[happy]") == 1), "emotion tag carried once to each continuation")
	var tags: Script = load("res://world/ai/pony_dialogue_tags.gd")
	var raw := "[face:happy] The flowers along the road look beautiful in the sunshine this morning. [face:sad] I wish our friends could have joined us on this walk today, because they would have enjoyed seeing them too."
	var parsed: Dictionary = tags.parse(raw)
	var faces: Array = tags.sentence_faces(original.split(raw))
	var facial: Array = helper.expand([{"speaker_id":"pinkie_pie", "speech":parsed.speech, "actions":[], "face_map":faces, "face":parsed.face}])
	check(facial.size() == 2 and facial[0].face == "happy" and facial[1].face == "sad" and facial.all(func(beat: Dictionary) -> bool: return not beat.has("face_map")), "expression mapping advances across clips")
	var page_text := "A gently flowing line with many words to reveal in order. ".repeat(8)
	var paging_matches := true
	for revealed in page_text.length() + 1:
		if helper.display_page(page_text, revealed) != original.display_page(page_text, revealed): paging_matches = false
	check(paging_matches, "display paging unchanged at every reveal position")
	check(helper.timed_words(short, 2.5) == original.timed_words(short, 2.5), "word timing stays on the original helper")
	check(helper.complete_part("A complete sentence. An unfinished") == original.complete_part("A complete sentence. An unfinished"), "output-limit trimming unchanged")
	helper.note_stream_client(-1, false)
	check(helper.audio_parts(short) == ["Oh!", "A cape!", "That sounds wonderful!"], "stock splitting without streaming")
	return failures
