"""Read posts from a public Telegram channel through its web preview (t.me/s/<name>). No API key needed."""
import re
import time

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (compatible; AFN-rates-bot/1.0)"}
_BG = re.compile(r"url\(['\"]?(.*?)['\"]?\)")


def parse_page(html):
    """Return posts as dicts: id, time (ISO, UTC), text, photo (image URL or None), oldest first."""
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for m in soup.select("div.tgme_widget_message[data-post]"):
        t = m.select_one("a.tgme_widget_message_date time")
        body = m.select_one(".tgme_widget_message_text")
        photo = m.select_one("a.tgme_widget_message_photo_wrap")
        url = None
        if photo is not None and photo.get("style"):
            hit = _BG.search(photo["style"])
            url = hit.group(1) if hit else None
        text = ""
        if body is not None:
            for br in body.find_all("br"):
                br.replace_with("\n")
            text = body.get_text()
        posts.append({"id": int(m["data-post"].split("/")[-1]),
                      "time": t.get("datetime") if t is not None else None,
                      "text": text, "photo": url})
    return sorted(posts, key=lambda p: p["id"])


def fetch(handle, before=None):
    url = f"https://t.me/s/{handle}" + (f"?before={before}" if before else "")
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return parse_page(r.text)


def collect(handle, after_id=0, max_pages=1):
    """Posts newer than after_id, oldest first. Goes back one page (about 20 posts) at a time."""
    got, before = {}, None
    for _ in range(max_pages):
        posts = fetch(handle, before)
        if not posts:
            break
        got.update({p["id"]: p for p in posts})
        oldest = posts[0]["id"]
        if oldest <= after_id + 1:
            break
        before = oldest
        time.sleep(1.5)  # be gentle with Telegram
    return sorted((p for p in got.values() if p["id"] > after_id), key=lambda p: p["id"])
