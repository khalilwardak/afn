"""Offline tests: python tests.py  (no network, no API key needed)."""
import json, tempfile
from datetime import datetime, timezone
from pathlib import Path

from collector import run, sarai_ocr, sarai_vision, telegram
from collector.telegram import parse_page

def board(s):
    return {"is_rate_board": True, "rows": [{"code": c, "buy": float(b), "sell": float(x)}
            for c, b, x in (p.split() for p in s.split(","))]}

MORNING = board("USD 64.85 64.90,EUR 73.00 73.20,GBP 85.20 85.50,IRR 0.24 0.25,PKR 228 229,SAR 17.28 17.30,AED 17.66 17.67,CHF 78.16 78.22,AUD 45.17 45.21,CAD 45.47 45.51,RUB 0.76 0.76,DKK 9.72 9.73,SEK 6.49 6.49,NOK 6.78 6.79,TRY 1.32 1.32,CNY 9.69 9.70,KWD 209 209,QAR 17.81 17.83,BHD 172 172,JPY 410 410")
AFTERNOON = board("USD 64.90 64.95,EUR 73.00 73.20,GBP 85.20 85.50,IRR 0.24 0.25,PKR 228 229,SAR 17.30 17.31,AED 17.67 17.69,CHF 78.22 78.28,AUD 45.21 45.24,CAD 45.51 45.54,RUB 0.76 0.76,DKK 9.73 9.73,SEK 6.49 6.50,NOK 6.79 6.79,TRY 1.32 1.32,CNY 9.70 9.71,KWD 209 209,QAR 17.83 17.84,BHD 172 172")
BAD = board("USD 70.00 70.05,AED 17.67 17.69,SAR 17.30 17.31,QAR 17.83 17.84")

HTML = '''<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="Sarai_Shahzada1/541">
<a class="tgme_widget_message_photo_wrap" href="x" style="width:800px;background-image:url('https://cdn5.telesco.pe/file/abc.jpg')"></a>
<div class="tgme_widget_message_text">hello<br/>world</div>
<a class="tgme_widget_message_date" href="x"><time datetime="2026-10-11T05:02:11+00:00" class="time">10:32</time></a></div></div>'''

def _rows(spec):
    return "".join("<tr><td>%s</td>%s</tr>" % (n, "".join("<td>%s</td>" % v for v in vals.split())) for n, vals in spec)

DAB_HTML = ("<h2>Exchange Rates</h2><p>Last updated: 11 October 2026</p><table><thead><tr><th>Currency</th><th>Cash (Sell)</th><th>Cash (Buy)</th><th>Transfer (Sell)</th><th>Transfer (Buy)</th></tr></thead><tbody>"
  + _rows([("USD$", "65.0650 64.8650 65.0150 64.9150"), ("EURO€", "73.1800 72.5800 73.0100 72.7500"), ("POUND£", "85.6300 84.8300 85.3800 85.0800"),
           ("SWISS₣", "78.5167 78.0167 78.3667 78.1667"), ("INDIAN Rs.", "0.7430 0.7330 0.7400 0.7360"), ("PAKISTAN Rs.", "0.2323 0.2243 0.2293 0.2273"),
           ("IRAN Toman", "0.0007 0.0001 0.0006 0.0002"), ("CNY¥", "10.1125 9.7125 10.0125 9.8125"), ("UAE DIRHAM", "17.7150 17.6150 17.6950 17.6350"),
           ("SAUDI RIYAL", "17.2188 17.1188 17.1988 17.1388")])
  + "</tbody></table><h2>Average Rates</h2><p>Last updated:11 October 2026</p><p>30 September 2026</p><table><thead><tr><th>Currency</th><th>Cash (Sell)</th><th>Cash (Buy)</th><th>Transfer (Sell)</th><th>Transfer (Buy)</th></tr></thead><tbody>"
  + _rows([("USD$", "64.7198 64.5198 64.6698 64.5698")]) + "</tbody></table>")

def post(i, t, photo=None, text=""):
    return {"id": i, "time": t, "photo": photo, "text": text}

SARAI = [post(1, "2026-10-11T05:02:11+00:00", "u1"), post(2, "2026-10-11T10:28:00+00:00", "u2")]
KHO = [post(1, "2026-10-11T05:30:00+00:00", text="هرات دالر به افغانی💵 64.95 خـرید 65.05 فـروش\n\nهرات یورو به افغانی 💶 73.00خرید 73.20 فروش\n\nهرات کلدار افغانی 🇵🇰 228,50 خرید 229,00 فروش\n\nهرات تومان چک 💎 0.27 خرید  0.28 فروش\n\nهرات تومان بانکی 💳 0.24 خرید  0.25 فروش"),
       post(2, "2026-10-11T09:30:00+00:00", text="هرات دالر به افغانی💵 65.00 خـرید 65.05 فـروش")]
NOW = datetime(2026, 10, 11, 10, 30, tzinfo=timezone.utc)  # 15:00 in Kabul

def run_once(sarai, boards):
    telegram.collect = lambda handle, after, pages: [p for p in (sarai if handle == "sarai_Shahzada1" else KHO) if p["id"] > after]
    run.get_image = lambda url: (b"x", "image/jpeg")
    run.sarai_readers = lambda: [sarai_vision.read_board]
    run.dab.fetch = lambda: run.dab.parse(DAB_HTML)
    it = iter(boards)
    sarai_vision.read_board = lambda img, mt: next(it)
    d = tempfile.mkdtemp()
    run.main(["--data-dir", d], now=NOW)
    return Path(d)

