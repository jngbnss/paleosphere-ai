"""Evaluate predator policies on fixed seed sets and write per-episode CSV + summary.

    uv run python -m training.evaluation.evaluate --policies rule random \\
        ppo_v0_s0=ppo:training/checkpoints/ppo_v0_s0/best_model.zip \\
        --sets eval_seen_map eval_unseen_map --out analytics/reports/exp001

Each policy entry is `spec` or `label=spec`; spec is rule | random | ppo:<path>.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from paleosphere.config import REPO_ROOT, load_world_config
from paleosphere.logging.episode import run_episode
from paleosphere.policies import RuleBasedHerbivore
from paleosphere.policies.factory import make_predator_policy
from training.evaluation.hacking_detectors import add_flags, policy_report, report_markdown

SEED_SETS_PATH = REPO_ROOT / "evals" / "fixed-seeds.yaml"
PREDATOR_ACTIONS = ["SEARCH", "APPROACH", "CHASE", "ATTACK", "GO_TO_WATER", "REST", "GIVE_UP"]

_POLICY_CACHE: dict[str, object] = {}


def load_seed_sets() -> dict:
    return yaml.safe_load(SEED_SETS_PATH.read_text(encoding="utf-8"))


def _policy(spec: str):
    if spec not in _POLICY_CACHE:
        _POLICY_CACHE[spec] = make_predator_policy(spec)
    return _POLICY_CACHE[spec]


def run_one(job: tuple[str, str, str, str, int, int, dict]) -> dict:
    label, spec, set_name, map_name, seed, max_ticks, overrides = job
    config = load_world_config(map_name, **overrides)
    summary = run_episode(config, seed, _policy(spec), RuleBasedHerbivore(), max_ticks)
    row = summary.to_dict()
    actions = row.pop("predator_action_counts")
    deaths = row.pop("herbivore_deaths")
    total_actions = max(1, sum(actions.values()))
    for a in PREDATOR_ACTIONS:
        row[f"act_{a.lower()}"] = actions.get(a, 0) / total_actions
    row["herbivore_deaths"] = json.dumps(deaths)
    row["invalid_attack_rate"] = (
        row["invalid_attacks"] / row["attack_attempts"] if row["attack_attempts"] else 0.0
    )
    row.update(policy=label, spec=spec, seed_set=set_name)
    return row


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "predator_survival_ticks": "survival",
        "kills": "kills",
        "hunt_success_rate": "hunt_success",
        "energy_per_kill": "energy_per_kill",
        "invalid_attack_rate": "invalid_attack_rate",
        "give_ups": "give_ups",
    }
    rows = []
    for (policy, seed_set), g in df.groupby(["policy", "seed_set"], sort=False):
        row = {"policy": policy, "seed_set": seed_set, "episodes": len(g)}
        for col, name in metrics.items():
            vals = g[col].dropna().astype(float)
            row[f"{name}_mean"] = vals.mean() if len(vals) else np.nan
            row[f"{name}_std"] = vals.std(ddof=0) if len(vals) else np.nan
        row["predator_death_rate"] = 1.0 - g["predator_alive"].mean()
        causes = g["predator_death_cause"].dropna().value_counts().to_dict()
        row["predator_death_causes"] = json.dumps(causes)
        for a in PREDATOR_ACTIONS:
            row[f"act_{a.lower()}"] = g[f"act_{a.lower()}"].mean()
        rows.append(row)
    return pd.DataFrame(rows)


def _mean_std(row, name: str, fmt: str = "{:.2f}") -> str:
    m, s = getattr(row, f"{name}_mean"), getattr(row, f"{name}_std")
    return "–" if pd.isna(m) else f"{fmt.format(m)} ± {fmt.format(s)}"


def to_markdown(summary: pd.DataFrame) -> str:
    lines = [
        "| policy | set | n | survival | kills | hunt success | energy/kill | invalid atk | "
        "give-ups | death rate |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary.itertuples():
        def ms(name, fmt="{:.2f}", r=r):
            return _mean_std(r, name, fmt)

        lines.append(
            f"| {r.policy} | {r.seed_set} | {r.episodes} | {ms('survival', '{:.0f}')} | "
            f"{ms('kills')} | {ms('hunt_success')} | {ms('energy_per_kill', '{:.0f}')} | "
            f"{ms('invalid_attack_rate')} | {ms('give_ups', '{:.1f}')} | "
            f"{r.predator_death_rate:.2f} |"
        )
    lines += ["", "행동 분포 (비율)", "",
              "| policy | set | " + " | ".join(PREDATOR_ACTIONS) + " |",
              "|---|---|" + "---|" * len(PREDATOR_ACTIONS)]
    for r in summary.itertuples():
        acts = " | ".join(f"{getattr(r, f'act_{a.lower()}'):.2f}" for a in PREDATOR_ACTIONS)
        lines.append(f"| {r.policy} | {r.seed_set} | {acts} |")
    return "\n".join(lines) + "\n"


def evaluate(
    policies: list[str],
    sets: list[str],
    out: Path | None = None,
    max_ticks: int = 2000,
    workers: int = 8,
    seeds_override: list[int] | None = None,
    world_overrides: dict | None = None,
    set_suffix: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seed_sets = load_seed_sets()
    jobs = []
    for entry in policies:
        label, _, spec = entry.partition("=") if "=" in entry else (entry, "", entry)
        for set_name in sets:
            seeds = seeds_override or seed_sets[set_name]["seeds"]
            map_name = seed_sets[set_name]["map"]
            for seed in seeds:
                jobs.append(
                    (label, spec, set_name + set_suffix, map_name, seed, max_ticks,
                     world_overrides or {})
                )
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(run_one, jobs, chunksize=4))
    else:
        rows = [run_one(j) for j in jobs]
    df = add_flags(pd.DataFrame(rows))
    summary = summarize(df)
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "episodes.csv", index=False)
        summary.to_csv(out / "summary.csv", index=False)
        hacks = policy_report(df)
        hacks.to_csv(out / "hacking.csv", index=False)
        (out / "summary.md").write_text(
            to_markdown(summary)
            + "\nReward hacking 탐지 (플래그 에피소드 비율)\n\n"
            + report_markdown(hacks),
            encoding="utf-8",
        )
    return df, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate predator policies on fixed seeds.")
    parser.add_argument("--policies", nargs="+", default=["rule", "random"])
    parser.add_argument("--sets", nargs="+", default=["eval_seen_map"])
    parser.add_argument("--seeds", nargs="+", type=int, help="override seeds of every set")
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--resource-scale", type=float,
        help="scale plant count & regrowth (e.g. 0.6 or 1.4) for robustness tests",
    )
    args = parser.parse_args(argv)

    overrides, suffix = None, ""
    if args.resource_scale:
        base = load_world_config("map_a").map.plants
        overrides = {"map": {"plants": {
            "count": max(1, round(base.count * args.resource_scale)),
            "regrow_per_tick": base.regrow_per_tick * args.resource_scale,
        }}}
        suffix = f"@res{args.resource_scale:g}"
    _, summary = evaluate(
        args.policies, args.sets, args.out, args.ticks, args.workers, args.seeds,
        overrides, suffix,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp949
    print(to_markdown(summary))


if __name__ == "__main__":
    main()
