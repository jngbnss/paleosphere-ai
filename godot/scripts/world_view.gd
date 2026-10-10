class_name WorldView
extends Control
## Draws one world snapshot. Positions are interpolated between consecutive snapshots so the
## view stays smooth regardless of simulation tick rate (FPS and sim tick are independent).

signal dino_selected(agent_id: String)

const COLOR_DAY := Color("e9e4d6")
const COLOR_NIGHT := Color("5c6470")
const COLOR_HERB := Color("4f9a53")
const COLOR_PRED := Color("c4472f")
const COLOR_PLANT := Color("8bbf6a")
const COLOR_WATER := Color("5aa0c8")
const COLOR_ROCK := Color("8a8580")
const COLOR_INK := Color("25323b")

var snapshot: Dictionary = {}
var selected_id := "predator-000"
var show_vision := true

var _prev_pos: Dictionary = {}
var _curr_pos: Dictionary = {}
var _since := 0.0
var _interval := 0.1


func set_snapshot(s: Dictionary, interval: float) -> void:
	var t := _alpha()
	var fresh: bool = snapshot.is_empty() or int(s.get("tick", 0)) < int(snapshot.get("tick", 0)) \
		or s.get("seed") != snapshot.get("seed")
	_prev_pos.clear()
	for d in s["dinos"]:
		var id := String(d["agent_id"])
		var target := _vec(d["position"])
		if fresh or not _curr_pos.has(id):
			_prev_pos[id] = target
		else:
			_prev_pos[id] = _lerp_pos(id, t)
	_curr_pos.clear()
	for d in s["dinos"]:
		_curr_pos[String(d["agent_id"])] = _vec(d["position"])
	snapshot = s
	_since = 0.0
	_interval = max(interval, 0.001)
	queue_redraw()


func _process(delta: float) -> void:
	_since += delta
	if not snapshot.is_empty():
		queue_redraw()


func _alpha() -> float:
	return clamp(_since / _interval, 0.0, 1.0)


func _lerp_pos(id: String, t: float) -> Vector2:
	var a: Vector2 = _prev_pos.get(id, _curr_pos.get(id, Vector2.ZERO))
	var b: Vector2 = _curr_pos.get(id, a)
	return a.lerp(b, t)


func _vec(p: Array) -> Vector2:
	return Vector2(float(p[0]), float(p[1]))


func _scale() -> float:
	var map_size := float(snapshot.get("map_size", 64.0))
	return min(size.x, size.y) / map_size


func _to_screen(p: Vector2) -> Vector2:
	return p * _scale()


func _draw() -> void:
	if snapshot.is_empty():
		draw_string(get_theme_default_font(), Vector2(24, 40), "서버 연결을 기다리는 중…  (uv run python -m app)",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 18, COLOR_INK)
		return
	var s := _scale()
	var map_px := float(snapshot.get("map_size", 64.0)) * s
	var night := bool(snapshot.get("is_night", false))
	draw_rect(Rect2(Vector2.ZERO, Vector2(map_px, map_px)), COLOR_NIGHT if night else COLOR_DAY)

	for w in snapshot["waters"]:
		draw_circle(_to_screen(_vec(w["position"])), float(w["radius"]) * s, COLOR_WATER)
	for p in snapshot["plants"]:
		var c := COLOR_PLANT
		c.a = 0.25 + 0.75 * clamp(float(p["food"]) / 60.0, 0.0, 1.0)
		draw_circle(_to_screen(_vec(p["position"])), float(p["radius"]) * s, c)
	for r in snapshot["rocks"]:
		draw_circle(_to_screen(_vec(r["position"])), float(r["radius"]) * s, COLOR_ROCK)

	var t := _alpha()
	var font := get_theme_default_font()
	for d in snapshot["dinos"]:
		var id := String(d["agent_id"])
		var pos := _to_screen(_lerp_pos(id, t))
		var alive := bool(d["alive"])
		var is_pred := String(d["species"]) == "predator"
		if is_pred and alive and show_vision and d.has("vision"):
			draw_arc(pos, float(d["vision"]) * s, 0.0, TAU, 64, Color(COLOR_PRED, 0.45), 1.5)
		var col := COLOR_PRED if is_pred else COLOR_HERB
		if not alive:
			col.a = 0.3
		if is_pred:
			var v := _vec(d["velocity"])
			var ang := v.angle() if v.length() > 0.0001 else 0.0
			var pts := PackedVector2Array([Vector2(14, 0), Vector2(-9, 8), Vector2(-9, -8)])
			var xf := Transform2D(ang, pos)
			draw_colored_polygon(xf * pts, col)
		else:
			draw_circle(pos, 7.0, col)
		if id == selected_id:
			draw_arc(pos, 13.0, 0.0, TAU, 32, COLOR_INK, 2.0)
			var label := String(d.get("status_label", d.get("current_action", "")))
			draw_string(font, pos + Vector2(15, -12), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, COLOR_INK)


func _gui_input(event: InputEvent) -> void:
	if snapshot.is_empty():
		return
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		var world_pos: Vector2 = event.position / _scale()
		var best := ""
		var best_d := 3.0
		for d in snapshot["dinos"]:
			var dist := world_pos.distance_to(_vec(d["position"]))
			if dist < best_d:
				best_d = dist
				best = String(d["agent_id"])
		if best != "":
			selected_id = best
			dino_selected.emit(best)
			queue_redraw()
