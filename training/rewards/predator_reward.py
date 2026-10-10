"""Predator reward, computed per component so reward hacking can be traced."""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from paleosphere.config import CONFIG_DIR
from paleosphere.core.events import Event, EventKind
from paleosphere.core.world import World
from paleosphere.policies.observation import PredatorView

REWARD_COMPONENTS = (
    "hunt_reward",
    "distance_reward",
    "move_penalty",
    "sprint_penalty",
    "long_chase_penalty",
    "invalid_attack_penalty",
    "energy_penalty",
    "drink_reward",
    "survival_reward",
    "death_penalty",
)


class RewardConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    hunt_reward: float
    distance_shaping_coef: float
    shaping_gamma: float
    move_penalty: float
    sprint_penalty: float
    long_chase_ticks: int
    long_chase_penalty: float
    invalid_attack_penalty: float
    low_energy_threshold: float
    low_energy_penalty: float
    drink_thirst_threshold: float
    drink_reward: float
    survival_reward: float
    death_penalty: float


def load_reward_config(name_or_path: str = "v0") -> RewardConfig:
    path = Path(name_or_path)
    if path.suffix not in {".yaml", ".yml"}:
        path = CONFIG_DIR / "rewards" / f"{name_or_path}.yaml"
    return RewardConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class PredatorReward:
    def __init__(self, config: RewardConfig, day_vision: float):
        self.cfg = config
        self.day_vision = day_vision

    def potential(self, view: PredatorView) -> float:
        """phi(s) >= 0: closer to the current target is higher. No target = 0.

        Keeping phi non-negative makes standing still cost (gamma - 1) * phi <= 0, so the
        shaping term cannot be farmed by idling near prey.
        """
        if view.target_id is None or view.prey_distance is None:
            return 0.0
        closeness = 1.0 - min(view.prey_distance / self.day_vision, 1.0)
        return self.cfg.distance_shaping_coef * closeness

    def compute(
        self,
        before: PredatorView,
        after: PredatorView | None,
        world: World,
        agent_id: str,
        events: list[Event],
    ) -> dict[str, float]:
        cfg = self.cfg
        me = world.dinos[agent_id]
        mine = [e for e in events if e.agent_id == agent_id]
        kills = sum(1 for e in mine if e.kind == EventKind.KILL)
        invalid = sum(1 for e in mine if e.kind == EventKind.ATTACK_INVALID)
        drank = any(e.kind == EventKind.DRINK for e in mine)

        r = dict.fromkeys(REWARD_COMPONENTS, 0.0)
        r["hunt_reward"] = cfg.hunt_reward * kills
        # Terminal state potential is 0 by convention, so shaping cannot be farmed by dying.
        next_phi = self.potential(after) if (after is not None and me.alive) else 0.0
        r["distance_reward"] = cfg.shaping_gamma * next_phi - self.potential(before)
        if me.sprinting:
            r["sprint_penalty"] = cfg.sprint_penalty
        elif me.speed > 1e-9:
            r["move_penalty"] = cfg.move_penalty
        if me.chase_ticks > cfg.long_chase_ticks:
            r["long_chase_penalty"] = cfg.long_chase_penalty
        r["invalid_attack_penalty"] = cfg.invalid_attack_penalty * invalid
        if me.alive and me.energy < cfg.low_energy_threshold:
            r["energy_penalty"] = cfg.low_energy_penalty
        if drank and before.thirst > cfg.drink_thirst_threshold:
            r["drink_reward"] = cfg.drink_reward
        if me.alive:
            r["survival_reward"] = cfg.survival_reward
        else:
            r["death_penalty"] = cfg.death_penalty

        r["total_reward"] = math.fsum(r[c] for c in REWARD_COMPONENTS)
        return r
