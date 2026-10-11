class_name DinoModel
extends Node3D
## Procedural low-poly dinosaur built from primitive meshes (no external assets).
## Herbivore: a small sauropod on four legs. Predator: a bipedal theropod.
## Model space is in metres and faces -Z (Godot forward). `animate()` drives the gait from the
## ground speed and poses neck/jaw/body from the server status code (explain.py LABELS).

const HERB_SKIN := Color("8f7650")
const HERB_BELLY := Color("d2c29a")
const PRED_SKIN := Color("9a4a2c")
const PRED_BELLY := Color("dcb88c")
const EYE := Color("1b1b1b")
const PRED_EYE := Color("e8c547")
const TOOTH := Color("f2efe4")

static var _meshes: Dictionary = {}

var species := "herbivore"
var hip := 1.7
var body: Node3D  # torso pivot (bob, lean, rest)
var neck: Node3D  # neck pivot (head down to eat / drink)
var jaw: Node3D = null
var legs: Array[Node3D] = []
var knees: Array[Node3D] = []
var leg_offsets: Array[float] = []
var tail: Array[Node3D] = []
var label: Label3D
var neck_up := 0.0
var _materials: Array[StandardMaterial3D] = []
var _phase := 0.0
var _dead := 0.0
var _dead_side := 1.0
var _darkened := false


func build(kind: String, agent_id: String, font: Font) -> void:
	species = kind
	var h := absi(agent_id.hash())
	var tint := 0.88 + float(h % 25) / 100.0  # individual colour variation
	_dead_side = 1.0 if h % 2 == 0 else -1.0
	body = Node3D.new()
	add_child(body)
	if kind == "predator":
		_build_predator(_mat(_shade(PRED_SKIN, tint)), _mat(PRED_BELLY))
	else:
		_build_herbivore(_mat(_shade(HERB_SKIN, tint)), _mat(HERB_BELLY))
	label = Label3D.new()
	label.font = font
	label.font_size = 56
	label.pixel_size = 0.007
	label.outline_size = 14
	label.outline_modulate = Color(0, 0, 0, 0.75)
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.position = Vector3(0, 5.6 if kind == "herbivore" else 4.9, 0)
	label.visible = false
	add_child(label)


func _build_herbivore(skin: StandardMaterial3D, belly: StandardMaterial3D) -> void:
	hip = 1.7
	body.position.y = hip
	_part(body, _sphere(), Vector3(0, 0.35, 0), Vector3.ZERO, Vector3(1.05, 0.9, 1.75), skin)
	_part(body, _sphere(), Vector3(0, 0.05, 0), Vector3.ZERO, Vector3(0.9, 0.7, 1.55), belly)
	# neck rises forward; head stays level by counter-rotating
	neck_up = deg_to_rad(50)
	neck = _pivot(body, Vector3(0, 0.75, -1.35), Vector3(neck_up, 0, 0))
	_part(neck, _capsule(0.34, 2.6), Vector3(0, 0, -1.05), Vector3(90, 0, 0), Vector3.ONE, skin)
	var head := _pivot(neck, Vector3(0, 0, -2.35), Vector3(-neck_up, 0, 0))
	head.set_meta("counter", true)
	_part(head, _sphere(), Vector3(0, 0, -0.25), Vector3.ZERO, Vector3(0.36, 0.32, 0.62), skin)
	_part(head, _sphere(), Vector3(0, -0.08, -0.6), Vector3.ZERO, Vector3(0.28, 0.2, 0.32), belly)
	for x in [-0.27, 0.27]:
		_part(head, _sphere(), Vector3(x, 0.1, -0.35), Vector3.ZERO, Vector3.ONE * 0.07, _mat(EYE))
	_tail(body, Vector3(0, 0.35, 1.5), [1.2, 1.1, 1.0, 0.9, 0.8], 0.42, 0.06, skin, 14.0)
	for p in [[-0.62, -0.95, 0.0], [0.62, -0.95, PI], [-0.62, 1.0, PI], [0.62, 1.0, 0.0]]:
		var leg := _pivot(body, Vector3(p[0], 0.0, p[1]), Vector3.ZERO)
		_part(leg, _cylinder(0.3, 0.26, hip), Vector3(0, -hip * 0.5, 0), Vector3.ZERO, Vector3.ONE, skin)
		_part(leg, _cylinder(0.3, 0.34, 0.14), Vector3(0, -hip + 0.07, -0.05), Vector3.ZERO,
			Vector3.ONE, belly)
		legs.append(leg)
		leg_offsets.append(p[2])


