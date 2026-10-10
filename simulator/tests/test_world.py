import numpy as np

from paleosphere.config import load_world_config
from paleosphere.core.events import EventKind
from paleosphere.core.metabolism import apply_metabolism
from paleosphere.core.world import World
from paleosphere.entities import DeathCause, Dino, Species
from paleosphere.policies.actions import HerbivoreAction, PredatorAction


def make_world(seed=42, **overrides):
    return World(load_world_config("map_a", **overrides), seed)


def test_idle_world_dies_of_starvation_or_thirst():
    world = make_world()
    for _ in range(2500):
        if not world.alive():
            break
        world.step({})  # everyone RESTs
    assert not world.alive()
    causes = {d.death_cause for d in world.dinos.values()}
    assert causes <= {DeathCause.STARVATION, DeathCause.DEHYDRATION}


def test_rest_recovers_energy_and_moving_costs_energy():
    cfg = load_world_config("map_a")
    sp = cfg.species["predator"]
    d = Dino("p", Species.PREDATOR, np.zeros(2), energy=50.0)
    apply_metabolism(d, sp, cfg.metabolism, resting=True, moved=False)
    assert d.energy == 50.0 + sp.energy_rest_gain
    d.sprinting = True
    apply_metabolism(d, sp, cfg.metabolism, resting=False, moved=True)
    assert d.energy == 50.0 + sp.energy_rest_gain - sp.energy_sprint_cost


def test_exhaustion_damages_health():
    cfg = load_world_config("map_a")
    d = Dino("p", Species.PREDATOR, np.zeros(2), energy=0.0, health=0.1)
    cause = apply_metabolism(d, cfg.species["predator"], cfg.metabolism, False, True)
    assert cause == DeathCause.EXHAUSTION


def test_day_night_cycle():
    world = make_world()
    t = world.config.time
    night_start = int(t.day_length * (1 - t.night_fraction))
    seen = []
    for _ in range(t.day_length):
        seen.append(world.is_night)
        world.step({})
    assert seen[0] is False
    assert seen[night_start] is True
    assert seen[night_start - 1] is False


def test_herbivore_drinks_at_water():
    world = make_world()
    herb = world.alive(Species.HERBIVORE)[0]
    water = world.waters[0]
    herb.pos = water.pos.copy()
    herb.thirst = 50.0
    events = world.step({herb.agent_id: HerbivoreAction.GO_TO_WATER})
    assert any(e.kind == EventKind.DRINK and e.agent_id == herb.agent_id for e in events)
    assert herb.thirst < 50.0


def test_herbivore_eats_plant():
    world = make_world()
    herb = world.alive(Species.HERBIVORE)[0]
    plant = max(world.plants, key=lambda p: p.food)
    herb.pos = plant.pos.copy()
    herb.hunger = 60.0
    food_before = plant.food
    world.step({herb.agent_id: HerbivoreAction.GO_TO_FOOD})
    assert herb.hunger < 60.0
    assert plant.food < food_before + plant.regrow_per_tick


def test_predator_chase_moves_faster_than_walk():
    world = make_world()
    pred = world.alive(Species.PREDATOR)[0]
    herb = world.alive(Species.HERBIVORE)[0]
    pred.pos = herb.pos + np.array([8.0, 0.0])
    world._update_targets()
    assert pred.target_id is not None
    world.step({pred.agent_id: PredatorAction.CHASE})
    assert pred.sprinting
    assert pred.speed > world.config.species["predator"].walk_speed


def test_give_up_ignores_target():
    world = make_world()
    pred = world.alive(Species.PREDATOR)[0]
    herb = world.alive(Species.HERBIVORE)[0]
    pred.pos = herb.pos + np.array([5.0, 0.0])
    world._update_targets()
    target = pred.target_id
    world.step({pred.agent_id: PredatorAction.GIVE_UP})
    assert pred.target_id != target
    assert pred.chase_ticks == 0


def test_positions_stay_in_bounds():
    world = make_world(seed=5)
    for _ in range(300):
        world.step({d.agent_id: 0 for d in world.alive()})  # SEARCH / WANDER
    for d in world.alive():
        assert 0.0 <= d.pos[0] <= world.size and 0.0 <= d.pos[1] <= world.size
        for r in world.rocks:
            assert np.linalg.norm(d.pos - r.pos) >= r.radius
