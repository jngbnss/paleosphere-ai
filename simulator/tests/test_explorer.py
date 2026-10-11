from paleosphere.config import load_world_config
from paleosphere.core.world import World
from paleosphere.explorer import FieldJournal
from paleosphere.policies import RuleBasedHerbivore, RuleBasedPredator


def step(world, journal=None, n=1):
    herd, pred = RuleBasedHerbivore(), RuleBasedPredator()
    for _ in range(n):
        acts = {d.agent_id: (pred if d.species.value == "predator" else herd).act(world, d.agent_id)
                for d in world.alive()}
        events = world.step(acts)
        if journal is not None:
            journal.witness(world, events)


def test_explorer_does_not_change_the_simulation():
    cfg = load_world_config("map_a")
    plain, explored = World(cfg, 10000), World(cfg, 10000)
    journal = FieldJournal(explored)
    for i in range(30):
        step(plain, n=20)
        journal.move_to(5 + i * 2, 60 - i * 2)
        journal.scan(explored)
        step(explored, journal, n=20)
    assert plain.snapshot_hash() == explored.snapshot_hash()


def test_scan_identifies_nearby_only_and_marks_new():
    world = World(load_world_config("map_a"), 10000)
    journal = FieldJournal(world)
    herd = world.alive()[0]
    journal.move_to(*herd.pos)
    first = journal.scan(world)
    assert first and first[0]["agent_id"] == herd.agent_id and first[0]["new"]
    assert all(s["distance"] <= journal.scan_radius for s in first)
    assert not any(s["new"] for s in journal.scan(world))
    assert journal.records[herd.agent_id].sightings == 2


def test_report_compares_estimate_with_truth():
    world = World(load_world_config("map_a"), 10000)
    journal = FieldJournal(world)
    journal.move_to(*world.alive()[0].pos)
    journal.scan(world)
    stats = journal.stats(world)
    assert 0 < stats["estimated_alive"]["herbivore"] <= stats["actual_alive"]["herbivore"]
    assert 0 < stats["explored_fraction"] < 1
    md = journal.report(world)
    assert "현장 보고서" in md and "실제 생존" in md


def test_witnesses_kills_in_view():
    world = World(load_world_config("map_a"), 10000)
    journal = FieldJournal(world, view_radius=200.0)  # sees the whole map
    step(world, journal, n=2000)
    kinds = {w["kind"] for w in journal.witnessed}
    assert "kill" in kinds and "death" in kinds


def test_witnessed_death_updates_estimate():
    world = World(load_world_config("map_a"), 10000)
    journal = FieldJournal(world, scan_radius=200.0, view_radius=200.0)
    journal.scan(world)
    step(world, journal, n=2000)
    dead_seen = {w["agent_id"] for w in journal.witnessed if w["kind"] == "death"}
    assert dead_seen
    assert all(not journal.records[a].alive_when_last_seen for a in dead_seen)
    journal.scan(world)
    stats = journal.stats(world)
    assert stats["estimated_alive"] == stats["actual_alive"]  # saw everything, missed nothing
    assert "사냥 성공" in journal.report(world)
