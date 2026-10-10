"""Deterministic map and population layout from a seeded Generator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from paleosphere.config import WorldConfig
from paleosphere.entities import Dino, Species
from paleosphere.resources.objects import PlantPatch, Rock, WaterSource

_MAX_TRIES = 500


@dataclass(slots=True)
class GeneratedMap:
    plants: list[PlantPatch]
    waters: list[WaterSource]
    rocks: list[Rock]
    dinos: list[Dino]


def _free_point(
    rng: np.random.Generator,
    size: float,
    margin: float,
    blockers: list[tuple[np.ndarray, float]],
    clearance: float,
) -> np.ndarray:
    for _ in range(_MAX_TRIES):
        p = rng.uniform(margin, size - margin, size=2)
        if all(np.linalg.norm(p - c) >= r + clearance for c, r in blockers):
            return p
    raise RuntimeError("could not place object; map too crowded")


def generate_map(config: WorldConfig, rng: np.random.Generator) -> GeneratedMap:
    m = config.map
    waters = [
        WaterSource(f"water-{i:03d}", np.array(w.pos, dtype=float), w.radius)
        for i, w in enumerate(m.waters)
    ]
    blockers: list[tuple[np.ndarray, float]] = [(w.pos, w.radius) for w in waters]

    rocks: list[Rock] = []
    for i in range(m.rocks.count):
        radius = float(rng.uniform(m.rocks.radius_min, m.rocks.radius_max))
        pos = _free_point(rng, m.size, radius + 2.0, blockers, radius + 3.0)
        rocks.append(Rock(f"rock-{i:03d}", pos, radius))
        blockers.append((pos, radius))

    plants: list[PlantPatch] = []
    for i in range(m.plants.count):
        pos = _free_point(rng, m.size, 4.0, blockers, m.plants.radius + 1.0)
        food = float(rng.uniform(0.5, 1.0)) * m.plants.max_food
        plants.append(
            PlantPatch(
                f"plant-{i:03d}", pos, m.plants.radius, food, m.plants.max_food,
                m.plants.regrow_per_tick,
            )
        )
        blockers.append((pos, m.plants.radius))

    rock_blockers = [(r.pos, r.radius) for r in rocks]
    pop = config.population
    herd_center = _free_point(rng, m.size, 12.0, rock_blockers, 4.0)
    dinos: list[Dino] = []
    for i in range(pop.herbivore):
        for _ in range(_MAX_TRIES):
            offset = rng.normal(0.0, pop.herd_spread / 2, size=2)
            pos = np.clip(herd_center + offset, 1.0, m.size - 1.0)
            if all(np.linalg.norm(pos - c) >= r + 0.5 for c, r in rock_blockers):
                break
        dinos.append(_spawn(config, rng, f"herbivore-{i:03d}", Species.HERBIVORE, pos))

    for i in range(pop.predator):
        pos = None
        for _ in range(_MAX_TRIES):
            cand = _free_point(rng, m.size, 2.0, rock_blockers, 1.0)
            if np.linalg.norm(cand - herd_center) >= pop.predator_min_distance:
                pos = cand
                break
        if pos is None:
            raise RuntimeError("could not place predator far enough from herd")
        dinos.append(_spawn(config, rng, f"predator-{i:03d}", Species.PREDATOR, pos))

    return GeneratedMap(plants=plants, waters=waters, rocks=rocks, dinos=dinos)


def _spawn(
    config: WorldConfig, rng: np.random.Generator, agent_id: str, species: Species,
    pos: np.ndarray,
) -> Dino:
    sp = config.species[species.value]
    return Dino(
        agent_id=agent_id,
        species=species,
        pos=np.asarray(pos, dtype=float).copy(),
        hunger=float(rng.uniform(*sp.initial_hunger)),
        thirst=float(rng.uniform(*sp.initial_thirst)),
    )
