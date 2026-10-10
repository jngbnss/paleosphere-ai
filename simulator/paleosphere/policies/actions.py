"""Macro action spaces. The simulator turns these into steering and interactions."""

from __future__ import annotations

from enum import IntEnum


class PredatorAction(IntEnum):
    SEARCH = 0
    APPROACH = 1  # walk toward the current target
    CHASE = 2  # sprint toward the current target
    ATTACK = 3
    GO_TO_WATER = 4
    REST = 5
    GIVE_UP = 6  # drop the current target and ignore it for a while


class HerbivoreAction(IntEnum):
    WANDER = 0
    FLEE = 1
    GO_TO_FOOD = 2
    GO_TO_WATER = 3
    REST = 4


PURSUIT_ACTIONS = frozenset(
    {PredatorAction.APPROACH, PredatorAction.CHASE, PredatorAction.ATTACK}
)
