import numpy as np
import pytest

from paleosphere.config import load_world_config
from paleosphere.entities import Species
from paleosphere.resources import generate_map


@pytest.mark.parametrize("map_name", ["map_a", "map_b"])
def test_generate_map_counts(map_name):
    cfg = load_world_config(map_name)
    gen = generate_map(cfg, np.random.default_rng(42))
    assert len(gen.plants) == cfg.map.plants.count
    assert len(gen.waters) == len(cfg.map.waters)
    assert len(gen.rocks) == cfg.map.rocks.count
    species = [d.species for d in gen.dinos]
    assert species.count(Species.HERBIVORE) == cfg.population.herbivore
    assert species.count(Species.PREDATOR) == cfg.population.predator


def test_map_b_overrides_default():
    a = load_world_config("map_a")
    b = load_world_config("map_b")
    assert b.map.name == "map_b"
    assert b.map.plants.count < a.map.plants.count
    assert b.map.plants.radius == a.map.plants.radius  # inherited
    assert b.map.waters != a.map.waters


def test_same_seed_same_layout():
    cfg = load_world_config("map_a")
    g1 = generate_map(cfg, np.random.default_rng(7))
    g2 = generate_map(cfg, np.random.default_rng(7))
    assert [p.to_dict() for p in g1.plants] == [p.to_dict() for p in g2.plants]
    assert [d.to_dict() for d in g1.dinos] == [d.to_dict() for d in g2.dinos]


def test_entities_inside_map_and_out_of_rocks():
    cfg = load_world_config("map_a")
    for seed in range(20):
        gen = generate_map(cfg, np.random.default_rng(seed))
        for d in gen.dinos:
            assert 0 <= d.pos[0] <= cfg.map.size and 0 <= d.pos[1] <= cfg.map.size
            for r in gen.rocks:
                assert np.linalg.norm(d.pos - r.pos) >= r.radius


def test_predator_far_from_herd():
    cfg = load_world_config("map_a")
    gen = generate_map(cfg, np.random.default_rng(3))
    herd = np.mean([d.pos for d in gen.dinos if d.species == Species.HERBIVORE], axis=0)
    pred = next(d for d in gen.dinos if d.species == Species.PREDATOR)
    assert np.linalg.norm(pred.pos - herd) > cfg.population.predator_min_distance / 2