def test_readers():
    # OCR reads a board that fails the checks -> the backup reader is used; with no backup it goes to review
    bad = lambda img, mt: dict(BAD, rows_found=4)
    good = lambda img, mt: MORNING
    state = {"last": {}}; ev, rv = [], []
    run.sarai_readers = lambda: [bad, good]
    run.get_image = lambda url: (b"x", "image/jpeg")
    run.handle_sarai(post(1, "2026-10-11T05:02:11+00:00", "u"), state, ev, rv)
    assert len(ev) == 20 and not rv, (len(ev), rv)
    state, ev, rv = {"last": {}}, [], []
    run.sarai_readers = lambda: [bad]
    run.handle_sarai(post(1, "2026-10-11T05:02:11+00:00", "u"), state, ev, rv)
    assert not ev and rv
    notboard = lambda img, mt: {"is_rate_board": False, "rows": [], "rows_found": 0}
    called = []
    run.sarai_readers = lambda: [notboard, lambda i, m: called.append(1)]
    run.handle_sarai(post(1, "2026-10-11T05:02:11+00:00", "u"), {"last": {}}, [], [])
    assert not called, "a post that is not a board must not reach the paid backup"
    toks = [("64.95", 190, 190), ("64.90", 258, 190), ("USD", 342, 190), ("02:58", 109, 192), ("0.25", 196, 232), ("0.24", 262, 232), ("lJPY", 325, 232)]
    assert sarai_ocr.rows_from_tokens(toks) == [{"code": "USD", "buy": 64.9, "sell": 64.95}, {"code": "JPY", "buy": 0.24, "sell": 0.25}]


def test_ocr_on_real_board():
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        print("OCR test skipped (rapidocr not installed)")
        return
    got = run.clean_rows(sarai_ocr.read_board(open(Path(__file__).parent / "tests_data" / "sarai_board_2026-10-11.jpeg", "rb").read())["rows"])
    assert got == run.clean_rows(AFTERNOON["rows"]), got


def test_dab_history():
    import requests
    from datetime import date
    assert requests.Request("GET", run.dab.URL, params={"field_date_value": date(2026, 10, 5).strftime("%m/%d/%Y")}).prepare().url == "https://www.dab.gov.af/exchange-rates?field_date_value=10%2F05%2F2026"
    oct5 = DAB_HTML.replace("11 October 2026", "05 October 2026").replace("<td>65.0650</td><td>64.8650</td><td>65.0150</td><td>64.9150</td>", "<td>64.9750</td><td>64.7750</td><td>64.9250</td><td>64.8250</td>")
    p = run.dab.parse(oct5)
    assert p["date"] == "2026-10-05" and p["rates"]["USD"]["cash"] == [64.775, 64.975] and p["rates"]["USD"]["transfer"] == [64.825, 64.925], p["rates"]["USD"]
    run.dab.fetch = lambda day=None: run.dab.parse(DAB_HTML.replace("11 October 2026", day.strftime("%d %B %Y")))
    d = tempfile.mkdtemp()
    run.backfill_dab(Path(d), 3)
    assert len(json.loads((Path(d) / "dab_history.json").read_text())) == 3
    run.backfill_dab(Path(d), 3)  # nothing new on a second run
    assert len(json.loads((Path(d) / "dab_history.json").read_text())) == 3


def test_all():
    p = parse_page(HTML)[0]
    assert p["id"] == 541 and p["photo"].endswith("abc.jpg") and p["time"].startswith("2026-10-11T05:02") and p["text"] == "hello\nworld", p

    d = run_once(SARAI, [MORNING, AFTERNOON])
    r = json.loads((d / "rates.json").read_text())
    names = [m["id"] for m in r["markets"]]
    assert names == ["sarai", "khorasan", "dab", "dabt"], names
    assert (r["reference"]["buy"], r["reference"]["sell"]) == (64.85, 64.90), r["reference"]   # held ~5h25m vs 2m
    assert r["solar"] == "19 Mizan 1405", r["solar"]
    sar = {x[0]: x for x in r["markets"][0]["rows"]}
    assert sar["USD"][2:5] == [64.90, 64.95, "2:58 PM"] and len(sar) == 20, sar["USD"]
    kho = {x[0]: x for x in r["markets"][1]["rows"]}
    assert kho["USD"][2:4] == [65.0, 65.05] and kho["PKR"][2:4] == [228.5, 229.0] and "IRRC" in kho and "IRRB" in kho

    dab = {x[0]: x for x in r["markets"][2]["rows"]}
    assert dab["USD"][2:4] == [64.865, 65.065] and dab["PKR"][2:4] == [224.3, 232.3] and dab["IRT"][2:4] == [0.1, 0.7] and len(dab) == 10, dab
    dabt = {x[0]: x for x in r["markets"][3]["rows"]}
    assert dabt["USD"][2:4] == [64.915, 65.015], dabt["USD"]
    parsed = run.dab.parse(DAB_HTML)
    assert parsed["date"] == "2026-10-11" and parsed["average"]["label"] == "30 September 2026" and parsed["average"]["rates"]["USD"]["cash"] == [64.5198, 64.7198]
    d2 = run_once(SARAI, [])          # nothing new: state remembers the last post
    n1 = len((d / "events.jsonl").read_text().splitlines())
    run.main(["--data-dir", str(d)], now=NOW)
    assert len((d / "events.jsonl").read_text().splitlines()) == n1, "rerun must add nothing"

    d3 = run_once(SARAI[:1], [BAD])   # USD 70 disagrees with the pegged currencies
    rev = (d3 / "review.jsonl").read_text()
    assert "disagrees" in rev and not any(e["market"] == "sarai" for e in map(json.loads, (d3 / "events.jsonl").read_text().splitlines()))
    print("all tests passed")
    return r

if __name__ == "__main__":
    test_all()
    test_dab_history()
    test_readers()
    test_ocr_on_real_board()
    print("dab, reader and OCR tests passed")
