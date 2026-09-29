"""World Bank Commodity Price Data (the "Pink Sheet"), monthly.

Published as an xlsx on the second business day of each month, covering the month just
ended. Licensed CC BY 4.0 (World Bank Data Catalog, dataset 0038238 "Commodity Prices -
History and Projections"), so republishing with attribution is fine. Parsed with zipfile
and ElementTree - an xlsx is a zip of XML, and pulling in openpyxl would break the
stdlib-only rule for the Actions run.

These are monthly averages, a month behind by construction. They sit on the dashboard
for the series that have no free daily feed (iron ore, thermal coal, tropical timber),
not as a substitute for the daily futures tiles.
"""
import calendar as _cal
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

from httpget import get, get_text

PAGE = "https://www.worldbank.org/en/research/commodity-markets"

# The file lives under a path that changes each year ("...-0050012026/..."), and the old
# paths keep answering HTTP 200. The 2021 path (".../0350012021/...") still serves a
# workbook that simply stops at 2024M12, so a hard-coded URL goes stale silently. We
# scrape the current link off the landing page and only fall back to this one (verified
# 2026-09-29, data to 2026M08) if the scrape finds nothing; the age guard catches the rest.
FALLBACK_URL = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-"
                "0050012026/related/CMO-Historical-Data-Monthly.xlsx")
SHEET = "Monthly Prices"
ATTRIBUTION = "World Bank Commodity Price Data (Pink Sheet), CC BY 4.0"

# The monthly file lands around the 2nd business day, so a healthy series is ~30-65 days
# old. 120 days means at least two releases were missed or the column was frozen.
STALE_AFTER_DAYS = 120
HISTORY_YEARS = 10

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# (tile id, exact column header in row 5, label, unit, note). Copper and aluminium are
# deliberately absent - the dashboard already carries them daily from futures. Both timber
# series were checked 2026-09-29 and still move month to month (not frozen).
SERIES = [
    ("wb_iron_ore", "Iron ore, cfr spot", "Iron ore (62% Fe, CFR China)", "USD/dmtu",
     "Monthly average. The terms-of-trade driver for the AUD and Australian fiscal "
     "revenue - not a direct build cost."),
    ("wb_coal_au", "Coal, Australian", "Thermal coal (Newcastle)", "USD/t",
     "Monthly average, thermal coal FOB Newcastle, 6000 kcal/kg (futures-based since "
     "Feb 2022)."),
    ("wb_sawnwood_my", "Sawnwood, Malaysian", "Sawnwood (Malaysian hardwood)", "USD/m3",
     "Monthly average, Malaysian tropical hardwood - a regional timber benchmark, not "
     "Australian structural pine."),
    ("wb_plywood", "Plywood", "Plywood (SE Asian lauan)", "USc/sheet",
     "Monthly average, lauan 3-ply wholesale, Tokyo. A regional timber price signal, "
     "not an Australian trade price."),
]


def find_url():
    """Current monthly workbook link from the landing page, or the fallback."""
    try:
        html = get_text(PAGE)
        m = re.search(r'href="([^"]+CMO-Historical-Data-Monthly\.xlsx)"', html)
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001 - fall through to the known link
        pass
    return FALLBACK_URL


def _col(ref):
    return re.match(r"[A-Z]+", ref).group()


def read_sheet(raw, name=SHEET):
    """{row_number: {column_letter: str}} for one sheet of an xlsx, via stdlib only."""
    z = zipfile.ZipFile(io.BytesIO(raw))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{_NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))

    # Sheet name -> rId -> part path. The file carries a hidden "Mismatch Details" sheet
    # first, so sheet1.xml is not the prices - resolve by name, never by position.
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rid = None
    for s in wb.iter(f"{_NS}sheet"):
        if s.get("name") == name:
            rid = s.get(f"{_RNS}id")
    if rid is None:
        raise ValueError(f"sheet {name!r} not found")
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = next(r.get("Target") for r in rels if r.get("Id") == rid)
    path = target.lstrip("/") if target.startswith("/") else "xl/" + target

    rows = {}
    for row in ET.fromstring(z.read(path)).iter(f"{_NS}row"):
        cells = {}
        for c in row.findall(f"{_NS}c"):
            v = c.find(f"{_NS}v")
            if v is None or v.text is None:
                continue
            cells[_col(c.get("r"))] = shared[int(v.text)] if c.get("t") == "s" else v.text
        rows[int(row.get("r"))] = cells
    return rows


