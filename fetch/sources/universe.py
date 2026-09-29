"""Curated equity universe for the stock search and company view.

A hand-picked list of the listed names that move a developer's world - the landlords
and developers they compete and joint-venture with, the contractors they hire, the
suppliers they buy from, the banks that lend to them, and a set of offshore peers that
tend to turn first. It is deliberately a list in code, not a scraped exchange directory:
the ASX company list and its markitdigital API are licensed for personal,
non-commercial use only, and this site is public.

Prices come from the same keyless Yahoo chart endpoint as the rest of the dashboard.
Key statistics come from Yahoo's quoteSummary endpoint, which is UNOFFICIAL and needs a
cookie + crumb handshake - it has changed without notice before and will again, so
profiles are cached per company and a failed handshake falls back to the cache.
"""
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Run both as `python fetch/sources/universe.py` and imported from main.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpget  # noqa: E402
from sources.yahoo import STALE_AFTER_DAYS, fetch_symbol  # noqa: E402

PAUSE = 0.6  # >= 0.5s between Yahoo requests; eighty names is a lot to ask of a free endpoint

# ------------------------------------------------------------------------ universe
# (yahoo_symbol, display_name, group)
#
# Every symbol below was checked live against the Yahoo chart endpoint on 29 Sep 2026:
# each returned a result with a last trade of 28 Sep 2026, i.e. within STALE_AFTER_DAYS.
# Candidates dropped in that check, recorded so nobody re-adds them:
#   404 (no longer quoted - acquired, merged or delisted):
#     BLD.AX Boral, ABC.AX Adbri, CSR.AX CSR, CIM.AX CIMIC, BKW.AX Brickworks (merged
#     into Soul Patts, SOL.AX), DHG.AX Domain, NSR.AX National Storage, AVJ.AX AVJennings,
#     AOF.AX Australian Unity Office, IPL.AX Incitec Pivot, JLG.AX Johns Lyng,
#     AVN.AX Aventus, ASK.AX Abacus Storage King, LIF.AX Life360, PEXA.AX (PEXA is PXA.AX)
#   renamed: SVW.AX Seven Group -> SGH.AX (404 on the old code).
#   stale:   QUB.AX Qube - HTTP 200 but last trade 8 Jul 2026, 83 days old.
#   wrong company on a familiar code: SCP.AX is now Scalare Partners (the old SCA
#     Property is RGN.AX Region Group); FRW.AX is Freightways (NZ), not a builder.
# Re-verify before editing: a code that 404s today was a live company last year, and a
# code that returns 200 may be a different company or a dead line with a frozen price.
UNIVERSE = [
    # Landlords, fund managers, developers and land-lease operators
    ("GMG.AX", "Goodman Group", "A-REITs & developers"),
    ("SCG.AX", "Scentre Group", "A-REITs & developers"),
    ("SGP.AX", "Stockland", "A-REITs & developers"),
    ("MGR.AX", "Mirvac", "A-REITs & developers"),
    ("DXS.AX", "Dexus", "A-REITs & developers"),
    ("GPT.AX", "GPT Group", "A-REITs & developers"),
    ("VCX.AX", "Vicinity Centres", "A-REITs & developers"),
    ("CHC.AX", "Charter Hall Group", "A-REITs & developers"),
    ("LLC.AX", "Lendlease", "A-REITs & developers"),
    ("CQR.AX", "Charter Hall Retail REIT", "A-REITs & developers"),
    ("CLW.AX", "Charter Hall Long WALE REIT", "A-REITs & developers"),
    ("CIP.AX", "Centuria Industrial REIT", "A-REITs & developers"),
    ("ARF.AX", "Arena REIT", "A-REITs & developers"),
    ("BWP.AX", "BWP Trust", "A-REITs & developers"),
    ("HDN.AX", "HomeCo Daily Needs REIT", "A-REITs & developers"),
    ("GOZ.AX", "Growthpoint Properties", "A-REITs & developers"),
    ("RGN.AX", "Region Group", "A-REITs & developers"),
    ("INA.AX", "Ingenia Communities", "A-REITs & developers"),
    ("LIC.AX", "Lifestyle Communities", "A-REITs & developers"),
    ("HMC.AX", "HMC Capital", "A-REITs & developers"),
    ("PPC.AX", "Peet", "A-REITs & developers"),
    ("CWP.AX", "Cedar Woods Properties", "A-REITs & developers"),

    # Who you hire - builders, civil, services and plant
    ("DOW.AX", "Downer EDI", "Contractors & engineering"),
    ("MND.AX", "Monadelphous", "Contractors & engineering"),
    ("NWH.AX", "NRW Holdings", "Contractors & engineering"),
    ("VNT.AX", "Ventia Services", "Contractors & engineering"),
    ("SSM.AX", "Service Stream", "Contractors & engineering"),
    ("GNG.AX", "GR Engineering Services", "Contractors & engineering"),
    ("LYL.AX", "Lycopodium", "Contractors & engineering"),
    ("SXE.AX", "Southern Cross Electrical", "Contractors & engineering"),
    ("DUR.AX", "Duratec", "Contractors & engineering"),
    ("CVL.AX", "Civmec", "Contractors & engineering"),
    ("MGH.AX", "Maas Group", "Contractors & engineering"),
    ("SGH.AX", "SGH (Coates hire)", "Contractors & engineering"),

    # What you buy - and where it is sold
    ("JHX.AX", "James Hardie", "Building materials & products"),
    ("FBU.AX", "Fletcher Building", "Building materials & products"),
    ("RWC.AX", "Reliance Worldwide", "Building materials & products"),
    ("GWA.AX", "GWA Group", "Building materials & products"),
    ("BXB.AX", "Brambles", "Building materials & products"),
    ("SOL.AX", "Soul Patts (incl. Brickworks)", "Building materials & products"),
    ("WES.AX", "Wesfarmers (Bunnings)", "Building materials & products"),

    # Steel, scrap and the iron ore / metals complex
    ("BSL.AX", "BlueScope Steel", "Steel, metals & miners"),
    ("SGM.AX", "Sims", "Steel, metals & miners"),
    ("BHP.AX", "BHP", "Steel, metals & miners"),
    ("RIO.AX", "Rio Tinto", "Steel, metals & miners"),
    ("FMG.AX", "Fortescue", "Steel, metals & miners"),
    ("S32.AX", "South32", "Steel, metals & miners"),
    ("MIN.AX", "Mineral Resources", "Steel, metals & miners"),

    # Who lends to you - majors, regionals, challengers and private credit
    ("CBA.AX", "Commonwealth Bank", "Banks & lenders"),
    ("WBC.AX", "Westpac", "Banks & lenders"),
    ("NAB.AX", "National Australia Bank", "Banks & lenders"),
    ("ANZ.AX", "ANZ", "Banks & lenders"),
    ("MQG.AX", "Macquarie Group", "Banks & lenders"),
    ("BOQ.AX", "Bank of Queensland", "Banks & lenders"),
    ("BEN.AX", "Bendigo and Adelaide Bank", "Banks & lenders"),
    ("JDO.AX", "Judo Capital", "Banks & lenders"),
    ("PPM.AX", "Pepper Money", "Banks & lenders"),
    ("MAF.AX", "MA Financial", "Banks & lenders"),

    # Demand signals and the infrastructure that sets land values
    ("REA.AX", "REA Group", "Property services & infrastructure"),
    ("PXA.AX", "PEXA Group", "Property services & infrastructure"),
    ("TCL.AX", "Transurban", "Property services & infrastructure"),
    ("ALX.AX", "Atlas Arteria", "Property services & infrastructure"),

    # Offshore peers - US and UK housebuilders tend to turn before ours
    ("DHI", "D.R. Horton", "Global peers"),
    ("LEN", "Lennar", "Global peers"),
    ("PHM", "PulteGroup", "Global peers"),
    ("PLD", "Prologis", "Global peers"),
    ("CRH", "CRH", "Global peers"),
    ("VMC", "Vulcan Materials", "Global peers"),
    ("CX", "Cemex", "Global peers"),
    ("DG.PA", "Vinci", "Global peers"),
    ("HOLN.SW", "Holcim", "Global peers"),
    ("HEI.DE", "Heidelberg Materials", "Global peers"),
    ("SGO.PA", "Saint-Gobain", "Global peers"),
    ("HOT.DE", "Hochtief (ex-CIMIC parent)", "Global peers"),
    ("BTRW.L", "Barratt Redrow", "Global peers"),
    ("SGRO.L", "SEGRO", "Global peers"),
    ("8801.T", "Mitsui Fudosan", "Global peers"),
    ("1928.T", "Sekisui House", "Global peers"),
    ("000002.SZ", "China Vanke", "Global peers"),
    ("1109.HK", "China Resources Land", "Global peers"),
]


