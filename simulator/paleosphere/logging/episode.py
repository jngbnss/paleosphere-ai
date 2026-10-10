"""Episode runner and summary metrics shared by the CLI, evaluation and tests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from paleosphere.config import WorldConfig
from paleosphere.core.events import Event, EventKind
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.policies import PredatorAction
from paleosphere.policies.base import Policy


@dataclass(slots=True)
class EpisodeSummary:
    seed: int
    map: str
    predator_policy: str
    ticks: int
    predator_alive: bool
    predator_death_cause: str | None
    predator_survival_ticks: int
    kills: int
    attack_attempts: int
    attack_hits: int
    invalid_attacks: int
    give_ups: int
    hunt_success_rate: float
    energy_spent: float
    energy_per_kill: float | None
    herbivores_alive: int
    herbivore_deaths: dict[str, int] = field(default_factory=dict)
    predator_action_counts: dict[str, int] = field(default_factory=dict)
    final_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class EpisodeTracker:
    """Accumulates per-tick events into an EpisodeSummary for one predator."""

    def __init__(self, world: World, predator_id: str, policy_name: str):
        self.world = world
        self.predator_id = predator_id
        self.policy_name = policy_name
        self.events: Counter[EventKind] = Counter()
        self.actions: Counter[str] = Counter()
        self.energy_spent = 0.0
        self.survival_ticks = 0

    def record(self, actions: dict[str, int], energy_before: float, events: list[Event]) -> None:
        pred = self.world.dinos[self.predator_id]
        if self.predator_id in actions:
            self.actions[PredatorAction(actions[self.predator_id]).name] += 1
            self.energy_spent += max(0.0, energy_before - pred.energy)
            if pred.alive:
                self.survival_ticks += 1
        for e in events:
            if e.agent_id == self.predator_id or e.kind == EventKind.KILL:
                self.events[e.kind] += 1

    def summary(self) -> EpisodeSummary:
        w = self.world
        pred = w.dinos[self.predator_id]
        kills = self.events[EventKind.KILL]
        valid = (
            self.events[EventKind.ATTACK_HIT] + self.events[EventKind.ATTACK_MISS]
        )
        herb_deaths = Counter(
            str(d.death_cause)
            for d in w.dinos.values()
            if d.species == Species.HERBIVORE and not d.alive
        )
        return EpisodeSummary(
            seed=w.seed,
            map=w.config.map.name,
            predator_policy=self.policy_name,
            ticks=w.tick,
            predator_alive=pred.alive,
            predator_death_cause=str(pred.death_cause) if pred.death_cause else None,
            predator_survival_ticks=self.survival_ticks,
            kills=kills,
            attack_attempts=valid + self.events[EventKind.ATTACK_INVALID],
            attack_hits=self.events[EventKind.ATTACK_HIT],
            invalid_attacks=self.events[EventKind.ATTACK_INVALID],
            give_ups=self.events[EventKind.GIVE_UP],
            hunt_success_rate=round(kills / valid, 6) if valid else 0.0,
            energy_spent=round(self.energy_spent, 6),
            energy_per_kill=round(self.energy_spent / kills, 6) if kills else None,
            herbivores_alive=len(w.alive(Species.HERBIVORE)),
            herbivore_deaths=dict(sorted(herb_deaths.items())),
            predator_action_counts=dict(sorted(self.actions.items())),
            final_hash=w.snapshot_hash(),
        )


def run_episode(
    config: WorldConfig,
    seed: int,
    predator_policy: Policy,
    herbivore_policy: Policy,
    max_ticks: int = 2000,
    on_tick: Callable[[World, list[Event]], None] | None = None,
) -> EpisodeSummary:
    world = World(config, seed)
    predator_policy.reset(seed)
    herbivore_policy.reset(seed)
    predator_id = world.alive(Species.PREDATOR)[0].agent_id
    tracker = EpisodeTracker(world, predator_id, predator_policy.name)
    if on_tick is not None:
        on_tick(world, [])
    while world.tick < max_ticks and not world.done:
        actions = {
            d.agent_id: int(
                (predator_policy if d.species == Species.PREDATOR else herbivore_policy).act(
                    world, d.agent_id
                )
            )
            for d in world.alive()
        }
        energy_before = world.dinos[predator_id].energy
        events = world.step(actions)
        tracker.record(actions, energy_before, events)
        if on_tick is not None:
            on_tick(world, events)
    return tracker.summary()
