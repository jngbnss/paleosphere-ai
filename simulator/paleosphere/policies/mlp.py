"""Portable PPO actor weights (`*.policy.json`) and a numpy forward pass.

`training/scripts/export_onnx.py` writes this file next to the ONNX model. It is the format
the Godot viewer reads for in-engine inference (godot/scripts/mlp_policy.gd), so the numpy
forward here is the reference those other runtimes are tested against.

Layout: hidden layers use `activation`; the last layer outputs one logit per action.
Weights are stored as `[out][in]` (torch Linear convention); the action is argmax(logits).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.policies.observation import OBS_DIM, predator_observation

if TYPE_CHECKING:
    from paleosphere.core.world import World

FORMAT = "paleosphere-mlp-v1"
_ACTIVATIONS = {"tanh": np.tanh, "relu": lambda x: np.maximum(x, 0.0)}


class MlpWeights:
    def __init__(self, data: dict):
        if data.get("format") != FORMAT:
            raise ValueError(f"unsupported policy weights format {data.get('format')!r}")
        if data["activation"] not in _ACTIVATIONS:
            raise ValueError(f"unsupported activation {data['activation']!r}")
        self.data = data
        self.activation = data["activation"]
        self.actions: list[str] = data["actions"]
        self.layers = [
            (np.asarray(layer["weight"], dtype=np.float32), np.asarray(layer["bias"], np.float32))
            for layer in data["layers"]
        ]
        if self.layers[0][0].shape[1] != data["obs_dim"]:
            raise ValueError("first layer input size does not match obs_dim")
        if self.layers[-1][0].shape[0] != len(self.actions):
            raise ValueError("last layer output size does not match the action list")

    @classmethod
    def load(cls, path: str | Path) -> MlpWeights:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def logits(self, obs: np.ndarray) -> np.ndarray:
        """obs: (obs_dim,) or (batch, obs_dim) -> logits of the same leading shape."""
        x = np.asarray(obs, dtype=np.float32)
        act = _ACTIVATIONS[self.activation]
        for i, (w, b) in enumerate(self.layers):
            x = x @ w.T + b
            if i < len(self.layers) - 1:
                x = act(x)
        return x

    def predict(self, obs: np.ndarray) -> int:
        return int(np.argmax(self.logits(obs)))


class MlpPolicy:
    """Torch-free policy over exported `*.policy.json` weights."""

    def __init__(self, path: str | Path, version: str | None = None):
        self.path = Path(path)
        self.weights = MlpWeights.load(self.path)
        obs_dim = self.weights.data["obs_dim"]
        if obs_dim != OBS_DIM:
            raise ValueError(f"weights expect obs_dim {obs_dim}, not {OBS_DIM}")
        source = self.weights.data.get("source", {})
        self.version = version or source.get("version", self.path.stem)
        self.name = f"mlp:{self.version}"

    def reset(self, seed: int | None = None) -> None:
        pass

    def predict(self, observation: np.ndarray) -> int:
        return self.weights.predict(observation)

    def act(self, world: World, agent_id: str) -> int:
        return self.predict(predator_observation(world, agent_id))

    def metadata(self) -> dict:
        source = self.weights.data.get("source", {})
        return {
            "name": self.name,
            "kind": "mlp",
            "version": self.version,
            "model_path": str(self.path),
            "model_sha256": source.get("model_sha256"),
            "reward_version": source.get("reward_version"),
            "train_seed": source.get("train_seed"),
        }
