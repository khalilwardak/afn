"""Read a Sarai Shahzada rate board (an image) with Claude and return structured rows."""
import base64
import json
import os

import requests

from . import config

PROMPT = """This image is a currency exchange rate board posted by the Sarai Shahzada market in Kabul (text is in Dari).

Return ONLY a JSON object, with no other text:
{"is_rate_board": true, "rows": [{"code": "USD", "buy": 64.90, "sell": 64.95, "time": "2:58 PM"}]}

Rules:
- Read each row's Latin ISO code from the code column (USD, EUR, GBP, ...). Ignore the Dari currency names: they can be misaligned.
- Each row has these values from left to right: time, sell, buy, code. The number immediately left of the code is BUY and the next number to its left is SELL.
- Convert the time: ق.ظ means AM and ب.ظ means PM.
- Include every row exactly as printed, as plain decimal numbers.
- If the image is not a rate board, return {"is_rate_board": false, "rows": []}."""


def read_board(image_bytes, media_type="image/jpeg"):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": config.CLAUDE_MODEL, "max_tokens": 2000, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.b64encode(image_bytes).decode()}},
            {"type": "text", "text": PROMPT}]}]},
        timeout=90)
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json()["content"]).strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)
