/* "실험 결과" tab: recorded results from analytics/reports (pages/data/results.json). */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const C = window.Charts;

  const FAMILIES = [
    { key: "rule", label: "Rule\n(기준선)", name: "규칙 기반", color: () => css("--rule") },
    { key: "random", label: "Random", name: "무작위", color: () => css("--rand") },
    { key: "ppo_v0", label: "PPO v0\n보상 v0", name: "PPO v0", color: () => "#f4b79a" },
    { key: "ppo_v1", label: "PPO v1\n+BC", name: "PPO v1", color: () => "#ef8f63" },
    { key: "ppo_v2", label: "PPO v2\n갈증 비용", name: "PPO v2", color: () => css("--ppo") },
  ];
  const SETS = {
    seen: "eval_seen_map", unseen: "eval_unseen_map",
    "res0.6": "eval_seen_map@res0.6", "res1.4": "eval_seen_map@res1.4",
  };
  const FLAG_KO = {
    idle_forever: "가만히 굶기", shadowing: "그림자 추적", attack_spam: "공격 남발", water_farming: "물가 머무름",
    boundary_hugging: "벽 붙기", chase_to_death: "탈진 추격", dehydration_neglect: "탈수 방치",
  };

  function family(policy) {
    const m = policy.match(/^(ppo_v\d)_s(\d)$/);
    return m ? m[1] : policy;
  }

  window.PaleoData = window.PaleoData || { results: fetch("data/results.json").then((r) => r.json()) };

  window.PaleoData.results.then(init).catch((e) => {
    $("tab-results").insertAdjacentHTML("beforeend", `<div class="card">결과 데이터를 불러오지 못했습니다: ${e}</div>`);
  });

  function init(data) {
    // all summary rows, later experiments override earlier ones for the same policy+set
    const rows = new Map();
    const add = (list) => list.forEach((r) => rows.set(r.policy + "|" + r.set, r));
    add(data.exp001.summary);
    for (const exp of ["exp002", "exp003"]) for (const v of ["base", "res0.6", "res1.4"]) add(data[exp][v].summary);
    const all = [...rows.values()];
    const hacks = new Map();
    const addH = (list) => list.forEach((r) => hacks.set(r.policy + "|" + r.set, r));
    addH(data.exp001.hacking);
    for (const exp of ["exp002", "exp003"]) for (const v of ["base", "res0.6", "res1.4"]) addH(data[exp][v].hacking);

    kpis(all);
    const kills = C.barChart($("killsChart"), { height: 230, yFmt: (v) => v.toFixed(2), axisFmt: (v) => v.toFixed(0) });
    const death = C.barChart($("deathChart"), { height: 230, yMax: 1, yFmt: (v) => v.toFixed(2), axisFmt: (v) => v.toFixed(2) });

    function showSet(setKey) {
      const set = SETS[setKey];
      const groups = FAMILIES.map((f) => {
        const rs = all.filter((r) => r.set === set && family(r.policy) === f.key);
        if (!rs.length) return null;
        const agg = (k) => {
          const v = rs.map((r) => r[k]);
          return { value: v.reduce((a, b) => a + b, 0) / v.length, lo: Math.min(...v), hi: Math.max(...v) };
        };
        return { f, rs, kills: agg("kills_mean"), death: agg("predator_death_rate") };
      }).filter(Boolean);
      const note = (g) => g.rs.length > 1 ? g.rs.map((r) => `${r.policy.replace(/^ppo_v\d_/, "")} ${r.kills_mean.toFixed(2)}`).join(" · ") : "";
      kills.update(groups.map((g) => ({ label: g.f.label, color: g.f.color(), ...g.kills, lo: g.rs.length > 1 ? g.kills.lo : null, hi: g.rs.length > 1 ? g.kills.hi : null, note: note(g) })));
      death.update(groups.map((g) => ({
        label: g.f.label, color: g.f.color(), ...g.death, lo: g.rs.length > 1 ? g.death.lo : null, hi: g.rs.length > 1 ? g.death.hi : null,
        note: g.rs.map((r) => Object.entries(r.death_causes).map(([c, n]) => `${c} ${n}`).join(", ")).filter(Boolean).join(" / "),
      })));
      const trs = all.filter((r) => r.set === set).sort((a, b) => FAMILIES.findIndex((f) => f.key === family(a.policy)) - FAMILIES.findIndex((f) => f.key === family(b.policy)) || a.policy.localeCompare(b.policy));
      $("expTable").innerHTML = `<div class="scroll-x"><table><thead><tr><th>policy</th><th class="num">사냥</th><th class="num">±sd</th><th class="num">사냥 성공률</th><th class="num">에너지/사냥</th><th class="num">무효 공격</th><th class="num">생존 tick</th><th class="num">사망률</th><th>사망 원인</th></tr></thead><tbody>${
        trs.map((r) => `<tr><td>${r.policy}</td><td class="num">${r.kills_mean.toFixed(2)}</td><td class="num">${r.kills_std.toFixed(2)}</td><td class="num">${r.hunt_success_mean.toFixed(3)}</td><td class="num">${r.energy_per_kill_mean == null ? "–" : r.energy_per_kill_mean.toFixed(0)}</td><td class="num">${r.invalid_attack_rate_mean == null ? "–" : r.invalid_attack_rate_mean.toFixed(2)}</td><td class="num">${r.survival_mean.toFixed(0)}</td><td class="num">${r.predator_death_rate.toFixed(2)}</td><td>${Object.entries(r.death_causes).map(([c, n]) => `${c} ${n}`).join(", ") || "–"}</td></tr>`).join("")
      }</tbody></table></div><p class="hint">세트: <code>${set}</code>, 각 20 seed. 출처: exp001 · exp002 · exp003 summary.csv</p>`;
    }
    segment("setSeg", "set", showSet);
    showSet("seen");

    hackTable([...hacks.values()]);
    ecosystem(data.exp004);
  }

  function kpis(all) {
    const g = (p, s) => all.find((r) => r.policy === p && r.set === s);
    const rule = g("rule", "eval_seen_map"), v2 = g("ppo_v2_s1", "eval_seen_map"), v2u = g("ppo_v2_s1", "eval_unseen_map");
    const v1 = all.filter((r) => family(r.policy) === "ppo_v1" && r.set === "eval_seen_map");
    const v2all = all.filter((r) => family(r.policy) === "ppo_v2" && (r.set === "eval_seen_map" || r.set === "eval_unseen_map"));
    const dr = v2all.map((r) => r.predator_death_rate);
    $("kpis").innerHTML = `
      <div class="kpi"><b>${rule.kills_mean.toFixed(2)} → ${v2.kills_mean.toFixed(2)}</b><span>에피소드당 사냥 · 규칙 → PPO v2 (학습 맵, 20 seed)</span></div>
      <div class="kpi"><b>${v2u.kills_mean.toFixed(2)}</b><span>처음 보는 맵 map_b에서 PPO v2 사냥 (규칙 ${g("rule", "eval_unseen_map").kills_mean.toFixed(2)})</span></div>
      <div class="kpi"><b>${rule.invalid_attack_rate_mean.toFixed(2)} → ${v2.invalid_attack_rate_mean.toFixed(2)}</b><span>무효 공격 비율 (사거리 밖·쿨다운 중 공격)</span></div>
      <div class="kpi"><b>${Math.min(...v1.map((r) => r.predator_death_rate)).toFixed(2)}–${Math.max(...v1.map((r) => r.predator_death_rate)).toFixed(2)} → ${Math.min(...dr).toFixed(2)}–${Math.max(...dr).toFixed(2)}</b><span>포식자 사망률 · 보상 v1 → v2 (탈수 해결). 규칙은 0.00</span></div>`;
  }

  function hackTable(rows) {
    const flags = Object.keys(FLAG_KO);
    const order = (p) => FAMILIES.findIndex((f) => f.key === family(p));
    const list = rows.filter((r) => r.set === "eval_seen_map" || r.set === "eval_unseen_map")
      .filter((r) => family(r.policy).startsWith("ppo"))
      .sort((a, b) => order(a.policy) - order(b.policy) || a.policy.localeCompare(b.policy) || a.set.localeCompare(b.set));
    $("hackTable").innerHTML = `<div class="scroll-x"><table><thead><tr><th>policy</th><th>세트</th>${flags.map((f) => `<th class="num">${FLAG_KO[f]}<br><small>${f}</small></th>`).join("")}<th>판정</th></tr></thead><tbody>${
      list.map((r) => `<tr><td>${r.policy}</td><td>${r.set === "eval_seen_map" ? "학습 맵" : "map_b"}</td>${flags.map((f) => {
        const v = r.flags[f];
        return v == null ? `<td class="num ok">·</td>` : `<td class="num ${v > 0 ? "flag" : "ok"}">${v > 0 ? v.toFixed(2) : "0"}</td>`;
      }).join("")}<td>${r.suspected === "-" ? `<span class="ok">–</span>` : `<span class="flag">⚠ ${r.suspected}</span>`}</td></tr>`).join("")
    }</tbody></table></div><p class="hint">Rule·Random은 모든 항목 0. <code>dehydration_neglect</code>는 Exp 002에서 v1의 탈수 사망을 보고 추가된 탐지기라 Exp 001 표(v0 학습 맵)에는 없습니다 (Exp 002 재계산 값으로 표시). 출처: exp00{1,2,3}/*/hacking.csv</p>`;
  }

  function ecosystem(e4) {
    const pop = e4.population;
    const herb = css("--herb"), pred = css("--pred");
    $("ecoLegend").innerHTML = `<span><i style="background:${herb}"></i>초식공룡 평균 (음영 = seed 하위 10%–상위 10%)</span><span><i style="background:${pred}"></i>육식공룡 평균</span>`;
    const eco = C.lineChart($("ecoChart"), { height: 280, xLabel: "tick", yFmt: (y) => (Math.round(y * 10) / 10).toString() });
    eco.update([
      { name: "초식 평균", color: herb, data: pop.mean.map((m) => [m.t, m.h]), band: pop.mean.map((m) => [m.t, m.h10, m.h90]) },
      { name: "육식 평균", color: pred, data: pop.mean.map((m) => [m.t, m.p]) },
    ]);
    const c = pop.herbivore_death_causes;
    const tot = Object.values(c).reduce((a, b) => a + b, 0);
    $("ecoNote").innerHTML = `${pop.seeds} seed 끝 상태: <b>공존 ${pop.outcome.coexist}</b> · 초식만 ${pop.outcome.herbivores_only} · 전멸 ${pop.outcome.extinct}. 초식 사망 원인: 탈진 ${(100 * c.exhaustion / tot).toFixed(0)}% · 사냥 ${(100 * c.predation / tot).toFixed(0)}% · 노화 ${(100 * c.old_age / tot).toFixed(0)}% (도망치며 에너지를 다 씀). 규칙 기반 초식·포식자, 출처: exp004/population.csv (${pop.rows.toLocaleString("ko-KR")}행). 라이브 탭에서 "번식 생태계"를 고르면 같은 규칙을 직접 돌려 볼 수 있습니다.`;

    const fc = C.barChart($("fcChart"), { height: 220, yFmt: (v) => v.toFixed(2), axisFmt: (v) => v.toFixed(0) });
    const MODEL = { persistence: "그대로 유지\n(persistence)", linear: "선형\n(Ridge)", gbm: "GBM" };
    const showFc = (h) => {
      fc.update(e4.forecast.filter((r) => r.horizon === +h && r.target === "herbivores").map((r) => ({
        label: MODEL[r.model], value: r.mae, color: r.model === "gbm" ? herb : r.model === "linear" ? "#7cc9a8" : css("--rand"),
        note: `RMSE ${r.rmse.toFixed(2)} · 포식자 MAE ${e4.forecast.find((x) => x.horizon === r.horizon && x.target === "predators" && x.model === r.model).mae.toFixed(2)}`,
      })));
    };
    segment("fcSeg", "h", showFc);
    showFc(500);

    const ex = C.lineChart($("exChart"), { height: 220, xLabel: "tick", yFmt: (y) => String(Math.round(y)) });
    const seeds = Object.keys(pop.examples);
    $("exSeg").innerHTML = seeds.map((s, i) => `<button data-seed="${s}" aria-pressed="${i === 0}">seed ${s}</button>`).join("");
    const showEx = (s) => ex.update([
      { name: "초식공룡", color: herb, data: pop.examples[s].map((r) => [r[0], r[1]]) },
      { name: "육식공룡", color: pred, data: pop.examples[s].map((r) => [r[0], r[2]]) },
    ]);
    segment("exSeg", "seed", showEx);
    showEx(seeds[0]);
  }

  function segment(id, attr, onPick) {
    const seg = $(id);
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || !seg.contains(b)) return;
      for (const x of seg.querySelectorAll("button")) x.setAttribute("aria-pressed", String(x === b));
      onPick(b.dataset[attr]);
    });
  }
})();
