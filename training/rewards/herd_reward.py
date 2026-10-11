"""Herbivore reward (Phase 7), per component like the predator reward."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from paleosphere.config import CONFIG_DIR
from paleosphere.core.events import Event, EventKind
from paleosphere.entities import Dino

HERD_REWARD_COMPONENTS = (
    "survival_reward",
    "death_penalty",
    "hit_penalty",
    "hunger_penalty",
    "thirst_penalty",
    "energy_penalty",
)


class HerdRewardConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    survival_reward: float
    death_penalty: float
    hit_penalty: float
    hunger_penalty_coef: float
    thirst_penalty_coef: float
    low_energy_threshold: float
    low_energy_penalty: float


def load_herd_reward_config(name_or_path: str = "herd_v0") -> HerdRewardConfig:
    path = Path(name_or_path)
    if path.suffix not in {".yaml", ".yml"}:
        path = CONFIG_DIR / "rewards" / f"{name_or_path}.yaml"
    return HerdRewardConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def herd_reward(cfg: HerdRewardConfig, dino: Dino, events: list[Event]) -> dict[str, float]:
    """Reward for one herbivore after a world step (`dino` is its post-step state)."""
    c = dict.fromkeys(HERD_REWARD_COMPONENTS, 0.0)
    hit = any(
        e.kind == EventKind.ATTACK_HIT and e.target_id == dino.agent_id for e in events
    )
    if hit:
        c["hit_penalty"] = cfg.hit_penalty
    if dino.alive:
        c["survival_reward"] = cfg.survival_reward
        c["hunger_penalty"] = -cfg.hunger_penalty_coef * dino.hunger / 100.0
        c["thirst_penalty"] = -cfg.thirst_penalty_coef * dino.thirst / 100.0
        if dino.energy < cfg.low_energy_threshold:
            c["energy_penalty"] = cfg.low_energy_penalty
    else:
        c["death_penalty"] = cfg.death_penalty
    c["total_reward"] = sum(c[k] for k in HERD_REWARD_COMPONENTS)
    return c
