extends RefCounted
## The 0.3.0 exported mod loader copies .gdc bases without their .gd remaps.
## Install the same subclasses from the entry node, with aliases confined to
## this mod's own cache. No game code is redistributed or patched on disk.
const CACHE := "user://mods/data/breeze_tts_pny/script-bases"
static var retained: Array[Script] = []

static func install(paths: Array) -> bool:
	if ProjectSettings.get_setting("application/config/version", "") != "0.3.0-maredev":
		push_warning("[breeze-tts-pny] This preview requires Home Equestria 0.3.0-maredev.")
		return false
	if DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(CACHE)) != OK: return false
	# A source replacement from the old development packs must not become our
	# parent: those packs already declare members this preview adds. Another
	# mod's replacement (a full copy of the game script with its own changes)
	# may, when it declares none of them.
	if OS.has_feature("template"):
		for path: String in paths:
			var text := FileAccess.get_file_as_string(path)
			var declaration := RegEx.create_from_string('(?m)^extends "(res://[^"\\n]+)"').search(text)
			if declaration == null: return false
			var target := declaration.get_string(1)
			if FileAccess.file_exists(target) and not replacement_compatible(target):
				push_warning("[breeze-tts-pny] A loose/replacement game script conflicts with this preview: " + target + ". Use an unmodified installed game directory.")
				return false
	var targets: Array[String] = []
	for path: String in paths:
		var text := FileAccess.get_file_as_string(path)
		var matched := RegEx.create_from_string('(?m)^extends "(res://[^"\\n]+)"').search(text)
		if matched == null: return false
		var target := matched.get_string(1)
		var base := load(target) as GDScript
		if base == null or not base.can_instantiate(): return false
		var stem := CACHE.path_join(str(targets.size()) + "_" + target.get_file().get_basename())
		var base_path := stem + ".gd"
		if not base.source_code.is_empty():
			DirAccess.remove_absolute(ProjectSettings.globalize_path(base_path + ".remap"))
			var source := RegEx.create_from_string("(?m)^class_name\\s+\\w+\\s*").sub(base.source_code, "", true)
			if not write(base_path, source.to_utf8_buffer()): return false
		else:
			DirAccess.remove_absolute(ProjectSettings.globalize_path(base_path))
			if base.get_global_name() != &"": return false
			var bytes := FileAccess.get_file_as_bytes(target.get_basename() + ".gdc")
			if bytes.is_empty() or not write(stem + ".gdc", bytes): return false
			var remap := ConfigFile.new(); remap.set_value("remap", "path", stem + ".gdc")
			if remap.save(base_path + ".remap") != OK: return false
		var base_copy := load(base_path) as GDScript
		if base_copy == null or not base_copy.can_instantiate(): return false
		retained.append(base_copy)
		text = text.replace('extends "' + target + '"', 'extends "' + base_path + '"')
		var extension_path := stem + "_extension.gd"
		if not write(extension_path, text.to_utf8_buffer()): return false
		var extension := load(extension_path) as GDScript
		if extension == null or not extension.can_instantiate(): return false
		# Move the original off the public path too: later source preloads can
		# otherwise recover it from Godot's script cache instead of our subclass.
		base.take_over_path(stem + "_original.gd")
		extension.take_over_path(target)
		if extension.reload() != OK: return false
		retained.append(extension)
		targets.append(target)
		print("[breeze-tts-pny] extends ", target)
	return true

## True when the replacement at target, with the scripts it extends, declares
## nothing this preview adds to the shipped script. build.py lists those members
## and the shipped script's own ancestors from the matching game source;
## compiling the original here would capture its preloads before installation.
## Anything the scan cannot follow or read is refused.
const ADDED := "res://mods/breeze_tts_pny/added_members.json"
const EXTENDS_LINE := "(?m)^(?:class_name\\s+\\w+\\s+)?extends\\b[^\\n]*"
const EXTENDS_TARGET := "^(?:class_name\\s+\\w+\\s+)?extends\\s+(\"(res://[^\"]+)\"|'(res://[^']+)'|([A-Za-z_]\\w*))\\s*(?:#.*)?$"
## One leading annotation, with arguments that may hold quoted strings (escapes included).
const ANNOTATION := "^@[A-Za-z_]\\w*(?:\\((?:[^()\"'\\n]|\"(?:[^\"\\\\\\n]|\\\\.)*\"|'(?:[^'\\\\\\n]|\\\\.)*')*\\))?\\s*"

