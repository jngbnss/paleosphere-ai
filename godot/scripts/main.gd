extends Control
## PaleoSphere observer viewer.
## The Python server owns the simulation; this scene renders snapshots and sends commands.
##   godot --path godot                         # normal
##   godot --path godot -- --server=ws://host:port/ws/sim
##   godot --headless --path godot -- --smoke   # CI/local smoke check
##   godot --headless --path godot -- --smoke-local --seed=10000 --actions-out=a.json
##       # client mode: Godot runs the PPO actor itself and drives the predator
##   godot --headless --path godot -- --mlp-check=fixture.json   # offline parity check
##   godot --headless --path godot -- --smoke-explorer --report-out=r.md   # explorer mode
## Explorer mode (side panel checkbox): WASD/arrows walk, E scans, R writes a field report.
## In-engine inference loads `--weights=<path>` (default ../models/ppo-v2.policy.json).

const BAR_COLORS := {
	"health": Color("4f9a53"), "energy": Color("d6a03a"),
	"hunger": Color("c4472f"), "thirst": Color("5aa0c8"),
}
const BAR_NAMES := {"health": "체력", "energy": "에너지", "hunger": "배고픔", "thirst": "갈증"}
const LOCAL_POLICY := "godot-mlp"  # dropdown entry; sent to the server as predator_policy "client"

var client: SimClient
var world_view: WorldView
var chart: LineChart
var chart_title: Label

var seed_box: SpinBox
var map_option: OptionButton
var policy_option: OptionButton
var herd_option: OptionButton
var explorer: Explorer
var explorer_check: CheckBox
var explorer_label: Label
var scan_label: Label
var report_dialog: AcceptDialog
var report_text: TextEdit
var smoke_explorer := false
var _report_out := ""
var _explorer_needs_reset := false
var _next_scan_tick := 40
var _report_requested := false
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
var replay: ReplayPlayer = null
var _replay_accum := 0.0
var _file_dialog: FileDialog
var smoke_mode := false
var screenshot_path := ""
var _smoke_snapshots := 0
var _smoke_done := false
var _smoke_deadline := 30.0
var local_policy := MlpPolicy.new()
var local_mode := false  # current run is driven by local_policy
var smoke_local := false
var _smoke_seed := 10000
var _smoke_ticks := 2000
var _actions_out := ""
var _local_actions: Array = []
var smoke_map := ""  # --map=<name>: map selected for smoke runs


