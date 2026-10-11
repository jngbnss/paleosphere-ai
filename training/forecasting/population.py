"""Population forecasting on ecosystem time series (Experiment 004).

    uv run python -m training.forecasting.population \
        --data analytics/reports/exp004/population.csv --out analytics/reports/exp004

Task: at sample t (one sample = 50 ticks) predict the herbivore and predator counts at t+h
from the last `WINDOW` samples. Horizons: 10 samples (500 ticks) and 40 (2,000 ticks).
Series are split by seed (train 0-29, test 30-39), so no world is seen in both sets.

Models, from simplest to most flexible:
- persistence: y(t+h) = y(t)
- linear:      ridge regression on window features -> change y(t+h) - y(t)
- gbm:         histogram gradient boosting on the same features and target

A series that ended (everyone dead) is padded with zeros: extinct stays extinct. Samples where
both species are already extinct at t are trivial and excluded from training and scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

WINDOW = 20
HORIZONS = (10, 40)
TARGETS = ("herbivores", "predators")
TRAIN_SEEDS = range(0, 30)
TEST_SEEDS = range(30, 40)
STATE_COLS = [
    "herbivores", "predators", "plant_food", "herbivore_mean_hunger",
    "herbivore_mean_thirst", "herbivore_mean_energy", "predator_mean_hunger",
]
FLOW_COLS = ["herbivore_births", "predator_births", "herbivore_deaths", "predator_deaths"]
LAGS = (1, 2, 5, 10, 20)
DAY_LENGTH = 400
DEFAULT_OUT = Path("analytics/reports/exp004")


def pad_series(df: pd.DataFrame) -> pd.DataFrame:
    """Give every seed the same tick grid; ticks after extinction are all zeros."""
    every = int(df.groupby("seed")["tick"].diff().mode().iloc[0])
    grid = np.arange(0, int(df["tick"].max()) + 1, every)
    out = []
    for seed, g in df.groupby("seed"):
        g = g[g["tick"] % every == 0].set_index("tick").reindex(grid)
        g = g.fillna(0.0)
        g["seed"] = seed
        out.append(g.reset_index(names="tick"))
    return pd.concat(out, ignore_index=True)


def make_features(g: pd.DataFrame) -> pd.DataFrame:
    """Window features for every sample of one seed (rows with a short history are NaN)."""
    f = pd.DataFrame(index=g.index)
    for col in STATE_COLS:
        f[col] = g[col]
    for col in ("herbivores", "predators", "plant_food"):
        for lag in LAGS:
            f[f"{col}_d{lag}"] = g[col] - g[col].shift(lag)
        f[f"{col}_mean{WINDOW}"] = g[col].rolling(WINDOW).mean()
        f[f"{col}_max{WINDOW}"] = g[col].rolling(WINDOW).max()
    for col in FLOW_COLS:
        f[f"{col}_sum10"] = g[col].rolling(10).sum()
    phase = 2 * np.pi * (g["tick"] % DAY_LENGTH) / DAY_LENGTH
    f["day_sin"], f["day_cos"] = np.sin(phase), np.cos(phase)
    f.iloc[:WINDOW] = np.nan
    return f


def build_dataset(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows = []
    for seed, g in pad_series(df).groupby("seed"):
        g = g.sort_values("tick").reset_index(drop=True)
        f = make_features(g)
        f["seed"], f["tick"] = seed, g["tick"]
        for t in TARGETS:
            f[f"y_{t}"] = g[t].shift(-horizon)
        alive = (g["herbivores"] + g["predators"]) > 0
        rows.append(f[alive].dropna())
    return pd.concat(rows, ignore_index=True)


def feature_columns(ds: pd.DataFrame) -> list[str]:
    return [c for c in ds.columns if c not in {"seed", "tick"} and not c.startswith("y_")]


def _models():
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return {
        "linear": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "gbm": lambda: HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0
        ),
    }


def evaluate(df: pd.DataFrame, horizons=HORIZONS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (metrics, test predictions)."""
    metrics, preds = [], []
    for h in horizons:
        ds = build_dataset(df, h)
        cols = feature_columns(ds)
        train = ds[ds["seed"].isin(TRAIN_SEEDS)]
        test = ds[ds["seed"].isin(TEST_SEEDS)]
        if train.empty or test.empty:
            raise ValueError("need series for both train seeds 0-29 and test seeds 30-39")
        pred_frame = test[["seed", "tick"]].copy()
        pred_frame["horizon"] = h
        for target in TARGETS:
            y_true = test[f"y_{target}"].to_numpy()
            current = test[target].to_numpy()
            results = {"persistence": current.astype(float)}
            for name, make in _models().items():
                model = make()
                model.fit(train[cols], train[f"y_{target}"] - train[target])
                results[name] = np.clip(current + model.predict(test[cols]), 0.0, None)
            pred_frame[f"{target}_true"] = y_true
            for name, y_pred in results.items():
                err = y_pred - y_true
                metrics.append({
                    "horizon_samples": h,
                    "horizon_ticks": h * int(df.groupby("seed")["tick"].diff().mode().iloc[0]),
                    "target": target,
                    "model": name,
                    "mae": round(float(np.mean(np.abs(err))), 4),
                    "rmse": round(float(np.sqrt(np.mean(err**2))), 4),
                    "n_train": len(train),
                    "n_test": len(test),
                })
                pred_frame[f"{target}_{name}"] = y_pred
        preds.append(pred_frame)
    return pd.DataFrame(metrics), pd.concat(preds, ignore_index=True)


