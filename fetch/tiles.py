"""Tile registry and panel assembly.

Panels are ordered the way the morning actually reads: rates first (they price the
debt), then the global session working backwards through the night, then the sector
indices that matter to a developer, then FX, inputs, and finally the slow structural
series. Derived values (spreads, curve shape) are computed here at fetch time so the
browser only ever renders numbers.
"""
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------- Yahoo-backed tiles
# (id, symbol, label, panel, group)
YAHOO = [
    # Panel 2 - global equities, ordered by trading session
    ("sp500", "^GSPC", "S&P 500", "equities", "Americas"),
    ("nasdaq", "^IXIC", "Nasdaq Composite", "equities", "Americas"),
    ("dow", "^DJI", "Dow Jones", "equities", "Americas"),
    ("russell", "^RUT", "Russell 2000", "equities", "Americas"),
    ("tsx", "^GSPTSE", "S&P/TSX Composite", "equities", "Americas"),
    ("ftse", "^FTSE", "FTSE 100", "equities", "Europe"),
    ("dax", "^GDAXI", "DAX", "equities", "Europe"),
    ("cac", "^FCHI", "CAC 40", "equities", "Europe"),
    ("stoxx", "^STOXX50E", "Euro Stoxx 50", "equities", "Europe"),
    ("nikkei", "^N225", "Nikkei 225", "equities", "Asia"),
    ("hangseng", "^HSI", "Hang Seng", "equities", "Asia"),
    ("shanghai", "000001.SS", "Shanghai Composite", "equities", "Asia"),
    ("kospi", "^KS11", "KOSPI", "equities", "Asia"),
    ("nifty", "^NSEI", "Nifty 50", "equities", "Asia"),
    ("asx200", "^AXJO", "S&P/ASX 200", "equities", "Australia"),
    ("allords", "^AORD", "All Ordinaries", "equities", "Australia"),

    # Panel 3 - the sector indices closest to a developer's business
    ("asx_areit", "^AXPJ", "ASX 200 A-REIT", "sector", "Australian property"),
    ("asx_materials", "^AXMJ", "ASX 200 Materials", "sector", "Australian inputs"),
    ("us_realestate", "^DJUSRE", "DJ US Real Estate", "sector", "Offshore property"),
    ("vnq", "VNQ", "Vanguard US REIT ETF", "sector", "Offshore property"),

    # Panel 4 - crypto (FX comes from the RBA)
    ("btc", "BTC-AUD", "Bitcoin", "fx", "Crypto"),
    ("eth", "ETH-AUD", "Ether", "fx", "Crypto"),

    # Panel 5 - inputs and commodities
    ("hrc_steel", "HRC=F", "HRC steel futures", "inputs", "Construction inputs"),
    ("copper", "HG=F", "Copper futures", "inputs", "Construction inputs"),
    ("aluminium", "ALI=F", "Aluminium futures", "inputs", "Construction inputs"),
    ("brent", "BZ=F", "Brent crude", "inputs", "Energy"),
    ("wti", "CL=F", "WTI crude", "inputs", "Energy"),
    ("gold", "GC=F", "Gold", "inputs", "Risk appetite"),
    ("vix", "^VIX", "VIX", "inputs", "Risk appetite"),
    ("dxy", "DX-Y.NYB", "US dollar index", "inputs", "Risk appetite"),
]

# Caveats that belong on the tile, not in a README nobody opens.
NOTES = {
    "hrc_steel": ("US Midwest hot-rolled coil, USD per short ton. A daily steel signal - "
                  "NOT your delivered Australian rebar or structural steel price, which is "
                  "set by supply contracts and local fabricator margins."),
    "asx_materials": "Miners and building-materials producers - a market proxy for input costs.",
    "asx_areit": ("Listed property trusts. Moves here reprice cap rate expectations well "
                  "before it shows in any quarterly ABS series."),
    "shanghai": "China is the demand side of iron ore and steel.",
    "hangseng": "China is the demand side of iron ore and steel.",
    "btc": "Carried as a risk-appetite gauge alongside VIX, not an asset class you hold.",
    "eth": "Carried as a risk-appetite gauge alongside VIX, not an asset class you hold.",
    "cash_rate": "The rate everything else is priced off.",
}

