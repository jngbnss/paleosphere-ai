/* Minimal canvas charts (line with crosshair tooltip, bars with hover) for the demo. */
(function () {
  "use strict";
  const tip = () => document.getElementById("tip");
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function showTip(html, cx, cy) {
    const t = tip();
    t.innerHTML = html;
    t.hidden = false;
    const r = t.getBoundingClientRect();
    let x = cx + 14, y = cy + 14;
    if (x + r.width > window.innerWidth - 8) x = cx - r.width - 14;
    if (y + r.height > window.innerHeight - 8) y = cy - r.height - 14;
    t.style.left = Math.max(8, x) + "px";
    t.style.top = Math.max(8, y) + "px";
  }
  function hideTip() { tip().hidden = true; }

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
    return 10 * p;
  }

  function setup(el, height) {
    el.innerHTML = "";
    const c = document.createElement("canvas");
    el.appendChild(c);
    const ctx = c.getContext("2d");
    const st = { c, ctx, w: 0, h: height };
    function size() {
      const dpr = window.devicePixelRatio || 1;
      st.w = el.clientWidth || 300;
      st.h = el.clientHeight || height;
      c.width = Math.round(st.w * dpr);
      c.height = Math.round(st.h * dpr);
      c.style.width = st.w + "px";
      c.style.height = st.h + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    size();
    st.size = size;
    return st;
  }

  function axes(ctx, L, T, W, H, yMax, ticks, fmt) {
    ctx.font = "11px " + css("--font");
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= ticks; i++) {
      const v = (yMax * i) / ticks, y = T + H - (H * i) / ticks;
      ctx.strokeStyle = css("--grid");
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(L, Math.round(y) + 0.5); ctx.lineTo(L + W, Math.round(y) + 0.5); ctx.stroke();
      ctx.fillStyle = css("--muted");
      ctx.fillText(fmt(v), L - 6, y);
    }
  }

  /**
   * Line chart. opts: { height, xFmt, yFmt, xLabel, yMax }
   * update(series): series = [{ name, color, data: [[x, y], ...], band: [[x, lo, hi]], dash }]
   */
  function lineChart(el, opts) {
    opts = opts || {};
    const st = setup(el, opts.height || 200);
    let series = [], hoverX = null;
    const xFmt = opts.xFmt || ((x) => x.toLocaleString("ko-KR"));
    const yFmt = opts.yFmt || ((y) => (Math.round(y * 10) / 10).toLocaleString("ko-KR"));
    const pad = { l: 38, r: 12, t: 10, b: 24 };

    function bounds() {
      let xMin = Infinity, xMax = -Infinity, yMax = opts.yMax || 0;
      for (const s of series) {
        for (const [x, y] of s.data) { xMin = Math.min(xMin, x); xMax = Math.max(xMax, x); if (!opts.yMax) yMax = Math.max(yMax, y); }
        if (s.band && !opts.yMax) for (const b of s.band) yMax = Math.max(yMax, b[2]);
      }
      if (!isFinite(xMin)) { xMin = 0; xMax = 1; }
      if (xMax === xMin) xMax = xMin + 1;
      return { xMin, xMax, yMax: opts.yMax || niceMax(Math.max(yMax, opts.yMinMax || 1)) };
    }

    function draw() {
      const { ctx, w, h } = st;
      ctx.clearRect(0, 0, w, h);
      const L = pad.l, T = pad.t, W = w - pad.l - pad.r, H = h - pad.t - pad.b;
      const b = bounds();
      const X = (x) => L + ((x - b.xMin) / (b.xMax - b.xMin)) * W;
      const Y = (y) => T + H - (y / b.yMax) * H;
      axes(ctx, L, T, W, H, b.yMax, 4, yFmt);
      ctx.fillStyle = css("--muted");
      ctx.textAlign = "left"; ctx.textBaseline = "top";
      ctx.fillText(xFmt(b.xMin), L, T + H + 6);
      ctx.textAlign = "right";
      ctx.fillText(xFmt(b.xMax) + (opts.xLabel ? " " + opts.xLabel : ""), L + W, T + H + 6);
      for (const s of series) {
        if (s.band && s.band.length) {
          ctx.fillStyle = s.color; ctx.globalAlpha = 0.14;
          ctx.beginPath();
          s.band.forEach(([x, lo], i) => (i ? ctx.lineTo(X(x), Y(lo)) : ctx.moveTo(X(x), Y(lo))));
          for (let i = s.band.length - 1; i >= 0; i--) ctx.lineTo(X(s.band[i][0]), Y(s.band[i][2]));
          ctx.closePath(); ctx.fill(); ctx.globalAlpha = 1;
        }
      }
      for (const s of series) {
        if (!s.data.length) continue;
        ctx.strokeStyle = s.color; ctx.lineWidth = s.width || 2; ctx.lineJoin = "round";
        ctx.setLineDash(s.dash || []);
        ctx.beginPath();
        s.data.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y))));
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (hoverX !== null && series.length && series[0].data.length) {
        const xv = b.xMin + ((hoverX - L) / W) * (b.xMax - b.xMin);
        const rows = [];
        let snapX = null;
        for (const s of series) {
          if (!s.data.length) continue;
          let best = s.data[0];
          for (const p of s.data) if (Math.abs(p[0] - xv) < Math.abs(best[0] - xv)) best = p;
          if (snapX === null) snapX = best[0];
          rows.push([s, best]);
        }
        const px = X(snapX);
        ctx.strokeStyle = css("--muted"); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(px + 0.5, T); ctx.lineTo(px + 0.5, T + H); ctx.stroke();
        for (const [s, p] of rows) {
          ctx.fillStyle = s.color; ctx.strokeStyle = css("--surface"); ctx.lineWidth = 2;
          ctx.beginPath(); ctx.arc(X(p[0]), Y(p[1]), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
        st.tipRows = { x: snapX, rows };
      } else st.tipRows = null;
    }

    function onMove(e) {
      const r = st.c.getBoundingClientRect();
      const x = e.clientX - r.left;
      if (x < pad.l || x > st.w - pad.r) { hoverX = null; hideTip(); draw(); return; }
      hoverX = x;
      draw();
      if (st.tipRows) {
        const html = `<b>${xFmt(st.tipRows.x)}${opts.xLabel ? " " + opts.xLabel : ""}</b>` +
          st.tipRows.rows.map(([s, p]) => `<div><i style="background:${s.color}"></i>${s.name} <b>${yFmt(p[1])}</b></div>`).join("");
        showTip(html, e.clientX, e.clientY);
      }
    }
    st.c.addEventListener("pointermove", onMove);
    st.c.addEventListener("pointerleave", () => { hoverX = null; hideTip(); draw(); });
    new ResizeObserver(() => { st.size(); draw(); }).observe(el);

    return { update(s) { series = s; draw(); }, redraw: draw };
  }

  /**
   * Bar chart. update(bars): [{ label, value, lo, hi, color, note }], opts { height, yMax, yFmt }
   */
  function barChart(el, opts) {
    opts = opts || {};
    const st = setup(el, opts.height || 210);
    let bars = [], hover = -1, rects = [];
    const yFmt = opts.yFmt || ((v) => (Math.round(v * 100) / 100).toString());
    const pad = { l: 36, r: 8, t: 14, b: 40 };

    function draw() {
      const { ctx, w, h } = st;
      ctx.clearRect(0, 0, w, h);
      const L = pad.l, T = pad.t, W = w - pad.l - pad.r, H = h - pad.t - pad.b;
      let m = 0;
      for (const b of bars) m = Math.max(m, b.hi != null ? b.hi : b.value);
      const yMax = opts.yMax || niceMax(m);
      axes(ctx, L, T, W, H, yMax, 4, opts.axisFmt || yFmt);
      const n = bars.length, slot = W / Math.max(1, n), bw = Math.min(46, slot * 0.62);
      rects = [];
      bars.forEach((b, i) => {
        const cx = L + slot * i + slot / 2;
        const y = T + H - (b.value / yMax) * H;
        const x0 = cx - bw / 2;
        ctx.fillStyle = b.color;
        ctx.globalAlpha = hover === -1 || hover === i ? 1 : 0.45;
        const hh = Math.max(0, T + H - y), r = Math.min(4, hh, bw / 2);
        ctx.beginPath();
        ctx.moveTo(x0, T + H); ctx.lineTo(x0, y + r); ctx.quadraticCurveTo(x0, y, x0 + r, y);
        ctx.lineTo(x0 + bw - r, y); ctx.quadraticCurveTo(x0 + bw, y, x0 + bw, y + r); ctx.lineTo(x0 + bw, T + H);
        ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
        if (b.lo != null && b.hi != null && b.hi > b.lo) {
          ctx.strokeStyle = css("--ink"); ctx.lineWidth = 1.5;
          const y1 = T + H - (b.lo / yMax) * H, y2 = T + H - (b.hi / yMax) * H;
          ctx.beginPath(); ctx.moveTo(cx, y1); ctx.lineTo(cx, y2);
          ctx.moveTo(cx - 5, y1); ctx.lineTo(cx + 5, y1); ctx.moveTo(cx - 5, y2); ctx.lineTo(cx + 5, y2); ctx.stroke();
        }
        ctx.fillStyle = css("--ink"); ctx.font = "600 11px " + css("--font");
        ctx.textAlign = "center"; ctx.textBaseline = "bottom";
        const topY = b.hi != null ? Math.min(y, T + H - (b.hi / yMax) * H) : y;
        ctx.fillText(yFmt(b.value), cx, topY - 3);
        ctx.fillStyle = css("--muted"); ctx.font = "11px " + css("--font"); ctx.textBaseline = "top";
        const lines = String(b.label).split("\n");
        lines.forEach((ln, k) => ctx.fillText(ln, cx, T + H + 6 + k * 13, slot - 2));
        rects.push([L + slot * i, T, slot, H + pad.b]);
      });
    }

    st.c.addEventListener("pointermove", (e) => {
      const r = st.c.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const i = rects.findIndex(([rx, ry, rw, rh]) => x >= rx && x < rx + rw && y >= ry && y < ry + rh);
      if (i !== hover) { hover = i; draw(); }
      if (i >= 0) {
        const b = bars[i];
        showTip(`<b>${b.label.replace("\n", " ")}</b><div><i style="background:${b.color}"></i>${yFmt(b.value)}${
          b.lo != null && b.hi != null && b.hi > b.lo ? ` <span class="t-mut">(범위 ${yFmt(b.lo)}–${yFmt(b.hi)})</span>` : ""}</div>${b.note ? `<div class="t-mut">${b.note}</div>` : ""}`, e.clientX, e.clientY);
      } else hideTip();
    });
    st.c.addEventListener("pointerleave", () => { hover = -1; hideTip(); draw(); });
    new ResizeObserver(() => { st.size(); draw(); }).observe(el);
    return { update(b) { bars = b; draw(); }, redraw: draw };
  }

  window.Charts = { lineChart, barChart, css };
})();
