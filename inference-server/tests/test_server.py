import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import main as server
from app import policies
from app.policies import PolicyRegistry


@pytest.fixture(scope="module")
def smoke_models_dir(tmp_path_factory):
    """A models/ dir holding a tiny smoke-trained PPO model ppo-v1 and its ONNX export."""
    from training.scripts.export_onnx import export
    from training.scripts.train_ppo import train

    out = train(["--smoke", "--run-name", "pytest_server_smoke"])
    models = tmp_path_factory.mktemp("models")
    (models / "ppo-v1.zip").write_bytes((out / "final_model.zip").read_bytes())
    export(models / "ppo-v1.zip", models, ticks=100, n_random=100)
    return models


@pytest.fixture
def client(monkeypatch, smoke_models_dir):
    monkeypatch.setattr(server, "registry", PolicyRegistry(smoke_models_dir))
    return TestClient(server.app)


def test_health_and_policies(client):
    assert client.get("/health").json()["status"] == "ok"
    names = [p["name"] for p in client.get("/policies").json()]
    assert names == ["rule", "random", "ppo-v1", "ppo-v1-onnx"]


def test_predict(client):
    resp = client.post("/predict", json={"observation": [0.0] * 26})
    body = resp.json()
    assert resp.status_code == 200
    assert body["policy_version"] == "ppo-v1"
    assert body["action"] in {"SEARCH", "APPROACH", "CHASE", "ATTACK", "GO_TO_WATER", "REST",
                              "GIVE_UP"}
    assert body["inference_time_ms"] < 100


def test_predict_onnx_matches_sb3(client):
    rng = np.random.default_rng(3)
    for obs in rng.uniform(-1, 1, (20, 26)).tolist():
        sb3 = client.post("/predict", json={"observation": obs, "policy": "ppo-v1"}).json()
        onnx = client.post("/predict", json={"observation": obs, "policy": "ppo-v1-onnx"}).json()
        assert onnx["action_id"] == sb3["action_id"]
        assert onnx["policy_version"] == "ppo-v1-onnx"


def test_registry_prefers_sb3_then_falls_back_to_onnx(smoke_models_dir, monkeypatch):
    assert PolicyRegistry(smoke_models_dir).default_ppo() == "ppo-v1"
    monkeypatch.setattr(policies, "_installed", lambda module: module == "onnxruntime")
    torch_free = PolicyRegistry(smoke_models_dir)
    assert torch_free.names == ["rule", "random", "ppo", "ppo-v1-onnx"]
    assert torch_free.get("ppo").name == "onnx:ppo-v1-onnx"


def test_predict_rejects_bad_observation(client):
    assert client.post("/predict", json={"observation": [0.0] * 3}).status_code == 422


def test_viewer_page(client):
    assert "PaleoSphere" in client.get("/").text


@pytest.mark.parametrize("policy", ["rule", "ppo", "ppo-v1-onnx"])
def test_websocket_session(client, policy):
    with client.websocket_connect("/ws/sim") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and "ppo" in hello["policies"]
        ws.send_text(json.dumps({"type": "start", "seed": 10000, "predator_policy": policy,
                                 "ticks_per_second": 200}))
        first = ws.receive_json()
        assert first["type"] == "snapshot" and first["tick"] == 0
        assert len(first["dinos"]) == 9
        ticks = [ws.receive_json()["tick"] for _ in range(5)]
        assert ticks == sorted(ticks) and ticks[-1] > 0
        ws.send_text(json.dumps({"type": "pause"}))
        msg = ws.receive_json()
        while not msg["paused"]:
            msg = ws.receive_json()
        ws.send_text(json.dumps({"type": "step", "n": 10}))
        stepped = ws.receive_json()
        assert stepped["tick"] == msg["tick"] + 10
        pred = next(d for d in stepped["dinos"] if d["species"] == "predator")
        assert pred["status_label"]


def test_websocket_errors(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "pause"}))
        assert ws.receive_json()["type"] == "error"
        ws.send_text(json.dumps({"type": "start", "predator_policy": "nope"}))
        assert ws.receive_json()["type"] == "error"
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
