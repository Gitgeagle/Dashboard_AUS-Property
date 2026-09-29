/* Morning Markets - full-size history chart for the drill-down view.
   Hand-rolled SVG rather than a charting library: one line series with a crosshair is
   ~200 lines, and the page stays dependency-free with nothing to break on a CDN. */

const Chart = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const mk = (tag, attrs = {}, text) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text != null) n.textContent = text;
    return n;
  };
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAY = 86400000;

  // Round axis steps to 1/2/2.5/5 x 10^n so gridlines land on numbers people read.
  function niceStep(span, target) {
    const raw = span / Math.max(target, 1);
    const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    for (const m of [1, 2, 2.5, 5, 10]) if (raw <= m * mag) return m * mag;
    return 10 * mag;
  }

  function stepDecimals(step) {
    const frac = String(+step.toPrecision(6)).split(".")[1];
    return Math.min(4, frac ? frac.length : 0);
  }

  // x ticks: days/weeks for short ranges, months for up to ~2.5 years, years beyond.
  function timeTicks(t0, t1, maxTicks) {
    const span = t1 - t0;
    const out = [];
    if (span <= 120 * DAY) {
      const stepDays = [1, 2, 7, 14, 28].find((d) => span / (d * DAY) <= maxTicks) || 28;
      const d = new Date(t0);
      d.setUTCHours(0, 0, 0, 0);
      while (d.getTime() <= t1) {
        if (d.getTime() >= t0) out.push([d.getTime(), `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`]);
        d.setUTCDate(d.getUTCDate() + stepDays);
      }
      return out;
    }
    if (span <= 900 * DAY) {
      const stepM = [1, 2, 3, 6].find((m) => span / (m * 30.4 * DAY) <= maxTicks) || 6;
      const d = new Date(Date.UTC(new Date(t0).getUTCFullYear(), new Date(t0).getUTCMonth() + 1, 1));
      while (d.getTime() <= t1) {
        if (d.getUTCMonth() % stepM === 0) {
          const m = d.getUTCMonth();
          out.push([d.getTime(), m === 0 ? String(d.getUTCFullYear()) : `${MONTHS[m]} ${String(d.getUTCFullYear()).slice(2)}`]);
        }
        d.setUTCMonth(d.getUTCMonth() + 1);
      }
      return out;
    }
    const stepY = [1, 2, 5].find((y) => span / (y * 365.25 * DAY) <= maxTicks) || 5;
    for (let y = new Date(t0).getUTCFullYear() + 1; ; y++) {
      const t = Date.UTC(y, 0, 1);
      if (t > t1) break;
      if (y % stepY === 0) out.push([t, String(y)]);
    }
    return out;
  }

  function nearestIndex(pts, t) {
    let lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (pts[mid][0] < t) lo = mid; else hi = mid;
    }
    return Math.abs(pts[lo][0] - t) <= Math.abs(pts[hi][0] - t) ? lo : hi;
  }

  /* pts: [[ms, value], ...] ascending. opts: {fmtValue, fmtAxis?, fmtDelta, fmtDate, dir}.
     fmtDelta(from, to) returns {text, dir} so rates read in bp and prices in %. */
  function draw(host, pts, opts) {
    host.innerHTML = "";
    if (!pts || pts.length < 2) {
      host.appendChild(Object.assign(document.createElement("div"),
        { className: "chart-empty", textContent: "Not enough history to chart." }));
      return;
    }
    const W = Math.max(host.clientWidth || 600, 280);
    const H = W < 520 ? 230 : 300;
    const padL = 8, padR = 58, padT = 12, padB = 24;
    const svg = mk("svg", { class: "chart-svg", width: W, height: H, viewBox: `0 0 ${W} ${H}` });

    const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    let v0 = Infinity, v1 = -Infinity;
    for (const [, v] of pts) { if (v < v0) v0 = v; if (v > v1) v1 = v; }
    const pad = (v1 - v0) * 0.08 || Math.abs(v1) * 0.02 || 1;
    let y0 = v0 - pad, y1 = v1 + pad;
    const step = niceStep(y1 - y0, H < 260 ? 4 : 5);
    y0 = Math.floor(y0 / step) * step;
    y1 = Math.ceil(y1 / step) * step;
    const dec = stepDecimals(step);

    const px = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
    const py = (v) => padT + (1 - (v - y0) / (y1 - y0 || 1)) * (H - padT - padB);

    for (let v = y0; v <= y1 + step / 2; v += step) {
      const y = py(v);
      svg.appendChild(mk("line", { x1: padL, x2: W - padR, y1: y, y2: y, class: "c-grid" }));
      svg.appendChild(mk("text", { x: W - padR + 6, y: y + 3.5, class: "c-axis" },
        opts.fmtAxis ? opts.fmtAxis(v)
          : v.toLocaleString("en-AU", { minimumFractionDigits: dec, maximumFractionDigits: dec })));
    }
    for (const [t, label] of timeTicks(t0, t1, Math.floor((W - padL - padR) / 70))) {
      const x = px(t);
      svg.appendChild(mk("line", { x1: x, x2: x, y1: padT, y2: H - padB, class: "c-grid c-vgrid" }));
      svg.appendChild(mk("text", { x, y: H - 7, "text-anchor": "middle", class: "c-axis" }, label));
    }

    // Dashed reference at the range's opening value: "above or below where this
    // window started" is the first thing the eye wants from a history chart.
    const base = py(pts[0][1]);
    svg.appendChild(mk("line", { x1: padL, x2: W - padR, y1: base, y2: base, class: "c-base" }));

    const dirClass = opts.dir === "up" ? "up" : opts.dir === "down" ? "down" : "flat";
    const line = pts.map(([t, v], i) => (i ? "L" : "M") + px(t).toFixed(1) + " " + py(v).toFixed(1)).join(" ");
    const area = line + ` L${px(t1).toFixed(1)} ${H - padB} L${px(t0).toFixed(1)} ${H - padB} Z`;
    svg.appendChild(mk("path", { d: area, class: "c-area " + dirClass }));
    svg.appendChild(mk("path", { d: line, class: "c-line " + dirClass }));

    // Sparse series (quarterly, monthly) get a marker on every release so a straight
    // segment isn't mistaken for data between prints.
    if (pts.length <= 60) {
      for (const [t, v] of pts) svg.appendChild(mk("circle", { cx: px(t), cy: py(v), r: 2.4, class: "c-dot " + dirClass }));
    }

    // Last-value flag on the axis, Bloomberg-style.
    const last = pts[pts.length - 1];
    const ly = py(last[1]);
    svg.appendChild(mk("rect", { x: W - padR + 1, y: ly - 8, width: padR - 2, height: 16, rx: 2, class: "c-flag " + dirClass }));
    svg.appendChild(mk("text", { x: W - padR + 6, y: ly + 3.5, class: "c-flag-text" }, opts.fmtValue(last[1])));

    // Crosshair and readout.
    const cross = mk("g", { class: "c-cross", visibility: "hidden" });
    const vline = mk("line", { y1: padT, y2: H - padB, class: "c-cross-line" });
    const dot = mk("circle", { r: 3.5, class: "c-cross-dot" });
    cross.append(vline, dot);
    svg.appendChild(cross);
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.hidden = true;

    const hit = mk("rect", { x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, class: "c-hit" });
    svg.appendChild(hit);

    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const x = (ev.clientX - r.left) * (W / r.width);
      const t = t0 + ((x - padL) / (W - padL - padR)) * (t1 - t0);
      const i = nearestIndex(pts, t);
      const [pt, pv] = pts[i];
      const cx = px(pt), cy = py(pv);
      vline.setAttribute("x1", cx); vline.setAttribute("x2", cx);
      dot.setAttribute("cx", cx); dot.setAttribute("cy", cy);
      cross.setAttribute("visibility", "visible");
      const d = opts.fmtDelta(pts[0][1], pv);
      tip.innerHTML = "";
      const a = document.createElement("b"); a.textContent = opts.fmtValue(pv);
      const b = document.createElement("span"); b.textContent = opts.fmtDate(pt);
      const c = document.createElement("span"); c.className = "t-change " + d.dir; c.textContent = d.text + " vs start";
      tip.append(b, a, c);
      tip.hidden = false;
      const left = (cx / W) * r.width;
      tip.style.left = Math.min(Math.max(left - 70, 0), r.width - 150) + "px";
      tip.style.top = "0px";
    };
    const leave = () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", leave);

    host.append(svg, tip);
  }

  function scale(vals, target) {
    let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const pad = (hi - lo) * 0.08 || 1;
    lo -= pad; hi += pad;
    const step = niceStep(hi - lo, target);
    return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step };
  }

  /* Comparative chart (Bloomberg COMP): every series as its change since the window
     opened. Prices rebase to percent, rates to basis points - they cannot honestly share
     an axis, so when both are present percent reads on the left and bp on the right.
     series: [{label, cls, mode: "pct"|"bp", pts: [[ms, change], ...]}] */
  function compare(host, series, opts) {
    host.innerHTML = "";
    const live = series.filter((s) => s.pts.length > 1);
    if (!live.length) {
      host.appendChild(Object.assign(document.createElement("div"),
        { className: "chart-empty", textContent: "Add a series to compare." }));
      return;
    }
    const W = Math.max(host.clientWidth || 600, 280);
    const H = W < 520 ? 250 : 340;
    const modes = [...new Set(live.map((s) => s.mode))];
    const dual = modes.length > 1;
    const padL = dual ? 52 : 8, padR = 58, padT = 12, padB = 24;
    const svg = mk("svg", { class: "chart-svg", width: W, height: H, viewBox: `0 0 ${W} ${H}` });

    const t0 = Math.min(...live.map((s) => s.pts[0][0]));
    const t1 = Math.max(...live.map((s) => s.pts[s.pts.length - 1][0]));
    const px = (t) => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
    const axes = {};
    for (const m of modes) {
      axes[m] = scale(live.filter((s) => s.mode === m).flatMap((s) => s.pts.map((p) => p[1])), H < 280 ? 4 : 5);
    }
    // Every series starts at zero, so zero must sit at the same height on both axes -
    // otherwise lines that start together appear to start apart. Give each axis the
    // largest below-zero share of any axis, extending its floor to match.
    if (dual) {
      const share = Math.max(...modes.map((m) => -axes[m].lo / (axes[m].hi - axes[m].lo)));
      for (const m of modes) {
        const a = axes[m];
        if (-a.lo / (a.hi - a.lo) < share) {
          a.lo = -share * a.hi / (1 - share);
          a.step = niceStep(a.hi - a.lo, H < 280 ? 6 : 8); // finer: the stretched axis still needs ticks above zero
        }
      }
    }
    const right = modes.includes("bp") && dual ? "bp" : modes[0];
    const left = dual ? modes.find((m) => m !== right) : null;
    const py = (m, v) => padT + (1 - (v - axes[m].lo) / (axes[m].hi - axes[m].lo || 1)) * (H - padT - padB);
    const unit = (m) => (m === "bp" ? " bp" : "%");
    const fmtAxis = (m, v) => (v > 0 ? "+" : "") + (m === "bp" ? Math.round(v) : +v.toFixed(stepDecimals(axes[m].step))) + unit(m);

    const R = axes[right];
    for (let v = Math.ceil(R.lo / R.step - 1e-9) * R.step; v <= R.hi + R.step * 1e-6; v += R.step) {
      const y = py(right, v);
      svg.appendChild(mk("line", { x1: padL, x2: W - padR, y1: y, y2: y, class: "c-grid" }));
      svg.appendChild(mk("text", { x: W - padR + 6, y: y + 3.5, class: "c-axis" }, fmtAxis(right, v)));
    }
    if (left) {
      const L = axes[left];
      for (let v = Math.ceil(L.lo / L.step - 1e-9) * L.step; v <= L.hi + L.step * 1e-6; v += L.step) {
        svg.appendChild(mk("text", { x: padL - 6, y: py(left, v) + 3.5, "text-anchor": "end", class: "c-axis" }, fmtAxis(left, v)));
      }
    }
    for (const [t, label] of timeTicks(t0, t1, Math.floor((W - padL - padR) / 70))) {
      const x = px(t);
      svg.appendChild(mk("line", { x1: x, x2: x, y1: padT, y2: H - padB, class: "c-grid c-vgrid" }));
      svg.appendChild(mk("text", { x, y: H - 7, "text-anchor": "middle", class: "c-axis" }, label));
    }
    const zero = py(right, 0);
    svg.appendChild(mk("line", { x1: padL, x2: W - padR, y1: zero, y2: zero, class: "c-base" }));

    for (const s of live) {
      const d = s.pts.map(([t, v], i) => (i ? "L" : "M") + px(t).toFixed(1) + " " + py(s.mode, v).toFixed(1)).join(" ");
      svg.appendChild(mk("path", { d, class: `c-line c-cmp ${s.cls}` + (dual && s.mode === left ? " c-left" : "") }));
      if (s.pts.length <= 60) {
        for (const [t, v] of s.pts) svg.appendChild(mk("circle", { cx: px(t), cy: py(s.mode, v), r: 2.2, class: `c-cmp-dot ${s.cls}` }));
      }
    }

    const cross = mk("g", { class: "c-cross", visibility: "hidden" });
    const vline = mk("line", { y1: padT, y2: H - padB, class: "c-cross-line" });
    cross.appendChild(vline);
    svg.appendChild(cross);
    const tip = document.createElement("div");
    tip.className = "chart-tip wide";
    tip.hidden = true;
    const hit = mk("rect", { x: padL, y: padT, width: W - padL - padR, height: H - padT - padB, class: "c-hit" });
    svg.appendChild(hit);

    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const x = (ev.clientX - r.left) * (W / r.width);
      const t = t0 + ((x - padL) / (W - padL - padR)) * (t1 - t0);
      const cx = px(t);
      vline.setAttribute("x1", cx); vline.setAttribute("x2", cx);
      cross.setAttribute("visibility", "visible");
      tip.innerHTML = "";
      tip.appendChild(Object.assign(document.createElement("span"), { textContent: opts.fmtDate(t) }));
      for (const s of live) {
        const p = s.pts[nearestIndex(s.pts, t)];
        const row = document.createElement("span");
        row.className = "tip-row";
        const sw = document.createElement("i");
        sw.className = "sw " + s.cls;
        const v = document.createElement("b");
        v.className = "t-change " + (p[1] > 0 ? "up" : p[1] < 0 ? "down" : "flat");
        v.textContent = (p[1] > 0 ? "+" : "") + (s.mode === "bp" ? Math.round(p[1]) + " bp" : p[1].toFixed(2) + "%");
        row.append(sw, document.createTextNode(s.label + " "), v);
        tip.appendChild(row);
      }
      tip.hidden = false;
      const left = (cx / W) * r.width;
      tip.style.left = (left > r.width / 2 ? Math.max(left - 250, 0) : left + 12) + "px";
      tip.style.top = "0px";
    };
    hit.addEventListener("pointermove", move);
    hit.addEventListener("pointerdown", move);
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); tip.hidden = true; });
    host.append(svg, tip);
  }

  return { draw, compare };
})();
