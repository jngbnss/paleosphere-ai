from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from paleosphere.core.world import World


class RandomPolicy:
    def __init__(self, action_enum: type[IntEnum], seed: int | None = None):
        self.action_enum = action_enum
        self.name = f"random-{action_enum.__name__.lower()}"
        self.reset(seed)

    def reset(self, seed: int | None = None) -> None:
        self._rng = np.random.default_rng(seed)

    def act(self, world: World, agent_id: str) -> int:
        return int(self._rng.integers(len(self.action_enum)))

    def metadata(self) -> dict:
        return {"name": self.name, "kind": "random"}
