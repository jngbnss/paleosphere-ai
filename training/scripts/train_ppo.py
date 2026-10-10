"""Train the predator with PPO.

    uv run python -m training.scripts.train_ppo --seed 0
    uv run python -m training.scripts.train_ppo --seed 0 --reward v1 --run-name ppo_v1_s0
    uv run python -m training.scripts.train_ppo --smoke        # ~2k steps, for CI

Outputs (git-ignored):
    training/checkpoints/<run>/final_model.zip, best_model.zip, metadata.json, eval_history.json
    training/runs/<run>/   (TensorBoard)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from paleosphere.config import CONFIG_DIR, REPO_ROOT
from training.environments import ENV_VERSION, PredatorEnv
from training.scripts.bc_pretrain import behavior_clone, collect_demonstrations

CHECKPOINT_DIR = REPO_ROOT / "training" / "checkpoints"
RUNS_DIR = REPO_ROOT / "training" / "runs"


def load_training_config(name_or_path: str) -> dict:
    path = Path(name_or_path)
    if path.suffix not in {".yaml", ".yml"}:
        path = CONFIG_DIR / "training" / f"{name_or_path}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def evaluate_model(model, env_kwargs: dict, seeds: list[int]) -> dict[str, float]:
    """Deterministic rollouts on fixed evaluation seeds (never used for training)."""
    env = PredatorEnv(**env_kwargs)
    kills, survival, rewards, invalid = [], [], [], []
    for seed in seeds:
        obs, _ = env.reset(options={"episode_seed": seed})
        total, done, info = 0.0, False, {}
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(int(action))
            total += reward
            done = terminated or truncated
        s = info["episode_summary"]
        kills.append(s["kills"])
        survival.append(s["predator_survival_ticks"])
        invalid.append(s["invalid_attacks"])
        rewards.append(total)
    return {
        "mean_kills": float(np.mean(kills)),
        "mean_survival": float(np.mean(survival)),
        "mean_reward": float(np.mean(rewards)),
        "mean_invalid_attacks": float(np.mean(invalid)),
    }


def selection_score(m: dict[str, float], max_steps: int) -> float:
    """Model selection uses hunting and survival, not total reward (see model-selection.md)."""
    return m["mean_kills"] + 0.5 * m["mean_survival"] / max_steps


class EpisodeStatsCallback(BaseCallback):
    """Logs simulator metrics from finished training episodes to TensorBoard."""

    def _on_step(self) -> bool:
        for info in self.locals.get("infos", []):
            s = info.get("episode_summary")
            if s is None:
                continue
            self.logger.record_mean("episode/kills", s["kills"])
            self.logger.record_mean("episode/survival_ticks", s["predator_survival_ticks"])
            self.logger.record_mean("episode/invalid_attacks", s["invalid_attacks"])
            self.logger.record_mean("episode/give_ups", s["give_ups"])
            for k, v in info["episode_reward_components"].items():
                self.logger.record_mean(f"reward/{k}", v)
        return True


class FixedSeedEvalCallback(BaseCallback):
    def __init__(self, env_kwargs: dict, seeds: list[int], freq: int, out_dir: Path):
        super().__init__()
        self.env_kwargs = env_kwargs
        self.seeds = seeds
        self.freq = freq
        self.out_dir = out_dir
        self.best = -np.inf
        self.history: list[dict[str, Any]] = []
        self._next = freq

    def _on_step(self) -> bool:
        if self.num_timesteps >= self._next:
            self._next += self.freq
            self.run_eval()
        return True

    def run_eval(self) -> None:
        m = evaluate_model(self.model, self.env_kwargs, self.seeds)
        score = selection_score(m, self.env_kwargs["max_steps"])
        record = {"timesteps": self.num_timesteps, "score": score, **m}
        self.history.append(record)
        for k, v in m.items():
            self.logger.record(f"eval/{k}", v)
        self.logger.record("eval/selection_score", score)
        if score > self.best:
            self.best = score
            self.model.save(self.out_dir / "best_model.zip")
            record["saved_best"] = True
        print(f"[eval] t={self.num_timesteps} score={score:.3f} {m}", flush=True)


def git_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def train(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="Train PPO predator.")
    parser.add_argument("--config", default="ppo_v0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--reward", help="override reward config version")
    parser.add_argument("--timesteps", type=int, help="override total_timesteps")
    parser.add_argument("--n-envs", type=int, help="override n_envs")
    parser.add_argument("--run-name")
    parser.add_argument("--smoke", action="store_true", help="2,048 steps, 1 env, tiny eval")
    args = parser.parse_args(argv)
    # A 64x64 MLP gains nothing from intra-op threads; 12 threads made training ~8x slower.
    torch.set_num_threads(1)

    cfg = load_training_config(args.config)
    reward = args.reward or cfg["reward"]
    total = args.timesteps or cfg["total_timesteps"]
    n_envs = args.n_envs or cfg["n_envs"]
    eval_seeds = cfg["eval"]["seeds"]
    eval_freq = cfg["eval"]["freq"]
    ppo_kwargs = dict(cfg["ppo"])
    net_arch = ppo_kwargs.pop("net_arch")
    if args.smoke:
        total, n_envs, eval_seeds, eval_freq = 2048, 1, eval_seeds[:1], 2048
        ppo_kwargs.update(n_steps=256, batch_size=64, n_epochs=2)

    run_name = args.run_name or f"ppo_{reward}_s{args.seed}" + ("_smoke" if args.smoke else "")
    out_dir = CHECKPOINT_DIR / run_name
    out_dir.mkdir(parents=True, exist_ok=True)

    env_kwargs = {
        "world_config": cfg["map"],
        "reward_config": reward,
        "max_steps": cfg["max_steps"],
    }
    train_env_kwargs = {
        **env_kwargs,
        "spawn_near_prey_prob": cfg.get("curriculum", {}).get("spawn_near_prey_prob", 0.0),
    }
    vec_cls = DummyVecEnv if n_envs == 1 else SubprocVecEnv
    vec_env = make_vec_env(
        PredatorEnv, n_envs=n_envs, seed=args.seed, env_kwargs=train_env_kwargs,
        vec_env_cls=vec_cls,
    )
    model = PPO(
        "MlpPolicy",
        vec_env,
        seed=args.seed,
        policy_kwargs={"net_arch": net_arch},
        tensorboard_log=None if args.smoke else str(RUNS_DIR),
        verbose=0,
        **ppo_kwargs,
    )
    bc_cfg = cfg.get("bc")
    bc_stats = None
    if bc_cfg:
        episodes = 2 if args.smoke else bc_cfg["episodes"]
        obs, acts, rets = collect_demonstrations(
            bc_cfg["teacher"], train_env_kwargs, episodes, args.seed, ppo_kwargs["gamma"]
        )
        bc_stats = behavior_clone(
            model, obs, acts, rets, epochs=bc_cfg.get("epochs", 10), seed=args.seed
        )
        print(f"[bc] teacher={bc_cfg['teacher']} {bc_stats}", flush=True)
    eval_cb = FixedSeedEvalCallback(
        {**env_kwargs}, eval_seeds, eval_freq, out_dir
    )
    started = time.perf_counter()
    model.learn(
        total_timesteps=total,
        callback=CallbackList([EpisodeStatsCallback(), eval_cb]),
        tb_log_name=run_name,
        progress_bar=False,
    )
    elapsed = time.perf_counter() - started
    vec_env.close()

    final_path = out_dir / "final_model.zip"
    model.save(final_path)
    if not eval_cb.history or eval_cb.history[-1]["timesteps"] != model.num_timesteps:
        eval_cb.run_eval()

    metadata = {
        "run_name": run_name,
        "algo": "PPO",
        "env_version": ENV_VERSION,
        "map": cfg["map"],
        "reward_version": reward,
        "reward_config": yaml.safe_load(
            (CONFIG_DIR / "rewards" / f"{reward}.yaml").read_text(encoding="utf-8")
        ),
        "train_seed": args.seed,
        "eval_seeds": eval_seeds,
        "total_timesteps": int(model.num_timesteps),
        "n_envs": n_envs,
        "curriculum": cfg.get("curriculum", {}),
        "behavior_cloning": {**bc_cfg, **bc_stats} if bc_cfg else None,
        "hyperparameters": {**ppo_kwargs, "net_arch": net_arch},
        "git_commit": git_hash(),
        "wall_time_sec": round(elapsed, 1),
        "env_steps_per_sec": round(model.num_timesteps / elapsed, 1),
        "final_model_sha256": sha256(final_path),
        "best_model_sha256": sha256(out_dir / "best_model.zip")
        if (out_dir / "best_model.zip").exists()
        else None,
        "best_eval": max(eval_cb.history, key=lambda r: r["score"]),
        "smoke": args.smoke,
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (out_dir / "eval_history.json").write_text(
        json.dumps(eval_cb.history, indent=2), encoding="utf-8"
    )
    print(f"done: {run_name} {model.num_timesteps} steps in {elapsed:.0f}s -> {out_dir}")
    return out_dir


if __name__ == "__main__":
    train()
