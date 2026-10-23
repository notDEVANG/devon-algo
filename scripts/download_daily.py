"""Phase 1: download daily candles for the whole universe, incrementally.

First try:   python scripts/download_daily.py --limit 5
Full run:    python scripts/download_daily.py
Rerunning only fetches what is missing (plus a 5-day overlap to catch corrections).
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import broker  # noqa: E402
import notify  # noqa: E402
import universe  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
PAUSE_BETWEEN_STOCKS = 1.5  # seconds
OVERLAP_DAYS = 5


def last_complete_date():
    """Newest date whose candle is final. NSE closes 15:30 IST; we wait until 16:00."""
    now = datetime.now(IST)
    return now.date() if now.hour >= 16 else (now - timedelta(days=1)).date()


def normalise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["timestamp"]).dt.tz_localize(None).dt.normalize()
    out = out[["date", "open", "high", "low", "close", "volume"]]
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col])
    return out.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=float, default=5, help="history to fetch on first run")
    parser.add_argument("--limit", type=int, default=0, help="only the first N stocks (testing)")
    parser.add_argument("--symbols", type=str, default="", help="comma-separated override")
    parser.add_argument("--refresh-universe", action="store_true")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        symbols = universe.get_universe(refresh=args.refresh_universe)
    if args.limit:
        symbols = symbols[: args.limit]

    cutoff = last_complete_date()
    print(f"{len(symbols)} stocks. Keeping candles up to {cutoff} (incomplete sessions dropped).")

    client = broker.login()
    updated, skipped, failed = 0, 0, []

    for i, symbol in enumerate(symbols, start=1):
        path = universe.csv_path(symbol)
        try:
            existing = None
            if path.exists():
                existing = pd.read_csv(path, parse_dates=["date"])
            if existing is not None and len(existing):
                from_dt = existing["date"].max().to_pydatetime() - timedelta(days=OVERLAP_DAYS)
            else:
                from_dt = datetime.now() - timedelta(days=int(args.years * 365))

            if existing is not None and len(existing) and existing["date"].max().date() >= cutoff:
                print(f"[{i}/{len(symbols)}] {symbol}: up to date")
                skipped += 1
                continue

            token, _ = broker.find_token(symbol)
            raw = broker.get_daily_candles(client, token, from_dt=from_dt, to_dt=datetime.now())
            if raw.empty:
                raise RuntimeError("no candles returned")
            new = normalise(raw)
            new = new[new["date"].dt.date <= cutoff]

            merged = pd.concat([existing, new]) if existing is not None else new
            merged = merged.drop_duplicates("date", keep="last").sort_values("date")
            merged.to_csv(path, index=False)
            print(f"[{i}/{len(symbols)}] {symbol}: {len(merged)} rows "
                  f"({merged['date'].min().date()} to {merged['date'].max().date()})")
            updated += 1
        except Exception as exc:  # keep going, report at the end
            msg = str(exc)[:150]
            print(f"[{i}/{len(symbols)}] {symbol}: FAILED - {msg}")
            failed.append((symbol, msg))
        time.sleep(PAUSE_BETWEEN_STOCKS)

    broker.logout(client)

    summary = (f"Download done: {updated} updated, {skipped} already current, "
               f"{len(failed)} failed.")
    print("\n" + summary)
    for symbol, msg in failed:
        print(f"  {symbol}: {msg}")
    if failed:
        print("Rerun the script to retry failures; finished stocks are skipped.")
    notify.send(summary + (f" Failed: {', '.join(s for s, _ in failed[:15])}" if failed else ""))


if __name__ == "__main__":
    main()