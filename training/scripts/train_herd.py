"""Train one PPO policy shared by every herbivore (multi-agent, parameter sharing).

    uv run python -m training.scripts.train_herd --seed 0
    uv run python -m training.scripts.train_herd --smoke     # ~2k agent-steps, for CI

Outputs (git-ignored): training/checkpoints/<run>/final_model.zip, best_model.zip,
metadata.json, eval_history.json; TensorBoard in training/runs/<run>/.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback

from training.environments.herd_env import HERD_ENV_VERSION, HerdParallelEnv
from training.environments.herd_vec_env import HerdVecEnv
from training.scripts.train_ppo import CHECKPOINT_DIR, RUNS_DIR, git_hash, load_training_config
from training.scripts.train_ppo import sha256 as file_sha256


def evaluate_herd(predict, env_kwargs: dict, seeds: list[int]) -> list[dict]:
    """Run whole episodes; `predict(obs_batch) -> actions` controls every herbivore."""
    env = HerdParallelEnv(**env_kwargs)
    summaries = []
    for seed in seeds:
        obs, _ = env.reset(options={"episode_seed": seed})
        infos = {}
        while env.agents:
            names = list(env.agents)
            actions = predict(np.stack([obs[a] for a in names]))
            obs, _, _, _, infos = env.step(dict(zip(names, map(int, actions), strict=True)))
        summaries.append(next(iter(infos.values()))["episode_summary"])
    return summaries


def model_predictor(model):
    return lambda batch: model.predict(batch, deterministic=True)[0]


def herd_score(summaries: list[dict]) -> dict[str, float]:
    return {
        "mean_survival_ticks": float(np.mean([s["mean_survival_ticks"] for s in summaries])),
        "mean_herbivores_alive": float(np.mean([s["herbivores_alive"] for s in summaries])),
    }


class HerdCallback(BaseCallback):
    """Logs finished herd episodes and evaluates on fixed seeds; keeps the best model."""

    def __init__(self, env_kwargs: dict, seeds: list[int], freq: int, out_dir: Path):
        super().__init__()
        self.env_kwargs, self.seeds, self.freq, self.out_dir = env_kwargs, seeds, freq, out_dir
        self.best = -np.inf
        self.history: list[dict] = []
        self._next = freq
        self._seen = 0

    def _on_step(self) -> bool:
        vec: HerdVecEnv = self.training_env
        for s in vec.episode_summaries[self._seen:]:
            self.logger.record_mean("episode/mean_survival_ticks", s["mean_survival_ticks"])
            self.logger.record_mean("episode/herbivores_alive", s["herbivores_alive"])
            for cause, n in s["death_causes"].items():
                self.logger.record_mean(f"deaths/{cause}", n)
        self._seen = len(vec.episode_summaries)
        if self.num_timesteps >= self._next:
            self._next += self.freq
            self.run_eval()
        return True

    def run_eval(self) -> None:
        m = herd_score(evaluate_herd(model_predictor(self.model), self.env_kwargs, self.seeds))
        record = {"timesteps": self.num_timesteps, **m}
        for k, v in m.items():
            self.logger.record(f"eval/{k}", v)
        if m["mean_survival_ticks"] > self.best:
            self.best = m["mean_survival_ticks"]
            self.model.save(self.out_dir / "best_model.zip")
            record["saved_best"] = True
        self.history.append(record)
        print(f"[eval] t={self.num_timesteps} {m}", flush=True)


def train(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Train a shared PPO herbivore policy.")
    parser.add_argument("--config", default="herd_v0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timesteps", type=int)
    parser.add_argument("--predator", help="override the fixed predator policy spec")
    parser.add_argument("--run-name")
    parser.add_argument("--smoke", action="store_true", help="~2k agent-steps, 1 world")
    args = parser.parse_args(argv)

    cfg = load_training_config(args.config)
    ppo_cfg = dict(cfg["ppo"])
    n_worlds = cfg["n_worlds"]
    total = args.timesteps or cfg["total_timesteps"]
    eval_seeds, eval_freq = cfg["eval"]["seeds"], cfg["eval"]["freq"]
    if args.smoke:
        n_worlds, total, eval_seeds = 1, 2048, eval_seeds[:1]
        ppo_cfg.update(n_steps=128, batch_size=256, n_epochs=1)
        eval_freq = total
    predator = args.predator or cfg["predator"]
    run_name = args.run_name or (
        f"{cfg['reward']}_s{args.seed}" + ("_smoke" if args.smoke else "")
    )
    out_dir = CHECKPOINT_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    env_kwargs = {
        "world_config": cfg["map"], "reward_config": cfg["reward"], "predator": predator,
        "max_steps": 300 if args.smoke else cfg["max_steps"],
    }

    torch.set_num_threads(1)
    vec = HerdVecEnv(n_worlds=n_worlds, seed=args.seed, **env_kwargs)
    net_arch = ppo_cfg.pop("net_arch")
    model = PPO(
        "MlpPolicy", vec, seed=args.seed, device="cpu", verbose=0,
        policy_kwargs={"net_arch": net_arch},
        tensorboard_log=None if args.smoke else str(RUNS_DIR), **ppo_cfg,
    )
    callback = HerdCallback(env_kwargs, eval_seeds, eval_freq, out_dir)
    started = time.perf_counter()
    model.learn(total_timesteps=total, callback=callback, tb_log_name=run_name)
    wall = time.perf_counter() - started
    if not callback.history or callback.history[-1]["timesteps"] != model.num_timesteps:
        callback.run_eval()
    final = out_dir / "final_model.zip"
    model.save(final)
    meta = {
        "run_name": run_name,
        "algo": "PPO (parameter sharing)",
        "env_version": HERD_ENV_VERSION,
        "map": cfg["map"],
        "reward_version": cfg["reward"],
        "predator": predator,
        "train_seed": args.seed,
        "n_worlds": n_worlds,
        "num_envs": vec.num_envs,
        "total_timesteps": int(model.num_timesteps),
        "hyperparameters": {**ppo_cfg, "net_arch": net_arch},
        "eval_seeds": eval_seeds,
        "git_commit": git_hash(),
        "wall_time_sec": round(wall, 1),
        "agent_steps_per_sec": round(model.num_timesteps / wall, 1),
        "final_model_sha256": file_sha256(final),
        "best_eval": max(callback.history, key=lambda r: r["mean_survival_ticks"]),
        "smoke": args.smoke,
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "eval_history.json").write_text(
        json.dumps(callback.history, indent=2), encoding="utf-8"
    )
    print(f"saved {final} ({meta['agent_steps_per_sec']} agent-steps/s)")
    return out_dir


if __name__ == "__main__":
    train()
