extends SceneTree
## Run through verify.py with the exported game and a disposable user directory.
var scan: GDScript
const PREFIX := "res://tests/replacement-compat/"
var failures := 0

func _initialize() -> void: run.call_deferred()

func check(value: bool, message: String) -> void:
	if not value: failures += 1
	printerr("PASS " if value else "FAIL ", message)

func run() -> void:
	scan = load("res://mods/breeze_tts_pny/runtime/install_extensions.gd")
	var cases := [
		{"name":"plain", "source":"extends RefCounted\nconst PCM_PLAYER = 1\n", "names":["PCM_PLAYER"], "compatible":false},
		{"name":"enum_comment", "source":"extends RefCounted\nenum { OTHER, # comment before the next member\n PCM_PLAYER }\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"enum_first_comment", "source":"extends RefCounted\nenum {\n # comment before the first member\n PCM_PLAYER, OTHER }\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"semicolon", "source":"extends RefCounted\nconst OTHER = 1; const PCM_PLAYER = 2\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"enum_after_semicolon", "source":"extends RefCounted\nconst OTHER = 1; enum { PCM_PLAYER }\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"annotation", "source":"extends Node\n@export var PCM_PLAYER: String = \"# ; }\"\n", "names":["PCM_PLAYER"], "compatible":false},
		{"name":"quoted_delimiters", "source":"extends RefCounted\nconst OTHER = \"escaped \\\"; # }\"; const PCM_PLAYER = 2\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"multiline_tail", "source":"extends RefCounted\nconst OTHER = \"\"\"documentation\n    more text\n    \"\"\"; const PCM_PLAYER = 2\n", "names":["OTHER", "PCM_PLAYER"], "compatible":false},
		{"name":"string_contents", "source":"var documentation = \"\"\"\nextends \"res://missing.gd\"\nconst PCM_PLAYER = 2\nenum { PCM_PLAYER }\n\"\"\"\n", "names":["documentation"], "compatible":true},
		{"name":"safe", "source":"extends RefCounted\nconst OTHER = \"; # PCM_PLAYER\" # const PCM_PLAYER = 2\nfunc local_only() -> void:\n\tvar PCM_PLAYER = 1\n\tprint(PCM_PLAYER)\n", "names":["OTHER", "local_only"], "compatible":true},
		{"name":"inline_locals", "source":"extends RefCounted\nfunc local_only(): var value = 1; var PCM_PLAYER = value; print(PCM_PLAYER)\n", "names":["local_only"], "compatible":true},
		{"name":"named_enum", "source":"extends RefCounted\nenum Other { PCM_PLAYER }\n", "names":["Other"], "compatible":true},
		{"name":"inherited", "source":"extends \"" + PREFIX + "enum_comment.gd\"\n", "names":[], "compatible":false},
	]
	var metadata: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(scan.ADDED))
	var folder := "user://replacement-compat"
	check(DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(folder)) == OK, "fixture directory")
	var pack := PCKPacker.new()
	check(pack.pck_start(folder.path_join("fixtures.pck")) == OK, "fixture pack starts")
	for fixture: Dictionary in cases:
		var target: String = PREFIX + fixture.name + ".gd"
		metadata[target] = {"added":["PCM_PLAYER"], "chain":[target]}
		var file: String = folder.path_join(fixture.name + ".gd")
		check(scan.write(file, fixture.source.to_utf8_buffer()), "write " + fixture.name)
		check(pack.add_file(target, ProjectSettings.globalize_path(file)) == OK, "pack " + fixture.name)
	var safe_extension := "extends \"" + PREFIX + "safe.gd\"\nconst PCM_PLAYER = 7\n"
	var bad_extension := "extends \"" + PREFIX + "enum_comment.gd\"\nconst PCM_PLAYER = 7\n"
	for name: String in ["safe_extension", "bad_extension"]:
		var source: String = safe_extension if name == "safe_extension" else bad_extension
		var file := folder.path_join(name + ".gd")
		check(scan.write(file, source.to_utf8_buffer()), "write " + name)
		check(pack.add_file(PREFIX + name + ".gd", ProjectSettings.globalize_path(file)) == OK, "pack " + name)
	var manifest := folder.path_join("added_members.json")
	check(scan.write(manifest, JSON.stringify(metadata).to_utf8_buffer()), "write fixture metadata")
	check(pack.add_file(scan.ADDED, ProjectSettings.globalize_path(manifest)) == OK, "pack fixture metadata")
	check(pack.flush() == OK, "fixture pack finishes")
	check(ProjectSettings.load_resource_pack(folder.path_join("fixtures.pck")), "fixture pack mounts")
	for fixture: Dictionary in cases:
		var names: Variant = scan.declared(fixture.source)
		var expected: Array = fixture.names.duplicate(); expected.sort()
		var actual: Array = names.keys() if names is Dictionary else []; actual.sort()
		check(names is Dictionary and actual == expected, "declared members: " + fixture.name)
		var target: String = PREFIX + fixture.name + ".gd"
		var script := load(target) as GDScript
		check(script != null and script.can_instantiate(), "fixture is valid GDScript: " + fixture.name)
		check(scan.replacement_compatible(target) == fixture.compatible, "replacement preflight: " + fixture.name)
	check(scan.declared("const BROKEN = \"unterminated") == null, "unterminated strings are refused")
	check(scan.declared("@unknown(nested(1)) var PCM_PLAYER = 1") == null, "unread annotation arguments are refused")
	var retained: int = scan.retained.size()
	check(not scan.install([PREFIX + "safe_extension.gd", PREFIX + "bad_extension.gd"]), "conflict refuses the whole installation")
	check(scan.retained.size() == retained, "conflict installs no earlier extensions")
	check(not load(PREFIX + "safe.gd").get_script_constant_map().has("PCM_PLAYER"), "safe target remains unchanged after refusal")
	printerr("BREEZE_REPLACEMENT_COMPAT_DONE failures=", failures)
	quit(0 if failures == 0 else 1)
