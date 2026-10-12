"""Convert analytics/reports CSVs (Exp 001–004) into pages/data for the web demo.

    uv run python scripts/web-demo/build_data.py

Writes pages/data/results.json (what the "실험 결과" tab draws). The values are recorded
results copied from the CSVs; nothing here is re-simulated.
"""

from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "analytics" / "reports"
OUT = ROOT / "pages" / "data"

SUMMARY_KEYS = [
    "episodes", "survival_mean", "kills_mean", "kills_std", "hunt_success_mean",
    "energy_per_kill_mean", "invalid_attack_rate_mean", "give_ups_mean", "predator_death_rate",
    "act_search", "act_approach", "act_chase", "act_attack", "act_go_to_water", "act_rest",
    "act_give_up",
]


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(v: str):
    if v in ("", None):
        return None
    try:
        return round(float(v), 4)
    except ValueError:
        return v


def summary(path: Path) -> list[dict]:
    rows = []
    for r in read(path):
        row = {"policy": r["policy"], "set": r["seed_set"]}
        row |= {k: num(r.get(k, "")) for k in SUMMARY_KEYS}
        row["death_causes"] = json.loads(r["predator_death_causes"] or "{}")
        rows.append(row)
    return rows


def hacking(path: Path) -> list[dict]:
    rows = []
    for r in read(path):
        flags = {k.removeprefix("hack_"): float(v) for k, v in r.items() if k.startswith("hack_")}
        rows.append({"policy": r["policy"], "set": r["seed_set"], "flags": flags,
                     "suspected": r["suspected"]})
    return rows


def population() -> dict:
    rows = read(REPORTS / "exp004" / "population.csv")
    by_tick: dict[int, list[dict]] = defaultdict(list)
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_tick[int(r["tick"])].append(r)
        by_seed[int(r["seed"])].append(r)
    seeds = sorted(by_seed)

    # Seeds that ended early (everyone dead) contribute 0 for the remaining ticks.
    last = {s: by_seed[s][-1] for s in seeds}
    end_tick = max(by_tick)
    ticks = list(range(0, end_tick + 1, 200))
    series = {s: {int(r["tick"]): r for r in by_seed[s]} for s in seeds}

    def value(s, t, key):
        r = series[s].get(t)
        if r is None:
            return 0 if t > int(last[s]["tick"]) else None
        return int(r[key])

    agg = []
    for t in ticks:
        h = [v for s in seeds if (v := value(s, t, "herbivores")) is not None]
        p = [v for s in seeds if (v := value(s, t, "predators")) is not None]
        hq = statistics.quantiles(h, n=10) if len(h) > 1 else [h[0]] * 9
        agg.append({"t": t, "h": round(statistics.mean(h), 2), "h10": hq[0], "h90": hq[-1],
                    "p": round(statistics.mean(p), 2)})

    examples = {}
    for s in (0, 3, 12):
        examples[s] = [[int(r["tick"]), int(r["herbivores"]), int(r["predators"])]
                       for r in by_seed[s] if int(r["tick"]) % 100 == 0 or r is by_seed[s][-1]]

    outcome = {"coexist": 0, "herbivores_only": 0, "extinct": 0}
    for r in last.values():
        h, p = int(r["herbivores"]), int(r["predators"])
        outcome["coexist" if h and p else "herbivores_only" if h else "extinct"] += 1

    causes = defaultdict(int)
    for r in rows:
        for c in ("predation", "starvation", "dehydration", "exhaustion", "old_age"):
            causes[c] += int(r[f"herbivore_death_{c}"])
    return {"seeds": len(seeds), "rows": len(rows), "ticks": end_tick, "mean": agg,
            "examples": examples, "outcome": outcome, "herbivore_death_causes": dict(causes)}


def forecast() -> list[dict]:
    return [
        {"horizon": int(r["horizon_ticks"]), "target": r["target"], "model": r["model"],
         "mae": float(r["mae"]), "rmse": float(r["rmse"])}
        for r in read(REPORTS / "exp004" / "forecast_metrics.csv")
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "source": "analytics/reports (github.com/jngbnss/paleosphere-ai)",
        "exp001": {"summary": summary(REPORTS / "exp001" / "summary.csv"),
                   "hacking": hacking(REPORTS / "exp001" / "hacking.csv")},
    }
    for exp in ("exp002", "exp003"):
        data[exp] = {}
        for variant in ("base", "res0.6", "res1.4"):
            d = REPORTS / exp / variant
            data[exp][variant] = {"summary": summary(d / "summary.csv"),
                                  "hacking": hacking(d / "hacking.csv")}
    data["exp004"] = {"population": population(), "forecast": forecast()}
    (OUT / "results.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    print("wrote", OUT / "results.json", (OUT / "results.json").stat().st_size, "bytes")


if __name__ == "__main__":
    main()
