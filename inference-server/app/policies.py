"""Predator policy registry for the server.

PPO models are discovered from `models/` (git-ignored; see README for how to produce them):
- `<name>.zip`  SB3 checkpoint, served as `<name>` (needs the training extra / torch)
- `<name>.onnx` exported actor, served as `<name>-onnx` (needs the onnx extra only)

A model kind is listed only when its runtime is installed, so a torch-free deploy
(`uv sync --extra server --extra onnx`) serves the ONNX models. The alias `ppo` points at
the highest `ppo-v<N>` model, preferring the SB3 checkpoint over its ONNX export.
"""

from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

from app.schemas import PolicyInfo
from paleosphere.config import REPO_ROOT
from paleosphere.policies import PredatorAction, RandomPolicy, RuleBasedPredator
from paleosphere.policies.base import Policy

MODELS_DIR = Path(os.environ.get("PALEOSPHERE_MODELS_DIR", REPO_ROOT / "models"))
ONNX_SUFFIX = "-onnx"
_VERSIONED = re.compile(r"ppo-v(\d+)(-onnx)?")


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class PolicyRegistry:
    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = Path(models_dir)
        self._ppo_paths: dict[str, Path] = {}
        if _installed("stable_baselines3"):
            self._ppo_paths |= {p.stem: p for p in sorted(self.models_dir.glob("*.zip"))}
        if _installed("onnxruntime"):
            self._ppo_paths |= {
                p.stem + ONNX_SUFFIX: p for p in sorted(self.models_dir.glob("*.onnx"))
            }
        self._loaded: dict[str, Policy] = {}

    @property
    def names(self) -> list[str]:
        names = ["rule", "random"]
        if self._ppo_paths:
            names.append("ppo")
            names += list(self._ppo_paths)
        return names

    def default_ppo(self) -> str | None:
        # highest version first; at equal version the SB3 checkpoint (no suffix) wins
        versioned = sorted(
            (m for n in self._ppo_paths if (m := _VERSIONED.fullmatch(n))),
            key=lambda m: (int(m.group(1)), m.group(2) is None),
        )
        if versioned:
            return versioned[-1].group(0)
        return next(iter(self._ppo_paths), None)

    def get(self, name: str) -> Policy:
        if name == "ppo":
            resolved = self.default_ppo()
            if resolved is None:
                raise KeyError("no PPO model found in models/ (see README)")
            name = resolved
        if name not in self._loaded:
            self._loaded[name] = self._build(name)
        return self._loaded[name]

    def _build(self, name: str) -> Policy:
        if name == "rule":
            return RuleBasedPredator()
        if name == "random":
            return RandomPolicy(PredatorAction)
        path = self._ppo_paths.get(name)
        if path is not None and path.suffix == ".onnx":
            from paleosphere.policies.onnx_policy import OnnxPolicy

            return OnnxPolicy(path, version=name)
        if path is not None:
            from paleosphere.policies.ppo_policy import PPOPolicy

            return PPOPolicy(path, version=name)
        raise KeyError(f"unknown policy {name!r}; available: {self.names}")

    def info(self) -> list[PolicyInfo]:
        out = [PolicyInfo(name="rule", kind="rule_based"), PolicyInfo(name="random", kind="random")]
        for name in self._ppo_paths:
            meta = self.get(name).metadata()
            out.append(
                PolicyInfo(
                    name=name, kind=meta["kind"], version=meta["version"],
                    model_sha256=meta["model_sha256"],
                )
            )
        return out
