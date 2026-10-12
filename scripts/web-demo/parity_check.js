// Compare pages/sim.js against Python trajectories from parity_dump.py (same RNG streams).
//   node scripts/web-demo/parity_check.js parity.json
"use strict";
const fs = require("fs");
const path = require("path");
const P = require(path.join(__dirname, "..", "..", "pages", "sim.js"));

const runs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
let failures = 0;

function state(w) {
  const r = (x, n) => Math.round(x * 10 ** n) / 10 ** n;
  return {
    tick: w.tick,
    dinos: [...w.dinos.values()].map((d) => [
      d.id, d.alive ? 1 : 0, r(d.pos[0], 6), r(d.pos[1], 6), r(d.health, 4), r(d.energy, 4),
      r(d.hunger, 4), r(d.thirst, 4), d.action, d.target,
    ]),
    plants: w.plants.map((p) => r(p.food, 4)),
  };
}

for (const run of runs) {
  const cfg = P.makeConfig(run.config, { resourceScale: run.resource_scale });
  const w = new P.World(cfg, run.seed);
  const pred = new P.RuleBasedPredator(), herb = new P.RuleBasedHerbivore();
  const events = { kill: 0, birth: 0, death: 0 };
  const js = [state(w)];
  while (w.tick < run.ticks && !w.done) {
    for (const e of w.step(P.decide(w, pred, herb))) if (e.kind in events) events[e.kind]++;
    if (w.tick % run.every === 0) js.push(state(w));
  }
  let firstDiff = null, maxPos = 0;
  for (let i = 0; i < Math.min(js.length, run.states.length); i++) {
    const a = js[i], b = run.states[i];
    const sa = JSON.stringify([a.dinos.map((d) => [d[0], d[1], d[8], d[9]]), a.dinos.length]);
    const sb = JSON.stringify([b.dinos.map((d) => [d[0], d[1], d[8], d[9]]), b.dinos.length]);
    if (sa !== sb && firstDiff === null) firstDiff = a.tick;
    if (firstDiff === null) {
      for (let k = 0; k < a.dinos.length; k++) {
        for (const j of [2, 3, 4, 5, 6, 7]) maxPos = Math.max(maxPos, Math.abs(a.dinos[k][j] - b.dinos[k][j]));
      }
      for (let k = 0; k < a.plants.length; k++) maxPos = Math.max(maxPos, Math.abs(a.plants[k] - b.plants[k]));
    }
  }
  const sameLen = js.length === run.states.length && w.tick === run.ticks;
  const ok = firstDiff === null && sameLen && JSON.stringify(events) === JSON.stringify(run.events);
  if (!ok) failures++;
  console.log(
    `${ok ? "OK  " : "DIFF"} ${run.config} seed=${run.seed} res=${run.resource_scale} ticks js/py=${w.tick}/${run.ticks} ` +
    `events js=${JSON.stringify(events)} py=${JSON.stringify(run.events)} ` +
    `first discrete diff @tick ${firstDiff} max numeric diff ${maxPos.toExponential(2)}`
  );
}
process.exit(failures ? 1 : 0);
