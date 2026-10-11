class_name Explorer
extends Node
## Explorer mode (Phase 8): a field researcher the player walks with WASD / arrow keys.
## The walk is local and smooth; the position is sent to the server (`explorer_move`) a few
## times per second. The server keeps the field journal (scans, witnessed events, report).

signal moved(position: Vector2)

const SPEED := 10.0  # map units per real second
const SEND_INTERVAL := 0.1

var active := false
var position := Vector2(32, 32)
var map_size := 64.0
var scan_radius := 12.0
var view_radius := 16.0
var autopilot_target = null  # Vector2 or null: smoke runs walk without a keyboard
var last_scan: Dictionary = {}  # agent_id -> true, highlighted after a scan
var last_scan_age := 99.0
var _since_send := 0.0
var _dirty := false


func reset(state: Dictionary) -> void:
	active = true
	position = Vector2(float(state["position"][0]), float(state["position"][1]))
	scan_radius = float(state["scan_radius"])
	view_radius = float(state["view_radius"])
	last_scan.clear()
	last_scan_age = 99.0


func set_scan(sightings: Array) -> void:
	last_scan.clear()
	for s in sightings:
		last_scan[String(s["agent_id"])] = true
	last_scan_age = 0.0


func can_see(p: Vector2) -> bool:
	return not active or p.distance_to(position) <= view_radius


func step(delta: float, keyboard_enabled: bool) -> bool:
	"""Advance local movement; returns true when a position update should be sent."""
	last_scan_age += delta
	if not active:
		return false
	var dir := Vector2.ZERO
	if keyboard_enabled:
		if Input.is_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP):
			dir.y -= 1
		if Input.is_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN):
			dir.y += 1
		if Input.is_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT):
			dir.x -= 1
		if Input.is_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT):
			dir.x += 1
	if autopilot_target != null:
		var to: Vector2 = autopilot_target - position
		if to.length() > 0.5:
			dir = to.normalized()
	if dir != Vector2.ZERO:
		position = (position + dir.normalized() * SPEED * delta).clamp(
			Vector2.ZERO, Vector2(map_size, map_size))
		_dirty = true
		moved.emit(position)
	_since_send += delta
	if _dirty and _since_send >= SEND_INTERVAL:
		_since_send = 0.0
		_dirty = false
		return true
	return false
