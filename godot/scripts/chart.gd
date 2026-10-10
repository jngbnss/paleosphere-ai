class_name LineChart
extends Control
## Two live series: herbivores alive (0..8) and predator energy (0..100).

const COLOR_HERB := Color("4f9a53")
const COLOR_ENERGY := Color("d6a03a")
const COLOR_GRID := Color(0.5, 0.5, 0.5, 0.25)

var _ticks: PackedFloat32Array = []
var _herbs: PackedFloat32Array = []
var _energy: PackedFloat32Array = []


func clear() -> void:
	_ticks.clear()
	_herbs.clear()
	_energy.clear()
	queue_redraw()


func add_point(tick: int, herbivores: float, energy: float) -> void:
	_ticks.append(tick)
	_herbs.append(herbivores)
	_energy.append(energy)
	queue_redraw()


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), COLOR_GRID, false, 1.0)
	if _ticks.size() < 2:
		return
	_series(_herbs, 8.0, COLOR_HERB)
	_series(_energy, 100.0, COLOR_ENERGY)


func _series(values: PackedFloat32Array, max_value: float, color: Color) -> void:
	var t0 := _ticks[0]
	var t1: float = max(_ticks[_ticks.size() - 1], t0 + 1.0)
	var pts := PackedVector2Array()
	for i in _ticks.size():
		var x := (_ticks[i] - t0) / (t1 - t0) * size.x
		var y := size.y - values[i] / max_value * (size.y - 4.0) - 2.0
		pts.append(Vector2(x, y))
	draw_polyline(pts, color, 2.0, true)