def tile_id(symbol):
    """'LLC.AX' -> 'eq_llc_ax', '8801.T' -> 'eq_8801_t', 'HOLN.SW' -> 'eq_holn_sw'."""
    return "eq_" + re.sub(r"[^a-z0-9]+", "_", symbol.lower()).strip("_")


# ---------------------------------------------------------------------------- prices
def fetch_prices(universe=UNIVERSE):
    """Fetch five years of daily closes per name. Returns (tiles, errors).

    Tiles are in main.py's schema with the full daily series in "spark"; main.py's
    history step writes it to data/series/ and thins the sparkline. A symbol that fails
    still yields an "unavailable" tile, as main.py does for its own Yahoo tiles, so the
    name stays searchable on a bad morning.
    """
    out, errors = [], {}
    for i, (sym, name, group) in enumerate(universe):
        tid = tile_id(sym)
        try:
            q = fetch_symbol(sym, "5y")
        except Exception as e:  # noqa: BLE001 - one bad symbol never sinks the run
            errors[f"yahoo/{sym}"] = f"{type(e).__name__}: {e}"
            out.append({"id": tid, "label": name, "panel": "universe", "group": group,
                        "symbol": sym, "status": "unavailable", "source": "Yahoo Finance",
                        "error": errors[f"yahoo/{sym}"]})
        else:
            # fetch_symbol applies the STALE_AFTER_DAYS guard. A delisted name keeps
            # returning HTTP 200 with its last price, so status is what stops a dead
            # company rendering as a live quote.
            status = "stale" if q.get("stale") else "ok"
            if status == "stale":
                errors[f"tile/{tid}"] = q.get("stale_reason")
            out.append({
                "id": tid, "label": name, "panel": "universe", "group": group,
                "symbol": sym,
                # Currency is Yahoo's code verbatim. London lines quote in pence ("GBp",
                # lower-case p), not pounds - render it as-is rather than as GBP.
                "value": q["value"], "unit": q.get("currency"),
                "change": q["change"], "change_pct": q["change_pct"],
                "asof": q["asof"], "age_days": q.get("age_days"),
                "freq": "D",
                "spark": q["spark"],
                "source": "Yahoo Finance",
                "note": None,
                "status": status,
                "stale_reason": q.get("stale_reason"),
            })
        if i < len(universe) - 1:
            time.sleep(PAUSE)
    return out, errors


