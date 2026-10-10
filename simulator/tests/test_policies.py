import numpy as np
import pytest

from paleosphere.config import load_world_config
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.policies import (
    OBS_DIM,
    HerbivoreAction,
    Policy,
    PredatorAction,
    RandomPolicy,
    RuleBasedHerbivore,
    RuleBasedPredator,
    predator_observation,
)
from paleosphere.policies.observation import OBS_FIELDS


def run(world, predator_policy, ticks):
    herb = RuleBasedHerbivore()
    for _ in range(ticks):
        if world.done:
            break
        actions = {
            d.agent_id: (predator_policy if d.species == Species.PREDATOR else herb).act(
                world, d.agent_id
            )
            for d in world.alive()
        }
        world.step(actions)
        yield world


def test_policies_follow_protocol():
    for p in (RuleBasedPredator(), RuleBasedHerbivore(), RandomPolicy(PredatorAction, 0)):
        assert isinstance(p, Policy)
        assert "name" in p.metadata()


@pytest.mark.parametrize("seed", [0, 42, 777])
def test_observation_shape_range_and_finite(seed):
    world = World(load_world_config("map_a"), seed)
    pid = world.alive(Species.PREDATOR)[0].agent_id
    seen_target = False
    for w in run(world, RuleBasedPredator(), 1500):
        if not w.dinos[pid].alive:
            break
        obs = predator_observation(w, pid)
        assert obs.shape == (OBS_DIM,) == (len(OBS_FIELDS),)
        assert obs.dtype == np.float32
        assert np.all(np.isfinite(obs))
        assert obs.min() >= -1.0 and obs.max() <= 1.0
        seen_target |= obs[5] == 1.0
    assert seen_target


def test_observation_prev_action_one_hot():
    world = World(load_world_config("map_a"), 0)
    pid = world.alive(Species.PREDATOR)[0].agent_id
    world.step({pid: PredatorAction.SEARCH})
    obs = predator_observation(world, pid)
    one_hot = obs[19:26]
    assert one_hot.sum() == 1.0 and one_hot[PredatorAction.SEARCH] == 1.0


def test_rule_predator_outhunts_random():
    cfg = load_world_config("map_a")

    def kills(policy, seed):
        world = World(cfg, seed)
        for _ in run(world, policy, 2000):
            pass
        return sum(
            1 for d in world.dinos.values() if d.death_cause and d.death_cause == "predation"
        )

    rule = sum(kills(RuleBasedPredator(), s) for s in range(3))
    rand = sum(kills(RandomPolicy(PredatorAction, s), s) for s in range(3))
    assert rule > rand


def test_rule_predator_decisions():
    world = World(load_world_config("map_a"), 0)
    pred = world.alive(Species.PREDATOR)[0]
    prey = world.alive(Species.HERBIVORE)[0]
    policy = RuleBasedPredator()
    pred.hunger, pred.thirst, pred.energy = 80.0, 10.0, 90.0

    pred.thirst = 90.0
    assert policy.act(world, pred.agent_id) == PredatorAction.GO_TO_WATER
    pred.thirst = 10.0

    pred.energy = 5.0
    assert policy.act(world, pred.agent_id) == PredatorAction.REST
    pred.energy = 90.0
    pred.current_action = "NONE"

    pred.pos = prey.pos + np.array([1.0, 0.0])
    world._update_targets()
    assert policy.act(world, pred.agent_id) == PredatorAction.ATTACK
    pred.attack_cooldown = 3
    assert policy.act(world, pred.agent_id) == PredatorAction.CHASE
    pred.chase_ticks = 1000
    assert policy.act(world, pred.agent_id) == PredatorAction.GIVE_UP


def test_rule_herbivore_flees_predator():
    world = World(load_world_config("map_a"), 0)
    pred = world.alive(Species.PREDATOR)[0]
    prey = world.alive(Species.HERBIVORE)[0]
    pred.pos = prey.pos + np.array([3.0, 0.0])
    assert RuleBasedHerbivore().act(world, prey.agent_id) == HerbivoreAction.FLEE
