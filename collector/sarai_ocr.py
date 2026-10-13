"""Free reader for Sarai Shahzada boards: OCR on the image, no API key and no cost.

Returns the same structure as sarai_vision.read_board. Each row on the board reads, left to right:
time, sell, buy, code. So the number just left of the code is BUY and the next one is SELL.
The printed time is ignored (the Telegram post time is used instead).
"""
import re
import statistics

from . import config

_engine = None
_NUM = re.compile(r"^\d+(?:\.\d+)?$")


def _ocr(image_bytes):
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # imported here so tests and probes do not need it
        _engine = RapidOCR()
    result, _ = _engine(image_bytes)
    return result or []


def _code(text):
    """A currency code, even with a stray glyph stuck to it (the Dari word for 'thousand' is read as 'J' or 'l')."""
    t = text.upper().strip()
    if t in config.NAMES:
        return t
    if len(t) <= 6:
        hits = [c for c in config.NAMES if len(c) == 3 and c in t]
        if len(hits) == 1:
            return hits[0]
    return None


def rows_from_tokens(tokens):
    """tokens: (text, x, y) triples. Returns [{'code','buy','sell'}] for each row with a known code."""
    codes = sorted(((x, y, _code(t)) for t, x, y in tokens if _code(t)), key=lambda c: c[1])
    if not codes:
        return []
    gaps = [b[1] - a[1] for a, b in zip(codes, codes[1:])]
    tol = 0.4 * (statistics.median(gaps) if gaps else 40)
    seen, rows = set(), []
    for cx, cy, code in codes:
        if code in seen:
            continue
        nums = sorted(((x, t) for t, x, y in tokens
                       if abs(y - cy) <= tol and x < cx and _NUM.match(t)), reverse=True)  # nearest the code first
        if len(nums) >= 2:
            seen.add(code)
            rows.append({"code": code, "buy": float(nums[0][1]), "sell": float(nums[1][1])})
    return rows


def read_board(image_bytes, media_type=None):
    tokens = []
    for box, text, _score in _ocr(image_bytes):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        pieces = text.replace(",", ".").split()
        left, width = min(xs), max(xs) - min(xs)
        for i, piece in enumerate(pieces):
            tokens.append((piece, left + width * (i + 0.5) / len(pieces), sum(ys) / 4))
    rows = rows_from_tokens(tokens)
    ok = len(rows) >= 5 and any(r["code"] == "USD" for r in rows)
    return {"is_rate_board": ok, "rows": rows if ok else [], "rows_found": len(rows)}
