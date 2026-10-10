class_name SimClient
extends Node
## WebSocket client for the Python sim server (docs/protocol.md).
## Reconnects automatically; emits one signal per server message type.

signal connected
signal disconnected
signal hello_received(policies: Array, maps: Array)
signal snapshot_received(snapshot: Dictionary)
signal error_received(message: String)

var url := "ws://127.0.0.1:8790/ws/sim"
var _ws := WebSocketPeer.new()
var _last_state := WebSocketPeer.STATE_CLOSED
var _retry_in := 0.0


func connect_to_server() -> void:
	_ws = WebSocketPeer.new()
	var err := _ws.connect_to_url(url)
	if err != OK:
		push_warning("WebSocket connect failed: %s" % error_string(err))


func is_open() -> bool:
	return _ws.get_ready_state() == WebSocketPeer.STATE_OPEN


func send_command(cmd: Dictionary) -> void:
	if is_open():
		_ws.send_text(JSON.stringify(cmd))


func _process(delta: float) -> void:
	_ws.poll()
	var state := _ws.get_ready_state()
	if state != _last_state:
		if state == WebSocketPeer.STATE_OPEN:
			connected.emit()
		elif state == WebSocketPeer.STATE_CLOSED:
			disconnected.emit()
		_last_state = state

	if state == WebSocketPeer.STATE_OPEN:
		while _ws.get_available_packet_count() > 0:
			_handle(_ws.get_packet().get_string_from_utf8())
	elif state == WebSocketPeer.STATE_CLOSED:
		_retry_in -= delta
		if _retry_in <= 0.0:
			_retry_in = 1.0
			connect_to_server()


func _handle(text: String) -> void:
	var msg: Variant = JSON.parse_string(text)
	if typeof(msg) != TYPE_DICTIONARY:
		return
	match String(msg.get("type", "")):
		"hello":
			hello_received.emit(msg["policies"], msg["maps"])
		"snapshot":
			snapshot_received.emit(msg)
		"error":
			error_received.emit(String(msg["message"]))
