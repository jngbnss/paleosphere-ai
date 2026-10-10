"""Gymnasium wrapper: one learning predator, rule-based herbivores."""

from __future__ import annotations

from collections import Counter
from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from paleosphere.config import WorldConfig, load_world_config
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.logging.episode import EpisodeTracker
from paleosphere.policies import OBS_DIM, PredatorAction, RuleBasedHerbivore
from paleosphere.policies.observation import encode_predator_view, predator_view
from training.rewards import REWARD_COMPONENTS, PredatorReward, load_reward_config

ENV_VERSION = "PaleoSpherePredator-v0"
TRAIN_SEED_RANGE = (0, 10_000)


class PredatorEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(
        self,
        world_config: str | WorldConfig = "map_a",
        reward_config: str = "v0",
        max_steps: int = 2000,
        seed_range: tuple[int, int] = TRAIN_SEED_RANGE,
        world_overrides: dict[str, Any] | None = None,
        spawn_near_prey_prob: float = 0.0,
        spawn_near_prey_distance: tuple[float, float] = (5.0, 9.0),
    ):
        super().__init__()
        if isinstance(world_config, WorldConfig):
            self.world_config = world_config
        else:
            self.world_config = load_world_config(world_config, **(world_overrides or {}))
        self.reward_config = load_reward_config(reward_config)
        self.reward_fn = PredatorReward(
            self.reward_config, self.world_config.species["predator"].vision
        )
        self.max_steps = max_steps
        self.seed_range = seed_range
        # Training-only curriculum: start some episodes next to prey so the agent experiences
        # hits and kills early. Evaluation always uses the default spawn (prob 0).
        self.spawn_near_prey_prob = spawn_near_prey_prob
        self.spawn_near_prey_distance = spawn_near_prey_distance
        self.observation_space = spaces.Box(-1.0, 1.0, shape=(OBS_DIM,), dtype=np.float32)
        self.action_space = spaces.Discrete(len(PredatorAction))
        self.herbivore_policy = RuleBasedHerbivore()
        self.world: World | None = None
        self.predator_id = ""
        self.episode_seed = -1

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        options = options or {}
        if "episode_seed" in options:
            self.episode_seed = int(options["episode_seed"])
        else:
            self.episode_seed = int(self.np_random.integers(*self.seed_range))
        self.world = World(self.world_config, self.episode_seed)
        self.herbivore_policy.reset(self.episode_seed)
        self.predator_id = self.world.alive(Species.PREDATOR)[0].agent_id
        if options.get("spawn_near_prey", self.np_random.random() < self.spawn_near_prey_prob):
            self._spawn_near_prey()
        self.tracker = EpisodeTracker(self.world, self.predator_id, "env")
        self.steps = 0
        self.episode_components = Counter()
        return self._obs(), {"episode_seed": self.episode_seed}

    def step(self, action):
        assert self.world is not None, "call reset() first"
        world, pid = self.world, self.predator_id
        action = int(action)
        before = predator_view(world, pid)
        actions = {
            d.agent_id: int(self.herbivore_policy.act(world, d.agent_id))
            for d in world.alive(Species.HERBIVORE)
        }
        actions[pid] = action
        energy_before = world.dinos[pid].energy
        events = world.step(actions)
        self.tracker.record(actions, energy_before, events)
        self.steps += 1

        alive = world.dinos[pid].alive
        after = predator_view(world, pid) if alive else None
        components = self.reward_fn.compute(before, after, world, pid, events, action)
        self.episode_components.update(components)

        terminated = (not alive) or not world.alive(Species.HERBIVORE)
        truncated = (not terminated) and self.steps >= self.max_steps
        info: dict[str, Any] = {
            "reward_components": components,
            "kills": self.tracker.events["kill"],
            "episode_seed": self.episode_seed,
        }
        if terminated or truncated:
            summary = self.tracker.summary()
            info["episode_summary"] = summary.to_dict()
            info["episode_reward_components"] = {
                k: float(self.episode_components[k]) for k in (*REWARD_COMPONENTS, "total_reward")
            }
        obs = encode_predator_view(after) if after is not None else self._dead_obs()
        return obs, float(components["total_reward"]), terminated, truncated, info

    def _spawn_near_prey(self) -> None:
        world = self.world
        herd = world.alive(Species.HERBIVORE)
        prey = herd[int(self.np_random.integers(len(herd)))]
        angle = float(self.np_random.uniform(0.0, 2.0 * np.pi))
        dist = float(self.np_random.uniform(*self.spawn_near_prey_distance))
        x = float(prey.pos[0]) + dist * np.cos(angle)
        z = float(prey.pos[1]) + dist * np.sin(angle)
        x, z = world._resolve_collisions(x, z)
        world.dinos[self.predator_id].pos = np.array([x, z])
        world._update_targets()

    def _obs(self) -> np.ndarray:
        return encode_predator_view(predator_view(self.world, self.predator_id))

    def _dead_obs(self) -> np.ndarray:
        return np.zeros(OBS_DIM, dtype=np.float32)
