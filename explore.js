/* Morning Markets - drill-down view and command line.

   Modelled on the Bloomberg Terminal's two habits worth stealing for a morning read:
   type a name and go (the command line), and click any number to see its history
   (GP / HP / DES in one view). Everything runs on the published JSON - the full
   history for a series is fetched only when its view is opened. */

const Explore = (() => {
  const state = { tiles: [], byId: new Map(), panels: [], cache: new Map(), current: null,
    range: null, pushed: false, cmpRange: "1Y" };

  const RANGES = [
    ["1M", 31], ["3M", 92], ["6M", 183], ["1Y", 366], ["2Y", 731],
    ["5Y", 1827], ["10Y", 3653], ["MAX", Infinity],
  ];
  const RETURNS = [["1W", 7], ["1M", 31], ["3M", 92], ["6M", 183], ["YTD", "ytd"],
    ["1Y", 366], ["3Y", 1096], ["5Y", 1827]];
  const DAY = 86400000;
  // Windows open a few days late so "1Y" on quarterly data lands on the same quarter a
  // year back (30 Jun - 366d is 29 Jun, which would otherwise pick March).
  const SLACK = 4 * DAY;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const $ = (id) => document.getElementById(id);

  /* ------------------------------------------------------------ data model */
  function index(data) {
    state.tiles = [];
    state.byId.clear();
    state.panels = [];
    for (const p of data.panels) {
      const n = p.groups.reduce((k, g) => k + g.tiles.length, 0);
      if (n || (p.id === "curves" && data.curves.length)) state.panels.push(p);
      for (const g of p.groups) {
        for (const t of g.tiles) {
          const rec = { ...t, panelTitle: p.title, panelId: p.id };
          state.tiles.push(rec);
          state.byId.set(t.id, rec);
        }
      }
    }
    // A shared link (#/au_10y) should open straight into the view once data is in.
    route();
  }

  // ABS periods ("2026-Q2", "2026-08") become the last day of the period, so a quarter
  // sits on the axis where its data ends rather than where it began.
  function toTime(p) {
    const s = String(p);
    let m = s.match(/^(\d{4})-Q([1-4])$/);
    if (m) return Date.UTC(+m[1], +m[2] * 3, 0);
    m = s.match(/^(\d{4})-(\d{2})$/);
    if (m) return Date.UTC(+m[1], +m[2], 0);
    const t = Date.parse(s.slice(0, 10) + "T00:00:00Z");
    return Number.isNaN(t) ? null : t;
  }

  function fmtDate(t, freq) {
    const d = new Date(t);
    if (freq === "Q") return `${d.getUTCFullYear()}-Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
    if (freq === "M") return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }

  const isRate = (t) => t.unit === "%" || t.unit === "pp";

  function num(v, t) {
    return fmtValue({ value: v, unit: t.unit });
  }

  // Rates move in basis points; everything else in percent - same rule as the tiles.
  function delta(t, from, to) {
    if (from == null || to == null) return { text: "—", dir: "flat" };
    if (isRate(t)) {
      const bp = Math.round((to - from) * 100);
      return { text: (bp > 0 ? "+" : "") + bp.toLocaleString("en-AU") + " bp", dir: bp > 0 ? "up" : bp < 0 ? "down" : "flat" };
    }
    if (!from) return { text: "—", dir: "flat" };
    const p = (to / from - 1) * 100;
    return { text: (p > 0 ? "+" : "") + p.toFixed(Math.abs(p) >= 100 ? 0 : 2) + "%", dir: p > 0.0001 ? "up" : p < -0.0001 ? "down" : "flat" };
  }

  async function loadHistory(t) {
    if (state.cache.has(t.id)) return state.cache.get(t.id);
    let obs = null, full = false;
    if (t.history) {
      try {
        const res = await fetch(`data/series/${encodeURIComponent(t.id)}.json`, { cache: "no-cache" });
        if (res.ok) { obs = (await res.json()).obs; full = true; }
      } catch (_) { /* fall through to the sparkline */ }
    }
    if (!obs) obs = t.spark || [];
    const pts = obs.map(([d, v]) => [toTime(d), v]).filter(([x, v]) => x != null && v != null);
    pts.sort((a, b) => a[0] - b[0]);
    const out = { pts, full, freq: t.freq || guessFreq(pts) };
    state.cache.set(t.id, out);
    return out;
  }

  function guessFreq(pts) {
    if (pts.length < 3) return "D";
    const gap = (pts[pts.length - 1][0] - pts[0][0]) / (pts.length - 1) / DAY;
    return gap > 60 ? "Q" : gap > 20 ? "M" : "D";
  }

  // Value on or before a date - the "close at the start of the window".
  function valueAt(pts, t) {
    let best = null;
    for (const p of pts) { if (p[0] <= t) best = p; else break; }
    return best;
  }

  /* ------------------------------------------------------------ drill-down */
  function open(id, focus) {
    if (!state.byId.has(id)) return;
    const target = "#/" + encodeURIComponent(id) + (focus ? "/" + focus : "");
    if (location.hash === target) { show(id, focus); return; }
    state.pushed = true;
    location.hash = target;
  }

  function close() {
    if (!state.current) return;
    if (state.pushed) { state.pushed = false; window.history.back(); }
    else { window.history.replaceState(null, "", location.pathname + location.search); hide(); }
  }

  function hide() {
    state.current = null;
    $("drill").hidden = true;
    document.body.classList.remove("modal-open");
  }

  function route() {
    const c = location.hash.match(/^#\/compare(?:\/([^/]*))?$/);
    if (c) {
      const ids = c[1] != null ? decodeURIComponent(c[1]).split(",") : compareList();
      showCompare(ids.filter((id) => state.byId.has(id)));
      return;
    }
    const m = location.hash.match(/^#\/([^/]+)(?:\/(\w+))?/);
    if (m && state.byId.has(decodeURIComponent(m[1]))) show(decodeURIComponent(m[1]), m[2]);
    else if (state.current) hide();
  }

  function siblings(t) {
    return state.tiles.filter((x) => x.panelId === t.panelId && x.status !== "unavailable");
  }

  async function show(id, focus) {
    const t = state.byId.get(id);
    const switching = state.current !== id;
    state.current = id;
    if (switching) state.range = null;
    remember(id);
    const box = $("drill");
    box.hidden = false;
    document.body.classList.add("modal-open");
    const body = $("drill-body");
    if (switching) body.innerHTML = '<div class="loading">Loading history…</div>';

    const h = await loadHistory(t);
    if (state.current !== id) return; // user moved on while this was loading
    renderDrill(t, h);
    if (focus === "hp") $("d-hist")?.scrollIntoView({ block: "start" });
    if (focus === "des") $("d-des")?.scrollIntoView({ block: "start" });
    if (switching) $("drill-close").focus({ preventScroll: true });
  }

  function defaultRange(h) {
    const span = h.pts.length > 1 ? (h.pts[h.pts.length - 1][0] - h.pts[0][0]) / DAY : 0;
    const want = h.freq === "D" ? 366 : 1827;
    return span <= want ? "MAX" : RANGES.find(([, d]) => d === want)[0];
  }

  function renderDrill(t, h) {
    const body = $("drill-body");
    body.innerHTML = "";
    const pts = h.pts;
    const last = pts[pts.length - 1];
    const spanDays = pts.length > 1 ? (last[0] - pts[0][0]) / DAY : 0;
    if (!state.range) state.range = defaultRange(h);

    // Header: where this lives, what it is, what it is now.
    const head = el("div", "d-head");
    const crumbs = el("div", "d-crumbs", `${t.panelTitle}${t.group ? " · " + t.group : ""}`);
    const title = el("h2", "d-title", t.label);
    if (t.symbol) title.appendChild(el("span", "d-sym", t.symbol));
    const now = el("div", "d-now");
    now.appendChild(el("span", "d-value", fmtValue(t)));
    const ch = fmtChange(t);
    now.appendChild(el("span", "t-change " + ch.dir, ch.text));
    now.appendChild(el("span", "d-asof", "as at " + (t.period || t.asof || "—")));
    const acts = el("div", "d-actions");
    const watch = el("button", "d-act" + (isWatched(t.id) ? " on" : ""), isWatched(t.id) ? "★ Watching" : "☆ Watch");
    watch.type = "button";
    watch.title = "Pin to your watchlist (kept in this browser)";
    watch.addEventListener("click", () => { toggleWatch(t.id); renderDrill(t, h); });
    const cmp = el("button", "d-act", "Compare +");
    cmp.type = "button";
    cmp.title = "Chart this against other series, rebased to the same start";
    cmp.addEventListener("click", () => openCompare(addToCompare(t.id)));
    acts.append(watch, cmp);
    head.append(crumbs, title, now, acts);
    body.appendChild(head);

    if (t.status === "stale") {
      body.appendChild(el("div", "d-warn", "STALE — " + (t.stale_reason || "this series is past its normal publication lag")));
    }
    if (!h.full) {
      body.appendChild(el("div", "d-warn", "No history file for this series — the source returned too few points. Showing what the tile carries."));
    }

    // A single print (Yahoo serves ^DJUSRE with no daily bars) has nothing to chart,
    // but its description and source still belong on screen.
    if (pts.length >= 2) {
      // Range buttons (GP). Only offer ranges the data can actually fill.
      const bar = el("div", "d-ranges");
      RANGES.forEach(([label, days], i) => {
        const prev = i ? RANGES[i - 1][1] : 0;
        if (label !== "MAX" && spanDays < prev * 1.05) return;
        if (label !== "MAX" && h.freq !== "D" && days < 366) return; // a quarter or two is not a chart
        const b = el("button", "d-range" + (state.range === label ? " on" : ""), label);
        b.type = "button";
        b.addEventListener("click", () => { state.range = label; renderDrill(t, h); });
        bar.appendChild(b);
      });
      body.appendChild(bar);

      const days = (RANGES.find(([l]) => l === state.range) || RANGES[RANGES.length - 1])[1];
      const from = days === Infinity ? -Infinity : last[0] - days * DAY + SLACK;
      const view = pts.filter(([x]) => x >= from);
      // Include the observation just before the window so a sparse series still has a
      // start value to measure the window's move from.
      const before = valueAt(pts, from);
      const shown = before && view.length && before[0] < view[0][0] ? [before, ...view] : view;

      // Window statistics: move, high, low, and where today sits between them.
      const vals = shown.map((p) => p[1]);
      const hi = Math.max(...vals), lo = Math.min(...vals);
      const move = delta(t, shown[0]?.[1], last[1]);
      const pos = hi > lo ? Math.round(((last[1] - lo) / (hi - lo)) * 100) : null;
      const stats = el("div", "d-stats");
      stat(stats, `${state.range} change`, move.text, move.dir);
      stat(stats, `${state.range} high`, num(hi, t));
      stat(stats, `${state.range} low`, num(lo, t));
      if (pos != null) stat(stats, "position in range", pos + "%", null,
        "0% = at the low of this window, 100% = at the high");
      body.appendChild(stats);

      const chartHost = el("div", "d-chart");
      body.appendChild(chartHost);
      const drawIt = () => Chart.draw(chartHost, shown, {
        dir: move.dir,
        fmtValue: (v) => num(v, t),
        // Dollar series ($1.8m) need the tile's compact format to fit the axis.
        fmtAxis: t.unit === "$" ? (v) => num(v, t) : null,
        fmtDelta: (a, b) => delta(t, a, b),
        fmtDate: (x) => fmtDate(x, h.freq),
      });
      drawIt(); // the view is already visible, so its width is measurable now
      state.redraw = drawIt;

      // Period returns (COMP-lite): the same series across standard windows.
      const rets = el("div", "d-returns");
      for (const [label, d] of RETURNS) {
        let start;
        if (d === "ytd") start = Date.UTC(new Date(last[0]).getUTCFullYear(), 0, 1) - 1;
        else start = last[0] - d * DAY + SLACK;
        if (start < pts[0][0] - 5 * DAY) continue;
        if (h.freq !== "D" && typeof d === "number" && d < 92) continue;
        const base = valueAt(pts, start);
        if (!base) continue;
        const r = delta(t, base[1], last[1]);
        const cell = el("div", "d-ret");
        cell.appendChild(el("span", "d-ret-l", label));
        cell.appendChild(el("span", "t-change " + r.dir, r.text));
        rets.appendChild(cell);
      }
      if (rets.children.length) body.appendChild(rets);
    } else {
      body.appendChild(el("div", "chart-empty", "Not enough history to chart."));
    }

    // Description (DES).
    const des = el("section", "d-sec");
    des.id = "d-des";
    des.appendChild(el("h3", null, "Description"));
    if (t.note) des.appendChild(el("p", "d-note", t.note));
    const dl = el("dl", "d-meta");
    const meta = [
      ["Source", t.source],
      ["Unit", t.unit],
      ["Frequency", { D: "daily", M: "monthly", Q: "quarterly" }[h.freq] || h.freq],
      ["History", pts.length ? `${pts.length.toLocaleString("en-AU")} obs from ${fmtDate(pts[0][0], h.freq)}` : "—"],
      ["Latest", t.period || t.asof],
      ["Code", t.symbol || t.id],
    ];
    for (const [k, v] of meta) {
      if (!v) continue;
      dl.appendChild(el("dt", null, k));
      dl.appendChild(el("dd", null, v));
    }
    des.appendChild(dl);
    body.appendChild(des);
    if (t.profile) body.appendChild(companySection(t));

    // History table (HP), newest first, with CSV of the full series.
    const hp = el("section", "d-sec");
    hp.id = "d-hist";
    const hpHead = el("div", "d-sec-head");
    hpHead.appendChild(el("h3", null, "History"));
    const dlBtn = el("button", null, "Download CSV");
    dlBtn.type = "button";
    dlBtn.addEventListener("click", () => downloadCsv(t, pts, h.freq));
    hpHead.appendChild(dlBtn);
    hp.appendChild(hpHead);
    const table = el("table", "d-table");
    const thead = el("thead");
    const hr = el("tr");
    ["Date", "Value", "Change"].forEach((x) => hr.appendChild(el("th", null, x)));
    thead.appendChild(hr);
    table.appendChild(thead);
    const tb = el("tbody");
    const rows = pts.slice(-15).reverse();
    rows.forEach(([x, v], i) => {
      const prev = pts[pts.length - 2 - i];
      const tr = el("tr");
      tr.appendChild(el("td", null, fmtDate(x, h.freq)));
      tr.appendChild(el("td", null, num(v, t)));
      const d = prev ? delta(t, prev[1], v) : { text: "—", dir: "flat" };
      tr.appendChild(el("td", "t-change " + d.dir, d.text));
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    hp.appendChild(table);
    body.appendChild(hp);

    // Prev / next within the panel, so a morning read can walk a panel without closing.
    const sib = siblings(t);
    const i = sib.findIndex((x) => x.id === t.id);
    $("drill-prev").disabled = i <= 0;
    $("drill-next").disabled = i < 0 || i >= sib.length - 1;
    $("drill-prev").onclick = () => i > 0 && step(-1);
    $("drill-next").onclick = () => i < sib.length - 1 && step(1);
  }

  function step(dir) {
    const t = state.byId.get(state.current);
    if (!t) return;
    const sib = siblings(t);
    const i = sib.findIndex((x) => x.id === t.id);
    const next = sib[i + dir];
    if (!next) return;
    // Replace rather than push, so Back still closes the view instead of rewinding tiles.
    window.history.replaceState(null, "", "#/" + encodeURIComponent(next.id));
    show(next.id);
  }

  function stat(parent, label, value, dir, title) {
    const s = el("div", "d-stat");
    if (title) s.title = title;
    s.appendChild(el("span", "d-stat-l", label));
    s.appendChild(el("span", "d-stat-v" + (dir ? " t-change " + dir : ""), value));
    parent.appendChild(s);
  }

  function downloadCsv(t, pts, freq) {
    const lines = ["date,value"];
    for (const [x, v] of pts) {
      const d = new Date(x);
      const iso = freq === "Q" ? fmtDate(x, "Q") : freq === "M"
        ? `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`
        : d.toISOString().slice(0, 10);
      lines.push(`${iso},${v}`);
    }
    const blob = new Blob([lines.join("\n") + "\n"], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${t.id}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* --------------------------------------------------------- command line */
  // Trailing Bloomberg mnemonics route to a section of the view: "hrc hp" opens the
  // history table, "cash des" the description. GP (or nothing) opens the chart.
  const VERBS = { GP: null, HP: "hp", DES: "des", COMP: "comp" };
  const pal = { items: [], sel: 0 };

  function openPalette(prefill) {
    const box = $("palette");
    box.hidden = false;
    const input = $("pal-input");
    input.value = prefill || "";
    input.focus();
    search();
  }

  function closePalette() {
    $("palette").hidden = true;
  }

  function parseQuery(raw) {
    const words = raw.trim().split(/\s+/).filter(Boolean);
    let verb = null;
    if (words.length > 1 && Object.hasOwn(VERBS, words[words.length - 1].toUpperCase())) {
      verb = VERBS[words.pop().toUpperCase()];
    }
    return { words: words.map((w) => w.toLowerCase()), verb };
  }

  // Score one query word against one item. Exact code > prefix > word-start >
  // substring > in-order letters, so "hrc" finds the steel tile before "Hang Seng".
  function scoreWord(w, item) {
    let best = 0;
    for (const code of item.codes) {
      if (code === w) best = Math.max(best, 120);
      else if (code.startsWith(w)) best = Math.max(best, 70);
    }
    const label = item.label;
    if (label.startsWith(w)) best = Math.max(best, 90);
    else if (item.words.some((x) => x.startsWith(w))) best = Math.max(best, 65);
    else if (label.includes(w)) best = Math.max(best, 40);
    else if (item.context.includes(w)) best = Math.max(best, 25);
    if (!best && w.length >= 2) {
      let j = 0;
      for (const ch of label) if (ch === w[j]) j++;
      if (j === w.length) best = 10;
    }
    return best;
  }

  function paletteIndex() {
    const out = state.tiles.filter((t) => t.status !== "unavailable").map((t) => ({
      kind: "tile", id: t.id, tile: t,
      label: t.label.toLowerCase(),
      words: t.label.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean),
      codes: [t.id.toLowerCase(), (t.symbol || "").toLowerCase().replace(/^[\^]/, "")].filter(Boolean),
      context: `${t.group || ""} ${t.panelTitle}`.toLowerCase(),
    }));
    for (const p of state.panels) {
      out.push({ kind: "panel", id: p.id, panel: p, label: p.title.toLowerCase(),
        words: p.title.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean),
        codes: [p.id], context: (p.subtitle || "").toLowerCase() });
    }
    // Layouts and commands sit in the same index, so "debt" or "compare" is one Enter away.
    for (const v of (typeof VIEWS !== "undefined" ? VIEWS : [])) {
      out.push({ kind: "view", id: v.id, view: v, label: (v.title + " view").toLowerCase(),
        words: [v.id, "view", "layout", ...v.title.toLowerCase().split(/\s+/)],
        codes: [v.id], context: v.hint.toLowerCase() });
    }
    out.push({ kind: "cmd", id: "compare", label: "compare", words: ["compare", "comp", "overlay"],
      codes: ["comp"], context: "chart several series rebased to the same start" });
    for (const pr of PRESETS) {
      out.push({ kind: "preset", id: pr.id, preset: pr, label: pr.title.toLowerCase(),
        words: ["compare", ...pr.title.toLowerCase().split(/[^a-z0-9]+/)], codes: [pr.id], context: pr.hint.toLowerCase() });
    }
    return out;
  }

  function search() {
    const { words } = parseQuery($("pal-input").value);
    const idx = paletteIndex();
    let items;
    if (!words.length) {
      const recent = recall().map((id) => idx.find((x) => x.kind === "tile" && x.id === id)).filter(Boolean);
      items = recent.length ? recent : idx.filter((x) => x.kind === "panel");
      $("pal-hint").textContent = recent.length ? "Recent" : "Panels";
    } else {
      items = idx.map((item) => {
        let total = 0;
        for (const w of words) {
          const s = scoreWord(w, item);
          if (!s) return null;
          total += s;
        }
        return { item, total: total + (item.kind === "panel" ? -5 : 0) };
      }).filter(Boolean).sort((a, b) => b.total - a.total);
      // Loose in-order-letter matches are a fallback, not padding under a real hit.
      const floor = items.length ? items[0].total * 0.3 : 0;
      items = items.filter((x) => x.total >= floor).slice(0, 12).map((x) => x.item);
      $("pal-hint").textContent = items.length ? "" : "No match — try a name, a code like AXJO, or a panel";
    }
    pal.items = items;
    pal.sel = 0;
    drawResults();
  }

  function drawResults() {
    const list = $("pal-list");
    list.innerHTML = "";
    pal.items.forEach((item, i) => {
      const li = el("li", "pal-item" + (i === pal.sel ? " sel" : ""));
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", i === pal.sel ? "true" : "false");
      if (item.kind === "tile") {
        const t = item.tile;
        const left = el("div", "pal-main");
        const name = el("span", "pal-name", t.label);
        if (t.symbol) name.appendChild(el("span", "pal-sym", t.symbol));
        left.appendChild(name);
        left.appendChild(el("span", "pal-ctx", `${t.panelTitle}${t.group ? " · " + t.group : ""}`));
        const right = el("div", "pal-num");
        right.appendChild(el("span", "pal-val", fmtValue(t)));
        const ch = fmtChange(t);
        right.appendChild(el("span", "t-change " + ch.dir, ch.text));
        li.append(left, right);
      } else {
        const left = el("div", "pal-main");
        const [name, ctx] = item.kind === "panel" ? [item.panel.title, "Jump to panel"]
          : item.kind === "view" ? [item.view.title + " layout", item.view.hint]
          : item.kind === "preset" ? [item.preset.title, "Compare · " + item.preset.hint]
          : ["Compare", "Chart several series rebased to the same start (COMP)"];
        left.appendChild(el("span", "pal-name", name));
        left.appendChild(el("span", "pal-ctx", ctx));
        li.appendChild(left);
      }
      li.addEventListener("mousemove", () => { if (pal.sel !== i) { pal.sel = i; drawResults(); } });
      li.addEventListener("click", () => choose(i));
      list.appendChild(li);
    });
    list.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
  }

  function choose(i) {
    const item = pal.items[i];
    if (!item) return;
    const { verb } = parseQuery($("pal-input").value);
    closePalette();
    if (item.kind === "tile" && verb === "comp") openCompare(addToCompare(item.id));
    else if (item.kind === "tile") open(item.id, verb);
    else if (item.kind === "view") setView(item.id);
    else if (item.kind === "preset") openCompare(item.preset.ids.filter((id) => state.byId.has(id)));
    else if (item.kind === "cmd") openCompare(compareList());
    else {
      if (typeof setView === "function" && !document.getElementById("panel-" + item.id)) setView("all");
      document.getElementById("panel-" + item.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  /* --------------------------------------------------------------- recents */
  const RECENT_KEY = "mm.recent";
  function recall() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch (_) { return []; }
  }
  function remember(id) {
    try {
      const list = [id, ...recall().filter((x) => x !== id)].slice(0, 8);
      localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    } catch (_) { /* private mode - recents are a convenience only */ }
  }

  /* ---------------------------------------------------------------- wiring */
  function typing(ev) {
    const t = ev.target;
    return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
  }

  function init() {
    window.addEventListener("hashchange", route);

    // Tiles, screener rows, mover chips - anything carrying data-id opens its view.
    document.getElementById("app").addEventListener("click", (ev) => {
      if (ev.target.closest("[data-nopen], a")) return;
      const tile = ev.target.closest("[data-id]");
      if (tile) open(tile.dataset.id);
    });
    document.getElementById("app").addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (ev.target.closest("[data-nopen], a, button")) return;
      const tile = ev.target.closest("[data-id]");
      if (tile) { ev.preventDefault(); open(tile.dataset.id); }
    });

    $("drill-close").addEventListener("click", close);
    $("drill").addEventListener("click", (ev) => { if (ev.target.id === "drill") close(); });
    $("search").addEventListener("click", () => openPalette());
    $("palette").addEventListener("click", (ev) => { if (ev.target.id === "palette") closePalette(); });

    const input = $("pal-input");
    input.addEventListener("input", search);
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown") { ev.preventDefault(); pal.sel = Math.min(pal.sel + 1, pal.items.length - 1); drawResults(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); pal.sel = Math.max(pal.sel - 1, 0); drawResults(); }
      else if (ev.key === "Enter") { ev.preventDefault(); choose(pal.sel); }
      else if (ev.key === "Escape") { ev.preventDefault(); closePalette(); }
    });

    document.addEventListener("keydown", (ev) => {
      const palOpen = !$("palette").hidden;
      if ((ev.key === "k" && (ev.ctrlKey || ev.metaKey)) || (ev.key === "/" && !typing(ev))) {
        ev.preventDefault();
        openPalette();
        return;
      }
      if (palOpen || typing(ev)) return;
      if (!state.current) return;
      if (ev.key === "Escape") { ev.preventDefault(); close(); }
      else if (ev.key === "ArrowLeft") { ev.preventDefault(); step(-1); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); step(1); }
    });

    let timer;
    window.addEventListener("resize", () => {
      clearTimeout(timer);
      timer = setTimeout(() => state.current && state.redraw && state.redraw(), 120);
    });
  }

  /* --------------------------------------------------------------- compare */
  // Bloomberg COMP for a developer: the pairings that actually decide feasibility.
  const PRESETS = [
    { id: "cap_rates", title: "REITs vs bond yields", hint: "A-REIT index against the AU 10-year - the cap rate squeeze",
      ids: ["asx_areit", "au_10y", "au_bab_3m"] },
    { id: "steel_chain", title: "Steel chain", hint: "HRC futures, steel producers, BlueScope, materials",
      ids: ["hrc_steel", "steel_producers", "eq_bsl_ax", "asx_materials"] },
    { id: "energy_inputs", title: "Energy inputs", hint: "Diesel, Brent, European gas",
      ids: ["diesel", "brent", "ttf_gas"] },
    { id: "rates_path", title: "Rates path", hint: "Cash rate against the 2- and 10-year",
      ids: ["cash_rate", "au_2y", "au_10y"] },
    { id: "housing_cycle", title: "Housing cycle, US vs AU", hint: "US homebuilders against the A-REITs and the ASX 200",
      ids: ["itb", "asx_areit", "asx200"] },
  ];
  const CMP_KEY = "mm.compare";
  const MAX_CMP = 4;

  function compareList() {
    try { return JSON.parse(localStorage.getItem(CMP_KEY) || "[]").filter((id) => state.byId.has(id)); }
    catch (_) { return []; }
  }
  function saveCompare(ids) {
    try { localStorage.setItem(CMP_KEY, JSON.stringify(ids)); } catch (_) { /* convenience only */ }
  }
  function addToCompare(id) {
    const ids = [...compareList().filter((x) => x !== id), id].slice(-MAX_CMP);
    saveCompare(ids);
    return ids;
  }

  function openCompare(ids) {
    const target = "#/compare/" + encodeURIComponent(ids.join(","));
    if (location.hash === target) { showCompare(ids); return; }
    state.pushed = true;
    location.hash = target;
  }

  async function showCompare(ids) {
    ids = ids.slice(0, MAX_CMP);
    saveCompare(ids);
    state.current = "compare";
    $("drill").hidden = false;
    document.body.classList.add("modal-open");
    $("drill-prev").disabled = true;
    $("drill-next").disabled = true;
    const tiles = ids.map((id) => state.byId.get(id));
    if (tiles.some((t) => !state.cache.has(t.id))) {
      $("drill-body").innerHTML = '<div class="loading">Loading history…</div>';
    }
    const hs = await Promise.all(tiles.map(loadHistory));
    if (state.current !== "compare") return;
    renderCompare(tiles, hs);
    $("drill-close").focus({ preventScroll: true });
  }

  function renderCompare(tiles, hs) {
    const body = $("drill-body");
    body.innerHTML = "";
    const head = el("div", "d-head");
    head.appendChild(el("div", "d-crumbs", "Compare · COMP"));
    head.appendChild(el("h2", "d-title", "Change since the window opened"));
    head.appendChild(el("p", "d-sub",
      "Prices rebased to percent, rates in basis points. When both are present, percent reads on the left axis and bp on the right."));
    body.appendChild(head);

    // Series chips, add box, presets.
    const chips = el("div", "cmp-chips");
    tiles.forEach((t, i) => {
      const c = el("span", "cmp-chip");
      c.appendChild(el("i", "sw s" + (i + 1)));
      c.appendChild(document.createTextNode(t.label + (isRate(t) ? " (bp)" : "")));
      const x = el("button", "cmp-x", "✕");
      x.type = "button";
      x.title = "Remove";
      x.addEventListener("click", () => openCompare(tiles.filter((y) => y !== t).map((y) => y.id)));
      c.appendChild(x);
      chips.appendChild(c);
    });
    if (tiles.length < MAX_CMP) {
      const wrap = el("span", "cmp-add");
      const input = el("input");
      input.placeholder = tiles.length ? "+ add series…" : "Type to add a series…";
      input.setAttribute("aria-label", "Add a series to compare");
      const list = el("ul", "cmp-sugg");
      let hits = [];
      input.addEventListener("input", () => {
        const words = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
        list.innerHTML = "";
        if (!words.length) return;
        hits = paletteIndex().filter((x) => x.kind === "tile" && !tiles.some((t) => t.id === x.id))
          .map((item) => ({ item, s: words.reduce((a, w) => (a < 0 ? a : (scoreWord(w, item) || -1) + a), 0) }))
          .filter((x) => x.s > 0).sort((a, b) => b.s - a.s).slice(0, 7).map((x) => x.item);
        hits.forEach((h) => {
          const li = el("li", null, h.tile.label);
          li.appendChild(el("span", "pal-ctx", " " + h.tile.panelTitle));
          li.addEventListener("mousedown", (ev) => { ev.preventDefault(); openCompare([...tiles.map((t) => t.id), h.id]); });
          list.appendChild(li);
        });
      });
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && hits[0]) openCompare([...tiles.map((t) => t.id), hits[0].id]);
        if (ev.key === "Escape") { ev.stopPropagation(); input.blur(); }
      });
      wrap.append(input, list);
      chips.appendChild(wrap);
    }
    body.appendChild(chips);

    const pre = el("div", "cmp-presets");
    pre.appendChild(el("span", "d-stat-l", "Presets"));
    for (const p of PRESETS) {
      const ids = p.ids.filter((id) => state.byId.has(id));
      if (ids.length < 2) continue;
      const b = el("button", "d-act", p.title);
      b.type = "button";
      b.title = p.hint;
      b.addEventListener("click", () => openCompare(ids));
      pre.appendChild(b);
    }
    body.appendChild(pre);

    if (!tiles.length) {
      body.appendChild(el("div", "chart-empty", "Add a series above, pick a preset, or press Compare + on any chart."));
      return;
    }

    const bar = el("div", "d-ranges");
    for (const [label] of RANGES) {
      const b = el("button", "d-range" + (state.cmpRange === label ? " on" : ""), label);
      b.type = "button";
      b.addEventListener("click", () => { state.cmpRange = label; renderCompare(tiles, hs); });
      bar.appendChild(b);
    }
    body.appendChild(bar);

    // Common window: end at the latest print across the set, open "range" before that.
    const end = Math.max(...hs.map((h) => (h.pts.length ? h.pts[h.pts.length - 1][0] : 0)));
    const days = RANGES.find(([l]) => l === state.cmpRange)[1];
    const from = days === Infinity ? Math.max(...hs.map((h) => (h.pts[0] ? h.pts[0][0] : 0))) : end - days * DAY + SLACK;
    const series = tiles.map((t, i) => {
      const pts = hs[i].pts;
      const base = valueAt(pts, from) || pts.find((p) => p[0] >= from);
      const mode = isRate(t) ? "bp" : "pct";
      const inWin = pts.filter((p) => p[0] >= from);
      const withBase = base && inWin.length && base[0] < inWin[0][0] ? [base, ...inWin] : inWin;
      const norm = base ? withBase.map(([x, v]) => [Math.max(x, from), mode === "bp" ? (v - base[1]) * 100 : base[1] ? (v / base[1] - 1) * 100 : 0]) : [];
      return { t, base, last: pts[pts.length - 1], mode, label: t.label, cls: "s" + (i + 1), pts: norm };
    });

    const host = el("div", "d-chart");
    body.appendChild(host);
    const drawIt = () => Chart.compare(host, series, { fmtDate: (x) => fmtDate(x, "D") });
    drawIt();
    state.redraw = drawIt;

    const table = el("table", "d-table cmp-table");
    const hr = el("tr");
    ["Series", "Start", "Latest", "Change", "As at"].forEach((x) => hr.appendChild(el("th", null, x)));
    const thead = el("thead");
    thead.appendChild(hr);
    table.appendChild(thead);
    const tb = el("tbody");
    for (const s of series) {
      const tr = el("tr");
      tr.dataset.id = s.t.id;
      const name = el("td");
      name.appendChild(el("i", "sw " + s.cls));
      name.appendChild(document.createTextNode(s.t.label));
      tr.appendChild(name);
      tr.appendChild(el("td", null, s.base ? num(s.base[1], s.t) : "—"));
      tr.appendChild(el("td", null, s.last ? num(s.last[1], s.t) : "—"));
      const d = s.base && s.last ? delta(s.t, s.base[1], s.last[1]) : { text: "—", dir: "flat" };
      tr.appendChild(el("td", "t-change " + d.dir, d.text));
      tr.appendChild(el("td", null, s.last ? fmtDate(s.last[0], hs[series.indexOf(s)].freq) : "—"));
      tr.addEventListener("click", () => open(s.t.id));
      tb.appendChild(tr);
    }
    table.appendChild(tb);
    body.appendChild(table);
    if (series.some((s) => s.t.freq === "Q" || s.t.freq === "M")) {
      body.appendChild(el("p", "d-sub", "Monthly and quarterly series step on release dates - read their line as a staircase, not a trend between prints."));
    }
  }

  /* --------------------------------------------------------------- company */
  function companySection(t) {
    const sec = el("section", "d-sec");
    sec.id = "d-co";
    sec.appendChild(el("h3", null, "Key statistics"));
    const grid = el("div", "co-grid");
    grid.appendChild(el("div", "loading", "Loading…"));
    sec.appendChild(grid);
    fetch(`data/company/${encodeURIComponent(t.id)}.json`, { cache: "no-cache" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
      .then((p) => {
        grid.innerHTML = "";
        const cur = p.currency || t.unit || "";
        const big = (v) => {
          if (v == null) return null;
          const a = Math.abs(v);
          const s = a >= 1e12 ? (v / 1e12).toFixed(2) + "tn" : a >= 1e9 ? (v / 1e9).toFixed(2) + "bn" : a >= 1e6 ? (v / 1e6).toFixed(1) + "m" : Math.round(v).toLocaleString("en-AU");
          return `${cur} ${s}`;
        };
        const x = (v, dp = 1, suf = "") => (v == null ? null : (+v).toFixed(dp) + suf);
        const rows = [
          ["Market cap", big(p.marketCap)],
          ["Enterprise value", big(p.enterpriseValue)],
          ["P/E (trailing)", x(p.trailingPE, 1, "×")],
          ["P/E (forward)", x(p.forwardPE, 1, "×")],
          ["Price / book", x(p.priceToBook, 2, "×"), "For REITs, below 1× means the market prices the assets under their book value"],
          ["Dividend yield", x(p.dividendYield, 2, "%")],
          ["Debt / equity", x(p.debtToEquity, 0, "%"), "Gearing as Yahoo reports it - check against the company's own covenant definition"],
          ["Total debt", big(p.totalDebt)],
          ["Cash", big(p.totalCash)],
          ["Return on equity", p.returnOnEquity == null ? null : x(p.returnOnEquity * 100, 1, "%")],
          ["Profit margin", p.profitMargins == null ? null : x(p.profitMargins * 100, 1, "%")],
          ["52-week range", p.fiftyTwoWeekLow != null && p.fiftyTwoWeekHigh != null ? `${num(p.fiftyTwoWeekLow, t)} – ${num(p.fiftyTwoWeekHigh, t)}` : null],
          ["Beta", x(p.beta, 2)],
          ["Sector", [p.sector, p.industry].filter(Boolean).join(" · ") || null],
        ];
        for (const [k, v, tip] of rows) {
          if (v == null) continue;
          const c = el("div", "co-cell");
          if (tip) c.title = tip;
          c.appendChild(el("span", "d-stat-l", k));
          c.appendChild(el("span", "co-v", v));
          grid.appendChild(c);
        }
        const foot = el("p", "d-sub", `Yahoo Finance key statistics, refreshed weekly (as at ${String(p.fetched_at || "").slice(0, 10) || "—"}). Unaudited aggregator figures - check filings before relying on any of them.`);
        if (p.website && /^https?:\/\//.test(p.website)) {
          const a = el("a", null, " Company website ↗");
          a.href = p.website;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          foot.appendChild(a);
        }
        sec.appendChild(foot);
      })
      .catch(() => { grid.innerHTML = ""; grid.appendChild(el("div", "d-sub", "Key statistics not available for this company.")); });
    return sec;
  }

  /* ------------------------------------------------------------- watchlist */
  const WATCH_KEY = "mm.watch";
  function watchList() {
    try { return JSON.parse(localStorage.getItem(WATCH_KEY) || "[]"); } catch (_) { return []; }
  }
  function isWatched(id) { return watchList().includes(id); }
  function toggleWatch(id) {
    const list = watchList();
    const next = list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
    try { localStorage.setItem(WATCH_KEY, JSON.stringify(next)); } catch (_) { /* convenience only */ }
    document.dispatchEvent(new CustomEvent("mm:watch", { detail: next }));
  }

  // Cached history belongs to the data file it came from; drop it when that reloads.
  function reset() { state.cache.clear(); }

  init();
  return { index, open, reset, openCompare, watchList, toggleWatch, isWatched, get: (id) => state.byId.get(id) };
})();
