import json

import pytest

from paleosphere.config import REPO_ROOT
from paleosphere.policies.ppo_policy import PPOPolicy
from training.evaluation.evaluate import evaluate, load_seed_sets


def test_seed_sets_disjoint_from_training_range():
    sets = load_seed_sets()
    lo, hi = sets["train"]["range"]
    for name in ("eval_seen_map", "eval_unseen_map"):
        assert all(not (lo <= s < hi) for s in sets[name]["seeds"])
    assert sets["eval_unseen_map"]["map"] == "map_b"


def test_evaluate_rule_and_random(tmp_path):
    df, summary = evaluate(
        ["rule", "random"], ["eval_seen_map"], tmp_path, max_ticks=600, workers=1,
        seeds_override=[10000, 10001, 10002],
    )
    assert len(df) == 6
    assert set(summary["policy"]) == {"rule", "random"}
    assert (tmp_path / "episodes.csv").exists()
    assert "| rule |" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_resource_override_changes_world(tmp_path):
    df, _ = evaluate(
        ["rule"], ["eval_seen_map"], None, max_ticks=50, workers=1, seeds_override=[10000],
        world_overrides={"map": {"plants": {"count": 4}}}, set_suffix="@res0.4",
    )
    assert df["seed_set"].iloc[0] == "eval_seen_map@res0.4"


@pytest.fixture(scope="module")
def smoke_model():
    from training.scripts.train_ppo import train

    out = train(["--smoke", "--run-name", "pytest_eval_smoke"])
    return out / "final_model.zip"


def test_ppo_policy_adapter(smoke_model, tmp_path):
    policy = PPOPolicy(smoke_model)
    meta = policy.metadata()
    assert meta["kind"] == "ppo" and len(meta["model_sha256"]) == 64
    df, _ = evaluate(
        [f"ppo=ppo:{smoke_model}"], ["eval_seen_map"], tmp_path, max_ticks=200, workers=1,
        seeds_override=[10000],
    )
    assert df["spec"].iloc[0].startswith("ppo:")
    json.loads(df["herbivore_deaths"].iloc[0])
    assert smoke_model.is_relative_to(REPO_ROOT)
