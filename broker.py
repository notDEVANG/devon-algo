"""Angel One SmartAPI: login, instrument lookup, daily candles (with retry + chunking)."""
import json
import time
from datetime import datetime, timedelta

import pandas as pd
import pyotp
import requests
from SmartApi import SmartConnect
from SmartApi.smartExceptions import DataException

import config

INSTRUMENT_CACHE = config.DATA_DIR / "instruments.json"

# Conservative window per request. Longer ranges are fetched in several calls.
MAX_DAYS_PER_REQUEST = 1000
PAUSE_BETWEEN_CHUNKS = 1.0  # seconds, to stay under Angel's rate limit

_token_map: dict[str, tuple[str, str]] | None = None


def login() -> SmartConnect:
    """Log in with API key + client code + PIN + auto-generated TOTP."""
    config.require(
        "ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PIN", "ANGEL_TOTP_SECRET"
    )
    client = SmartConnect(api_key=config.ANGEL_API_KEY)
    totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
    resp = client.generateSession(config.ANGEL_CLIENT_CODE, config.ANGEL_PIN, totp)
    if not resp or not resp.get("status"):
        msg = resp.get("message") if isinstance(resp, dict) else resp
        raise SystemExit(
            f"Login failed: {msg}\n"
            "If this says 'Invalid totp': the secret must come from SmartAPI's "
            "enable-TOTP page, and your computer clock must be accurate."
        )
    return client


def load_instruments(refresh: bool = False) -> list[dict]:
    """Download Angel's instrument master (big file), cache it locally."""
    if INSTRUMENT_CACHE.exists() and not refresh:
        return json.loads(INSTRUMENT_CACHE.read_text())
    print("Downloading instrument master (one time, can take a minute)...")
    resp = requests.get(config.INSTRUMENT_MASTER_URL, timeout=120)
    resp.raise_for_status()
    INSTRUMENT_CACHE.write_text(resp.text)
    return resp.json()


def find_token(symbol: str, exchange: str = "NSE") -> tuple[str, str]:
    """Return (token, trading_symbol) for a cash-segment stock, e.g. RELIANCE.

    Raises LookupError if the symbol is not found.
    """
    global _token_map
    if _token_map is None:
        _token_map = {
            f"{row['exch_seg']}:{row['symbol']}": (row["token"], row["symbol"])
            for row in load_instruments()
            if row.get("symbol", "").endswith("-EQ")
        }
    key = f"{exchange}:{symbol.upper()}-EQ"
    if key not in _token_map:
        raise LookupError(f"{symbol} not found on {exchange} (looked for {key})")
    return _token_map[key]


def _candle_request(client: SmartConnect, params: dict, max_attempts: int = 6) -> dict:
    """Call getCandleData, retrying with backoff when Angel rate-limits us."""
    for attempt in range(1, max_attempts + 1):
        try:
            return client.getCandleData(params)
        except DataException as exc:
            if "rate" in str(exc).lower() and attempt < max_attempts:
                wait = min(10 * 2 ** (attempt - 1), 60)
                print(f"  rate limited, retrying in {wait}s ({attempt}/{max_attempts})")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def get_daily_candles(client: SmartConnect, token: str, days: int = 365,
                      exchange: str = "NSE", from_dt: datetime | None = None,
                      to_dt: datetime | None = None) -> pd.DataFrame:
    """Fetch daily candles between from_dt and to_dt (default: last `days` days).

    Returns columns: timestamp, open, high, low, close, volume.
    An empty DataFrame means Angel returned no candles for the range.
    """
    to_dt = to_dt or datetime.now()
    from_dt = from_dt or (to_dt - timedelta(days=days))

    rows: list[list] = []
    start = from_dt
    first = True
    while start.date() <= to_dt.date():
        end = min(start + timedelta(days=MAX_DAYS_PER_REQUEST - 1), to_dt)
        if not first:
            time.sleep(PAUSE_BETWEEN_CHUNKS)
        first = False
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": start.strftime("%Y-%m-%d 09:15"),
            "todate": end.strftime("%Y-%m-%d 15:30"),
        }
        resp = _candle_request(client, params)
        if not resp or not resp.get("status"):
            raise RuntimeError(f"Candle request failed: {resp}")
        rows.extend(resp.get("data") or [])
        start = end + timedelta(days=1)

    df = pd.DataFrame(
        rows, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def logout(client: SmartConnect) -> None:
    try:
        client.terminateSession(config.ANGEL_CLIENT_CODE)
    except Exception as exc:  # logout failure is not critical
        print(f"Logout warning: {exc}")