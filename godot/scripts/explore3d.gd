extends Node3D
## PaleoSphere 3D explorer: walk the simulated world in first person.
## The Python server still owns the simulation (docs/protocol.md); this scene renders snapshots
## in 3D and moves the explorer-mode researcher (explorer_move / scan / report commands).
##   godot --path godot res://scenes/explore3d.tscn
##   godot --path godot res://scenes/explore3d.tscn -- --server=ws://host:port/ws/sim
##   godot --headless --path godot res://scenes/explore3d.tscn -- --smoke [--screenshot=a.png]
## The 2D observer stays the project's main scene (res://scenes/main.tscn).

const S := SimWorld3D.S
const WALK := 4.5  # m/s
const RUN := 10.0
const EYE := 1.7
const MOUSE_SENS := 0.0025
const SEND_INTERVAL := 0.1
const DEFAULT_TPS := 5.0

var client: SimClient
var world: SimWorld3D
var player: Node3D
var camera: Camera3D
var font: Font
var hud: CanvasLayer
var status_label: Label

var last_snapshot: Dictionary = {}
var policies: Array = []
var herbivore_policies: Array = []
var world_seed := 10000
var tps := DEFAULT_TPS
var paused := false
var _pitch := -0.08
var _since_send := 0.0
var _moved := false
var _needs_spawn := true
var _done_wait := 0.0

