"""Parameter sharing for the herd: a PettingZoo ParallelEnv seen by SB3 as one VecEnv.

Every (world, herbivore) pair is one VecEnv slot, so a single PPO policy is trained on all
herbivores of `n_worlds` worlds at once (num_envs = n_worlds x herd size).

A dead herbivore's slot reports `done` once (with its terminal observation), then waits with a
zero observation and zero reward until its world resets ("black death", as in SuperSuit).
A world resets when its last herbivore is done; waiting slots end their idle stretch then.
Truncation is flagged with `TimeLimit.truncated` so PPO bootstraps the value at the time limit.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from stable_baselines3.common.vec_env import VecEnv

from training.environments.herd_env import HerdParallelEnv


class HerdVecEnv(VecEnv):
    def __init__(self, n_worlds: int = 4, seed: int = 0, **env_kwargs: Any):
        self.envs = [HerdParallelEnv(**env_kwargs) for _ in range(n_worlds)]
        first = self.envs[0]
        self.agent_names = list(first.possible_agents)
        self.n_agents = len(self.agent_names)
        agent = self.agent_names[0]
        super().__init__(
            n_worlds * self.n_agents, first.observation_space(agent), first.action_space(agent)
        )
        self._seed = seed
        self._obs = np.zeros((self.num_envs, *self.observation_space.shape), dtype=np.float32)
        self._ep_return = np.zeros(self.num_envs)
        self._ep_len = np.zeros(self.num_envs, dtype=np.int64)
        self._actions: np.ndarray | None = None
        self.episode_summaries: list[dict] = []

    def _slot(self, w: int, j: int) -> int:
        return w * self.n_agents + j

    def _reset_world(self, w: int) -> None:
        obs, _ = self.envs[w].reset()  # later episodes follow the env's rng seeded in reset()
        for j, name in enumerate(self.agent_names):
            self._obs[self._slot(w, j)] = obs.get(name, 0.0)

    def reset(self) -> np.ndarray:
        seed = self._seed
        for w, env in enumerate(self.envs):
            obs, _ = env.reset(seed=None if seed is None else seed + 7919 * w)
            for j, name in enumerate(self.agent_names):
                self._obs[self._slot(w, j)] = obs.get(name, 0.0)
        self._seed = None
        self._ep_return[:] = 0.0
        self._ep_len[:] = 0
        return self._obs.copy()

    def step_async(self, actions: np.ndarray) -> None:
        self._actions = np.asarray(actions)

    def step_wait(self):
        rewards = np.zeros(self.num_envs, dtype=np.float32)
        dones = np.zeros(self.num_envs, dtype=bool)
        infos: list[dict] = [{} for _ in range(self.num_envs)]
        for w, env in enumerate(self.envs):
            live = list(env.agents)
            idx = {name: j for j, name in enumerate(self.agent_names)}
            acts = {a: int(self._actions[self._slot(w, idx[a])]) for a in live}
            obs, rew, terms, truncs, inf = env.step(acts)
            for a in live:
                s = self._slot(w, idx[a])
                rewards[s] = rew[a]
                self._ep_return[s] += rew[a]
                self._ep_len[s] += 1
                self._obs[s] = obs[a]
                if terms[a] or truncs[a]:
                    dones[s] = True
                    infos[s]["terminal_observation"] = obs[a].copy()
                    infos[s]["TimeLimit.truncated"] = bool(truncs[a] and not terms[a])
                    infos[s]["episode"] = {"r": float(self._ep_return[s]),
                                           "l": int(self._ep_len[s])}
                    self._obs[s] = 0.0
            if not env.agents:  # world finished: every waiting slot ends too, then reset
                self.episode_summaries.append(next(iter(inf.values()))["episode_summary"])
                for j in range(self.n_agents):
                    s = self._slot(w, j)
                    if not dones[s]:
                        dones[s] = True
                        infos[s]["terminal_observation"] = np.zeros_like(self._obs[s])
                        infos[s]["TimeLimit.truncated"] = False
                    self._ep_return[s] = 0.0
                    self._ep_len[s] = 0
                self._reset_world(w)
        return self._obs.copy(), rewards, dones, infos

    def close(self) -> None:
        for env in self.envs:
            env.close()

    # -- VecEnv plumbing (no sub-process envs to forward to)
    def get_attr(self, attr_name, indices=None):
        return [getattr(self.envs[i // self.n_agents], attr_name)
                for i in self._get_indices(indices)]

    def set_attr(self, attr_name, value, indices=None):
        for i in self._get_indices(indices):
            setattr(self.envs[i // self.n_agents], attr_name, value)

    def env_method(self, method_name, *method_args, indices=None, **method_kwargs):
        return [getattr(self.envs[i // self.n_agents], method_name)(*method_args, **method_kwargs)
                for i in self._get_indices(indices)]

    def env_is_wrapped(self, wrapper_class, indices=None):
        return [False for _ in self._get_indices(indices)]
