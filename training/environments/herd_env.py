"""PettingZoo ParallelEnv: every herbivore is a learning agent, the predator is fixed.

`PaleoSphereHerd-v0`: map_a, 8 herbivores (agents), 1 predator driven by a fixed policy
(rule by default, or any `make_predator_policy` spec such as `onnx:models/ppo-v2.onnx`).
Agents leave `env.agents` when they die. The episode ends when the herd is gone or after
`max_steps`; if the predator dies first the herd simply keeps living until truncation.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
from gymnasium import spaces
from pettingzoo import ParallelEnv

from paleosphere.config import WorldConfig, load_world_config
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.policies import HerbivoreAction
from paleosphere.policies.factory import make_predator_policy
from paleosphere.policies.herbivore_observation import HERB_OBS_DIM, herbivore_observation
from training.environments.predator_env import TRAIN_SEED_RANGE
from training.rewards.herd_reward import (
    HERD_REWARD_COMPONENTS,
    herd_reward,
    load_herd_reward_config,
)

HERD_ENV_VERSION = "PaleoSphereHerd-v0"


class HerdParallelEnv(ParallelEnv):
    metadata = {"name": HERD_ENV_VERSION, "render_modes": []}

    def __init__(
        self,
        world_config: str | WorldConfig = "map_a",
        reward_config: str = "herd_v0",
        predator: str = "rule",
        max_steps: int = 2000,
        seed_range: tuple[int, int] = TRAIN_SEED_RANGE,
    ):
        if isinstance(world_config, WorldConfig):
            self.world_config = world_config
        else:
            self.world_config = load_world_config(world_config)
        if self.world_config.reproduction is not None:
            raise ValueError("the herd env needs a fixed population (no reproduction)")
        self.reward_config = load_herd_reward_config(reward_config)
        self.predator_spec = predator
        self.predator_policy = make_predator_policy(predator)
        self.max_steps = max_steps
        self.seed_range = seed_range
        n = self.world_config.population.herbivore
        self.possible_agents = [f"herbivore-{i:03d}" for i in range(n)]
        self.render_mode = None
        self.agents: list[str] = []
        self.world: World | None = None
        self._rng = np.random.default_rng()
        self.episode_seed = -1
        # shared by every agent (parameter sharing needs identical spaces)
        self._obs_space = spaces.Box(-1.0, 1.0, shape=(HERB_OBS_DIM,), dtype=np.float32)
        self._act_space = spaces.Discrete(len(HerbivoreAction))

    def observation_space(self, agent: str) -> spaces.Box:
        return self._obs_space

    def action_space(self, agent: str) -> spaces.Discrete:
        return self._act_space

    def reset(self, seed: int | None = None, options: dict | None = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        options = options or {}
        self.episode_seed = int(options.get("episode_seed", self._rng.integers(*self.seed_range)))
        self.world = World(self.world_config, self.episode_seed)
        self.predator_policy.reset(self.episode_seed)
        self.agents = [d.agent_id for d in self.world.alive(Species.HERBIVORE)]
        self.predator_id = self.world.alive(Species.PREDATOR)[0].agent_id
        self.steps = 0
        self.components = Counter()
        self.death_causes: Counter[str] = Counter()
        obs = {a: herbivore_observation(self.world, a) for a in self.agents}
        infos = {a: {"episode_seed": self.episode_seed} for a in self.agents}
        return obs, infos

    def step(self, actions: dict[str, int]):
        world = self.world
        assert world is not None, "call reset() first"
        joint = {a: int(actions[a]) for a in self.agents}
        for d in world.alive(Species.PREDATOR):
            joint[d.agent_id] = int(self.predator_policy.act(world, d.agent_id))
        events = world.step(joint)
        self.steps += 1

        obs, rewards, terms, truncs, infos = {}, {}, {}, {}, {}
        herd_alive = bool(world.alive(Species.HERBIVORE))
        for a in self.agents:
            dino = world.dinos[a]
            comp = herd_reward(self.reward_config, dino, events)
            self.components.update(comp)
            rewards[a] = float(comp["total_reward"])
            terms[a] = not dino.alive
            truncs[a] = dino.alive and self.steps >= self.max_steps
            obs[a] = (
                herbivore_observation(world, a) if dino.alive
                else np.zeros(HERB_OBS_DIM, dtype=np.float32)
            )
            infos[a] = {"reward_components": comp}
            if not dino.alive:
                self.death_causes[str(dino.death_cause)] += 1
        self.agents = [a for a in self.agents if not (terms[a] or truncs[a])]
        if not self.agents:
            summary = self.episode_summary(herd_alive)
            for info in infos.values():
                info["episode_summary"] = summary
        return obs, rewards, terms, truncs, infos

    def episode_summary(self, herd_alive: bool | None = None) -> dict[str, Any]:
        world = self.world
        herd = [world.dinos[a] for a in self.possible_agents]
        predator = world.dinos[self.predator_id]
        return {
            "episode_seed": self.episode_seed,
            "ticks": world.tick,
            "predator": self.predator_spec,
            "herbivores_alive": sum(d.alive for d in herd),
            "mean_survival_ticks": float(np.mean([d.age for d in herd])),
            "death_causes": dict(sorted(self.death_causes.items())),
            "predator_alive": predator.alive,
            "predator_death_cause": str(predator.death_cause) if predator.death_cause else None,
            "predator_survival_ticks": predator.age,
            "reward_components": {
                k: float(self.components[k]) for k in (*HERD_REWARD_COMPONENTS, "total_reward")
            },
        }

    def render(self):
        return None

    def close(self):
        pass


def parallel_env(**kwargs) -> HerdParallelEnv:
    return HerdParallelEnv(**kwargs)
