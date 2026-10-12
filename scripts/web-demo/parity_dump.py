"""Dump Python World trajectories driven by the web demo's RNG (pages/sim.js `Rng`).

The browser port uses mulberry32 instead of numpy PCG64. To check that the *rules* are ported
faithfully, this script swaps the World's numpy generators for a Python copy of that generator,
runs the real Python simulator with the rule-based policies, and writes per-tick states.
`parity_check.js` replays the same seeds with pages/sim.js and compares them.

    uv run python scripts/web-demo/parity_dump.py --out parity.json
    node scripts/web-demo/parity_check.js parity.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import paleosphere.core.world as world_mod
from paleosphere.config import load_world_config
from paleosphere.policies import RuleBasedHerbivore
from paleosphere.policies.factory import make_predator_policy

M32 = 0xFFFFFFFF


def imul(a: int, b: int) -> int:
    return (a * b) & M32


def hash32(a: int, b: int) -> int:
    h = imul(a ^ 0x9E3779B9, 0x85EBCA6B) ^ imul((b + 0x7F4A7C15) & M32, 0xC2B2AE35)
    h &= M32
    h ^= h >> 16
    h = imul(h, 0x7FEB352D)
    h ^= h >> 15
    h = imul(h, 0x846CA68B)
    h ^= h >> 16
    return h


class Mulberry:
    """Python copy of pages/sim.js Rng with the numpy Generator methods the sim uses."""

    def __init__(self, seed: int, stream: int):
        self.state = hash32(seed & M32, stream & M32)

    def _next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & M32
        t = self.state
        t = imul(t ^ (t >> 15), t | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296

    def random(self) -> float:
        return self._next()

    def _uniform1(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self._next()

    def _normal1(self, mu: float, sigma: float) -> float:
        u1 = 1.0 - self._next()
        u2 = self._next()
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def uniform(self, lo, hi, size=None):
        if size is None:
            return self._uniform1(float(lo), float(hi))
        return np.array([self._uniform1(float(lo), float(hi)) for _ in range(size)])

    def normal(self, mu, sigma, size=None):
        if size is None:
            return self._normal1(float(mu), float(sigma))
        return np.array([self._normal1(float(mu), float(sigma)) for _ in range(size)])


def make_world(config, seed: int):
    """World with Mulberry streams (0 layout, 1 move, 2 combat, 3 repro)."""
    real = np.random.default_rng

    def fake(ss):
        return Mulberry(seed, ss.spawn_key[-1])

    np.random.default_rng = fake
    try:
        return world_mod.World(config, seed)
    finally:
        np.random.default_rng = real


def state(world) -> dict:
    return {
        "tick": world.tick,
        "dinos": [
            [d.agent_id, int(d.alive), round(float(d.pos[0]), 6), round(float(d.pos[1]), 6),
             round(d.health, 4), round(d.energy, 4), round(d.hunger, 4), round(d.thirst, 4),
             d.current_action, d.target_id]
            for d in world.dinos.values()
        ],
        "plants": [round(p.food, 4) for p in world.plants],
    }


def run(config_name: str, seed: int, ticks: int, every: int, resource_scale: float | None):
    overrides = {}
    if resource_scale:
        base = load_world_config(config_name).map.plants
        overrides = {"map": {"plants": {
            "count": max(1, round(base.count * resource_scale)),
            "regrow_per_tick": base.regrow_per_tick * resource_scale,
        }}}
    config = load_world_config(config_name, **overrides)
    world = make_world(config, seed)
    pred, herb = make_predator_policy("rule"), RuleBasedHerbivore()
    out = [state(world)]
    events = {"kill": 0, "birth": 0, "death": 0}
    while world.tick < ticks and not world.done:
        actions = {
            d.agent_id: int((pred if d.species == "predator" else herb).act(world, d.agent_id))
            for d in world.alive()
        }
        for e in world.step(actions):
            if str(e.kind) in events:
                events[str(e.kind)] += 1
        if world.tick % every == 0:
            out.append(state(world))
    return {"config": config_name, "seed": seed, "resource_scale": resource_scale or 1.0,
            "ticks": world.tick, "every": every, "events": events, "states": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--every", type=int, default=10)
    args = ap.parse_args()
    # Use the plain sqrt form of hypot, as sim.js does, so last-bit differences in libm
    # implementations do not get amplified into diverging trajectories.
    math.hypot = lambda x, y: math.sqrt(x * x + y * y)
    runs = []
    for cfg, seed, scale, ticks in [
        ("map_a", 1, None, args.ticks), ("map_a", 42, None, args.ticks),
        ("map_a", 7, 0.6, args.ticks), ("map_b", 3, None, args.ticks),
        ("map_a", 11, 1.4, args.ticks), ("ecosystem", 5, None, 6000),
    ]:
        runs.append(run(cfg, seed, ticks, args.every, scale))
        r = runs[-1]
        print(cfg, seed, scale, "ticks", r["ticks"], r["events"])
    args.out.write_text(json.dumps(runs), encoding="utf-8")


if __name__ == "__main__":
    main()
