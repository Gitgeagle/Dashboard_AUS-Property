"""Yahoo Finance chart endpoint.

Public, undocumented, and needs no account or API key - a plain GET with a browser
User-Agent is the whole authentication story. It is unsupported, so treat every symbol
as individually failable and never let one bad response sink the run.
"""
import time
from datetime import datetime, timezone

from httpget import get_json

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d"
PAUSE = 0.35  # gentle on an endpoint that owes us nothing

# Yahoo keeps serving delisted contracts with a stale price and an HTTP 200 - TIO=F
# (SGX iron ore) still returns a number last traded in 2021, and LBS=F stopped in 2023.
# Anything this far past its last trade is dead, not quiet, and must not render as a
# live quote.
STALE_AFTER_DAYS = 10


def fetch_symbol(symbol, rng="1y"):
    """Return a normalised quote dict, or raise."""
    import urllib.parse
    js = get_json(URL.format(sym=urllib.parse.quote(symbol, safe=""), rng=rng))
    res = (js.get("chart") or {}).get("result") or []
    if not res:
        err = (js.get("chart") or {}).get("error")
        raise ValueError(f"no result for {symbol}: {err}")
    r = res[0]
    meta = r.get("meta") or {}

    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"no price for {symbol}")

    ts = meta.get("regularMarketTime")
    asof = (datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            if ts else datetime.now(timezone.utc).date().isoformat())

    # Daily closes for the sparkline, oldest first, gaps dropped.
    spark = []
    try:
        stamps = r.get("timestamp") or []
        closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        for t, c in zip(stamps, closes):
            if c is None:
                continue
            spark.append([datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat(), round(c, 4)])
    except Exception:  # noqa: BLE001 - sparkline is cosmetic, never fatal
        spark = []

    # Previous close = the most recent daily close BEFORE the current session.
    # meta.chartPreviousClose is the close at the start of the requested range (a year
    # ago for range=1y), so using it would report the annual move as the daily move.
    prev = None
    for day, close in reversed(spark):
        if day < asof:
            prev = close
            break
    if prev is None:
        prev = meta.get("previousClose") or meta.get("chartPreviousClose")

    change = round(price - prev, 4) if prev else None
    change_pct = round((price / prev - 1) * 100, 2) if prev else None

    age_days = (datetime.now(timezone.utc).date() - datetime.strptime(asof, "%Y-%m-%d").date()).days
    stale = age_days > STALE_AFTER_DAYS

    return {
        "age_days": age_days,
        "stale": stale,
        "stale_reason": (f"last trade {asof} is {age_days} days old - contract likely delisted"
                         if stale else None),
        "value": price,
        "prev_close": prev,
        "change": change,
        "change_pct": change_pct,
        "currency": meta.get("currency"),
        "exchange": meta.get("fullExchangeName"),
        "asof": asof,
        "spark": spark[-260:],
        "source": "Yahoo Finance",
    }


def fetch_many(symbols, rng="1y"):
    """Fetch a list of symbols. Returns (results, errors), both keyed by symbol."""
    out, errors = {}, {}
    for i, sym in enumerate(symbols):
        try:
            out[sym] = fetch_symbol(sym, rng)
        except Exception as e:  # noqa: BLE001
            errors[sym] = f"{type(e).__name__}: {e}"
        if i < len(symbols) - 1:
            time.sleep(PAUSE)
    return out, errors


if __name__ == "__main__":
    test = ["^AXJO", "^GSPC", "^AXPJ", "GC=F", "BTC-AUD"]
    res, errs = fetch_many(test)
    for s, q in res.items():
        flag = "  <-- STALE" if q.get("stale") else ""
        print(f"  {s:<10} {q['value']:>12}  {str(q['change_pct'])+'%':>8}  {q['currency']:<4} "
              f"{q['asof']}  spark={len(q['spark'])}{flag}")
    if errs:
        print("  ERRORS:", errs)
