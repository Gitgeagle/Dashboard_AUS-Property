"""FRED (St Louis Fed) series. Needs a free API key in FRED_API_KEY.

Optional by design: if the key is absent every series is reported as skipped rather
than failed, and the dashboard still builds. Brent and WTI come from here because they
are official daily series rather than a scraped futures quote.
"""
import os

from httpget import get_json

URL = ("https://api.stlouisfed.org/fred/series/observations"
       "?series_id={sid}&api_key={key}&file_type=json&sort_order=desc&limit={n}")

SERIES = {
    "brent": {"sid": "DCOILBRENTEU", "label": "Brent crude", "unit": "USD/bbl"},
    "wti": {"sid": "DCOILWTICO", "label": "WTI crude", "unit": "USD/bbl"},
    "fed_funds_upper": {"sid": "DFEDTARU", "label": "US Fed funds target (upper)", "unit": "%"},
    "us_cpi_yoy": {"sid": "CPIAUCSL", "label": "US CPI (index)", "unit": "index"},
}


def fetch_series(sid, key, n=260):
    js = get_json(URL.format(sid=sid, key=key, n=n))
    obs = []
    for o in js.get("observations", []):
        if o.get("value") in (".", "", None):
            continue
        try:
            obs.append((o["date"], float(o["value"])))
        except ValueError:
            continue
    obs.sort(key=lambda t: t[0])
    return obs


def fetch_all():
    key = os.environ.get("FRED_API_KEY", "").strip()
    out, errors, skipped = {}, {}, []
    if not key:
        return out, errors, list(SERIES)
    for sid, spec in SERIES.items():
        try:
            obs = fetch_series(spec["sid"], key)
            if not obs:
                raise ValueError("empty series")
            out[sid] = {**spec, "obs": obs}
        except Exception as e:  # noqa: BLE001
            errors[sid] = f"{type(e).__name__}: {e}"
    return out, errors, skipped


if __name__ == "__main__":
    res, errs, skipped = fetch_all()
    if skipped:
        print(f"  SKIPPED (no FRED_API_KEY set): {', '.join(skipped)}")
    for sid, s in res.items():
        d, v = s["obs"][-1]
        print(f"  {sid:<18} {v:>10}  {s['unit']:<10} {d}")
    if errs:
        print("  ERRORS:", errs)
