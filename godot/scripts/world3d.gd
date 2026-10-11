class_name SimWorld3D
extends Node3D
## 3D rendering of server snapshots: terrain, water, food plants, rocks, sky with day/night and
## procedural dinosaurs (DinoModel). The sim map (x, z) maps to 3D (x*S, 0, z*S) in metres.
## Dino positions are interpolated between snapshots like the 2D WorldView.

const S := 2.0  # metres per sim unit
const MAX_FOOD := 60.0
const SPREAD_DIST := 4.5  # metres between models before they are nudged apart
const SPREAD_MAX := 4.0
const GRASS := Color("557a32")
const GRASS_DARK := Color("3b5a24")
const SAND := Color("9c8a62")
const WATER := Color(0.12, 0.32, 0.48, 0.9)
const ROCK := Color("6c675f")
const DAY_TOP := Color(0.3, 0.5, 0.78)
const DAY_HORIZON := Color(0.74, 0.8, 0.84)
const NIGHT_TOP := Color(0.02, 0.03, 0.08)
const NIGHT_HORIZON := Color(0.08, 0.1, 0.17)

var font: Font
var map_size := 64.0
var snapshot: Dictionary = {}
var dinos: Dictionary = {}  # agent_id -> DinoModel
var states: Dictionary = {}  # agent_id -> latest DinoState dict
var blockers: Array = []  # [Vector2 centre (m), radius (m)] for the walking researcher

var _env: Environment
var _sky: ProceduralSkyMaterial
var _sun: DirectionalLight3D
var _static: Node3D
var _plants: Dictionary = {}  # plant_id -> [Node3D, StandardMaterial3D]
var _world_key := ""
var _prev: Dictionary = {}
var _curr: Dictionary = {}
var _since := 0.0
var _interval := 0.2
var _night := 0.0
var _offset: Dictionary = {}  # agent_id -> display-only spacing (see _spread)


func _ready() -> void:
	_sky = ProceduralSkyMaterial.new()
	_sky.sky_top_color = DAY_TOP
	_sky.sky_horizon_color = DAY_HORIZON
	_sky.ground_horizon_color = DAY_HORIZON
	_sky.ground_bottom_color = GRASS_DARK
	var sky := Sky.new()
	sky.sky_material = _sky
	_env = Environment.new()
	_env.background_mode = Environment.BG_SKY
	_env.sky = sky
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	_env.ambient_light_energy = 0.3
	_env.tonemap_mode = Environment.TONE_MAPPER_ACES
	_env.fog_enabled = true
	_env.fog_light_color = DAY_HORIZON
	_env.fog_density = 0.004
	_env.fog_sky_affect = 0.3
	var we := WorldEnvironment.new()
	we.environment = _env
	add_child(we)
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	_sun.directional_shadow_max_distance = 140.0
	_sun.rotation_degrees = Vector3(-50, 30, 0)
	add_child(_sun)
	_static = Node3D.new()
	add_child(_static)


func to3d(p: Array) -> Vector3:
	return Vector3(float(p[0]) * S, 0.0, float(p[1]) * S)


func dino_position(id: String) -> Vector3:
	var a: Vector3 = _prev.get(id, _curr.get(id, Vector3.ZERO))
	var b: Vector3 = _curr.get(id, a)
	return a.lerp(b, clampf(_since / _interval, 0.0, 1.0))


