"""Load the downloaded daily candles for backtesting (with light repairs)."""
import pandas as pd

import universe

# Restructured/demerged names with messy history: left out of the backtest.
EXCLUDE = {"TMPV", "TMCV"}


def repair_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Force high/low to contain open and close.

    Angel's candles for 2023-03-03 have the open a few paise outside the day's
    [low, high] on six stocks. Widening the range by that much is harmless.
    """
    df = df.copy()
    cols = ["open", "high", "low", "close"]
    df["high"] = df[cols].max(axis=1)
    df["low"] = df[cols].min(axis=1)
    return df


def load_universe(min_rows: int = 750, exclude=EXCLUDE):
    """Return ({symbol: DataFrame indexed by date}, [(symbol, reason skipped)])."""
    data, skipped = {}, []
    for f in sorted(universe.DAILY_DIR.glob("*.csv")):
        sym = f.stem
        if sym in exclude:
            skipped.append((sym, "excluded"))
            continue
        df = pd.read_csv(f, parse_dates=["date"]).sort_values("date")
        df = df.drop_duplicates("date")
        df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
        if len(df) < min_rows:
            skipped.append((sym, f"only {len(df)} rows"))
            continue
        data[sym] = repair_ohlc(df).set_index("date")
    return data, skipped