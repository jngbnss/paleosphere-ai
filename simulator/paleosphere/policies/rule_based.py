"""Hand-written baselines. These are NOT AI; they are what the PPO policy is compared to."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from paleosphere.config import CONFIG_DIR
from paleosphere.policies.actions import HerbivoreAction, PredatorAction
from paleosphere.policies.observation import herbivore_view, predator_view

if TYPE_CHECKING:
    from paleosphere.core.world import World

DEFAULT_RULES = CONFIG_DIR / "policies" / "rule_based.yaml"


def load_rules(path: Path = DEFAULT_RULES) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class RuleBasedPredator:
    name = "rule-predator"

    def __init__(self, params: dict | None = None):
        self.p = params or load_rules()["predator"]

    def reset(self, seed: int | None = None) -> None:
        pass

    def act(self, world: World, agent_id: str) -> int:
        v = predator_view(world, agent_id)
        p = self.p
        prev = v.prev_action

        drinking = prev == PredatorAction.GO_TO_WATER and v.thirst > p["thirst_done"]
        if v.thirst > p["thirst_go_water"] or drinking:
            return PredatorAction.GO_TO_WATER
        resting = prev == PredatorAction.REST and v.energy < p["energy_rested"]
        if v.energy < p["energy_rest"] or resting:
            return PredatorAction.REST
        if v.hunger < p["hunger_rest"]:
            return PredatorAction.REST
        if v.target_id is None:
            return PredatorAction.SEARCH
        if v.chase_ticks > p["give_up_chase_ticks"]:
            return PredatorAction.GIVE_UP
        if v.prey_distance <= v.attack_range and v.attack_cooldown == 0:
            return PredatorAction.ATTACK
        if v.prey_distance <= p["chase_distance"]:
            return PredatorAction.CHASE
        return PredatorAction.APPROACH

    def metadata(self) -> dict:
        return {"name": self.name, "kind": "rule_based", "params": dict(self.p)}


class RuleBasedHerbivore:
    name = "rule-herbivore"

    def __init__(self, params: dict | None = None):
        self.p = params or load_rules()["herbivore"]

    def reset(self, seed: int | None = None) -> None:
        pass

    def act(self, world: World, agent_id: str) -> int:
        v = herbivore_view(world, agent_id)
        p = self.p
        prev = v.current_action

        if v.predator_distance is not None:
            limit = p["flee_distance"]
            if prev == HerbivoreAction.FLEE.name:
                limit *= p["flee_release_multiplier"]
            if v.predator_distance <= limit:
                return HerbivoreAction.FLEE
        drinking = prev == HerbivoreAction.GO_TO_WATER.name and v.thirst > p["thirst_done"]
        if v.thirst > p["thirst_go_water"] or drinking:
            return HerbivoreAction.GO_TO_WATER
        eating = prev == HerbivoreAction.GO_TO_FOOD.name and v.hunger > p["hunger_done"]
        if v.hunger > p["hunger_go_food"] or eating:
            return HerbivoreAction.GO_TO_FOOD
        resting = prev == HerbivoreAction.REST.name and v.energy < p["energy_rested"]
        if v.energy < p["energy_rest"] or resting:
            return HerbivoreAction.REST
        return HerbivoreAction.WANDER

    def metadata(self) -> dict:
        return {"name": self.name, "kind": "rule_based", "params": dict(self.p)}