func set_snapshot(s: Dictionary) -> void:
	var key := "%s:%s" % [s["seed"], s["map"]]
	var fresh := key != _world_key or int(s["tick"]) < int(snapshot.get("tick", 0))
	if key != _world_key:
		_world_key = key
		_rebuild(s)
	var seen := {}
	for d in s["dinos"]:
		var id := String(d["agent_id"])
		seen[id] = true
		states[id] = d
		var target := to3d(d["position"])
		_prev[id] = target if (fresh or not _curr.has(id)) else dino_position(id)
		_curr[id] = target
		if not dinos.has(id):
			var m := DinoModel.new()
			m.build(String(d["species"]), id, font)
			m.position = target
			add_child(m)
			dinos[id] = m
	for id in dinos.keys():
		if not seen.has(id):  # pruned corpse or new episode
			dinos[id].queue_free()
			dinos.erase(id)
			states.erase(id)
			_prev.erase(id)
			_curr.erase(id)
			_offset.erase(id)
	for p in s["plants"]:
		var entry: Array = _plants.get(String(p["plant_id"]), [])
		if entry.is_empty():
			continue
		var f := clampf(float(p["food"]) / MAX_FOOD, 0.0, 1.0)
		var root: Node3D = entry[0]
		root.scale = Vector3.ONE * (0.35 + 0.65 * f)
		var mat: StandardMaterial3D = entry[1]
		mat.albedo_color = Color("8a7a45").lerp(Color("3f7a2e"), f)
	snapshot = s
	_since = 0.0
	_interval = 1.0 / maxf(float(s.get("ticks_per_second", 5.0)), 0.1)


func _process(delta: float) -> void:
	if snapshot.is_empty():
		return
	_since += delta
	var paused := bool(snapshot.get("paused", false))
	_spread(delta)
	for id in dinos:
		var m: DinoModel = dinos[id]
		var d: Dictionary = states[id]
		var pos := dino_position(id)
		var step: Vector3 = _curr.get(id, pos) - _prev.get(id, pos)
		var speed := 0.0 if paused or _since > _interval * 1.5 else step.length() / _interval
		var alive := bool(d["alive"])
		if alive and step.length() > 0.01:
			var yaw := atan2(-step.x, -step.z)
			m.rotation.y = lerp_angle(m.rotation.y, yaw, 1.0 - exp(-6.0 * delta))
		m.position = pos + _offset.get(id, Vector3.ZERO)
		m.animate(delta, speed, String(d.get("status_code", "")), alive)
	# day / night
	var target := 1.0 if bool(snapshot.get("is_night", false)) else 0.0
	_night = move_toward(_night, target, delta * 0.5)
	_sky.sky_top_color = DAY_TOP.lerp(NIGHT_TOP, _night)
	_sky.sky_horizon_color = DAY_HORIZON.lerp(NIGHT_HORIZON, _night)
	_sky.ground_horizon_color = _sky.sky_horizon_color
	_env.fog_light_color = _sky.sky_horizon_color
	_env.ambient_light_energy = lerpf(0.3, 0.1, _night)
	_sun.light_energy = lerpf(0.75, 0.12, _night)
	_sun.light_color = Color(1.0, 0.96, 0.88).lerp(Color(0.6, 0.7, 1.0), _night)
	_sun.rotation_degrees.y = 30.0 + float(int(snapshot["tick"]) % 400) / 400.0 * 120.0


func display_position(id: String) -> Vector3:
	return dino_position(id) + _offset.get(id, Vector3.ZERO)


func _spread(delta: float) -> void:
	"""Display only: the sim has no dino-dino collision, so herds stack on one spot.
	Nudge living models apart (at most SPREAD_MAX metres); the simulation is untouched."""
	var ids := []
	var pos := []
	for id in dinos:
		if bool(states[id]["alive"]):
			ids.append(id)
			pos.append(dino_position(id) + _offset.get(id, Vector3.ZERO))
	var k := 1.0 - exp(-3.0 * delta)
	for i in ids.size():
		var push := Vector3.ZERO
		for j in ids.size():
			if i == j:
				continue
			var away: Vector3 = pos[i] - pos[j]
			away.y = 0.0
			var dist := away.length()
			if dist < SPREAD_DIST:
				if dist < 0.01:  # exactly stacked: split by id order
					away = Vector3(1, 0, 0).rotated(Vector3.UP, float(i) * 2.4)
					dist = 0.01
				push += away / dist * (SPREAD_DIST - dist)
		var off: Vector3 = _offset.get(ids[i], Vector3.ZERO)
		off = off.lerp((off + push * 0.5).limit_length(SPREAD_MAX), k)
		_offset[ids[i]] = off


