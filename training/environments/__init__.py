import gymnasium as gym

from training.environments.predator_env import ENV_VERSION, PredatorEnv

if ENV_VERSION not in gym.registry:
    gym.register(id=ENV_VERSION, entry_point="training.environments.predator_env:PredatorEnv")

__all__ = ["ENV_VERSION", "PredatorEnv"]
