"""Collect rates from the Telegram channels and write rates.json.

    python -m collector.run --data-dir data_branch [--mode normal|probe|backfill] [--pages 10]
"""
import argparse
import json
import os
import statistics
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path

import jdatetime
import requests

from . import config, dab, khorasan_parser, sarai_ocr, sarai_vision, telegram

ROOT = Path(__file__).resolve().parent.parent


def log(*a):
    print(*a, flush=True)


def load_json(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_jsonl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def append_jsonl(p, rows):
    if rows:
        with p.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def when(iso):
    return datetime.fromisoformat(iso).astimezone(config.TZ)


# ---------- events: one record each time a price changes ----------

def add_event(state, events, market, code, buy, sell, t, post):
    last = state["last"].setdefault(market, {})
    cur = last.get(code)
    if cur and cur["buy"] == buy and cur["sell"] == sell:
        return  # same price reposted: not a new quote
    last[code] = {"buy": buy, "sell": sell, "t": t}
    events.append({"t": t, "market": market, "code": code, "buy": buy, "sell": sell, "post": post})


def add_close(state, events, market, code, buy, sell, t, post):
    day, key = when(t).date().isoformat(), f"{market}|{code}"
    if state["closed"].get(key) == [day, buy, sell]:
        return
    state["closed"][key] = [day, buy, sell]
    events.append({"t": t, "market": market, "code": code, "buy": buy, "sell": sell, "post": post, "close": True})


# ---------- Sarai Shahzada: image boards ----------

def get_image(url):
    r = requests.get(url, headers=telegram.UA, timeout=30)
    r.raise_for_status()
    return r.content, r.headers.get("content-type", "image/jpeg").split(";")[0]


def clean_rows(rows):
    out = {}
    for r in rows or []:
        try:
            code, buy, sell = str(r["code"]).strip().upper(), float(r["buy"]), float(r["sell"])
        except (KeyError, TypeError, ValueError):
            continue
        if code in config.NAMES and buy > 0 and sell > 0:
            out[code] = (buy, sell)
    return out


def check_board(rows, last):
    """Return (accepted rows, problems). A USD price that disagrees with the pegged currencies rejects the board."""
    if "USD" not in rows:
        return {}, ["no USD row"]
    mid = lambda v: (v[0] + v[1]) / 2
    implied = [mid(rows[c]) * p for c, p in config.PEGS.items() if c in rows]
    if implied:
        ref = statistics.median(implied)
        if abs(mid(rows["USD"]) - ref) / ref > config.PEG_TOLERANCE:
            return {}, [f"USD {mid(rows['USD']):.2f} disagrees with pegged currencies ({ref:.2f})"]
    ok, problems = {}, []
    for code, (buy, sell) in rows.items():
        if buy > sell:
            problems.append(f"{code}: buy above sell")
            continue
        prev = last.get(code)
        if prev and code != "USD" and code not in config.PEGS:
            pm = (prev["buy"] + prev["sell"]) / 2
            if pm and abs(mid((buy, sell)) - pm) / pm > config.JUMP_LIMIT:
                problems.append(f"{code}: jumped from {pm:.2f}")
                continue
        ok[code] = (buy, sell)
    return ok, problems


def sarai_readers():
    """Free OCR first. Claude is only a backup, and only when an API key has been set."""
    paid = [sarai_vision.read_board] if os.environ.get("ANTHROPIC_API_KEY") else []
    return {"ocr": [sarai_ocr.read_board], "claude": [sarai_vision.read_board]}.get(config.READER, [sarai_ocr.read_board] + paid)


def handle_sarai(post, state, events, review):
    if not post["photo"]:
        return
    img, mtype = get_image(post["photo"])
    readers = sarai_readers()
    for i, read in enumerate(readers):
        more = i < len(readers) - 1
        board = read(img, mtype)
        if not board.get("is_rate_board"):
            if more and board.get("rows_found", 0) >= 3:
                continue  # looked like a board but could not be read: try the backup reader
            return
        rows, problems = check_board(clean_rows(board.get("rows")), state["last"].get("sarai", {}))
        if problems and more:
            continue  # failed the checks: try the backup reader
        if problems:
            review.append({"t": post["time"], "market": "sarai", "post": post["id"], "problems": problems})
        for code, (buy, sell) in rows.items():
            add_event(state, events, "sarai", code, buy, sell, post["time"], post["id"])
        return


# ---------- Khorasan Market (Herat): plain text ----------

def handle_khorasan(post, state, events, review):
    for q in khorasan_parser.parse_day(post["text"])["quotes"]:
        if not q["valid"]:
            review.append({"t": post["time"], "market": "khorasan", "post": post["id"], "problems": [f"{q['instrument']}: buy above sell"]})
        elif q["is_close"]:
            if q["city"] != "KABUL":
                add_close(state, events, "khorasan", q["instrument"], q["buy"], q["sell"], post["time"], post["id"])
        elif q["city"] == "HERAT":
            add_event(state, events, "khorasan", q["instrument"], q["buy"], q["sell"], post["time"], post["id"])


def process_channel(ch, state, events, review, mode, pages):
    after = 0 if mode == "backfill" else state["last_id"].get(ch["id"], 0)
    posts = telegram.collect(ch["handle"], after, pages if mode == "backfill" else 3)
    log(f"{ch['id']}: {len(posts)} new posts")
    handler = handle_sarai if ch["kind"] == "image" else handle_khorasan
    for p in posts:
        try:
            if p["time"]:
                handler(p, state, events, review)
        except Exception as e:  # stop here and retry this post on the next run
            log(f"  post {p['id']} failed ({e!r}); will retry next run")
            break
        state["last_id"][ch["id"]] = p["id"]


# ---------- aggregation ----------

def previous_day_mid(events, market, code, today):
    prev = [e for e in events if e["market"] == market and e["code"] == code and not e.get("close")
            and when(e["t"]).date() < today]
    if not prev:
        return None
    e = max(prev, key=lambda e: datetime.fromisoformat(e["t"]))
    return (e["buy"] + e["sell"]) / 2


def held_longest(events, market, code, day, now):
    """The (buy, sell) price in effect longest between WINDOW start and min(now, WINDOW end) on `day`."""
    start = datetime.combine(day, dtime(config.WINDOW[0]), config.TZ)
    end = min(now.astimezone(config.TZ), datetime.combine(day, dtime(config.WINDOW[1]), config.TZ))
    if end <= start:
        return None
    series = sorted(((when(e["t"]), (e["buy"], e["sell"])) for e in events
                     if e["market"] == market and e["code"] == code and not e.get("close")), key=lambda s: s[0])
    before = [s for s in series if s[0] <= start]
    cur = before[-1][1] if before else None
    t_prev, dur = start, {}
    for t, val in (s for s in series if start < s[0] < end):
        if cur is not None:
            dur[cur] = dur.get(cur, 0) + (t - t_prev).total_seconds()
        cur, t_prev = val, t
    if cur is not None:
        dur[cur] = dur.get(cur, 0) + (end - t_prev).total_seconds()
    if not dur:
        return None
    return sorted(dur.items(), key=lambda kv: kv[1])[-1]  # ties go to the later price


def build_rates(events, state, now, dab):
    local = now.astimezone(config.TZ)
    today = local.date()
    markets = []
    for ch in config.CHANNELS:
        rows = []
        for code in ch["order"]:
            cur = state["last"].get(ch["id"], {}).get(code)
            if not cur:
                continue
            shown, name = config.NAMES[code]
            m = (cur["buy"] + cur["sell"]) / 2
            pm = previous_day_mid(events, ch["id"], code, today)
            chg = round((m - pm) / pm * 100, 2) if pm else None
            rows.append([shown, name, cur["buy"], cur["sell"], when(cur["t"]).strftime("%I:%M %p").lstrip("0"),
                         chg, config.UNITS.get(code, 1)])
        if any(r[0] == "USD" for r in rows):
            markets.append({"id": ch["id"], "name": ch["name"], "rows": rows})
    markets.extend(dab or [])
    hl = held_longest(events, "sarai", "USD", today, now)
    ref = {"market": "sarai", "buy": hl[0][0], "sell": hl[0][1], "basis": "held longest",
           "final": local.hour >= config.WINDOW[1]} if hl else None
    d = jdatetime.date.fromgregorian(date=today)
    return {"date": today.isoformat(), "solar": f"{d.day} {config.AF_MONTHS[d.month - 1]} {d.year}",
            "generated": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
            "static": False, "reference": ref, "markets": markets}


def update_daily(daily, events, now):
    local = now.astimezone(config.TZ)
    day = daily.setdefault(local.date().isoformat(), {})
    for ch in config.CHANNELS:
        for code in ch["order"]:
            hl = held_longest(events, ch["id"], code, local.date(), now)
            if hl:
                day.setdefault(ch["id"], {})[code] = {"buy": hl[0][0], "sell": hl[0][1],
                                                      "held_minutes": round(hl[1] / 60),
                                                      "final": local.hour >= config.WINDOW[1]}


def update_dab(data, state, now):
    """Read the bank's page at most once an hour. Falls back to the last saved rates, then to config/dab.json."""
    hist = load_json(data / "dab_history.json", {})
    last = state.get("dab_checked")
    if not last or (now - datetime.fromisoformat(last)).total_seconds() >= 3600:
        try:
            parsed = dab.fetch()
            hist[parsed["date"]] = parsed
            save_json(data / "dab_history.json", hist)
            state["dab_checked"] = now.isoformat(timespec="seconds")
        except Exception as e:
            log(f"DAB: could not read the page ({e!r}); using the last saved rates")
    if hist:
        latest = hist[max(hist)]
        prev = next((hist[d] for d in sorted(hist, reverse=True) if d < latest["date"]), None)
        return dab.to_markets(latest, prev)
    seed = load_json(ROOT / "config" / "dab.json", None)
    return [seed] if seed else []


def backfill_dab(data, days):
    """Load the bank's past daily rates, one page request per day. Days it has no rates for are skipped."""
    hist = load_json(data / "dab_history.json", {})
    today, added = datetime.now(config.TZ).date(), 0
    for i in range(days):
        day = today - timedelta(days=i)
        if day.isoformat() in hist:
            continue
        try:
            parsed = dab.fetch(day)
        except Exception as e:
            log(f"DAB {day}: skipped ({e!r})")
            continue
        if parsed["date"] not in hist:  # the page names the date it really shows
            hist[parsed["date"]] = parsed
            added += 1
        time.sleep(1)
    save_json(data / "dab_history.json", hist)
    log(f"DAB: added {added} days of history")


def probe():
    """Show what the collector can see, without reading any images or saving anything."""
    log(f"Sarai Shahzada boards are read with: {[r.__module__.split('.')[-1] for r in sarai_readers()]}")
    for ch in config.CHANNELS:
        posts = telegram.collect(ch["handle"], 0, 1)
        log(f"{ch['id']}: {len(posts)} posts found, {sum(bool(p['photo']) for p in posts)} with a photo, "
            f"{sum(bool(p['text']) for p in posts)} with text")
        for p in posts[-3:]:
            log(f"  #{p['id']} {p['time']} photo={'yes' if p['photo'] else 'no'} text={p['text'][:50]!r}")
    try:
        d = dab.fetch()
        log(f"dab: rates dated {d['date']}, {len(d['rates'])} currencies, USD {d['rates']['USD']}")
    except Exception as e:
        log(f"dab: could not read the page ({e!r})")


def main(argv=None, now=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data_branch")
    ap.add_argument("--mode", default="normal", choices=["normal", "probe", "backfill"])
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--dab-days", type=int, default=60)
    a = ap.parse_args(argv)
    if a.mode == "probe":
        return probe()
    data = Path(a.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)

    state = load_json(data / "state.json", {})
    for k in ("last_id", "last", "closed"):
        state.setdefault(k, {})
    old = load_jsonl(data / "events.jsonl")
    new, review = [], []
    for ch in config.CHANNELS:
        if a.mode == "backfill" and state["last_id"].get(ch["id"]):
            log(f"{ch['id']}: already has data, skipping backfill")
            continue
        process_channel(ch, state, new, review, a.mode, a.pages)
    events = old + new
    append_jsonl(data / "events.jsonl", new)
    append_jsonl(data / "review.jsonl", review)
    if a.mode == "backfill":
        backfill_dab(data, a.dab_days)

    rates = build_rates(events, state, now, update_dab(data, state, now))
    if rates["markets"] and rates["markets"][0]["id"] == "sarai":
        save_json(data / "rates.json", rates)
    else:
        log("No Sarai Shahzada USD price yet; keeping the previous rates.json")
    daily = load_json(data / "daily.json", {})
    update_daily(daily, events, now)
    save_json(data / "daily.json", daily)
    save_json(data / "state.json", state)

    guard, copy = ROOT / "site" / "vercel.json", data / "site" / "vercel.json"
    if guard.exists() and not copy.exists():  # stops Vercel from rebuilding the site on data updates
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(guard.read_text())
    log(f"done: {len(new)} new price changes, {len(review)} items for review")


if __name__ == "__main__":
    main()