def period_to_iso(p):
    """'2026M08' -> '2026-08-31' (last day of the month the average covers)."""
    m = re.fullmatch(r"(\d{4})M(\d{2})", (p or "").strip())
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    return date(y, mo, _cal.monthrange(y, mo)[1]).isoformat()


def _num(s):
    # Missing months are "…" or "..." in the sheet, not blanks.
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def fetch_all():
    """Returns (tiles, errors). One bad column never sinks the others."""
    tiles, errors = [], {}
    try:
        url = find_url()
        rows = read_sheet(get(url))
    except Exception as e:  # noqa: BLE001
        return [], {"worldbank": f"{type(e).__name__}: {e}"}

    # Headers sit in row 5, units in row 6, data from row 7 with the period in column A.
    # Locate the header row rather than trusting the number, in case a title line is added.
    hdr_row = next((r for r, c in sorted(rows.items())
                    if any((v or "").strip() == "Iron ore, cfr spot" for v in c.values())), None)
    if hdr_row is None:
        return [], {"worldbank": "header row not found - layout changed"}
    headers = {(v or "").strip(): col for col, v in rows[hdr_row].items()}
    cutoff = date.today().year - HISTORY_YEARS

    for tid, header, label, unit, note in SERIES:
        try:
            col = headers.get(header)
            if col is None:
                raise ValueError(f"column {header!r} not found")
            obs = []
            for r in sorted(rows):
                if r <= hdr_row:
                    continue
                iso = period_to_iso(rows[r].get("A"))
                v = _num(rows[r].get(col))
                if iso and v is not None and int(iso[:4]) >= cutoff:
                    obs.append([iso, round(v, 4)])
            if not obs:
                raise ValueError("no observations")
            asof, value = obs[-1]
            prev = obs[-2][1] if len(obs) > 1 else None
            age = (date.today() - date.fromisoformat(asof)).days
            stale = age > STALE_AFTER_DAYS
            tiles.append({
                "id": tid, "label": label, "panel": "inputs",
                "group": "Global commodity prices (monthly)",
                "value": value, "unit": unit,
                "change": round(value - prev, 4) if prev is not None else None,
                "change_pct": round((value / prev - 1) * 100, 2) if prev else None,
                "period": date.fromisoformat(asof).strftime("%b %Y"),
                "asof": asof, "freq": "M", "age_days": age,
                "spark": obs,
                "source": ATTRIBUTION,
                "note": note,
                "status": "stale" if stale else "ok",
                "stale_reason": (f"last month {asof[:7]} is {age} days old (> {STALE_AFTER_DAYS}d)"
                                 " - workbook link may be an old edition" if stale else None),
            })
        except Exception as e:  # noqa: BLE001
            errors[f"worldbank/{tid}"] = f"{type(e).__name__}: {e}"
    return tiles, errors


if __name__ == "__main__":
    print("  url:", find_url())
    ts, errs = fetch_all()
    for t in ts:
        flag = "  <-- STALE" if t["status"] == "stale" else ""
        print(f"  {t['id']:<16} {t['value']:>10,.2f} {t['unit']:<10} {t['asof']} "
              f"chg={t['change_pct']}% n={len(t['spark'])} age={t['age_days']}d{flag}")
    for k, e in errs.items():
        print(f"  FAIL {k:<24} {e[:90]}")
