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
| Rates & Credit | daily | RBA cash rate, AU 2/3/5/10yr and longest bond, 3m bank bill, AU lending rates, US 2/10/30yr |
| Credit & Lending | monthly & quarterly | BBB and A corporate bond yields and BBB spreads (F3), small/medium/large business lending rates (F7), credit growth (D1), housing finance commitments (ABS) |
| Yield Curve Shape | daily | AU curve to 2054 (bills, F2 bonds, then individual F16 bonds) and US curve, with 1-month and 1-year ghost overlays, spreads, shape classifier |
| Calendar & Releases | daily | Upcoming ABS releases, RBA and FOMC decisions in Sydney time; RBA, APRA and Fed media release headlines |
| Global Equities | end of day | 16 indices ordered by trading session — Americas, Europe, Asia, then our open |
| Property & Input Sectors | end of day | ASX 200 A-REIT, ASX 200 Materials, DJ US Real Estate, VNQ |
| Listed Property & Construction | end of day | ~80 developers, REITs, contractors, materials, lenders and global peers as a sortable screener: returns, market cap, P/E, P/B, yield, gearing |
| Capital City Property | quarterly | ABS median house and unit prices for all 8 capitals, QoQ and YoY |
| Supply Pipeline | monthly & quarterly | Dwelling approvals (rolling 12 months) nationally and by capital; dwellings under construction and completed |
| Demand & Labour | monthly & quarterly | Unemployment, job vacancies, population growth, net overseas migration |
| FX & Crypto | daily | AUD crosses and TWI (RBA 4pm fixes), BTC/ETH in AUD |
| Inputs & Commodities | end of day & monthly | Steel (HRC + producers), copper, aluminium; Brent, WTI, **diesel**, US & EU gas; NEM wholesale electricity by state; World Bank iron ore, coal and timber; freight & shipping; gold, VIX, DXY |
| Thematic & Cycle | end of day | Housing/infrastructure, materials & energy sectors, energy-transition themes |
| Inflation | mixed | Headline, trimmed mean and weighted median CPI, CPI rents, plus **daily AU and US breakevens** |
| Structural / Construction | quarterly | ABS construction PPIs, materials used in house building by capital, work done, dwelling commencements, WPI, mean dwelling price |

## Drilling in

Every tile opens. Click it (or Tab to it and press Enter) for a full-size chart with
1M to 10Y ranges, the window's high, low and where today sits between them, period
returns from 1W to 5Y, a description of the series, and the latest releases as a table
with a CSV download of the whole history. `←` and `→` step through the rest of the panel;
`Esc` closes. The URL follows the view (`#/au_10y`), so a chart can be sent as a link.

Press `/` or `Ctrl+K` anywhere for the command line. Type a name or a code (`hrc`,
`axjo`, `sydney house`, `au 10`) and Enter. Borrowing Bloomberg's habit, a trailing
mnemonic picks the section: `GP` the chart (the default), `HP` the history table,
`DES` the description, so `hrc hp` lands on steel's recent closes.

`Compare +` on any chart (or `COMP` after a name in the command line) overlays up to four
series from the same start date - prices rebased to percent, rates in basis points, on
separate axes when both are present, because they cannot honestly share one. Presets
cover the pairings that decide a feasibility: A-REITs against the 10-year, the steel
chain, energy inputs, the rates path.

Layouts across the top (Debt, Inputs, Cycle, Stocks, Watchlist) cut the page for the
question at hand; `☆ Watch` on any chart pins it. Both live in your browser only.

Two strips sit above the panels. **Next up** lists the high-importance releases in the
next fortnight. **Unusual moves** ranks today's moves by how far each sits outside that
series' own normal daily range (today's change over the standard deviation of a year of
daily changes), so a 3σ diesel move outranks a routine Nasdaq wobble. A traded price
that sat unchanged for four or more sessions and then stepped is tagged `THIN` and kept
off that strip - HRC futures did exactly this in Sep 2026, and the step was a thin
market or contract roll, not news.

