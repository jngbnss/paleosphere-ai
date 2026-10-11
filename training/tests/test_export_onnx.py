import json

import numpy as np
import pytest
from stable_baselines3 import PPO

from paleosphere.config import load_world_config
from paleosphere.logging.episode import run_episode
from paleosphere.policies import OBS_DIM, PredatorAction, RuleBasedHerbivore
from paleosphere.policies.factory import make_predator_policy
from paleosphere.policies.mlp import MlpPolicy, MlpWeights
from training.environments import PredatorEnv
from training.scripts.export_onnx import build_onnx, export, extract_actor

ort = pytest.importorskip("onnxruntime")


@pytest.fixture(scope="module")
def model_path(tmp_path_factory):
    # An untrained policy is enough: the export must reproduce whatever the weights are.
    path = tmp_path_factory.mktemp("model") / "tiny.zip"
    PPO("MlpPolicy", PredatorEnv(max_steps=50), seed=0, device="cpu").save(path)
    return path


def test_export_matches_sb3(model_path, tmp_path):
    report = export(model_path, tmp_path, name="tiny", ticks=200, n_random=500)
    assert report["onnx_matches_sb3"] == 1.0
    assert report["numpy_matches_sb3"] == 1.0
    assert report["max_abs_logit_diff_onnx"] < 1e-4
    assert (tmp_path / "tiny.onnx").exists()
    weights = json.loads((tmp_path / "tiny.policy.json").read_text(encoding="utf-8"))
    assert weights["obs_dim"] == OBS_DIM
    assert weights["actions"] == [a.name for a in PredatorAction]
    assert weights["source"]["model_sha256"] == report["source"]["model_sha256"]


def test_onnx_graph_batches_and_outputs_int64_actions(model_path):
    weights = extract_actor(PPO.load(model_path, device="cpu"))
    session = ort.InferenceSession(
        build_onnx(weights).SerializeToString(), providers=["CPUExecutionProvider"]
    )
    obs = np.random.default_rng(1).uniform(-1, 1, (5, OBS_DIM)).astype(np.float32)
    logits, action = session.run(["logits", "action"], {"obs": obs})
    assert logits.shape == (5, len(PredatorAction))
    assert action.dtype == np.int64
    np.testing.assert_array_equal(action, MlpWeights(weights).logits(obs).argmax(axis=1))


def test_mlp_policy_rejects_wrong_format(tmp_path):
    path = tmp_path / "bad.policy.json"
    path.write_text(json.dumps({"format": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="format"):
        MlpPolicy(path)


def test_exported_policies_reproduce_sb3_episode(model_path, tmp_path):
    export(model_path, tmp_path, name="tiny", ticks=50, n_random=10)
    cfg = load_world_config("map_a")
    hashes = {
        spec.split(":")[0]: run_episode(
            cfg, 42, make_predator_policy(spec), RuleBasedHerbivore(), 400
        ).final_hash
        for spec in (
            f"ppo:{model_path}",
            f"onnx:{tmp_path / 'tiny.onnx'}",
            f"mlp:{tmp_path / 'tiny.policy.json'}",
        )
    }
    assert hashes["onnx"] == hashes["ppo"]
    assert hashes["mlp"] == hashes["ppo"]
