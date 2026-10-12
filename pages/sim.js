/*
 * PaleoSphere AI — browser port of simulator/paleosphere (core/world.py, metabolism.py,
 * combat/attack.py, resources/mapgen.py, policies/rule_based.py, policies/observation.py,
 * policies/mlp.py). Same rules, same tick order, same parameters (configs/world/*.yaml,
 * configs/policies/rule_based.yaml).
 *
 * The one deliberate difference: random numbers. Python uses numpy PCG64 streams; this file
 * uses a small seeded generator (same stream layout: layout / move / combat / repro). A given
 * seed therefore produces a different map than in Python, but the rules are identical. The
 * test harness (scripts/web-demo/parity_*.py|js) injects this generator into the Python World and checks that
 * both produce the same trajectories tick by tick.
 *
 * Works in the browser (window.Paleo) and in node (module.exports).
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ config
  // configs/world/default.yaml (map_a)
  const DEFAULT = {
    map: {
      name: "map_a", size: 64.0,
      plants: { count: 10, radius: 2.5, max_food: 60.0, regrow_per_tick: 0.05 },
      waters: [{ pos: [16.0, 48.0], radius: 4.0 }, { pos: [50.0, 14.0], radius: 3.5 }],
      rocks: { count: 6, radius_min: 1.5, radius_max: 3.0 },
    },
    population: { herbivore: 8, predator: 1, herd_spread: 6.0, predator_min_distance: 25.0 },
    time: { day_length: 400, night_fraction: 0.3, night_vision_multiplier: 0.6 },
    species: {
      herbivore: {
        walk_speed: 0.30, sprint_speed: 0.80, vision: 14.0, hunger_rate: 0.05, thirst_rate: 0.05,
        energy_rest_gain: 0.5, energy_walk_cost: 0.03, energy_sprint_cost: 0.25,
        sprint_thirst_extra: 0.04, initial_hunger: [20.0, 50.0], initial_thirst: [10.0, 40.0],
      },
      predator: {
        walk_speed: 0.35, sprint_speed: 0.95, vision: 18.0, hunger_rate: 0.04, thirst_rate: 0.05,
        energy_rest_gain: 0.5, energy_walk_cost: 0.05, energy_sprint_cost: 0.5,
        sprint_thirst_extra: 0.05, initial_hunger: [45.0, 55.0], initial_thirst: [10.0, 30.0],
      },
    },
    metabolism: {
      starving_threshold: 100.0, starvation_damage: 0.2, dehydration_damage: 0.25,
      exhaustion_damage: 0.3, health_regen: 0.05, min_sprint_energy: 5.0, eat_rate: 0.5,
      hunger_per_food: 2.0, drink_rate: 3.0,
    },
    combat: {
      attack_range: 1.8, attack_cooldown: 6, attack_energy_cost: 2.0, damage: 50.0,
      hit_chance_vs_walking: 0.75, hit_chance_vs_sprinting: 0.45, kill_hunger_reduction: 60.0,
      kill_energy_gain: 20.0, give_up_ignore_ticks: 30,
    },
    reproduction: null,
  };

  // configs/world/map_b.yaml (extends default)
  const MAP_B = {
    map: {
      name: "map_b", plants: { count: 6 },
      waters: [{ pos: [48.0, 50.0], radius: 3.5 }, { pos: [12.0, 12.0], radius: 3.0 }],
    },
  };

  // configs/world/ecosystem.yaml (extends default)
  const ECOSYSTEM = {
    map: { name: "ecosystem", plants: { count: 12, regrow_per_tick: 0.06 } },
    population: { herbivore: 12, predator: 2 },
    reproduction: {
      prune_dead_after: 50,
      herbivore: {
        min_age: 300, cooldown: 350, max_hunger: 50.0, max_thirst: 60.0, min_energy: 40.0,
        min_health: 60.0, chance: 0.015, energy_cost: 25.0, hunger_cost: 20.0,
        max_population: 50, max_age: 4000,
        offspring_hunger: 30.0, offspring_thirst: 30.0, offspring_energy: 60.0,
      },
      predator: {
        min_age: 500, cooldown: 1000, max_hunger: 40.0, max_thirst: 60.0, min_energy: 40.0,
        min_health: 60.0, chance: 0.004, energy_cost: 30.0, hunger_cost: 25.0,
        max_population: 4, max_age: 5000,
        offspring_hunger: 30.0, offspring_thirst: 30.0, offspring_energy: 60.0,
      },
    },
  };

  // configs/policies/rule_based.yaml
  const RULES = {
    predator: {
      thirst_go_water: 70.0, thirst_done: 15.0, energy_rest: 20.0, energy_rested: 60.0,
      hunger_rest: 30.0, give_up_chase_ticks: 80, chase_distance: 10.0,
    },
    herbivore: {
      flee_distance: 8.0, flee_release_multiplier: 1.5, thirst_go_water: 60.0, thirst_done: 15.0,
      hunger_go_food: 50.0, hunger_done: 15.0, energy_rest: 20.0, energy_rested: 60.0,
    },
  };

  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  function deepMerge(base, over) {
    const out = clone(base);
    for (const k of Object.keys(over)) {
      const v = over[k];
      if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object"
          && !Array.isArray(out[k])) {
        out[k] = deepMerge(out[k], v);
      } else {
        out[k] = clone(v);
      }
    }
    return out;
  }

  // Python round(): banker's rounding (matters for x.5 only)
  function pyRound(x) {
    const f = Math.floor(x), d = x - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
  }

  /**
   * name: "map_a" | "map_b" | "ecosystem". opts.resourceScale scales plant count & regrowth
   * exactly like training/evaluation/evaluate.py --resource-scale. opts.herbivores /
   * opts.predators override the starting population.
   */
  function makeConfig(name, opts) {
    opts = opts || {};
    let cfg = clone(DEFAULT);
    if (name === "map_b") cfg = deepMerge(cfg, MAP_B);
    else if (name === "ecosystem") cfg = deepMerge(cfg, ECOSYSTEM);
    const s = opts.resourceScale;
    if (s && s !== 1) {
      cfg.map.plants.count = Math.max(1, pyRound(cfg.map.plants.count * s));
      cfg.map.plants.regrow_per_tick = cfg.map.plants.regrow_per_tick * s;
    }
    if (opts.herbivores != null) cfg.population.herbivore = opts.herbivores;
    if (opts.predators != null) cfg.population.predator = opts.predators;
    return cfg;
  }

  // --------------------------------------------------------------------- rng
  // mulberry32 seeded from (seed, stream). Normal via Box-Muller, two uniforms per draw.
  function hash32(a, b) {
    let h = (Math.imul(a ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(b + 0x7f4a7c15, 0xc2b2ae35)) >>> 0;
    h ^= h >>> 16; h = Math.imul(h, 0x7feb352d) >>> 0;
    h ^= h >>> 15; h = Math.imul(h, 0x846ca68b) >>> 0;
    h ^= h >>> 16;
    return h >>> 0;
  }

  class Rng {
    constructor(seed, stream) { this.state = hash32(seed >>> 0, stream >>> 0); }
    random() {
      let t = (this.state = (this.state + 0x6d2b79f5) >>> 0);
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
    uniform(lo, hi) { return lo + (hi - lo) * this.random(); }
    normal(mu, sigma) {
      const u1 = 1.0 - this.random(), u2 = this.random();
      return mu + sigma * Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
    }
  }

  // ----------------------------------------------------------------- helpers
  function hyp(x, z) { return Math.sqrt(x * x + z * z); }
  function dist(a, b) { return hyp(a[0] - b[0], a[1] - b[1]); }
  function unit(x, z) {
    const n = hyp(x, z);
    return n < 1e-9 ? [0, 0] : [x / n, z / n];
  }
  function cmpStr(a, b) { return a < b ? -1 : a > b ? 1 : 0; }

  const PRED_ACTIONS = ["SEARCH", "APPROACH", "CHASE", "ATTACK", "GO_TO_WATER", "REST", "GIVE_UP"];
  const HERB_ACTIONS = ["WANDER", "FLEE", "GO_TO_FOOD", "GO_TO_WATER", "REST"];
  const PA = { SEARCH: 0, APPROACH: 1, CHASE: 2, ATTACK: 3, GO_TO_WATER: 4, REST: 5, GIVE_UP: 6 };
  const HA = { WANDER: 0, FLEE: 1, GO_TO_FOOD: 2, GO_TO_WATER: 3, REST: 4 };
  const DEATH_CAUSES = ["predation", "starvation", "dehydration", "exhaustion", "old_age"];

  const MIN_EDIBLE_FOOD = 5.0;
  const WAYPOINT_REACHED = 1.0;
  const BORDER_MARGIN = 6.0;
  const ROCK_CLEARANCE = 0.3;
  const MAX_TRIES = 500;

  function pad3(n) { return String(n).padStart(3, "0"); }

  function makeDino(id, species, pos, extra) {
    return Object.assign({
      id, species, pos: [pos[0], pos[1]], vel: [0, 0], health: 100, energy: 100, hunger: 0,
      thirst: 0, age: 0, action: "NONE", target: null, alive: true, cooldown: 0, chase: 0,
      ignored: null, ignoreUntil: -1, waypoint: null, sprinting: false, deathCause: null,
      generation: 0, parent: null, breedCooldown: 0, deathTick: null,
    }, extra || {});
  }

  // ------------------------------------------------------------------ mapgen
  function freePoint(rng, size, margin, blockers, clearance) {
    for (let i = 0; i < MAX_TRIES; i++) {
      const p = [rng.uniform(margin, size - margin), rng.uniform(margin, size - margin)];
      let ok = true;
      for (const [c, r] of blockers) {
        if (dist(p, c) < r + clearance) { ok = false; break; }
      }
      if (ok) return p;
    }
    throw new Error("could not place object; map too crowded");
  }

  function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi); }

  function generateMap(cfg, rng) {
    const m = cfg.map;
    const waters = m.waters.map((w, i) => ({ id: "water-" + pad3(i), pos: w.pos.slice(), radius: w.radius }));
    const blockers = waters.map((w) => [w.pos, w.radius]);
    const rocks = [];
    for (let i = 0; i < m.rocks.count; i++) {
      const radius = rng.uniform(m.rocks.radius_min, m.rocks.radius_max);
      const pos = freePoint(rng, m.size, radius + 2.0, blockers, radius + 3.0);
      rocks.push({ id: "rock-" + pad3(i), pos, radius });
      blockers.push([pos, radius]);
    }
    const plants = [];
    for (let i = 0; i < m.plants.count; i++) {
      const pos = freePoint(rng, m.size, 4.0, blockers, m.plants.radius + 1.0);
      const food = rng.uniform(0.5, 1.0) * m.plants.max_food;
      plants.push({
        id: "plant-" + pad3(i), pos, radius: m.plants.radius, food,
        max: m.plants.max_food, regrow: m.plants.regrow_per_tick,
      });
      blockers.push([pos, m.plants.radius]);
    }
    const rockBlockers = rocks.map((r) => [r.pos, r.radius]);
    const pop = cfg.population;
    const herdCenter = freePoint(rng, m.size, 12.0, rockBlockers, 4.0);
    const dinos = [];
    for (let i = 0; i < pop.herbivore; i++) {
      let pos = null;
      for (let t = 0; t < MAX_TRIES; t++) {
        const ox = rng.normal(0.0, pop.herd_spread / 2), oz = rng.normal(0.0, pop.herd_spread / 2);
        pos = [clamp(herdCenter[0] + ox, 1.0, m.size - 1.0), clamp(herdCenter[1] + oz, 1.0, m.size - 1.0)];
        if (rockBlockers.every(([c, r]) => dist(pos, c) >= r + 0.5)) break;
      }
      dinos.push(spawn(cfg, rng, "herbivore-" + pad3(i), "herbivore", pos));
    }
    for (let i = 0; i < pop.predator; i++) {
      let pos = null;
      for (let t = 0; t < MAX_TRIES; t++) {
        const cand = freePoint(rng, m.size, 2.0, rockBlockers, 1.0);
        if (dist(cand, herdCenter) >= pop.predator_min_distance) { pos = cand; break; }
      }
      if (pos === null) throw new Error("could not place predator far enough from herd");
      dinos.push(spawn(cfg, rng, "predator-" + pad3(i), "predator", pos));
    }
    return { plants, waters, rocks, dinos };
  }

  function spawn(cfg, rng, id, species, pos) {
    const sp = cfg.species[species];
    const hunger = rng.uniform(sp.initial_hunger[0], sp.initial_hunger[1]);
    const thirst = rng.uniform(sp.initial_thirst[0], sp.initial_thirst[1]);
    return makeDino(id, species, pos, { hunger, thirst });
  }

  // ------------------------------------------------------------------- world
  class World {
    /** rngFactory(stream) lets tests inject generators; stream 0 layout, 1 move, 2 combat, 3 repro */
    constructor(cfg, seed, rngFactory) {
      this.cfg = cfg;
      this.seed = seed;
      const mk = rngFactory || ((s) => new Rng(seed, s));
      const layout = mk(0);
      this.moveRng = mk(1);
      this.combatRng = mk(2);
      this.reproRng = mk(3);
      const gen = generateMap(cfg, layout);
      this.plants = gen.plants;
      this.waters = gen.waters;
      this.rocks = gen.rocks;
      this.rockShapes = this.rocks.map((r) => [r.pos[0], r.pos[1], r.radius + ROCK_CLEARANCE]);
      gen.dinos.sort((a, b) => cmpStr(a.id, b.id));
      this.dinos = new Map(gen.dinos.map((d) => [d.id, d]));
      this.spawned = { herbivore: 0, predator: 0 };
      for (const d of gen.dinos) this.spawned[d.species]++;
      this.tick = 0;
      this.isNight = false;
      this.events = [];
      this.updateDayNight();
      this.updateTargets();
    }

    get size() { return this.cfg.map.size; }

    alive(species) {
      const out = [];
      for (const d of this.dinos.values()) {
        if (d.alive && (species == null || d.species === species)) out.push(d);
      }
      return out;
    }

    vision(d) {
      const v = this.cfg.species[d.species].vision;
      return this.isNight ? v * this.cfg.time.night_vision_multiplier : v;
    }

    nearestWater(pos) {
      let best = null, bestKey = Infinity;
      for (const w of this.waters) {
        const k = dist(pos, w.pos) - w.radius;
        if (k < bestKey || (k === bestKey && w.id < best.id)) { best = w; bestKey = k; }
      }
      return [best, Math.max(0.0, dist(pos, best.pos) - best.radius)];
    }

    nearestFood(pos) {
      let best = null, bestD = Infinity;
      for (const p of this.plants) {
        if (p.food < MIN_EDIBLE_FOOD) continue;
        const d = dist(pos, p.pos);
        if (d < bestD || (d === bestD && p.id < best.id)) { best = p; bestD = d; }
      }
      return best;
    }

    nearestVisible(dino, species) {
      const vision = this.vision(dino);
      let best = null, bestD = Infinity;
      for (const o of this.alive(species)) {
        const d = dist(dino.pos, o.pos);
        if (d > vision) continue;
        if (d < bestD || (d === bestD && o.id < best.id)) { best = o; bestD = d; }
      }
      return best;
    }

    herdCenter() {
      const herd = this.alive("herbivore");
      if (!herd.length) return [this.size / 2, this.size / 2];
      let x = 0, z = 0;
      for (const h of herd) { x += h.pos[0]; z += h.pos[1]; }
      return [x / herd.length, z / herd.length];
    }

    get done() {
      if (this.cfg.reproduction) return this.alive().length === 0;
      return this.alive("predator").length === 0 || this.alive("herbivore").length === 0;
    }

    /** actions: Map|object agent id -> action int; missing = REST */
    step(actions) {
      const get = actions instanceof Map ? (k) => actions.get(k) : (k) => actions[k];
      this.events = [];
      const decided = [];
      for (const d of this.alive()) {
        const a = get(d.id);
        const rest = d.species === "predator" ? PA.REST : HA.REST;
        decided.push([d, a == null ? rest : a]);
      }
      for (const [d, a] of decided) this.applyDecision(d, a);
      for (const [d, a] of decided) this.move(d, a);
      this.resolveAttacks(decided);
      this.resolveFeeding(decided);
      for (const [d, a] of decided) {
        if (!d.alive) continue;
        const sp = this.cfg.species[d.species];
        const resting = d.species === "predator" ? a === PA.REST : a === HA.REST;
        const moved = hyp(d.vel[0], d.vel[1]) > 1e-9;
        const cause = applyMetabolism(d, sp, this.cfg.metabolism, resting, moved);
        if (cause !== null) this.kill(d, cause);
        else d.age += 1;
        d.cooldown = Math.max(0, d.cooldown - 1);
      }
      for (const p of this.plants) p.food = Math.min(p.max, p.food + p.regrow);
      if (this.cfg.reproduction) this.lifeCycle();
      this.tick += 1;
      this.updateDayNight();
      this.updateTargets();
      return this.events;
    }

    applyDecision(d, a) {
      if (d.species !== "predator") { d.action = HERB_ACTIONS[a]; return; }
      d.action = PRED_ACTIONS[a];
      if (a === PA.GIVE_UP) {
        if (d.target !== null) {
          this.emit("give_up", d.id, d.target);
          d.ignored = d.target;
          d.ignoreUntil = this.tick + this.cfg.combat.give_up_ignore_ticks;
        }
        d.target = null;
        d.chase = 0;
      } else if ((a === PA.APPROACH || a === PA.CHASE || a === PA.ATTACK) && d.target !== null) {
        d.chase += 1;
      } else {
        d.chase = 0;
      }
    }

    move(d, a) {
      const sp = this.cfg.species[d.species];
      const canSprint = d.energy >= this.cfg.metabolism.min_sprint_energy;
      let goal = null, direction = null, speed = 0.0, sprint = false;
      if (d.species === "predator") {
        const target = d.target ? this.dinos.get(d.target) || null : null;
        if (a === PA.SEARCH || (target === null && (a === PA.APPROACH || a === PA.CHASE))) {
          goal = this.wanderGoal(d); speed = sp.walk_speed;
        } else if (a === PA.APPROACH) {
          goal = target.pos; speed = sp.walk_speed;
        } else if (a === PA.CHASE) {
          sprint = canSprint;
          goal = target.pos; speed = sprint ? sp.sprint_speed : sp.walk_speed;
        } else if (a === PA.ATTACK && target !== null) {
          if (dist(d.pos, target.pos) > this.cfg.combat.attack_range * 0.8) {
            goal = target.pos; speed = sp.walk_speed;
          }
        } else if (a === PA.GO_TO_WATER) {
          goal = this.waterGoal(d); speed = sp.walk_speed;
        }
      } else {
        if (a === HA.WANDER) {
          goal = this.wanderGoal(d); speed = sp.walk_speed;
        } else if (a === HA.FLEE) {
          const threat = this.nearestVisible(d, "predator");
          if (threat !== null) {
            direction = this.fleeDirection(d, threat);
            sprint = canSprint;
            speed = sprint ? sp.sprint_speed : sp.walk_speed;
          }
        } else if (a === HA.GO_TO_FOOD) {
          const plant = this.nearestFood(d.pos);
          if (plant !== null && dist(d.pos, plant.pos) > plant.radius * 0.5) {
            goal = plant.pos; speed = sp.walk_speed;
          }
        } else if (a === HA.GO_TO_WATER) {
          goal = this.waterGoal(d); speed = sp.walk_speed;
        }
      }
      const ox = d.pos[0], oz = d.pos[1];
      let x = ox, z = oz;
      if (goal !== null) {
        const dx = goal[0] - x, dz = goal[1] - z;
        const dd = hyp(dx, dz);
        if (dd > 1e-9) {
          const st = Math.min(speed, dd);
          x += (dx / dd) * st;
          z += (dz / dd) * st;
        }
      } else if (direction !== null) {
        x += direction[0] * speed;
        z += direction[1] * speed;
      }
      [x, z] = this.resolveCollisions(x, z);
      const vx = x - ox, vz = z - oz;
      d.vel = [vx, vz];
      d.pos = [x, z];
      d.sprinting = sprint && hyp(vx, vz) > sp.walk_speed + 1e-9;
    }

    wanderGoal(d) {
      if (d.waypoint === null || dist(d.pos, d.waypoint) < WAYPOINT_REACHED) {
        let wp;
        if (d.species === "herbivore") {
          const spread = this.cfg.population.herd_spread;
          const c = this.herdCenter();
          const ux = this.moveRng.uniform(-spread, spread), uz = this.moveRng.uniform(-spread, spread);
          wp = [c[0] + ux, c[1] + uz];
        } else {
          wp = [this.moveRng.uniform(2.0, this.size - 2.0), this.moveRng.uniform(2.0, this.size - 2.0)];
        }
        d.waypoint = [clamp(wp[0], 1.0, this.size - 1.0), clamp(wp[1], 1.0, this.size - 1.0)];
      }
      return d.waypoint;
    }

    waterGoal(d) {
      const [water] = this.nearestWater(d.pos);
      if (dist(d.pos, water.pos) < water.radius * 0.7) return null;
      return water.pos;
    }

    fleeDirection(d, threat) {
      const away = unit(d.pos[0] - threat.pos[0], d.pos[1] - threat.pos[1]);
      const pull = [0, 0];
      for (let ax = 0; ax < 2; ax++) {
        if (d.pos[ax] < BORDER_MARGIN) pull[ax] = 1.0;
        else if (d.pos[ax] > this.size - BORDER_MARGIN) pull[ax] = -1.0;
      }
      const u = unit(away[0] + pull[0], away[1] + pull[1]);
      if (u[0] !== 0 || u[1] !== 0) return u;
      return unit(this.size / 2 - d.pos[0], this.size / 2 - d.pos[1]);
    }

    resolveCollisions(x, z) {
      for (const [rx, rz, gap] of this.rockShapes) {
        let dx = x - rx, dz = z - rz;
        const d2 = dx * dx + dz * dz;
        if (d2 < gap * gap) {
          let d = Math.sqrt(d2);
          if (d < 1e-9) { dx = 1.0; dz = 0.0; d = 1.0; }
          x = rx + (dx / d) * gap;
          z = rz + (dz / d) * gap;
        }
      }
      const s = this.size;
      return [Math.min(Math.max(x, 0.0), s), Math.min(Math.max(z, 0.0), s)];
    }

    resolveAttacks(decided) {
      const c = this.cfg.combat;
      for (const [att, a] of decided) {
        if (att.species !== "predator" || a !== PA.ATTACK) continue;
        const target = att.target ? this.dinos.get(att.target) || null : null;
        const tid = target ? target.id : null;
        // combat/attack.py resolve_attack
        let outcome;
        if (target === null || !target.alive) outcome = "no_target";
        else if (att.cooldown > 0) outcome = "on_cooldown";
        else if (dist(att.pos, target.pos) > c.attack_range) outcome = "out_of_range";
        else {
          att.cooldown = c.attack_cooldown;
          att.energy = Math.max(0.0, att.energy - c.attack_energy_cost);
          const chance = target.sprinting ? c.hit_chance_vs_sprinting : c.hit_chance_vs_walking;
          if (this.combatRng.random() >= chance) outcome = "miss";
          else {
            target.health = Math.max(0.0, target.health - c.damage);
            if (target.health > 0.0) outcome = "hit";
            else {
              att.hunger = Math.max(0.0, att.hunger - c.kill_hunger_reduction);
              att.energy = Math.min(100.0, att.energy + c.kill_energy_gain);
              outcome = "kill";
            }
          }
        }
        if (outcome === "no_target" || outcome === "on_cooldown" || outcome === "out_of_range") {
          this.emit("attack_invalid", att.id, tid, { reason: outcome });
        } else if (outcome === "miss") {
          this.emit("attack_miss", att.id, tid);
        } else {
          this.emit("attack_hit", att.id, tid, { damage: c.damage });
          if (outcome === "kill") {
            this.emit("kill", att.id, tid);
            this.kill(target, "predation", att.id);
          }
        }
      }
    }

    resolveFeeding(decided) {
      const met = this.cfg.metabolism;
      for (const [d, a] of decided) {
        if (!d.alive) continue;
        if (d.species === "herbivore" && a === HA.GO_TO_FOOD) {
          for (const p of this.plants) {
            if (p.food > 0 && dist(d.pos, p.pos) <= p.radius) {
              const eaten = Math.min(met.eat_rate, p.food, d.hunger / met.hunger_per_food);
              if (eaten > 0) {
                p.food -= eaten;
                d.hunger -= eaten * met.hunger_per_food;
                this.emit("eat", d.id, p.id, { amount: eaten });
              }
              break;
            }
          }
        }
        const water = d.species === "predator" ? a === PA.GO_TO_WATER : a === HA.GO_TO_WATER;
        if (water) {
          const [w, edge] = this.nearestWater(d.pos);
          if (edge <= 0.0 && d.thirst > 0) {
            const before = d.thirst;
            d.thirst = Math.max(0.0, d.thirst - met.drink_rate);
            this.emit("drink", d.id, w.id, { amount: before - d.thirst });
          }
        }
      }
    }

    lifeCycle() {
      const repro = this.cfg.reproduction;
      for (const d of this.alive()) {
        const rc = repro[d.species];
        if (rc.max_age != null && d.age >= rc.max_age) this.kill(d, "old_age");
      }
      const living = { herbivore: this.alive("herbivore").length, predator: this.alive("predator").length };
      for (const parent of this.alive()) {
        const rc = repro[parent.species];
        if (parent.breedCooldown > 0) { parent.breedCooldown -= 1; continue; }
        if (!(parent.age >= rc.min_age && parent.hunger <= rc.max_hunger
          && parent.thirst <= rc.max_thirst && parent.energy >= rc.min_energy
          && parent.health >= rc.min_health && living[parent.species] < rc.max_population)) continue;
        if (this.reproRng.random() >= rc.chance) continue;
        const child = this.giveBirth(parent, rc);
        living[parent.species] += 1;
        this.emit("birth", parent.id, child.id);
      }
      const cutoff = this.tick - repro.prune_dead_after;
      for (const [id, d] of [...this.dinos]) {
        if (!d.alive && d.deathTick !== null && d.deathTick <= cutoff) this.dinos.delete(id);
      }
    }

    giveBirth(parent, rc) {
      parent.energy = Math.max(0.0, parent.energy - rc.energy_cost);
      parent.hunger = Math.min(100.0, parent.hunger + rc.hunger_cost);
      parent.breedCooldown = rc.cooldown;
      const ox = this.reproRng.normal(0.0, 1.0), oz = this.reproRng.normal(0.0, 1.0);
      const [x, z] = this.resolveCollisions(parent.pos[0] + ox, parent.pos[1] + oz);
      const n = this.spawned[parent.species]++;
      const child = makeDino(parent.species + "-" + pad3(n), parent.species, [x, z], {
        energy: rc.offspring_energy, hunger: rc.offspring_hunger, thirst: rc.offspring_thirst,
        generation: parent.generation + 1, parent: parent.id,
      });
      this.dinos.set(child.id, child);
      return child;
    }

    kill(d, cause, killer) {
      d.alive = false;
      d.deathTick = this.tick;
      d.deathCause = cause;
      d.vel = [0, 0];
      d.target = null;
      this.emit("death", d.id, killer || null, { cause });
    }

    updateDayNight() {
      const t = this.cfg.time;
      const phase = this.tick % t.day_length;
      this.isNight = phase >= t.day_length * (1.0 - t.night_fraction);
    }

    updateTargets() {
      const herd = this.alive("herbivore");
      for (const d of this.alive("predator")) {
        const vision = this.vision(d);
        let best = null, bestD = Infinity, keep = false;
        for (const h of herd) {
          const dd = dist(d.pos, h.pos);
          if (dd > vision) continue;
          if (h.id === d.ignored && this.tick < d.ignoreUntil) continue;
          if (h.id === d.target) { keep = true; break; }
          if (dd < bestD || (dd === bestD && h.id < best.id)) { best = h; bestD = dd; }
        }
        if (keep) continue;
        const newId = best ? best.id : null;
        if (newId !== d.target) d.chase = 0;
        d.target = newId;
      }
    }

    emit(kind, agent, target, data) {
      this.events.push({ tick: this.tick, kind, agent, target: target == null ? null : target, data: data || {} });
    }

    snapshot() {
      return {
        tick: this.tick,
        dinos: [...this.dinos.values()].map((d) => ({
          id: d.id, alive: d.alive, pos: d.pos, health: d.health, energy: d.energy,
          hunger: d.hunger, thirst: d.thirst, action: d.action, target: d.target,
        })),
        plants: this.plants.map((p) => p.food),
      };
    }
  }

  // core/metabolism.py
  function applyMetabolism(d, sp, cfg, resting, moved) {
    d.hunger = Math.min(100.0, d.hunger + sp.hunger_rate);
    d.thirst = Math.min(100.0, d.thirst + sp.thirst_rate + (d.sprinting ? sp.sprint_thirst_extra : 0.0));
    if (resting) d.energy += sp.energy_rest_gain;
    else if (d.sprinting) d.energy -= sp.energy_sprint_cost;
    else if (moved) d.energy -= sp.energy_walk_cost;
    d.energy = Math.min(100.0, Math.max(0.0, d.energy));
    const dmg = [];
    if (d.hunger >= cfg.starving_threshold) dmg.push(["starvation", cfg.starvation_damage]);
    if (d.thirst >= cfg.starving_threshold) dmg.push(["dehydration", cfg.dehydration_damage]);
    if (d.energy <= 0.0) dmg.push(["exhaustion", cfg.exhaustion_damage]);
    if (dmg.length) {
      let s = 0; for (const [, v] of dmg) s += v;
      d.health -= s;
    } else if (d.hunger < 80.0 && d.thirst < 80.0) {
      d.health = Math.min(100.0, d.health + cfg.health_regen);
    }
    if (d.health <= 0.0) {
      d.health = 0.0;
      if (!dmg.length) return "exhaustion";
      let best = dmg[0];
      for (const x of dmg) if (x[1] > best[1]) best = x;  // ties: first (enum order)
      return best[0];
    }
    return null;
  }

  // -------------------------------------------------------------- perception
  // policies/observation.py predator_view
  const OBSTACLE_SENSE_RANGE = 5.0;
  const MAX_CHASE_TICKS = 80;

  function predatorView(world, id) {
    const me = world.dinos.get(id);
    const sp = world.cfg.species.predator;
    let target = me.target ? world.dinos.get(me.target) || null : null;
    if (target && !target.alive) target = null;
    const [water, edge] = world.nearestWater(me.pos);
    let gap = Infinity;
    for (const r of world.rocks) gap = Math.min(gap, dist(me.pos, r.pos) - r.radius);
    const obstacle = Math.max(0.0, 1.0 - Math.max(0.0, gap) / OBSTACLE_SENSE_RANGE);
    const prevIdx = PRED_ACTIONS.indexOf(me.action);
    return {
      energy: me.energy, hunger: me.hunger, thirst: me.thirst, health: me.health,
      speed: hyp(me.vel[0], me.vel[1]), sprintSpeed: sp.sprint_speed, vision: world.vision(me),
      targetId: target ? target.id : null,
      preyDistance: target ? dist(me.pos, target.pos) : null,
      preyAngle: target ? Math.atan2(target.pos[1] - me.pos[1], target.pos[0] - me.pos[0]) : null,
      preyRelVel: target ? [target.vel[0] - me.vel[0], target.vel[1] - me.vel[1]] : [0, 0],
      preyEnergy: target ? target.energy : null,
      waterEdge: edge,
      waterAngle: Math.atan2(water.pos[1] - me.pos[1], water.pos[0] - me.pos[0]),
      obstacle, chaseTicks: me.chase, cooldown: me.cooldown,
      maxCooldown: world.cfg.combat.attack_cooldown, attackRange: world.cfg.combat.attack_range,
      isNight: world.isNight, prev: prevIdx >= 0 ? prevIdx : null,
      diag: world.size * Math.SQRT2,
    };
  }

  // encode_predator_view -> 26-dim observation in [-1, 1]
  function encodeView(v) {
    const o = new Float64Array(26);
    o[0] = v.energy / 100; o[1] = v.hunger / 100; o[2] = v.thirst / 100; o[3] = v.health / 100;
    o[4] = v.speed / v.sprintSpeed;
    if (v.targetId !== null) {
      o[5] = 1.0;
      o[6] = v.preyDistance / v.vision;
      o[7] = Math.cos(v.preyAngle);
      o[8] = Math.sin(v.preyAngle);
      o[9] = v.preyRelVel[0] / v.sprintSpeed;
      o[10] = v.preyRelVel[1] / v.sprintSpeed;
      o[11] = v.preyEnergy / 100;
    } else {
      o[6] = 1.0;
    }
    o[12] = v.waterEdge / v.diag;
    o[13] = Math.cos(v.waterAngle);
    o[14] = Math.sin(v.waterAngle);
    o[15] = v.obstacle;
    o[16] = v.chaseTicks / MAX_CHASE_TICKS;
    o[17] = v.cooldown / Math.max(1, v.maxCooldown);
    o[18] = v.isNight ? 1.0 : 0.0;
    if (v.prev !== null) o[19 + v.prev] = 1.0;
    for (let i = 0; i < 26; i++) {
      o[i] = Math.fround(Math.min(1, Math.max(-1, o[i])));  // float32 like numpy
    }
    return o;
  }

  function herbivoreView(world, id) {
    const me = world.dinos.get(id);
    const threat = world.nearestVisible(me, "predator");
    return {
      energy: me.energy, hunger: me.hunger, thirst: me.thirst, health: me.health,
      predatorDistance: threat ? dist(me.pos, threat.pos) : null, action: me.action,
    };
  }

  // ---------------------------------------------------------------- policies
  // policies/rule_based.py
  class RuleBasedPredator {
    constructor(p) { this.p = p || RULES.predator; this.name = "rule"; }
    reset() {}
    act(world, id) {
      const v = predatorView(world, id), p = this.p, prev = v.prev;
      const drinking = prev === PA.GO_TO_WATER && v.thirst > p.thirst_done;
      if (v.thirst > p.thirst_go_water || drinking) return PA.GO_TO_WATER;
      const resting = prev === PA.REST && v.energy < p.energy_rested;
      if (v.energy < p.energy_rest || resting) return PA.REST;
      if (v.hunger < p.hunger_rest) return PA.REST;
      if (v.targetId === null) return PA.SEARCH;
      if (v.chaseTicks > p.give_up_chase_ticks) return PA.GIVE_UP;
      if (v.preyDistance <= v.attackRange && v.cooldown === 0) return PA.ATTACK;
      if (v.preyDistance <= p.chase_distance) return PA.CHASE;
      return PA.APPROACH;
    }
  }

  class RuleBasedHerbivore {
    constructor(p) { this.p = p || RULES.herbivore; this.name = "rule-herbivore"; }
    reset() {}
    act(world, id) {
      const v = herbivoreView(world, id), p = this.p, prev = v.action;
      if (v.predatorDistance !== null) {
        let limit = p.flee_distance;
        if (prev === "FLEE") limit *= p.flee_release_multiplier;
        if (v.predatorDistance <= limit) return HA.FLEE;
      }
      const drinking = prev === "GO_TO_WATER" && v.thirst > p.thirst_done;
      if (v.thirst > p.thirst_go_water || drinking) return HA.GO_TO_WATER;
      const eating = prev === "GO_TO_FOOD" && v.hunger > p.hunger_done;
      if (v.hunger > p.hunger_go_food || eating) return HA.GO_TO_FOOD;
      const resting = prev === "REST" && v.energy < p.energy_rested;
      if (v.energy < p.energy_rest || resting) return HA.REST;
      return HA.WANDER;
    }
  }

  // policies/random_policy.py
  class RandomPredator {
    constructor(seed) { this.name = "random"; this.reset(seed); }
    reset(seed) { this.rng = new Rng(seed == null ? 0 : seed, 99); }
    act() { return Math.floor(this.rng.random() * 7); }
  }

  // policies/mlp.py — *.policy.json ("paleosphere-mlp-v1"), argmax over logits
  class MlpPredator {
    constructor(data) {
      if (data.format !== "paleosphere-mlp-v1") throw new Error("unsupported weights format");
      if (data.obs_dim !== 26) throw new Error("weights expect obs_dim " + data.obs_dim);
      this.data = data;
      this.name = "ppo";
      this.act_fn = data.activation === "tanh" ? Math.tanh : (x) => Math.max(0, x);
      this.layers = data.layers.map((l) => ({
        w: l.weight.map((row) => Float64Array.from(row)), b: Float64Array.from(l.bias),
      }));
      this.lastLogits = null;
    }
    reset() {}
    logits(obs) {
      let x = obs;
      for (let li = 0; li < this.layers.length; li++) {
        const { w, b } = this.layers[li];
        const y = new Float64Array(b.length);
        for (let i = 0; i < b.length; i++) {
          const row = w[i];
          let s = b[i];
          for (let j = 0; j < row.length; j++) s += row[j] * x[j];
          y[i] = li < this.layers.length - 1 ? this.act_fn(s) : s;
        }
        x = y;
      }
      return x;
    }
    predict(obs) {
      const l = this.logits(obs);
      this.lastLogits = l;
      let best = 0;
      for (let i = 1; i < l.length; i++) if (l[i] > l[best]) best = i;
      return best;
    }
    act(world, id) { return this.predict(encodeView(predatorView(world, id))); }
  }

  // ------------------------------------------------------------- runner util
  /** Collect actions for every living dino (runner loop in logging/episode.py). */
  function decide(world, predPolicy, herbPolicy) {
    const actions = new Map();
    for (const d of world.alive()) {
      actions.set(d.id, (d.species === "predator" ? predPolicy : herbPolicy).act(world, d.id));
    }
    return actions;
  }

  /** Headless episode with the same summary metrics as logging/episode.py (first predator). */
  function runEpisode(cfg, seed, predPolicy, herbPolicy, maxTicks) {
    maxTicks = maxTicks || 2000;
    const world = new World(cfg, seed);
    predPolicy.reset(seed); herbPolicy.reset(seed);
    const pred = world.alive("predator")[0];
    const acts = {}; PRED_ACTIONS.forEach((a) => (acts[a] = 0));
    let kills = 0, hits = 0, misses = 0, invalid = 0, giveUps = 0, energySpent = 0, survival = 0;
    let thirstSum = 0;
    while (world.tick < maxTicks && !world.done) {
      const actions = decide(world, predPolicy, herbPolicy);
      const before = pred.energy;
      const events = world.step(actions);
      if (actions.has(pred.id)) {
        acts[PRED_ACTIONS[actions.get(pred.id)]]++;
        energySpent += Math.max(0, before - pred.energy);
        if (pred.alive) { survival++; thirstSum += pred.thirst; }
      }
      for (const e of events) {
        if (e.kind === "kill") kills++;
        if (e.agent !== pred.id) continue;
        if (e.kind === "attack_hit") hits++;
        else if (e.kind === "attack_miss") misses++;
        else if (e.kind === "attack_invalid") invalid++;
        else if (e.kind === "give_up") giveUps++;
      }
    }
    const valid = hits + misses;
    return {
      seed, ticks: world.tick, predatorAlive: pred.alive, predatorDeathCause: pred.deathCause,
      survival, kills, attackAttempts: valid + invalid, hits, invalid, giveUps,
      huntSuccess: valid ? kills / valid : 0, energySpent,
      energyPerKill: kills ? energySpent / kills : null,
      herbivoresAlive: world.alive("herbivore").length, meanThirst: thirstSum / Math.max(1, survival),
      actions: acts,
    };
  }

  const api = {
    DEFAULT, MAP_B, ECOSYSTEM, RULES, makeConfig, deepMerge, Rng, World, generateMap,
    applyMetabolism, predatorView, encodeView, herbivoreView, RuleBasedPredator,
    RuleBasedHerbivore, RandomPredator, MlpPredator, decide, runEpisode,
    PRED_ACTIONS, HERB_ACTIONS, PA, HA, DEATH_CAUSES, pyRound,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Paleo = api;
})(typeof window !== "undefined" ? window : globalThis);