func _ready() -> void:
	smoke_mode = "--smoke" in OS.get_cmdline_user_args()
	smoke_local = "--smoke-local" in OS.get_cmdline_user_args()
	smoke_explorer = "--smoke-explorer" in OS.get_cmdline_user_args()
	var weights_path := ProjectSettings.globalize_path("res://").path_join(
		"../models/ppo-v2.policy.json").simplify_path()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--screenshot="):
			screenshot_path = arg.trim_prefix("--screenshot=")
			smoke_mode = true
		elif arg.begins_with("--weights="):
			weights_path = arg.trim_prefix("--weights=")
		elif arg.begins_with("--seed="):
			_smoke_seed = int(arg.trim_prefix("--seed="))
		elif arg.begins_with("--ticks="):
			_smoke_ticks = int(arg.trim_prefix("--ticks="))
		elif arg.begins_with("--report-out="):
			_report_out = arg.trim_prefix("--report-out=")
		elif arg.begins_with("--map="):
			smoke_map = arg.trim_prefix("--map=")
		elif arg.begins_with("--actions-out="):
			_actions_out = arg.trim_prefix("--actions-out=")
	var weights_error := local_policy.load_file(weights_path)
	if weights_error != "":
		print("in-engine inference off: ", weights_error)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--mlp-check="):
			_run_mlp_check(arg.trim_prefix("--mlp-check="))
			return
	if smoke_local:
		smoke_mode = true
		_smoke_deadline = 300.0
		if not local_policy.is_loaded():
			print("SMOKE FAIL: ", weights_error)
			get_tree().quit(1)
			return
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
	client.scan_received.connect(_on_scan)
	client.report_received.connect(_on_report)
	explorer = Explorer.new()
	add_child(explorer)
	world_view.explorer = explorer
	if smoke_explorer:
		smoke_mode = true
		_smoke_deadline = 120.0
		explorer_check.button_pressed = true
	client.connect_to_server()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--replay="):
			_load_replay(arg.trim_prefix("--replay="))


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

	var replay_button := Button.new()
	replay_button.text = "리플레이 열기"
	replay_button.pressed.connect(func() -> void: _file_dialog.popup_centered_ratio(0.6))
	bar.add_child(replay_button)
	_file_dialog = FileDialog.new()
	_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
	_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	_file_dialog.filters = PackedStringArray(["*.jsonl ; PaleoSphere replay"])
	_file_dialog.file_selected.connect(_load_replay)
	add_child(_file_dialog)

	status_label = Label.new()
	status_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	# no minimum width: a long status must not push the side panel off-screen
	status_label.clip_text = true
	status_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
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

	var herd_row := HBoxContainer.new()
	herd_row.add_child(_caption("초식 정책"))
	herd_option = OptionButton.new()
	herd_option.add_item("rule")
	herd_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	herd_option.tooltip_text = "herd-*: 정책 공유 PPO로 학습한 초식 무리 (Phase 7)"
	herd_row.add_child(herd_option)
	side.add_child(herd_row)

	var explorer_row := HBoxContainer.new()
	explorer_check = CheckBox.new()
	explorer_check.text = "탐험자 모드"
	explorer_check.tooltip_text = "다음 [시작]부터 연구자가 맵을 걸어 다니며 관찰합니다"
	explorer_row.add_child(explorer_check)
	var scan_button := Button.new()
	scan_button.text = "스캔 (E)"
	scan_button.pressed.connect(_scan)
	explorer_row.add_child(scan_button)
	var report_button := Button.new()
	report_button.text = "보고서 (R)"
	report_button.pressed.connect(_request_report)
	explorer_row.add_child(report_button)
	side.add_child(explorer_row)
	explorer_label = Label.new()
	explorer_label.add_theme_font_size_override("font_size", 13)
	explorer_label.visible = false
	side.add_child(explorer_label)
	scan_label = Label.new()
	scan_label.add_theme_font_size_override("font_size", 12)
	scan_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	scan_label.visible = false
	side.add_child(scan_label)

	report_dialog = AcceptDialog.new()
	report_dialog.title = "현장 보고서"
	report_dialog.size = Vector2i(760, 620)
	report_text = TextEdit.new()
	report_text.editable = false
	report_text.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	report_dialog.add_child(report_text)
	add_child(report_dialog)

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

	chart_title = _section("초식 개체수(초록) · 포식자 에너지(노랑)")
	side.add_child(chart_title)
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
	replay = null
	paused = false
	pause_button.text = "일시정지"
	chart.clear()
	local_mode = _selected_policy() == LOCAL_POLICY
	_local_actions.clear()
	explorer.active = false
	_explorer_needs_reset = explorer_check.button_pressed
	scan_label.visible = false
	client.send_command({
		"type": "start",
		"seed": int(seed_box.value),
		"map": map_option.get_item_text(map_option.selected),
		"predator_policy": "client" if local_mode else _selected_policy(),
		"herbivore_policy": herd_option.get_item_text(herd_option.selected),
		"explorer": explorer_check.button_pressed,
		"ticks_per_second": speed_slider.value,
	})


func _toggle_pause() -> void:
	paused = not paused
	pause_button.text = "재개" if paused else "일시정지"
	if replay == null:
		client.send_command({"type": "pause" if paused else "resume"})


func _on_speed(value: float) -> void:
	speed_label.text = "%d tick/s" % int(value)
	if replay == null:
		client.send_command({"type": "set_speed", "ticks_per_second": value})


