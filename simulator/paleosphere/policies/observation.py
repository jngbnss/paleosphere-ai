"""What an agent is allowed to perceive.

`PredatorView` is the single source for both the rule-based predator and the RL observation
vector, so the baseline and the learned policy see exactly the same information.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.core.geometry import distance
from paleosphere.entities import Species
from paleosphere.policies.actions import PredatorAction

if TYPE_CHECKING:
    from paleosphere.core.world import World

OBS_DIM = 26
OBSTACLE_SENSE_RANGE = 5.0
MAX_CHASE_TICKS = 80

OBS_FIELDS = (
    "energy", "hunger", "thirst", "health", "speed",
    "prey_visible", "prey_distance", "prey_dir_cos", "prey_dir_sin",
    "prey_rel_vel_x", "prey_rel_vel_z", "prey_energy",
    "water_distance", "water_dir_cos", "water_dir_sin",
    "obstacle_proximity", "chase_ticks", "attack_cooldown", "is_night",
    *(f"prev_action_{a.name.lower()}" for a in PredatorAction),
)
assert len(OBS_FIELDS) == OBS_DIM


@dataclass(slots=True, frozen=True)
class PredatorView:
    energy: float
    hunger: float
    thirst: float
    health: float
    speed: float
    sprint_speed: float
    vision: float
    target_id: str | None
    prey_distance: float | None
    prey_angle: float | None
    prey_rel_vel: tuple[float, float]
    prey_energy: float | None
    water_edge_distance: float
    water_angle: float
    obstacle_proximity: float
    chase_ticks: int
    attack_cooldown: int
    max_attack_cooldown: int
    attack_range: float
    is_night: bool
    prev_action: PredatorAction | None
    map_diagonal: float


@dataclass(slots=True, frozen=True)
class HerbivoreView:
    energy: float
    hunger: float
    thirst: float
    health: float
    predator_distance: float | None
    current_action: str


def _angle(src: np.ndarray, dst: np.ndarray) -> float:
    return math.atan2(float(dst[1] - src[1]), float(dst[0] - src[0]))


def predator_view(world: World, agent_id: str) -> PredatorView:
    me = world.dinos[agent_id]
    sp = world.config.species["predator"]
    target = world.dinos.get(me.target_id) if me.target_id else None
    if target is not None and not target.alive:
        target = None

    water, edge = world.nearest_water(me.pos)
    nearest_rock_gap = min(
        (distance(me.pos, r.pos) - r.radius for r in world.rocks), default=math.inf
    )
    obstacle = max(0.0, 1.0 - max(0.0, nearest_rock_gap) / OBSTACLE_SENSE_RANGE)
    try:
        prev = PredatorAction[me.current_action]
    except KeyError:
        prev = None

    return PredatorView(
        energy=me.energy,
        hunger=me.hunger,
        thirst=me.thirst,
        health=me.health,
        speed=me.speed,
        sprint_speed=sp.sprint_speed,
        vision=world.vision(me),
        target_id=target.agent_id if target else None,
        prey_distance=distance(me.pos, target.pos) if target else None,
        prey_angle=_angle(me.pos, target.pos) if target else None,
        prey_rel_vel=(
            (float(target.vel[0] - me.vel[0]), float(target.vel[1] - me.vel[1]))
            if target
            else (0.0, 0.0)
        ),
        prey_energy=target.energy if target else None,
        water_edge_distance=edge,
        water_angle=_angle(me.pos, water.pos),
        obstacle_proximity=obstacle,
        chase_ticks=me.chase_ticks,
        attack_cooldown=me.attack_cooldown,
        max_attack_cooldown=world.config.combat.attack_cooldown,
        attack_range=world.config.combat.attack_range,
        is_night=world.is_night,
        prev_action=prev,
        map_diagonal=world.size * math.sqrt(2),
    )


def herbivore_view(world: World, agent_id: str) -> HerbivoreView:
    me = world.dinos[agent_id]
    threat = world.nearest_visible(me, Species.PREDATOR)
    return HerbivoreView(
        energy=me.energy,
        hunger=me.hunger,
        thirst=me.thirst,
        health=me.health,
        predator_distance=distance(me.pos, threat.pos) if threat else None,
        current_action=me.current_action,
    )


def encode_predator_view(v: PredatorView) -> np.ndarray:
    """Normalize a PredatorView into the 26-dim RL observation in [-1, 1]."""
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    obs[0] = v.energy / 100.0
    obs[1] = v.hunger / 100.0
    obs[2] = v.thirst / 100.0
    obs[3] = v.health / 100.0
    obs[4] = v.speed / v.sprint_speed
    if v.target_id is not None:
        obs[5] = 1.0
        obs[6] = v.prey_distance / v.vision
        obs[7] = math.cos(v.prey_angle)
        obs[8] = math.sin(v.prey_angle)
        obs[9] = v.prey_rel_vel[0] / v.sprint_speed
        obs[10] = v.prey_rel_vel[1] / v.sprint_speed
        obs[11] = v.prey_energy / 100.0
    else:
        obs[6] = 1.0
    obs[12] = v.water_edge_distance / v.map_diagonal
    obs[13] = math.cos(v.water_angle)
    obs[14] = math.sin(v.water_angle)
    obs[15] = v.obstacle_proximity
    obs[16] = v.chase_ticks / MAX_CHASE_TICKS
    obs[17] = v.attack_cooldown / max(1, v.max_attack_cooldown)
    obs[18] = 1.0 if v.is_night else 0.0
    if v.prev_action is not None:
        obs[19 + int(v.prev_action)] = 1.0
    return np.clip(obs, -1.0, 1.0)


def predator_observation(world: World, agent_id: str) -> np.ndarray:
    return encode_predator_view(predator_view(world, agent_id))
