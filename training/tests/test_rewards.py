import itertools
import math

import numpy as np
import pytest

from paleosphere.config import load_world_config
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.policies import PredatorAction, RandomPolicy, RuleBasedHerbivore
from paleosphere.policies.observation import predator_view
from training.rewards import REWARD_COMPONENTS, PredatorReward, load_reward_config


@pytest.fixture
def setup():
    world = World(load_world_config("map_a"), 42)
    pid = world.alive(Species.PREDATOR)[0].agent_id
    reward = PredatorReward(load_reward_config("v0"), world.config.species["predator"].vision)
    return world, pid, reward


def step(world, pid, action, reward):
    herb = RuleBasedHerbivore()
    before = predator_view(world, pid)
    actions = {d.agent_id: herb.act(world, d.agent_id) for d in world.alive(Species.HERBIVORE)}
    actions[pid] = int(action)
    events = world.step(actions)
    after = predator_view(world, pid) if world.dinos[pid].alive else None
    return reward.compute(before, after, world, pid, events)


def test_components_present_and_sum(setup):
    world, pid, reward = setup
    r = step(world, pid, PredatorAction.SEARCH, reward)
    assert set(REWARD_COMPONENTS) <= set(r)
    assert math.isclose(r["total_reward"], sum(r[c] for c in REWARD_COMPONENTS))


def test_rewards_finite_under_random_policy(setup):
    world, pid, reward = setup
    policy = RandomPolicy(PredatorAction, 0)
    for _ in range(1500):
        if not world.dinos[pid].alive:
            break
        r = step(world, pid, policy.act(world, pid), reward)
        assert all(np.isfinite(v) for v in r.values())


def test_invalid_attack_penalized(setup):
    world, pid, reward = setup
    r = step(world, pid, PredatorAction.ATTACK, reward)
    assert r["invalid_attack_penalty"] < 0


def test_kill_rewarded(setup):
    world, pid, reward = setup
    pred = world.dinos[pid]
    prey = world.alive(Species.HERBIVORE)[0]
    pred.pos = prey.pos + np.array([1.0, 0.0])
    world._update_targets()
    prey.health = 1.0
    world.combat_rng = type("Hit", (), {"random": lambda self: 0.0})()
    r = step(world, pid, PredatorAction.ATTACK, reward)
    assert r["hunt_reward"] == 10.0


def test_shaping_is_potential_based(setup):
    """Approaching then retreating to the same distance nets ~0 (no shadowing farm)."""
    _, _, reward = setup

    class V:
        def __init__(self, d):
            self.target_id = "h"
            self.prey_distance = d

    gamma = reward.cfg.shaping_gamma
    loop = [10.0, 5.0, 10.0]
    total = sum(
        gamma * reward.potential(V(b)) - reward.potential(V(a)) for a, b in itertools.pairwise(loop)
    )
    assert total <= 1e-12


def test_death_penalty(setup):
    world, pid, reward = setup
    pred = world.dinos[pid]
    pred.health, pred.hunger = 0.1, 100.0
    r = step(world, pid, PredatorAction.REST, reward)
    assert not pred.alive
    assert r["death_penalty"] == -10.0
