"""Build predator policies from a short spec string: 'rule', 'random' or 'ppo:<path>'."""

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
    raise ValueError(f"unknown predator policy spec: {spec!r} (use rule | random | ppo:<path>)")
