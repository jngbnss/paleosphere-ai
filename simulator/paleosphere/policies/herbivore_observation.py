"""Observation vector for a learning herbivore (Phase 7, multi-agent).

Same principles as the predator observation: only what the animal could perceive (nearest
visible predator within vision, nearest edible plant, nearest water, visible herd mates),
normalised to [-1, 1]. Every herbivore uses this encoder, so one shared policy can control the
whole herd (parameter sharing).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.core.geometry import distance
from paleosphere.entities import Species
from paleosphere.policies.actions import HerbivoreAction
from paleosphere.policies.observation import OBSTACLE_SENSE_RANGE

if TYPE_CHECKING:
    from paleosphere.core.world import World

HERB_OBS_FIELDS = (
    "energy", "hunger", "thirst", "health", "speed",
    "predator_visible", "predator_distance", "predator_dir_cos", "predator_dir_sin",
    "predator_closing_speed", "predator_targets_me",
    "food_distance", "food_dir_cos", "food_dir_sin", "food_amount", "on_food",
    "water_distance", "water_dir_cos", "water_dir_sin",
    "herd_visible", "herd_distance", "herd_dir_cos", "herd_dir_sin",
    "obstacle_proximity", "is_night",
    *(f"prev_action_{a.name.lower()}" for a in HerbivoreAction),
)
HERB_OBS_DIM = len(HERB_OBS_FIELDS)
HERD_NORMALIZER = 8.0  # visible mates are counted up to the default herd size


def _angle(src: np.ndarray, dst: np.ndarray) -> float:
    return math.atan2(float(dst[1] - src[1]), float(dst[0] - src[0]))


def herbivore_observation(world: World, agent_id: str) -> np.ndarray:
    me = world.dinos[agent_id]
    sp = world.config.species["herbivore"]
    vision = world.vision(me)
    diag = world.size * math.sqrt(2)
    obs = np.zeros(HERB_OBS_DIM, dtype=np.float32)
    obs[0] = me.energy / 100.0
    obs[1] = me.hunger / 100.0
    obs[2] = me.thirst / 100.0
    obs[3] = me.health / 100.0
    obs[4] = me.speed / sp.sprint_speed

    threat = world.nearest_visible(me, Species.PREDATOR)
    if threat is not None:
        d = distance(me.pos, threat.pos)
        a = _angle(me.pos, threat.pos)
        obs[5] = 1.0
        obs[6] = d / vision
        obs[7], obs[8] = math.cos(a), math.sin(a)
        # closing speed: how fast the gap shrinks (positive = predator approaching)
        if d > 1e-9:
            gap_dir = (me.pos - threat.pos) / d
            closing = float(np.dot(threat.vel - me.vel, gap_dir))
            obs[9] = closing / sp.sprint_speed
        obs[10] = 1.0 if threat.target_id == agent_id else 0.0
    else:
        obs[6] = 1.0

    food = world.nearest_food(me.pos)
    if food is not None:
        d = distance(me.pos, food.pos)
        a = _angle(me.pos, food.pos)
        obs[11] = max(0.0, d - food.radius) / diag
        obs[12], obs[13] = math.cos(a), math.sin(a)
        obs[14] = food.food / world.config.map.plants.max_food
        obs[15] = 1.0 if d <= food.radius else 0.0
    else:
        obs[11] = 1.0

    water, edge = world.nearest_water(me.pos)
    a = _angle(me.pos, water.pos)
    obs[16] = edge / diag
    obs[17], obs[18] = math.cos(a), math.sin(a)

    mates = [
        h.pos for h in world.alive(Species.HERBIVORE)
        if h.agent_id != agent_id and distance(me.pos, h.pos) <= vision
    ]
    if mates:
        center = np.mean(mates, axis=0)
        a = _angle(me.pos, center)
        obs[19] = len(mates) / HERD_NORMALIZER
        obs[20] = distance(me.pos, center) / vision
        obs[21], obs[22] = math.cos(a), math.sin(a)
    else:
        obs[20] = 1.0

    gap = min((distance(me.pos, r.pos) - r.radius for r in world.rocks), default=math.inf)
    obs[23] = max(0.0, 1.0 - max(0.0, gap) / OBSTACLE_SENSE_RANGE)
    obs[24] = 1.0 if world.is_night else 0.0
    if me.current_action in HerbivoreAction.__members__:
        obs[25 + int(HerbivoreAction[me.current_action])] = 1.0
    return np.clip(obs, -1.0, 1.0)
