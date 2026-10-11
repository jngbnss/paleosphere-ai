"""One simulation run driven by a viewer connection."""

from __future__ import annotations

from app.schemas import (
    CLIENT_POLICY,
    DinoState,
    EventState,
    Metrics,
    PlantState,
    RockState,
    Snapshot,
    StartCommand,
    WaterState,
)
from paleosphere.config import load_world_config
from paleosphere.core.events import EventKind
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.explain import status_code, status_label
from paleosphere.logging.episode import EpisodeTracker
from paleosphere.policies import RuleBasedHerbivore, predator_observation
from paleosphere.policies.base import Policy

MAX_TICKS = 2000
ECOSYSTEM_MAX_TICKS = 20000  # maps with reproduction run long (population dynamics)


class ClientPolicy:
    """Predator decisions made by the viewer (client mode). Holds one pending action."""

    name = CLIENT_POLICY

    def __init__(self) -> None:
        self.pending: int | None = None

    def reset(self, seed: int | None = None) -> None:
        self.pending = None

    def act(self, world, agent_id: str) -> int:
        if self.pending is None:
            raise RuntimeError("client mode: no action received for this tick")
        action, self.pending = self.pending, None
        return action

    def metadata(self) -> dict:
        return {"name": self.name, "kind": "client"}


class SimSession:
    def __init__(self, cmd: StartCommand, predator_policy: Policy):
        self.config = load_world_config(cmd.map)
        self.world = World(self.config, cmd.seed)
        if isinstance(predator_policy, ClientPolicy) and len(
            self.world.alive(Species.PREDATOR)
        ) != 1:
            raise ValueError("client mode drives exactly one predator; use map_a or map_b")
        self.max_ticks = MAX_TICKS if self.config.reproduction is None else ECOSYSTEM_MAX_TICKS
        self.births = 0
        self.predator_policy = predator_policy
        self.predator_policy_name = cmd.predator_policy
        self.herbivore_policy = RuleBasedHerbivore()
        self.predator_policy.reset(cmd.seed)
        self.ticks_per_second = cmd.ticks_per_second
        self.paused = False
        self.predator_id = self.world.alive(Species.PREDATOR)[0].agent_id
        self.tracker = EpisodeTracker(self.world, self.predator_id, cmd.predator_policy)
        self.last_events: list = []

    @property
    def done(self) -> bool:
        return self.world.done or self.world.tick >= self.max_ticks

    @property
    def client_mode(self) -> bool:
        return isinstance(self.predator_policy, ClientPolicy)

    @property
    def ready(self) -> bool:
        """Can advance a tick now (client mode needs the viewer's action first)."""
        return not self.done and (not self.client_mode or self.predator_policy.pending is not None)

    def set_client_action(self, tick: int, action: int) -> str | None:
        """Queue the viewer's action; returns an error message if it does not apply."""
        if not self.client_mode:
            return f"action is only accepted when predator_policy is {CLIENT_POLICY!r}"
        if tick != self.world.tick:
            return f"stale action for tick {tick}; current tick is {self.world.tick}"
        if self.done:
            return "episode is over"
        self.predator_policy.pending = action
        return None

    def step(self) -> None:
        if self.done:
            return
        world = self.world
        actions = {
            d.agent_id: int(
                (
                    self.predator_policy
                    if d.species == Species.PREDATOR
                    else self.herbivore_policy
                ).act(world, d.agent_id)
            )
            for d in world.alive()
        }
        energy_before = self.tracker.predator.energy
        self.last_events = world.step(actions)
        self.births += sum(e.kind == EventKind.BIRTH for e in self.last_events)
        self.tracker.record(actions, energy_before, self.last_events)

    def snapshot(self) -> Snapshot:
        w = self.world
        raw = w.to_snapshot()
        pred = self.tracker.predator
        dinos = []
        for d in raw["dinos"]:
            code = status_code(w, d["agent_id"])
            dino = w.dinos[d["agent_id"]]
            dinos.append(
                DinoState(
                    **d, status_code=code, status_label=status_label(code), vision=w.vision(dino)
                )
            )
        ev = self.tracker.events
        return Snapshot(
            tick=w.tick,
            seed=w.seed,
            map=w.config.map.name,
            map_size=w.size,
            is_night=w.is_night,
            predator_policy=self.predator_policy_name,
            paused=self.paused,
            ticks_per_second=self.ticks_per_second,
            done=self.done,
            dinos=dinos,
            plants=[PlantState(**p) for p in raw["plants"]],
            waters=[WaterState(**x) for x in raw["waters"]],
            rocks=[RockState(**r) for r in raw["rocks"]],
            events=[EventState(**e.to_dict()) for e in self.last_events],
            metrics=Metrics(
                herbivores_alive=len(w.alive(Species.HERBIVORE)),
                predator_energy=round(pred.energy, 3),
                predator_hunger=round(pred.hunger, 3),
                kills=ev["kill"],
                attack_attempts=ev["attack_hit"] + ev["attack_miss"] + ev["attack_invalid"],
                invalid_attacks=ev["attack_invalid"],
                predators_alive=len(w.alive(Species.PREDATOR)),
                births=self.births,
            ),
            predator_observation=(
                predator_observation(w, self.predator_id).tolist()
                if self.client_mode and not self.done
                else None
            ),
        )