# -------------------------------------------------------------------- static scenery
func _rebuild(s: Dictionary) -> void:
	for c in _static.get_children():
		c.queue_free()
	for id in dinos:
		dinos[id].queue_free()
	dinos.clear()
	states.clear()
	_prev.clear()
	_curr.clear()
	_offset.clear()
	_plants.clear()
	blockers.clear()
	map_size = float(s["map_size"])
	var size := map_size * S
	var rng := RandomNumberGenerator.new()
	rng.seed = int(s["seed"]) * 7919 + 17

	# ground: one large noise-textured plane; the map is the central square
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(size + 400.0, size + 400.0)
	ground.mesh = plane
	ground.position = Vector3(size * 0.5, 0, size * 0.5)
	var noise := FastNoiseLite.new()
	noise.seed = rng.randi()
	noise.frequency = 0.02
	var tex := NoiseTexture2D.new()
	tex.width = 512
	tex.height = 512
	tex.seamless = true
	tex.noise = noise
	var ramp := Gradient.new()
	ramp.set_color(0, GRASS_DARK)
	ramp.set_color(1, GRASS)
	tex.color_ramp = ramp
	var gmat := StandardMaterial3D.new()
	gmat.albedo_texture = tex
	gmat.uv1_scale = Vector3(30, 30, 1)
	gmat.roughness = 1.0
	ground.material_override = gmat
	_static.add_child(ground)

	for w in s["waters"]:
		var c := to3d(w["position"])
		var r := float(w["radius"]) * S
		_disc(c + Vector3(0, 0.02, 0), r + 1.8, 0.02, _flat(SAND))
		var wm := _flat(WATER)
		wm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		wm.roughness = 0.05
		wm.metallic = 0.3
		_disc(c + Vector3(0, 0.06, 0), r, 0.04, wm)
		blockers.append([Vector2(c.x, c.z), r])

	for r in s["rocks"]:
		var c := to3d(r["position"])
		var rad := float(r["radius"]) * S
		var mat := _flat(ROCK.darkened(rng.randf() * 0.25))
		_blob(c + Vector3(0, rad * 0.2, 0), Vector3(rad, rad * 0.75, rad * 0.9), rng.randf() * TAU, mat)
		for k in 2:
			var off := Vector3(rng.randf_range(-1, 1), 0, rng.randf_range(-1, 1)).normalized() * rad
			var small := rad * rng.randf_range(0.25, 0.4)
			_blob(c + off + Vector3(0, small * 0.2, 0), Vector3.ONE * small, rng.randf() * TAU, mat)
		blockers.append([Vector2(c.x, c.z), rad])

	for p in s["plants"]:
		var c := to3d(p["position"])
		var rad := float(p["radius"]) * S
		_disc(c + Vector3(0, 0.03, 0), rad, 0.02, _flat(GRASS_DARK.darkened(0.15)))
		var root := Node3D.new()
		root.position = c
		_static.add_child(root)
		var mat := _flat(Color("3f7a2e"))
		for k in 6:
			var off := Vector3(rng.randf_range(-1, 1), 0, rng.randf_range(-1, 1)) * rad * 0.7
			var b := rng.randf_range(0.6, 1.1)
			_blob_in(root, off + Vector3(0, b * 0.6, 0), Vector3(b, b * 0.85, b), 0.0, mat)
			_blob_in(root, off + Vector3(b * 0.5, b * 0.4, 0.2), Vector3.ONE * b * 0.6, 0.0, mat)
		_plants[String(p["plant_id"])] = [root, mat]

	_scatter_grass(rng, size)
	_border_trees(rng, size)


func _scatter_grass(rng: RandomNumberGenerator, size: float) -> void:
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.07
	cone.height = 0.5
	cone.radial_segments = 4
	cone.rings = 1
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = cone
	var spots: Array[Transform3D] = []
	while spots.size() < 3500:
		var p := Vector3(rng.randf() * size, 0, rng.randf() * size)
		if _blocked(Vector2(p.x, p.z), 1.5):
			continue
		var h := rng.randf_range(0.4, 1.2)
		spots.append(Transform3D(Basis().scaled(Vector3(1, h, 1)), p + Vector3(0, 0.25 * h, 0)))
	mm.instance_count = spots.size()
	for i in spots.size():
		mm.set_instance_transform(i, spots[i])
		mm.set_instance_color(i, GRASS.lerp(Color("8a9a45"), rng.randf()))
	_multimesh(mm)


