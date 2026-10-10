import gymnasium as gym
import numpy as np
from gymnasium.utils.env_checker import check_env

from paleosphere.policies import PredatorAction, RuleBasedPredator
from training.environments import ENV_VERSION, PredatorEnv


def test_check_env_passes():
    check_env(PredatorEnv(max_steps=200), skip_render_check=True)


def test_registered():
    env = gym.make(ENV_VERSION, max_steps=50)
    obs, _ = env.reset(seed=0)
    assert env.observation_space.contains(obs)


def test_observations_stay_in_space_and_rewards_finite():
    env = PredatorEnv(max_steps=500)
    obs, info = env.reset(seed=1)
    rng = np.random.default_rng(0)
    done = False
    while not done:
        assert env.observation_space.contains(obs)
        obs, reward, terminated, truncated, info = env.step(int(rng.integers(7)))
        assert np.isfinite(reward)
        done = terminated or truncated
    assert "episode_summary" in info


def test_truncated_vs_terminated():
    env = PredatorEnv(max_steps=30)
    env.reset(seed=2)
    for _ in range(30):
        _, _, terminated, truncated, _ = env.step(PredatorAction.REST)
    assert truncated and not terminated

    env = PredatorEnv(max_steps=5000)
    env.reset(seed=2)
    env.world.dinos[env.predator_id].health = 0.1
    env.world.dinos[env.predator_id].hunger = 100.0
    _, _, terminated, truncated, info = env.step(PredatorAction.REST)
    assert terminated and not truncated
    assert info["episode_summary"]["predator_death_cause"] == "starvation"


def test_same_seed_same_rewards():
    def rollout():
        env = PredatorEnv(max_steps=300)
        env.reset(options={"episode_seed": 123})
        actions = np.random.default_rng(5).integers(7, size=300)
        return [env.step(int(a))[1] for a in actions]

    assert rollout() == rollout()


def test_episode_seed_option_matches_rule_episode():
    """Driving the env with the rule policy reproduces the plain simulator run."""
    from paleosphere.config import load_world_config
    from paleosphere.logging.episode import run_episode
    from paleosphere.policies import RuleBasedHerbivore

    env = PredatorEnv(max_steps=400)
    env.reset(options={"episode_seed": 42})
    rule = RuleBasedPredator()
    done = False
    while not done:
        a = rule.act(env.world, env.predator_id)
        _, _, terminated, truncated, info = env.step(a)
        done = terminated or truncated
    cfg = load_world_config("map_a")
    ref = run_episode(cfg, 42, RuleBasedPredator(), RuleBasedHerbivore(), 400)
    assert info["episode_summary"]["final_hash"] == ref.final_hash
