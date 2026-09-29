"""Additional ABS series: the supply pipeline (approvals, work under construction,
completions), housing finance, labour, population and house-building input costs.

Same rules as abs.py: the ABS Data API is beta and keyless, so every block below is
fetched in isolation and a failure costs only its own tiles. Every key was checked
against the live dataflow structure (Sep 2026) rather than recalled - several guessed
keys 404 outright (the API answers a non-matching key with HTTP 404, not an empty set).

Dimension orders, as served:
  BA_GCCSA          MEASURE.VALUE.SECTOR.WORK_TYPE.BUILDING_TYPE.TSEST.REGION.FREQ
  BUILDING_ACTIVITY MEASURE.REGION.PRICE_ADJ.BLD_WORK_TYPE.SECTOR_OWN.TYPE_BLDG.TSEST.FREQ
  LEND_HOUSING      MEASURE.DATA_ITEM.LOAN_TYPE.LOAN_PURPOSE.LENDER_TYPE.HOUSING_PURPOSE.TSEST.REGION.FREQ
  LF                MEASURE.SEX.AGE.TSEST.REGION.FREQ
  JV                MEASURE.SECTOR.INDUSTRY.TSEST.REGION.FREQ
  ERP_COMP_Q        MEASURE.REGION.FREQ
  PPI               MEASURE.INDEX.TYPE.FREQ
"""
from sources import abs as abs_src
from httpget import get_json

SOURCE = "ABS Data API"


# ------------------------------------------------------------------- plumbing
def _fetch_multi(flow, key, n):
    """{dotted series key: [(period, value)]} with UNIT_MULT applied per series.

    abs._extract takes only the first series; these requests deliberately return
    several (e.g. houses + other dwellings x 9 regions), so decode them all. UNIT_MULT
    varies BY SERIES within one flow - in ERP_COMP_Q population is in thousands but
    net internal migration is in units - so it must be resolved per series.
    """
    js = get_json(abs_src.BASE.format(flow=flow, key=key, n=n))
    data = js.get("data") or {}
    datasets, structures = data.get("dataSets") or [], data.get("structures") or []
    if not datasets or not structures:
        raise ValueError(f"{flow}: no dataSets/structures in response")
    dims = structures[0].get("dimensions") or {}
    periods = [v.get("id") for v in (dims.get("observation") or [{}])[0].get("values", [])]
    sdims = dims.get("series") or []
    attr_defs = (structures[0].get("attributes") or {}).get("series") or []

    out = {}
    for skey, sval in (datasets[0].get("series") or {}).items():
        idx = [int(i) for i in skey.split(":")]
        dotted = ".".join(sdims[i]["values"][idx[i]]["id"] for i in range(len(idx)))
        mult = 1
        attr_idx = sval.get("attributes") or []
        for pos, adef in enumerate(attr_defs):
            if adef.get("id") != "UNIT_MULT" or pos >= len(attr_idx) or attr_idx[pos] is None:
                continue
            vals = adef.get("values") or []
            if attr_idx[pos] < len(vals):
                nm = (vals[attr_idx[pos]].get("name") or "").strip().lower()
                mult = abs_src.UNIT_MULTS.get(nm, 1)
        obs = []
        for k, v in (sval.get("observations") or {}).items():
            i = int(k)
            # Some flows (ERP_COMP_Q) serve observation values as strings.
            if i < len(periods) and v and v[0] is not None:
                obs.append((periods[i], float(v[0]) * mult))
        obs.sort(key=lambda t: t[0])
        if obs:
            out[dotted] = obs
    if not out:
        raise ValueError(f"{flow}/{key}: no series returned")
    return out


def _period_index(p):
    """Months since year 0 for '2026-07', or quarters for '2026-Q2' - to detect gaps."""
    if "-Q" in p:
        y, q = p.split("-Q")
        return int(y) * 4 + int(q) - 1
    y, m = p.split("-")[:2]
    return int(y) * 12 + int(m) - 1


def _rolling_sum(obs, window):
    """Trailing sum over `window` consecutive periods. Windows that span a gap in the
    series are skipped rather than summed short, which would print a false dip."""
    out = []
    for i in range(window - 1, len(obs)):
        chunk = obs[i - window + 1:i + 1]
        if _period_index(chunk[-1][0]) - _period_index(chunk[0][0]) != window - 1:
            continue
        out.append((obs[i][0], sum(v for _, v in chunk)))
    return out


