"""Behavior-cloning warm start for the PPO predator.

PPO from scratch never lands a single hit (see docs/reward-design.md): episodes are ~1,700
ticks long and a kill needs ~40 consecutive pursuit actions, which random exploration does
not produce. We therefore initialise the PPO actor by imitating a teacher (the rule-based
baseline) on *training* seeds, fit the critic to the teacher's discounted returns under the
same reward, and let PPO improve from there. The teacher never sees evaluation seeds.
"""

from __future__ import annotations

import numpy as np
import torch

from paleosphere.policies.factory import make_predator_policy
from training.environments import PredatorEnv


def collect_demonstrations(
    teacher_spec: str, env_kwargs: dict, episodes: int, seed: int, gamma: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    teacher = make_predator_policy(teacher_spec)
    env = PredatorEnv(**env_kwargs)
    env.reset(seed=seed)  # seeds the env RNG; episode seeds come from the training range
    obs_buf, act_buf, ret_buf = [], [], []
    for _ in range(episodes):
        obs, _ = env.reset()
        rewards, done = [], False
        while not done:
            action = int(teacher.act(env.world, env.predator_id))
            obs_buf.append(obs)
            act_buf.append(action)
            obs, reward, terminated, truncated, _ = env.step(action)
            rewards.append(reward)
            done = terminated or truncated
        ret, returns = 0.0, []
        for r in reversed(rewards):
            ret = r + gamma * ret
            returns.append(ret)
        ret_buf.extend(reversed(returns))
    return (
        np.asarray(obs_buf, dtype=np.float32),
        np.asarray(act_buf, dtype=np.int64),
        np.asarray(ret_buf, dtype=np.float32),
    )


def behavior_clone(
    model, obs: np.ndarray, actions: np.ndarray, returns: np.ndarray,
    epochs: int = 10, batch_size: int = 1024, lr: float = 1e-3, seed: int = 0,
) -> dict[str, float]:
    policy = model.policy
    policy.set_training_mode(True)
    optimizer = torch.optim.Adam(policy.parameters(), lr=lr)
    gen = torch.Generator().manual_seed(seed)
    obs_t = torch.as_tensor(obs)
    act_t = torch.as_tensor(actions)
    ret_t = torch.as_tensor(returns)
    n = len(obs_t)
    for _ in range(epochs):
        perm = torch.randperm(n, generator=gen)
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            values, log_prob, _ = policy.evaluate_actions(obs_t[idx], act_t[idx])
            actor_loss = -log_prob.mean()
            critic_loss = torch.nn.functional.mse_loss(values.flatten(), ret_t[idx])
            loss = actor_loss + 0.5 * critic_loss
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
            optimizer.step()
    policy.set_training_mode(False)
    with torch.no_grad():
        dist = policy.get_distribution(obs_t)
        pred = dist.distribution.probs.argmax(dim=1)
        accuracy = float((pred == act_t).float().mean())
    return {
        "samples": int(n),
        "imitation_accuracy": accuracy,
        "final_actor_loss": float(actor_loss),
    }
