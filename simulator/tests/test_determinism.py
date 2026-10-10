"""Same seed + same config + same policies must reproduce the exact same world.

Regenerate golden files after an intentional rule change with:
    UPDATE_GOLDEN=1 uv run pytest simulator/tests/test_determinism.py
and record the reason in docs/decision-log.md.
"""

import json
import os
from pathlib import Path

import pytest

from paleosphere.config import load_world_config
from paleosphere.core.world import World
from paleosphere.logging.episode import run_episode
from paleosphere.policies import (
    PredatorAction,
    RandomPolicy,
    RuleBasedHerbivore,
    RuleBasedPredator,
)

GOLDEN_DIR = Path(__file__).parent / "golden"
REGRESSION_SEEDS = [42, 777, 2026]


def rule_episode(seed, map_name="map_a", ticks=2000):
    return run_episode(
        load_world_config(map_name), seed, RuleBasedPredator(), RuleBasedHerbivore(), ticks
    )


def test_same_seed_same_hash():
    a = rule_episode(42, ticks=600)
    b = rule_episode(42, ticks=600)
    assert a.final_hash == b.final_hash
    assert a.to_dict() == b.to_dict()


def test_different_seed_different_hash():
    assert rule_episode(42, ticks=50).final_hash != rule_episode(43, ticks=50).final_hash


def test_random_policy_is_seeded():
    cfg = load_world_config("map_a")
    runs = [
        run_episode(cfg, 7, RandomPolicy(PredatorAction), RuleBasedHerbivore(), 300).final_hash
        for _ in range(2)
    ]
    assert runs[0] == runs[1]


def test_initial_hash_stable_across_instances():
    cfg = load_world_config("map_b")
    assert World(cfg, 5).snapshot_hash() == World(cfg, 5).snapshot_hash()


@pytest.mark.parametrize("seed", REGRESSION_SEEDS)
def test_rule_based_golden(seed):
    summary = rule_episode(seed).to_dict()
    path = GOLDEN_DIR / f"rule_map_a_seed{seed}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    golden = json.loads(path.read_text(encoding="utf-8"))
    assert summary == golden
