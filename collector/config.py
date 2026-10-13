"""Settings. Edit here, not in the code."""
import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kabul")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")  # "claude-haiku-5-5" is cheaper: test it first
READER = os.environ.get("READER", "auto")  # auto: free OCR, Claude only as a backup if a key exists; ocr; claude
WINDOW = (8, 15)  # Kabul hours used for the "price held longest" reference (08:00 to 15:00)

CHANNELS = [
    {"id": "sarai", "name": "Sarai Shahzada", "handle": "sarai_Shahzada1", "kind": "image",
     "order": ["USD", "EUR", "GBP", "IRR", "PKR", "SAR", "AED", "CHF", "AUD", "CAD", "RUB", "DKK",
               "SEK", "NOK", "TRY", "CNY", "KWD", "QAR", "BHD", "JPY"]},
    {"id": "khorasan", "name": "Khorasan Market (Herat)", "handle": "nerkhyabkorasan", "kind": "text",
     "order": ["USD", "EUR", "PKR", "IRR_BANK", "IRR_CHEQUE"]},
]

NAMES = {  # instrument: (code shown on the site, English name)
    "USD": ("USD", "US dollar"), "EUR": ("EUR", "Euro"), "GBP": ("GBP", "British pound"),
    "IRR": ("IRR", "Iranian rial"), "PKR": ("PKR", "Pakistani rupee"), "SAR": ("SAR", "Saudi riyal"),
    "AED": ("AED", "UAE dirham"), "CHF": ("CHF", "Swiss franc"), "AUD": ("AUD", "Australian dollar"),
    "CAD": ("CAD", "Canadian dollar"), "RUB": ("RUB", "Russian ruble"), "DKK": ("DKK", "Danish krone"),
    "SEK": ("SEK", "Swedish krona"), "NOK": ("NOK", "Norwegian krone"), "TRY": ("TRY", "Turkish lira"),
    "CNY": ("CNY", "Chinese yuan"), "KWD": ("KWD", "Kuwaiti dinar"), "QAR": ("QAR", "Qatari riyal"),
    "BHD": ("BHD", "Bahraini dinar"), "JPY": ("JPY", "Japanese yen"),
    "IRR_BANK": ("IRRB", "Iranian toman (bank)"), "IRR_CHEQUE": ("IRRC", "Iranian toman (cheque)"),
}
# Quoted per 1,000 units. CONFIRM the Khorasan toman and rupee units with the market.
UNITS = {"IRR": 1000, "PKR": 1000, "JPY": 1000, "IRR_BANK": 1000, "IRR_CHEQUE": 1000}

PEGS = {"AED": 3.6725, "SAR": 3.75, "QAR": 3.64, "BHD": 0.376}  # units per USD (fixed rates)
PEG_TOLERANCE = 0.01   # USD must agree with the pegged currencies within 1%
JUMP_LIMIT = 0.05      # skip a non-USD row that moves more than 5% in one update
AF_MONTHS = ["Hamal", "Sawr", "Jawza", "Saratan", "Asad", "Sunbula", "Mizan", "Aqrab", "Qaws", "Jadi", "Dalw", "Hut"]
