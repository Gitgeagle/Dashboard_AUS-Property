"""ABS Data API (SDMX-JSON).

Free and keyless, but flagged beta by the ABS - availability is explicitly not
guaranteed, so callers must tolerate failure. Everything here is quarterly or monthly:
these are structural indicators, not market prices, and the dashboard labels them so.
"""
from httpget import get_json

BASE = "https://data.api.abs.gov.au/rest/data/{flow}/{key}?format=jsondata&lastNObservations={n}"

UNIT_MULTS = {
    "units": 1, "tens": 10, "hundreds": 100, "thousands": 1_000,
    "millions": 1_000_000, "billions": 1_000_000_000,
}

# flow, datakey, label, unit-ish hint. Dimension order per dataflow:
#   PPI               MEASURE.INDEX.TYPE.FREQ
#   CWD               MEASURE.PRICE_ADJUSTMENT.SECTOR_OWN.CONSTRUCTION_TYPE.TSEST.REGION.FREQ
#   RPPI              MEASURE.PROPERTY_TYPE.REGION.FREQ
#   CPI_M             MEASURE.INDEX.TSEST.REGION.FREQ
#   WPI               MEASURE.INDEX.SECTOR.INDUSTRY.TSEST.REGION.FREQ
#   BUILDING_ACTIVITY MEASURE.REGION.PRICE_ADJ.BLD_WORK_TYPE.SECTOR_OWN.TYPE_BLDG.TSEST.FREQ
#   RES_DWELL_ST      MEASURE.REGION.FREQ
SERIES = {
    "ppi_building_construction": {
        "flow": "PPI", "key": "1.1451369.OUTPUT.Q",
        "label": "Building construction PPI", "unit": "index",
        "note": "ABS PPI output, Building construction (ANZSIC 30), Australia",
    },
    "ppi_heavy_civil": {
        "flow": "PPI", "key": "1.8194096.OUTPUT.Q",
        "label": "Heavy & civil engineering PPI", "unit": "index",
        "note": "ABS PPI output, Heavy and civil engineering construction (ANZSIC 31)",
    },
    "ppi_house_construction": {
        "flow": "PPI", "key": "1.1451370.OUTPUT.Q",
        "label": "House construction PPI", "unit": "index",
        "note": "ABS PPI output, House construction (ANZSIC 3011), Australia",
    },
    "ppi_nonres_building": {
        "flow": "PPI", "key": "1.1451389.OUTPUT.Q",
        "label": "Non-residential building PPI", "unit": "index",
        "note": "ABS PPI output, Non-residential building construction (ANZSIC 3020)",
    },
    "construction_work_done": {
        "flow": "CWD", "key": "M1.CUR.9.TOT.20.AUS.Q",
        "label": "Construction work done", "unit": "$",
        "note": "Total construction, current prices, seasonally adjusted, Australia",
    },
    # NOTE: the RPPI dataflow stops at 2021-Q4 - the ABS discontinued it. RES_DWELL_ST
    # is the live replacement, so we use mean dwelling price instead of an index.
    "mean_dwelling_price": {
        "flow": "RES_DWELL_ST", "key": "5.AUS.Q",
        "label": "Mean residential dwelling price", "unit": "$",
        "note": "ABS Total Value of Dwellings, mean price, Australia",
    },
    # The CPI_M dataflow stalls at 2025-09; the CPI dataflow carries the live monthly
    # series under the same key, so we read it from there.
    "cpi_monthly": {
        "flow": "CPI", "key": "3.10001.10.50.M",
        "label": "CPI (monthly indicator, annual)", "unit": "%",
        "note": "All groups CPI, change from corresponding month of previous year",
    },
    "wpi_construction": {
        "flow": "WPI", "key": "3.THRPEB.7.E.10.AUS.Q",
        "label": "Wage price index - construction", "unit": "%",
        "note": "Total hourly rates excl. bonuses, construction industry, annual change",
    },
    "dwellings_commenced": {
        "flow": "BUILDING_ACTIVITY", "key": "M6.AUS.CUR.1.9.100.20.Q",
        "label": "Dwelling units commenced", "unit": "number",
        "note": "New residential, all sectors, seasonally adjusted, Australia",
    },
}