func _selected_policy() -> String:
	if policy_option.item_count == 0:
		return "rule"
	return policy_option.get_item_text(policy_option.selected)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			_toggle_pause()
		elif event.keycode == KEY_E and explorer.active:
			_scan()
		elif event.keycode == KEY_R and explorer.active:
			_request_report()


func _scan() -> void:
	if explorer.active and replay == null:
		client.send_command({"type": "scan"})


func _request_report() -> void:
	if explorer.active and replay == null:
		client.send_command({"type": "report"})


func _keyboard_free() -> bool:
	var focus := get_viewport().gui_get_focus_owner()
	return not (focus is LineEdit or focus is TextEdit)


func _on_scan(scan: Dictionary) -> void:
	var sightings: Array = scan["sightings"]
	explorer.set_scan(sightings)
	var new_count := 0
	var lines := []
	for s in sightings:
		if s["new"]:
			new_count += 1
		if lines.size() < 6:
			lines.append("· %s%s  %s  %.0fm" % [s["agent_id"], " (새로)" if s["new"] else "",
				s["status_label"], float(s["distance"])])
	scan_label.text = "스캔 tick %d: %d마리 (새로 식별 %d)\n%s" % [
		int(scan["tick"]), sightings.size(), new_count,
		"\n".join(lines) if lines.size() > 0 else "반경 안에 공룡 없음"]
	scan_label.visible = true


func _on_report(report: Dictionary) -> void:
	var md := String(report["markdown"])
	var path := _report_out
	if path == "":
		path = "user://field_report_%d_%d.md" % [int(last_snapshot.get("seed", 0)), int(report["tick"])]
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f != null:
		f.store_string(md)
		f.close()
	if smoke_explorer:
		var st: Dictionary = report["stats"]
		if screenshot_path:
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png(screenshot_path)
		print("EXPLORER SMOKE OK tick=%d scans=%d identified=%s witnessed=%s explored=%.2f" % [
			int(report["tick"]), int(st["scans"]), st["identified"], st["witnessed"],
			float(st["explored_fraction"])])
		get_tree().quit(0)
		return
	report_text.text = md + "\n\n(저장: %s)" % ProjectSettings.globalize_path(path)
	report_dialog.popup_centered()


# ----------------------------------------------------------------------------- server events
func _on_hello(policies: Array, maps: Array, herbivore_policies: Array) -> void:
	var current_herd := herd_option.get_item_text(herd_option.selected)
	herd_option.clear()
	for h in herbivore_policies:
		herd_option.add_item(String(h))
		if String(h) == current_herd:
			herd_option.select(herd_option.item_count - 1)
	var current_map := map_option.get_item_text(map_option.selected)
	map_option.clear()
	for m in maps:
		map_option.add_item(String(m))
		if String(m) == current_map:
			map_option.select(map_option.item_count - 1)
	if smoke_map != "":
		for i in map_option.item_count:
			if map_option.get_item_text(i) == smoke_map:
				map_option.select(i)
	policy_option.clear()
	for p in policies:
		policy_option.add_item(String(p))
	if local_policy.is_loaded():
		policy_option.add_item(LOCAL_POLICY)
		policy_option.set_item_tooltip(policy_option.item_count - 1,
			"Godot 안에서 %s 가중치로 직접 추론 (서버는 규칙만 실행)" % local_policy.version)
	var preferred := policies.find("ppo")
	policy_option.select(preferred if preferred >= 0 else 0)
	if smoke_explorer:
		speed_slider.set_value_no_signal(60)
		_start()
	elif smoke_local:
		policy_option.select(policy_option.item_count - 1)
		seed_box.value = _smoke_seed
		speed_slider.set_value_no_signal(200)
		_start()
	elif smoke_mode and replay == null:
		speed_slider.set_value_no_signal(60 if screenshot_path else 20)
		_start()


