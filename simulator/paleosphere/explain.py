"""Human-readable status labels for the viewer.

These labels translate the agent's *observation and chosen action* into words. They are not
an explanation of what a neural network "thinks"; the same mapping is used for rule-based and
PPO predators so the viewer shows behaviour, not model internals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from paleosphere.entities import Species
from paleosphere.policies.actions import HerbivoreAction, PredatorAction
from paleosphere.policies.observation import predator_view

if TYPE_CHECKING:
    from paleosphere.core.world import World

LOW_ENERGY = 20.0

# code -> Korean label shown in Godot
LABELS = {
    "searching": "탐색 중",
    "prey_spotted": "먹잇감 발견",
    "chasing": "추격 중",
    "attacking": "공격 준비",
    "low_energy": "에너지 부족",
    "seeking_water": "물 탐색",
    "giving_up": "추격 포기",
    "resting": "휴식",
    "fleeing": "도주",
    "foraging": "먹이 찾기",
    "wandering": "무리 근처 배회",
    "dead": "사망",
}


def status_code(world: World, agent_id: str) -> str:
    dino = world.dinos[agent_id]
    if not dino.alive:
        return "dead"
    if dino.species == Species.HERBIVORE:
        try:
            action = HerbivoreAction[dino.current_action]
        except KeyError:
            return "wandering"
        return {
            HerbivoreAction.FLEE: "fleeing",
            HerbivoreAction.GO_TO_FOOD: "foraging",
            HerbivoreAction.GO_TO_WATER: "seeking_water",
            HerbivoreAction.REST: "low_energy" if dino.energy < LOW_ENERGY else "resting",
        }.get(action, "wandering")

    try:
        action = PredatorAction[dino.current_action]
    except KeyError:
        return "searching"
    view = predator_view(world, agent_id)
    if action == PredatorAction.REST:
        return "low_energy" if view.energy < LOW_ENERGY else "resting"
    if action == PredatorAction.SEARCH:
        return "prey_spotted" if view.target_id else "searching"
    return {
        PredatorAction.APPROACH: "prey_spotted",
        PredatorAction.CHASE: "chasing",
        PredatorAction.ATTACK: "attacking",
        PredatorAction.GO_TO_WATER: "seeking_water",
        PredatorAction.GIVE_UP: "giving_up",
    }[action]


def status_label(code: str) -> str:
    return LABELS[code]