def _extract(js):
    """Pull [(period, value)] from an SDMX-JSON 2.0 response.

    The ABS serves SDMX-JSON 2.0, where the structure lives under data.structures[0]
    (a list) rather than data.structure. Observation keys index into the TIME_PERIOD
    values list, which the API returns newest-first when lastNObservations is used.
    """
    data = js.get("data") or {}
    datasets = data.get("dataSets") or []
    structures = data.get("structures") or []
    if not datasets or not structures:
        raise ValueError("no dataSets/structures in response")

    dims = structures[0].get("dimensions") or {}
    obs_dims = dims.get("observation") or []
    if not obs_dims:
        raise ValueError("no observation dimension")
    periods = [v.get("id") or v.get("name") for v in obs_dims[0].get("values", [])]

    series = datasets[0].get("series") or {}
    if not series:
        raise ValueError("no series returned (key may match nothing)")

    # A well-specified key returns one series; if several come back take the first.
    skey = next(iter(series))
    obs = series[skey].get("observations") or {}
    pairs = []
    for k, v in obs.items():
        i = int(k)
        if i < len(periods) and v and v[0] is not None:
            pairs.append((periods[i], float(v[0])))
    pairs.sort(key=lambda t: t[0])

    # ABS reports many dollar series in thousands. Ignoring UNIT_MULT turns $90bn of
    # construction work into "89,999,396 $m", so resolve it and scale here.
    mult, unit_measure = 1, None
    attr_defs = (structures[0].get("attributes") or {}).get("series") or []
    attr_idx = series[skey].get("attributes") or []
    for pos, adef in enumerate(attr_defs):
        if pos >= len(attr_idx) or attr_idx[pos] is None:
            continue
        vals = adef.get("values") or []
        if attr_idx[pos] >= len(vals):
            continue
        name = vals[attr_idx[pos]].get("name") or vals[attr_idx[pos]].get("id") or ""
        if adef.get("id") == "UNIT_MULT":
            mult = UNIT_MULTS.get(name.strip().lower(), 1)
        elif adef.get("id") == "UNIT_MEASURE":
            unit_measure = name

    if mult != 1:
        pairs = [(pp, vv * mult) for pp, vv in pairs]
    return {"obs": pairs, "unit_mult": mult, "unit_measure": unit_measure}


def fetch_series(spec, n=12):
    js = get_json(BASE.format(flow=spec["flow"], key=spec["key"], n=n))
    return _extract(js)


# ---------------------------------------------------------- capital city property
# RES_DWELL: MEASURE.REGION.FREQ, quarterly medians by Greater Capital City Statistical
# Area. This is the free official substitute for a commercial city price index - Domain's
# API has no published free tier and domain.com.au blocks automated requests outright.
CITY_FLOW = "RES_DWELL"
CITY_MEASURES = {"3": "house", "4": "unit"}
CAPITALS = {
    "1GSYD": "Sydney", "2GMEL": "Melbourne", "3GBRI": "Brisbane",
    "4GADE": "Adelaide", "5GPER": "Perth", "6GHOB": "Hobart",
    "7GDAR": "Darwin", "8ACTE": "Canberra (ACT)",
}