# ------------------------------------------------------------------ RBA-backed tiles
# (id, table, series_id, label, panel, group, unit)
RBA = [
    ("cash_rate", "f1", "FIRMMCRTD", "RBA cash rate target", "rates", "Australia", "%"),
    ("au_bab_3m", "f1", "FIRMMBAB90D", "AU 3-month bank bill", "rates", "Australia", "%"),
    ("au_2y", "f2", "FCMYGBAG2D", "AU 2-year bond", "rates", "Australia", "%"),
    ("au_3y", "f2", "FCMYGBAG3D", "AU 3-year bond", "rates", "Australia", "%"),
    ("au_5y", "f2", "FCMYGBAG5D", "AU 5-year bond", "rates", "Australia", "%"),
    ("au_10y", "f2", "FCMYGBAG10D", "AU 10-year bond", "rates", "Australia", "%"),
    ("au_housing_var", "f5", "FILRHLBVO", "Housing variable (owner-occ)", "rates", "Lending rates", "%"),
    ("au_smallbiz_var", "f5", "FILRSBVOO", "Small business variable", "rates", "Lending rates", "%"),
    ("aud_usd", "f11.1", "FXRUSD", "AUD / USD", "fx", "Australian dollar", "USD"),
    ("aud_cny", "f11.1", "FXRCR", "AUD / CNY", "fx", "Australian dollar", "CNY"),
    ("aud_eur", "f11.1", "FXREUR", "AUD / EUR", "fx", "Australian dollar", "EUR"),
    ("aud_gbp", "f11.1", "FXRUKPS", "AUD / GBP", "fx", "Australian dollar", "GBP"),
    ("aud_jpy", "f11.1", "FXRJY", "AUD / JPY", "fx", "Australian dollar", "JPY"),
    ("aud_twi", "f11.1", "FXRTWI", "AUD trade-weighted index", "fx", "Australian dollar", "index"),
]

PANELS = [
    {"id": "rates", "title": "Rates & Credit", "cadence": "daily",
     "subtitle": "What money costs - the numbers that price your debt"},
    {"id": "curves", "title": "Yield Curve Shape", "cadence": "daily",
     "subtitle": "Where the debt market thinks the cycle is going"},
    {"id": "equities", "title": "Global Equities", "cadence": "end of day",
     "subtitle": "Read backwards through last night - Americas, Europe, Asia, then our open"},
    {"id": "sector", "title": "Property & Input Sectors", "cadence": "end of day",
     "subtitle": "The indices closest to your actual business"},
    {"id": "fx", "title": "FX & Crypto", "cadence": "daily",
     "subtitle": "RBA 4pm fixes, plus crypto as a risk-appetite gauge"},
    {"id": "inputs", "title": "Inputs & Commodities", "cadence": "end of day",
     "subtitle": "Traded proxies for what you build with"},
    {"id": "structural", "title": "Structural / Construction", "cadence": "quarterly & monthly",
     "subtitle": ("ABS series. These move on release dates, not overnight - read the "
                  "reference period, not the refresh time.")},
]


# ------------------------------------------------------------------------- utilities
def pct_change(obs):
    """(change, pct_change) across the last two observations of [(date, value)]."""
    if len(obs) < 2:
        return None, None
    prev, cur = obs[-2][1], obs[-1][1]
    if not prev:
        return None, None
    return round(cur - prev, 4), round((cur / prev - 1) * 100, 2)


def age_days(iso):
    try:
        return (date.today() - datetime.strptime(iso[:10], "%Y-%m-%d").date()).days
    except Exception:  # noqa: BLE001
        return None


def nearest_on_or_before(series, target):
    """Value in ascending [(date, value)] nearest to but not after target."""
    best = None
    for d, v in series:
        if d <= target:
            best = (d, v)
        else:
            break
    return best


# ---------------------------------------------------------------------- curve builder
# Australian curve points. The short end is bank bills, the rest government bonds -
# a distinction the page keeps visible because the gap between them is credit spread,
# not curve shape.
AU_CURVE = [
    (0.003, "O/N", "f1", "FIRMMCRTD", "cash"),
    (1 / 12, "1M", "f1", "FIRMMBAB30D", "bill"),
    (0.25, "3M", "f1", "FIRMMBAB90D", "bill"),
    (0.5, "6M", "f1", "FIRMMBAB180D", "bill"),
    (2, "2Y", "f2", "FCMYGBAG2D", "govt"),
    (3, "3Y", "f2", "FCMYGBAG3D", "govt"),
    (5, "5Y", "f2", "FCMYGBAG5D", "govt"),
    (10, "10Y", "f2", "FCMYGBAG10D", "govt"),
]

