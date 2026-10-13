"""Parser for the Khorasan Market (Herat) Telegram channel, @nerkhyabkorasan.

Posts are plain text in Dari, so no AI is needed: text in, list of quotes out.
The parser reports raw numbers only. Unit conversion (per 1 or per 1,000) happens later,
after the market confirms its units.
"""
import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# Arabic ye/kaf variants to Persian forms; drop the tatweel (ـ) used to stretch words.
_CHARS = str.maketrans({"ي": "ی", "ك": "ک", "ڪ": "ک", "ـ": None})

# "<buy> خرید <sell> فروش": the number comes BEFORE its label. Emoji or "|" may sit between.
QUOTE = re.compile(r"(?P<buy>\d+(?:\.\d+)?)\s*خرید[^\d\n]{0,6}(?P<sell>\d+(?:\.\d+)?)\s*فروش")
SOLAR_DATE = re.compile(r"(1[34]\d\d)[./](\d\d)[./](\d\d)")

INSTRUMENTS = [  # checked in order
    (("چک",), "IRR_CHEQUE", "تومان"),   # Iranian toman, cheque
    (("بانکی",), "IRR_BANK", "تومان"),  # Iranian toman, bank transfer
    (("دالر", "دلار"), "USD", None),
    (("یورو",), "EUR", None),
    (("کلدار",), "PKR", None),
]


def normalize(text: str) -> str:
    text = text.translate(_DIGITS).translate(_CHARS).replace("٫", ".")
    text = re.sub(r"(?<=\d),(?=\d{1,2}(?!\d))", ".", text)  # "228,50" -> 228.50
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)            # "1,250" -> 1250
    return text


def instrument_of(label: str):
    if "تومان" in label:
        return "IRR_CHEQUE" if "چک" in label else "IRR_BANK" if "بانکی" in label else "IRR"
    for words, code, _ in INSTRUMENTS:
        if code in ("IRR_CHEQUE", "IRR_BANK"):
            continue
        if any(w in label for w in words):
            return code
    return None


def parse_day(text: str) -> dict:
    """Parse a day of posts (blank-line separated). Returns solar_date and a list of quotes."""
    text = normalize(text)
    quotes, closed, solar_date, prev = [], False, None, ""
    for block_no, block in enumerate(re.split(r"\n\s*\n", text)):
        if "پایان معاملات" in block:   # "end of trading": what follows is the official close
            closed = True
        d = SOLAR_DATE.search(block)
        if d and not solar_date:
            solar_date = "-".join(d.groups())
        for line in (l.strip() for l in block.splitlines() if l.strip()):
            q = QUOTE.search(line)
            if not q:                  # greetings, gold, bitcoin, oil... are ignored
                prev = line
                continue
            label = line[:q.start()]
            inst = instrument_of(label)
            if inst is None:           # label is on the previous line, even across a blank line
                label = prev
                inst = instrument_of(label)
            if inst is None:
                continue
            buy, sell = float(q["buy"]), float(q["sell"])
            quotes.append({
                "block": block_no,
                "city": "KABUL" if "کابل" in label else "HERAT" if "هرات" in label else None,
                "instrument": inst,
                "buy": buy,
                "sell": sell,
                "is_close": closed or not ("کابل" in label or "هرات" in label),  # summary lines name no city
                "valid": buy <= sell,
            })
            prev = line
    return {"solar_date": solar_date, "quotes": quotes}


if __name__ == "__main__":
    sample = "هرات دالر به افغانی💵 64.95 خـرید 65.05 فـروش\n\nهرات کلدار افغانی 🇵🇰 228,50 خرید 229,00 فروش"
    for q in parse_day(sample)["quotes"]:
        print(q)