var smoke_mode := false
var screenshot_path := ""
var _smoke_deadline := 120.0
var _smoke_done := false


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	smoke_mode = "--smoke" in args
	for arg in args:
		if arg.begins_with("--screenshot="):
			screenshot_path = arg.trim_prefix("--screenshot=")
			smoke_mode = true
		elif arg.begins_with("--seed="):
			world_seed = int(arg.trim_prefix("--seed="))
	font = SystemFont.new()
	font.font_names = PackedStringArray(
		["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "sans-serif"])

	world = SimWorld3D.new()
	world.font = font
	add_child(world)
	player = Node3D.new()
	player.position = Vector3(64, 0, 64)
	add_child(player)
	camera = Camera3D.new()
	camera.position.y = EYE
	camera.fov = 72.0
	camera.far = 600.0
	player.add_child(camera)
	camera.make_current()
	_build_hud()

	client = SimClient.new()
	for arg in args:
		if arg.begins_with("--server="):
			client.url = arg.trim_prefix("--server=")
	add_child(client)
	client.connected.connect(func() -> void: _set_status("연결됨"))
	client.disconnected.connect(func() -> void: _set_status("서버 연결 끊김, 재연결 중…  (scripts\\dev.ps1)"))
	client.hello_received.connect(_on_hello)
	client.snapshot_received.connect(_on_snapshot)
	client.error_received.connect(func(m: String) -> void: _set_status("서버 오류: " + m))
	client.connect_to_server()
	_set_status("서버 연결을 기다리는 중…  (scripts\\dev.ps1 로 실행하면 서버도 함께 켜집니다)")


func _build_hud() -> void:
	hud = CanvasLayer.new()
	add_child(hud)
	var th := Theme.new()
	th.default_font = font
	th.default_font_size = 16
	var root := Control.new()
	root.theme = th
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(root)
	status_label = Label.new()
	status_label.position = Vector2(16, 12)
	status_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	status_label.add_theme_constant_override("outline_size", 6)
	root.add_child(status_label)


func _set_status(text: String) -> void:
	status_label.text = text


# ------------------------------------------------------------------------- server
func _on_hello(p: Array, _maps: Array, herd: Array) -> void:
	policies = p
	herbivore_policies = herd
	_start()


func _start() -> void:
	_needs_spawn = true
	_done_wait = 0.0
	paused = false
	client.send_command({
		"type": "start",
		"seed": world_seed,
		"map": "ecosystem",
		"predator_policy": "ppo" if "ppo" in policies else String(policies[0]),
		"herbivore_policy": "herd-v1" if "herd-v1" in herbivore_policies else "rule",
		"explorer": true,
		"ticks_per_second": 60.0 if smoke_mode else tps,
	})


func _on_snapshot(s: Dictionary) -> void:
	last_snapshot = s
	world.set_snapshot(s)
	var ex: Variant = s.get("explorer")
	if _needs_spawn and ex != null:
		_needs_spawn = false
		player.position = Vector3(float(ex["position"][0]) * S, 0, float(ex["position"][1]) * S)
	var m: Dictionary = s["metrics"]
	_set_status("tick %d  ·  %s  ·  초식 %d  ·  포식자 %d  ·  사냥 %d  ·  출생 %d" % [
		int(s["tick"]), "밤" if s["is_night"] else "낮", int(m["herbivores_alive"]),
		int(m.get("predators_alive", 1)), int(m["kills"]), int(m.get("births", 0))])
	if smoke_mode and not _smoke_done and int(s["tick"]) >= 300:
		_finish_smoke()


# --------------------------------------------------------------------------- input
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		player.rotation.y -= event.relative.x * MOUSE_SENS
		_pitch = clampf(_pitch - event.relative.y * MOUSE_SENS, -1.4, 1.4)
		camera.rotation.x = _pitch
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _process(delta: float) -> void:
	_walk(delta)
	if smoke_mode and not _smoke_done:
		_smoke_deadline -= delta
		if _smoke_deadline <= 0.0:
			print("3D SMOKE FAIL: no tick 300 (last=%s)" % last_snapshot.get("tick", "none"))
			get_tree().quit(1)


func _walk(delta: float) -> void:
	var dir := Vector3.ZERO
	if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
		dir.z -= 1
	if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
		dir.z += 1
	if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
		dir.x -= 1
	if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
		dir.x += 1
	if dir != Vector3.ZERO:
		var speed := RUN if Input.is_key_pressed(KEY_SHIFT) else WALK
		var step := player.global_transform.basis * dir.normalized() * speed * delta
		step.y = 0.0
		_move_to(player.position + step)
	_since_send += delta
	if _moved and _since_send >= SEND_INTERVAL:
		_since_send = 0.0
		_moved = false
		client.send_command({"type": "explorer_move", "x": player.position.x / S,
			"z": player.position.z / S})


func _move_to(p: Vector3) -> void:
	var size := world.map_size * S
	var flat := Vector2(clampf(p.x, 0.0, size), clampf(p.z, 0.0, size))
	for b in world.blockers:  # walk around rocks and ponds
		var c: Vector2 = b[0]
		var r := float(b[1]) + 0.5
		if flat.distance_to(c) < r:
			flat = c + (flat - c).normalized() * r
	player.position = Vector3(flat.x, 0, flat.y)
	_moved = true


# --------------------------------------------------------------------------- smoke
func _finish_smoke() -> void:
	_smoke_done = true
	client.send_command({"type": "pause"})  # hold the frame still for the screenshot
	_look_at_herd()
	if screenshot_path != "":
		for i in 30:  # let models settle after the jump
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(screenshot_path)
	print("3D SMOKE OK tick=%d dinos=%d models=%d plants=%d" % [
		int(last_snapshot["tick"]), last_snapshot["dinos"].size(), world.dinos.size(),
		last_snapshot["plants"].size()])
	get_tree().quit(0)


func _look_at_herd() -> void:
	"""Smoke runs: stand near a live dino (`--closeup=<species>:<metres>`, default the herd
	from 22 m), side-on, so the screenshot shows the models."""
	var species := "herbivore"
	var dist := 22.0
	var single := false
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--closeup="):
			var parts := arg.trim_prefix("--closeup=").split(":")
			species = parts[0]
			dist = float(parts[1]) if parts.size() > 1 else 9.0
			single = true
	var focus := Vector3.ZERO
	var n := 0
	var heading := Vector3.FORWARD
	for id in world.states:
		var d: Dictionary = world.states[id]
		if d["alive"] and d["species"] == species:
			focus += world.display_position(id)
			heading = -world.dinos[id].global_transform.basis.z
			n += 1
			if single:
				break
	if n == 0:
		return
	focus /= n
	var side := heading.cross(Vector3.UP).normalized()
	if not single:
		var centre := Vector3(world.map_size * S * 0.5, 0, world.map_size * S * 0.5)
		side = (centre - focus).normalized() if centre.distance_to(focus) > 1.0 else Vector3.BACK
	player.position = focus + side * dist  # bypass blockers: framing only
	player.look_at(Vector3(focus.x, 0, focus.z), Vector3.UP)
	player.rotation.x = 0.0
	player.rotation.z = 0.0
	_pitch = -0.05
	camera.rotation.x = _pitch
