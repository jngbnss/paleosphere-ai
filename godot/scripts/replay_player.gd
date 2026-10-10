class_name ReplayPlayer
extends RefCounted
## Plays a jsonl replay written by `python -m paleosphere.run --replay <file>` without a server.
## Raw world snapshots are converted to the same shape the server streams (docs/protocol.md).

const ACTION_LABELS := {
	"SEARCH": "탐색 중", "APPROACH": "먹잇감 발견", "CHASE": "추격 중", "ATTACK": "공격 준비",
	"GO_TO_WATER": "물 탐색", "REST": "휴식", "GIVE_UP": "추격 포기",
	"WANDER": "무리 근처 배회", "FLEE": "도주", "GO_TO_FOOD": "먹이 찾기", "NONE": "",
}

var header: Dictionary = {}
var frames: Array = []
var index := 0


func load_file(path: String) -> String:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return "파일을 열 수 없음: %s" % error_string(FileAccess.get_open_error())
	header = {}
	frames.clear()
	index = 0
	while not f.eof_reached():
		var line := f.get_line().strip_edges()
		if line.is_empty():
			continue
		var msg: Variant = JSON.parse_string(line)
		if typeof(msg) != TYPE_DICTIONARY:
			continue
		if msg.get("type") == "header":
			header = msg
		elif msg.get("type") == "frame":
			frames.append(msg)
	if frames.is_empty():
		return "리플레이에 프레임이 없음"
	return ""


func is_finished() -> bool:
	return index >= frames.size() - 1


func ticks_per_frame() -> int:
	return int(header.get("every", 1))


func current(ticks_per_second: float, paused: bool) -> Dictionary:
	var raw: Dictionary = frames[index]["snapshot"]
	var snap := raw.duplicate(true)
	var herbivores_alive := 0
	var kills := 0
	var predator_energy := 0.0
	var predator_hunger := 0.0
	for d in snap["dinos"]:
		d["status_label"] = ACTION_LABELS.get(String(d["current_action"]), "") \
			if d["alive"] else "사망"
		if d["species"] == "herbivore":
			if d["alive"]:
				herbivores_alive += 1
			elif d.get("death_cause") == "predation":
				kills += 1
		else:
			predator_energy = float(d["energy"])
			predator_hunger = float(d["hunger"])
	snap["map_size"] = float(header.get("map_size", 64.0))
	snap["predator_policy"] = "replay: %s" % header.get("predator_policy", "?")
	snap["ticks_per_second"] = ticks_per_second
	snap["paused"] = paused
	snap["done"] = is_finished()
	snap["events"] = frames[index].get("events", [])
	snap["metrics"] = {
		"herbivores_alive": herbivores_alive, "predator_energy": predator_energy,
		"predator_hunger": predator_hunger, "kills": kills,
		"attack_attempts": 0, "invalid_attacks": 0,
	}
	return snap


func advance() -> void:
	index = min(index + 1, frames.size() - 1)
