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

  if (t.status !== "unavailable") {
    // Every live tile opens its drill-down (explore.js), by click or keyboard.
    node.dataset.id = t.id;
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", `${t.label}: open chart and history`);
  }

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

  if (typeof Explore !== "undefined" && Explore.isWatched(t.id)) {
    node.appendChild(el("span", "t-star", "★"));
  }
  if (t.thin && t.status !== "stale") node.appendChild(el("span", "badge-stale badge-thin", "THIN"));
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
  // Tenors can print on different days (AU bonds lag bills), so show the span rather
  // than letting the newest print date the whole curve.
  const dates = (c.points || []).map((p) => p.date).filter(Boolean).sort();
  const span = dates.length && dates[0] !== dates[dates.length - 1]
    ? `${dates[0]} → ${dates[dates.length - 1]}` : c.date;
  stat0(stats, "as at", span);
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

  // x tick labels from the current curve. Individual long bonds sit at odd maturities
  // and would crowd the axis, so past 10Y the axis carries round tenors instead.
  const maxYears = Math.max(...c.points.map((p) => p.years));
  const xTicks = c.points.filter((p) => p.instrument !== "bond").map((p) => [p.years, p.tenor]);
  for (const y of [15, 20, 30]) if (maxYears >= y - 0.5 && !xTicks.some(([v]) => v === y)) xTicks.push([y, y + "Y"]);
  for (const [years, tenor] of xTicks) {
    const lab = svgEl("text", { x: px(years), y: H - 8, "text-anchor": "middle",
      fill: "var(--dim)", "font-size": 9.5, "font-family": "var(--mono)" });
    lab.textContent = tenor;
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
      : p.instrument === "bond"
      ? svgEl("circle", { cx: px(p.years), cy: py(p.yield), r: 2.6, fill: "var(--bg)",
          stroke: "var(--accent)", "stroke-width": 1.2 })
      : svgEl("rect", { x: px(p.years) - 2.3, y: py(p.yield) - 2.3, width: 4.6, height: 4.6,
          fill: "none", stroke: "var(--accent)", "stroke-width": 1.2 });
    const title = svgEl("title");
    title.textContent = p.instrument === "bond"
      ? `${p.bond || p.tenor}: ${p.yield}%  (${p.years.toFixed(1)} years to maturity)`
      : `${p.tenor}: ${p.yield}%  (${isGovt ? "government" : p.instrument})`;
    marker.appendChild(title);
    svg.appendChild(marker);
  }
  return svg;
}

/* ----------------------------------------------------------------- layouts */
// Named layouts, Bloomberg Launchpad-style: the same data cut for the question at hand.
const VIEWS = [
  { id: "all", title: "All", hint: "Every panel", panels: null },
  { id: "debt", title: "Debt", hint: "Rates, credit, curves, inflation, calendar",
    panels: ["rates", "credit", "curves", "calendar", "inflation"] },
  { id: "inputs", title: "Inputs", hint: "Commodities, energy, construction costs",
    panels: ["inputs", "structural", "sector"] },
  { id: "cycle", title: "Cycle", hint: "Markets, property, supply pipeline, demand",
    panels: ["equities", "capital_property", "pipeline", "demand", "thematic", "fx"] },
  { id: "stocks", title: "Stocks", hint: "Listed property & construction screener",
    panels: ["universe", "sector"] },
  { id: "watch", title: "Watchlist", hint: "Series you have pinned with ☆ Watch", panels: [] },
];

let DATA = null;
let VIEW = (() => {
  try { return localStorage.getItem("mm.view") || "all"; } catch (_) { return "all"; }
})();

function setView(id) {
  VIEW = VIEWS.some((v) => v.id === id) ? id : "all";
  try { localStorage.setItem("mm.view", VIEW); } catch (_) { /* convenience only */ }
  if (DATA) render(DATA);
  window.scrollTo({ top: 0 });
}

