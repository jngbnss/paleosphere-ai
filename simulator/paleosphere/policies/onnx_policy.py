"""Run an exported PPO actor (`training/scripts/export_onnx.py`) with onnxruntime.

Needs only the `onnx` extra (onnxruntime), not torch or stable-baselines3, so a server or
evaluation box can run trained predators without the training stack.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.policies.observation import OBS_DIM, predator_observation

if TYPE_CHECKING:
    from paleosphere.core.world import World


class OnnxPolicy:
    def __init__(self, model_path: str | Path, version: str | None = None):
        import onnxruntime as ort

        self.model_path = Path(model_path)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1  # one tiny MLP per tick; threads only add overhead
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(self.model_path), options, providers=["CPUExecutionProvider"]
        )
        shape = self.session.get_inputs()[0].shape
        if shape[-1] != OBS_DIM:
            raise ValueError(f"model expects obs_dim {shape[-1]}, not {OBS_DIM}")
        self.sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        props = self.session.get_modelmeta().custom_metadata_map
        self.source = json.loads(props.get("source", "{}"))
        self.version = version or self.source.get("version", self.model_path.stem)
        self.name = f"onnx:{self.version}"

    def reset(self, seed: int | None = None) -> None:
        pass

    def predict(self, observation: np.ndarray) -> int:
        obs = np.asarray(observation, dtype=np.float32).reshape(1, OBS_DIM)
        (action,) = self.session.run(["action"], {"obs": obs})
        return int(action[0])

    def act(self, world: World, agent_id: str) -> int:
        return self.predict(predator_observation(world, agent_id))

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "kind": "onnx",
            "version": self.version,
            "model_path": str(self.model_path),
            "model_sha256": self.sha256,
            "source_model_sha256": self.source.get("model_sha256"),
            "reward_version": self.source.get("reward_version"),
            "train_seed": self.source.get("train_seed"),
        }
