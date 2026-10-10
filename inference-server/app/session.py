"""One simulation run driven by a viewer connection."""

from __future__ import annotations

from app.schemas import (
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
from paleosphere.core.world import World
from paleosphere.entities import Species
from paleosphere.explain import status_code, status_label
from paleosphere.logging.episode import EpisodeTracker
from paleosphere.policies import RuleBasedHerbivore
from paleosphere.policies.base import Policy

MAX_TICKS = 2000


class SimSession:
    def __init__(self, cmd: StartCommand, predator_policy: Policy):
        self.config = load_world_config(cmd.map)
        self.world = World(self.config, cmd.seed)
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
        return self.world.done or self.world.tick >= MAX_TICKS

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
        energy_before = world.dinos[self.predator_id].energy
        self.last_events = world.step(actions)
        self.tracker.record(actions, energy_before, self.last_events)

    def snapshot(self) -> Snapshot:
        w = self.world
        raw = w.to_snapshot()
        pred = w.dinos[self.predator_id]
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
            ),
        )
