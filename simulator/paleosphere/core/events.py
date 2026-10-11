from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class EventKind(StrEnum):
    ATTACK_HIT = "attack_hit"
    ATTACK_MISS = "attack_miss"
    ATTACK_INVALID = "attack_invalid"
    KILL = "kill"
    DEATH = "death"
    EAT = "eat"
    DRINK = "drink"
    GIVE_UP = "give_up"
    BIRTH = "birth"


@dataclass(slots=True, frozen=True)
class Event:
    tick: int
    kind: EventKind
    agent_id: str
    target_id: str | None = None
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "kind": str(self.kind),
            "agent_id": self.agent_id,
            "target_id": self.target_id,
            "data": self.data,
        }
