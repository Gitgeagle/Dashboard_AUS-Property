"""Upcoming release and decision calendar: ABS releases, RBA and FOMC rate decisions.

Named releases.py, not calendar.py: a module called calendar in a directory on sys.path
shadows the stdlib calendar module, which http.cookiejar and email.utils import.

All times are expressed in Sydney local time, because that is when the reader sees the
number. Every source is scraped separately so one layout change drops one category.
"""
import html
import re
from datetime import date, datetime, timedelta, timezone

from httpget import get_text

ABS_URL = "https://www.abs.gov.au/release-calendar/future-releases/{ym}/all"
RBA_URL = "https://www.rba.gov.au/schedules-events/board-meeting-schedules.html"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}
MON3 = {k[:3]: v for k, v in MONTHS.items()}

# ------------------------------------------------------------------ time zones
# zoneinfo needs the IANA database. Ubuntu runners have it; Windows Python usually does
# not (no tzdata package), and ZoneInfo then raises. The fallback below hard-codes the
# current rules, which have been stable since 2007 (US) and 2008 (NSW):
#   Sydney:     AEDT (UTC+11) from 02:00 AEST first Sunday of October
#               to 03:00 AEDT first Sunday of April; otherwise AEST (UTC+10).
#   US Eastern: EDT (UTC-4) from 02:00 EST second Sunday of March
#               to 02:00 EDT first Sunday of November; otherwise EST (UTC-5).
try:
    from zoneinfo import ZoneInfo
    _SYD, _NY = ZoneInfo("Australia/Sydney"), ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001 - missing tzdata, use the manual rules
    _SYD = _NY = None