History depth follows the source: 10 years for RBA and ABS series, 5 years for Yahoo
and Treasury (each extra year costs requests or bytes).

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
  circles. The RBA publishes no interpolated yield past 10 years, so beyond 10Y the curve
  plots individual Treasury bonds from table F16 at their actual maturities, drawn as
  hollow circles - real bonds, not a fitted curve.

## Data sources

All free. All either official or public.

| Source | Key needed | Used for |
|---|---|---|
| [RBA statistical tables](https://www.rba.gov.au/statistics/tables/) (F1, F2, F5, F6, F11.1) | no | Cash rate, AU bonds, bank bills, lending rates, FX |
| [US Treasury par yield curve](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve) | no | Full US curve, 13 tenors, 1M–30Y |
| [ABS Data API](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/data-api-user-guide) (SDMX-JSON) | no | Construction PPIs, work done, commencements, CPI, WPI, dwelling prices, capital city medians |
| Yahoo Finance chart endpoint | no | Equities, commodity futures, crypto |
| Coinbase / Kraken public APIs | no | Crypto fallback |
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | free key, optional | US Fed funds, US CPI |
| RBA tables F3, F7, F16, D1 | no | Corporate bond yields, business lending rates, individual long bonds, credit growth |
| ABS `BA_GCCSA`, `LEND_HOUSING`, `LF`, `JV`, `ERP_COMP_Q`, PPI inputs | no | Approvals, housing finance, labour, population, materials costs by city |
| [World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) (CC BY 4.0) | no | Iron ore, Australian coal, sawnwood, plywood (monthly) |
| [AEMO price and demand](https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data) | no | NEM wholesale electricity by region; history accumulates run over run |
| ABS release calendar, RBA board schedule, Fed FOMC calendar | no | Upcoming releases and rate decisions, Sydney time |
| RBA, APRA and Fed media pages / RSS | no | Headlines and links only - never article text |
| Yahoo Finance `quoteSummary` (cookie + crumb) | no | Key statistics for the equity universe, refreshed weekly |

Deliberately **not** used, because this repo and site are public and the terms say no:

- **ASX** (Rate Tracker implied cash-rate path, the listed companies CSV): site terms allow
  personal, non-commercial use only. The equity universe is hand-curated in
  `fetch/sources/universe.py` instead.
- **ICE BofA credit spreads via FRED**: ICE's notes restrict them to internal use. BBB
  spreads here are computed from RBA F3 less F2.
- **AIP terminal gate prices** (diesel by city): no licence stated, so treated as all rights
  reserved. NY Harbor ULSD futures stay the diesel read.
- **Atlanta Fed market probability tracker**: terms not yet reviewed.
- **Company business descriptions** from Yahoo: licensed third-party prose. Only numbers
  and short facts (sector, industry, website) are stored.

Each of those is a question for a lawyer, not one to infer - and all of them change if the
site is ever made private.

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
- **Domain** is not used. Their developer API publishes no free tier (OAuth, contract
  pricing, industry-oriented), and `domain.com.au` blocks automated requests at the edge
  — even `robots.txt` returns an Akamai *Access Denied*. Separately, republishing their
  proprietary stratified-median index from a public repo is a copyright/terms question
  for a lawyer, not one to infer. ABS `RES_DWELL` is the free official substitute and
  carries all eight capitals.

## Inflation expectations come free

The most useful inflation tiles here are *daily*, not quarterly, and cost nothing extra
because both sit in feeds already being fetched:

- **AU 10-year breakeven** — the RBA publishes a 10-year indexed (inflation-linked) bond
  yield in table F2 alongside the nominal. The difference is the market's 10-year
  inflation expectation.
- **US 5/10/30-year breakevens** — Treasury serves a real (TIPS) par yield curve from the
  same XML feed as the nominal one, just `data=daily_treasury_real_yield_curve`. Nominal
  less real gives the breakeven.

The ABS underlying measures the RBA actually targets — trimmed mean and weighted median
— live in the `CPI_Q` dataflow (seasonally adjusted), not `CPI`, and are published only
as an index, so the annual change is computed here. Their sparklines plot the annual rate
rather than the index; charting the index would draw a rising line beneath a falling rate.

## Freight and shipping: no free container index

Container freight indices are proprietary. Drewry's World Container Index is published
weekly on their site and their `robots.txt` does permit crawling, but it remains a
commercial index and republishing it from a public repo is the same redistribution
problem as any other licensed feed. The Freightos Baltic Index sits behind Cloudflare
redirects. The Baltic Dry Index (`^BDIY`) is not on Yahoo.

The dashboard uses free market proxies instead, which are arguably better for reading
direction anyway:

- **BDRY** — dry bulk freight futures: the cost of moving iron ore, coal, cement and
  aggregates.
- **Maersk, ZIM, BOAT** — container liner equities. ZIM is close to a pure-play spot
  carrier, so it tracks container rates fairly directly.

## Rental yields: why there is no city-level yield panel

A gross yield needs median rent over median price. Prices are solved — ABS `RES_DWELL`
gives all eight capitals. **Rents are not**, and the gap is in the data, not the code:

- The ABS publishes no rent series by capital city. Both CPI "Rents" codes (`30014`,
  `115522`) exist only for `REGION=50` (Australia), and neither offers an annual-change
  measure. National CPI Rents is carried in the structural panel with year-on-year
  computed from the index.
- Australian rent levels come from **state bond authorities**, and they are not usable
  as one series: Victoria's Rental Report is on data.gov.au but the latest quarter
  published is ~12 months behind; NSW offers only "website link" and PDF resources, last
  touched in 2022–23; Queensland's RTA medians are not on the state open-data portal at
  all. They also report by LGA rather than Greater Capital City, on differing definitions.
- Computing Sydney and Melbourne yields off different bases and different vintages would
  be worse than showing nothing, because the comparison between them is the whole point.

Current city-level yields are a commercial product (Cotality, SQM Research, Domain,
PropTrack).

**Decision (Sep 2026): stay on free sources.** The A-REIT tile is the daily read on where
the market prices yield. Licensing a commercial feed would also collide with this repo
being public — most such licences prohibit redistribution, so publishing the data to a
public Pages site would likely breach the terms. Revisit only if a specific decision
actually turns on a stratified or yield number, and get the licence terms checked before
any licensed data enters the repo.

## Stratified price indexes

The ABS used to publish exactly this — `6416.0 Residential Property Price Indexes: Eight
Capital Cities`, stratified, split into House and Attached Dwellings. **It ceased with
the December quarter 2021 issue** and was folded into *Total Value of Dwellings*, which
carries mean price rather than a stratified index. The `RPPI` dataflow is still in the
API and still returns data, which is a trap — it stops at 2021-Q4.

So there is no free stratified or hedonic Australian price index post-2021. What this
dashboard uses, `RES_DWELL`, is an **unstratified** median: a straight median of actual
transfers, so it is noisier quarter to quarter and moves with whatever happened to sell.
That is why every city tile leads with year-on-year rather than the quarterly move.

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

## A note on merge conflicts

`data/latest.json` is regenerated in full on every run, and CI refreshes it on a cron
while you may be rebuilding it locally from new code. `.gitattributes` marks it
`merge=ours` so rebases stop trying to hand-merge generated JSON (the same applies to
`data/series/`). Enable the
driver once per clone:

```bash
git config merge.ours.driver true
```

## Layout

```
fetch/
  main.py              orchestrator; isolates every source so one failure degrades one tile
  httpget.py           stdlib HTTP with a curl TLS fallback
  tiles.py             tile registry, panel order, curve building, shape classifier
  sources/             rba, abs, ustreasury, yahoo, crypto, fred - the core set
                       rba_extra, abs_extra, worldbank, aemo, releases, news, universe -
                       imported one by one, so a broken module costs only its own tiles
data/latest.json       what the page reads on load: every tile, with a thinned sparkline
data/series/{id}.json  full history per tile, fetched only when that tile is opened
data/company/{id}.json key statistics per listed company, refreshed when a week old
index.html app.js style.css    single page, no build step
chart.js explore.js    drill-down chart, and the drill-down view + command line
```

Committing the data each morning is deliberate: free APIs give you today's number, not
the series. The commit history becomes a growing archive of every series at no cost.