function renderViewBar() {
  const nav = document.getElementById("views");
  nav.innerHTML = "";
  for (const v of VIEWS) {
    const b = el("button", "view-btn" + (VIEW === v.id ? " on" : ""), v.title);
    b.type = "button";
    b.title = v.hint;
    b.setAttribute("aria-pressed", VIEW === v.id ? "true" : "false");
    if (v.id === "watch") {
      const n = Explore.watchList().length;
      if (n) b.appendChild(el("span", "view-n", String(n)));
    }
    b.addEventListener("click", () => setView(v.id));
    nav.appendChild(b);
  }
}

/* ------------------------------------------------------------------ dates */
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Calendar dates are Sydney dates; the reader is in Sydney, so local midnight is right.
function daysUntil(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((new Date(y, m - 1, d) - today) / 86400000);
}
function whenLabel(n) {
  return n === 0 ? "today" : n === 1 ? "tomorrow" : n < 0 ? `${-n}d ago` : `in ${n}d`;
}
function dayLabel(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${DOW[dt.getDay()]} ${d} ${MON[m - 1]}`;
}
function timeLabel(hhmm) {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h + 11) % 12) + 1}${m ? ":" + String(m).padStart(2, "0") : ""}${h < 12 ? "am" : "pm"}`;
}

/* ------------------------------------------------------------------ strips */
// "Next up": the handful of releases that could move rates or costs this fortnight.
function renderNextUp(events) {
  const soon = (events || []).map((e) => ({ ...e, n: daysUntil(e.date) }))
    .filter((e) => e.n >= 0 && e.n <= 14 && e.importance === "high").slice(0, 6);
  if (!soon.length) return null;
  const strip = el("div", "strip");
  strip.appendChild(el("span", "strip-label", "Next up"));
  for (const e of soon) {
    const chip = el(e.url ? "a" : "span", "chip" + (e.n <= 1 ? " hot" : ""));
    if (e.url) { chip.href = e.url; chip.target = "_blank"; chip.rel = "noopener noreferrer"; }
    chip.appendChild(el("span", "chip-cat cat-" + e.category, e.category));
    chip.appendChild(el("span", "chip-title", e.title));
    chip.appendChild(el("span", "chip-when", whenLabel(e.n) + (e.time ? " · " + timeLabel(e.time) : "")));
    strip.appendChild(chip);
  }
  return strip;
}

// Unusual moves: ranked by how far today's move sits outside the series' own normal
// daily range, not by raw percent - see tile_stats in fetch/tiles.py.
function renderMovers(tiles) {
  const scored = tiles.filter((t) => t.z != null && t.panel !== "universe" && t.status === "ok")
    .sort((a, b) => Math.abs(b.z) - Math.abs(a.z));
  if (!scored.length) return null;
  let pick = scored.filter((t) => Math.abs(t.z) >= 2).slice(0, 8);
  const quiet = !pick.length;
  if (quiet) pick = scored.slice(0, 4);
  const strip = el("div", "strip");
  const lab = el("span", "strip-label", quiet ? "Quiet session" : "Unusual moves");
  lab.title = "Today's move divided by the standard deviation of that series' daily moves over the past year. 2σ or more is unusual.";
  strip.appendChild(lab);
  for (const t of pick) {
    const ch = fmtChange(t);
    const chip = el("button", "chip mover");
    chip.type = "button";
    chip.dataset.id = t.id;
    chip.appendChild(el("span", "chip-title", t.label));
    chip.appendChild(el("span", "t-change " + ch.dir, ch.text));
    chip.appendChild(el("span", "chip-when", Math.abs(t.z).toFixed(1) + "σ"));
    strip.appendChild(chip);
  }
  return strip;
}

