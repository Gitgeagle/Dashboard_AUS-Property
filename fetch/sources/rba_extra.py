"""Additional RBA tables: corporate bond yields, business lending rates, credit growth,
and the long end of the government curve.

Kept apart from rba.py so these tiles can be added (or dropped) without touching the
core rates panel. Same design rule as everywhere else: each table is fetched in
isolation and a failure costs only that table's tiles.

Series IDs below were read off the live CSV headers (Sep 2026), not recalled. The one
exception is F16, whose IDs roll as bonds mature - those are selected from metadata.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

import tiles
from httpget import get_text
from sources import rba

# Daily tables go stale fast; monthly tables publish about a month after the reference
# month. Past these, the series is more likely discontinued than late.
STALE_AFTER_DAYS = {"D": 10, "M": 120, "Q": 300}

# (id, series_id, label, target tenor in years)
# F3 is month-end, so a tile here moves once a month even though the page refreshes daily.
F3 = [
    ("corp_bbb_3y", "FNFYBBB3M", "BBB corporate 3y", 3),
    ("corp_bbb_5y", "FNFYBBB5M", "BBB corporate 5y", 5),
    ("corp_bbb_7y", "FNFYBBB7M", "BBB corporate 7y", 7),
    ("corp_bbb_10y", "FNFYBBB10M", "BBB corporate 10y", 10),
    ("corp_a_3y", "FNFYA3M", "A corporate 3y", 3),
    ("corp_a_5y", "FNFYA5M", "A corporate 5y", 5),
    ("corp_a_7y", "FNFYA7M", "A corporate 7y", 7),
    ("corp_a_10y", "FNFYA10M", "A corporate 10y", 10),
]
F3_GROUP = "Corporate bond yields"
F3_NOTE = ("RBA month-end aggregate of non-financial corporate bonds at a {tenor}y target "
           "tenor. Investment-grade issuers - a floor for what private development debt costs.")

# F3 carries no spread series (checked: only yield, effective tenor and bond-count
# columns). The spread to government bonds is computed here against the F2 CGS yield
# on the same month-end date. The effective tenor of the BBB bucket drifts from its
# target (e.g. 4.9y for the "5y" bucket, 8.3y for "10y"), so the spread is indicative.
F3_SPREADS = [
    ("corp_bbb_5y_spread", "FNFYBBB5M", "FNFTBBB5M", "FCMYGBAG5D", "BBB 5y spread to CGS", 5),
    ("corp_bbb_10y_spread", "FNFYBBB10M", "FNFTBBB10M", "FCMYGBAG10D", "BBB 10y spread to CGS", 10),
]

# F7 - "Total" is the average across fixed and variable on loans funded in the month.
# History starts Jul-2019 (the ABS/APRA EFS collection), so no deeper sparkline exists.
F7 = [
    ("biz_rate_small_new", "FLRBFNSBT", "Small business - new loans"),
    ("biz_rate_medium_new", "FLRBFNMBT", "Medium business - new loans"),
    ("biz_rate_large_new", "FLRBFNLBT", "Large business - new loans"),
]
F7_GROUP = "Business lending rates"
F7_NOTE = ("Average rate on new business loans funded in the month. Closest free read on "
           "development/construction facility pricing - not a quote.")

# D1 - 12-month ended growth. Trap: DGFACB12 ("Business") and DGFAC12 ("Total") still
# come back in the CSV but stop at Jun-2019 - they were replaced by the non-financial
# business series below. The stale guard would catch them, but don't use them.
D1 = [
    ("credit_housing", "DGFACH12", "Housing credit", "Total housing credit, 12-month ended growth."),
    ("credit_owner_occ", "DGFACOH12", "Owner-occupier housing", None),
    ("credit_investor", "DGFACIH12", "Investor housing",
     "Investor credit running ahead of owner-occupier is what APRA macroprudential limits target."),
    ("credit_business", "DGFACBNF12", "Business credit",
     "Non-financial business credit. Replaced the old 'Business' series (DGFACB12) in 2019."),
]
D1_GROUP = "Credit growth (12-month)"


def _status(freq, asof):
    age = tiles.age_days(asof)
    limit = STALE_AFTER_DAYS.get(freq, 300)
    if age is not None and age > limit:
        return age, "stale", (f"last observation {asof} is {age} days old "
                              f"(> {limit}d for {freq}) - series may be discontinued")
    return age, "ok", None


def _rate_tile(tid, obs, label, group, source, note, freq="M", panel="credit"):
    """Tile for a series already in per cent: change in pp, no ratio."""
    asof, value = obs[-1]
    change, _pct = tiles.pct_change(obs)
    age, status, reason = _status(freq, asof)
    return {
        "id": tid, "label": label, "panel": panel, "group": group,
        "value": value, "unit": "%",
        "change": change, "change_pct": None,
        "asof": asof, "freq": freq, "age_days": age,
        "spark": [[d, v] for d, v in obs],
        "source": source, "note": note,
        "status": status, "stale_reason": reason,
    }


def _series_tiles(table, spec, group, source, note_fn, errors):
    """Fetch one table and build a tile per (id, sid, label, ...) row."""
    out = []
    try:
        data = rba.fetch_table(table)
    except Exception as e:  # noqa: BLE001
        errors[f"rba/{table}"] = f"{type(e).__name__}: {e}"
        return out, None
    for row in spec:
        tid, sid, label = row[:3]
        obs = (data.get(sid) or {}).get("obs") or []
        if len(obs) < 2:
            errors[f"tile/{tid}"] = f"RBA {table.upper()}/{sid} missing or empty"
            continue
        out.append(_rate_tile(tid, obs, label, group, source, note_fn(row)))
    return out, data


def _f3_spreads(f3, errors):
    """BBB less CGS at matching month-end dates, in percentage points."""
    out = []
    try:
        f2 = rba.fetch_table("f2")
    except Exception as e:  # noqa: BLE001
        errors["rba/f2_for_spreads"] = f"{type(e).__name__}: {e}"
        return out
    for tid, ysid, tsid, gsid, label, tenor in F3_SPREADS:
        corp = (f3.get(ysid) or {}).get("obs") or []
        govt = (f2.get(gsid) or {}).get("obs") or []
        eff = dict((f3.get(tsid) or {}).get("obs") or [])
        if not corp or not govt:
            errors[f"tile/{tid}"] = f"RBA F3/{ysid} or F2/{gsid} missing"
            continue
        hist = []
        for d, y in corp:
            # F3 dates are calendar month-end; F2 skips weekends/holidays, so take the
            # last CGS print on or before it (never more than a few days earlier).
            hit = tiles.nearest_on_or_before(govt, d)
            if hit and (datetime.strptime(d, "%Y-%m-%d") -
                        datetime.strptime(hit[0], "%Y-%m-%d")).days <= 7:
                hist.append((d, round(y - hit[1], 3)))
        if len(hist) < 2:
            errors[f"tile/{tid}"] = "not enough overlapping F2/F3 history"
            continue
        t = _rate_tile(tid, hist, label, F3_GROUP, "RBA F3 less F2", None)
        t["unit"] = "pp"
        e = eff.get(hist[-1][0])
        t["note"] = (f"BBB {tenor}y bucket yield less the {tenor}y government bond. "
                     f"Bucket's effective tenor is {e:.1f}y, so this is indicative."
                     if e else f"BBB {tenor}y bucket yield less the {tenor}y government bond.")
        out.append(t)
    return out


# ------------------------------------------------------------------ F16 long end
# F16 lists every Treasury Bond and Treasury Indexed Bond on issue, one column each.
# Series IDs are built from the maturity (FCMYAPR37D) and new columns appear as bonds
# are issued, so the bond set is read from the Description row every run:
#   "Treasury Bond 144 3.75% 21-Apr-2037"  /  "Treasury Indexed Bond 413 1.25% 21-Aug-2040"
# The CSV lags a couple of business days (published 25-Sep with data to 23-Sep).
F16_DESC = re.compile(r"^Treasury Bond\s+(\d+)\s+([\d.]+)%\s+(\d{1,2}-[A-Za-z]{3}-\d{4})\s*$")
LONG_END_MIN_YEARS = 10.5
# Tenor labels are round(years), so two bonds can share one (Apr-37 and Oct-37 both
# read "11Y"). Plot on "years", use "tenor"/"bond" only for labels.


def _fetch_f16():
    """[{"sid", "bond", "maturity": date, "obs": [(iso, yield)]}] for nominal TBs only."""
    text = get_text(rba.BASE.format("f16"))
    rows = list(csv.reader(io.StringIO(text)))
    titles = descs = ids = None
    start = None
    for i, row in enumerate(rows):
        if not row:
            continue
        k = row[0].strip().lower()
        if k == "title":
            titles = row
        elif k == "description":
            descs = row
        elif k == "series id":
            ids, start = row, i + 1
            break
    if ids is None or descs is None:
        raise ValueError("RBA F16: metadata rows not found")

    bonds = {}
    for col in range(1, len(ids)):
        title = (titles[col] if titles and col < len(titles) else "").strip()
        desc = (descs[col] if col < len(descs) else "").strip()
        # Title separates "Treasury Bond" from "Treasury Indexed Bond"; the description
        # regex is anchored on "Treasury Bond " as a second guard against TIBs (real yields).
        if title != "Treasury Bond":
            continue
        m = F16_DESC.match(desc)
        if not m:
            continue
        mat = datetime.strptime(m.group(3), "%d-%b-%Y").date()
        bonds[col] = {"sid": ids[col].strip(), "maturity": mat,
                      "bond": f"TB {float(m.group(2)):.2f}% {mat.strftime('%b %Y')}",
                      "obs": []}

    for row in rows[start:]:
        if not row or not row[0].strip():
            continue
        d = rba._parse_date(row[0])
        if not d:
            continue
        for col, b in bonds.items():
            if col < len(row) and row[col].strip():
                try:
                    b["obs"].append((d, float(row[col])))
                except ValueError:
                    pass
    return [b for b in bonds.values() if b["obs"]]


def _long_snapshot(bonds, target):
    """Long-end points on the last F16 date on or before target."""
    dates = sorted({d for b in bonds for d, _ in b["obs"] if d <= target})
    if not dates:
        return None, []
    snap = dates[-1]
    sdate = datetime.strptime(snap, "%Y-%m-%d").date()
    pts = []
    for b in bonds:
        y = dict(b["obs"]).get(snap)
        if y is None:
            continue
        years = (b["maturity"] - sdate).days / 365.25
        if years <= LONG_END_MIN_YEARS:
            continue
        pts.append({"tenor": f"{round(years)}Y", "years": round(years, 2), "yield": y,
                    "instrument": "govt", "date": snap, "bond": b["bond"]})
    pts.sort(key=lambda p: p["years"])
    return snap, pts


def fetch_long_end(bonds=None):
    """Nominal Treasury Bonds beyond 10.5 years, now / ~1 month ago / ~1 year ago.

    Individual bond yields, not an interpolated curve - the tenors fall where the bonds
    happen to mature, and they roll down by a year every year.
    """
    if bonds is None:
        bonds = _fetch_f16()
    today = date.today()
    snap, now = _long_snapshot(bonds, today.isoformat())
    if not now:
        raise ValueError("RBA F16: no nominal bonds beyond 10.5 years")
    _, month = _long_snapshot(bonds, (today - timedelta(days=30)).isoformat())
    _, year = _long_snapshot(bonds, (today - timedelta(days=365)).isoformat())
    return {"date": snap, "points": now, "month_ago": month, "year_ago": year}


def _long_bond_tile(bonds):
    latest = max(d for b in bonds for d, _ in b["obs"])
    live = [b for b in bonds if b["obs"][-1][0] == latest]
    b = max(live, key=lambda x: x["maturity"])
    t = _rate_tile("au_long_bond", b["obs"], f"AU {b['maturity'].year} bond", "Australia",
                   "RBA F16", None, freq="D", panel="rates")
    years = (b["maturity"] - datetime.strptime(latest, "%Y-%m-%d").date()).days / 365.25
    t["note"] = (f"{b['bond']}, the longest nominal bond on issue ({years:.0f}y to maturity). "
                 "A single bond, so its tenor shortens over time and history starts at issue.")
    return t


def fetch_all():
    tile_list, errors = [], {}

    f3_tiles, f3 = _series_tiles(
        "f3", F3, F3_GROUP, "RBA F3",
        lambda r: F3_NOTE.format(tenor=r[3]), errors)
    tile_list += f3_tiles
    if f3:
        tile_list += _f3_spreads(f3, errors)

    t, _ = _series_tiles("f7", F7, F7_GROUP, "RBA F7", lambda r: F7_NOTE, errors)
    tile_list += t

    t, _ = _series_tiles("d1", D1, D1_GROUP, "RBA D1", lambda r: r[3], errors)
    tile_list += t

    try:
        tile_list.append(_long_bond_tile(_fetch_f16()))
    except Exception as e:  # noqa: BLE001
        errors["rba/f16"] = f"{type(e).__name__}: {e}"

    return tile_list, errors


if __name__ == "__main__":
    ts, errs = fetch_all()
    for t in ts:
        print(f"  {t['id']:<24} {t['value']:>8.3f} {t['unit']:<3} {t['asof']:<11} "
              f"n={len(t['spark']):<4} chg={t['change']} {t['status']}  {t['label']}")
    le = fetch_long_end()
    print(f"\nLong end {le['date']}: {len(le['points'])} bonds; "
          f"month_ago {len(le['month_ago'])}, year_ago {len(le['year_ago'])}")
    for p in le["points"]:
        print(f"    {p['tenor']:>4} {p['years']:>6.2f}y {p['yield']:.3f}  {p['bond']}")
    for k in ("month_ago", "year_ago"):
        if le[k]:
            print(f"  {k}: {le[k][0]['date']} {[p['tenor'] for p in le[k]]}")
    for k, e in errs.items():
        print(f"  FAIL {k}: {e}")