static func replacement_compatible(target: String) -> bool:
	var lists: Variant = JSON.parse_string(FileAccess.get_file_as_string(ADDED)) if FileAccess.file_exists(ADDED) else null
	var info: Variant = lists.get(target) if lists is Dictionary else null
	if not info is Dictionary or not info.get("added") is Array or not info.get("chain") is Array: return false
	var names := {}
	var path := target
	var seen := {}
	while not seen.has(path):
		seen[path] = true
		if not FileAccess.file_exists(path):
			# A compiled game script: fine when it is one the shipped script inherits.
			return path != target and info.chain.has(path) and none_added(names, info.added)
		var source := FileAccess.get_file_as_string(path)
		var layout: Variant = code_layout(source)
		if layout == null: return false
		var scanned: Variant = declared_layout(layout)
		if scanned == null: return false
		names.merge(scanned)
		var line := RegEx.create_from_string(EXTENDS_LINE).search(layout)
		if line == null: return none_added(names, info.added) # implicitly RefCounted
		var parent := RegEx.create_from_string(EXTENDS_TARGET).search(source.substr(line.get_start(), line.get_end() - line.get_start()).strip_edges())
		if parent == null: return false # a relative path, an inner class or another form
		if parent.get_string(4) != "":
			# An engine class ends the chain; a global script class is not followed.
			return ClassDB.class_exists(parent.get_string(4)) and none_added(names, info.added)
		path = parent.get_string(2) + parent.get_string(3)
	return false # an extends cycle

static func none_added(names: Dictionary, added: Array) -> bool:
	for name: Variant in added:
		if names.has(str(name)): return false
	return true

## Top-level member names of a script, or null for a declaration form it cannot read.
static func declared(source: String) -> Variant:
	var layout: Variant = code_layout(source)
	return declared_layout(layout) if layout != null else null

## Mask comments and strings without moving character offsets. Newlines inside
## strings are masked too, keeping a following semicolon on the same logical
## line. A tooltip must not become a declaration or an inheritance directive.
static func code_layout(source: String) -> Variant:
	var result := PackedStringArray()
	var quote := ""
	var comment := false
	var index := 0
	while index < source.length():
		var character := source[index]
		if comment:
			comment = character != "\n"
			result.append(" " if comment else "\n")
			index += 1
		elif not quote.is_empty():
			if source.substr(index, quote.length()) == quote:
				result.append(" ".repeat(quote.length()))
				index += quote.length()
				quote = ""
			elif character == "\\":
				result.append(" ")
				index += 1
				if index >= source.length(): return null
				result.append(" ")
				index += 1
			else:
				if character == "\n" and quote.length() == 1: return null
				result.append(" ")
				index += 1
		elif character == "#":
			comment = true
			result.append(" ")
			index += 1
		elif character == "\"" or character == "'":
			quote = character.repeat(3) if source.substr(index, 3) == character.repeat(3) else character
			result.append(" ".repeat(quote.length()))
			index += quote.length()
		else:
			result.append(character)
			index += 1
	return "".join(result) if quote.is_empty() else null

static func declared_layout(layout: String) -> Variant:
	var names := {}
	var annotation := RegEx.create_from_string(ANNOTATION)
	var declaration := RegEx.create_from_string("^(?:static\\s+)?(func|var|const|signal|enum|class)\\s+([A-Za-z_]\\w*)")
	var unread := RegEx.create_from_string("^(?:static\\s+)?(?:func|var|const|signal|class)\\b")
	for line: String in layout.split("\n"):
		if line.begins_with(" ") or line.begins_with("\t"): continue
		for statement: String in line.split(";"):
			var rest := statement.strip_edges()
			var leading := annotation.search(rest)
			while leading != null and leading.get_end() > 0:
				rest = rest.substr(leading.get_end())
				leading = annotation.search(rest)
			var found := declaration.search(rest)
			if found != null:
				names[found.get_string(2)] = true
				# Later statements on a function/class header belong to its body.
				if found.get_string(1) in ["func", "class"]: break
			# An annotation with an argument form we cannot read is refused.
			elif statement.strip_edges().begins_with("@") and not rest.strip_edges().is_empty(): return null
			elif unread.search(rest) != null: return null
	# Values of unnamed enums are members too.
	for block: RegExMatch in RegEx.create_from_string("(?m)(?:^enum|;[\\t ]*enum)\\s*\\{([^}]*)\\}").search_all(layout):
		for value: String in block.get_string(1).split(","):
			var value_name := RegEx.create_from_string("^\\s*([A-Za-z_]\\w*)").search(value)
			if value_name != null: names[value_name.get_string(1)] = true
	return names

static func write(path: String, data: PackedByteArray) -> bool:
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null: return false
	file.store_buffer(data); file.close()
	return true
