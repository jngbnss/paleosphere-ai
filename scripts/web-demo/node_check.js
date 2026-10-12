// Headless sanity check of pages/sim.js (no browser needed).
//   node scripts/web-demo/node_check.js [models/ppo-v2.fixture.json]
// 1. JS MLP vs the export fixture (SB3/ONNX/numpy actions) when a fixture is given
// 2. 20-seed episodes per policy on map_a / map_b (compare with analytics/reports/exp003)
// 3. ecosystem long runs (compare with analytics/reports/exp004 outcomes)
"use strict";
const fs = require("fs");
const path = require("path");
const P = require(path.join(__dirname, "..", "..", "pages", "sim.js"));

const weights = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "pages", "data", "ppo-v2.policy.json"), "utf8"));
const ppo = new P.MlpPredator(weights);
let failed = false;

if (process.argv[2]) {
  const fx = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  let same = 0;
  fx.obs.forEach((o, i) => { if (ppo.predict(Float64Array.from(o)) === fx.actions[i]) same++; });
  const rate = same / fx.obs.length;
  console.log(`MLP fixture: ${same}/${fx.obs.length} actions match SB3 (${(rate * 100).toFixed(2)}%)`);
  if (rate < 0.999) failed = true;
}

function mean(a) { return a.reduce((s, x) => s + x, 0) / a.length; }

const policies = {
  rule: () => new P.RuleBasedPredator(),
  ppo: () => ppo,
  random: () => new P.RandomPredator(0),
};
const t0 = Date.now();
let ticks = 0;
for (const map of ["map_a", "map_b"]) {
  for (const [name, mk] of Object.entries(policies)) {
    const eps = [];
    for (let s = 10000; s < 10020; s++) {
      const r = P.runEpisode(P.makeConfig(map), s, mk(), new P.RuleBasedHerbivore(), 2000);
      ticks += r.ticks;
      eps.push(r);
    }
    const valid = eps.filter((e) => e.attackAttempts > 0);
    const acts = {};
    for (const a of P.PRED_ACTIONS) acts[a] = mean(eps.map((e) => e.actions[a] / Math.max(1, e.ticks))).toFixed(2);
    console.log(
      `${map} ${name.padEnd(6)} kills ${mean(eps.map((e) => e.kills)).toFixed(2)}  ` +
      `death rate ${mean(eps.map((e) => (e.predatorAlive ? 0 : 1))).toFixed(2)}  ` +
      `invalid rate ${mean(valid.map((e) => e.invalid / e.attackAttempts)).toFixed(2)}  ` +
      `causes ${JSON.stringify(eps.filter((e) => !e.predatorAlive).reduce((c, e) => ((c[e.predatorDeathCause] = (c[e.predatorDeathCause] || 0) + 1), c), {}))}  ` +
      `acts ${JSON.stringify(acts)}`
    );
  }
}
console.log(`episodes: ${ticks} ticks in ${Date.now() - t0} ms`);

const out = { coexist: 0, herbivores_only: 0, extinct: 0 };
for (let s = 0; s < 10; s++) {
  const w = new P.World(P.makeConfig("ecosystem"), s);
  const pr = new P.RuleBasedPredator(), hb = new P.RuleBasedHerbivore();
  while (w.tick < 20000 && !w.done) w.step(P.decide(w, pr, hb));
  const h = w.alive("herbivore").length, p = w.alive("predator").length;
  out[h && p ? "coexist" : h ? "herbivores_only" : "extinct"]++;
}
console.log("ecosystem 10 seeds x 20000 ticks (rule):", JSON.stringify(out), `(${Date.now() - t0} ms total)`);
process.exit(failed ? 1 : 0);