// The fetch runs weekdays at 17:00 UTC (GitHub often starts it hours late). If the
// published file predates the run that should have landed, say so plainly - a missed
// refresh otherwise looks exactly like a quiet market.
const SCHEDULE_UTC_HOUR = 17;
const SCHEDULE_GRACE_HOURS = 5;
function refreshBanner(data) {
  const now = Date.now();
  const gen = Date.parse(data.generated_at);
  let due = null;
  for (let back = 0; back < 8 && due == null; back++) {
    const d = new Date(now - back * 86400000);
    const run = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), SCHEDULE_UTC_HOUR);
    const wd = new Date(run).getUTCDay();
    if (wd >= 1 && wd <= 5 && run + SCHEDULE_GRACE_HOURS * 3600000 <= now) due = run;
  }
  if (due == null || gen >= due - 3600000) return null;
  const fmt = (t) => new Date(t).toLocaleString("en-AU", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false });
  return el("div", "banner",
    `Missed refresh: this data was published ${fmt(gen)}, and the run due ${fmt(due)} has not landed. ` +
    "Every tile still shows its own as-at date - read those.");
}

/* ------------------------------------------------------- calendar & news */
function renderCalendarPanel(data) {
  const events = (data.calendar || []).map((e) => ({ ...e, n: daysUntil(e.date) })).filter((e) => e.n >= 0);
  const news = data.news || [];
  if (!events.length && !news.length) return null;
  const sec = panelShell({ id: "calendar", title: "Calendar & Releases", cadence: "daily",
    subtitle: "What prints next, and what the RBA, APRA and the Fed said this fortnight. Times are Sydney time." });
  const cols = el("div", "cal-cols");

  const cal = el("div", "cal-col");
  cal.appendChild(el("div", "group-name", "Upcoming releases"));
  const list = el("ul", "cal-list");
  let lastDate = null;
  for (const e of events.slice(0, 40)) {
    if (e.date !== lastDate) {
      list.appendChild(el("li", "cal-day", `${dayLabel(e.date)} · ${whenLabel(e.n)}`));
      lastDate = e.date;
    }
    const li = el("li", "cal-item" + (e.importance === "high" ? " high" : ""));
    li.appendChild(el("span", "cal-time", timeLabel(e.time)));
    li.appendChild(el("span", "chip-cat cat-" + e.category, e.category));
    const t = el(e.url ? "a" : "span", "cal-title", e.title);
    if (e.url) { t.href = e.url; t.target = "_blank"; t.rel = "noopener noreferrer"; }
    li.appendChild(t);
    list.appendChild(li);
  }
  cal.appendChild(list);
  cols.appendChild(cal);

  if (news.length) {
    const nc = el("div", "cal-col");
    nc.appendChild(el("div", "group-name", "Official releases"));
    const nl = el("ul", "cal-list");
    for (const n of news.slice(0, 16)) {
      const li = el("li", "cal-item");
      li.appendChild(el("span", "cal-time", n.date ? dayLabel(n.date.slice(0, 10)).replace(/^\w+ /, "") : ""));
      li.appendChild(el("span", "chip-cat cat-" + n.source, n.source));
      const a = el("a", "cal-title", n.title);
      a.href = n.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      li.appendChild(a);
      nl.appendChild(li);
    }
    nc.appendChild(nl);
    cols.appendChild(nc);
  }
  sec.appendChild(cols);
  return sec;
}

/* ------------------------------------------------------------ screener */
const UNI = { sort: "marketCap", dir: -1, group: "all" };
const UNI_COLS = [
  ["label", "Company", "text"], ["value", "Price", "num"], ["1D", "1D", "ret"], ["1M", "1M", "ret"],
  ["3M", "3M", "ret"], ["YTD", "YTD", "ret"], ["1Y", "1Y", "ret"], ["marketCap", "Mkt cap", "f"],
  ["trailingPE", "P/E", "f"], ["priceToBook", "P/B", "f"], ["dividendYield", "Yield", "f"],
  ["debtToEquity", "Debt/Eq", "f"],
];