def fetch_city_property(n=13):
    """Median dwelling prices for the eight capitals.

    Returns {(region_id, kind): {"city":..., "kind":..., "obs":[(period, value)]}}.
    One request covers both measures and every region; n=13 gives four years of
    quarters so year-on-year is available alongside quarter-on-quarter.
    """
    key = "+".join(CITY_MEASURES) + "..Q"
    js = get_json(BASE.format(flow=CITY_FLOW, key=key, n=n))
    data = js.get("data") or {}
    datasets, structures = data.get("dataSets") or [], data.get("structures") or []
    if not datasets or not structures:
        raise ValueError("no dataSets/structures in RES_DWELL response")

    dims = structures[0].get("dimensions") or {}
    periods = [v.get("id") for v in (dims.get("observation") or [{}])[0].get("values", [])]
    series_dims = dims.get("series") or []
    dim_values = {d["id"]: d.get("values", []) for d in series_dims}
    dim_order = [d["id"] for d in series_dims]

    # UNIT_MULT is "Thousands" here - a raw 1488 is $1.488m, not $1,488.
    attr_defs = (structures[0].get("attributes") or {}).get("series") or []

    out = {}
    for skey, sval in (datasets[0].get("series") or {}).items():
        idx = [int(i) for i in skey.split(":")]
        coords = {dim_order[i]: dim_values[dim_order[i]][idx[i]]["id"] for i in range(len(idx))}
        region, measure = coords.get("REGION"), coords.get("MEASURE")
        if region not in CAPITALS or measure not in CITY_MEASURES:
            continue

        mult = 1
        attr_idx = sval.get("attributes") or []
        for pos, adef in enumerate(attr_defs):
            if adef.get("id") != "UNIT_MULT" or pos >= len(attr_idx) or attr_idx[pos] is None:
                continue
            vals = adef.get("values") or []
            if attr_idx[pos] < len(vals):
                nm = (vals[attr_idx[pos]].get("name") or "").strip().lower()
                mult = UNIT_MULTS.get(nm, 1)

        obs = []
        for k, v in (sval.get("observations") or {}).items():
            i = int(k)
            if i < len(periods) and v and v[0] is not None:
                obs.append((periods[i], float(v[0]) * mult))
        obs.sort(key=lambda t: t[0])
        if obs:
            out[(region, CITY_MEASURES[measure])] = {
                "city": CAPITALS[region], "kind": CITY_MEASURES[measure],
                "region": region, "obs": obs,
            }
    return out


def _period_age_days(period):
    """Rough age of an ABS period label like '2026-Q2' or '2026-08'."""
    from datetime import date
    try:
        if "-Q" in period:
            y, q = period.split("-Q")
            end_month = int(q) * 3
            ref = date(int(y), end_month, 28)
        else:
            y, m = period.split("-")[:2]
            ref = date(int(y), int(m), 28)
    except Exception:  # noqa: BLE001
        return None
    return (date.today() - ref).days


period_age_days = _period_age_days  # public alias for callers outside this module


# A series far past its normal publication lag is probably discontinued rather than
# merely late. Two ABS dataflows failed exactly this way while this was being built -
# RPPI stops at 2021-Q4 and CPI_M at 2025-09 - so the threshold is frequency-aware and
# the result is surfaced rather than rendered as if it were current.
STALE_AFTER_DAYS = {"Q": 300, "M": 120}


def fetch_all(n=12):
    out, errors = {}, {}
    for sid, spec in SERIES.items():
        try:
            parsed = fetch_series(spec, n)
            if not parsed["obs"]:
                raise ValueError("empty series")
            obs = parsed["obs"]
            age = _period_age_days(obs[-1][0])
            freq = "Q" if "-Q" in obs[-1][0] else "M"
            rec = {**spec, "obs": obs, "age_days": age, "freq": freq,
                   "unit_measure": parsed.get("unit_measure")}
            limit = STALE_AFTER_DAYS.get(freq, 300)
            if age is not None and age > limit:
                rec["stale"] = True
                rec["stale_reason"] = (f"last observation {obs[-1][0]} is {age} days old "
                                       f"(> {limit}d for {freq}) - series may be discontinued")
            out[sid] = rec
        except Exception as e:  # noqa: BLE001
            errors[sid] = f"{type(e).__name__}: {e}"
    return out, errors


if __name__ == "__main__":
    res, errs = fetch_all()
    for sid, s in res.items():
        p, v = s["obs"][-1]
        prev = s["obs"][-2][1] if len(s["obs"]) > 1 else None
        chg = f"{(v/prev-1)*100:+.1f}%" if prev else "n/a"
        flag = "  <-- STALE" if s.get("stale") else ""
        print(f"  {sid:<28} {v:>14,.1f}  {s['unit']:<7} {p:<8} chg={chg}{flag}")
    for sid, e in errs.items():
        print(f"  FAIL {sid:<26} {e[:90]}")
