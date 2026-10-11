import numpy as np
from pettingzoo.test import parallel_api_test

from paleosphere.config import load_world_config
from paleosphere.logging.episode import run_episode
from paleosphere.policies import RuleBasedHerbivore, RuleBasedPredator
from paleosphere.policies.herbivore_observation import HERB_OBS_DIM, herbivore_observation
from training.environments.herd_env import HerdParallelEnv


def test_parallel_api():
    parallel_api_test(HerdParallelEnv(max_steps=300), num_cycles=400)


def test_observation_shape_and_range():
    env = HerdParallelEnv(max_steps=50)
    obs, _ = env.reset(seed=0)
    assert len(obs) == 8
    for o in obs.values():
        assert o.shape == (HERB_OBS_DIM,) and o.dtype == np.float32
        assert np.all(o >= -1) and np.all(o <= 1) and not np.isnan(o).any()


def test_rule_herd_through_env_matches_plain_world():
    env = HerdParallelEnv(max_steps=300)
    env.reset(options={"episode_seed": 10000})
    herd = RuleBasedHerbivore()
    while env.agents:
        env.step({a: herd.act(env.world, a) for a in env.agents})
    plain = run_episode(load_world_config("map_a"), 10000, RuleBasedPredator(), herd, 300)
    assert env.world.snapshot_hash() == plain.final_hash


def test_rewards_finite_and_episode_summary():
    env = HerdParallelEnv(max_steps=400)
    env.reset(seed=1)
    rng = np.random.default_rng(0)
    infos = {}
    while env.agents:
        _, rewards, _, _, infos = env.step({a: int(rng.integers(5)) for a in env.agents})
        assert all(np.isfinite(r) for r in rewards.values())
    summary = next(iter(infos.values()))["episode_summary"]
    assert summary["ticks"] <= 400
    assert set(summary["reward_components"]) >= {"survival_reward", "total_reward"}


def test_observation_sees_chasing_predator():
    env = HerdParallelEnv(max_steps=10)
    env.reset(options={"episode_seed": 10000})
    world = env.world
    pred = world.alive()[-1]
    prey = world.dinos["herbivore-000"]
    pred.pos = prey.pos + np.array([3.0, 0.0])
    world._update_targets()
    obs = herbivore_observation(world, "herbivore-000")
    assert obs[5] == 1.0 and obs[6] < 0.5 and obs[10] == 1.0
