"""Long-only trend + breakout swing strategy on daily candles.

HYPOTHESIS (written down before testing): large, liquid Indian stocks that are in
an established uptrend and then close above their recent range keep trending for
weeks, and a trailing channel exit lets winners run while the stop caps losers.
This file does not claim that is true. The backtest exists to find out.

RULES (all signals use data up to the CLOSE of day t; orders fill at the OPEN of t+1)
  Trend filter : close > SMA(trend_len)
  Entry        : close > highest HIGH of the previous entry_len days
  Exit         : close < lowest LOW of the previous exit_len days
  Stop         : fixed at entry fill - atr_mult * ATR(atr_len); hit intraday, and if a
                 stock opens below the stop we fill at the open (gap risk, not the stop)
  Sizing       : risk risk_pct of equity to the stop, capped at max_pos_pct of equity
  Capacity     : at most max_positions at once; if more signals than slots, take the
                 strongest rank_len-day return first
"""
from dataclasses import dataclass

import pandas as pd


@dataclass
class Params:
    trend_len: int = 200
    entry_len: int = 55
    exit_len: int = 20
    atr_len: int = 20
    atr_mult: float = 3.0
    risk_pct: float = 0.01
    max_pos_pct: float = 0.10
    max_positions: int = 10
    rank_len: int = 126


def add_indicators(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Add sma, atr, mom, entry, exit columns. Row t only ever uses rows <= t."""
    out = df.copy()
    close, high, low = out["close"], out["high"], out["low"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    out["atr"] = true_range.rolling(p.atr_len).mean()
    out["sma"] = close.rolling(p.trend_len).mean()
    # shift(1): the channel covers the PREVIOUS N days, never including today.
    channel_high = high.rolling(p.entry_len).max().shift(1)
    channel_low = low.rolling(p.exit_len).min().shift(1)
    out["mom"] = close.pct_change(p.rank_len)
    out["entry"] = (close > channel_high) & (close > out["sma"]) & out["atr"].notna()
    out["exit"] = close < channel_low
    return out