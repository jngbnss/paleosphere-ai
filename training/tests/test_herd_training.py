import json

import numpy as np

from training.environments.herd_vec_env import HerdVecEnv
from training.scripts.train_herd import train


def test_vec_env_slots_follow_agents_until_world_reset():
    vec = HerdVecEnv(n_worlds=2, seed=0, max_steps=60)
    obs = vec.reset()
    assert obs.shape == (16, 30)
    rng = np.random.default_rng(0)
    ended = np.zeros(16, dtype=bool)
    for _ in range(60):
        obs, rewards, dones, infos = vec.step(rng.integers(5, size=16))
        assert np.isfinite(rewards).all()
        for i in np.flatnonzero(dones):
            assert "terminal_observation" in infos[i]
        ended |= dones
    assert ended.all()  # every slot ended at the 60-tick truncation
    assert any(info.get("TimeLimit.truncated") for info in infos)
    assert len(vec.episode_summaries) == 2
    assert (obs != 0).any(axis=1).all()  # worlds were reset: fresh observations


def test_smoke_herd_training():
    out = train(["--smoke", "--run-name", "pytest_herd_smoke"])
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["env_version"] == "PaleoSphereHerd-v0"
    assert meta["total_timesteps"] >= 2048
    assert (out / "final_model.zip").exists()
