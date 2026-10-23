"""Which stocks to download.

Default: today's Nifty 100 constituents (NSE's published CSV, cached locally).
Override: create universe.txt in the project root, one NSE symbol per line.
"""
import io
import re

import pandas as pd
import requests

import config

NIFTY100_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
CACHE = config.DATA_DIR / "nifty100.csv"
MANUAL = config.ROOT / "universe.txt"
DAILY_DIR = config.DATA_DIR / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)


def csv_path(symbol: str):
    """File for one stock's daily candles (safe filename)."""
    return DAILY_DIR / f"{re.sub(r'[^A-Z0-9_-]', '_', symbol.upper())}.csv"


def get_universe(refresh: bool = False) -> list[str]:
    if MANUAL.exists():
        symbols = [
            s.strip().upper()
            for s in MANUAL.read_text().splitlines()
            if s.strip() and not s.strip().startswith("#")
        ]
        if symbols:
            return symbols

    if CACHE.exists() and not refresh:
        df = pd.read_csv(CACHE)
    else:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Referer": "https://www.niftyindices.com/indices/equity/broad-based-indices",
        }
        try:
            resp = requests.get(NIFTY100_URL, headers=headers, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise SystemExit(
                f"Could not download the Nifty 100 list ({exc}).\n"
                "Workaround: create universe.txt in the project folder with one "
                "NSE symbol per line (RELIANCE, TCS, ...) and rerun."
            )
        CACHE.write_text(resp.text)
        df = pd.read_csv(io.StringIO(resp.text))

    return sorted(df["Symbol"].astype(str).str.strip().str.upper().unique())