"""Figures for the experiment report.

    uv run python analytics/reports/make_figures.py analytics/reports/exp002 \\
        --runs ppo_v0_s0 ppo_v0_s1 ppo_v0_s2 ppo_v1_s0 ppo_v1_s1 ppo_v1_s2
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from paleosphere.config import REPO_ROOT  # noqa: E402

ACTIONS = ["SEARCH", "APPROACH", "CHASE", "ATTACK", "GO_TO_WATER", "REST", "GIVE_UP"]
ACTION_COLORS = ["#9aa5ab", "#e0b25a", "#c4472f", "#7a2e8e", "#5aa0c8", "#4f9a53", "#3b3b3b"]
CAUSES = ["starvation", "dehydration", "exhaustion", "predation"]


def boxplots(df: pd.DataFrame, out: Path) -> None:
    metrics = [
        ("predator_survival_ticks", "포식자 생존 tick"),
        ("kills", "사냥 수"),
        ("hunt_success_rate", "사냥 성공률 (사냥/유효 공격)"),
        ("invalid_attack_rate", "무효 공격 비율"),
    ]
    for seed_set, g in df.groupby("seed_set", sort=False):
        policies = list(dict.fromkeys(g["policy"]))
        fig, axes = plt.subplots(1, len(metrics), figsize=(4.2 * len(metrics), 4.2))
        for ax, (col, title) in zip(axes, metrics, strict=True):
            data = [g.loc[g["policy"] == p, col].dropna().astype(float) for p in policies]
            ax.boxplot(data, tick_labels=policies, showmeans=True)
            ax.set_title(title)
            ax.tick_params(axis="x", rotation=40)
            ax.grid(axis="y", alpha=0.3)
        fig.suptitle(f"정책 비교 — {seed_set} ({len(g) // max(1, len(policies))} seed)")
        fig.tight_layout()
        fig.savefig(out / f"box_{_slug(seed_set)}.png", dpi=120)
        plt.close(fig)


def action_bars(df: pd.DataFrame, out: Path) -> None:
    g = df[df["seed_set"] == df["seed_set"].iloc[0]]
    means = g.groupby("policy", sort=False)[[f"act_{a.lower()}" for a in ACTIONS]].mean()
    fig, ax = plt.subplots(figsize=(9, 4.2))
    left = pd.Series(0.0, index=means.index)
    for a, color in zip(ACTIONS, ACTION_COLORS, strict=True):
        vals = means[f"act_{a.lower()}"]
        ax.barh(means.index, vals, left=left, color=color, label=a)
        left += vals
    ax.set_xlim(0, 1)
    ax.invert_yaxis()
    ax.set_xlabel("행동 비율")
    ax.legend(ncol=4, fontsize=8, loc="lower right")
    ax.set_title(f"포식자 행동 분포 — {g['seed_set'].iloc[0]}")
    fig.tight_layout()
    fig.savefig(out / "actions.png", dpi=120)
    plt.close(fig)


def death_causes(df: pd.DataFrame, out: Path) -> None:
    g = df[df["seed_set"] == df["seed_set"].iloc[0]]
    counts = (
        g.assign(cause=g["predator_death_cause"].fillna("alive"))
        .groupby(["policy", "cause"], sort=False)
        .size()
        .unstack(fill_value=0)
    )
    counts = counts.reindex(columns=[c for c in ["alive", *CAUSES] if c in counts.columns])
    ax = counts.plot.barh(stacked=True, figsize=(8, 4), colormap="tab10")
    ax.invert_yaxis()
    ax.set_xlabel("에피소드 수")
    ax.set_title("포식자 결말 (생존 / 사망 원인)")
    plt.tight_layout()
    plt.savefig(out / "predator_outcomes.png", dpi=120)
    plt.close()


def learning_curves(runs: list[str], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    for run in runs:
        path = REPO_ROOT / "training" / "checkpoints" / run / "eval_history.json"
        if not path.exists():
            continue
        hist = json.loads(path.read_text(encoding="utf-8"))
        ax.plot([h["timesteps"] for h in hist], [h["mean_kills"] for h in hist],
                marker="o", label=run, linestyle="--" if "_v0_" in run else "-")
    ax.set_xlabel("timesteps")
    ax.set_ylabel("평가 평균 사냥 수 (eval seed 5개)")
    ax.set_title("학습 곡선")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "learning_curves.png", dpi=120)
    plt.close(fig)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--runs", nargs="*", default=[])
    args = parser.parse_args()
    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    out = args.report_dir / "figures"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(args.report_dir / "episodes.csv")
    boxplots(df, out)
    action_bars(df, out)
    death_causes(df, out)
    learning_curves(args.runs, out)
    print(f"figures -> {out}")


if __name__ == "__main__":
    main()
