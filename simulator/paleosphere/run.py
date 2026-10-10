"""Run one headless episode and print its summary.

    uv run python -m paleosphere.run --seed 42 --map map_a --predator rule --ticks 2000
    uv run python -m paleosphere.run --seed 42 --replay replays/seed42.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from paleosphere.config import load_world_config
from paleosphere.logging.episode import run_episode
from paleosphere.logging.replay import ReplayWriter
from paleosphere.policies import RuleBasedHerbivore
from paleosphere.policies.factory import make_predator_policy


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Run a PaleoSphere episode headless.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--map", default="map_a", help="map_a | map_b | path to yaml")
    parser.add_argument("--predator", default="rule", help="rule | random | ppo:<model.zip>")
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--replay", type=Path, help="write a jsonl replay to this path")
    parser.add_argument("--replay-every", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="print summary as JSON only")
    args = parser.parse_args(argv)

    config = load_world_config(args.map)
    predator = make_predator_policy(args.predator)
    started = time.perf_counter()
    if args.replay:
        meta = {"seed": args.seed, "map": config.map.name, "predator_policy": predator.name}
        with ReplayWriter(args.replay, args.replay_every, meta) as writer:
            summary = run_episode(
                config, args.seed, predator, RuleBasedHerbivore(), args.ticks, on_tick=writer
            )
    else:
        summary = run_episode(config, args.seed, predator, RuleBasedHerbivore(), args.ticks)
    elapsed = time.perf_counter() - started

    result = summary.to_dict()
    result["steps_per_sec"] = round(summary.ticks / elapsed, 1) if elapsed > 0 else None
    if args.json:
        print(json.dumps(result, indent=2))
        return result

    print(f"PaleoSphere episode  seed={summary.seed}  map={summary.map}  "
          f"predator={summary.predator_policy}")
    print(f"  ticks              {summary.ticks}  ({result['steps_per_sec']} steps/s)")
    status = "alive" if summary.predator_alive else f"dead ({summary.predator_death_cause})"
    print(f"  predator           {status}, survived {summary.predator_survival_ticks} ticks")
    print(f"  kills              {summary.kills}")
    print(f"  attacks            {summary.attack_attempts} "
          f"(hits {summary.attack_hits}, invalid {summary.invalid_attacks})")
    print(f"  hunt success rate  {summary.hunt_success_rate:.3f}")
    print(f"  energy per kill    {summary.energy_per_kill}")
    print(f"  give-ups           {summary.give_ups}")
    print(f"  herbivores alive   {summary.herbivores_alive}  deaths={summary.herbivore_deaths}")
    print(f"  predator actions   {summary.predator_action_counts}")
    print(f"  final hash         {summary.final_hash[:16]}")
    if args.replay:
        print(f"  replay             {args.replay}")
    return result


if __name__ == "__main__":
    main()