func _border_trees(rng: RandomNumberGenerator, size: float) -> void:
	var trunk := CylinderMesh.new()
	trunk.top_radius = 0.25
	trunk.bottom_radius = 0.4
	trunk.height = 1.0
	trunk.radial_segments = 6
	var crown := CylinderMesh.new()  # conifer cone
	crown.top_radius = 0.0
	crown.bottom_radius = 1.0
	crown.height = 1.0
	crown.radial_segments = 7
	var trunks := MultiMesh.new()
	trunks.transform_format = MultiMesh.TRANSFORM_3D
	trunks.use_colors = true
	trunks.mesh = trunk
	var crowns := MultiMesh.new()
	crowns.transform_format = MultiMesh.TRANSFORM_3D
	crowns.use_colors = true
	crowns.mesh = crown
	var t_list: Array[Transform3D] = []
	var c_list: Array[Transform3D] = []
	var colors: Array[Color] = []
	var n := 260
	for i in n:
		# a band of forest just outside the map edge (and a few further out)
		var along := rng.randf() * size
		var depth := rng.randf_range(3.0, 45.0) * (1.0 + rng.randf() * rng.randf() * 3.0)
		var side := i % 4
		var p := Vector3.ZERO
		match side:
			0: p = Vector3(along, 0, -depth)
			1: p = Vector3(along, 0, size + depth)
			2: p = Vector3(-depth, 0, along)
			_: p = Vector3(size + depth, 0, along)
		var h := rng.randf_range(7.0, 16.0)
		var w := h * rng.randf_range(0.22, 0.32)
		t_list.append(Transform3D(Basis().scaled(Vector3(1, h * 0.35, 1)), p + Vector3(0, h * 0.175, 0)))
		c_list.append(Transform3D(Basis().scaled(Vector3(w, h * 0.8, w)), p + Vector3(0, h * 0.6, 0)))
		colors.append(Color("2f5a2a").lerp(Color("4c7a35"), rng.randf()))
	trunks.instance_count = n
	crowns.instance_count = n
	for i in n:
		trunks.set_instance_transform(i, t_list[i])
		trunks.set_instance_color(i, Color("5a4330"))
		crowns.set_instance_transform(i, c_list[i])
		crowns.set_instance_color(i, colors[i])
	_multimesh(trunks)
	_multimesh(crowns)


func _blocked(p: Vector2, margin: float) -> bool:
	for b in blockers:
		if p.distance_to(b[0]) < float(b[1]) + margin:
			return true
	return false


func _multimesh(mm: MultiMesh) -> void:
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	var mat := StandardMaterial3D.new()
	mat.vertex_color_use_as_albedo = true
	mat.roughness = 0.95
	mmi.material_override = mat
	_static.add_child(mmi)


func _flat(c: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = c
	m.roughness = 0.9
	return m


func _disc(pos: Vector3, radius: float, height: float, mat: StandardMaterial3D) -> void:
	var cyl := CylinderMesh.new()
	cyl.top_radius = radius
	cyl.bottom_radius = radius
	cyl.height = height
	cyl.radial_segments = 40
	cyl.rings = 1
	var mi := MeshInstance3D.new()
	mi.mesh = cyl
	mi.material_override = mat
	mi.position = pos
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_static.add_child(mi)


func _blob(pos: Vector3, scl: Vector3, yaw: float, mat: StandardMaterial3D) -> void:
	_blob_in(_static, pos, scl, yaw, mat)


func _blob_in(parent: Node3D, pos: Vector3, scl: Vector3, yaw: float, mat: StandardMaterial3D) -> void:
	var sph := SphereMesh.new()
	sph.radial_segments = 9
	sph.rings = 5
	var mi := MeshInstance3D.new()
	mi.mesh = sph
	mi.material_override = mat
	mi.position = pos
	mi.rotation.y = yaw
	mi.scale = scl * 2.0  # SphereMesh default radius 0.5
	parent.add_child(mi)
