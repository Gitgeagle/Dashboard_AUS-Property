"""US Treasury daily par yield curve.

Note: the Treasury *FiscalData* API (api.fiscaldata.treasury.gov) does NOT carry the par
yield curve - it serves average interest rates on outstanding debt. The correct source is
this XML feed, which needs no key.
"""
import re
import xml.etree.ElementTree as ET
from datetime import date

from httpget import get_text

URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
       "pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={year}")

NS = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}

# Field name -> years to maturity. Drives the curve x-axis.
TENORS = [
    ("BC_1MONTH", 1 / 12, "1M"), ("BC_2MONTH", 2 / 12, "2M"),
    ("BC_3MONTH", 3 / 12, "3M"), ("BC_4MONTH", 4 / 12, "4M"),
    ("BC_6MONTH", 0.5, "6M"), ("BC_1YEAR", 1, "1Y"),
    ("BC_2YEAR", 2, "2Y"), ("BC_3YEAR", 3, "3Y"),
    ("BC_5YEAR", 5, "5Y"), ("BC_7YEAR", 7, "7Y"),
    ("BC_10YEAR", 10, "10Y"), ("BC_20YEAR", 20, "20Y"),
    ("BC_30YEAR", 30, "30Y"),
]


def fetch_curve(year=None):
    """Return [{date, points:[{tenor,years,yield}]}] ascending by date for a year."""
    year = year or date.today().year
    xml = get_text(URL.format(year=year))
    root = ET.fromstring(xml)
    days = []
    for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
        props = entry.find(".//{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}properties")
        if props is None:
            continue
        dt_el = props.find("d:NEW_DATE", NS)
        if dt_el is None or not dt_el.text:
            continue
        day = dt_el.text[:10]
        pts = []
        for field, yrs, label in TENORS:
            el = props.find(f"d:{field}", NS)
            if el is None or not el.text:
                continue
            try:
                pts.append({"tenor": label, "years": yrs, "yield": float(el.text)})
            except ValueError:
                continue
        if pts:
            days.append({"date": day, "points": pts})
    days.sort(key=lambda d: d["date"])
    return days


def fetch(years_back=1):
    """Current year plus the prior one, so we can show a 1-year-ago overlay."""
    this_year = date.today().year
    out = []
    for y in range(this_year - years_back, this_year + 1):
        try:
            out.extend(fetch_curve(y))
        except Exception:  # noqa: BLE001 - a missing prior year is not fatal
            continue
    out.sort(key=lambda d: d["date"])
    return out


if __name__ == "__main__":
    days = fetch()
    print(f"{len(days)} trading days fetched; latest:")
    latest = days[-1]
    print(" ", latest["date"])
    for p in latest["points"]:
        print(f"    {p['tenor']:<4} {p['yield']:>7.2f}%")