func _build_predator(skin: StandardMaterial3D, belly: StandardMaterial3D) -> void:
	hip = 2.1
	body.position.y = hip
	_part(body, _sphere(), Vector3(0, 0.3, -0.35), Vector3(-8, 0, 0), Vector3(0.78, 0.82, 1.5), skin)
	_part(body, _sphere(), Vector3(0, 0.05, -0.55), Vector3(-8, 0, 0), Vector3(0.62, 0.62, 1.2), belly)
	neck_up = deg_to_rad(28)
	neck = _pivot(body, Vector3(0, 0.75, -1.55), Vector3(neck_up, 0, 0))
	_part(neck, _capsule(0.38, 1.3), Vector3(0, 0, -0.4), Vector3(90, 0, 0), Vector3.ONE, skin)
	var head := _pivot(neck, Vector3(0, 0, -0.9), Vector3(-neck_up, 0, 0))
	head.set_meta("counter", true)
	_part(head, _box(), Vector3(0, 0.12, -0.55), Vector3.ZERO, Vector3(0.66, 0.55, 1.3), skin)
	_part(head, _box(), Vector3(0, 0.36, -0.25), Vector3.ZERO, Vector3(0.5, 0.12, 0.5), skin)
	for x in [-0.3, 0.3]:
		_part(head, _sphere(), Vector3(x, 0.28, -0.35), Vector3.ZERO, Vector3.ONE * 0.08, _mat(PRED_EYE))
	jaw = _pivot(head, Vector3(0, -0.12, -0.05), Vector3.ZERO)
	_part(jaw, _box(), Vector3(0, -0.06, -0.55), Vector3.ZERO, Vector3(0.56, 0.16, 1.15), belly)
	var tooth := _mat(TOOTH)
	for x in [-0.27, 0.27]:
		_part(head, _box(), Vector3(x, -0.12, -0.7), Vector3.ZERO, Vector3(0.04, 0.12, 0.9), tooth)
		_part(body, _capsule(0.08, 0.6), Vector3(x * 1.6, -0.05, -1.25), Vector3(60, 0, 0),
			Vector3.ONE, skin)  # tiny arms
	_tail(body, Vector3(0, 0.35, 0.9), [1.2, 1.15, 1.1, 1.0, 0.95], 0.48, 0.08, skin, 6.0)
	for p in [[-0.45, 0.0], [0.45, PI]]:
		var leg := _pivot(body, Vector3(p[0], 0.0, 0.1), Vector3.ZERO)
		_part(leg, _sphere(), Vector3(0, -0.35, 0), Vector3(-15, 0, 0), Vector3(0.36, 0.7, 0.5), skin)
		var knee := _pivot(leg, Vector3(0, -1.0, -0.15), Vector3.ZERO)
		_part(knee, _cylinder(0.17, 0.13, 1.1), Vector3(0, -0.5, 0.1), Vector3(-12, 0, 0),
			Vector3.ONE, skin)
		_part(knee, _box(), Vector3(0, -hip + 1.03, -0.15), Vector3.ZERO, Vector3(0.32, 0.1, 0.6), belly)
		legs.append(leg)
		knees.append(knee)
		leg_offsets.append(p[1])


func _tail(parent: Node3D, start: Vector3, lengths: Array, radius: float, tip: float,
		mat: StandardMaterial3D, droop_deg: float) -> void:
	var joint := _pivot(parent, start, Vector3(deg_to_rad(droop_deg), 0, 0))
	var n := lengths.size()
	for i in n:
		var length: float = lengths[i]
		var r := lerpf(radius, tip, float(i) / float(n - 1))
		_part(joint, _capsule(r, maxf(length + r, 2.0 * r)), Vector3(0, 0, length * 0.5),
			Vector3(90, 0, 0), Vector3.ONE, mat)
		tail.append(joint)
		if i < n - 1:
			joint = _pivot(joint, Vector3(0, 0, length * 0.9), Vector3.ZERO)


