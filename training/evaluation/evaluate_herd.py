"""Evaluate herbivore policies against fixed predators on the fixed seed sets (Exp 005).

    uv run python -m training.evaluation.evaluate_herd \
        --herd rule random herd_s0=ppo:training/checkpoints/herd_v0_s0/best_model.zip \
        --predators rule ppo=onnx:models/ppo-v2.onnx \
        --sets eval_seen_map eval_unseen_map --out analytics/reports/exp005

Entries are `spec` or `label=spec`. Herd specs: rule | random | ppo:<zip>. Predator specs:
any `make_predator_policy` spec. Each episode runs `PaleoSphereHerd-v0` for up to 2,000 ticks
(the herd keeps living if the predator dies).
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from paleosphere.entities import DeathCause
from paleosphere.policies.factory import make_herbivore_policy
from training.environments.herd_env import HerdParallelEnv
from training.evaluation.evaluate import load_seed_sets

CAUSES = [c.value for c in DeathCause]
_CACHE: dict[tuple, object] = {}


def _label(entry: str) -> tuple[str, str]:
    label, _, spec = entry.partition("=") if "=" in entry else (entry, "", entry)
    return label, spec


def run_one(job: tuple) -> dict:
    herd_label, herd_spec, pred_label, pred_spec, set_name, map_name, seed, max_ticks = job
    key = ("env", pred_spec, map_name, max_ticks)
    if key not in _CACHE:
        _CACHE[key] = HerdParallelEnv(world_config=map_name, predator=pred_spec,
                                      max_steps=max_ticks)
    if ("herd", herd_spec) not in _CACHE:
        _CACHE[("herd", herd_spec)] = make_herbivore_policy(herd_spec)
    env, herd = _CACHE[key], _CACHE[("herd", herd_spec)]
    herd.reset(seed)
    env.reset(options={"episode_seed": seed})
    infos = {}
    while env.agents:
        _, _, _, _, infos = env.step({a: int(herd.act(env.world, a)) for a in env.agents})
    s = next(iter(infos.values()))["episode_summary"]
    row = {
        "herd": herd_label, "predator": pred_label, "seed_set": set_name, "seed": seed,
        "ticks": s["ticks"], "herbivores_alive": s["herbivores_alive"],
        "mean_survival_ticks": s["mean_survival_ticks"],
        "predator_alive": s["predator_alive"],
        "predator_survival_ticks": s["predator_survival_ticks"],
    }
    for c in CAUSES:
        row[f"deaths_{c}"] = s["death_causes"].get(c, 0)
    return row


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["mean_survival_ticks", "herbivores_alive", *(f"deaths_{c}" for c in CAUSES)]
    g = df.groupby(["herd", "predator", "seed_set"], sort=False)
    out = g[cols].agg(["mean", "std"])
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    out["predator_death_rate"] = 1.0 - g["predator_alive"].mean()
    out["episodes"] = g.size()
    return out.reset_index()


def to_markdown(summary: pd.DataFrame) -> str:
    lines = [
        "| herd | predator | set | 평균 생존 tick | 생존 수 (/8) | 포식 | 탈진 | 굶주림 | 탈수 "
        "| 포식자 사망률 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            f"| {r['herd']} | {r['predator']} | {r['seed_set']} "
            f"| {r['mean_survival_ticks_mean']:.0f} ± {r['mean_survival_ticks_std']:.0f} "
            f"| {r['herbivores_alive_mean']:.2f} | {r['deaths_predation_mean']:.2f} "
            f"| {r['deaths_exhaustion_mean']:.2f} | {r['deaths_starvation_mean']:.2f} "
            f"| {r['deaths_dehydration_mean']:.2f} | {r['predator_death_rate']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def evaluate(
    herds: list[str], predators: list[str], sets: list[str], out: Path | None = None,
    max_ticks: int = 2000, workers: int = 8, seeds_override: list[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    seed_sets = load_seed_sets()
    jobs = []
    for herd_entry in herds:
        for pred_entry in predators:
            for set_name in sets:
                for seed in seeds_override or seed_sets[set_name]["seeds"]:
                    jobs.append((*_label(herd_entry), *_label(pred_entry), set_name,
                                 seed_sets[set_name]["map"], seed, max_ticks))
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(run_one, jobs, chunksize=4))
    else:
        rows = [run_one(j) for j in jobs]
    df = pd.DataFrame(rows)
    summary = summarize(df)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        df.to_csv(out / "episodes.csv", index=False)
        summary.to_csv(out / "summary.csv", index=False)
        (out / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    return df, summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate herbivore policies (Exp 005).")
    parser.add_argument("--herd", nargs="+", default=["rule", "random"])
    parser.add_argument("--predators", nargs="+", default=["rule"])
    parser.add_argument("--sets", nargs="+", default=["eval_seen_map"])
    parser.add_argument("--seeds", nargs="+", type=int, help="override seeds of every set")
    parser.add_argument("--ticks", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    _, summary = evaluate(args.herd, args.predators, args.sets, args.out, args.ticks,
                          args.workers, args.seeds)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(to_markdown(summary))


if __name__ == "__main__":
    main()
