"""Explorer mode: a field researcher walking through the world (Phase 8).

The explorer is an observer, not an entity of the simulation: dinosaurs do not see it and
it never touches world state, so a run with an explorer has the same snapshot hashes as one
without. It can only learn what it perceives:

- `scan()` identifies every dinosaur within `scan_radius` and records it in the journal;
- every tick, events (hunts, deaths, births) within `view_radius` are noted as witnessed;
- the walked area is tracked on a coarse grid.

`report()` turns the journal into a field report, including a population *estimate* from
sightings next to the true count, so the gap between what was observed and the truth is
visible.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from paleosphere.core.events import Event, EventKind
from paleosphere.entities import Species
from paleosphere.explain import status_code, status_label

if TYPE_CHECKING:
    from paleosphere.core.world import World

SCAN_RADIUS = 12.0
VIEW_RADIUS = 16.0
GRID = 8  # explored-area grid (GRID x GRID cells)
RECENT_TICKS = 400  # sightings this recent count toward the population estimate
WITNESSED = {
    EventKind.KILL: "사냥",
    EventKind.DEATH: "죽음",
    EventKind.BIRTH: "출생",
    EventKind.ATTACK_MISS: "사냥 실패",
}
SPECIES_KO = {"herbivore": "초식공룡", "predator": "육식공룡"}


@dataclass(slots=True)
class Record:
    agent_id: str
    species: str
    first_seen: int
    last_seen: int
    sightings: int = 0
    statuses: Counter = field(default_factory=Counter)
    actions: Counter = field(default_factory=Counter)
    alive_when_last_seen: bool = True
    generation: int | None = None


class FieldJournal:
    def __init__(self, world: World, scan_radius: float = SCAN_RADIUS,
                 view_radius: float = VIEW_RADIUS):
        self.size = world.size
        self.scan_radius = scan_radius
        self.view_radius = view_radius
        self.position = np.array([world.size / 2, world.size / 2])
        self.start_tick = world.tick
        self.records: dict[str, Record] = {}
        self.witnessed: list[dict] = []
        self.scans = 0
        self.distance_walked = 0.0
        self.explored = np.zeros((GRID, GRID), dtype=bool)
        self._mark_explored()

    # ------------------------------------------------------------------ movement
    def move_to(self, x: float, z: float) -> None:
        target = np.clip(np.array([x, z], dtype=float), 0.0, self.size)
        self.distance_walked += float(np.linalg.norm(target - self.position))
        self.position = target
        self._mark_explored()

    def _mark_explored(self) -> None:
        cell = self.size / GRID
        for i in range(GRID):
            for j in range(GRID):
                center = np.array([(i + 0.5) * cell, (j + 0.5) * cell])
                if np.linalg.norm(center - self.position) <= self.view_radius:
                    self.explored[i, j] = True

    @property
    def explored_fraction(self) -> float:
        return float(self.explored.mean())

    def _dist(self, pos: np.ndarray) -> float:
        return float(np.linalg.norm(np.asarray(pos) - self.position))

    # ------------------------------------------------------------------ observing
    def scan(self, world: World) -> list[dict]:
        """Identify dinosaurs within scan_radius. Returns sightings, nearest first."""
        self.scans += 1
        out = []
        for d in world.dinos.values():
            dist = self._dist(d.pos)
            if dist > self.scan_radius:
                continue
            code = status_code(world, d.agent_id)
            new = d.agent_id not in self.records
            rec = self.records.setdefault(
                d.agent_id, Record(d.agent_id, d.species.value, world.tick, world.tick)
            )
            rec.last_seen = world.tick
            rec.sightings += 1
            rec.statuses[code] += 1
            rec.actions[d.current_action] += 1
            rec.alive_when_last_seen = d.alive
            rec.generation = d.generation if world.config.reproduction is not None else None
            out.append({
                "agent_id": d.agent_id,
                "species": d.species.value,
                "position": (round(float(d.pos[0]), 3), round(float(d.pos[1]), 3)),
                "distance": round(dist, 3),
                "alive": d.alive,
                "status_label": status_label(code),
                "current_action": d.current_action,
                "health": round(d.health, 2),
                "energy": round(d.energy, 2),
                "hunger": round(d.hunger, 2),
                "thirst": round(d.thirst, 2),
                "new": new,
            })
        out.sort(key=lambda s: (s["distance"], s["agent_id"]))
        return out

    def witness(self, world: World, events: list[Event]) -> list[dict]:
        """Note notable events of the last tick that happened within view_radius."""
        noted = []
        for e in events:
            label = WITNESSED.get(e.kind)
            dino = world.dinos.get(e.agent_id)
            if label is None or dino is None:
                continue
            subject = world.dinos.get(e.target_id) if e.kind == EventKind.BIRTH else dino
            pos = subject.pos if subject is not None else dino.pos
            if self._dist(pos) > self.view_radius:
                continue
            entry = {"tick": e.tick, "kind": str(e.kind), "label": label,
                     "agent_id": e.agent_id, "target_id": e.target_id}
            if e.kind == EventKind.DEATH:
                entry["cause"] = e.data.get("cause")
            self.witnessed.append(entry)
            noted.append(entry)
        return noted

    # ------------------------------------------------------------------ reporting
    def population_estimate(self, world: World) -> dict[str, int]:
        recent = world.tick - RECENT_TICKS
        est = Counter(
            r.species for r in self.records.values()
            if r.alive_when_last_seen and r.last_seen >= recent
        )
        return {s.value: est[s.value] for s in Species}

    def stats(self, world: World) -> dict:
        identified = Counter(r.species for r in self.records.values())
        return {
            "tick": world.tick,
            "duration_ticks": world.tick - self.start_tick,
            "scans": self.scans,
            "distance_walked": round(self.distance_walked, 2),
            "explored_fraction": round(self.explored_fraction, 3),
            "identified": {s.value: identified[s.value] for s in Species},
            "estimated_alive": self.population_estimate(world),
            "actual_alive": {s.value: len(world.alive(s)) for s in Species},
            "witnessed": dict(Counter(w["kind"] for w in self.witnessed)),
        }

    def report(self, world: World) -> str:
        st = self.stats(world)
        lines = [
            f"# 현장 보고서 — {world.config.map.name}, seed {world.seed}",
            "",
            f"- 관찰 기간: tick {self.start_tick}–{world.tick} ({st['duration_ticks']} tick)",
            f"- 스캔 {st['scans']}회 · 이동 {st['distance_walked']:.0f}m · "
            f"탐사 면적 {st['explored_fraction'] * 100:.0f}%",
            "",
            "## 개체수",
            "",
            "| 종 | 식별한 개체 | 추정 생존 (최근 관찰) | 실제 생존 |",
            "|---|---|---|---|",
        ]
        for s in Species:
            lines.append(
                f"| {SPECIES_KO[s.value]} | {st['identified'][s.value]} | "
                f"{st['estimated_alive'][s.value]} | {st['actual_alive'][s.value]} |"
            )
        lines += ["", f"추정은 최근 {RECENT_TICKS} tick 안에 살아 있는 채로 스캔한 개체 수다. "
                  "보지 못한 개체는 세지 않으므로 실제보다 작게 나온다.", ""]

        lines += ["## 관찰한 행동", ""]
        for s in Species:
            acts = Counter()
            for r in self.records.values():
                if r.species == s.value:
                    acts.update(r.statuses)
            total = sum(acts.values())
            if not total:
                lines.append(f"- {SPECIES_KO[s.value]}: 관찰 없음")
                continue
            top = ", ".join(
                f"{status_label(code)} {n / total * 100:.0f}%" for code, n in acts.most_common(4)
            )
            lines.append(f"- {SPECIES_KO[s.value]} ({total}회 관찰): {top}")

        lines += ["", "## 목격한 사건", ""]
        if not self.witnessed:
            lines.append("- 없음")
        for w in self.witnessed[-15:]:
            detail = f" ({w['cause']})" if w.get("cause") else ""
            target = f" → {w['target_id']}" if w.get("target_id") else ""
            lines.append(f"- tick {w['tick']}: {w['label']}{detail} — {w['agent_id']}{target}")
        if len(self.witnessed) > 15:
            lines.append(f"- … 외 {len(self.witnessed) - 15}건")

        lines += ["", "## 개체 기록 (최근 관찰 순)", "",
                  "| 개체 | 종 | 처음 / 마지막 관찰 | 관찰 수 | 주된 상태 |",
                  "|---|---|---|---|---|"]
        for r in sorted(self.records.values(), key=lambda r: -r.last_seen)[:20]:
            main = status_label(r.statuses.most_common(1)[0][0]) if r.statuses else "-"
            dead = "" if r.alive_when_last_seen else " (사망)"
            gen = f" · {r.generation}세대" if r.generation else ""
            lines.append(
                f"| {r.agent_id}{dead} | {SPECIES_KO[r.species]}{gen} | "
                f"{r.first_seen} / {r.last_seen} | {r.sightings} | {main} |"
            )
        return "\n".join(lines) + "\n"

