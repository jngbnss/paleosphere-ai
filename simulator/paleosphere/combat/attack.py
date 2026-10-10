"""Attack resolution: range, cooldown, hit roll, damage, kill & feeding."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from paleosphere.config import CombatConfig
from paleosphere.core.geometry import distance
from paleosphere.entities import Dino


class AttackOutcome(StrEnum):
    NO_TARGET = "no_target"
    OUT_OF_RANGE = "out_of_range"
    ON_COOLDOWN = "on_cooldown"
    MISS = "miss"
    HIT = "hit"
    KILL = "kill"


@dataclass(slots=True, frozen=True)
class AttackResult:
    outcome: AttackOutcome
    damage: float = 0.0

    @property
    def valid(self) -> bool:
        return self.outcome in (AttackOutcome.MISS, AttackOutcome.HIT, AttackOutcome.KILL)


def resolve_attack(
    attacker: Dino, target: Dino | None, cfg: CombatConfig, rng: np.random.Generator
) -> AttackResult:
    """Mutates attacker/target. The caller handles death bookkeeping on KILL."""
    if target is None or not target.alive:
        return AttackResult(AttackOutcome.NO_TARGET)
    if attacker.attack_cooldown > 0:
        return AttackResult(AttackOutcome.ON_COOLDOWN)
    if distance(attacker.pos, target.pos) > cfg.attack_range:
        return AttackResult(AttackOutcome.OUT_OF_RANGE)

    attacker.attack_cooldown = cfg.attack_cooldown
    attacker.energy = max(0.0, attacker.energy - cfg.attack_energy_cost)
    hit_chance = cfg.hit_chance_vs_sprinting if target.sprinting else cfg.hit_chance_vs_walking
    if rng.random() >= hit_chance:
        return AttackResult(AttackOutcome.MISS)

    target.health = max(0.0, target.health - cfg.damage)
    if target.health > 0.0:
        return AttackResult(AttackOutcome.HIT, cfg.damage)

    attacker.hunger = max(0.0, attacker.hunger - cfg.kill_hunger_reduction)
    attacker.energy = min(100.0, attacker.energy + cfg.kill_energy_gain)
    return AttackResult(AttackOutcome.KILL, cfg.damage)