# -------------------------------------------------------------------------- profiles
# quoteSummary is not the chart endpoint: since 2023 it answers 401 "Invalid Crumb"
# unless the request carries Yahoo's session cookie AND a crumb minted for that cookie.
# The handshake: collect cookies from a Yahoo page, GET /v1/test/getcrumb with them, then
# pass ?crumb= on every quoteSummary call with the same cookies. Unofficial throughout.
COOKIE_URLS = ["https://fc.yahoo.com", "https://finance.yahoo.com/"]
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"
SUMMARY_URL = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
               "?modules=assetProfile,summaryDetail,defaultKeyStatistics,financialData,price"
               "&crumb={crumb}")

# (field, module, ...fallback modules). NUMBERS AND SHORT FACTS ONLY. assetProfile also
# carries longBusinessSummary and officer names - licensed third-party prose and personal
# data, neither of which belongs in a public repo - so fields are whitelisted, never
# copied wholesale.
PROFILE_FIELDS = [
    ("longName", "price"),
    ("shortName", "price"),
    ("exchange", "price"),            # read from price.exchangeName
    ("currency", "price", "summaryDetail", "financialData"),
    ("sector", "assetProfile"),
    ("industry", "assetProfile"),
    ("country", "assetProfile"),
    ("website", "assetProfile"),
    ("marketCap", "price", "summaryDetail"),
    ("enterpriseValue", "defaultKeyStatistics"),
    ("trailingPE", "summaryDetail"),
    ("forwardPE", "summaryDetail", "defaultKeyStatistics"),
    ("priceToBook", "defaultKeyStatistics"),
    ("dividendYield", "summaryDetail"),
    ("trailingAnnualDividendYield", "summaryDetail"),
    ("fiftyTwoWeekHigh", "summaryDetail"),
    ("fiftyTwoWeekLow", "summaryDetail"),
    ("beta", "summaryDetail", "defaultKeyStatistics"),
    ("totalDebt", "financialData"),
    ("totalCash", "financialData"),
    ("debtToEquity", "financialData"),
    ("returnOnEquity", "financialData"),
    ("profitMargins", "financialData", "defaultKeyStatistics"),
    ("sharesOutstanding", "defaultKeyStatistics"),
    ("averageVolume", "summaryDetail", "price"),
]
SOURCE_KEYS = {"exchange": "exchangeName"}
# Units, because Yahoo mixes them: both dividend yields are converted from fractions to
# percent here (4.5 means 4.5%). debtToEquity already arrives as a percent (45 = 0.45x).
# returnOnEquity and profitMargins stay as Yahoo's fractions (0.12 = 12%). Money fields
# are in the listing currency, which for London lines is still GBP-denominated totals
# even though the share price is in pence.
AS_PERCENT = {"dividendYield", "trailingAnnualDividendYield"}