def _yoy_series(obs, lag):
    """[(period, % change on `lag` periods earlier)], matched by period, not position."""
    by_idx = {_period_index(p): v for p, v in obs}
    out = []
    for p, v in obs:
        prev = by_idx.get(_period_index(p) - lag)
        if prev:
            out.append((p, round((v / prev - 1) * 100, 2)))
    return out


def _yoy_note(obs, lag, note):
    y = _yoy_series(obs[-(lag + 1):], lag)
    head = f"Year on year {y[-1][1]:+.1f}%" if y and y[-1][0] == obs[-1][0] else None
    return " · ".join(s for s in (head, note) if s) or None


def _tile(tid, label, panel, group, obs, unit, note, freq):
    """Common tile shape. `obs` is exactly what the headline and spark both show."""
    period, value = obs[-1]
    change = pchg = None
    if len(obs) > 1:
        prev = obs[-2][1]
        change = round(value - prev, 4)
        if prev and unit not in ("%", "pp"):
            pchg = round((value / prev - 1) * 100, 2)
    age = abs_src.period_age_days(period)
    limit = abs_src.STALE_AFTER_DAYS.get(freq, 300)
    stale = age is not None and age > limit
    return {
        "id": tid, "label": label, "panel": panel, "group": group,
        "value": value, "unit": unit,
        "change": change, "change_pct": pchg,
        "asof": period, "period": period, "freq": freq, "age_days": age,
        "spark": [[p, v] for p, v in obs],
        "source": SOURCE, "note": note,
        "status": "stale" if stale else "ok",
        "stale_reason": (f"last observation {period} is {age} days old (> {limit}d for "
                         f"{freq}) - series may be discontinued") if stale else None,
    }


def _run(name, fn, tiles_out, errors):
    try:
        tiles_out += fn(errors)
    except Exception as e:  # noqa: BLE001
        errors[f"abs/{name}"] = f"{type(e).__name__}: {e}"


# ---------------------------------------------------------- building approvals
# BA_GCCSA only carries ORIGINAL (TSEST 10) - there is no seasonally adjusted series by
# capital city. Monthly original approvals swing 30%+ on a single apartment project, so
# the tile shows the trailing 12-month total, which is what a pipeline read needs anyway.
# MEASURE 1 = number of dwelling units; BUILDING_TYPE 100 total residential, 110 houses,
# 850 dwellings excluding houses. WORK_TYPE TOT includes alterations that create
# dwellings. 110 + 850 lands within a few units of 100 (not exact), so don't expect the
# three Australia tiles to add up precisely.
BA_KEY = "1.1.9.TOT.{types}.10.{regions}.M"
BA_N = 132  # 11 years of months -> ten years of 12-month sums
BA_NOTE = "Rolling 12-month total, original series (no seasonally adjusted series by city)."
BA_AUS = [("100", "approvals_total_aus", "Total dwellings"),
          ("110", "approvals_houses_aus", "Houses"),
          ("850", "approvals_other_aus", "Other dwellings (units, townhouses)")]
BA_CITIES = {
    "1GSYD": "Sydney", "2GMEL": "Melbourne", "3GBRI": "Brisbane", "5GPER": "Perth",
    "4GADE": "Adelaide", "8ACTE": "Canberra (ACT)", "6GHOB": "Hobart", "7GDAR": "Darwin",
}


def _approval_tile(tid, label, group, monthly):
    roll = _rolling_sum(monthly, 12)
    if len(roll) < 2:
        raise ValueError(f"{tid}: not enough consecutive months for a 12-month total")
    return _tile(tid, label, "pipeline", group, roll, "number",
                 _yoy_note(roll, 12, BA_NOTE), "M")


def _approvals_aus(errors):
    got = _fetch_multi("BA_GCCSA", BA_KEY.format(types="100+110+850", regions="AUS"), BA_N)
    out = []
    for btype, tid, label in BA_AUS:
        obs = got.get(f"1.1.9.TOT.{btype}.10.AUS.M")
        if not obs:
            errors[f"tile/{tid}"] = "BA_GCCSA series missing"
            continue
        out.append(_approval_tile(tid, label, "Dwelling approvals, Australia", obs))
    return out


