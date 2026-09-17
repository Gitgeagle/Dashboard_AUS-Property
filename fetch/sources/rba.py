"""RBA statistical tables.

The published CSVs carry a block of metadata rows (Title / Description / Frequency /
Type / Units / Source / Publication date / Series ID) before the observations start,
so we locate the 'Series ID' row and treat everything after it as data.
"""
import csv
import io
from datetime import datetime

from httpget import get_text

BASE = "https://www.rba.gov.au/statistics/tables/csv/{}-data.csv"

# Tables we pull, and the series within each that we care about.
TABLES = {
    "f1": "Money market - daily",
    "f2": "Government bond yields - daily",
    "f5": "Indicator lending rates",
    "f6": "Housing lending rates",
    "f11.1": "Exchange rates - daily",
}


def _parse_date(s):
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_table(table):
    """Return {series_id: {"title":..., "units":..., "obs": [(iso_date, float), ...]}}."""
    text = get_text(BASE.format(table))
    rows = list(csv.reader(io.StringIO(text)))

    meta = {}
    header_idx = None
    for i, row in enumerate(rows):
        if not row:
            continue
        key = row[0].strip().lower()
        if key in ("title", "units", "frequency", "description", "publication date"):
            meta[key] = row
        if key == "series id":
            header_idx = i
            ids = row
            break
    if header_idx is None:
        raise ValueError(f"RBA {table}: no 'Series ID' row found")

    out = {}
    for col in range(1, len(ids)):
        sid = ids[col].strip()
        if not sid:
            continue
        out[sid] = {
            "title": (meta.get("title", [])[col] if col < len(meta.get("title", [])) else "").strip(),
            "units": (meta.get("units", [])[col] if col < len(meta.get("units", [])) else "").strip(),
            "obs": [],
        }

    for row in rows[header_idx + 1:]:
        if not row or not row[0].strip():
            continue
        d = _parse_date(row[0])
        if not d:
            continue
        for col in range(1, min(len(row), len(ids))):
            sid = ids[col].strip()
            if not sid or sid not in out:
                continue
            raw = row[col].strip()
            if not raw:
                continue
            try:
                out[sid]["obs"].append((d, float(raw)))
            except ValueError:
                continue
    return out


def fetch_all():
    """Fetch every table we use. Each table is isolated so one failure can't sink the rest."""
    data, errors = {}, {}
    for t in TABLES:
        try:
            data[t] = fetch_table(t)
        except Exception as e:  # noqa: BLE001
            errors[t] = f"{type(e).__name__}: {e}"
    return data, errors


if __name__ == "__main__":
    d, errs = fetch_all()
    for t, series in d.items():
        print(f"\n### {t} - {TABLES[t]} ({len(series)} series)")
        for sid, s in list(series.items())[:8]:
            if s["obs"]:
                dt, v = s["obs"][-1]
                print(f"   {sid:<12} {v:>12}  {s['units']:<10} {dt}   {s['title'][:44]}")
    if errs:
        print("\nERRORS:", errs)
