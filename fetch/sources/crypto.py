"""Crypto spot prices, keyless.

Yahoo already returns BTC-AUD / ETH-AUD, so this exists as a fallback for when Yahoo
is unavailable. Both Coinbase and Kraken serve public endpoints with no account.
CoinGecko is deliberately not used - it now requires a (free) Demo API key, and the
point of this build is no extra accounts.
"""
from httpget import get_json

COINBASE = "https://api.coinbase.com/v2/prices/{pair}/spot"
KRAKEN = "https://api.kraken.com/0/public/Ticker?pair={pair}"


def coinbase(pair="BTC-AUD"):
    js = get_json(COINBASE.format(pair=pair))
    return float(js["data"]["amount"])


def kraken(pair="XBTUSD"):
    js = get_json(KRAKEN.format(pair=pair))
    if js.get("error"):
        raise ValueError(f"kraken error: {js['error']}")
    result = js["result"]
    key = next(iter(result))
    return float(result[key]["c"][0])  # 'c' = last trade closed [price, lot volume]


def fetch(pair="BTC-AUD"):
    """Try Coinbase, then Kraken. Returns (value, source)."""
    errors = []
    try:
        return coinbase(pair), "Coinbase"
    except Exception as e:  # noqa: BLE001
        errors.append(f"coinbase: {e}")
    kpair = {"BTC-AUD": "XBTAUD", "ETH-AUD": "ETHAUD",
             "BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD"}.get(pair)
    if kpair:
        try:
            return kraken(kpair), "Kraken"
        except Exception as e:  # noqa: BLE001
            errors.append(f"kraken: {e}")
    raise RuntimeError("; ".join(errors))


if __name__ == "__main__":
    for p in ("BTC-AUD", "ETH-AUD"):
        try:
            v, src = fetch(p)
            print(f"  {p:<9} {v:>14,.2f}  via {src}")
        except Exception as e:  # noqa: BLE001
            print(f"  {p:<9} FAILED: {e}")
