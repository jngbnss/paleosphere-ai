"""Export a trained PPO predator to ONNX and to portable JSON weights.

    uv run --extra training --extra onnx python -m training.scripts.export_onnx \
        --model models/ppo-v2.zip

writes `models/ppo-v2.onnx` (onnxruntime, no torch) and `models/ppo-v2.policy.json` (Godot,
numpy). Only the deterministic actor is exported: obs -> MLP -> logits -> argmax. The value
head and the action distribution are training-only.

The ONNX graph is assembled from the weights with `onnx.helper` instead of torch.onnx: the
actor is three Gemm layers, and building it directly keeps the export free of the exporter
backend (TorchScript vs dynamo/onnxscript) that changes between torch releases.

Before writing, the export is verified: on observations collected from real episodes on the
regression seeds plus random in-range observations, SB3, ONNX and numpy must pick the same
action. The report also records the smallest top-2 logit margin, i.e. how much numeric slack
other runtimes (float64 GDScript) have before an argmax could flip.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from paleosphere.config import load_world_config
from paleosphere.logging.episode import run_episode
from paleosphere.policies import OBS_DIM, PredatorAction, RuleBasedHerbivore
from paleosphere.policies.mlp import FORMAT, MlpWeights
from paleosphere.policies.observation import predator_observation

REGRESSION_SEEDS = [42, 777, 2026]
OPSET = 17


def extract_actor(model) -> dict:
    """SB3 PPO (MlpPolicy, Box obs, Discrete actions) -> portable weights dict."""
    import torch.nn as nn
    from stable_baselines3.common.torch_layers import FlattenExtractor

    policy = model.policy
    if not isinstance(policy.pi_features_extractor, FlattenExtractor):
        raise ValueError("only FlattenExtractor policies can be exported")
    activation = {nn.Tanh: "tanh", nn.ReLU: "relu"}.get(policy.activation_fn)
    if activation is None:
        raise ValueError(f"unsupported activation {policy.activation_fn}")
    linears = [m for m in policy.mlp_extractor.policy_net if isinstance(m, nn.Linear)]
    linears.append(policy.action_net)
    layers = [
        {
            "weight": m.weight.detach().cpu().numpy().astype(np.float32).tolist(),
            "bias": m.bias.detach().cpu().numpy().astype(np.float32).tolist(),
        }
        for m in linears
    ]
    return {
        "format": FORMAT,
        "obs_dim": int(policy.observation_space.shape[0]),
        "activation": activation,
        "actions": [a.name for a in PredatorAction],
        "layers": layers,
    }


def build_onnx(weights: dict):
    """Inputs `obs` float32[N, obs_dim]; outputs `logits` float32[N, A], `action` int64[N]."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    activation = {"tanh": "Tanh", "relu": "Relu"}[weights["activation"]]
    n_layers = len(weights["layers"])
    nodes, inits = [], []
    x = "obs"
    for i, layer in enumerate(weights["layers"]):
        w = np.asarray(layer["weight"], dtype=np.float32)
        b = np.asarray(layer["bias"], dtype=np.float32)
        inits += [numpy_helper.from_array(w, f"w{i}"), numpy_helper.from_array(b, f"b{i}")]
        last = i == n_layers - 1
        out = "logits" if last else f"h{i}_pre"
        nodes.append(helper.make_node("Gemm", [x, f"w{i}", f"b{i}"], [out], transB=1))
        if not last:
            nodes.append(helper.make_node(activation, [out], [f"h{i}"]))
            x = f"h{i}"
    nodes.append(helper.make_node("ArgMax", ["logits"], ["action"], axis=1, keepdims=0))
    n_actions = len(weights["actions"])
    graph = helper.make_graph(
        nodes,
        "paleosphere_predator_actor",
        [helper.make_tensor_value_info("obs", TensorProto.FLOAT, ["N", weights["obs_dim"]])],
        [
            helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["N", n_actions]),
            helper.make_tensor_value_info("action", TensorProto.INT64, ["N"]),
        ],
        inits,
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", OPSET)], producer_name="paleosphere-ai"
    )
    model.ir_version = 8  # loadable by onnxruntime >= 1.10
    helper.set_model_props(
        model,
        {
            "actions": json.dumps(weights["actions"]),
            "source": json.dumps(weights.get("source", {})),
        },
    )
    onnx.checker.check_model(model)
    return model


