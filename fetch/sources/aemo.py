"""AEMO NEM wholesale electricity prices, from the public monthly price-and-demand CSVs.

One file per region per month, 5-minute regional reference prices (RRP, $/MWh). Keyless
and public. AEMO grants general permission to use its published material for any purpose
with attribution to AEMO as the source (aemo.com.au/privacy-and-legal-notices/
copyright-permissions) - hence "Source: AEMO" on every tile.

Electricity is a live input cost for site works, concrete batching and anything running
cranes and hoists on grid power, and a leading read on retail tariffs.

Only the current and previous month are downloaded each run - pulling ten years of files
nightly would be ~600 requests. History accumulates instead in the series file main.py
already writes for each tile.
"""
import json
import os
import time
from datetime import date, datetime, timedelta, timezone

from httpget import get_text

# The bare aemo.com.au host 301s to www - use www directly.
URL = "https://www.aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_{ym}_{region}.csv"
PAUSE = 0.5          # a public file server, not an API - be gentle
BACKFILL_MONTHS = 12  # first run only: a year of history on top of the two live months
WINDOW = 30           # days in the headline rolling average
STALE_AFTER_DAYS = 5  # files update daily; a few days' slack covers a weekend outage
SOURCE = "AEMO (Source: AEMO)"

# NEM market time is AEST all year - no daylight saving - regardless of the region.
NEM_TZ = timezone(timedelta(hours=10))

# (tile id, AEMO region, label)
REGIONS = [
    ("elec_nsw", "NSW1", "NSW"),
    ("elec_qld", "QLD1", "Queensland"),
    ("elec_vic", "VIC1", "Victoria"),
    ("elec_sa", "SA1", "South Australia"),
    ("elec_tas", "TAS1", "Tasmania"),
]

# A 5-minute day has 288 intervals. Keep a day only if nearly all are present, so a
# partly-published day never drags an average around.
MIN_INTERVALS = 276


def _months_back(today, n):
    """['YYYYMM', ...] for this month and the n months before it, oldest first."""
    y, m = today.year, today.month
    out = []
    for _ in range(n + 1):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def parse_daily(csv_text):
    """{iso_date: mean RRP} from one month's CSV.

    SETTLEMENTDATE is the END of each 5-minute interval, so a file runs 00:05 on the 1st
    to 00:00 on the 1st of the next month. That final 00:00 row belongs to the last day
    of the month, not the next - shift every stamp back five minutes before taking the date.
    """
    sums, counts = {}, {}
    lines = csv_text.splitlines()
    if not lines:
        return {}
    head = [h.strip().upper() for h in lines[0].split(",")]
    try:
        i_dt, i_rrp = head.index("SETTLEMENTDATE"), head.index("RRP")
    except ValueError:
        raise ValueError(f"unexpected CSV header: {lines[0][:80]}")
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) <= max(i_dt, i_rrp):
            continue
        try:
            ts = datetime.strptime(parts[i_dt].strip().strip('"'), "%Y/%m/%d %H:%M:%S")
            rrp = float(parts[i_rrp])
        except ValueError:
            continue
        d = (ts - timedelta(minutes=5)).date().isoformat()
        sums[d] = sums.get(d, 0.0) + rrp
        counts[d] = counts.get(d, 0) + 1
    return {d: sums[d] / counts[d] for d in sums if counts[d] >= MIN_INTERVALS}


def rolling(daily, window=WINDOW):
    """[(date, mean of the trailing `window` calendar days)] where every day is present.

    Only full windows are emitted: a 30-day average built from 12 days is a different
    number, and it would overwrite a good value already in the history file.
    """
    out = []
    for d in sorted(daily):
        dd = date.fromisoformat(d)
        vals = [daily.get((dd - timedelta(days=k)).isoformat()) for k in range(window)]
        if all(v is not None for v in vals):
            out.append((d, round(sum(vals) / window, 2)))
    return out


def _load_history(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {d: v for d, v in (json.load(f).get("obs") or [])}
    except FileNotFoundError:
        return None
    except Exception:  # noqa: BLE001 - corrupt file: rebuild as if first run
        return None


def fetch_all(series_dir):
    """Returns (tiles, errors).

    The history file for each tile holds the 30-day rolling series (it is written by
    main.py from this tile's spark), so the merge is rolling-onto-rolling: fresh values
    overwrite the same dates, older dates survive from previous runs. Raw daily averages
    are not persisted; the latest one rides in the note.
    """
    tiles, errors = [], {}
    today = datetime.now(NEM_TZ).date()
    first = True
    for tid, region, label in REGIONS:
        try:
            hist = _load_history(os.path.join(series_dir, f"{tid}.json"))
            months = _months_back(today, 1 if hist else 1 + BACKFILL_MONTHS)
            daily, fails = {}, []
            for ym in months:
                if not first:
                    time.sleep(PAUSE)
                first = False
                try:
                    daily.update(parse_daily(get_text(URL.format(ym=ym, region=region))))
                except Exception as e:  # noqa: BLE001 - early in a month the file may not exist yet
                    fails.append(f"{ym}: {type(e).__name__}")
            if not daily:
                raise ValueError(f"no daily data ({'; '.join(fails) or 'empty files'})")
            if fails:
                errors[f"aemo/{tid}/partial"] = "; ".join(fails)

            merged = dict(hist or {})
            merged.update(dict(rolling(daily)))
            cutoff = (today - timedelta(days=365 * 10)).isoformat()
            obs = [[d, v] for d, v in sorted(merged.items()) if d >= cutoff]
            if not obs:
                raise ValueError("not enough consecutive days for a 30-day average")

            asof, value = obs[-1]
            prev = obs[-2][1] if len(obs) > 1 else None
            last_day = max(daily)
            y_avg = daily[last_day]
            age = (today - date.fromisoformat(asof)).days
            stale = age > STALE_AFTER_DAYS
            tiles.append({
                "id": tid, "label": f"{label} wholesale (30-day avg)",
                "panel": "inputs", "group": "Electricity (NEM wholesale)",
                "value": value, "unit": "$/MWh",
                "change": round(value - prev, 2) if prev is not None else None,
                "change_pct": round((value / prev - 1) * 100, 2) if prev else None,
                "asof": asof, "freq": "D", "age_days": age,
                "spark": obs,
                "source": SOURCE,
                "note": (f"{date.fromisoformat(last_day).strftime('%a %d %b')} daily average "
                         f"${y_avg:,.2f}/MWh. Trailing 30-day mean of daily average spot "
                         f"prices ({region}). Source: AEMO."),
                "status": "stale" if stale else "ok",
                "stale_reason": (f"last full day {asof} is {age} days old" if stale else None),
            })
        except Exception as e:  # noqa: BLE001
            errors[f"aemo/{tid}"] = f"{type(e).__name__}: {e}"
    return tiles, errors


if __name__ == "__main__":
    # Point at a scratch directory so a test run never touches data/series. An empty
    # directory exercises the first-run backfill; run twice to exercise the merge.
    import sys
    import tempfile
    d = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="aemo_")
    ts, errs = fetch_all(d)
    for t in ts:
        flag = "  <-- STALE" if t["status"] == "stale" else ""
        print(f"  {t['id']:<9} {t['value']:>9,.2f} {t['unit']} {t['asof']} "
              f"chg={t['change']} n={len(t['spark'])} from {t['spark'][0][0]}{flag}")
        print(f"            {t['note']}")
    for k, e in errs.items():
        print(f"  FAIL {k:<22} {e[:100]}")
