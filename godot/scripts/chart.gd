class_name LineChart
extends Control
## Live series: herbivores alive, predator energy (0..100) and, on the ecosystem map,
## predators alive. Count series scale to the largest value seen (at least 8 / 4).
## Long runs are thinned to MAX_POINTS by dropping every other point.

const COLOR_HERB := Color("4f9a53")
const COLOR_ENERGY := Color("d6a03a")
const COLOR_PRED := Color("c4472f")
const COLOR_GRID := Color(0.5, 0.5, 0.5, 0.25)
const MAX_POINTS := 1500

var show_predators := false
var _ticks: PackedFloat32Array = []
var _herbs: PackedFloat32Array = []
var _energy: PackedFloat32Array = []
var _preds: PackedFloat32Array = []


func clear() -> void:
	_ticks.clear()
	_herbs.clear()
	_energy.clear()
	_preds.clear()
	queue_redraw()


func add_point(tick: int, herbivores: float, energy: float, predators: float = 1.0) -> void:
	_ticks.append(tick)
	_herbs.append(herbivores)
	_energy.append(energy)
	_preds.append(predators)
	if _ticks.size() > MAX_POINTS:
		_ticks = _thin(_ticks)
		_herbs = _thin(_herbs)
		_energy = _thin(_energy)
		_preds = _thin(_preds)
	queue_redraw()


func _thin(values: PackedFloat32Array) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	for i in range(0, values.size(), 2):
		out.append(values[i])
	return out


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), COLOR_GRID, false, 1.0)
	if _ticks.size() < 2:
		return
	_series(_herbs, maxf(8.0, _max(_herbs)), COLOR_HERB)
	if show_predators:
		_series(_preds, maxf(4.0, _max(_preds)), COLOR_PRED)
	else:
		_series(_energy, 100.0, COLOR_ENERGY)


func _max(values: PackedFloat32Array) -> float:
	var m := 0.0
	for v in values:
		m = maxf(m, v)
	return m


func _series(values: PackedFloat32Array, max_value: float, color: Color) -> void:
	var t0 := _ticks[0]
	var t1: float = max(_ticks[_ticks.size() - 1], t0 + 1.0)
	var pts := PackedVector2Array()
	for i in _ticks.size():
		var x := (_ticks[i] - t0) / (t1 - t0) * size.x
		var y := size.y - values[i] / max_value * (size.y - 4.0) - 2.0
		pts.append(Vector2(x, y))
	draw_polyline(pts, color, 2.0, true)