def _raw(v):
    """Yahoo wraps numbers as {"raw": 1.23, "fmt": "1.23"}; empty dicts mean missing."""
    if isinstance(v, dict):
        return v.get("raw")
    return v


def parse_profile(result):
    prof = {}
    for field, *modules in PROFILE_FIELDS:
        key = SOURCE_KEYS.get(field, field)
        for m in modules:
            v = _raw((result.get(m) or {}).get(key))
            if v is None or v == "":
                continue
            if field in AS_PERCENT and isinstance(v, (int, float)):
                v = round(v * 100, 3)
            prof[field] = v
            break
    return prof


class _YahooSession:
    """Cookie-carrying GETs: urllib + http.cookiejar, or curl with a jar file.

    Local runs on this machine fail Python's TLS verification (GPO-trimmed root store);
    curl on Windows uses Schannel and verifies fine. Same pattern as httpget._curl, but
    the cookies must survive between requests, so curl gets a jar file (-c/-b) in a
    temp dir. Verification stays on in both modes - no -k, no unverified context.
    """

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=httpget._context()),
            urllib.request.HTTPCookieProcessor(self.jar))
        self.use_curl = False
        self.tmp = None
        self.jarfile = None

    def _to_curl(self):
        if not shutil.which("curl"):
            raise RuntimeError("TLS verification failed and curl unavailable for fallback")
        self.use_curl = True
        self.tmp = tempfile.mkdtemp(prefix="yq_")
        self.jarfile = os.path.join(self.tmp, "cookies.txt")

    def close(self):
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def get(self, url, allow_error=False):
        """Return (status, body_bytes). allow_error=True keeps 4xx bodies (the cookie
        step: fc.yahoo.com answers 404 but still sets the cookie)."""
        if not self.use_curl:
            req = urllib.request.Request(url, headers={
                "User-Agent": httpget.UA, "Accept": "*/*", "Accept-Language": "en-AU,en;q=0.9"})
            try:
                with self.opener.open(req, timeout=httpget.TIMEOUT) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                # Cookies are already in the jar - HTTPCookieProcessor runs before the
                # error processor raises.
                body = e.read()
                if allow_error:
                    return e.code, body
                raise RuntimeError(f"HTTP {e.code}: {body[:120]!r}") from e
            except Exception as e:  # noqa: BLE001
                if not httpget._is_tls_error(e):
                    raise
                self._to_curl()
        return self._curl(url, allow_error)

    def _curl(self, url, allow_error):
        out = os.path.join(self.tmp, "body")
        cmd = [shutil.which("curl"), "-sSL", "--compressed", "--max-time", str(httpget.TIMEOUT),
               "-A", httpget.UA, "-H", "Accept-Language: en-AU,en;q=0.9",
               "-c", self.jarfile, "-b", self.jarfile,
               "-o", out, "-w", "%{http_code}", url]
        r = subprocess.run(cmd, capture_output=True, timeout=httpget.TIMEOUT + 15)
        if r.returncode != 0:
            raise RuntimeError(f"curl exit {r.returncode}: {r.stderr.decode(errors='replace')[:200]}")
        code = int((r.stdout.decode().strip() or "0")[-3:])
        body = b""
        if os.path.exists(out):
            with open(out, "rb") as f:
                body = f.read()
            os.remove(out)
        if code >= 400 and not allow_error:
            raise RuntimeError(f"HTTP {code}: {body[:120]!r}")
        return code, body


