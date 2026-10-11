extends Node3D
## PaleoSphere 3D explorer: walk the simulated world in first person.
## The Python server still owns the simulation (docs/protocol.md); this scene renders snapshots
## in 3D and moves the explorer-mode researcher (explorer_move / scan / report commands).
##   godot --path godot res://scenes/explore3d.tscn
##   godot --path godot res://scenes/explore3d.tscn -- --server=ws://host:port/ws/sim
##   godot --headless --path godot res://scenes/explore3d.tscn -- --smoke [--screenshot=a.png]
##       [--report-out=r.md] [--closeup=predator:8] [--follow]   # autopilot walk, scans, report
## The 2D observer stays the project's main scene (res://scenes/main.tscn).
## Keys: WASD walk · Shift run · mouse look · E scan · R report · F follow the dino in the
## crosshair · M map · Space pause · [ ] speed · N new world · Esc frees the mouse.

const S := SimWorld3D.S
const WALK := 4.5  # m/s
const RUN := 10.0
const EYE := 1.7
const MOUSE_SENS := 0.0025
const SEND_INTERVAL := 0.1
const SPEEDS := [1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0]  # ticks per second
const LOOK_RANGE := 90.0  # metres
const LABEL_SEC := 5.0  # scanned dinos keep their label this long
const FOLLOW_DIST := 11.0
const FOLLOW_HEIGHT := 4.5
const BAR_COLORS := {
	"health": Color("4f9a53"), "energy": Color("d6a03a"),
	"hunger": Color("c4472f"), "thirst": Color("5aa0c8"),
}
const BAR_NAMES := {"health": "체력", "energy": "에너지", "hunger": "배고픔", "thirst": "갈증"}
const CAUSES := {
	"predation": "사냥당함", "starvation": "굶주림", "dehydration": "탈수",
	"exhaustion": "탈진", "old_age": "노화",
}
const HELP := "WASD 이동 · Shift 달리기 · 마우스 둘러보기 · E 스캔 · R 보고서 · F 따라가기 · M 지도 · " \
	+ "Space 일시정지 · [ ] 속도 · N 새 세계 · Esc 마우스 해제"

var client: SimClient
var world: SimWorld3D
var player: Node3D
var camera: Camera3D
var explorer: Explorer  # minimap state (position, radii, scan highlight)
var font: Font

var status_label: Label
var hint_label: Label
var info_panel: PanelContainer
var info_title: Label
var info_detail: Label
var bars: Dictionary = {}
var toast_box: VBoxContainer
var map_panel: PanelContainer
var minimap: WorldView
var report_dialog: AcceptDialog
var report_text: TextEdit
var scan_ring: MeshInstance3D
var _ring_mat: StandardMaterial3D
var _ring_age := 99.0
var _ring_radius := 24.0

var last_snapshot: Dictionary = {}
var policies: Array = []
var herbivore_policies: Array = []
var world_seed := 10000
var speed_index := 3
var paused := false
var target_id := ""
var follow_id := ""
var _scanned: Dictionary = {}  # agent_id -> seconds since scan
var _pitch := -0.08
var _since_send := 0.0
var _moved := false
var _needs_spawn := true
var _done_wait := 0.0

var smoke_mode := false
var screenshot_path := ""
var _report_out := ""
var _smoke_deadline := 150.0
var _smoke_done := false
var _next_scan_tick := 40
var _report_requested := false
var _scans := 0


func _ready() -> void:
	var args := OS.get_cmdline_user_args()
	smoke_mode = "--smoke" in args
	for arg in args:
		if arg.begins_with("--screenshot="):
			screenshot_path = arg.trim_prefix("--screenshot=")
			smoke_mode = true
		elif arg.begins_with("--seed="):
			world_seed = int(arg.trim_prefix("--seed="))
		elif arg.begins_with("--report-out="):
			_report_out = arg.trim_prefix("--report-out=")
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
	explorer = Explorer.new()
	add_child(explorer)
	_build_scan_ring()
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
	client.error_received.connect(func(m: String) -> void: _toast("서버 오류: " + m, Color("e07a5f")))
	client.scan_received.connect(_on_scan)
	client.report_received.connect(_on_report)
	client.connect_to_server()
	_set_status("서버 연결을 기다리는 중…  (scripts\\dev.ps1 로 실행하면 서버도 함께 켜집니다)")


