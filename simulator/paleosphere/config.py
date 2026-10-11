"""World configuration models loaded from configs/world/*.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlantConfig(_Frozen):
    count: int
    radius: float
    max_food: float
    regrow_per_tick: float


class WaterConfig(_Frozen):
    pos: tuple[float, float]
    radius: float


class RockConfig(_Frozen):
    count: int
    radius_min: float
    radius_max: float


class MapConfig(_Frozen):
    name: str
    size: float
    plants: PlantConfig
    waters: tuple[WaterConfig, ...]
    rocks: RockConfig


class PopulationConfig(_Frozen):
    herbivore: int
    predator: int
    herd_spread: float
    predator_min_distance: float


class TimeConfig(_Frozen):
    day_length: int
    night_fraction: float
    night_vision_multiplier: float


class SpeciesConfig(_Frozen):
    walk_speed: float
    sprint_speed: float
    vision: float
    hunger_rate: float
    thirst_rate: float
    energy_rest_gain: float
    energy_walk_cost: float
    energy_sprint_cost: float
    sprint_thirst_extra: float
    initial_hunger: tuple[float, float]
    initial_thirst: tuple[float, float]


class MetabolismConfig(_Frozen):
    starving_threshold: float
    starvation_damage: float
    dehydration_damage: float
    exhaustion_damage: float
    health_regen: float
    min_sprint_energy: float
    eat_rate: float
    hunger_per_food: float
    drink_rate: float


class CombatConfig(_Frozen):
    attack_range: float
    attack_cooldown: int
    attack_energy_cost: float
    damage: float
    hit_chance_vs_walking: float
    hit_chance_vs_sprinting: float
    kill_hunger_reduction: float
    kill_energy_gain: float
    give_up_ignore_ticks: int


class SpeciesReproductionConfig(_Frozen):
    """When a well-fed adult may give birth, and what it costs. Asexual, one offspring."""

    min_age: int
    cooldown: int                 # ticks between births of the same parent
    max_hunger: float             # parent must be at most this hungry / thirsty
    max_thirst: float
    min_energy: float
    min_health: float
    chance: float                 # birth probability per eligible tick
    energy_cost: float
    hunger_cost: float            # added to the parent's hunger
    max_population: int           # living individuals of this species
    max_age: int | None = None    # old-age death; None = never
    offspring_hunger: float = 30.0
    offspring_thirst: float = 30.0
    offspring_energy: float = 60.0


class ReproductionConfig(_Frozen):
    herbivore: SpeciesReproductionConfig
    predator: SpeciesReproductionConfig
    prune_dead_after: int = 50    # drop corpses after N ticks so long runs stay bounded


class WorldConfig(_Frozen):
    map: MapConfig
    population: PopulationConfig
    time: TimeConfig
    species: dict[str, SpeciesConfig]
    metabolism: MetabolismConfig
    combat: CombatConfig
    reproduction: ReproductionConfig | None = None  # None = fixed population (MVP rules)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_raw(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    parent = data.pop("extends", None)
    if parent is None:
        return data
    return _deep_merge(_load_raw(path.parent / f"{parent}.yaml"), data)


def resolve_world_path(name_or_path: str) -> Path:
    """Accept 'map_a', 'map_b', 'default' or a yaml path."""
    path = Path(name_or_path)
    if path.suffix in {".yaml", ".yml"}:
        return path
    alias = "default" if name_or_path == "map_a" else name_or_path
    return CONFIG_DIR / "world" / f"{alias}.yaml"


def load_world_config(name_or_path: str = "map_a", **overrides: Any) -> WorldConfig:
    raw = _load_raw(resolve_world_path(name_or_path))
    if overrides:
        raw = _deep_merge(raw, overrides)
    return WorldConfig.model_validate(raw)