class _Recorder:
    """Wraps a policy and keeps every predator observation it was asked about."""

    def __init__(self, policy):
        self.policy = policy
        self.name = policy.name
        self.observations: list[np.ndarray] = []

    def reset(self, seed=None):
        self.policy.reset(seed)

    def act(self, world, agent_id):
        obs = predator_observation(world, agent_id)
        self.observations.append(obs)
        return self.policy.predict(obs)


def collect_observations(policy, seeds: list[int], ticks: int, n_random: int) -> np.ndarray:
    recorder = _Recorder(policy)
    config = load_world_config("map_a")
    for seed in seeds:
        run_episode(config, seed, recorder, RuleBasedHerbivore(), ticks)
    rng = np.random.default_rng(0)
    random_obs = rng.uniform(-1.0, 1.0, size=(n_random, OBS_DIM)).astype(np.float32)
    return np.concatenate([np.asarray(recorder.observations, np.float32), random_obs])


def verify(model, onnx_path: Path, weights: dict, obs: np.ndarray) -> dict:
    import onnxruntime as ort
    import torch

    with torch.no_grad():
        dist = model.policy.get_distribution(torch.as_tensor(obs))
        sb3_logits = dist.distribution.logits.numpy()
    sb3_actions, _ = model.predict(obs, deterministic=True)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    onnx_logits, onnx_actions = session.run(["logits", "action"], {"obs": obs})
    mlp = MlpWeights(weights)
    np_logits = mlp.logits(obs)
    np_actions = np_logits.argmax(axis=1)
    # logits from the Categorical are log-softmax normalised; compare raw scores via argmax
    # agreement and via the differences between logits, which normalisation does not change.
    centered = lambda z: z - z.mean(axis=1, keepdims=True)  # noqa: E731
    top2 = np.sort(np_logits, axis=1)[:, -2:]
    return {
        "samples": int(len(obs)),
        "onnx_matches_sb3": float(np.mean(onnx_actions == sb3_actions)),
        "numpy_matches_sb3": float(np.mean(np_actions == sb3_actions)),
        "max_abs_logit_diff_onnx": float(
            np.max(np.abs(centered(onnx_logits) - centered(sb3_logits)))
        ),
        "max_abs_logit_diff_numpy": float(
            np.max(np.abs(centered(np_logits) - centered(sb3_logits)))
        ),
        "min_top2_margin": float(np.min(top2[:, 1] - top2[:, 0])),
    }


def export(
    model_path: Path, out_dir: Path, name: str | None = None, ticks: int = 2000,
    n_random: int = 2000,
) -> dict:
    import onnx

    from paleosphere.policies.ppo_policy import PPOPolicy

    ppo = PPOPolicy(model_path)
    name = name or model_path.stem
    weights = extract_actor(ppo.model)
    weights["source"] = {
        "version": name,
        "model_file": model_path.name,
        "model_sha256": ppo.sha256,
        "run_name": ppo.training_metadata.get("run_name"),
        "reward_version": ppo.training_metadata.get("reward_version"),
        "train_seed": ppo.training_metadata.get("train_seed"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    onnx_path = out_dir / f"{name}.onnx"
    json_path = out_dir / f"{name}.policy.json"
    onnx.save(build_onnx(weights), onnx_path)
    json_path.write_text(json.dumps(weights, separators=(",", ":")), encoding="utf-8")

    obs = collect_observations(ppo, REGRESSION_SEEDS, ticks, n_random)
    report = verify(ppo.model, onnx_path, weights, obs)
    report.update(
        onnx=str(onnx_path),
        onnx_sha256=hashlib.sha256(onnx_path.read_bytes()).hexdigest(),
        policy_json=str(json_path),
        policy_json_sha256=hashlib.sha256(json_path.read_bytes()).hexdigest(),
        source=weights["source"],
    )
    if report["onnx_matches_sb3"] < 1.0 or report["numpy_matches_sb3"] < 1.0:
        raise RuntimeError(f"exported actor disagrees with SB3: {report}")
    return report


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Export a PPO predator to ONNX + JSON weights.")
    parser.add_argument("--model", type=Path, default=Path("models/ppo-v2.zip"))
    parser.add_argument("--out-dir", type=Path, help="default: next to the model")
    parser.add_argument("--name", help="output base name (default: model file stem)")
    parser.add_argument("--ticks", type=int, default=2000, help="ticks per verification episode")
    parser.add_argument("--random-samples", type=int, default=2000)
    args = parser.parse_args(argv)
    report = export(
        args.model, args.out_dir or args.model.parent, args.name, args.ticks, args.random_samples
    )
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()
