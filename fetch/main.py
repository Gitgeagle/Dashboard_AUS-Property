"""Build data/latest.json for the dashboard.

Design rule: every source is fetched in isolation and any failure degrades one tile
rather than the run. Free endpoints break without notice, and a dashboard that shows
nine good numbers and one grey "stale" tile is far more useful than one that shows an
error page. The exit code stays 0 unless literally nothing was fetched.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tiles  # noqa: E402
from sources import abs as abs_src  # noqa: E402
from sources import crypto, fred, rba, ustreasury, yahoo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SERIES_DIR = os.path.join(DATA, "series")


def log(msg):
    print(msg, flush=True)


def build():
    now = datetime.now(timezone.utc)
    errors = {}
    tile_list = []

    # ---------------------------------------------------------------- RBA
    log("Fetching RBA tables...")
    rba_data, rba_errors = rba.fetch_all()
    for table, err in rba_errors.items():
        errors[f"rba/{table}"] = err
    log(f"  {len(rba_data)} tables, {len(rba_errors)} failed")

    for tid, table, sid, label, panel, group, unit in tiles.RBA:
        series = (rba_data.get(table) or {}).get(sid)
        if not series or not series["obs"]:
            errors[f"tile/{tid}"] = f"RBA {table}/{sid} unavailable"
            tile_list.append({"id": tid, "label": label, "panel": panel, "group": group,
                              "status": "unavailable", "source": f"RBA {table.upper()}"})
            continue
        obs = series["obs"]
        asof, value = obs[-1]
        change, change_pct = tiles.pct_change(obs)
        # A yield moving 4.79 -> 4.835 is +4.5 basis points, not "+0.81%". Percent change
        # of a percentage is not a quantity anyone in rates uses, so rate tiles report
        # the percentage-point move and suppress the ratio.
        if unit == "%":
            change_pct = None
        tile_list.append({
            "id": tid, "label": label, "panel": panel, "group": group,
            "value": value, "unit": unit,
            "change": change, "change_pct": change_pct,
            "asof": asof, "age_days": tiles.age_days(asof),
            "spark": [[d, v] for d, v in obs[-260:]],
            "source": f"RBA {table.upper()}",
            "note": tiles.NOTES.get(tid),
            "status": "ok",
        })

    # -------------------------------------------------------------- Yahoo
    symbols = [y[1] for y in tiles.YAHOO]
    log(f"Fetching {len(symbols)} Yahoo symbols...")
    quotes, yahoo_errors = yahoo.fetch_many(symbols)
    for sym, err in yahoo_errors.items():
        errors[f"yahoo/{sym}"] = err
    log(f"  {len(quotes)} ok, {len(yahoo_errors)} failed")

    for tid, sym, label, panel, group in tiles.YAHOO:
        q = quotes.get(sym)
        if not q:
            tile_list.append({"id": tid, "label": label, "panel": panel, "group": group,
                              "symbol": sym, "status": "unavailable",
                              "source": "Yahoo Finance",
                              "error": yahoo_errors.get(sym)})
            continue
        status = "stale" if q.get("stale") else "ok"
        if status == "stale":
            errors[f"tile/{tid}"] = q.get("stale_reason")
        tile_list.append({
            "id": tid, "label": label, "panel": panel, "group": group, "symbol": sym,
            "value": q["value"], "unit": q.get("currency"),
            "change": q["change"], "change_pct": q["change_pct"],
            "asof": q["asof"], "age_days": q.get("age_days"),
            "spark": q["spark"],
            "source": "Yahoo Finance",
            "note": tiles.NOTES.get(tid),
            "status": status,
            "stale_reason": q.get("stale_reason"),
        })

    # Crypto fallback if Yahoo dropped either pair.
    for tid, pair in (("btc", "BTC-AUD"), ("eth", "ETH-AUD")):
        t = next((x for x in tile_list if x["id"] == tid), None)
        if t and t["status"] == "ok":
            continue
        try:
            value, src = crypto.fetch(pair)
            log(f"  crypto fallback: {pair} via {src}")
            if t:
                t.update({"value": value, "unit": "AUD", "source": src, "status": "ok",
                          "asof": now.date().isoformat(), "age_days": 0,
                          "change": None, "change_pct": None, "spark": []})
        except Exception as e:  # noqa: BLE001
            errors[f"crypto/{pair}"] = f"{type(e).__name__}: {e}"

    # ------------------------------------------------------------ Treasury
    log("Fetching US Treasury yield curve...")
    try:
        treasury_days = ustreasury.fetch()
        log(f"  {len(treasury_days)} trading days")
    except Exception as e:  # noqa: BLE001
        treasury_days = []
        errors["ustreasury"] = f"{type(e).__name__}: {e}"

    # US rate tiles derived from the curve.
    if treasury_days:
        latest = treasury_days[-1]
        prev = treasury_days[-2] if len(treasury_days) > 1 else None
        for years, label, tid in ((2, "US 2-year Treasury", "us_2y"),
                                  (10, "US 10-year Treasury", "us_10y"),
                                  (30, "US 30-year Treasury", "us_30y")):
            v = tiles.yield_at(latest["points"], years)
            if v is None:
                continue
            pv = tiles.yield_at(prev["points"], years) if prev else None
            hist = []
            for d in treasury_days[-260:]:
                yv = tiles.yield_at(d["points"], years)
                if yv is not None:
                    hist.append([d["date"], yv])
            tile_list.append({
                "id": tid, "label": label, "panel": "rates", "group": "United States",
                "value": v, "unit": "%",
                "change": round(v - pv, 3) if pv is not None else None,
                "change_pct": None,
                "asof": latest["date"], "age_days": tiles.age_days(latest["date"]),
                "spark": hist, "source": "US Treasury", "status": "ok",
            })

    # ----------------------------------------------------------- yield curves
    log("Building yield curves...")
    curves = []
    au_curve = tiles.build_au_curve(rba_data)
    if au_curve:
        au_curve["metrics"] = tiles.classify_curve(au_curve["points"])
        au_curve["metrics"]["days_inverted"] = tiles.days_since_inversion(
            tiles.spread_history_au(rba_data))
        curves.append(au_curve)
    else:
        errors["curve/au"] = "could not build Australian curve"

    us_curve = tiles.build_us_curve(treasury_days)
    if us_curve:
        us_curve["metrics"] = tiles.classify_curve(us_curve["points"])
        us_curve["metrics"]["days_inverted"] = tiles.days_since_inversion(
            tiles.spread_history_us(treasury_days))
        curves.append(us_curve)
    else:
        errors["curve/us"] = "could not build US curve"

    # Spread tiles beneath the chart. The curve card already prints the current spread,
    # so these earn their place only by carrying history - whether the curve is
    # steepening or flattening is the actual signal, not today's level.
    spread_hist = {
        "au": tiles.spread_history_au(rba_data),
        "us": tiles.spread_history_us(treasury_days),
    }
    for c in curves:
        m = c["metrics"]
        cc = c["code"]
        for key, label, unit in (("spread_10_2", "10y - 2y spread", "pp"),
                                 ("spread_10_3m", "10y - 3m spread", "pp")):
            if m.get(key) is None:
                continue
            hist = spread_hist.get(cc, []) if key == "spread_10_2" else []
            prev = hist[-2][1] if len(hist) > 1 else None
            tile_list.append({
                "id": f"{cc}_{key}", "label": f"{c['country']}: {label}",
                "panel": "curves", "group": c["country"],
                "value": m[key], "unit": unit,
                "change": round(m[key] - prev, 3) if prev is not None else None,
                "change_pct": None,
                "asof": c["date"], "age_days": tiles.age_days(c["date"]),
                "spark": [[d, v] for d, v in hist[-260:]],
                "source": c["source"], "status": "ok",
                "note": ("Negative = inverted. Rising = steepening."
                         if key == "spread_10_2"
                         else "Negative = inverted. An early recession signal."),
            })

    # ----------------------------------------------------------------- ABS
    log("Fetching ABS series...")
    abs_data, abs_errors = abs_src.fetch_all()
    for sid, err in abs_errors.items():
        errors[f"abs/{sid}"] = err
    log(f"  {len(abs_data)} ok, {len(abs_errors)} failed")

    for sid, s in abs_data.items():
        obs = s["obs"]
        period, value = obs[-1]
        change, change_pct = tiles.pct_change(obs)
        # For series already expressed as a percentage, a percent-change-of-a-percent is
        # meaningless - report the move in percentage points instead.
        is_pct = s.get("unit") == "%"
        tile_list.append({
            "id": sid, "label": s["label"], "panel": "structural",
            "group": "ABS", "value": value, "unit": s.get("unit"),
            "change": change, "change_pct": None if is_pct else change_pct,
            "period": period, "freq": s.get("freq"),
            "asof": period, "age_days": s.get("age_days"),
            "spark": [[p, v] for p, v in obs],
            "source": "ABS Data API", "note": s.get("note"),
            "status": "stale" if s.get("stale") else "ok",
            "stale_reason": s.get("stale_reason"),
        })

    # ------------------------------------------------- capital city property
    log("Fetching ABS capital city property prices...")
    try:
        city = abs_src.fetch_city_property()
        log(f"  {len(city)} series across {len(tiles.CAPITAL_ORDER)} capitals")
    except Exception as e:  # noqa: BLE001
        city = {}
        errors["abs/city_property"] = f"{type(e).__name__}: {e}"

    for kind in ("house", "unit"):
        for region in tiles.CAPITAL_ORDER:
            rec = city.get((region, kind))
            if not rec:
                continue
            obs = rec["obs"]
            period, value = obs[-1]
            _chg, qoq = tiles.pct_change(obs)
            yoy = tiles.yoy_change(obs)
            note = f"Year on year {yoy:+.1f}%" if yoy is not None else None
            tile_list.append({
                "id": f"city_{kind}_{region}", "label": rec["city"],
                "panel": "capital_property", "group": tiles.CITY_GROUPS[kind],
                "value": value, "unit": "$",
                "change": None, "change_pct": qoq,
                "period": period, "freq": "Q",
                "asof": period, "age_days": abs_src.period_age_days(period),
                "spark": [[p, v] for p, v in obs],
                "source": "ABS Data API (RES_DWELL)",
                "note": note, "status": "ok",
            })

    # ---------------------------------------------------------------- FRED
    log("Fetching FRED series...")
    fred_data, fred_errors, fred_skipped = fred.fetch_all()
    for sid, err in fred_errors.items():
        errors[f"fred/{sid}"] = err
    if fred_skipped:
        log(f"  skipped (no FRED_API_KEY): {', '.join(fred_skipped)}")
    else:
        log(f"  {len(fred_data)} ok, {len(fred_errors)} failed")

    for sid, s in fred_data.items():
        if sid in ("brent", "wti"):
            continue  # Yahoo already supplies these with a sparkline
        obs = s["obs"]
        asof, value = obs[-1]
        change, change_pct = tiles.pct_change(obs)
        tile_list.append({
            "id": f"fred_{sid}", "label": s["label"], "panel": "rates",
            "group": "United States", "value": value, "unit": s["unit"],
            "change": change, "change_pct": change_pct,
            "asof": asof, "age_days": tiles.age_days(asof),
            "spark": [[d, v] for d, v in obs[-260:]],
            "source": "FRED", "status": "ok",
        })

    # ------------------------------------------------------------- assemble
    panels = []
    for p in tiles.PANELS:
        pts = [t for t in tile_list if t["panel"] == p["id"]]
        groups, order = {}, []
        for t in pts:
            g = t.get("group") or ""
            if g not in groups:
                groups[g] = []
                order.append(g)
            groups[g].append(t)
        panels.append({**p, "groups": [{"name": g, "tiles": groups[g]} for g in order]})

    ok = sum(1 for t in tile_list if t["status"] == "ok")
    payload = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "panels": panels,
        "curves": curves,
        "errors": errors,
        "counts": {"total": len(tile_list), "ok": ok,
                   "degraded": len(tile_list) - ok, "errors": len(errors)},
        "sources": [
            "RBA statistical tables (F1, F2, F5, F6, F11.1)",
            "US Treasury daily par yield curve",
            "ABS Data API (SDMX-JSON)",
            "Yahoo Finance chart endpoint",
            "Coinbase / Kraken public APIs",
            "FRED" if fred_data else None,
        ],
    }
    payload["sources"] = [s for s in payload["sources"] if s]

    os.makedirs(SERIES_DIR, exist_ok=True)
    out = os.path.join(DATA, "latest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)

    log(f"\nWrote {out}")
    log(f"  {ok}/{len(tile_list)} tiles ok, {len(errors)} issues")
    for k, v in errors.items():
        log(f"    ! {k}: {str(v)[:110]}")

    if ok == 0:
        log("FATAL: no tiles resolved - not publishing")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(build())
