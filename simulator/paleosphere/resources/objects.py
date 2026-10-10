from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class PlantPatch:
    plant_id: str
    pos: np.ndarray
    radius: float
    food: float
    max_food: float
    regrow_per_tick: float

    def regrow(self) -> None:
        self.food = min(self.max_food, self.food + self.regrow_per_tick)

    def to_dict(self) -> dict:
        return {
            "plant_id": self.plant_id,
            "position": [round(float(self.pos[0]), 6), round(float(self.pos[1]), 6)],
            "radius": self.radius,
            "food": round(self.food, 6),
        }


@dataclass(slots=True, frozen=True)
class WaterSource:
    water_id: str
    pos: np.ndarray
    radius: float

    def to_dict(self) -> dict:
        return {
            "water_id": self.water_id,
            "position": [float(self.pos[0]), float(self.pos[1])],
            "radius": self.radius,
        }


@dataclass(slots=True, frozen=True)
class Rock:
    rock_id: str
    pos: np.ndarray
    radius: float

    def to_dict(self) -> dict:
        return {
            "rock_id": self.rock_id,
            "position": [round(float(self.pos[0]), 6), round(float(self.pos[1]), 6)],
            "radius": round(self.radius, 6),
        }
