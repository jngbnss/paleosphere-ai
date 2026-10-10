"""Adapter that exposes a trained Stable-Baselines3 PPO model through the Policy interface.

Requires the `training` extra (stable-baselines3, torch).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.policies.observation import predator_observation

if TYPE_CHECKING:
    from paleosphere.core.world import World


class PPOPolicy:
    def __init__(self, model_path: str | Path, version: str | None = None):
        import torch
        from stable_baselines3 import PPO

        torch.set_num_threads(1)
        self.model_path = Path(model_path)
        self.model = PPO.load(self.model_path, device="cpu")
        self.sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        meta_path = self.model_path.parent / "metadata.json"
        self.training_metadata = (
            json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        )
        self.version = version or self.training_metadata.get("run_name", self.model_path.stem)
        self.name = f"ppo:{self.version}"

    def reset(self, seed: int | None = None) -> None:
        pass

    def predict(self, observation: np.ndarray) -> int:
        obs = np.asarray(observation, dtype=np.float32)
        action, _ = self.model.predict(obs, deterministic=True)
        return int(action)

    def act(self, world: World, agent_id: str) -> int:
        return self.predict(predator_observation(world, agent_id))

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "kind": "ppo",
            "version": self.version,
            "model_path": str(self.model_path),
            "model_sha256": self.sha256,
            "reward_version": self.training_metadata.get("reward_version"),
            "train_seed": self.training_metadata.get("train_seed"),
        }
