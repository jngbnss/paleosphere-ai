"""Build predator policies from a spec string: rule | random | ppo:<zip> | onnx:<onnx> | mlp:<json>.

`ppo:` needs the training extra (torch), `onnx:` the onnx extra, `mlp:` only numpy.
"""

from __future__ import annotations

from paleosphere.policies.actions import PredatorAction
from paleosphere.policies.base import Policy
from paleosphere.policies.random_policy import RandomPolicy
from paleosphere.policies.rule_based import RuleBasedPredator


def make_predator_policy(spec: str) -> Policy:
    if spec == "rule":
        return RuleBasedPredator()
    if spec == "random":
        return RandomPolicy(PredatorAction)
    if spec.startswith("ppo:"):
        from paleosphere.policies.ppo_policy import PPOPolicy  # needs training extras

        return PPOPolicy(spec.removeprefix("ppo:"))
    if spec.startswith("onnx:"):
        from paleosphere.policies.onnx_policy import OnnxPolicy  # needs onnx extra

        return OnnxPolicy(spec.removeprefix("onnx:"))
    if spec.startswith("mlp:"):
        from paleosphere.policies.mlp import MlpPolicy

        return MlpPolicy(spec.removeprefix("mlp:"))
    raise ValueError(
        f"unknown predator policy spec: {spec!r} "
        "(use rule | random | ppo:<zip> | onnx:<onnx> | mlp:<policy.json>)"
    )
