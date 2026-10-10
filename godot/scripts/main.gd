extends Control
## PaleoSphere observer viewer.
## The Python server owns the simulation; this scene renders snapshots and sends commands.
##   godot --path godot                         # normal
##   godot --path godot -- --server=ws://host:port/ws/sim
##   godot --headless --path godot -- --smoke   # CI/local smoke check

const BAR_COLORS := {
	"health": Color("4f9a53"), "energy": Color("d6a03a"),
	"hunger": Color("c4472f"), "thirst": Color("5aa0c8"),
}
const BAR_NAMES := {"health": "체력", "energy": "에너지", "hunger": "배고픔", "thirst": "갈증"}

var client: SimClient
var world_view: WorldView
var chart: LineChart

var seed_box: SpinBox
var map_option: OptionButton
var policy_option: OptionButton
var pause_button: Button
var speed_slider: HSlider
var speed_label: Label
var status_label: Label
var metrics_label: Label
var selected_title: Label
var selected_detail: Label
var bars: Dictionary = {}

var paused := false
var last_snapshot: Dictionary = {}
var smoke_mode := false
var screenshot_path := ""
var _smoke_snapshots := 0
var _smoke_done := false
var _smoke_deadline := 30.0


func _ready() -> void:
	smoke_mode = "--smoke" in OS.get_cmdline_user_args()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--screenshot="):
			screenshot_path = arg.trim_prefix("--screenshot=")
			smoke_mode = true
	RenderingServer.set_default_clear_color(Color("1d2226"))
	_apply_theme()
	_build_ui()

	client = SimClient.new()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--server="):
			client.url = arg.trim_prefix("--server=")
	add_child(client)
	client.connected.connect(func() -> void: _set_status("연결됨 — [시작]을 누르세요"))
	client.disconnected.connect(func() -> void: _set_status("서버 연결 끊김, 재연결 중… (uv run python -m app)"))
	client.hello_received.connect(_on_hello)
	client.snapshot_received.connect(_on_snapshot)
	client.error_received.connect(func(m: String) -> void: _set_status("서버 오류: " + m))
	client.connect_to_server()


# ----------------------------------------------------------------------------- UI build
func _apply_theme() -> void:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(
		["Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans CJK KR", "Noto Sans KR", "sans-serif"])
	var th := Theme.new()
	th.default_font = font
	th.default_font_size = 15
	theme = th


func _build_ui() -> void:
	var root := VBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 8)
	add_child(root)

	var margin := MarginContainer.new()
	for side in ["left", "right", "top"]:
		margin.add_theme_constant_override("margin_" + side, 10)
	root.add_child(margin)
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 10)
	margin.add_child(bar)

	var title := Label.new()
	title.text = "PaleoSphere"
	title.add_theme_font_size_override("font_size", 20)
	bar.add_child(title)

	bar.add_child(_caption("seed"))
	seed_box = SpinBox.new()
	seed_box.min_value = 0
	seed_box.max_value = 99999
	seed_box.value = 10000
	bar.add_child(seed_box)

	bar.add_child(_caption("맵"))
	map_option = OptionButton.new()
	map_option.add_item("map_a")
	map_option.add_item("map_b")
	bar.add_child(map_option)

	bar.add_child(_caption("포식자 정책"))
	policy_option = OptionButton.new()
	policy_option.custom_minimum_size.x = 110
	bar.add_child(policy_option)

	var start := Button.new()
	start.text = "시작"
	start.pressed.connect(_start)
	bar.add_child(start)

	pause_button = Button.new()
	pause_button.text = "일시정지"
	pause_button.pressed.connect(_toggle_pause)
	bar.add_child(pause_button)

	bar.add_child(_caption("속도"))
	speed_slider = HSlider.new()
	speed_slider.min_value = 1
	speed_slider.max_value = 100
	speed_slider.value = 20
	speed_slider.custom_minimum_size.x = 140
	speed_slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	speed_slider.value_changed.connect(_on_speed)
	bar.add_child(speed_slider)
	speed_label = _caption("20 tick/s")
	bar.add_child(speed_label)

	var vision := CheckBox.new()
	vision.text = "시야"
	vision.button_pressed = true
	vision.toggled.connect(func(on: bool) -> void: world_view.show_vision = on)
	bar.add_child(vision)

	status_label = Label.new()
	status_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	status_label.text = "서버 연결 중…"
	bar.add_child(status_label)

	var body_margin := MarginContainer.new()
	body_margin.size_flags_vertical = Control.SIZE_EXPAND_FILL
	for side in ["left", "right", "bottom"]:
		body_margin.add_theme_constant_override("margin_" + side, 10)
	root.add_child(body_margin)
	var body := HBoxContainer.new()
	body.add_theme_constant_override("separation", 12)
	body_margin.add_child(body)

	world_view = WorldView.new()
	world_view.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	world_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	world_view.dino_selected.connect(func(_id: String) -> void: _refresh_selected())
	body.add_child(world_view)

	var side := VBoxContainer.new()
	side.custom_minimum_size.x = 320
	side.add_theme_constant_override("separation", 10)
	body.add_child(side)

	side.add_child(_section("현황"))
	metrics_label = Label.new()
	side.add_child(metrics_label)

	side.add_child(_section("선택한 공룡 (클릭)"))
	selected_title = Label.new()
	selected_title.add_theme_font_size_override("font_size", 17)
	side.add_child(selected_title)
	selected_detail = Label.new()
	selected_detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	side.add_child(selected_detail)
	for key in ["health", "energy", "hunger", "thirst"]:
		side.add_child(_caption(BAR_NAMES[key]))
		var pb := ProgressBar.new()
		pb.max_value = 100
		pb.show_percentage = false
		pb.custom_minimum_size.y = 10
		var fill := StyleBoxFlat.new()
		fill.bg_color = BAR_COLORS[key]
		pb.add_theme_stylebox_override("fill", fill)
		side.add_child(pb)
		bars[key] = pb

	side.add_child(_section("초식 개체수(초록) · 포식자 에너지(노랑)"))
	chart = LineChart.new()
	chart.custom_minimum_size = Vector2(300, 140)
	side.add_child(chart)

	var note := Label.new()
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.add_theme_font_size_override("font_size", 12)
	note.modulate = Color(1, 1, 1, 0.6)
	note.text = "상태 라벨은 관찰값과 선택된 행동을 사람이 읽기 쉽게 바꾼 것이며, 모델 내부 추론이 아닙니다. Space: 일시정지"
	side.add_child(note)


