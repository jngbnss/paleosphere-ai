"""Long ecosystem runs with reproduction -> population time series (Phase 6).

    uv run python -m paleosphere.ecosystem --seeds 0-39 --ticks 20000 \
        --out analytics/reports/exp004/population.csv

Every `--every` ticks one row per seed is written: population per species, births and
deaths (by cause) since the previous row, total plant food and herd condition. The run stops
early when every individual is dead; its last row is the final (empty) state.
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from paleosphere.config import load_world_config
from paleosphere.core.events import EventKind
from paleosphere.core.world import World
from paleosphere.entities import DeathCause, Species
from paleosphere.policies import RuleBasedHerbivore
from paleosphere.policies.factory import make_predator_policy

DEATH_CAUSES = [c.value for c in DeathCause]
COLUMNS = [
    "seed", "tick", "herbivores", "predators", "plant_food", "is_night",
    "herbivore_births", "predator_births", "herbivore_deaths", "predator_deaths",
    *(f"herbivore_death_{c}" for c in DEATH_CAUSES),
    "herbivore_mean_hunger", "herbivore_mean_thirst", "herbivore_mean_energy",
    "predator_mean_hunger",
]


def parse_seeds(text: str) -> list[int]:
    """'0-9,42' -> [0, 1, ..., 9, 42]"""
    seeds: list[int] = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        seeds += list(range(int(lo), int(hi) + 1)) if hi else [int(lo)]
    return seeds


def _mean(values: list[float]) -> float:
    return round(float(np.mean(values)), 4) if values else 0.0


def _row(world: World, seed: int, counts: Counter) -> dict:
    herd = world.alive(Species.HERBIVORE)
    preds = world.alive(Species.PREDATOR)
    row = {
        "seed": seed,
        "tick": world.tick,
        "herbivores": len(herd),
        "predators": len(preds),
        "plant_food": round(sum(p.food for p in world.plants), 3),
        "is_night": int(world.is_night),
        "herbivore_births": counts["birth_herbivore"],
        "predator_births": counts["birth_predator"],
        "herbivore_deaths": counts["death_herbivore"],
        "predator_deaths": counts["death_predator"],
        "herbivore_mean_hunger": _mean([d.hunger for d in herd]),
        "herbivore_mean_thirst": _mean([d.thirst for d in herd]),
        "herbivore_mean_energy": _mean([d.energy for d in herd]),
        "predator_mean_hunger": _mean([d.hunger for d in preds]),
    }
    for c in DEATH_CAUSES:
        row[f"herbivore_death_{c}"] = counts[f"herbivore_death_{c}"]
    return row


def run_series(
    seed: int, config: str = "ecosystem", predator: str = "rule", ticks: int = 20000,
    every: int = 50,
) -> list[dict]:
    world = World(load_world_config(config), seed)
    if world.config.reproduction is None:
        raise ValueError(f"world config {config!r} has no reproduction section")
    pred_policy, herb_policy = make_predator_policy(predator), RuleBasedHerbivore()
    pred_policy.reset(seed)
    herb_policy.reset(seed)
    counts: Counter = Counter()
    rows = [_row(world, seed, counts)]
    while world.tick < ticks and not world.done:
        actions = {
            d.agent_id: int(
                (pred_policy if d.species == Species.PREDATOR else herb_policy).act(
                    world, d.agent_id
                )
            )
            for d in world.alive()
        }
        for e in world.step(actions):
            if e.kind == EventKind.BIRTH:
                counts[f"birth_{world.dinos[e.target_id].species.value}"] += 1
            elif e.kind == EventKind.DEATH:
                species = world.dinos[e.agent_id].species.value
                counts[f"death_{species}"] += 1
                counts[f"{species}_death_{e.data['cause']}"] += 1
        if world.tick % every == 0:
            rows.append(_row(world, seed, counts))
            counts.clear()
    if world.tick % every != 0:  # ended early (everyone dead): record the final state
        rows.append(_row(world, seed, counts))
    return rows


def _job(args: tuple) -> list[dict]:
    return run_series(*args)


def run_many(
    seeds: list[int], out: Path, config: str = "ecosystem", predator: str = "rule",
    ticks: int = 20000, every: int = 50, workers: int = 8,
) -> list[dict]:
    jobs = [(s, config, predator, ticks, every) for s in seeds]
    if workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_job, jobs))
    else:
        results = [_job(j) for j in jobs]
    rows = [r for series in results for r in series]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> list[dict]:
    parser = argparse.ArgumentParser(description="Long ecosystem runs -> population CSV.")
    parser.add_argument("--seeds", default="0-39")
    parser.add_argument("--config", default="ecosystem")
    parser.add_argument("--predator", default="rule", help="make_predator_policy spec")
    parser.add_argument("--ticks", type=int, default=20000)
    parser.add_argument("--every", type=int, default=50, help="sample interval in ticks")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=Path("analytics/reports/exp004/population.csv"))
    args = parser.parse_args(argv)
    started = time.perf_counter()
    seeds = parse_seeds(args.seeds)
    rows = run_many(
        seeds, args.out, args.config, args.predator, args.ticks, args.every, args.workers
    )
    last = {}
    for r in rows:
        last[r["seed"]] = r
    coexist = sum(r["herbivores"] > 0 and r["predators"] > 0 for r in last.values())
    herb_only = sum(r["herbivores"] > 0 and r["predators"] == 0 for r in last.values())
    print(f"{len(seeds)} seeds, {len(rows)} rows -> {args.out} "
          f"({time.perf_counter() - started:.0f}s)")
    print(f"  at end: coexist {coexist}, herbivores only {herb_only}, "
          f"extinct/predators only {len(seeds) - coexist - herb_only}")
    return rows


if __name__ == "__main__":
    main()