AU_CAVEAT = ("Short end (1M-6M) is bank bills, which carry bank credit risk; 2Y-10Y is "
             "Commonwealth government bonds. The step between them is a credit spread, "
             "not curve shape. The RBA publishes no free interpolated yield beyond 10 "
             "years, so this curve stops where the US one continues to 30Y.")


def build_au_curve(rba_data):
    def snapshot(target):
        pts = []
        for years, label, table, sid, kind in AU_CURVE:
            series = (rba_data.get(table) or {}).get(sid, {}).get("obs") or []
            hit = nearest_on_or_before(series, target)
            if hit:
                pts.append({"tenor": label, "years": years, "yield": hit[1],
                            "instrument": kind, "date": hit[0]})
        return pts

    now = snapshot(date.today().isoformat())
    if not now:
        return None
    return {
        "country": "Australia",
        "code": "au",
        "date": max(p["date"] for p in now),
        "points": now,
        "month_ago": snapshot((date.today() - timedelta(days=30)).isoformat()),
        "year_ago": snapshot((date.today() - timedelta(days=365)).isoformat()),
        "caveat": AU_CAVEAT,
        "source": "RBA tables F1 and F2",
    }


def build_us_curve(treasury_days):
    if not treasury_days:
        return None
    by_date = {d["date"]: d for d in treasury_days}
    dates = sorted(by_date)
    latest = by_date[dates[-1]]

    def snapshot(target):
        prior = [d for d in dates if d <= target]
        if not prior:
            return []
        return [{**p, "instrument": "govt", "date": prior[-1]}
                for p in by_date[prior[-1]]["points"]]

    return {
        "country": "United States",
        "code": "us",
        "date": latest["date"],
        "points": [{**p, "instrument": "govt", "date": latest["date"]} for p in latest["points"]],
        "month_ago": snapshot((date.today() - timedelta(days=30)).isoformat()),
        "year_ago": snapshot((date.today() - timedelta(days=365)).isoformat()),
        "caveat": "Treasury par yield curve, all 13 published tenors, 1 month to 30 years.",
        "source": "US Treasury daily par yield curve",
    }


def yield_at(points, years, tol=0.01):
    for p in points:
        if abs(p["years"] - years) < tol:
            return p["yield"]
    return None


def classify_curve(points):
    """Spreads plus a plain-English shape label."""
    y2 = yield_at(points, 2)
    y10 = yield_at(points, 10)
    y3m = yield_at(points, 0.25)
    out = {"spread_10_2": None, "spread_10_3m": None, "shape": "unknown"}

    if y2 is not None and y10 is not None:
        out["spread_10_2"] = round(y10 - y2, 3)
    if y3m is not None and y10 is not None:
        out["spread_10_3m"] = round(y10 - y3m, 3)

    s = out["spread_10_2"]
    if s is None:
        return out
    if s < -0.10:
        out["shape"] = "Inverted"
    elif s < 0.10:
        out["shape"] = "Flat"
    else:
        # A mid-curve peak meaningfully above the 10y reads as humped, not normal.
        mids = [p for p in points if 0.5 <= p["years"] <= 7]
        if mids and y10 is not None and max(p["yield"] for p in mids) > y10 + 0.10:
            out["shape"] = "Humped"
        else:
            out["shape"] = "Normal"
    return out


def spread_history_us(treasury_days):
    """[(date, 10y-2y)] ascending, for the days-since-inversion count."""
    hist = []
    for d in treasury_days:
        y2 = yield_at(d["points"], 2)
        y10 = yield_at(d["points"], 10)
        if y2 is not None and y10 is not None:
            hist.append((d["date"], round(y10 - y2, 3)))
    return hist


def spread_history_au(rba_data):
    s2 = dict((rba_data.get("f2") or {}).get("FCMYGBAG2D", {}).get("obs") or [])
    s10 = dict((rba_data.get("f2") or {}).get("FCMYGBAG10D", {}).get("obs") or [])
    return [(d, round(s10[d] - s2[d], 3)) for d in sorted(set(s2) & set(s10))]


def days_since_inversion(history):
    """Days since 10y-2y was last non-negative. None if not currently inverted."""
    if not history or history[-1][1] >= 0:
        return None
    last_day = datetime.strptime(history[-1][0], "%Y-%m-%d").date()
    for d, spread in reversed(history):
        if spread >= 0:
            return (last_day - datetime.strptime(d, "%Y-%m-%d").date()).days
    return None