## speed: ground speed in m/s. status: status_code from the server.
func animate(delta: float, speed: float, status: String, alive: bool) -> void:
	if not alive:
		_die(delta)
		return
	var k := 1.0 - exp(-8.0 * delta)
	var stride := clampf(speed * 0.11, 0.0, 0.75)
	_phase += delta * (1.5 + speed * (1.4 if species == "herbivore" else 1.1))
	for i in legs.size():
		var swing := sin(_phase + leg_offsets[i])
		legs[i].rotation.x = swing * stride
		if i < knees.size():
			knees[i].rotation.x = maxf(0.0, -cos(_phase + leg_offsets[i])) * stride * 1.2
	var resting := status == "resting" or status == "low_energy"
	var bob := absf(sin(_phase)) * stride * 0.18
	var breathe := sin(Time.get_ticks_msec() * 0.002) * 0.03
	var target_y := hip * (0.62 if resting else 1.0) + bob + breathe
	body.position.y = lerpf(body.position.y, target_y, k)
	var lean := -stride * 0.1 if species == "predator" else 0.0
	body.rotation.x = lerpf(body.rotation.x, lean, k)
	# head down while feeding or drinking in place
	var feeding := speed < 0.8 and (status == "foraging" or status == "seeking_water")
	var neck_target := neck_up
	if feeding:
		neck_target = deg_to_rad(-35) + sin(Time.get_ticks_msec() * 0.004) * 0.08
	elif status == "fleeing":
		neck_target = neck_up * 0.6
	elif status == "attacking":
		neck_target = neck_up - 0.4 + sin(Time.get_ticks_msec() * 0.02) * 0.2
	neck.rotation.x = lerpf(neck.rotation.x, neck_target, k)
	for c in neck.get_children():
		if c.has_meta("counter"):
			c.rotation.x = -neck.rotation.x * 0.85
	if jaw != null:
		var open := 0.0
		if status == "attacking" or status == "chasing":
			open = 0.35 + 0.2 * sin(Time.get_ticks_msec() * 0.015)
		jaw.rotation.x = lerpf(jaw.rotation.x, open, k)
	for i in tail.size():
		tail[i].rotation.y = sin(_phase * 0.5 + i * 0.7) * (0.05 + stride * 0.12)


func _die(delta: float) -> void:
	_dead = minf(1.0, _dead + delta * 1.2)
	var t := ease(_dead, 0.4)
	rotation.z = t * PI * 0.5 * _dead_side
	body.position.y = lerpf(body.position.y, hip * 0.55, t)
	for leg in legs:
		leg.rotation.x = lerpf(leg.rotation.x, 0.3, t)
	if not _darkened:
		_darkened = true
		for m in _materials:
			m.albedo_color = m.albedo_color.darkened(0.45)


func _mat(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = 0.85
	_materials.append(m)
	return m


func _pivot(parent: Node3D, pos: Vector3, rot: Vector3) -> Node3D:
	var n := Node3D.new()
	n.position = pos
	n.rotation = rot
	parent.add_child(n)
	return n


func _part(parent: Node3D, mesh: Mesh, pos: Vector3, rot_deg: Vector3, scl: Vector3,
		mat: StandardMaterial3D) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.rotation_degrees = rot_deg
	mi.scale = scl
	parent.add_child(mi)
	return mi


static func _sphere() -> Mesh:
	if not _meshes.has("sphere"):
		var m := SphereMesh.new()
		m.radius = 1.0
		m.height = 2.0
		m.radial_segments = 16
		m.rings = 8
		_meshes["sphere"] = m
	return _meshes["sphere"]


static func _box() -> Mesh:
	if not _meshes.has("box"):
		var m := BoxMesh.new()
		m.size = Vector3.ONE
		_meshes["box"] = m
	return _meshes["box"]


static func _capsule(radius: float, height: float) -> Mesh:
	var key := "capsule:%.2f:%.2f" % [radius, height]
	if not _meshes.has(key):
		var m := CapsuleMesh.new()
		m.radius = radius
		m.height = maxf(height, radius * 2.0)
		m.radial_segments = 12
		m.rings = 4
		_meshes[key] = m
	return _meshes[key]


static func _cylinder(top: float, bottom: float, height: float) -> Mesh:
	var key := "cyl:%.2f:%.2f:%.2f" % [top, bottom, height]
	if not _meshes.has(key):
		var m := CylinderMesh.new()
		m.top_radius = top
		m.bottom_radius = bottom
		m.height = height
		m.radial_segments = 10
		m.rings = 1
		_meshes[key] = m
	return _meshes[key]


static func _shade(c: Color, f: float) -> Color:
	return Color(c.r * f, c.g * f, c.b * f, c.a)
