import pytest

from paleosphere.policies.factory import make_herbivore_policy
from training.evaluation.evaluate_herd import evaluate, to_markdown
from training.scripts.train_herd import train


def test_rule_vs_random_herd(tmp_path):
    df, summary = evaluate(["rule", "random"], ["rule"], ["eval_seen_map"], tmp_path,
                           max_ticks=300, workers=1, seeds_override=[10000, 10001])
    assert len(df) == 4
    assert (tmp_path / "episodes.csv").exists() and (tmp_path / "summary.md").exists()
    assert set(summary["herd"]) == {"rule", "random"}
    assert "포식자 사망률" in to_markdown(summary)


def test_trained_herd_policy_runs_in_evaluation():
    out = train(["--smoke", "--run-name", "pytest_herd_eval"])
    df, _ = evaluate([f"herd=ppo:{out / 'final_model.zip'}"], ["rule"], ["eval_seen_map"],
                     max_ticks=100, workers=1, seeds_override=[10000])
    assert df.loc[0, "herd"] == "herd" and df.loc[0, "ticks"] <= 100


def test_unknown_herbivore_spec():
    with pytest.raises(ValueError):
        make_herbivore_policy("nope")
