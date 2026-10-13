"""Da Afghanistan Bank's daily exchange rates, read from https://www.dab.gov.af/exchange-rates

The page lists, per currency: Cash (Sell), Cash (Buy), Transfer (Sell), Transfer (Buy), plus a short
"Average Rates" table. Columns are found by their header text, so a changed column order is fine.
"""
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

URL = "https://www.dab.gov.af/exchange-rates"
UA = {"User-Agent": "Mozilla/5.0 (compatible; AFN-rates-bot/1.0)"}

# (text found in the table's first column, code, English name, units the bank's price is quoted for -> shown per N)
CURRENCIES = [
    ("USD", "USD", "US dollar", 1), ("EURO", "EUR", "Euro", 1), ("POUND", "GBP", "British pound", 1),
    ("SWISS", "CHF", "Swiss franc", 1), ("INDIAN", "INR", "Indian rupee", 1000),
    ("PAKISTAN", "PKR", "Pakistani rupee", 1000), ("IRAN", "IRT", "Iranian toman", 1000),
    ("CNY", "CNY", "Chinese yuan", 1), ("DIRHAM", "AED", "UAE dirham", 1), ("SAUDI", "SAR", "Saudi riyal", 1),
]
DATE = r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"


def parse_table(table):
    rows = table.find_all("tr")
    head = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
    cols = {}
    for i, h in enumerate(head):
        m = re.search(r"(cash|transfer)\s*\(\s*(buy|sell)\s*\)", h)
        if m:
            cols[i] = (m.group(1), m.group(2))
    out = {}
    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        label = cells[0].upper() if cells else ""
        code = next((c for key, c, _, _ in CURRENCIES if key in label), None)
        if not code:
            continue
        vals = {}
        for i, (kind, side) in cols.items():
            try:
                vals.setdefault(kind, {})[side] = float(cells[i].replace(",", ""))
            except (IndexError, ValueError):
                pass
        out[code] = {k: [v["buy"], v["sell"]] for k, v in vals.items() if "buy" in v and "sell" in v}
    return out


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = re.search(rf"Last updated:\s*({DATE})", text)
    if not m:
        raise ValueError("no 'Last updated' date on the page")
    tables = [t for t in soup.find_all("table") if "currency" in t.get_text().lower()]
    if not tables:
        raise ValueError("no rates table on the page")
    rates = parse_table(tables[0])
    if "USD" not in rates:
        raise ValueError("no USD row in the rates table")
    label = re.search(rf"Average Rates\s*Last updated:\s*{DATE}\s+({DATE})", text)
    return {"date": datetime.strptime(" ".join(m.group(1).split()), "%d %B %Y").date().isoformat(),
            "rates": rates,
            "average": {"label": label.group(1) if label else None,
                        "rates": parse_table(tables[1]) if len(tables) > 1 else {}}}


def fetch(day=None):
    """Today's page, or the rates for `day` (the page takes ?field_date_value=MM/DD/YYYY)."""
    params = {"field_date_value": day.strftime("%m/%d/%Y")} if day else None
    r = requests.get(URL, params=params, headers=UA, timeout=30)
    r.raise_for_status()
    return parse(r.text)


def to_markets(parsed, previous=None):
    """Two markets for the site: cash and transfer. `previous` is an earlier day's parsed record."""
    day = datetime.fromisoformat(parsed["date"])
    shown = f"{day.day} {day.strftime('%b')}"
    out = []
    for kind, mid_id, label in (("cash", "dab", "Da Afghanistan Bank (cash)"),
                                ("transfer", "dabt", "Da Afghanistan Bank (transfer)")):
        rows = []
        for _, code, name, unit in CURRENCIES:
            r = parsed["rates"].get(code)
            if not r or kind not in r:
                continue
            buy, sell = round(r[kind][0] * unit, 4), round(r[kind][1] * unit, 4)
            chg = None
            if previous and code in previous["rates"] and kind in previous["rates"][code]:
                pm = sum(previous["rates"][code][kind]) / 2 * unit
                chg = round(((buy + sell) / 2 - pm) / pm * 100, 2) if pm else None
            rows.append([code, name, buy, sell, shown, chg, unit])
        out.append({"id": mid_id, "name": label, "rows": rows})
    return out
