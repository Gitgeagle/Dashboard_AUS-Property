"""Official headlines: RBA, APRA and Federal Reserve releases.

Headline, link and date only - never article bodies or descriptions. The site is public,
and a headline plus a link back is attribution, not republication. Licensing, checked
2026-09-29: RBA website material is CC BY 4.0 apart from listed exclusions (rba.gov.au/
copyright); Federal Reserve Board web content is public domain, cite the Board
(federalreserve.gov/disclaimer.htm); APRA material is used here only as titles and links.

Gotchas found while building this:
  * The RBA RSS-CB feeds carry only the single most recent item, so over a three-week
    window they show one media release and one speech at most. The listing pages at
    /media-releases/ and /speeches/ hold the rest in clean <article> markup with a
    machine-readable <time datetime>, so they are read as well and merged by URL.
  * APRA has no news feed. apra.gov.au/rss.xml is live but lists statistical
    publications only (ADI, super and insurance statistics) - no media releases - so it
    is filtered to the banking and property items a developer cares about.
  * The Fed feeds start with a UTF-8 byte-order mark. press_monetary.xml is the
    monetary-policy subset of press_all.xml; using it directly keeps FOMC items that the
    20-item press_all window would push out behind bank merger orders.
"""
import email.utils
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from httpget import get
from sources.releases import utc_to_sydney

FEEDS = [
    ("RBA", "https://www.rba.gov.au/rss/rss-cb-media-releases.xml"),
    ("RBA", "https://www.rba.gov.au/rss/rss-cb-speeches.xml"),
    ("APRA", "https://www.apra.gov.au/rss.xml"),
    ("Fed", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
]
RBA_LISTINGS = [
    ("https://www.rba.gov.au/media-releases/", ""),
    ("https://www.rba.gov.au/speeches/", "Speech: "),  # matches the RSS title style
]
# APRA's feed is statistics only. Keep the series relevant to credit conditions.
APRA_KEEP = re.compile(r"deposit-taking|\bADI\b|property exposure|residential mortgage|"
                       r"housing|lending|bank", re.I)
TITLE_MAX = 160


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def clean_title(s):
    s = re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(s or "")))
    # Tag stripping leaves "Jeffreys , 9Now" - pull punctuation back onto its word.
    s = re.sub(r"\s+([,.;:])", r"\1", re.sub(r"\s+", " ", s)).strip()
    return s if len(s) <= TITLE_MAX else s[:TITLE_MAX - 1].rstrip() + "…"


def parse_date(s):
    """RFC 822 (RSS 2.0 pubDate) or ISO 8601 (dc:date) -> aware UTC datetime, or None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_feed(raw):
    """[(title, url, utc_datetime)] from RSS 2.0 or RSS 1.0/RDF, namespace-agnostic."""
    root = ET.fromstring(raw)  # bytes in, so a leading BOM is handled by the parser
    out = []
    for el in root.iter():
        if _local(el.tag) != "item":
            continue
        f = {}
        for ch in el:
            name = _local(ch.tag)
            if name in ("title", "link", "pubDate", "date") and name not in f:
                f[name] = (ch.text or "").strip()
        url = f.get("link") or el.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about")
        dt = parse_date(f.get("pubDate") or f.get("date"))
        if f.get("title") and url and dt:
            out.append((clean_title(f["title"]), url.strip(), dt))
    return out


def parse_rba_listing(page, prefix=""):
    """[(title, url, utc_datetime)] from an RBA /media-releases/ or /speeches/ page."""
    out = []
    for art in re.findall(r"<article\b(.*?)</article>", page, re.S):
        a = re.search(r'<a href="(/[^"]+\.html)"', art)
        h = re.search(r'itemprop="headline">(.*?)</span>', art, re.S)
        t = re.search(r'<time[^>]*datetime="([^"]+)"', art)
        if not (a and h and t):
            continue
        dt = parse_date(t.group(1))
        # Speeches page mixes speeches, interviews and fireside chats; label by type.
        et = re.search(r'class="event-type">(.*?)</span>', art, re.S)
        head = clean_title(h.group(1))
        pre = f"{clean_title(et.group(1))}: " if (prefix and et) else prefix
        if pre and head.lower().startswith(pre[:-2].lower()):
            pre = ""  # "Fireside Chat at ..." needs no "Fireside Chat:" in front
        if dt:
            out.append((clean_title(pre + head), "https://www.rba.gov.au" + a.group(1), dt))
    return out


def fetch_news(max_items=24, days=21):
    """Returns (items, errors). Items newest first, deduplicated by URL."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found, errors = {}, {}

    def add(source, rows):
        for title, url, dt in rows:
            if dt >= cutoff and url not in found:
                found[url] = {"title": title, "url": url, "dt": dt, "source": source}

    for source, url in FEEDS:
        try:
            rows = parse_feed(get(url))
            if source == "APRA":
                rows = [r for r in rows if APRA_KEEP.search(r[0])]
            add(source, rows)
        except Exception as e:  # noqa: BLE001
            errors[f"news/{source}/{url.rsplit('/', 1)[-1]}"] = f"{type(e).__name__}: {e}"

    for url, prefix in RBA_LISTINGS:
        try:
            add("RBA", parse_rba_listing(get(url).decode("utf-8", "replace"), prefix))
        except Exception as e:  # noqa: BLE001
            errors[f"news/RBA/{url.rstrip('/').rsplit('/', 1)[-1]}"] = f"{type(e).__name__}: {e}"

    # Sydney-local calendar date, so a Fed release at 2pm ET lands on the day Australians
    # read it (the next morning), not the US date.
    items = sorted(found.values(), key=lambda x: x["dt"], reverse=True)[:max_items]
    return [{"title": i["title"], "url": i["url"],
             "date": utc_to_sydney(i["dt"]).date().isoformat(),
             "source": i["source"]} for i in items], errors


if __name__ == "__main__":
    its, errs = fetch_news()
    for i in its:
        print(f"  {i['date']} {i['source']:<4} {i['title'][:100]}")
    print(f"  {len(its)} items")
    for k, v in errs.items():
        print(f"  FAIL {k}: {v[:100]}")
