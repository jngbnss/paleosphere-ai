import numpy as np
import pytest

from paleosphere.combat import AttackOutcome, resolve_attack
from paleosphere.config import load_world_config
from paleosphere.core.events import EventKind
from paleosphere.core.world import World
from paleosphere.entities import DeathCause, Dino, Species
from paleosphere.policies.actions import PredatorAction


class AlwaysHit:
    def random(self):
        return 0.0


class AlwaysMiss:
    def random(self):
        return 0.999


@pytest.fixture
def cfg():
    return load_world_config("map_a").combat


def pair(gap=1.0):
    pred = Dino("predator-000", Species.PREDATOR, np.array([10.0, 10.0]), hunger=80.0, energy=50.0)
    prey = Dino("herbivore-000", Species.HERBIVORE, np.array([10.0 + gap, 10.0]))
    return pred, prey


def test_out_of_range(cfg):
    pred, prey = pair(gap=cfg.attack_range + 0.5)
    assert resolve_attack(pred, prey, cfg, AlwaysHit()).outcome == AttackOutcome.OUT_OF_RANGE
    assert pred.attack_cooldown == 0


def test_no_target(cfg):
    pred, _ = pair()
    assert resolve_attack(pred, None, cfg, AlwaysHit()).outcome == AttackOutcome.NO_TARGET


def test_cooldown_blocks_second_attack(cfg):
    pred, prey = pair()
    assert resolve_attack(pred, prey, cfg, AlwaysHit()).outcome == AttackOutcome.HIT
    assert pred.attack_cooldown == cfg.attack_cooldown
    assert resolve_attack(pred, prey, cfg, AlwaysHit()).outcome == AttackOutcome.ON_COOLDOWN


def test_miss_still_costs_energy_and_cooldown(cfg):
    pred, prey = pair()
    out = resolve_attack(pred, prey, cfg, AlwaysMiss())
    assert out.outcome == AttackOutcome.MISS
    assert pred.energy == 50.0 - cfg.attack_energy_cost
    assert prey.health == 100.0


def test_kill_feeds_predator(cfg):
    pred, prey = pair()
    resolve_attack(pred, prey, cfg, AlwaysHit())
    pred.attack_cooldown = 0
    out = resolve_attack(pred, prey, cfg, AlwaysHit())
    assert out.outcome == AttackOutcome.KILL
    assert pred.hunger == 80.0 - cfg.kill_hunger_reduction


def test_sprinting_prey_harder_to_hit(cfg):
    assert cfg.hit_chance_vs_sprinting < cfg.hit_chance_vs_walking


def test_world_kill_records_predation():
    world = World(load_world_config("map_a"), 42)
    pred = world.alive(Species.PREDATOR)[0]
    prey = world.alive(Species.HERBIVORE)[0]
    pred.pos = prey.pos + np.array([1.0, 0.0])
    world._update_targets()
    prey.health = 1.0
    events = []
    for _ in range(40):  # enough attempts despite misses
        events += world.step({pred.agent_id: PredatorAction.ATTACK, prey.agent_id: 4})
        if not prey.alive:
            break
    assert not prey.alive
    assert prey.death_cause == DeathCause.PREDATION
    assert any(e.kind == EventKind.KILL for e in events)


def test_world_invalid_attack_event():
    world = World(load_world_config("map_a"), 42)
    pred = world.alive(Species.PREDATOR)[0]
    events = world.step({pred.agent_id: PredatorAction.ATTACK})
    assert any(e.kind == EventKind.ATTACK_INVALID for e in events)
