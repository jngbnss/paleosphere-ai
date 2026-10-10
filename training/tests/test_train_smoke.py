import json

from training.scripts.train_ppo import train


def test_smoke_training_writes_artifacts():
    out = train(["--smoke", "--run-name", "pytest_smoke"])
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["total_timesteps"] >= 2048
    assert meta["env_version"] == "PaleoSpherePredator-v0"
    assert len(meta["final_model_sha256"]) == 64
    assert (out / "final_model.zip").exists()


def test_smoke_training_v1_with_bc_and_curriculum():
    out = train(["--config", "ppo_v1", "--smoke", "--run-name", "pytest_smoke_v1"])
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["reward_version"] == "v1"
    assert meta["curriculum"]["spawn_near_prey_prob"] > 0
    assert meta["behavior_cloning"]["teacher"] == "rule"
    assert meta["behavior_cloning"]["imitation_accuracy"] > 0.5