# ---------------------------------------------------------------------------- HUD
func _build_hud() -> void:
	var hud := CanvasLayer.new()
	add_child(hud)
	var th := Theme.new()
	th.default_font = font
	th.default_font_size = 16
	var root := Control.new()
	root.theme = th
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	hud.add_child(root)

	status_label = _outlined(16)
	status_label.position = Vector2(16, 12)
	root.add_child(status_label)

	var help := _outlined(13)
	help.text = HELP
	_place(help, Control.PRESET_BOTTOM_LEFT, Vector2(16, -12))
	help.modulate = Color(1, 1, 1, 0.85)
	root.add_child(help)

	hint_label = _outlined(20)
	_place(hint_label, Control.PRESET_CENTER, Vector2(0, 48))
	hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	root.add_child(hint_label)

	var cross := Label.new()
	cross.text = "+"
	cross.add_theme_font_size_override("font_size", 22)
	_place(cross, Control.PRESET_CENTER, Vector2.ZERO)
	cross.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	cross.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	cross.grow_horizontal = Control.GROW_DIRECTION_BOTH
	cross.grow_vertical = Control.GROW_DIRECTION_BOTH
	cross.modulate = Color(1, 1, 1, 0.8)
	root.add_child(cross)

	info_panel = PanelContainer.new()
	info_panel.add_theme_stylebox_override("panel", _panel_style())
	_place(info_panel, Control.PRESET_CENTER_BOTTOM, Vector2(0, -44))
	info_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	info_panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	info_panel.custom_minimum_size = Vector2(420, 0)
	info_panel.visible = false
	root.add_child(info_panel)
	var info_box := VBoxContainer.new()
	info_panel.add_child(info_box)
	info_title = Label.new()
	info_title.add_theme_font_size_override("font_size", 18)
	info_box.add_child(info_title)
	info_detail = Label.new()
	info_detail.add_theme_font_size_override("font_size", 14)
	info_box.add_child(info_detail)
	for key in ["health", "energy", "hunger", "thirst"]:
		var row := HBoxContainer.new()
		var name_label := Label.new()
		name_label.text = BAR_NAMES[key]
		name_label.custom_minimum_size = Vector2(60, 0)
		name_label.add_theme_font_size_override("font_size", 13)
		row.add_child(name_label)
		var bar := ProgressBar.new()
		bar.max_value = 100.0
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(300, 12)
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		var fill := StyleBoxFlat.new()
		fill.bg_color = BAR_COLORS[key]
		bar.add_theme_stylebox_override("fill", fill)
		row.add_child(bar)
		info_box.add_child(row)
		bars[key] = bar

	toast_box = VBoxContainer.new()
	toast_box.position = Vector2(16, 64)
	toast_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(toast_box)

	map_panel = PanelContainer.new()
	map_panel.add_theme_stylebox_override("panel", _panel_style())
	_place(map_panel, Control.PRESET_TOP_RIGHT, Vector2(-16, 12))
	map_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	root.add_child(map_panel)
	minimap = WorldView.new()
	minimap.custom_minimum_size = Vector2(230, 230)
	minimap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	minimap.show_vision = false
	minimap.selected_id = ""
	minimap.explorer = explorer
	map_panel.add_child(minimap)

	report_dialog = AcceptDialog.new()
	report_dialog.title = "현장 보고서"
	report_dialog.size = Vector2i(760, 620)
	report_text = TextEdit.new()
	report_text.editable = false
	report_text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	report_dialog.add_child(report_text)
	report_dialog.theme = th
	add_child(report_dialog)


func _outlined(size: int) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.85))
	l.add_theme_constant_override("outline_size", 6)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _panel_style() -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.1, 0.12, 0.72)
	sb.set_corner_radius_all(8)
	sb.set_content_margin_all(10)
	return sb


func _build_scan_ring() -> void:
	var torus := TorusMesh.new()
	torus.inner_radius = 0.96
	torus.outer_radius = 1.0
	torus.rings = 64
	torus.ring_segments = 4
	_ring_mat = StandardMaterial3D.new()
	_ring_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_ring_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_ring_mat.albedo_color = Color(0.45, 0.75, 1.0, 0.0)
	scan_ring = MeshInstance3D.new()
	scan_ring.mesh = torus
	scan_ring.material_override = _ring_mat
	scan_ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	scan_ring.visible = false
	add_child(scan_ring)


func _set_status(text: String) -> void:
	status_label.text = text


func _toast(text: String, color := Color.WHITE) -> void:
	var l := _outlined(15)
	l.text = text
	l.modulate = color
	toast_box.add_child(l)
	while toast_box.get_child_count() > 6:
		toast_box.get_child(0).free()
	var tw := create_tween()
	tw.tween_interval(5.0)
	tw.tween_property(l, "modulate:a", 0.0, 1.0)
	tw.tween_callback(l.queue_free)


