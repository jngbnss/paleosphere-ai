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
    from training.scripts.train_herd import train as train_herd

    herd = train_herd(["--smoke", "--run-name", "pytest_server_herd"])
    (models / "herd-v0.zip").write_bytes((herd / "final_model.zip").read_bytes())
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


def _drive(ws, start: dict, ticks: int, decide=None) -> list[dict]:
    """Start a session and collect `ticks` snapshots after tick 0.

    With `decide`, the session is in client mode and each snapshot is answered with an action.
    """
    ws.receive_json()
    ws.send_text(json.dumps({"type": "start", "seed": 10000, "ticks_per_second": 200, **start}))
    snaps = [ws.receive_json()]
    while len(snaps) <= ticks:
        if decide is not None:
            obs = snaps[-1]["predator_observation"]
            ws.send_text(json.dumps({"type": "action", "tick": snaps[-1]["tick"],
                                     "action": decide(obs)}))
        snaps.append(ws.receive_json())
    return snaps


def test_client_mode_reproduces_server_policy(client):
    policy = server.registry.get("ppo-v1-onnx")
    with client.websocket_connect("/ws/sim") as ws:
        local = _drive(ws, {"predator_policy": "client"}, 60,
                       lambda obs: policy.predict(np.asarray(obs, dtype=np.float32)))
    with client.websocket_connect("/ws/sim") as ws:
        remote = _drive(ws, {"predator_policy": "ppo-v1-onnx"}, 60)
    assert [s["tick"] for s in local] == list(range(61))
    assert len(local[0]["predator_observation"]) == 26
    assert remote[0]["predator_observation"] is None
    assert [s["dinos"] for s in local] == [s["dinos"] for s in remote]


def test_client_mode_waits_and_rejects_bad_actions(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start", "predator_policy": "client"}))
        assert ws.receive_json()["tick"] == 0
        ws.send_text(json.dumps({"type": "action", "tick": 5, "action": 0}))
        assert "stale" in ws.receive_json()["message"]
        ws.send_text(json.dumps({"type": "step", "n": 1}))
        assert ws.receive_json()["type"] == "error"
        ws.send_text(json.dumps({"type": "action", "tick": 0, "action": 5}))
        nxt = ws.receive_json()
        assert nxt["tick"] == 1
        pred = next(d for d in nxt["dinos"] if d["species"] == "predator")
        assert pred["current_action"] == "REST"


def test_action_rejected_outside_client_mode(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start", "predator_policy": "rule",
                                 "ticks_per_second": 1}))
        ws.receive_json()
        ws.send_text(json.dumps({"type": "action", "tick": 0, "action": 0}))
        msg = ws.receive_json()
        while msg["type"] != "error":
            msg = ws.receive_json()
        assert "client" in msg["message"]


def test_ecosystem_map_session(client):
    with client.websocket_connect("/ws/sim") as ws:
        assert "ecosystem" in ws.receive_json()["maps"]
        ws.send_text(json.dumps({"type": "start", "seed": 3, "map": "ecosystem",
                                 "predator_policy": "rule", "ticks_per_second": 1}))
        first = ws.receive_json()
        assert first["map"] == "ecosystem"
        assert first["metrics"]["predators_alive"] == 2
        assert first["dinos"][0]["generation"] == 0
        ws.send_text(json.dumps({"type": "pause"}))
        msg = ws.receive_json()
        while not msg["paused"]:
            msg = ws.receive_json()
        ws.send_text(json.dumps({"type": "step", "n": 1000}))
        later = ws.receive_json()
        assert later["metrics"]["births"] > 0
        assert any(d["parent_id"] for d in later["dinos"])


def test_client_mode_rejected_on_ecosystem(client):
    with client.websocket_connect("/ws/sim") as ws:
        ws.receive_json()
        ws.send_text(json.dumps({"type": "start", "map": "ecosystem",
                                 "predator_policy": "client"}))
        assert "exactly one predator" in ws.receive_json()["message"]


def test_learned_herd_policy_session(client):
    with client.websocket_connect("/ws/sim") as ws:
        hello = ws.receive_json()
        assert hello["herbivore_policies"] == ["rule", "random", "herd-v0"]
        assert "herd-v0" not in hello["policies"]
        ws.send_text(json.dumps({"type": "start", "seed": 10000, "predator_policy": "rule",
                                 "herbivore_policy": "herd-v0", "ticks_per_second": 200}))
        first = ws.receive_json()
        assert first["herbivore_policy"] == "herd-v0"
        assert ws.receive_json()["tick"] == 1
        ws.send_text(json.dumps({"type": "start", "herbivore_policy": "nope"}))
        msg = ws.receive_json()
        while msg["type"] != "error":
            msg = ws.receive_json()
        assert "herbivore" in msg["message"]
