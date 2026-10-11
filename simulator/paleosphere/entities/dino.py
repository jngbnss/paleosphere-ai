"""Dinosaur state. Values for health/energy/hunger/thirst are in [0, 100].

hunger and thirst are "bad when high": 100 means starving / dehydrated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np


class Species(StrEnum):
    HERBIVORE = "herbivore"
    PREDATOR = "predator"


class DeathCause(StrEnum):
    PREDATION = "predation"
    STARVATION = "starvation"
    DEHYDRATION = "dehydration"
    EXHAUSTION = "exhaustion"
    OLD_AGE = "old_age"


@dataclass(slots=True)
class Dino:
    agent_id: str
    species: Species
    pos: np.ndarray
    vel: np.ndarray = field(default_factory=lambda: np.zeros(2))
    health: float = 100.0
    energy: float = 100.0
    hunger: float = 0.0
    thirst: float = 0.0
    age: int = 0
    current_action: str = "NONE"
    target_id: str | None = None
    alive: bool = True
    attack_cooldown: int = 0
    chase_ticks: int = 0
    ignored_target_id: str | None = None
    ignore_until: int = -1
    waypoint: np.ndarray | None = None
    sprinting: bool = False
    death_cause: DeathCause | None = None
    # reproduction (only used and serialised when the world config enables it)
    generation: int = 0
    parent_id: str | None = None
    breed_cooldown: int = 0
    death_tick: int | None = None

    @property
    def speed(self) -> float:
        return float(np.hypot(self.vel[0], self.vel[1]))

    def to_dict(self, reproduction: bool = False) -> dict:
        out = {
            "agent_id": self.agent_id,
            "species": str(self.species),
            "position": [round(float(self.pos[0]), 6), round(float(self.pos[1]), 6)],
            "velocity": [round(float(self.vel[0]), 6), round(float(self.vel[1]), 6)],
            "health": round(self.health, 6),
            "energy": round(self.energy, 6),
            "hunger": round(self.hunger, 6),
            "thirst": round(self.thirst, 6),
            "age": self.age,
            "current_action": self.current_action,
            "target_id": self.target_id,
            "alive": self.alive,
            "death_cause": str(self.death_cause) if self.death_cause else None,
        }
        if reproduction:
            out |= {
                "generation": self.generation,
                "parent_id": self.parent_id,
                "breed_cooldown": self.breed_cooldown,
            }
        return out