def _approvals_cities(errors):
    got = _fetch_multi("BA_GCCSA", BA_KEY.format(types="100", regions="+".join(BA_CITIES)), BA_N)
    out = []
    for region, city in BA_CITIES.items():
        tid = f"approvals_{region}"
        obs = got.get(f"1.1.9.TOT.100.10.{region}.M")
        if not obs:
            errors[f"tile/{tid}"] = "BA_GCCSA series missing"
            continue
        out.append(_approval_tile(tid, city, "Dwelling approvals by capital", obs))
    return out


# ---------------------------------------------------------- building activity
# Quarterly, and a full quarter behind approvals (Q1 publishes in July). Completions
# exist seasonally adjusted (TSEST 20); dwellings under construction is a stock and the
# ABS publishes it ORIGINAL only - requesting M8 with TSEST 20 returns nothing.
BACT = [
    ("dwellings_under_construction", "M8.AUS.CUR.1.9.100.10.Q", "Dwellings under construction",
     "Stock of dwellings under construction at quarter end, original series. The pipeline "
     "still to complete - high and flat means trades stay tied up."),
    ("dwellings_completed", "M7.AUS.CUR.1.9.100.20.Q", "Dwellings completed",
     "New residential dwellings completed in the quarter, seasonally adjusted."),
]


def _building_activity(errors):
    out = []
    for tid, key, label, note in BACT:
        try:
            obs = _fetch_multi("BUILDING_ACTIVITY", key, 44)[key]
            out.append(_tile(tid, label, "pipeline", "Dwellings", obs, "number",
                             _yoy_note(obs, 4, note), "Q"))
        except Exception as e:  # noqa: BLE001
            errors[f"abs/{tid}"] = f"{type(e).__name__}: {e}"
    return out


# ------------------------------------------------------------- housing finance
# LEND_HOUSING is quarterly only since the ABS moved it off monthly. LOAN_TYPE DV8368 is
# fixed-term plus revolving; LOAN_PURPOSE TOTDWELL is dwellings excluding refinancing.
# Construction-of-dwellings loans (DV8353) have NO total-housing-purpose series - only
# owner-occupier and investor - so the construction tile sums the two SA series.
# UNIT_MULT is millions. The investor construction SA series only starts 2019-Q3, so
# the summed construction tile has ~7 years of history, not ten.
LEND_KEY = "FIN_VAL.NEWCOMMITS.DV8368.{purpose}.TOT.{hp}.20.AUS.Q"
LEND = [
    ("lend_owner_occ", "TOTDWELL", ["DV5167"], "Owner-occupier",
     "Value of new owner-occupier loan commitments (excl. refinancing), seasonally adjusted."),
    ("lend_investor", "TOTDWELL", ["DV5168"], "Investor",
     "Value of new investor loan commitments (excl. refinancing), seasonally adjusted."),
    ("lend_construction", "DV8353", ["DV5167", "DV5168"], "Construction of dwellings",
     "Loans to build a dwelling - owner-occupier plus investor, each seasonally adjusted. "
     "The most direct read on buyer-funded new builds."),
]


def _housing_finance(errors):
    out = []
    for tid, purpose, hps, label, note in LEND:
        try:
            parts = []
            for hp in hps:
                key = LEND_KEY.format(purpose=purpose, hp=hp)
                parts.append(dict(_fetch_multi("LEND_HOUSING", key, 44)[key]))
            common = sorted(set.intersection(*(set(p) for p in parts)))
            obs = [(p, sum(part[p] for part in parts)) for p in common]
            out.append(_tile(tid, label, "credit", "Housing finance (new commitments)", obs,
                             "$", _yoy_note(obs, 4, note), "Q"))
        except Exception as e:  # noqa: BLE001
            errors[f"abs/{tid}"] = f"{type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------------- labour
def _unemployment(errors):
    key = "M13.3.1599.20.AUS.M"  # persons, 15+, seasonally adjusted
    obs = _fetch_multi("LF", key, 120)[key]
    # The API serves 8 decimals (4.64629609); the ABS headline is one decimal.
    obs = [(p, round(v, 2)) for p, v in obs]
    return [_tile("unemployment_rate", "Unemployment rate", "demand", "Labour", obs, "%",
                  "Seasonally adjusted. A loosening labour market eases trade costs but "
                  "softens buyer depth.", "M")]


def _job_vacancies(errors):
    key = "M1.7.TOT.20.AUS.Q"  # private + public, all industries, SA; UNIT_MULT thousands
    obs = _fetch_multi("JV", key, 44)[key]
    return [_tile("job_vacancies", "Job vacancies", "demand", "Labour", obs, "number",
                  _yoy_note(obs, 4, "All industries, seasonally adjusted. Survey is taken "
                            "mid-quarter (May for Q2)."), "Q")]