func _on_snapshot(s: Dictionary) -> void:
	if replay != null:
		return
	var obs: Variant = s.get("predator_observation")
	if local_mode and obs != null and not s["done"]:
		var action := local_policy.predict(obs)
		if _local_actions.size() == int(s["tick"]):
			_local_actions.append(action)
		client.send_command({"type": "action", "tick": int(s["tick"]), "action": action})
	_show(s)
	if smoke_local and not _smoke_done and (s["done"] or int(s["tick"]) >= _smoke_ticks):
		_smoke_done = true
		if _actions_out != "":
			var f := FileAccess.open(_actions_out, FileAccess.WRITE)
			f.store_string(JSON.stringify({
				"seed": int(s["seed"]), "map": s["map"], "ticks": int(s["tick"]),
				"weights": local_policy.version, "actions": _local_actions}))
			f.close()
		print("LOCAL SMOKE OK tick=%d kills=%d actions=%d weights=%s" % [
			int(s["tick"]), int(s["metrics"]["kills"]), _local_actions.size(),
			local_policy.version])
		get_tree().quit(0)


func _show(s: Dictionary) -> void:
	if not last_snapshot.is_empty() and (int(s["tick"]) < int(last_snapshot["tick"]) \
			or s["seed"] != last_snapshot["seed"]):
		chart.clear()
	last_snapshot = s
	world_view.set_snapshot(s, 1.0 / float(s.get("ticks_per_second", 10.0)))
	var m: Dictionary = s["metrics"]
	var ecosystem := String(s["map"]) == "ecosystem"
	chart.show_predators = ecosystem
	chart_title.text = "초식 개체수(초록) · 포식자 수(빨강)" if ecosystem \
		else "초식 개체수(초록) · 포식자 에너지(노랑)"
	chart.add_point(int(s["tick"]), float(m["herbivores_alive"]), float(m["predator_energy"]),
		float(m.get("predators_alive", 1)))
	if ecosystem:
		metrics_label.text = "정책  %s / 초식 %s\n초식  %d · 포식자  %d\n출생  %d · 사냥  %d" % [
			_policy_display(String(s["predator_policy"])), s.get("herbivore_policy", "rule"),
			int(m["herbivores_alive"]),
			int(m.get("predators_alive", 0)), int(m.get("births", 0)), int(m["kills"])]
	else:
		metrics_label.text = "정책  %s / 초식 %s\n초식 생존  %d / 8\n사냥  %d\n공격 시도 / 무효  %d / %d" % [
			_policy_display(String(s["predator_policy"])), s.get("herbivore_policy", "rule"),
			int(m["herbivores_alive"]),
			int(m["kills"]), int(m["attack_attempts"]), int(m["invalid_attacks"])]
	var phase := "밤" if s["is_night"] else "낮"
	var state := "종료" if s["done"] else ("일시정지" if s["paused"] else "진행 중")
	_set_status("tick %d · %s · %s · seed %d · %s" % [
		int(s["tick"]), phase, state, int(s["seed"]), s["map"]])
	_refresh_selected()

	_update_explorer(s)
	if smoke_mode and not smoke_local and not smoke_explorer and not _smoke_done:
		_smoke_snapshots += 1
		if _smoke_snapshots >= (120 if screenshot_path else 20):
			_smoke_done = true
			if screenshot_path:
				await RenderingServer.frame_post_draw
				get_viewport().get_texture().get_image().save_png(screenshot_path)
			print("SMOKE OK tick=%d policy=%s dinos=%d" % [
				int(s["tick"]), s["predator_policy"], s["dinos"].size()])
			get_tree().quit(0)


func _policy_display(name: String) -> String:
	if name == "client":
		return "%s (Godot 추론: %s)" % [LOCAL_POLICY, local_policy.version]
	return name