def _nth_sunday(y, m, n):
    d = date(y, m, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _sydney_offset(utc_dt):
    y = utc_dt.year
    # Transitions both fall at 16:00 UTC on the Saturday before the first Sunday.
    end = datetime.combine(_nth_sunday(y, 4, 1), datetime.min.time(), timezone.utc) - timedelta(hours=8)
    start = datetime.combine(_nth_sunday(y, 10, 1), datetime.min.time(), timezone.utc) - timedelta(hours=8)
    return timedelta(hours=10 if end <= utc_dt < start else 11)


def _eastern_offset(local_naive):
    y = local_naive.year
    start = datetime.combine(_nth_sunday(y, 3, 2), datetime.min.time()) + timedelta(hours=2)
    end = datetime.combine(_nth_sunday(y, 11, 1), datetime.min.time()) + timedelta(hours=2)
    return timedelta(hours=-4 if start <= local_naive < end else -5)


def utc_to_sydney(utc_dt):
    """Aware UTC datetime -> naive Sydney local datetime."""
    if _SYD is not None:
        return utc_dt.astimezone(_SYD).replace(tzinfo=None)
    return (utc_dt + _sydney_offset(utc_dt)).replace(tzinfo=None)


def eastern_to_utc(local_naive):
    if _NY is not None:
        return local_naive.replace(tzinfo=_NY).astimezone(timezone.utc)
    return (local_naive - _eastern_offset(local_naive)).replace(tzinfo=timezone.utc)


def sydney_today():
    return utc_to_sydney(datetime.now(timezone.utc)).date()


def _text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


# ------------------------------------------------------------------------ ABS
# (pattern on the release name, short title, importance). Matched with re.fullmatch so
# "Labour Force, Australia, Detailed" and "National Accounts: Supply Use Tables" drop out.
ABS_KEEP = [
    (r"Consumer Price Index, Australia", "CPI", "high"),
    (r"Labour Force, Australia", "Labour Force", "high"),
    (r"Australian National Accounts: National Income, Expenditure and Product",
     "National Accounts (GDP)", "high"),
    (r"Building Approvals, Australia", "Building Approvals", "high"),
    (r"Building Activity, Australia", "Building Activity", "normal"),
    (r"Construction Work Done, Australia, Preliminary", "Construction Work Done", "normal"),
    (r"Engineering Construction Activity, Australia", "Engineering Construction", "normal"),
    (r"Wage Price Index, Australia", "Wage Price Index", "normal"),
    (r"Producer Price Indexes, Australia", "Producer Price Indexes", "normal"),
    (r"Lending Indicators", "Lending Indicators", "normal"),
    (r"Total Value of Dwellings", "Total Value of Dwellings", "normal"),
    (r"Monthly Household Spending Indicator", "Household Spending Indicator", "normal"),
    (r"National, state and territory population", "Population (national, state)", "normal"),
    (r"Job Vacancies, Australia", "Job Vacancies", "normal"),
]


def _abs_months(today, last):
    y, m = today.year, today.month
    out = []
    while (y, m) <= (last.year, last.month):
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch_abs(today, last):
    """ABS releases between today and last (Sydney dates), relevant series only.

    The calendar gives each release a UTC <time datetime> - 01:30Z in AEST months and
    00:30Z in AEDT months, i.e. 11:30am Canberra time all year (the page's own label says
    "11:30am AEST/AEDT"). Converting from UTC rather than trusting the label keeps it
    right across the daylight-saving change.
    """
    events, errors = [], {}
    for ym in _abs_months(today, last):
        try:
            page = get_text(ABS_URL.format(ym=ym))
        except Exception as e:  # noqa: BLE001
            errors[f"calendar/abs/{ym}"] = f"{type(e).__name__}: {e}"
            continue
        blocks = page.split('class="exportable-element"')[1:]
        if not blocks:
            errors[f"calendar/abs/{ym}"] = "no release blocks found - layout changed?"
            continue
        for b in blocks:
            # A second listing marked "Updated information" is a supplementary data cube
            # (e.g. small-area Building Approvals a week after the headline), not the release.
            if "Updated information" in b:
                continue
            t = re.search(r'<time datetime="([^"]+)"', b)
            n = re.search(r'event-name">(.*?)</h3>', b, re.S)
            if not t or not n:
                continue
            name = _text(n.group(1))
            match = next((k for k in ABS_KEEP if re.fullmatch(k[0], name)), None)
            if not match:
                continue
            try:
                utc = datetime.strptime(t.group(1), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            local = utc_to_sydney(utc)
            if not (today <= local.date() <= last):
                continue
            rp = re.search(r'reference-period-value">(.*?)<', b)
            period = _text(rp.group(1)) if rp else ""
            # "View current release" points at the latest edition (".../jul-2026"); the
            # parent path is the product's stable landing page.
            link = re.search(r'href="(/statistics/[^"]+)"', b)
            url = ("https://www.abs.gov.au" + link.group(1).rsplit("/", 1)[0]
                   if link else ABS_URL.format(ym=ym))
            events.append({
                "date": local.date().isoformat(), "time": local.strftime("%H:%M"),
                "title": match[1] + (f" ({period})" if period else ""),
                "category": "ABS", "importance": match[2], "url": url,
            })
    return events, errors


# ------------------------------------------------------------------------ RBA
# Decision day (second day of each two-day meeting). Fallback only, used if the scrape
# finds nothing. Verified against RBA_URL on 2026-09-29 - re-check each January.
RBA_FALLBACK = [
    "2026-02-03", "2026-03-17", "2026-05-05", "2026-06-16", "2026-08-11", "2026-09-29",
    "2026-11-03", "2026-12-08",
    "2027-02-09", "2027-03-23", "2027-05-04", "2027-06-22", "2027-08-10", "2027-09-28",
    "2027-11-02", "2027-12-14",
]
# "The outcome of the meeting is announced at 2.30 pm on the second day" - RBA Monetary
# Policy Board page, checked 2026-09-29. Sydney local time, so no conversion needed.
RBA_TIME = "14:30"


def rba_dates():
    """Decision dates scraped from the board schedule; raises if none parse."""
    page = get_text(RBA_URL)
    out = []
    for cap, body in re.findall(r"<caption[^>]*>(.*?)</caption>(.*?)</table>", page, re.S):
        ym = re.search(r"(\d{4})", _text(cap))
        if not ym or "Board meeting" not in _text(cap):
            continue
        year = int(ym.group(1))
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if not tds:
                continue
            cell = _text(tds[0])  # first column is the Monetary Policy Board
            # "28-29 September" or "31 March-1 April": the decision is the LAST date.
            m = re.search(r"(\d{1,2})\s+([A-Z][a-z]+)\s*$", cell)
            if m and m.group(2) in MONTHS:
                out.append(date(year, MONTHS[m.group(2)], int(m.group(1))).isoformat())
    if not out:
        raise ValueError("no Monetary Policy Board dates parsed")
    return sorted(set(out))


# ----------------------------------------------------------------------- FOMC
# Decision day = last day of the meeting. Fallback verified against FOMC_URL 2026-09-29.
FOMC_FALLBACK = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16",
    "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15",
    "2027-10-27", "2027-12-08",
]
# Statements are "For release at 2:00 p.m." Eastern (checked on the 16 Sep 2026 release).
# In Sydney that is the next morning - 04:00-07:00 depending on both DST regimes - so the
# Sydney DATE is one day after the US decision date.
FOMC_ET = (14, 0)


def fomc_dates():
    page = get_text(FOMC_URL)
    heads = [(m.start(), int(m.group(1))) for m in re.finditer(r"(\d{4}) FOMC Meetings", page)]
    if not heads:
        raise ValueError("no year headings found")
    out = []
    pat = re.compile(r'fomc-meeting__month[^>]*><strong>([^<]+)</strong></div>\s*'
                     r'<div class="fomc-meeting__date[^>]*>([^<]+)</div>')
    for m in pat.finditer(page):
        # Headings are not in year order on the page (2027 comes last), so take the
        # nearest heading ABOVE this row rather than the largest year.
        year = next(y for pos, y in sorted(heads, reverse=True) if pos < m.start())
        month_s, days_s = m.group(1).strip(), m.group(2).strip()
        # Skip unscheduled/notation votes and cancellations - no scheduled statement.
        if re.search(r"notation|unscheduled|cancel", days_s, re.I):
            continue
        days_s = days_s.replace("*", "").strip()
        last_day = int(re.findall(r"\d+", days_s)[-1])
        # "Apr/May 30-1" - the meeting ends in the second month.
        month = MON3.get(month_s.split("/")[-1].strip()[:3])
        if month is None:
            continue
        # "Dec/Jan" has not happened, but guard the year roll anyway.
        y = year + 1 if month_s.startswith("Dec/") else year
        out.append(date(y, month, last_day).isoformat())
    if not out:
        raise ValueError("no FOMC meeting rows parsed")
    return sorted(set(out))


def _fomc_event(iso):
    d = date.fromisoformat(iso)
    utc = eastern_to_utc(datetime(d.year, d.month, d.day, *FOMC_ET))
    local = utc_to_sydney(utc)
    return {
        "date": local.date().isoformat(), "time": local.strftime("%H:%M"),
        "title": f"FOMC rate decision (US {d.strftime('%d %b')}, 2:00pm ET)",
        "category": "Fed", "importance": "high", "url": FOMC_URL,
    }


def fetch_calendar(days_ahead=75):
    """Returns (events, errors). Events sorted by Sydney date/time."""
    today = sydney_today()
    last = today + timedelta(days=days_ahead)
    events, errors = [], {}

    abs_ev, abs_err = fetch_abs(today, last)
    events += abs_ev
    errors.update(abs_err)

    try:
        rdates = rba_dates()
    except Exception as e:  # noqa: BLE001
        errors["calendar/rba"] = f"{type(e).__name__}: {e} - using fallback list"
        rdates = RBA_FALLBACK
    for iso in rdates:
        if today.isoformat() <= iso <= last.isoformat():
            events.append({"date": iso, "time": RBA_TIME, "title": "RBA cash rate decision",
                           "category": "RBA", "importance": "high", "url": RBA_URL})

    try:
        fdates = fomc_dates()
    except Exception as e:  # noqa: BLE001
        errors["calendar/fomc"] = f"{type(e).__name__}: {e} - using fallback list"
        fdates = FOMC_FALLBACK
    for iso in fdates:
        ev = _fomc_event(iso)
        if today.isoformat() <= ev["date"] <= last.isoformat():
            events.append(ev)

    # If either hard-coded list is the one in use and has run out, say so rather than
    # quietly showing a calendar with no rate decisions on it.
    for key, used, fb in (("rba", rdates, RBA_FALLBACK), ("fomc", fdates, FOMC_FALLBACK)):
        if used is fb and max(fb) < last.isoformat():
            errors[f"calendar/{key}/fallback"] = f"fallback list ends {max(fb)} - update it"

    events.sort(key=lambda e: (e["date"], e["time"] or "99:99", e["category"]))
    return events, errors


if __name__ == "__main__":
    print(f"  zoneinfo available: {_SYD is not None}")
    evs, errs = fetch_calendar()
    for e in evs:
        star = "*" if e["importance"] == "high" else " "
        print(f"  {e['date']} {e['time'] or '--:--'} {star} {e['category']:<4} {e['title']}")
    print(f"  {len(evs)} events")
    for k, v in errs.items():
        print(f"  FAIL {k}: {v[:100]}")