# ------------------------------------------------------------------ population
# ERP_COMP_Q (not ERP_Q, which is split by sex and age) carries ERP and its components.
# MEASURE 10 = estimated resident population, 9 = net overseas migration. NOM here is
# original and strongly seasonal (Q1 student arrivals), so the tile shows the trailing
# four-quarter total - the annual figure that gets quoted.
def _population(errors):
    got = _fetch_multi("ERP_COMP_Q", "10+9.AUS.Q", 48)
    out = []
    erp = got.get("10.AUS.Q")
    if erp:
        growth = _yoy_series(erp, 4)
        if len(growth) >= 2:
            out.append(_tile("population_growth", "Population growth", "demand", "Population",
                             growth, "%",
                             f"Estimated resident population {erp[-1][1] / 1e6:.2f}m, annual "
                             "growth. Underlying demand for dwellings.", "Q"))
    else:
        errors["tile/population_growth"] = "ERP_COMP_Q measure 10 missing"
    nom = got.get("9.AUS.Q")
    if nom:
        roll = _rolling_sum(nom, 4)
        if len(roll) >= 2:
            out.append(_tile("net_overseas_migration", "Net overseas migration (annual)",
                             "demand", "Population", roll, "number",
                             _yoy_note(roll, 4, "Trailing four-quarter total, original "
                                       "series. The swing factor in housing demand."), "Q"))
    else:
        errors["tile/net_overseas_migration"] = "ERP_COMP_Q measure 9 missing"
    return out


# ------------------------------------------------ materials used in house building
# PPI "INPUT" indexes - the old "Materials used in house building" series, labelled in
# the flow as "All groups; <city>" under the header "House Construction Inputs" (T18).
# Six capitals plus the weighted average only; Darwin and Canberra are not published.
# Materials only - no labour - so they understate total build-cost inflation.
PPI_INPUTS = [
    ("8102825", "ppi_house_inputs_avg", "Six-capital average"),
    ("8102560", "ppi_house_inputs_syd", "Sydney"),
    ("8102576", "ppi_house_inputs_mel", "Melbourne"),
    ("8102591", "ppi_house_inputs_bne", "Brisbane"),
    ("8104034", "ppi_house_inputs_per", "Perth"),
    ("8104018", "ppi_house_inputs_adl", "Adelaide"),
    ("8104049", "ppi_house_inputs_hob", "Hobart"),
]


def _ppi_inputs(errors):
    key = "1." + "+".join(p[0] for p in PPI_INPUTS) + ".INPUT.Q"
    got = _fetch_multi("PPI", key, 44)
    out = []
    for code, tid, label in PPI_INPUTS:
        idx = got.get(f"1.{code}.INPUT.Q")
        if not idx:
            errors[f"tile/{tid}"] = f"PPI {code} missing"
            continue
        yoy = _yoy_series(idx, 4)
        if len(yoy) < 2:
            errors[f"tile/{tid}"] = "not enough history for year-on-year"
            continue
        out.append(_tile(tid, label, "structural", "Materials used in house building (by city)",
                         yoy, "%",
                         f"Annual change in the materials index ({idx[-1][1]:.1f}). "
                         "Materials only - excludes labour.", "Q"))
    return out


BLOCKS = [
    ("approvals_aus", _approvals_aus),
    ("approvals_cities", _approvals_cities),
    ("building_activity", _building_activity),
    ("housing_finance", _housing_finance),
    ("unemployment", _unemployment),
    ("job_vacancies", _job_vacancies),
    ("population", _population),
    ("ppi_house_inputs", _ppi_inputs),
]


def fetch_all():
    tile_list, errors = [], {}
    for name, fn in BLOCKS:
        _run(name, fn, tile_list, errors)
    return tile_list, errors


if __name__ == "__main__":
    ts, errs = fetch_all()
    for t in ts:
        cp = f"{t['change_pct']:+.2f}%" if t["change_pct"] is not None else "-"
        print(f"  {t['id']:<30} {t['value']:>16,.2f} {t['unit']:<6} {t['asof']:<8} "
              f"n={len(t['spark']):<4} chg={t['change']} ({cp}) {t['status']}")
        print(f"      {t['note']}")
    for k, e in errs.items():
        print(f"  FAIL {k}: {e}")