# ------------------------------------------------------------------------- server
func _on_hello(p: Array, _maps: Array, herd: Array) -> void:
	policies = p
	herbivore_policies = herd
	_start()


func _start() -> void:
	_needs_spawn = true
	_done_wait = 0.0
	paused = false
	follow_id = ""
	target_id = ""
	_scanned.clear()
	client.send_command({
		"type": "start",
		"seed": world_seed,
		"map": "ecosystem",
		"predator_policy": "ppo" if "ppo" in policies else String(policies[0]),
		"herbivore_policy": "herd-v1" if "herd-v1" in herbivore_policies else "rule",
		"explorer": true,
		"ticks_per_second": 60.0 if smoke_mode else float(SPEEDS[speed_index]),
	})


func _on_snapshot(s: Dictionary) -> void:
	last_snapshot = s
	world.set_snapshot(s)
	minimap.set_snapshot(s, 1.0 / maxf(float(s["ticks_per_second"]), 0.1))
	var ex: Variant = s.get("explorer")
	if ex != null:
		explorer.active = true
		explorer.map_size = float(s["map_size"])
		explorer.scan_radius = float(ex["scan_radius"])
		explorer.view_radius = float(ex["view_radius"])
		if _needs_spawn:
			_needs_spawn = false
			player.position = Vector3(float(ex["position"][0]) * S, 0, float(ex["position"][1]) * S)
	_witness(s)
	var m: Dictionary = s["metrics"]
	var exs := ""
	if ex != null:
		exs = "  ·  스캔 %d · 식별 %d · 탐사 %.0f%%" % [int(ex["scans"]), int(ex["identified"]),
			float(ex["explored_fraction"]) * 100.0]
	_set_status("seed %d · tick %d · %s · %s배속%s\n초식 %d · 포식자 %d · 사냥 %d · 출생 %d%s" % [
		world_seed, int(s["tick"]), "밤" if s["is_night"] else "낮", _speed_text(),
		"  (일시정지)" if paused else "", int(m["herbivores_alive"]),
		int(m.get("predators_alive", 1)), int(m["kills"]), int(m.get("births", 0)), exs])
	if smoke_mode:
		_smoke_step(s)


func _speed_text() -> String:
	return str(snappedf(float(SPEEDS[speed_index]) / 5.0, 0.1))


func _witness(s: Dictionary) -> void:
	"""Toast events that happen within the researcher's view radius."""
	var me := Vector2(player.position.x, player.position.z)
	var reach := explorer.view_radius * S
	for e in s["events"]:
		var kind := String(e["kind"])
		if kind not in ["kill", "birth", "death"]:
			continue
		var id := String(e["agent_id"])
		if not world.states.has(id):
			continue
		var p := world.display_position(id)
		if me.distance_to(Vector2(p.x, p.z)) > reach:
			continue
		match kind:
			"kill":
				_toast("사냥 목격: %s → %s" % [_name(id), _name(String(e["target_id"]))], Color("ff9b85"))
			"birth":
				_toast("출생: %s (부모 %s)" % [_name(String(e["target_id"])), _name(id)], Color("a8e6a1"))
			"death":
				var cause := String(e["data"].get("cause", ""))
				if cause != "predation":
					_toast("죽음: %s (%s)" % [_name(id), CAUSES.get(cause, cause)], Color("d9d9d9"))


func _name(id: String) -> String:
	var kind := "포식자" if id.begins_with("predator") else "초식"
	return "%s %s" % [kind, id.get_slice("-", 1)]


func _on_scan(scan: Dictionary) -> void:
	var sightings: Array = scan["sightings"]
	explorer.set_scan(sightings)
	_scans += 1
	var fresh := 0
	for st in sightings:
		_scanned[String(st["agent_id"])] = 0.0
		if st["new"]:
			fresh += 1
	_ring_radius = float(scan["radius"]) * S
	_ring_age = 0.0
	scan_ring.visible = true
	_toast("스캔: %d마리 (새로 식별 %d)" % [sightings.size(), fresh], Color("9fd3ff"))


func _on_report(report: Dictionary) -> void:
	var md := String(report["markdown"])
	var path := _report_out
	if path == "":
		path = "user://field_report_%d_%d.md" % [world_seed, int(report["tick"])]
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f != null:
		f.store_string(md)
		f.close()
	if smoke_mode:
		_finish_smoke(report)
		return
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	report_text.text = md + "\n\n(저장: %s)" % ProjectSettings.globalize_path(path)
	report_dialog.popup_centered()


