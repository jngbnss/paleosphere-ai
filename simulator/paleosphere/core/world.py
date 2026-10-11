"""Deterministic ecosystem World with a fixed tick order.

Tick order (see docs/office-hours.md §3):
  (outside)  observations are built and policies decide from the current state
  1. apply decisions (targets, give-up, chase counters)
  2. movement (steering, rocks, map bounds)
  3. interactions: attack -> eat -> drink
  4. metabolism
  5. deaths
  6. plant regrowth
  7. (reproduction enabled) old age, births, corpse pruning
  8. tick += 1, day/night, target refresh for the next observation
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping

import numpy as np

from paleosphere.combat import AttackOutcome, resolve_attack
from paleosphere.config import WorldConfig
from paleosphere.core.events import Event, EventKind
from paleosphere.core.geometry import distance, unit
from paleosphere.core.metabolism import apply_metabolism
from paleosphere.entities import DeathCause, Dino, Species
from paleosphere.policies.actions import PURSUIT_ACTIONS, HerbivoreAction, PredatorAction
from paleosphere.resources import PlantPatch, WaterSource, generate_map

MIN_EDIBLE_FOOD = 5.0
WAYPOINT_REACHED = 1.0
BORDER_MARGIN = 6.0
ROCK_CLEARANCE = 0.3


class World:
    def __init__(self, config: WorldConfig, seed: int):
        self.config = config
        self.seed = seed
        # spawn(4)'s first three children equal spawn(3)'s, so adding the reproduction
        # stream does not change worlds without reproduction.
        layout_ss, move_ss, combat_ss, repro_ss = np.random.SeedSequence(seed).spawn(4)
        self.move_rng = np.random.default_rng(move_ss)
        self.combat_rng = np.random.default_rng(combat_ss)
        self.repro_rng = np.random.default_rng(repro_ss)
        gen = generate_map(config, np.random.default_rng(layout_ss))
        self.plants = gen.plants
        self.waters = gen.waters
        self.rocks = gen.rocks
        self._rock_shapes = [
            (float(r.pos[0]), float(r.pos[1]), r.radius + ROCK_CLEARANCE) for r in self.rocks
        ]
        self.dinos: dict[str, Dino] = {d.agent_id: d for d in sorted(gen.dinos, key=_id)}
        self._spawned = {s: sum(d.species == s for d in self.dinos.values()) for s in Species}
        self.tick = 0
        self.is_night = False
        self.events: list[Event] = []
        self._update_day_night()
        self._update_targets()

    # ------------------------------------------------------------------ queries
    @property
    def size(self) -> float:
        return self.config.map.size

    def alive(self, species: Species | None = None) -> list[Dino]:
        return [
            d for d in self.dinos.values() if d.alive and (species is None or d.species == species)
        ]

    def vision(self, dino: Dino) -> float:
        v = self.config.species[dino.species.value].vision
        return v * self.config.time.night_vision_multiplier if self.is_night else v

    def nearest_water(self, pos: np.ndarray) -> tuple[WaterSource, float]:
        """Nearest water and the distance to its edge (0 when inside)."""
        best = min(self.waters, key=lambda w: (distance(pos, w.pos) - w.radius, w.water_id))
        return best, max(0.0, distance(pos, best.pos) - best.radius)

    def nearest_food(self, pos: np.ndarray) -> PlantPatch | None:
        edible = [p for p in self.plants if p.food >= MIN_EDIBLE_FOOD]
        if not edible:
            return None
        return min(edible, key=lambda p: (distance(pos, p.pos), p.plant_id))

    def nearest_visible(self, dino: Dino, species: Species) -> Dino | None:
        vision = self.vision(dino)
        candidates = [
            o for o in self.alive(species) if distance(dino.pos, o.pos) <= vision
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda o: (distance(dino.pos, o.pos), o.agent_id))

    def herd_center(self) -> np.ndarray:
        herd = self.alive(Species.HERBIVORE)
        if not herd:
            return np.full(2, self.size / 2)
        return np.mean([h.pos for h in herd], axis=0)

    @property
    def done(self) -> bool:
        if self.config.reproduction is not None:
            # an ecosystem keeps running while either species can still grow back
            return not self.alive()
        return not self.alive(Species.PREDATOR) or not self.alive(Species.HERBIVORE)

    # --------------------------------------------------------------------- step
    def step(self, actions: Mapping[str, int]) -> list[Event]:
        """Advance one tick. `actions` maps agent_id -> action int; missing = REST."""
        self.events = []
        decided = {
            d.agent_id: self._action_for(d, actions.get(d.agent_id)) for d in self.alive()
        }
        for agent_id, action in decided.items():
            self._apply_decision(self.dinos[agent_id], action)
        for agent_id, action in decided.items():
            self._move(self.dinos[agent_id], action)
        self._resolve_attacks(decided)
        self._resolve_feeding(decided)
        for agent_id, action in decided.items():
            dino = self.dinos[agent_id]
            if not dino.alive:
                continue
            sp = self.config.species[dino.species.value]
            resting = _is_rest(dino, action)
            moved = dino.speed > 1e-9
            cause = apply_metabolism(dino, sp, self.config.metabolism, resting, moved)
            if cause is not None:
                self._kill(dino, cause)
            else:
                dino.age += 1
            dino.attack_cooldown = max(0, dino.attack_cooldown - 1)
        for plant in self.plants:
            plant.regrow()
        if self.config.reproduction is not None:
            self._life_cycle()
        self.tick += 1
        self._update_day_night()
        self._update_targets()
        return self.events

    # ---------------------------------------------------------------- internals
    def _action_for(self, dino: Dino, action: int | None):
        if dino.species == Species.PREDATOR:
            return PredatorAction(PredatorAction.REST if action is None else action)
        return HerbivoreAction(HerbivoreAction.REST if action is None else action)

    def _apply_decision(self, dino: Dino, action) -> None:
        dino.current_action = action.name
        if dino.species != Species.PREDATOR:
            return
        if action == PredatorAction.GIVE_UP:
            if dino.target_id is not None:
                self._emit(EventKind.GIVE_UP, dino.agent_id, dino.target_id)
                dino.ignored_target_id = dino.target_id
                dino.ignore_until = self.tick + self.config.combat.give_up_ignore_ticks
            dino.target_id = None
            dino.chase_ticks = 0
        elif action in PURSUIT_ACTIONS and dino.target_id is not None:
            dino.chase_ticks += 1
        else:
            dino.chase_ticks = 0

    def _move(self, dino: Dino, action) -> None:
        sp = self.config.species[dino.species.value]
        can_sprint = dino.energy >= self.config.metabolism.min_sprint_energy
        goal: np.ndarray | None = None
        direction: np.ndarray | None = None
        speed = 0.0
        sprint = False

        if dino.species == Species.PREDATOR:
            target = self.dinos.get(dino.target_id) if dino.target_id else None
            if action == PredatorAction.SEARCH or (
                target is None and action in (PredatorAction.APPROACH, PredatorAction.CHASE)
            ):
                goal, speed = self._wander_goal(dino), sp.walk_speed
            elif action == PredatorAction.APPROACH:
                goal, speed = target.pos, sp.walk_speed
            elif action == PredatorAction.CHASE:
                sprint = can_sprint
                goal, speed = target.pos, sp.sprint_speed if sprint else sp.walk_speed
            elif action == PredatorAction.ATTACK and target is not None:
                if distance(dino.pos, target.pos) > self.config.combat.attack_range * 0.8:
                    goal, speed = target.pos, sp.walk_speed
            elif action == PredatorAction.GO_TO_WATER:
                goal, speed = self._water_goal(dino), sp.walk_speed
        else:
            if action == HerbivoreAction.WANDER:
                goal, speed = self._wander_goal(dino), sp.walk_speed
            elif action == HerbivoreAction.FLEE:
                threat = self.nearest_visible(dino, Species.PREDATOR)
                if threat is not None:
                    direction = self._flee_direction(dino, threat)
                    sprint = can_sprint
                    speed = sp.sprint_speed if sprint else sp.walk_speed
            elif action == HerbivoreAction.GO_TO_FOOD:
                plant = self.nearest_food(dino.pos)
                if plant is not None and distance(dino.pos, plant.pos) > plant.radius * 0.5:
                    goal, speed = plant.pos, sp.walk_speed
            elif action == HerbivoreAction.GO_TO_WATER:
                goal, speed = self._water_goal(dino), sp.walk_speed

        # Plain float math: numpy overhead on 2-element arrays dominated the tick cost.
        ox, oz = float(dino.pos[0]), float(dino.pos[1])
        x, z = ox, oz
        if goal is not None:
            dx, dz = float(goal[0]) - x, float(goal[1]) - z
            dist = math.hypot(dx, dz)
            if dist > 1e-9:
                step = min(speed, dist)
                x += dx / dist * step
                z += dz / dist * step
        elif direction is not None:
            x += float(direction[0]) * speed
            z += float(direction[1]) * speed
        x, z = self._resolve_collisions(x, z)
        vx, vz = x - ox, z - oz
        dino.vel = np.array([vx, vz])
        dino.pos = np.array([x, z])
        dino.sprinting = sprint and math.hypot(vx, vz) > sp.walk_speed + 1e-9

    def _wander_goal(self, dino: Dino) -> np.ndarray:
        if dino.waypoint is None or distance(dino.pos, dino.waypoint) < WAYPOINT_REACHED:
            if dino.species == Species.HERBIVORE:
                spread = self.config.population.herd_spread
                wp = self.herd_center() + self.move_rng.uniform(-spread, spread, size=2)
            else:
                wp = self.move_rng.uniform(2.0, self.size - 2.0, size=2)
            dino.waypoint = np.clip(wp, 1.0, self.size - 1.0)
        return dino.waypoint

    def _water_goal(self, dino: Dino) -> np.ndarray | None:
        water, edge = self.nearest_water(dino.pos)
        if distance(dino.pos, water.pos) < water.radius * 0.7:
            return None
        return water.pos

    def _flee_direction(self, dino: Dino, threat: Dino) -> np.ndarray:
        away = unit(dino.pos - threat.pos)
        # Steer back toward the middle when hugging the border so prey does not get pinned.
        center_pull = np.zeros(2)
        for axis in range(2):
            if dino.pos[axis] < BORDER_MARGIN:
                center_pull[axis] = 1.0
            elif dino.pos[axis] > self.size - BORDER_MARGIN:
                center_pull[axis] = -1.0
        d = unit(away + center_pull)
        return d if np.any(d) else unit(np.array([self.size / 2, self.size / 2]) - dino.pos)

    def _resolve_collisions(self, x: float, z: float) -> tuple[float, float]:
        """Push a point out of rocks, then clamp it to the map."""
        for rx, rz, min_gap in self._rock_shapes:
            dx, dz = x - rx, z - rz
            d2 = dx * dx + dz * dz
            if d2 < min_gap * min_gap:
                d = math.sqrt(d2)
                if d < 1e-9:
                    dx, dz, d = 1.0, 0.0, 1.0
                x, z = rx + dx / d * min_gap, rz + dz / d * min_gap
        size = self.size
        return min(max(x, 0.0), size), min(max(z, 0.0), size)

    def _resolve_attacks(self, decided: Mapping[str, object]) -> None:
        for agent_id, action in decided.items():
            attacker = self.dinos[agent_id]
            if attacker.species != Species.PREDATOR or action != PredatorAction.ATTACK:
                continue
            target = self.dinos.get(attacker.target_id) if attacker.target_id else None
            result = resolve_attack(attacker, target, self.config.combat, self.combat_rng)
            target_id = target.agent_id if target else None
            if not result.valid:
                self._emit(
                    EventKind.ATTACK_INVALID, agent_id, target_id, reason=str(result.outcome)
                )
            elif result.outcome == AttackOutcome.MISS:
                self._emit(EventKind.ATTACK_MISS, agent_id, target_id)
            else:
                self._emit(EventKind.ATTACK_HIT, agent_id, target_id, damage=result.damage)
                if result.outcome == AttackOutcome.KILL:
                    self._emit(EventKind.KILL, agent_id, target_id)
                    self._kill(target, DeathCause.PREDATION, killer_id=agent_id)

    def _resolve_feeding(self, decided: Mapping[str, object]) -> None:
        met = self.config.metabolism
        for agent_id, action in decided.items():
            dino = self.dinos[agent_id]
            if not dino.alive:
                continue
            if dino.species == Species.HERBIVORE and action == HerbivoreAction.GO_TO_FOOD:
                for plant in self.plants:
                    if plant.food > 0 and distance(dino.pos, plant.pos) <= plant.radius:
                        eaten = min(met.eat_rate, plant.food, dino.hunger / met.hunger_per_food)
                        if eaten > 0:
                            plant.food -= eaten
                            dino.hunger -= eaten * met.hunger_per_food
                            self._emit(EventKind.EAT, agent_id, plant.plant_id, amount=eaten)
                        break
            if _is_water(dino, action):
                water, edge = self.nearest_water(dino.pos)
                if edge <= 0.0 and dino.thirst > 0:
                    before = dino.thirst
                    dino.thirst = max(0.0, dino.thirst - met.drink_rate)
                    self._emit(
                        EventKind.DRINK, agent_id, water.water_id, amount=before - dino.thirst
                    )

    def _life_cycle(self) -> None:
        """Old age, births and corpse pruning (only when reproduction is configured)."""
        repro = self.config.reproduction
        for dino in self.alive():
            rc = getattr(repro, dino.species.value)
            if rc.max_age is not None and dino.age >= rc.max_age:
                self._kill(dino, DeathCause.OLD_AGE)
        living = {s: len(self.alive(s)) for s in Species}
        for parent in self.alive():
            rc = getattr(repro, parent.species.value)
            if parent.breed_cooldown > 0:
                parent.breed_cooldown -= 1
                continue
            if not (
                parent.age >= rc.min_age
                and parent.hunger <= rc.max_hunger
                and parent.thirst <= rc.max_thirst
                and parent.energy >= rc.min_energy
                and parent.health >= rc.min_health
                and living[parent.species] < rc.max_population
            ):
                continue
            if self.repro_rng.random() >= rc.chance:
                continue
            child = self._give_birth(parent, rc)
            living[parent.species] += 1
            self._emit(EventKind.BIRTH, parent.agent_id, child.agent_id)
        cutoff = self.tick - repro.prune_dead_after
        stale = [
            i for i, d in self.dinos.items()
            if not d.alive and d.death_tick is not None and d.death_tick <= cutoff
        ]
        for agent_id in stale:
            del self.dinos[agent_id]

    def _give_birth(self, parent: Dino, rc) -> Dino:
        parent.energy = max(0.0, parent.energy - rc.energy_cost)
        parent.hunger = min(100.0, parent.hunger + rc.hunger_cost)
        parent.breed_cooldown = rc.cooldown
        offset = self.repro_rng.normal(0.0, 1.0, size=2)
        x, z = self._resolve_collisions(
            float(parent.pos[0] + offset[0]), float(parent.pos[1] + offset[1])
        )
        n = self._spawned[parent.species]
        self._spawned[parent.species] += 1
        child = Dino(
            agent_id=f"{parent.species.value}-{n:03d}",
            species=parent.species,
            pos=np.array([x, z]),
            energy=rc.offspring_energy,
            hunger=rc.offspring_hunger,
            thirst=rc.offspring_thirst,
            generation=parent.generation + 1,
            parent_id=parent.agent_id,
        )
        self.dinos[child.agent_id] = child
        return child

    def _kill(self, dino: Dino, cause: DeathCause, killer_id: str | None = None) -> None:
        dino.alive = False
        dino.death_tick = self.tick
        dino.death_cause = cause
        dino.vel = np.zeros(2)
        dino.target_id = None
        self._emit(EventKind.DEATH, dino.agent_id, killer_id, cause=str(cause))

    def _update_day_night(self) -> None:
        t = self.config.time
        phase = self.tick % t.day_length
        self.is_night = phase >= t.day_length * (1.0 - t.night_fraction)

    def _update_targets(self) -> None:
        for dino in self.alive(Species.PREDATOR):
            vision = self.vision(dino)
            candidates = [
                h
                for h in self.alive(Species.HERBIVORE)
                if distance(dino.pos, h.pos) <= vision
                and not (h.agent_id == dino.ignored_target_id and self.tick < dino.ignore_until)
            ]
            ids = {c.agent_id for c in candidates}
            if dino.target_id in ids:
                continue
            new = (
                min(candidates, key=lambda h: (distance(dino.pos, h.pos), h.agent_id))
                if candidates
                else None
            )
            new_id = new.agent_id if new else None
            if new_id != dino.target_id:
                dino.chase_ticks = 0
            dino.target_id = new_id

    def _emit(self, kind: EventKind, agent_id: str, target_id: str | None = None, **data) -> None:
        self.events.append(Event(self.tick, kind, agent_id, target_id, data))

    # ---------------------------------------------------------------- snapshot
    def to_snapshot(self) -> dict:
        return {
            "tick": self.tick,
            "seed": self.seed,
            "map": self.config.map.name,
            "is_night": self.is_night,
            "dinos": [
                d.to_dict(reproduction=self.config.reproduction is not None)
                for d in self.dinos.values()
            ],
            "plants": [p.to_dict() for p in self.plants],
            "waters": [w.to_dict() for w in self.waters],
            "rocks": [r.to_dict() for r in self.rocks],
        }

    def snapshot_hash(self) -> str:
        """Stable digest of the full world state, used for determinism checks."""
        payload = json.dumps(self.to_snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _id(d: Dino) -> str:
    return d.agent_id


def _is_rest(dino: Dino, action) -> bool:
    return (dino.species == Species.PREDATOR and action == PredatorAction.REST) or (
        dino.species == Species.HERBIVORE and action == HerbivoreAction.REST
    )


def _is_water(dino: Dino, action) -> bool:
    return (dino.species == Species.PREDATOR and action == PredatorAction.GO_TO_WATER) or (
        dino.species == Species.HERBIVORE and action == HerbivoreAction.GO_TO_WATER
    )
