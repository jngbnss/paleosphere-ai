class_name MlpPolicy
extends RefCounted
## In-engine inference for an exported PPO actor (`*.policy.json`, format paleosphere-mlp-v1).
## Mirrors simulator/paleosphere/policies/mlp.py: hidden layers -> activation, last layer ->
## one logit per action, action = argmax. Weights are stored [out][in].
## Produce the file with: uv run python -m training.scripts.export_onnx --model models/ppo-v2.zip

const FORMAT := "paleosphere-mlp-v1"

var version := ""
var obs_dim := 0
var actions: Array = []
var activation := "tanh"
var _weights: Array = []  # per layer: Array of PackedFloat64Array rows
var _biases: Array = []  # per layer: PackedFloat64Array


## Returns "" on success, otherwise an error message.
func load_file(path: String) -> String:
	if not FileAccess.file_exists(path):
		return "가중치 파일 없음: %s" % path
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	if typeof(data) != TYPE_DICTIONARY or data.get("format", "") != FORMAT:
		return "지원하지 않는 가중치 형식: %s" % path
	activation = String(data["activation"])
	if activation != "tanh" and activation != "relu":
		return "지원하지 않는 활성화 함수: %s" % activation
	obs_dim = int(data["obs_dim"])
	actions = data["actions"]
	version = String(data.get("source", {}).get("version", path.get_file().get_basename()))
	_weights.clear()
	_biases.clear()
	for layer in data["layers"]:
		var rows: Array = []
		for row in layer["weight"]:
			rows.append(PackedFloat64Array(row))
		_weights.append(rows)
		_biases.append(PackedFloat64Array(layer["bias"]))
	if _weights.is_empty() or (_weights[0][0] as PackedFloat64Array).size() != obs_dim:
		return "첫 층 입력 크기가 obs_dim과 다름"
	if (_weights[-1] as Array).size() != actions.size():
		return "마지막 층 출력 크기가 행동 수와 다름"
	return ""


func is_loaded() -> bool:
	return not _weights.is_empty()


func logits(observation: Array) -> PackedFloat64Array:
	var x := PackedFloat64Array(observation)
	var last := _weights.size() - 1
	for li in _weights.size():
		var rows: Array = _weights[li]
		var bias: PackedFloat64Array = _biases[li]
		var out := PackedFloat64Array()
		out.resize(rows.size())
		for o in rows.size():
			var row: PackedFloat64Array = rows[o]
			var acc := bias[o]
			for i in row.size():
				acc += row[i] * x[i]
			if li < last:
				acc = tanh(acc) if activation == "tanh" else maxf(acc, 0.0)
			out[o] = acc
		x = out
	return x


func predict(observation: Array) -> int:
	var z := logits(observation)
	var best := 0
	for i in range(1, z.size()):
		if z[i] > z[best]:
			best = i
	return best
