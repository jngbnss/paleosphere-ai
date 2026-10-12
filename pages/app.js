/* Live tab: runs pages/sim.js worlds on canvas, with controls, charts and quick evaluation. */
(function () {
  "use strict";
  const P = window.Paleo;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const $ = (id) => document.getElementById(id);
  const fmt = (n) => n.toLocaleString("ko-KR");

  const POLICY_LABEL = { rule: "규칙 기반", ppo: "PPO (학습)", random: "무작위" };
  const POLICY_COLOR = { rule: "--rule", ppo: "--ppo", random: "--rand" };
  const ACTION_KO = {
    SEARCH: "탐색", APPROACH: "접근", CHASE: "질주 추격", ATTACK: "공격", GO_TO_WATER: "물 마시러",
    REST: "휴식", GIVE_UP: "포기", WANDER: "배회", FLEE: "도주", GO_TO_FOOD: "먹이로", NONE: "–",
  };
  const CAUSE_KO = { predation: "사냥당함", starvation: "굶주림", dehydration: "탈수", exhaustion: "탈진", old_age: "노화" };
  const TICKS_PER_SEC = 10; // 1x

  // Shared data promises (results.js uses window.PaleoData too)
  window.PaleoData = window.PaleoData || {
    results: fetch("data/results.json").then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
  };
  let ppoWeights = null, ppoError = null;
  const ppoReady = fetch("data/ppo-v2.policy.json")
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((d) => { ppoWeights = d; })
    .catch((e) => { ppoError = e; });

  const ui = {
    scenario: $("scenario"), res: $("res"), herb: $("herb"), pred: $("pred"), seed: $("seed"),
    play: $("play"), showVision: $("showVision"),
  };
  const state = { policy: "rule", speed: 4, running: false, sims: [], acc: 0, last: 0 };

  // ------------------------------------------------------------------ sims
  function makePolicy(key, seed) {
    if (key === "ppo") return new P.MlpPredator(ppoWeights);
    if (key === "random") return new P.RandomPredator(seed);
    return new P.RuleBasedPredator();
  }

  function config() {
    return P.makeConfig(ui.scenario.value, {
      resourceScale: parseFloat(ui.res.value),
      herbivores: parseInt(ui.herb.value, 10),
      predators: parseInt(ui.pred.value, 10),
    });
  }

  function maxTicks() { return ui.scenario.value === "ecosystem" ? 20000 : 2000; }

  function build() {
    const seed = Math.max(0, parseInt(ui.seed.value, 10) || 0);
    const keys = state.policy === "compare" ? ["rule", "ppo"] : [state.policy];
    const container = $("worlds");
    container.innerHTML = "";
    container.classList.toggle("two", keys.length === 2);
    state.sims = keys.map((key) => {
      const cfg = config();
      let world;
      try {
        world = new P.World(cfg, seed);
      } catch (e) {
        world = null;
      }
      const sim = {
        key, world, cfg, seed, pred: makePolicy(key, seed), herb: new P.RuleBasedHerbivore(),
        hist: [], kills: 0, births: 0, attacks: 0, invalid: 0, hits: 0, deaths: {},
        actions: Object.fromEntries(P.PRED_ACTIONS.map((a) => [a, 0])), ended: null,
        selected: null, fx: [], els: {},
      };
      sim.els = mountWorld(container, sim);
      if (!world) { sim.ended = "맵을 만들 수 없습니다 (개체가 너무 많음). 다른 seed를 써 보세요."; }
      else record(sim);
      return sim;
    });
    renderAll();
    updateCharts();
    $("log").innerHTML = "";
  }

  function mountWorld(container, sim) {
    const el = document.createElement("div");
    el.className = "world";
    el.innerHTML = `
      <div class="world-canvas"><canvas aria-label="시뮬레이션 화면 (${POLICY_LABEL[sim.key]})"></canvas>
        <div class="hud"><span class="tag-${sim.key}">${POLICY_LABEL[sim.key]} 포식자</span><span data-k="clock"></span></div>
        <div class="banner" hidden></div></div>
      <div class="side">
        <div class="stats">
          <div class="stat"><b data-k="herb">0</b><span>초식공룡</span></div>
          <div class="stat"><b data-k="pred">0</b><span>육식공룡</span></div>
          <div class="stat"><b data-k="kills">0</b><span>사냥 성공</span></div>
          <div class="stat"><b data-k="inv">–</b><span>무효 공격 비율</span></div>
        </div>
        <div class="inspect" data-k="inspect"><span class="hint" style="margin:0">공룡을 탭하면 상태가 보입니다.</span></div>
      </div>`;
    container.appendChild(el);
    const canvas = el.querySelector("canvas");
    const q = (k) => el.querySelector(`[data-k="${k}"]`);
    canvas.addEventListener("click", (e) => {
      if (!sim.world) return;
      const r = canvas.getBoundingClientRect();
      const s = sim.world.size;
      const x = ((e.clientX - r.left) / r.width) * s, z = ((e.clientY - r.top) / r.height) * s;
      let best = null, bd = 3.0;
      for (const d of sim.world.dinos.values()) {
        const dd = Math.hypot(d.pos[0] - x, d.pos[1] - z);
        if (dd < bd) { best = d; bd = dd; }
      }
      // keep the same selection in both compare worlds when ids match
      for (const other of state.sims) other.selected = best ? best.id : null;
      renderAll();
    });
    return {
      root: el, canvas, ctx: canvas.getContext("2d"), banner: el.querySelector(".banner"),
      clock: q("clock"), herb: q("herb"), pred: q("pred"), kills: q("kills"), inv: q("inv"), inspect: q("inspect"),
    };
  }

  function record(sim) {
    const w = sim.world;
    sim.hist.push([w.tick, w.alive("herbivore").length, w.alive("predator").length, sim.kills]);
    if (sim.hist.length > 900) sim.hist = sim.hist.filter((_, i) => i % 2 === 0 || i === sim.hist.length - 1);
  }

  function stepSim(sim) {
    if (sim.ended || !sim.world) return;
    const w = sim.world;
    const actions = P.decide(w, sim.pred, sim.herb);
    for (const d of w.alive("predator")) sim.actions[P.PRED_ACTIONS[actions.get(d.id)]]++;
    const evs = w.step(actions);
    for (const e of evs) {
      if (e.kind === "kill") {
        sim.kills++;
        const t = w.dinos.get(e.target);
        if (t) sim.fx.push({ x: t.pos[0], z: t.pos[1], age: 0, kind: "kill" });
        log(sim, `<b>사냥</b> ${short(e.agent)} → ${short(e.target)}`);
      } else if (e.kind === "attack_hit" || e.kind === "attack_miss") {
        sim.attacks++;
        if (e.kind === "attack_hit") sim.hits++;
        const t = w.dinos.get(e.target);
        if (t && e.kind === "attack_hit") sim.fx.push({ x: t.pos[0], z: t.pos[1], age: 0, kind: "hit" });
      } else if (e.kind === "attack_invalid") {
        sim.attacks++; sim.invalid++;
      } else if (e.kind === "death") {
        const c = e.data.cause;
        sim.deaths[c] = (sim.deaths[c] || 0) + 1;
        if (c !== "predation") log(sim, `<b>사망</b> ${short(e.agent)} (${CAUSE_KO[c] || c})`);
      } else if (e.kind === "birth") {
        sim.births++;
        if (sim.births <= 30 || sim.births % 10 === 0) log(sim, `<b>출생</b> ${short(e.target)} (부모 ${short(e.agent)})${sim.births > 30 ? ` · 누적 ${sim.births}` : ""}`);
      } else if (e.kind === "give_up") {
        log(sim, `<b>추격 포기</b> ${short(e.agent)}`, true);
      }
    }
    const every = sim.cfg.reproduction ? 50 : 10;
    if (w.tick % every === 0) record(sim);
    const limit = maxTicks();
    if (w.done || w.tick >= limit) {
      record(sim);
      const h = w.alive("herbivore").length, p = w.alive("predator").length;
      let why;
      if (w.tick >= limit) why = `${fmt(limit)} tick 도달`;
      else if (!p && !h) why = "모든 개체 사망";
      else if (!p) why = "포식자 전멸";
      else why = "초식공룡 전멸";
      sim.ended = `종료 · ${why} — 사냥 ${sim.kills}회, 초식 ${h} · 육식 ${p} 생존`;
      log(sim, `<b>종료</b> ${why}`);
    }
  }

  function short(id) {
    if (!id) return "?";
    const [sp, n] = id.split("-");
    return (sp === "predator" ? "육식" : "초식") + "#" + parseInt(n, 10);
  }

  let logCount = 0;
  function log(sim, html, minor) {
    if (minor && state.speed >= 16) return;
    const li = document.createElement("li");
    const who = state.sims.length > 1 ? `<span class="pill" style="background:${css(POLICY_COLOR[sim.key])};color:#fff">${sim.key === "ppo" ? "PPO" : "규칙"}</span> ` : "";
    li.innerHTML = `<span class="k">t=${fmt(sim.world.tick)}</span> ${who}${html}`;
    const ol = $("log");
    ol.prepend(li);
    if (++logCount % 20 === 0) while (ol.children.length > 120) ol.lastChild.remove();
  }

  // ----------------------------------------------------------------- render
  function renderWorld(sim) {
    const { canvas, ctx } = sim.els;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (!W || !H) return;
    if (canvas.width !== Math.round(W * dpr)) { canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = sim.world;
    ctx.fillStyle = css("--ground");
    ctx.fillRect(0, 0, W, H);
    if (!w) return;
    const k = W / w.size;
    const X = (v) => v * k;
    // subtle tiles
    ctx.fillStyle = css("--ground-2");
    for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) if ((i + j) % 2) ctx.fillRect(i * W / 8, j * H / 8, W / 8, H / 8);
    // water
    for (const wa of w.waters) {
      ctx.fillStyle = css("--water");
      ctx.beginPath(); ctx.arc(X(wa.pos[0]), X(wa.pos[1]), X(wa.radius), 0, 7); ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.45)"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(X(wa.pos[0]), X(wa.pos[1]), X(wa.radius) - 3, 0.3, 1.6); ctx.stroke();
    }
    // plants
    for (const p of w.plants) {
      const f = p.food / p.max;
      ctx.fillStyle = css("--plant");
      ctx.globalAlpha = 0.15 + 0.55 * f;
      ctx.beginPath(); ctx.arc(X(p.pos[0]), X(p.pos[1]), X(p.radius), 0, 7); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = css("--plant"); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(X(p.pos[0]), X(p.pos[1]), X(p.radius), -Math.PI / 2, -Math.PI / 2 + f * Math.PI * 2); ctx.stroke();
    }
    // rocks
    for (const r of w.rocks) {
      ctx.fillStyle = css("--rock");
      ctx.beginPath(); ctx.arc(X(r.pos[0]), X(r.pos[1]), X(r.radius), 0, 7); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,.18)";
      ctx.beginPath(); ctx.arc(X(r.pos[0]) - X(r.radius) * .3, X(r.pos[1]) - X(r.radius) * .3, X(r.radius) * .45, 0, 7); ctx.fill();
    }
    const show = ui.showVision.checked;
    const predCol = css("--pred"), herbCol = css("--herb");
    // vision + target lines
    if (show) {
      for (const d of w.alive("predator")) {
        ctx.strokeStyle = predCol; ctx.globalAlpha = 0.35; ctx.setLineDash([4, 5]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.arc(X(d.pos[0]), X(d.pos[1]), X(w.vision(d)), 0, 7); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha = 1;
        const t = d.target && w.dinos.get(d.target);
        if (t && t.alive) {
          ctx.strokeStyle = predCol; ctx.lineWidth = d.action === "CHASE" ? 2 : 1.2;
          ctx.globalAlpha = 0.8;
          ctx.beginPath(); ctx.moveTo(X(d.pos[0]), X(d.pos[1])); ctx.lineTo(X(t.pos[0]), X(t.pos[1])); ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }
    }
    // corpses
    for (const d of w.dinos.values()) {
      if (d.alive) continue;
      ctx.strokeStyle = "rgba(60,50,40,.55)"; ctx.lineWidth = 2;
      const x = X(d.pos[0]), z = X(d.pos[1]), s = Math.max(3, k * 0.6);
      ctx.beginPath(); ctx.moveTo(x - s, z - s); ctx.lineTo(x + s, z + s); ctx.moveTo(x + s, z - s); ctx.lineTo(x - s, z + s); ctx.stroke();
    }
    // herbivores
    const hr = Math.max(4, k * 0.85);
    for (const d of w.alive("herbivore")) {
      const x = X(d.pos[0]), z = X(d.pos[1]);
      ctx.fillStyle = herbCol; ctx.strokeStyle = "#fff"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, z, hr, 0, 7); ctx.fill(); ctx.stroke();
      if (d.action === "FLEE") {
        ctx.strokeStyle = herbCol; ctx.globalAlpha = .5;
        ctx.beginPath(); ctx.arc(x, z, hr + 3, 0, 7); ctx.stroke(); ctx.globalAlpha = 1;
      }
      if (d.health < 100) {
        ctx.fillStyle = "rgba(0,0,0,.35)"; ctx.fillRect(x - hr, z - hr - 5, hr * 2, 3);
        ctx.fillStyle = d.health > 50 ? herbCol : predCol; ctx.fillRect(x - hr, z - hr - 5, hr * 2 * d.health / 100, 3);
      }
    }
    // predators
    const pr = Math.max(7, k * 1.5);
    for (const d of w.alive("predator")) {
      const x = X(d.pos[0]), z = X(d.pos[1]);
      let ang = Math.atan2(d.vel[1], d.vel[0]);
      if (Math.hypot(d.vel[0], d.vel[1]) < 1e-6) ang = d._ang == null ? -Math.PI / 2 : d._ang;
      d._ang = ang;
      if (d.sprinting) {
        ctx.strokeStyle = predCol; ctx.globalAlpha = .45; ctx.lineWidth = 2;
        for (const o of [-4, 0, 4]) {
          ctx.beginPath();
          ctx.moveTo(x - Math.cos(ang) * pr * 1.1 + Math.sin(ang) * o, z - Math.sin(ang) * pr * 1.1 - Math.cos(ang) * o);
          ctx.lineTo(x - Math.cos(ang) * pr * 2 + Math.sin(ang) * o, z - Math.sin(ang) * pr * 2 - Math.cos(ang) * o);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
      }
      ctx.save(); ctx.translate(x, z); ctx.rotate(ang);
      ctx.fillStyle = predCol; ctx.strokeStyle = css(POLICY_COLOR[sim.key]); ctx.lineWidth = 2.5;
      ctx.beginPath(); ctx.moveTo(pr, 0); ctx.lineTo(-pr * .75, pr * .7); ctx.lineTo(-pr * .4, 0); ctx.lineTo(-pr * .75, -pr * .7); ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.restore();
    }
    // effects
    sim.fx = sim.fx.filter((f) => f.age < 24);
    for (const f of sim.fx) {
      const a = 1 - f.age / 24;
      ctx.strokeStyle = f.kind === "kill" ? predCol : "#fff"; ctx.globalAlpha = a; ctx.lineWidth = f.kind === "kill" ? 3 : 2;
      ctx.beginPath(); ctx.arc(X(f.x), X(f.z), (f.kind === "kill" ? 6 : 3) + f.age * 1.2, 0, 7); ctx.stroke();
      ctx.globalAlpha = 1;
      f.age++;
    }
    // selection
    const sel = sim.selected && w.dinos.get(sim.selected);
    if (sel) {
      ctx.strokeStyle = css("--ink"); ctx.lineWidth = 2; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.arc(X(sel.pos[0]), X(sel.pos[1]), (sel.species === "predator" ? pr : hr) + 6, 0, 7); ctx.stroke();
      ctx.setLineDash([]);
    }
    if (w.isNight) { ctx.fillStyle = css("--night"); ctx.fillRect(0, 0, W, H); }
  }

  function meter(label, v, color) {
    return `<div class="meter"><span>${label}</span><div class="bar"><i style="width:${Math.max(0, Math.min(100, v))}%;background:${color}"></i></div><em>${v.toFixed(0)}</em></div>`;
  }

  function renderSide(sim) {
    const e = sim.els, w = sim.world;
    if (!w) { e.banner.hidden = false; e.banner.textContent = sim.ended; return; }
    const day = w.cfg.time.day_length;
    e.clock.textContent = `t=${fmt(w.tick)} · ${w.isNight ? "밤 🌙" : "낮 ☀"} · ${Math.floor(w.tick / day) + 1}일차`;
    e.herb.textContent = w.alive("herbivore").length;
    e.pred.textContent = w.alive("predator").length;
    e.kills.textContent = sim.kills;
    e.inv.textContent = sim.attacks ? (sim.invalid / sim.attacks).toFixed(2) : "–";
    e.banner.hidden = !sim.ended;
    if (sim.ended) e.banner.textContent = sim.ended;
    const d = sim.selected && w.dinos.get(sim.selected);
    if (!d) {
      e.inspect.innerHTML = `<span class="hint" style="margin:0">공룡을 탭하면 상태가 보입니다.${sim.cfg.reproduction ? ` 출생 ${sim.births} · 사망 ${Object.values(sim.deaths).reduce((a, b) => a + b, 0)}` : ""}</span>`;
      return;
    }
    const sp = d.species === "predator" ? "육식공룡" : "초식공룡";
    let extra = "";
    if (d.species === "predator") {
      const t = d.target && w.dinos.get(d.target);
      extra = `<div class="hint" style="margin:4px 0 0">목표: ${t ? short(t.id) + ` · ${Math.hypot(t.pos[0] - d.pos[0], t.pos[1] - d.pos[1]).toFixed(1)}m` : "없음"} · 추격 ${d.chase} tick · 쿨다운 ${d.cooldown}</div>`;
    }
    e.inspect.innerHTML = `<h5>${short(d.id)} <span class="hint">${sp}${d.generation ? ` · ${d.generation}세대` : ""}</span></h5>
      ${d.alive ? `<div class="hint" style="margin:0 0 6px">행동: <b style="color:var(--ink)">${ACTION_KO[d.action] || d.action}</b> (${d.action})</div>` : `<div class="hint" style="margin:0 0 6px">사망 · ${CAUSE_KO[d.deathCause] || ""}</div>`}
      ${meter("체력", d.health, css("--herb"))}${meter("에너지", d.energy, css("--rule"))}${meter("배고픔", d.hunger, css("--ppo"))}${meter("갈증", d.thirst, css("--water"))}${extra}`;
  }

  function renderAll() {
    for (const s of state.sims) { renderWorld(s); renderSide(s); }
  }

  // ----------------------------------------------------------------- charts
  const popChart = window.Charts.lineChart($("popChart"), { height: 210, xLabel: "tick", yFmt: (y) => String(Math.round(y)) });
  function updateCharts() {
    const sims = state.sims;
    let series, legend;
    if (sims.length === 2) {
      $("popTitle").textContent = "초식공룡 생존 수 · 규칙 vs PPO (같은 seed)";
      series = sims.map((s) => ({ name: `초식 (${POLICY_LABEL[s.key]})`, color: css(POLICY_COLOR[s.key]), data: s.hist.map((h) => [h[0], h[1]]) }))
        .concat(sims.map((s) => ({ name: `누적 사냥 (${POLICY_LABEL[s.key]})`, color: css(POLICY_COLOR[s.key]), dash: [5, 4], width: 1.5, data: s.hist.map((h) => [h[0], h[3]]) })));
      legend = sims.map((s) => `<span><i style="background:${css(POLICY_COLOR[s.key])}"></i>${POLICY_LABEL[s.key]} — 실선 초식 수 · 점선 누적 사냥</span>`).join("");
    } else {
      const s = sims[0];
      $("popTitle").textContent = "개체수 (실시간)";
      series = [
        { name: "초식공룡", color: css("--herb"), data: s.hist.map((h) => [h[0], h[1]]) },
        { name: "육식공룡", color: css("--pred"), data: s.hist.map((h) => [h[0], h[2]]) },
        { name: "누적 사냥", color: css("--muted"), dash: [5, 4], width: 1.5, data: s.hist.map((h) => [h[0], h[3]]) },
      ];
      legend = `<span><i style="background:${css("--herb")}"></i>초식공룡</span><span><i style="background:${css("--pred")}"></i>육식공룡</span><span><i style="background:${css("--muted")}"></i>누적 사냥 (점선)</span>`;
    }
    $("popLegend").innerHTML = legend;
    popChart.update(series);
    // action distribution
    const rows = P.PRED_ACTIONS.map((a) => {
      const bars = sims.map((s) => {
        const tot = Object.values(s.actions).reduce((x, y) => x + y, 0) || 1;
        const f = s.actions[a] / tot;
        return `<div class="b" style="width:calc(${(f * 100).toFixed(1)}% * .8);background:${css(POLICY_COLOR[s.key])}" title="${POLICY_LABEL[s.key]}"><span>${(f * 100).toFixed(0)}%</span></div>`;
      }).join("");
      return `<div class="actrow"><span class="lbl">${ACTION_KO[a]}<br><small>${a}</small></span><div class="bars">${bars}</div></div>`;
    }).join("");
    const lg = `<div class="legend">${sims.map((s) => `<span><i style="background:${css(POLICY_COLOR[s.key])}"></i>${POLICY_LABEL[s.key]}</span>`).join("")}</div>`;
    $("actionBars").innerHTML = lg + `<div class="actbars">${rows}</div>`;
  }

  // ------------------------------------------------------------------- loop
  function frame(now) {
    if (!state.running) return;
    const dt = Math.min(0.1, (now - state.last) / 1000);
    state.last = now;
    state.acc += dt * TICKS_PER_SEC * state.speed;
    let n = Math.floor(state.acc);
    state.acc -= n;
    const t0 = performance.now();
    while (n-- > 0) {
      for (const s of state.sims) stepSim(s);
      if (performance.now() - t0 > 24) { state.acc = 0; break; }
    }
    renderAll();
    chartTick();
    if (state.sims.every((s) => s.ended)) setRunning(false);
    else requestAnimationFrame(frame);
  }
  let lastChart = 0;
  function chartTick() {
    const now = performance.now();
    if (now - lastChart > 250) { lastChart = now; updateCharts(); }
  }

  function setRunning(on) {
    if (on && state.sims.every((s) => s.ended)) build();
    state.running = on;
    ui.play.textContent = on ? "❚❚ 일시정지" : "▶ 재생";
    updateCharts();
    if (on) { state.last = performance.now(); requestAnimationFrame(frame); }
  }

  // --------------------------------------------------------------- controls
  function segment(id, attr, onPick) {
    const seg = $(id);
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || !seg.contains(b)) return;
      for (const x of seg.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
      onPick(b.dataset[attr], b);
    });
  }

  function rebuild(keepRunning) {
    const was = state.running;
    state.running = false;
    build();
    if (keepRunning && was) setRunning(true);
    else setRunning(false);
  }

  segment("policySeg", "policy", async (p) => {
    if (p === "ppo" || p === "compare") {
      await ppoReady;
      if (!ppoWeights) {
        alert("PPO 가중치(data/ppo-v2.policy.json)를 불러오지 못했습니다. 로컬 파일로 열었다면 간단한 웹 서버로 열어 주세요.\n" + (ppoError || ""));
        return;
      }
    }
    state.policy = p;
    rebuild(true);
  });
  segment("speedSeg", "speed", (s) => { state.speed = parseInt(s, 10); });

  ui.scenario.addEventListener("change", () => {
    const eco = ui.scenario.value === "ecosystem";
    ui.herb.value = eco ? 12 : 8;
    ui.pred.value = eco ? 2 : 1;
    syncOutputs();
    rebuild(true);
  });
  for (const el of [ui.res, ui.herb, ui.pred]) {
    el.addEventListener("input", syncOutputs);
    el.addEventListener("change", () => rebuild(true));
  }
  ui.seed.addEventListener("change", () => rebuild(true));
  $("dice").addEventListener("click", () => { ui.seed.value = Math.floor(Math.random() * 100000); rebuild(true); });
  $("reset").addEventListener("click", () => rebuild(true));
  ui.play.addEventListener("click", () => setRunning(!state.running));
  $("stepBtn").addEventListener("click", () => {
    if (state.running) setRunning(false);
    for (const s of state.sims) stepSim(s);
    renderAll(); updateCharts();
  });
  ui.showVision.addEventListener("change", renderAll);
  function syncOutputs() {
    $("resOut").textContent = "×" + parseFloat(ui.res.value).toFixed(1);
    $("herbOut").textContent = ui.herb.value;
    $("predOut").textContent = ui.pred.value;
  }
  window.addEventListener("resize", renderAll);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { renderAll(); updateCharts(); });

  // ------------------------------------------------------------- quick eval
  const SET_REF = (scenario, res) => {
    if (scenario === "map_b") return res === 1 ? ["exp003", "base", "eval_unseen_map"] : null;
    if (res === 1) return ["exp003", "base", "eval_seen_map"];
    if (res === 0.6) return ["exp003", "res0.6", "eval_seen_map@res0.6"];
    if (res === 1.4) return ["exp003", "res1.4", "eval_seen_map@res1.4"];
    return null;
  };
  $("evalBtn").addEventListener("click", async () => {
    await ppoReady;
    const btn = $("evalBtn");
    btn.disabled = true;
    const scenario = ui.scenario.value === "ecosystem" ? "map_a" : ui.scenario.value;
    const res = Math.round(parseFloat(ui.res.value) * 10) / 10;
    const keys = ppoWeights ? ["rule", "ppo", "random"] : ["rule", "random"];
    const jobs = [];
    for (const k of keys) for (let s = 10000; s < 10020; s++) jobs.push([k, s]);
    const out = Object.fromEntries(keys.map((k) => [k, []]));
    const t0 = performance.now();
    for (let i = 0; i < jobs.length; i++) {
      const [k, s] = jobs[i];
      const cfg = P.makeConfig(scenario, { resourceScale: res });
      out[k].push(P.runEpisode(cfg, s, makePolicy(k, s), new P.RuleBasedHerbivore(), 2000));
      if (i % 4 === 3) {
        $("evalStatus").textContent = `${i + 1}/${jobs.length} 에피소드…`;
        await new Promise((r) => setTimeout(r, 0));
      }
    }
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    $("evalStatus").textContent = `${scenario} · 자원 ×${res.toFixed(1)} · ${jobs.length} 에피소드 · ${secs}초${ui.scenario.value === "ecosystem" ? " (번식 생태계 대신 map_a 에피소드로 평가)" : ""}`;
    let ref = null;
    const r = SET_REF(scenario, res);
    if (r) {
      try {
        const data = await window.PaleoData.results;
        const rows = data[r[0]][r[1]].summary.filter((x) => x.set === r[2]);
        ref = { rule: rows.find((x) => x.policy === "rule"), ppo: rows.find((x) => x.policy === "ppo_v2_s1"), random: rows.find((x) => x.policy === "random") };
      } catch (e) { ref = null; }
    }
    const mean = (a) => a.reduce((x, y) => x + y, 0) / Math.max(1, a.length);
    const rowsHtml = keys.map((k) => {
      const eps = out[k];
      const kills = mean(eps.map((e) => e.kills));
      const death = mean(eps.map((e) => (e.predatorAlive ? 0 : 1)));
      const withAtt = eps.filter((e) => e.attackAttempts);
      const inv = withAtt.length ? mean(withAtt.map((e) => e.invalid / e.attackAttempts)) : null;
      const causes = {};
      eps.filter((e) => !e.predatorAlive).forEach((e) => (causes[e.predatorDeathCause] = (causes[e.predatorDeathCause] || 0) + 1));
      const cs = Object.entries(causes).map(([c, n]) => `${CAUSE_KO[c] || c} ${n}`).join(", ") || "–";
      const rf = ref && ref[k];
      return `<tr><td><i style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${css(POLICY_COLOR[k])};margin-right:6px"></i>${POLICY_LABEL[k]}</td>
        <td class="num"><b>${kills.toFixed(2)}</b></td><td class="num">${rf ? rf.kills_mean.toFixed(2) : "–"}</td>
        <td class="num"><b>${death.toFixed(2)}</b></td><td class="num">${rf ? rf.predator_death_rate.toFixed(2) : "–"}</td>
        <td class="num">${inv == null ? "–" : inv.toFixed(2)}</td><td>${cs}</td></tr>`;
    }).join("");
    $("evalOut").innerHTML = `<div class="scroll-x"><table>
      <thead><tr><th>포식자</th><th class="num">사냥 (브라우저)</th><th class="num">사냥 (Python 기록)</th><th class="num">사망률 (브라우저)</th><th class="num">사망률 (기록)</th><th class="num">무효 공격</th><th>포식자 사망 원인</th></tr></thead>
      <tbody>${rowsHtml}</tbody></table></div>
      <p class="hint">"Python 기록" = <code>analytics/reports/exp003</code>의 같은 평가 세트(규칙·무작위, PPO는 배포 모델과 같은 <code>ppo_v2_s1</code>). ${r ? "" : "이 설정과 같은 기록 세트가 없어 비교값은 비워 둡니다."}</p>`;
    btn.disabled = false;
  });

  // tab switching (shared with results.js)
  function selectTab(name) {
    for (const t of document.querySelectorAll(".tab")) t.setAttribute("aria-selected", String(t.dataset.tab === name));
    for (const p of document.querySelectorAll(".panel")) p.hidden = p.id !== "tab-" + name;
    if (name === "live") { renderAll(); updateCharts(); }
    window.dispatchEvent(new CustomEvent("paleo:tab", { detail: name }));
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
  }
  for (const t of document.querySelectorAll(".tab")) t.addEventListener("click", () => selectTab(t.dataset.tab));
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-goto]");
    if (a) { e.preventDefault(); selectTab(a.dataset.goto); window.scrollTo({ top: 0, behavior: "smooth" }); }
  });

  // provenance text for the PPO weights
  ppoReady.then(() => {
    if (!ppoWeights) return;
    const s = ppoWeights.source || {};
    const el = $("ppoProvenance");
    if (el) el.innerHTML += ` 출처: <code>${s.run_name || "ppo_v2_s1"}</code> (보상 ${s.reward_version || "v2"}, 학습 seed ${s.train_seed ?? 1}). 저장소에는 모델 파일이 없어(<code>.gitignore</code>) README 절차 <code>train_ppo --config ppo_v2 --seed 1</code>로 다시 학습해 내보낸 가중치입니다. Python 평가(20 seed): 사냥 6.95 / 7.15, 사망률 0.20 / 0.10 (학습 맵 / map_b) — 기록된 <code>ppo_v2_s1</code> 7.05 / 7.15, 0.20 / 0.05와 거의 같습니다. 내보내기 검증 관찰 7,367개에서 JS 추론 행동이 SB3와 100% 일치.`;
  });

  // ------------------------------------------------------------------- boot
  syncOutputs();
  const initial = (location.hash || "").slice(1);
  build();
  if (["results", "about"].includes(initial)) selectTab(initial);
  ppoReady.then(() => {
    if (initial && initial !== "live") return;
    // start with the side-by-side comparison, which is the point of the project
    if (ppoWeights) {
      for (const x of $("policySeg").querySelectorAll("button")) x.setAttribute("aria-pressed", String(x.dataset.policy === "compare"));
      state.policy = "compare";
      build();
    }
    setRunning(true);
  });
})();
