"""Predator policy registry for the server.

PPO models are discovered from `models/*.zip` (git-ignored; see README for how to produce
`models/ppo-v1.zip`). The alias `ppo` points at `ppo-v1` when present, else the first model.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.schemas import PolicyInfo
from paleosphere.config import REPO_ROOT
from paleosphere.policies import PredatorAction, RandomPolicy, RuleBasedPredator
from paleosphere.policies.base import Policy

MODELS_DIR = Path(os.environ.get("PALEOSPHERE_MODELS_DIR", REPO_ROOT / "models"))
PREFERRED_PPO = "ppo-v1"


class PolicyRegistry:
    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = Path(models_dir)
        self._ppo_paths = {p.stem: p for p in sorted(self.models_dir.glob("*.zip"))}
        self._loaded: dict[str, Policy] = {}

    @property
    def names(self) -> list[str]:
        names = ["rule", "random"]
        if self._ppo_paths:
            names.append("ppo")
            names += list(self._ppo_paths)
        return names

    def default_ppo(self) -> str | None:
        if PREFERRED_PPO in self._ppo_paths:
            return PREFERRED_PPO
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
        if name in self._ppo_paths:
            from paleosphere.policies.ppo_policy import PPOPolicy

            return PPOPolicy(self._ppo_paths[name], version=name)
        raise KeyError(f"unknown policy {name!r}; available: {self.names}")

    def info(self) -> list[PolicyInfo]:
        out = [PolicyInfo(name="rule", kind="rule_based"), PolicyInfo(name="random", kind="random")]
        for name in self._ppo_paths:
            meta = self.get(name).metadata()
            out.append(
                PolicyInfo(
                    name=name, kind="ppo", version=meta["version"],
                    model_sha256=meta["model_sha256"],
                )
            )
        return out