func _caption(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.modulate = Color(1, 1, 1, 0.7)
	return l


func _section(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", 13)
	l.modulate = Color(0.75, 0.85, 0.75)
	return l


func _set_status(text: String) -> void:
	status_label.text = text


# ----------------------------------------------------------------------------- commands
func _start() -> void:
	paused = false
	pause_button.text = "일시정지"
	chart.clear()
	client.send_command({
		"type": "start",
		"seed": int(seed_box.value),
		"map": map_option.get_item_text(map_option.selected),
		"predator_policy": _selected_policy(),
		"ticks_per_second": speed_slider.value,
	})


func _toggle_pause() -> void:
	paused = not paused
	pause_button.text = "재개" if paused else "일시정지"
	client.send_command({"type": "pause" if paused else "resume"})


func _on_speed(value: float) -> void:
	speed_label.text = "%d tick/s" % int(value)
	client.send_command({"type": "set_speed", "ticks_per_second": value})


func _selected_policy() -> String:
	if policy_option.item_count == 0:
		return "rule"
	return policy_option.get_item_text(policy_option.selected)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_SPACE:
		_toggle_pause()


# ----------------------------------------------------------------------------- server events
func _on_hello(policies: Array, _maps: Array) -> void:
	policy_option.clear()
	for p in policies:
		policy_option.add_item(String(p))
	var preferred := policies.find("ppo")
	policy_option.select(preferred if preferred >= 0 else 0)
	if smoke_mode:
		speed_slider.set_value_no_signal(60 if screenshot_path else 20)
		_start()


func _on_snapshot(s: Dictionary) -> void:
	if not last_snapshot.is_empty() and (int(s["tick"]) < int(last_snapshot["tick"]) \
			or s["seed"] != last_snapshot["seed"]):
		chart.clear()
	last_snapshot = s
	world_view.set_snapshot(s, 1.0 / float(s.get("ticks_per_second", 10.0)))
	var m: Dictionary = s["metrics"]
	chart.add_point(int(s["tick"]), float(m["herbivores_alive"]), float(m["predator_energy"]))
	metrics_label.text = "정책  %s\n초식 생존  %d / 8\n사냥  %d\n공격 시도 / 무효  %d / %d" % [
		s["predator_policy"], int(m["herbivores_alive"]), int(m["kills"]),
		int(m["attack_attempts"]), int(m["invalid_attacks"])]
	var phase := "밤" if s["is_night"] else "낮"
	var state := "종료" if s["done"] else ("일시정지" if s["paused"] else "진행 중")
	_set_status("tick %d · %s · %s · seed %d · %s" % [
		int(s["tick"]), phase, state, int(s["seed"]), s["map"]])
	_refresh_selected()

	if smoke_mode and not _smoke_done:
		_smoke_snapshots += 1
		if _smoke_snapshots >= (120 if screenshot_path else 20):
			_smoke_done = true
			if screenshot_path:
				await RenderingServer.frame_post_draw
				get_viewport().get_texture().get_image().save_png(screenshot_path)
			print("SMOKE OK tick=%d policy=%s dinos=%d" % [
				int(s["tick"]), s["predator_policy"], s["dinos"].size()])
			get_tree().quit(0)


func _refresh_selected() -> void:
	if last_snapshot.is_empty():
		return
	for d in last_snapshot["dinos"]:
		if String(d["agent_id"]) != world_view.selected_id:
			continue
		selected_title.text = "%s  ·  %s" % [d["agent_id"], d.get("status_label", "")]
		var target: Variant = d.get("target_id")
		selected_detail.text = "행동: %s%s%s" % [
			d["current_action"],
			("  → " + String(target)) if target != null else "",
			("" if d["alive"] else "  (사망: %s)" % d.get("death_cause"))]
		for key in bars:
			bars[key].value = float(d[key])
		return


func _process(delta: float) -> void:
	if smoke_mode:
		_smoke_deadline -= delta
		if _smoke_deadline <= 0.0:
			print("SMOKE FAIL: no snapshots from server")
			get_tree().quit(1)