def to_markdown(metrics: pd.DataFrame) -> str:
    lines = [
        "| horizon | target | persistence MAE / RMSE | linear MAE / RMSE | gbm MAE / RMSE |",
        "|---|---|---|---|---|",
    ]
    for (ticks, target), g in metrics.groupby(["horizon_ticks", "target"], sort=False):
        cells = []
        best = g["mae"].min()
        for name in ("persistence", "linear", "gbm"):
            r = g[g["model"] == name].iloc[0]
            cell = f"{r['mae']:.2f} / {r['rmse']:.2f}"
            cells.append(f"**{cell}**" if r["mae"] == best else cell)
        lines.append(f"| {ticks} tick | {target} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def figures(df: pd.DataFrame, preds: pd.DataFrame, metrics: pd.DataFrame, out: Path) -> None:
    import logging

    import matplotlib

    matplotlib.use("Agg")
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    import matplotlib.pyplot as plt

    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 1. population series of a few training seeds
    fig, axes = plt.subplots(2, 3, figsize=(14, 6), sharex=True)
    for ax, seed in zip(axes.flat, sorted(df["seed"].unique())[:6], strict=False):
        g = df[df["seed"] == seed]
        ax.plot(g["tick"], g["herbivores"], color="#4f9a53", label="초식")
        ax.plot(g["tick"], g["predators"] * 5, color="#c4472f", label="포식자 ×5")
        ax.set_title(f"seed {seed}")
    axes.flat[0].legend(fontsize=8)
    fig.suptitle("ecosystem 개체수 시계열 (규칙 기반 정책, 번식·노화)")
    fig.tight_layout()
    fig.savefig(fig_dir / "population_series.png", dpi=120)
    plt.close(fig)

    # 2. forecasts on two test seeds, longest horizon
    h = int(preds["horizon"].max())
    every = int(df.groupby("seed")["tick"].diff().mode().iloc[0])
    seeds = sorted(preds["seed"].unique())[:2]
    fig, axes = plt.subplots(2, len(seeds), figsize=(7 * len(seeds), 6), squeeze=False)
    for col, seed in enumerate(seeds):
        p = preds[(preds["seed"] == seed) & (preds["horizon"] == h)]
        target_tick = p["tick"] + h * every
        for row, target in enumerate(TARGETS):
            ax = axes[row][col]
            ax.plot(target_tick, p[f"{target}_true"], color="black", lw=2, label="실제")
            for name, color in (("persistence", "#9aa5ab"), ("linear", "#5aa0c8"),
                                ("gbm", "#e0b25a")):
                ax.plot(target_tick, p[f"{target}_{name}"], color=color, label=name)
            ax.set_title(f"test seed {seed} · {target} · {h * every} tick 뒤 예측")
    axes[0][0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(fig_dir / "forecast_examples.png", dpi=120)
    plt.close(fig)

    # 3. MAE by model
    fig, axes = plt.subplots(1, len(TARGETS), figsize=(11, 4))
    for ax, target in zip(axes, TARGETS, strict=True):
        m = metrics[metrics["target"] == target]
        pivot = m.pivot(index="horizon_ticks", columns="model", values="mae")
        pivot = pivot[["persistence", "linear", "gbm"]]
        pivot.plot.bar(ax=ax, color=["#9aa5ab", "#5aa0c8", "#e0b25a"], rot=0)
        ax.set_title(f"{target} MAE (test seed 30-39)")
        ax.set_xlabel("예측 거리 (tick)")
    fig.tight_layout()
    fig.savefig(fig_dir / "forecast_mae.png", dpi=120)
    plt.close(fig)


def main(argv: list[str] | None = None) -> pd.DataFrame:
    parser = argparse.ArgumentParser(description="Population forecasting (Experiment 004).")
    parser.add_argument("--data", type=Path, default=DEFAULT_OUT / "population.csv")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    df = pd.read_csv(args.data)
    metrics, preds = evaluate(df)
    args.out.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(args.out / "forecast_metrics.csv", index=False)
    md = to_markdown(metrics)
    (args.out / "forecast_summary.md").write_text(md + "\n", encoding="utf-8")
    if not args.no_figures:
        figures(df, preds, metrics, args.out)
    print(md)
    print(json.dumps({"n_train": int(metrics["n_train"].iloc[0]),
                      "n_test": int(metrics["n_test"].iloc[0])}))
    return metrics


if __name__ == "__main__":
    main()
