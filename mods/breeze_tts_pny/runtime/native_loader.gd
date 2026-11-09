extends RefCounted
## A .pck cannot dlopen a packed library. Extract only this mod's hash-checked
## binary into user://, then load it through a local GDExtension descriptor.
const ROOT := "res://mods/breeze_tts_pny/native/"
static var attempted := false
static var loaded := false

static func platform_key() -> String:
	if not OS.has_feature("x86_64"): return ""
	return {"Linux":"linux.x86_64", "Windows":"windows.x86_64"}.get(OS.get_name(), "")

static var _supported := -1 # unknown; the packed defaults can't change while the game runs

static func supported() -> bool:
	if _supported < 0:
		var defaults: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://mods/breeze_tts_pny/defaults.json"))
		_supported = int(defaults is Dictionary and defaults.get("lip_sync", false) and not platform_key().is_empty() and ProjectSettings.get_setting("application/config/version", "") == "0.3.0-maredev")
	return _supported == 1

static func prepare() -> bool:
	if attempted: return loaded
	attempted = true
	if not supported():
		push_warning("[breeze-tts-pny] This build supports Linux/Windows x86_64 on 0.3.0; keeping the game's normal speech.")
		return false
	if ClassDB.class_exists("TalkingAvatarAnalyzer"):
		loaded = true
		return true
	var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(ROOT + "manifest.json"))
	if not manifest is Dictionary: return false
	var key := platform_key()
	var library := "talking_avatar.dll" if key == "windows.x86_64" else "libtalking_avatar.so"
	var expected := "talking_avatar.windows.x86_64.dll.bin" if key == "windows.x86_64" else "libtalking_avatar.linux.x86_64.so.bin"
	var entry: Dictionary = manifest.get(key, {})
	var digest: String = entry.get("sha256", "")
	var name: String = entry.get("file", "")
	if not RegEx.create_from_string("^[0-9a-f]{64}$").search(digest): return false
	if name != expected: return false
	var packed := ROOT + name
	if FileAccess.get_sha256(packed) != digest: return false
	var directory := "user://mods/data/breeze_tts_pny/native/" + digest
	if DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(directory)) != OK: return false
	var binary := directory + "/" + library
	if FileAccess.get_sha256(binary) != digest:
		var file := FileAccess.open(binary + ".tmp", FileAccess.WRITE)
		if file == null: return false
		file.store_buffer(FileAccess.get_file_as_bytes(packed)); file.close()
		if FileAccess.get_sha256(binary + ".tmp") != digest: return false
		if DirAccess.rename_absolute(ProjectSettings.globalize_path(binary + ".tmp"), ProjectSettings.globalize_path(binary)) != OK: return false
	var descriptor := directory + "/talking_avatar.gdextension"
	var config := ConfigFile.new()
	config.set_value("configuration", "entry_symbol", "talking_avatar_library_init")
	config.set_value("configuration", "compatibility_minimum", "4.5")
	config.set_value("configuration", "reloadable", false)
	config.set_value("libraries", key, ProjectSettings.globalize_path(binary))
	if config.save(descriptor) != OK: return false
	var result := GDExtensionManager.load_extension(ProjectSettings.globalize_path(descriptor))
	loaded = result in [GDExtensionManager.LOAD_STATUS_OK, GDExtensionManager.LOAD_STATUS_ALREADY_LOADED] and ClassDB.class_exists("TalkingAvatarAnalyzer")
	if not loaded: push_warning("[breeze-tts-pny] Lip-sync library unavailable; streaming audio remains usable.")
	return loaded
