# Morning Markets

A single page to read at 6am: the rates that price the debt, the inputs that price the
builds, and the macro signals that say which way the cycle is turning — aimed at
property development and construction rather than at trading.

Static site on GitHub Pages. A GitHub Actions cron fetches the data before the
Australian open, commits it to `data/`, and the page renders that JSON. No server, no
database, no paid feeds, no accounts beyond an optional free FRED key.

## What it shows

| Panel | Cadence | Contents |
|---|---|---|
| Rates & Credit | daily | RBA cash rate, AU 2/3/5/10yr, 3m bank bill, AU lending rates, US 2/10/30yr |
| Yield Curve Shape | daily | AU and US curves with 1-month and 1-year ghost overlays, spreads, shape classifier |
| Global Equities | end of day | 16 indices ordered by trading session — Americas, Europe, Asia, then our open |
| Property & Input Sectors | end of day | ASX 200 A-REIT, ASX 200 Materials, DJ US Real Estate, VNQ |
| FX & Crypto | daily | AUD crosses and TWI (RBA 4pm fixes), BTC/ETH in AUD |
| Inputs & Commodities | end of day | HRC steel, copper, aluminium, Brent, WTI, gold, VIX, DXY |
| Structural / Construction | quarterly & monthly | ABS construction PPIs, work done, dwelling commencements, CPI, WPI, mean dwelling price |

## Reading it honestly

Three things the page is explicit about, because a dashboard that flatters you is worse
than none:

- **It is not real time.** Real-time ASX and futures data is gated by exchange
  licensing, not API pricing. Every tile stamps the date its number refers to. For
  orienting yourself at 6am, previous close is the same information.
- **No tile is your steel price.** HRC futures are US Midwest hot-rolled coil — a real
  daily steel signal, but not delivered Australian rebar or structural steel, which is
  set by supply contracts and local fabricator margins. Treat it as direction, not cost.
- **The Australian curve mixes instruments.** Its short end (1M–6M) is bank bills, which
  carry bank credit risk; 2Y–10Y is Commonwealth government bonds. The step between them
  is a credit spread, not curve shape — so the chart draws bills as squares and bonds as
  circles. The RBA publishes no free interpolated yield past 10 years, so the AU curve
  stops where the US one runs on to 30Y.

## Data sources

All free. All either official or public.

| Source | Key needed | Used for |
|---|---|---|
| [RBA statistical tables](https://www.rba.gov.au/statistics/tables/) (F1, F2, F5, F6, F11.1) | no | Cash rate, AU bonds, bank bills, lending rates, FX |
| [US Treasury par yield curve](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve) | no | Full US curve, 13 tenors, 1M–30Y |
| [ABS Data API](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide) (SDMX-JSON) | no | Construction PPIs, work done, commencements, CPI, WPI, dwelling prices |
| Yahoo Finance chart endpoint | no | Equities, commodity futures, crypto |
| Coinbase / Kraken public APIs | no | Crypto fallback |
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | free key, optional | US Fed funds, US CPI |

Notes on sources that did **not** work, recorded so nobody retries them:

- **Stooq** now serves a JavaScript proof-of-work anti-bot challenge instead of CSV. It
  cannot be scripted server-side.
- **CoinGecko** now requires a free Demo API key, so Coinbase and Kraken are used instead.
- **Treasury FiscalData API** serves average interest rates on outstanding debt, *not*
  the par yield curve. It is the wrong dataset for curve shape.
- **ABS `RPPI`** stops at 2021-Q4 and **`CPI_M`** at 2025-09; both are discontinued.
  `RES_DWELL_ST` and `CPI` are the live replacements.
- **`TIO=F`** (SGX iron ore) last traded in 2021 and **`LBS=F`** (lumber) in 2023, but
  Yahoo still serves both with HTTP 200 and a stale price. They are excluded.

## Staleness guards

Free endpoints fail loudly less often than they fail *quietly*. Two guards exist because
both failure modes were hit while building this:

- `fetch/sources/yahoo.py` rejects any quote whose last trade is more than 10 days old.
- `fetch/sources/abs.py` flags series past their normal publication lag (120 days for
  monthly, 300 for quarterly).

Anything caught renders greyed and dashed with a `STALE` badge and the reason, rather
than as a live number.

## Running it locally

```bash
python fetch/main.py
```

Writes `data/latest.json`. Then serve the folder:

```bash
python -m http.server 8787
```

Each source module also runs standalone for debugging, e.g.:

```bash
PYTHONPATH=fetch python fetch/sources/rba.py
```

Requires Python 3.9+. No dependencies — everything is stdlib, so there is nothing to
install and nothing to break on upgrade.

> On a corporate Windows machine whose root certificate store has been trimmed by group
> policy, OpenSSL may fail to verify genuine certificates that Schannel accepts.
> `fetch/httpget.py` falls back to the `curl` binary in that case, with verification
> still enabled. CI runners never hit this path.

## Setup

1. Push to GitHub.
2. **Settings → Pages → Source: GitHub Actions.** Private repos need GitHub Pro for
   Pages; a public repo works on the free plan (the repo holds no private data — only
   published market figures).
3. Optional: **Settings → Secrets and variables → Actions** → add `FRED_API_KEY`
   ([free key here](https://fredaccount.stlouisfed.org/apikey)). Without it the FRED
   tiles are skipped and everything else still builds.
4. Run the workflow once manually from the Actions tab to confirm it works.

### If the scheduled run returns no market data

GitHub Actions runners use shared cloud IPs and Yahoo sometimes blocks those ranges. The
RBA, ABS and Treasury sources are unaffected. If Yahoo tiles come back empty from CI but
work locally, run the fetcher on Windows Task Scheduler instead and let it push — the
code is identical, only the trigger changes.

## Layout

```
fetch/
  main.py              orchestrator; isolates every source so one failure degrades one tile
  httpget.py           stdlib HTTP with a curl TLS fallback
  tiles.py             tile registry, panel order, curve building, shape classifier
  sources/             rba, abs, ustreasury, yahoo, crypto, fred
data/latest.json       what the page reads; committed each run so git history is the archive
index.html app.js style.css    single page, no build step
```

Committing the data each morning is deliberate: free APIs give you today's number, not
the series. The commit history becomes a growing archive of every series at no cost.