# --------------------------------------------------------------------------- input
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		player.rotation.y -= event.relative.x * MOUSE_SENS
		_pitch = clampf(_pitch - event.relative.y * MOUSE_SENS, -1.4, 1.4)
	elif event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_ESCAPE:
				Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
			KEY_E:
				client.send_command({"type": "scan"})
			KEY_R:
				client.send_command({"type": "report"})
			KEY_F:
				_toggle_follow()
			KEY_M:
				map_panel.visible = not map_panel.visible
			KEY_SPACE:
				paused = not paused
				client.send_command({"type": "pause" if paused else "resume"})
			KEY_BRACKETLEFT, KEY_BRACKETRIGHT:
				var step := -1 if event.keycode == KEY_BRACKETLEFT else 1
				speed_index = clampi(speed_index + step, 0, SPEEDS.size() - 1)
				client.send_command({"type": "set_speed", "ticks_per_second": float(SPEEDS[speed_index])})
				_toast("속도 %s배" % _speed_text())
			KEY_N:
				world_seed += 1
				_toast("새 세계: seed %d" % world_seed)
				_start()


func _toggle_follow() -> void:
	if follow_id != "":
		_toast("따라가기 끝")
		follow_id = ""
		_pitch = -0.08
	elif target_id != "":
		follow_id = target_id
		_pitch = 0.0
		_toast("따라가기: %s  (F 또는 WASD로 해제)" % _name(follow_id))


func _process(delta: float) -> void:
	if follow_id != "" and (not world.dinos.has(follow_id) or _wasd()):
		follow_id = ""
		_pitch = -0.08
	if follow_id != "":
		_follow(delta)
	else:
		camera.position = Vector3(0, EYE, 0)
		camera.rotation.x = _pitch
		_walk(delta)
	_send_position(delta)
	_update_target()
	_update_labels(delta)
	_update_ring(delta)
	explorer.position = Vector2(player.position.x, player.position.z) / S
	explorer.last_scan_age += delta
	minimap.selected_id = target_id
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED and not smoke_mode and not report_dialog.visible:
		hint_label.text = "화면을 클릭하면 마우스로 둘러볼 수 있어요"
	else:
		hint_label.text = ""
	if last_snapshot.get("done", false):
		_done_wait += delta
		if _done_wait > 4.0 and not smoke_mode:
			world_seed += 1
			_toast("세계가 끝났어요 — 새 세계 seed %d" % world_seed)
			_start()
	if smoke_mode and not _smoke_done:
		_smoke_deadline -= delta
		if _smoke_deadline <= 0.0:
			print("3D SMOKE FAIL: no report (tick=%s scans=%d)" % [last_snapshot.get("tick", "none"), _scans])
			get_tree().quit(1)


func _wasd() -> bool:
	for k in [KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT]:
		if Input.is_key_pressed(k):
			return true
	return false


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


func _follow(delta: float) -> void:
	"""Third person: orbit behind the followed dino; the mouse turns the orbit."""
	var focus := world.display_position(follow_id)
	var back := player.global_transform.basis.z
	back.y = 0.0
	var goal := focus + back.normalized() * FOLLOW_DIST
	var size := world.map_size * S
	goal.x = clampf(goal.x, -20.0, size + 20.0)
	goal.z = clampf(goal.z, -20.0, size + 20.0)
	player.position = player.position.lerp(Vector3(goal.x, 0, goal.z), 1.0 - exp(-5.0 * delta))
	camera.position = Vector3(0, FOLLOW_HEIGHT, 0)
	camera.rotation.x = -atan2(FOLLOW_HEIGHT - 2.0, FOLLOW_DIST) + _pitch
	_moved = true


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


func _send_position(delta: float) -> void:
	_since_send += delta
	if _moved and _since_send >= SEND_INTERVAL:
		_since_send = 0.0
		_moved = false
		var size := world.map_size
		client.send_command({"type": "explorer_move",
			"x": clampf(player.position.x / S, 0.0, size), "z": clampf(player.position.z / S, 0.0, size)})