func _refresh_selected() -> void:
	if last_snapshot.is_empty():
		return
	for d in last_snapshot["dinos"]:
		if String(d["agent_id"]) != world_view.selected_id:
			continue
		selected_title.text = "%s  ·  %s" % [d["agent_id"], d.get("status_label", "")]
		var target: Variant = d.get("target_id")
		var lineage := ""
		if d.get("generation") != null:
			lineage = "\n세대 %d%s · 나이 %d" % [int(d["generation"]),
				("  (부모 %s)" % d["parent_id"]) if d.get("parent_id") != null else "",
				int(d["age"])]
		selected_detail.text = "행동: %s%s%s%s" % [
			d["current_action"],
			("  → " + String(target)) if target != null else "",
			("" if d["alive"] else "  (사망: %s)" % d.get("death_cause")),
			lineage]
		for key in bars:
			bars[key].value = float(d[key])
		return


func _load_replay(path: String) -> void:
	var player := ReplayPlayer.new()
	var err := player.load_file(path)
	if err != "":
		_set_status(err)
		return
	if not paused:
		client.send_command({"type": "pause"})
	replay = player
	_replay_accum = 0.0
	chart.clear()
	last_snapshot = {}
	_show(replay.current(speed_slider.value, paused))
	_set_status("리플레이: %s (%d 프레임)" % [path.get_file(), replay.frames.size()])


## Offline parity check: fixture {"obs": [[...]], "actions": [...]} from the Python export.
func _run_mlp_check(path: String) -> void:
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not local_policy.is_loaded() or typeof(data) != TYPE_DICTIONARY:
		print("MLP CHECK FAIL: weights or fixture missing")
		get_tree().quit(1)
		return
	var mismatches := 0
	var obs_list: Array = data["obs"]
	for i in obs_list.size():
		if local_policy.predict(obs_list[i]) != int(data["actions"][i]):
			mismatches += 1
	if mismatches == 0:
		print("MLP CHECK OK n=%d weights=%s" % [obs_list.size(), local_policy.version])
		get_tree().quit(0)
	else:
		print("MLP CHECK FAIL mismatches=%d / %d" % [mismatches, obs_list.size()])
		get_tree().quit(1)


func _update_explorer(s: Dictionary) -> void:
	var state: Variant = s.get("explorer")
	if state == null:
		explorer.active = false
		explorer_label.visible = false
		return
	explorer.map_size = float(s["map_size"])
	if _explorer_needs_reset or not explorer.active:
		explorer.reset(state)
		_explorer_needs_reset = false
	explorer_label.visible = true
	explorer_label.text = "WASD 이동 · E 스캔 · R 보고서\n스캔 %d회 · 식별 %d마리 · 탐사 %.0f%%" % [
		int(state["scans"]), int(state["identified"]), float(state["explored_fraction"]) * 100.0]
	if smoke_explorer and not _report_requested:
		# autopilot: walk toward the herd, scan regularly, then ask for the report
		var herd := Vector2.ZERO
		var n := 0
		for d in s["dinos"]:
			if d["species"] == "herbivore" and d["alive"]:
				herd += Vector2(float(d["position"][0]), float(d["position"][1]))
				n += 1
		if n > 0:
			explorer.autopilot_target = herd / n
		if int(s["tick"]) >= _next_scan_tick:
			_next_scan_tick += 40
			_scan()
		if int(s["tick"]) >= 300 or s["done"]:
			_report_requested = true
			_request_report()


func _process(delta: float) -> void:
	if explorer != null and explorer.step(delta, _keyboard_free()) and replay == null:
		client.send_command({"type": "explorer_move", "x": explorer.position.x,
			"z": explorer.position.y})
	if replay != null and not paused and not replay.is_finished():
		_replay_accum += delta
		var frame_time := float(replay.ticks_per_frame()) / speed_slider.value
		while _replay_accum >= frame_time and not replay.is_finished():
			_replay_accum -= frame_time
			replay.advance()
			_show(replay.current(speed_slider.value, paused))
	if smoke_mode:
		_smoke_deadline -= delta
		if _smoke_deadline <= 0.0:
			print("SMOKE FAIL: no snapshots from server")
			get_tree().quit(1)
