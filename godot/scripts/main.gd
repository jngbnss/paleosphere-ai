extends Control
## PaleoSphere observer viewer. Connects to the sim server, starts a run and renders it.
## Run headless smoke check: godot --headless --path godot -- --smoke

var client: SimClient
var world_view: WorldView
var smoke_mode := false
var _smoke_snapshots := 0
var _smoke_deadline := 15.0


func _ready() -> void:
	smoke_mode = "--smoke" in OS.get_cmdline_user_args()
	world_view = WorldView.new()
	world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(world_view)

	client = SimClient.new()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--server="):
			client.url = arg.trim_prefix("--server=")
	add_child(client)
	client.hello_received.connect(_on_hello)
	client.snapshot_received.connect(_on_snapshot)
	client.error_received.connect(func(m: String) -> void: push_warning("server: " + m))
	client.connect_to_server()


func _process(delta: float) -> void:
	if smoke_mode:
		_smoke_deadline -= delta
		if _smoke_deadline <= 0.0:
			print("SMOKE FAIL: no snapshots from server")
			get_tree().quit(1)


func _on_hello(policies: Array, _maps: Array) -> void:
	client.send_command({
		"type": "start", "seed": 10000, "map": "map_a",
		"predator_policy": "ppo" if "ppo" in policies else "rule", "ticks_per_second": 20,
	})


func _on_snapshot(s: Dictionary) -> void:
	world_view.set_snapshot(s, 1.0 / float(s.get("ticks_per_second", 10.0)))
	if smoke_mode:
		_smoke_snapshots += 1
		if _smoke_snapshots >= 20:
			print("SMOKE OK tick=%d policy=%s dinos=%d" % [
				int(s["tick"]), s["predator_policy"], s["dinos"].size()])
			get_tree().quit(0)