func _update_target() -> void:
	"""The dino closest to the crosshair (within LOOK_RANGE) gets the info panel."""
	var origin := camera.global_position
	var forward := -camera.global_transform.basis.z
	var best := ""
	var best_score := 1.0
	for id in world.dinos:
		var centre := world.display_position(id) + Vector3(0, 1.6, 0)
		var to := centre - origin
		var dist := to.length()
		if dist > LOOK_RANGE or dist < 0.5:
			continue
		var angle := forward.angle_to(to)
		var score := angle / maxf(atan2(3.0, dist), deg_to_rad(2.5))
		if score < best_score:
			best_score = score
			best = id
	if follow_id != "":
		best = follow_id
	target_id = best
	if best == "":
		info_panel.visible = false
		return
	var d: Dictionary = world.states[best]
	var p := world.display_position(best)
	var dist_m := p.distance_to(Vector3(player.position.x, 0, player.position.z))
	var gen := ""
	if d.get("generation") != null:
		var g := int(d["generation"])
		gen = " · 초기 개체" if g == 0 else " · %d세대" % g
		if d.get("parent_id") != null:
			gen += " (부모 %s)" % _name(String(d["parent_id"]))
	info_title.text = "%s%s" % [_name(best), "  [따라가는 중]" if best == follow_id else ""]
	var state := String(d.get("status_label", ""))
	if not d["alive"]:
		state = "사망 — %s" % CAUSES.get(String(d.get("death_cause", "")), "")
	info_detail.text = "%s · %.0fm · 나이 %d%s" % [state, dist_m, int(d["age"]), gen]
	for key in bars:
		bars[key].value = float(d[key])
	info_panel.visible = true


func _update_labels(delta: float) -> void:
	for id in _scanned.keys():
		_scanned[id] += delta
		if _scanned[id] > LABEL_SEC:
			_scanned.erase(id)
	for id in world.dinos:
		var m: DinoModel = world.dinos[id]
		var show: bool = id == target_id or _scanned.has(id)
		m.label.visible = show
		if show:
			var d: Dictionary = world.states[id]
			m.label.text = "%s\n%s" % [_name(id), String(d.get("status_label", ""))]
			m.label.modulate = Color("ffd7c9") if id.begins_with("predator") else Color("e6f2d0")


func _update_ring(delta: float) -> void:
	if not scan_ring.visible:
		return
	_ring_age += delta
	var t := _ring_age / 0.8
	if t >= 1.0:
		scan_ring.visible = false
		return
	scan_ring.position = Vector3(player.position.x, 0.3, player.position.z)
	scan_ring.scale = Vector3.ONE * maxf(_ring_radius * ease(t, 0.4), 0.1)
	_ring_mat.albedo_color.a = 0.8 * (1.0 - t)


# --------------------------------------------------------------------------- smoke
func _smoke_step(s: Dictionary) -> void:
	"""Autopilot: walk toward the herd, scan every 40 ticks, ask for the report at tick 300."""
	if _report_requested:
		return
	var herd := Vector3.ZERO
	var n := 0
	for id in world.states:
		var d: Dictionary = world.states[id]
		if d["alive"] and d["species"] == "herbivore":
			herd += world.display_position(id)
			n += 1
	if n > 0:
		herd /= n
		var to := herd - player.position
		to.y = 0.0
		if to.length() > 14.0:
			_move_to(player.position + to.normalized() * minf(RUN * 0.2, to.length() - 14.0))
		player.look_at(Vector3(herd.x, 0, herd.z), Vector3.UP)
		player.rotation.x = 0.0
		player.rotation.z = 0.0
	if int(s["tick"]) >= _next_scan_tick:
		_next_scan_tick += 40
		client.send_command({"type": "scan"})
	if int(s["tick"]) >= 300 or s["done"]:
		_report_requested = true
		client.send_command({"type": "report"})


func _finish_smoke(report: Dictionary) -> void:
	_smoke_done = true
	client.send_command({"type": "pause"})  # hold the frame still for the screenshot
	_look_at_herd()
	if "--follow" in OS.get_cmdline_user_args():  # third-person camera check
		_update_target()
		_toggle_follow()
		for i in 90:
			await get_tree().process_frame
		if follow_id == "":
			print("3D SMOKE FAIL: follow camera lost its target")
			get_tree().quit(1)
			return
	if screenshot_path != "":
		for i in 30:  # let models settle after the jump
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(screenshot_path)
	var st: Dictionary = report["stats"]
	print("3D SMOKE OK tick=%d dinos=%d models=%d scans=%d identified=%s witnessed=%s target=%s" % [
		int(report["tick"]), last_snapshot["dinos"].size(), world.dinos.size(), int(st["scans"]),
		st["identified"], st["witnessed"], target_id if target_id != "" else "-"])
	get_tree().quit(0)


func _look_at_herd() -> void:
	"""Smoke screenshots: stand near a live dino (`--closeup=<species>:<metres>`, default the
	herd from 22 m), side-on, so the screenshot shows the models."""
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


func _place(c: Control, preset: Control.LayoutPreset, offset: Vector2) -> void:
	c.set_anchors_and_offsets_preset(preset)
	c.offset_left += offset.x
	c.offset_right += offset.x
	c.offset_top += offset.y
	c.offset_bottom += offset.y