def _get_crumb(sess):
    """Run the cookie + crumb handshake. Returns the crumb or raises."""
    last = None
    for url in COOKIE_URLS:
        try:
            sess.get(url, allow_error=True)
        except Exception as e:  # noqa: BLE001 - try the next cookie source
            last = f"{url}: {type(e).__name__}: {e}"
            continue
        time.sleep(PAUSE)
        try:
            code, body = sess.get(CRUMB_URL, allow_error=True)
        except Exception as e:  # noqa: BLE001
            last = f"getcrumb: {type(e).__name__}: {e}"
            continue
        crumb = body.decode("utf-8", errors="replace").strip()
        # A failed crumb comes back as HTML, a JSON error, or "Too Many Requests" -
        # a real one is a short token with no markup or spaces.
        if code == 200 and crumb and len(crumb) < 40 and not re.search(r"[<{\s]", crumb):
            return crumb
        last = f"getcrumb after {url}: HTTP {code} {crumb[:80]!r}"
        time.sleep(PAUSE)
    raise RuntimeError(f"crumb handshake failed ({last})")


def _read_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 - missing or corrupt cache is just a miss
        return None


def _cache_age_days(rec):
    try:
        t = datetime.fromisoformat(rec["fetched_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() / 86400
    except Exception:  # noqa: BLE001
        return None


def fetch_profiles(universe=UNIVERSE, cache_dir=None, max_age_days=7):
    """Key statistics per company. Returns ({tile_id: profile}, errors). Never raises.

    One cache file per company at {cache_dir}/{tile_id}.json. Fresh files (younger than
    max_age_days) skip the network entirely - these numbers move quarterly, so a weekly
    refresh keeps the unofficial endpoint's load to a trickle. On any failure the last
    cached profile is served, however old, and the error is reported.
    """
    if cache_dir is None:
        raise ValueError("cache_dir is required")
    os.makedirs(cache_dir, exist_ok=True)
    profiles, errors, todo = {}, {}, []

    for sym, _name, _group in universe:
        tid = tile_id(sym)
        rec = _read_cache(os.path.join(cache_dir, f"{tid}.json"))
        age = _cache_age_days(rec) if rec else None
        if rec and age is not None and age < max_age_days:
            profiles[tid] = rec
        else:
            todo.append((sym, tid, rec))
    if not todo:
        return profiles, errors

    sess = _YahooSession()
    try:
        try:
            crumb = _get_crumb(sess)
        except Exception as e:  # noqa: BLE001 - serve the cache, report, move on
            errors["quoteSummary/crumb"] = f"{type(e).__name__}: {e}"
            for _sym, tid, rec in todo:
                if rec:
                    profiles[tid] = rec
            return profiles, errors

        refreshed = False
        for i, (sym, tid, rec) in enumerate(todo):
            time.sleep(PAUSE)
            try:
                url = SUMMARY_URL.format(sym=urllib.parse.quote(sym, safe=""),
                                         crumb=urllib.parse.quote(crumb, safe=""))
                code, body = sess.get(url, allow_error=True)
                # Crumbs expire mid-run occasionally. Re-mint once, then give up.
                if code == 401 and not refreshed:
                    refreshed = True
                    crumb = _get_crumb(sess)
                    time.sleep(PAUSE)
                    url = SUMMARY_URL.format(sym=urllib.parse.quote(sym, safe=""),
                                             crumb=urllib.parse.quote(crumb, safe=""))
                    code, body = sess.get(url, allow_error=True)
                js = json.loads(body.decode("utf-8", errors="replace"))
                qs = js.get("quoteSummary") or {}
                res = qs.get("result") or []
                if code != 200 or not res:
                    raise ValueError(f"HTTP {code}: {qs.get('error') or js.get('finance')}")
                prof = parse_profile(res[0])
                if not prof:
                    raise ValueError("empty profile")
                out = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "symbol": sym, **prof}
                with open(os.path.join(cache_dir, f"{tid}.json"), "w", encoding="utf-8") as f:
                    json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
                profiles[tid] = out
            except Exception as e:  # noqa: BLE001 - one company never sinks the run
                errors[f"quoteSummary/{sym}"] = f"{type(e).__name__}: {e}"
                if rec:
                    profiles[tid] = rec
    finally:
        sess.close()
    return profiles, errors


if __name__ == "__main__":
    ids = [tile_id(s) for s, _n, _g in UNIVERSE]
    assert len(ids) == len(set(ids)), "tile id collision"
    counts = {}
    for _s, _n, g in UNIVERSE:
        counts[g] = counts.get(g, 0) + 1
    print(f"Universe: {len(UNIVERSE)} names")
    for g, n in counts.items():
        print(f"  {n:>3}  {g}")

    t0 = time.time()
    tl, errs = fetch_prices()
    t_prices = time.time() - t0
    by = {}
    for t in tl:
        by[t["status"]] = by.get(t["status"], 0) + 1
    print(f"\nPrices: {by} in {t_prices:.1f}s (stale guard {STALE_AFTER_DAYS}d)")
    for t in tl:
        if t["status"] != "ok":
            print(f"  {t['symbol']:<10} {t['status']}: {t.get('stale_reason') or t.get('error')}")
    for t in tl[:3] + tl[-3:]:
        if t["status"] != "unavailable":
            print(f"  {t['id']:<16} {t['value']:>10} {t['unit']:<4} {str(t['change_pct'])+'%':>7} "
                  f"{t['asof']}  spark={len(t['spark'])}")

    t1 = time.time()
    tmp = tempfile.mkdtemp(prefix="profiles_")
    sample = [u for u in UNIVERSE if u[0] in ("LLC.AX", "8801.T", "DHI")]
    profs, perrs = fetch_profiles(sample, tmp)
    print(f"\nProfiles: {len(profs)} into {tmp} in {time.time() - t1:.1f}s")
    for tid, p in profs.items():
        print(f"  {tid}: " + ", ".join(f"{k}={v}" for k, v in p.items()))
    if perrs:
        print("  ERRORS:", perrs)
    # Second call should be served entirely from cache.
    t2 = time.time()
    again, _ = fetch_profiles(sample, tmp)
    print(f"  cached re-read: {len(again)} in {time.time() - t2:.2f}s")
    print(f"\nTotal runtime {time.time() - t0:.1f}s")