function uniValue(t, key, kind) {
  if (kind === "text") return t.label.toLowerCase();
  if (kind === "num") return t.value;
  if (kind === "ret") return t.returns ? t.returns[key] : null;
  return t.fundamentals ? t.fundamentals[key] : null;
}

function compact(v, cur) {
  if (v == null) return "—";
  const a = Math.abs(v);
  const s = a >= 1e12 ? (v / 1e12).toFixed(1) + "tn" : a >= 1e9 ? (v / 1e9).toFixed(1) + "bn" : (v / 1e6).toFixed(0) + "m";
  return (cur && cur !== "AUD" ? cur + " " : "") + s;
}

function renderUniverse(panel) {
  const all = panel.groups.flatMap((g) => g.tiles.map((t) => ({ ...t, group: g.name })));
  const wrap = el("div", "uni");
  const filt = el("div", "uni-filter");
  for (const g of ["all", ...panel.groups.map((x) => x.name)]) {
    const b = el("button", "view-btn" + (UNI.group === g ? " on" : ""), g === "all" ? "All" : g);
    b.type = "button";
    b.addEventListener("click", () => { UNI.group = g; wrap.replaceWith(renderUniverse(panel)); });
    filt.appendChild(b);
  }
  wrap.appendChild(filt);

  const rows = all.filter((t) => UNI.group === "all" || t.group === UNI.group);
  const col = UNI_COLS.find((c) => c[0] === UNI.sort);
  rows.sort((a, b) => {
    const x = uniValue(a, col[0], col[2]), y = uniValue(b, col[0], col[2]);
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (x < y ? -1 : x > y ? 1 : 0) * UNI.dir;
  });

  const scroll = el("div", "uni-scroll");
  const table = el("table", "uni-table");
  const hr = el("tr");
  for (const [key, label, kind] of UNI_COLS) {
    const th = el("th", kind === "text" ? "l" : null);
    const b = el("button", "uni-sort" + (UNI.sort === key ? " on" : ""), label + (UNI.sort === key ? (UNI.dir < 0 ? " ▾" : " ▴") : ""));
    b.type = "button";
    b.addEventListener("click", () => {
      if (UNI.sort === key) UNI.dir = -UNI.dir;
      else { UNI.sort = key; UNI.dir = kind === "text" ? 1 : -1; }
      wrap.replaceWith(renderUniverse(panel));
    });
    th.appendChild(b);
    hr.appendChild(th);
  }
  const thead = el("thead");
  thead.appendChild(hr);
  table.appendChild(thead);
  const tb = el("tbody");
  for (const t of rows) {
    const tr = el("tr", "uni-row" + (t.status !== "ok" ? " is-stale" : ""));
    tr.dataset.id = t.id;
    tr.tabIndex = 0;
    const name = el("td", "l");
    name.appendChild(el("span", "uni-name", t.label));
    name.appendChild(el("span", "pal-sym", t.symbol || ""));
    if (t.sector) name.appendChild(el("span", "uni-sector", t.sector));
    tr.appendChild(name);
    tr.appendChild(el("td", null, fmtValue(t)));
    for (const k of ["1D", "1M", "3M", "YTD", "1Y"]) {
      const v = t.returns ? t.returns[k] : null;
      tr.appendChild(el("td", "t-change " + (v > 0 ? "up" : v < 0 ? "down" : "flat"), v == null ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"));
    }
    const f = t.fundamentals || {};
    tr.appendChild(el("td", null, compact(f.marketCap, f.currency || t.unit)));
    tr.appendChild(el("td", null, f.trailingPE == null ? "—" : f.trailingPE.toFixed(1)));
    tr.appendChild(el("td", null, f.priceToBook == null ? "—" : f.priceToBook.toFixed(2)));
    tr.appendChild(el("td", null, f.dividendYield == null ? "—" : f.dividendYield.toFixed(1) + "%"));
    tr.appendChild(el("td", null, f.debtToEquity == null ? "—" : Math.round(f.debtToEquity) + "%"));
    tb.appendChild(tr);
  }
  table.appendChild(tb);
  scroll.appendChild(table);
  wrap.appendChild(scroll);
  wrap.appendChild(el("p", "d-sub", "Returns are price only (no dividends), in each stock's own currency. Market caps in other currencies are shown in that currency, so sorting across regions compares unlike units. Valuation and gearing are Yahoo Finance aggregates, refreshed weekly."));
  return wrap;
}

/* ------------------------------------------------------------------ render */
function panelShell(panel) {
  const slow = (panel.cadence || "").includes("quarterly") && !(panel.cadence || "").includes("daily") && panel.view !== "table";
  const sec = el("section", "panel" + (slow ? " slow" : ""));
  sec.id = "panel-" + panel.id;
  const head = el("div", "panel-head");
  head.appendChild(el("h2", null, panel.title));
  if (panel.cadence) head.appendChild(el("span", "cadence", panel.cadence));
  if (panel.subtitle) head.appendChild(el("div", "panel-sub", panel.subtitle));
  sec.appendChild(head);
  return sec;
}

function tileGroups(sec, groups) {
  for (const g of groups) {
    if (!g.tiles.length) continue;
    const grp = el("div", "group");
    if (g.name) grp.appendChild(el("div", "group-name", g.name));
    const grid = el("div", "grid");
    g.tiles.forEach((t) => grid.appendChild(renderTile(t)));
    grp.appendChild(grid);
    sec.appendChild(grp);
  }
}

function render(data) {
  DATA = data;
  const app = document.getElementById("app");
  app.innerHTML = "";
  renderViewBar();

  const allTiles = data.panels.flatMap((p) => p.groups.flatMap((g) => g.tiles));
  const banner = refreshBanner(data);
  if (banner) app.appendChild(banner);
  const strips = el("div", "strips");
  for (const s of [renderNextUp(data.calendar), renderMovers(allTiles)]) if (s) strips.appendChild(s);
  if (strips.children.length) app.appendChild(strips);

  const view = VIEWS.find((v) => v.id === VIEW) || VIEWS[0];
  if (view.id === "watch") {
    const ids = Explore.watchList();
    const byId = new Map(allTiles.map((t) => [t.id, t]));
    const sec = panelShell({ id: "watch", title: "Watchlist", cadence: "yours",
      subtitle: "Pinned with ☆ Watch on any chart. Kept in this browser only." });
    const picked = ids.map((id) => byId.get(id)).filter(Boolean);
    if (picked.length) tileGroups(sec, [{ name: "", tiles: picked }]);
    else sec.appendChild(el("p", "d-sub", "Nothing pinned yet. Open any tile or stock and press ☆ Watch."));
    app.appendChild(sec);
  }

  const wanted = view.panels;
  const show = (id) => wanted === null || (wanted && wanted.includes(id));
  for (const panel of data.panels) {
    const tileCount = panel.groups.reduce((n, g) => n + g.tiles.length, 0);
    const isCurves = panel.id === "curves";
    if (show(panel.id) && (tileCount || (isCurves && data.curves.length))) {
      const sec = panelShell(panel);
      if (isCurves && data.curves.length) {
        const wrap = el("div", "curves");
        data.curves.forEach((c) => wrap.appendChild(renderCurve(c)));
        sec.appendChild(wrap);
      }
      if (panel.view === "table") sec.appendChild(renderUniverse(panel));
      else tileGroups(sec, panel.groups);
      app.appendChild(sec);
    }
    // The calendar reads best straight after the curve: "here is the shape, here is
    // what could move it next".
    if (isCurves && show("calendar")) {
      const cal = renderCalendarPanel(data);
      if (cal) app.appendChild(cal);
    }
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

  Explore.index(data);
}

// Pinning from a chart re-renders the page behind it, so stars and the Watchlist
// count stay current without a reload.
document.addEventListener("mm:watch", () => { if (DATA) render(DATA); });

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
    Explore.reset();
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
