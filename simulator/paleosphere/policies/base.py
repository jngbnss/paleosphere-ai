from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from paleosphere.core.world import World


@runtime_checkable
class Policy(Protocol):
    """Every policy (random, rule-based, PPO, player) exposes the same interface.

    `act` receives the world and an agent id; each policy builds only the view it is
    allowed to see (see policies/observation.py). It returns an action int.
    """

    name: str

    def reset(self, seed: int | None = None) -> None: ...

    def act(self, world: World, agent_id: str) -> int: ...

    def metadata(self) -> dict: ...
