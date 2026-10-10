import pytest
from pydantic import ValidationError

from app import schemas
from app.export_schema import render
from paleosphere.config import REPO_ROOT, load_world_config
from paleosphere.core.world import World
from paleosphere.explain import LABELS, status_code
from paleosphere.policies import RuleBasedHerbivore, RuleBasedPredator


def test_control_commands_parse():
    a = schemas.control_adapter
    assert isinstance(a.validate_python({"type": "pause"}), schemas.PauseCommand)
    start = a.validate_python({"type": "start", "seed": 5, "predator_policy": "ppo"})
    assert start.map == "map_a" and start.seed == 5
    with pytest.raises(ValidationError):
        a.validate_python({"type": "set_speed", "ticks_per_second": 0})
    with pytest.raises(ValidationError):
        a.validate_python({"type": "explode"})


def test_predict_request_requires_26_dims():
    schemas.PredictRequest(observation=[0.0] * 26)
    with pytest.raises(ValidationError):
        schemas.PredictRequest(observation=[0.0] * 25)


def test_status_codes_cover_episode():
    world = World(load_world_config("map_a"), 42)
    pred, herb = RuleBasedPredator(), RuleBasedHerbivore()
    seen = set()
    for _ in range(1500):
        actions = {
            d.agent_id: (pred if d.species == "predator" else herb).act(world, d.agent_id)
            for d in world.alive()
        }
        world.step(actions)
        for d in world.dinos.values():
            code = status_code(world, d.agent_id)
            assert code in LABELS
            seen.add(code)
    assert {"chasing", "fleeing", "resting"} <= seen


def test_protocol_doc_up_to_date():
    """docs/protocol.md must match the schemas (regenerate with python -m app.export_schema)."""
    doc = (REPO_ROOT / "docs" / "protocol.md").read_text(encoding="utf-8")
    assert doc == render()
