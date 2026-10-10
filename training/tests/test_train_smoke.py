import json

from training.scripts.train_ppo import train


def test_smoke_training_writes_artifacts():
    out = train(["--smoke", "--run-name", "pytest_smoke"])
    meta = json.loads((out / "metadata.json").read_text(encoding="utf-8"))
    assert meta["total_timesteps"] >= 2048
    assert meta["env_version"] == "PaleoSpherePredator-v0"
    assert len(meta["final_model_sha256"]) == 64
    assert (out / "final_model.zip").exists()
