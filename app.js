/* Morning Markets - renders data/latest.json into panels.
   No framework, no build step. The fetcher does the arithmetic; this file only
   formats and draws. */

const SVG = "http://www.w3.org/2000/svg";
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

/* ------------------------------------------------------------- formatting */
function fmtValue(t) {
  if (t.text_value != null) return t.text_value;
  const v = t.value;
  if (v == null) return "—";
  const u = t.unit;
  if (u === "%") return v.toFixed(2) + "%";
  if (u === "pp") return (v > 0 ? "+" : "") + v.toFixed(2) + "pp";
  if (u === "$") {
    if (Math.abs(v) >= 1e9) return "$" + (v / 1e9).toFixed(1) + "bn";
    if (Math.abs(v) >= 1e6) return "$" + (v / 1e6).toFixed(2) + "m";
    return "$" + Math.round(v).toLocaleString("en-AU");
  }
  const abs = Math.abs(v);
  const dp = abs >= 1000 ? 1 : abs >= 10 ? 2 : abs >= 1 ? 3 : 4;
  return v.toLocaleString("en-AU", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function fmtChange(t) {
  // Rate-like tiles move in percentage points; everything else in percent.
  if (t.unit === "%" || t.unit === "pp") {
    if (t.change == null) return { text: "—", dir: "flat" };
    const bp = Math.round(t.change * 100);
    return {
      text: (bp > 0 ? "+" : "") + bp + " bp",
      dir: bp > 0 ? "up" : bp < 0 ? "down" : "flat",
    };
  }
  if (t.change_pct == null) return { text: "—", dir: "flat" };
  const p = t.change_pct;
  return {
    text: (p > 0 ? "+" : "") + p.toFixed(2) + "%",
    dir: p > 0 ? "up" : p < 0 ? "down" : "flat",
  };
}

function fmtAsOf(t) {
  if (t.period) return t.period;
  if (!t.asof) return "";
  const age = t.age_days;
  if (age === 0) return "today";
  if (age === 1) return "yesterday";
  if (age != null && age <= 6) return age + "d ago";
  return t.asof;
}

/* ---------------------------------------------------------------- sparkline */
function sparkline(points, dir) {
  const svg = svgEl("svg", { class: "t-spark", viewBox: "0 0 100 26", preserveAspectRatio: "none" });
  if (!points || points.length < 2) return svg;
  const vals = points.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const step = 100 / (vals.length - 1);
  const xy = vals.map((v, i) => [i * step, 25 - ((v - min) / span) * 23]);
  const d = xy.map(([x, y], i) => (i ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2)).join(" ");
  const stroke = dir === "up" ? "var(--up)" : dir === "down" ? "var(--down)" : "var(--flat)";
  svg.appendChild(svgEl("path", { d, fill: "none", stroke, "stroke-width": "1.1",
    "vector-effect": "non-scaling-stroke", "stroke-linejoin": "round" }));
  return svg;
}

/* --------------------------------------------------------------------- tile */
function renderTile(t) {
  const node = el("div", "tile" + (t.status === "stale" ? " is-stale"
    : t.status === "unavailable" ? " is-unavailable" : ""));

  node.appendChild(el("div", "t-label", t.label));

  if (t.status === "unavailable") {
    node.appendChild(el("div", "t-value text", "unavailable"));
    node.appendChild(el("div", "t-note t-warn", t.error ? String(t.error).slice(0, 120) : "no data returned"));
    return node;
  }

  const val = el("div", "t-value" + (t.text_value != null ? " text" : ""), fmtValue(t));
  node.appendChild(val);

  const ch = fmtChange(t);
  const row = el("div", "t-row");
  row.appendChild(el("span", "t-change " + ch.dir, ch.text));
  row.appendChild(el("span", "t-asof", fmtAsOf(t)));
  node.appendChild(row);

  if (t.spark && t.spark.length > 1) node.appendChild(sparkline(t.spark, ch.dir));

  if (t.status === "stale") {
    node.appendChild(el("span", "badge-stale", "STALE"));
    if (t.stale_reason) node.appendChild(el("div", "t-note t-warn", t.stale_reason));
  } else if (t.note) {
    node.appendChild(el("div", "t-note", t.note));
  }
  return node;
}

/* -------------------------------------------------------------- curve chart */
// sqrt spacing on the maturity axis, so the short end stays legible next to 30 years.
const xScale = (years) => Math.sqrt(years);

function renderCurve(c) {
  const card = el("div", "curve-card");

  const head = el("div", "curve-head");
  head.appendChild(el("h3", null, c.country + " yield curve"));
  const m = c.metrics || {};
  head.appendChild(el("span", "shape " + (m.shape || "unknown"), m.shape || "unknown"));
  card.appendChild(head);

  const stats = el("div", "curve-stats");
  if (m.spread_10_2 != null) stat0(stats, "10y−2y", (m.spread_10_2 > 0 ? "+" : "") + m.spread_10_2.toFixed(2) + "pp");
  if (m.spread_10_3m != null) stat0(stats, "10y−3m", (m.spread_10_3m > 0 ? "+" : "") + m.spread_10_3m.toFixed(2) + "pp");
  if (m.days_inverted) stat0(stats, "inverted", m.days_inverted + "d");
  stat0(stats, "as at", c.date);
  card.appendChild(stats);

  card.appendChild(drawCurve(c));

  const legend = el("div", "curve-legend");
  const item = (color, label, dash) => {
    const s = el("span");
    const i = el("i");
    i.style.background = dash ? "none" : color;
    if (dash) i.style.borderTop = "2px dashed " + color;
    s.appendChild(i);
    s.appendChild(document.createTextNode(label));
    return s;
  };
  legend.appendChild(item("var(--accent)", "today"));
  if (c.month_ago && c.month_ago.length) legend.appendChild(item("var(--muted)", "1 month ago", true));
  if (c.year_ago && c.year_ago.length) legend.appendChild(item("var(--dim)", "1 year ago", true));
  card.appendChild(legend);

  if (c.caveat) card.appendChild(el("div", "curve-caveat", c.caveat));
  return card;
}

function stat0(parent, label, val) {
  const s = el("span", null, label + " ");
  s.appendChild(el("b", null, val));
  parent.appendChild(s);
}

function drawCurve(c) {
  const W = 620, H = 210, padL = 40, padR = 12, padT = 12, padB = 26;
  const svg = svgEl("svg", { class: "curve-svg", viewBox: `0 0 ${W} ${H}`,
    preserveAspectRatio: "xMidYMid meet" });

  const sets = [
    { pts: c.year_ago, color: "var(--dim)", dash: "3 3", w: 1 },
    { pts: c.month_ago, color: "var(--muted)", dash: "4 3", w: 1 },
    { pts: c.points, color: "var(--accent)", dash: null, w: 1.8 },
  ].filter((s) => s.pts && s.pts.length);

  const all = sets.flatMap((s) => s.pts);
  if (!all.length) return svg;

  const xs = all.map((p) => xScale(p.years));
  const ys = all.map((p) => p.yield);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  const padY = Math.max((y1 - y0) * 0.18, 0.12);
  y0 -= padY; y1 += padY;

  const px = (years) => padL + ((xScale(years) - x0) / (x1 - x0 || 1)) * (W - padL - padR);
  const py = (v) => padT + (1 - (v - y0) / (y1 - y0 || 1)) * (H - padT - padB);

  // horizontal gridlines + y labels
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = y0 + ((y1 - y0) * i) / ticks;
    const y = py(v);
    svg.appendChild(svgEl("line", { x1: padL, x2: W - padR, y1: y, y2: y,
      stroke: "var(--line)", "stroke-width": 1 }));
    const lab = svgEl("text", { x: padL - 6, y: y + 3.5, "text-anchor": "end",
      fill: "var(--dim)", "font-size": 9.5, "font-family": "var(--mono)" });
    lab.textContent = v.toFixed(2);
    svg.appendChild(lab);
  }

  // x tick labels from the current curve
  for (const p of c.points) {
    const lab = svgEl("text", { x: px(p.years), y: H - 8, "text-anchor": "middle",
      fill: "var(--dim)", "font-size": 9.5, "font-family": "var(--mono)" });
    lab.textContent = p.tenor;
    svg.appendChild(lab);
  }

  for (const s of sets) {
    const sorted = [...s.pts].sort((a, b) => a.years - b.years);
    const d = sorted.map((p, i) => (i ? "L" : "M") + px(p.years).toFixed(1) + " " + py(p.yield).toFixed(1)).join(" ");
    const path = svgEl("path", { d, fill: "none", stroke: s.color, "stroke-width": s.w,
      "stroke-linejoin": "round" });
    if (s.dash) path.setAttribute("stroke-dasharray", s.dash);
    svg.appendChild(path);
  }

  // Markers on the current curve, shaped by instrument: the Australian short end is
  // bank bills, not government paper, so it is drawn differently rather than implied
  // to be the same instrument.
  for (const p of c.points) {
    const isGovt = p.instrument === "govt";
    const marker = isGovt
      ? svgEl("circle", { cx: px(p.years), cy: py(p.yield), r: 2.6, fill: "var(--accent)" })
      : svgEl("rect", { x: px(p.years) - 2.3, y: py(p.yield) - 2.3, width: 4.6, height: 4.6,
          fill: "none", stroke: "var(--accent)", "stroke-width": 1.2 });
    const title = svgEl("title");
    title.textContent = `${p.tenor}: ${p.yield}%  (${isGovt ? "government" : p.instrument})`;
    marker.appendChild(title);
    svg.appendChild(marker);
  }
  return svg;
}

/* ------------------------------------------------------------------ render */
function render(data) {
  const app = document.getElementById("app");
  app.innerHTML = "";

  for (const panel of data.panels) {
    const tileCount = panel.groups.reduce((n, g) => n + g.tiles.length, 0);
    const isCurves = panel.id === "curves";
    if (!tileCount && !(isCurves && data.curves.length)) continue;

    const sec = el("section", "panel" + (panel.cadence.includes("quarterly") ? " slow" : ""));
    const head = el("div", "panel-head");
    head.appendChild(el("h2", null, panel.title));
    head.appendChild(el("span", "cadence", panel.cadence));
    if (panel.subtitle) head.appendChild(el("div", "panel-sub", panel.subtitle));
    sec.appendChild(head);

    if (isCurves && data.curves.length) {
      const wrap = el("div", "curves");
      data.curves.forEach((c) => wrap.appendChild(renderCurve(c)));
      sec.appendChild(wrap);
    }

    for (const g of panel.groups) {
      if (!g.tiles.length) continue;
      const grp = el("div", "group");
      if (g.name) grp.appendChild(el("div", "group-name", g.name));
      const grid = el("div", "grid");
      g.tiles.forEach((t) => grid.appendChild(renderTile(t)));
      grp.appendChild(grid);
      sec.appendChild(grp);
    }
    app.appendChild(sec);
  }

  // header meta
  const gen = new Date(data.generated_at);
  document.getElementById("generated").textContent =
    "data " + gen.toLocaleString("en-AU", { day: "2-digit", month: "short",
      hour: "2-digit", minute: "2-digit", hour12: false });

  const c = data.counts;
  const health = document.getElementById("health");
  health.innerHTML = "";
  const span = el("span", c.degraded || c.errors ? "bad" : "good",
    `${c.ok}/${c.total} tiles` + (c.degraded ? ` · ${c.degraded} degraded` : ""));
  span.title = Object.entries(data.errors || {}).map(([k, v]) => `${k}: ${v}`).join("\n") || "all sources returned";
  health.appendChild(span);

  document.getElementById("sources").textContent = "Sources: " + (data.sources || []).join(" · ");
}

function clock() {
  const now = new Date();
  document.getElementById("localtime").textContent =
    now.toLocaleString("en-AU", { weekday: "short", day: "2-digit", month: "short",
      hour: "2-digit", minute: "2-digit", hour12: false });
}

async function load() {
  try {
    const res = await fetch("data/latest.json?t=" + Date.now(), { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    render(await res.json());
  } catch (e) {
    document.getElementById("app").innerHTML =
      '<div class="loading">Could not load data/latest.json — ' + e.message + "</div>";
  }
}

document.getElementById("refresh").addEventListener("click", load);
clock();
setInterval(clock, 30000);
load();
