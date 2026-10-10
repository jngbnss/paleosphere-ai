"""Each detector must fire on a policy that deliberately exhibits the hack, and stay quiet
on the rule-based baseline."""

import pandas as pd
import pytest

from paleosphere.policies import PredatorAction
from training.evaluation import evaluate as ev
from training.evaluation.hacking_detectors import (
    DETECTORS,
    add_flags,
    flag_episode,
    load_cases,
    policy_report,
)

SEEDS = [10000, 10001]


class ScriptedPredator:
    """Fixed-action predator used to reproduce a hack on purpose."""

    def __init__(self, action: PredatorAction):
        self.action = action
        self.name = f"scripted-{action.name.lower()}"

    def reset(self, seed=None):
        pass

    def act(self, world, agent_id):
        return int(self.action)

    def metadata(self):
        return {"name": self.name}


class Shadower:
    """Pursues forever and never attacks."""

    name = "scripted-shadow"

    def reset(self, seed=None):
        pass

    def act(self, world, agent_id):
        me = world.dinos[agent_id]
        if me.target_id is None:
            return int(PredatorAction.SEARCH)
        return int(PredatorAction.APPROACH if me.energy < 30 else PredatorAction.CHASE)

    def metadata(self):
        return {"name": self.name}


@pytest.fixture
def scripted(monkeypatch):
    policies = {
        "idle": ScriptedPredator(PredatorAction.REST),
        "spam": ScriptedPredator(PredatorAction.ATTACK),
        "water": ScriptedPredator(PredatorAction.GO_TO_WATER),
        "shadow": Shadower(),
    }

    def resolve(spec):
        return policies.get(spec) or ev.make_predator_policy(spec)

    monkeypatch.setattr(ev, "_policy", resolve)
    return policies


def flagged(spec, ticks=2000):
    df, _ = ev.evaluate([spec], ["eval_seen_map"], None, ticks, workers=1, seeds_override=SEEDS)
    return add_flags(df)


@pytest.mark.parametrize(
    ("spec", "detector"),
    [
        ("idle", "idle_forever"),
        ("spam", "attack_spam"),
        ("water", "water_farming"),
        ("shadow", "shadowing"),
    ],
)
def test_detector_fires_on_scripted_hack(scripted, spec, detector):
    df = flagged(spec)
    assert df[f"hack_{detector}"].all(), df.filter(like="act_").to_dict("records")


def test_rule_baseline_is_clean():
    df = flagged("rule")
    rates = policy_report(df)
    assert rates["suspected"].iloc[0] == "-"


def base_row(**kw):
    row = {f"act_{a.name.lower()}": 0.0 for a in PredatorAction}
    row.update(
        kills=1, invalid_attack_rate=0.0, predator_mean_thirst=40.0,
        predator_boundary_fraction=0.0, predator_death_cause=None,
    )
    row.update(kw)
    return row


def test_boundary_hugging_synthetic():
    assert flag_episode(base_row(predator_boundary_fraction=0.8))["boundary_hugging"]
    assert not flag_episode(base_row(predator_boundary_fraction=0.1))["boundary_hugging"]


def test_idle_via_give_up_synthetic():
    """Regression for PPO v0: standing still with GIVE_UP must count as idling."""
    assert flag_episode(base_row(act_give_up=0.83, act_rest=0.15, kills=0))["idle_forever"]


def test_chase_to_death_synthetic():
    assert flag_episode(base_row(predator_death_cause="exhaustion"))["chase_to_death"]
    assert not flag_episode(base_row(predator_death_cause="starvation"))["chase_to_death"]


def test_policy_report_threshold():
    cases = load_cases()
    rows = [base_row(act_rest=0.9, kills=0)] * 2 + [base_row()] * 2
    df = pd.DataFrame(rows).assign(policy="p", seed_set="s")
    rates = policy_report(add_flags(df, cases), cases)
    assert rates["hack_idle_forever"].iloc[0] == 0.5
    assert "idle_forever" in rates["suspected"].iloc[0]
    assert set(DETECTORS) == {c.removeprefix("hack_") for c in rates.columns if "hack_" in c}
