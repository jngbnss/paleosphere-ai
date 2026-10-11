from collections import Counter

from paleosphere.config import load_world_config
from paleosphere.core.events import EventKind
from paleosphere.core.world import World
from paleosphere.entities import DeathCause, Species
from paleosphere.policies import RuleBasedHerbivore, RuleBasedPredator


def run(world: World, ticks: int) -> Counter:
    herb, pred = RuleBasedHerbivore(), RuleBasedPredator()
    events: Counter = Counter()
    while world.tick < ticks and not world.done:
        actions = {
            d.agent_id: (pred if d.species == Species.PREDATOR else herb).act(world, d.agent_id)
            for d in world.alive()
        }
        for e in world.step(actions):
            events[e.kind] += 1
    return events


def test_ecosystem_is_deterministic():
    cfg = load_world_config("ecosystem")
    a, b = World(cfg, 3), World(cfg, 3)
    run(a, 1500)
    run(b, 1500)
    assert a.snapshot_hash() == b.snapshot_hash()
    c = World(cfg, 4)
    run(c, 1500)
    assert c.snapshot_hash() != a.snapshot_hash()


def test_births_create_new_individuals():
    world = World(load_world_config("ecosystem"), 3)
    events = run(world, 1500)
    assert events[EventKind.BIRTH] > 0
    children = [d for d in world.dinos.values() if d.parent_id is not None]
    assert children and all(d.generation >= 1 for d in children)
    assert len({d.agent_id for d in world.dinos.values()}) == len(world.dinos)
    snap = world.to_snapshot()["dinos"][0]
    assert {"generation", "parent_id", "breed_cooldown"} <= snap.keys()


def test_fixed_population_worlds_are_unchanged():
    world = World(load_world_config("map_a"), 3)
    assert world.config.reproduction is None
    assert "generation" not in world.to_snapshot()["dinos"][0]


def test_population_cap_respected():
    cfg = load_world_config(
        "ecosystem", reproduction={"herbivore": {"max_population": 13, "chance": 1.0,
                                                 "min_age": 0}}
    )
    world = World(cfg, 1)
    for _ in range(300):
        run(world, world.tick + 1)
        assert len(world.alive(Species.HERBIVORE)) <= 13


def test_old_age_and_corpse_pruning():
    cfg = load_world_config(
        "ecosystem",
        reproduction={"herbivore": {"max_age": 20}, "predator": {"max_age": 20},
                      "prune_dead_after": 5},
    )
    world = World(cfg, 2)
    run(world, 21)
    dead = [d for d in world.dinos.values() if not d.alive]
    assert dead and all(d.death_cause == DeathCause.OLD_AGE for d in dead)
    assert world.done  # everyone died of old age
    world.step({})
    run_ticks = world.tick
    for _ in range(6):
        world.step({})
    assert world.tick == run_ticks + 6
    assert not world.dinos  # all corpses pruned
