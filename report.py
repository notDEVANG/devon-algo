"""Performance numbers for a backtest and an equal-weight buy-and-hold benchmark."""
import numpy as np
import pandas as pd


def perf(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 3:
        return {"cagr": np.nan, "maxdd": np.nan, "sharpe": np.nan, "total": np.nan}
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    rets = eq.pct_change().dropna()
    return {
        "total": eq.iloc[-1] / eq.iloc[0] - 1,
        "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan,
        "maxdd": (eq / eq.cummax() - 1).min(),
        "sharpe": rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else np.nan,
    }


def benchmark(data: dict, start, capital: float) -> pd.Series:
    """Equal-weight, daily-rebalanced buy-and-hold of the same stocks.

    Built from TODAY's constituents, so it has survivorship bias too.
    """
    closes = pd.DataFrame({s: df["close"] for s, df in data.items()})
    daily = closes.pct_change().mean(axis=1, skipna=True).fillna(0.0)
    curve = (1 + daily).cumprod().loc[start:]
    return capital * curve / curve.iloc[0]


def yearly(eq: pd.Series) -> pd.Series:
    year_end = eq.groupby(eq.index.year).last()
    prev = year_end.shift(1)
    prev.iloc[0] = eq.iloc[0]
    return year_end / prev - 1


def trade_stats(trades: pd.DataFrame, capital: float) -> dict:
    if trades.empty:
        return {"n": 0}
    wins, losses = trades[trades["pnl"] > 0], trades[trades["pnl"] <= 0]
    total_pnl = trades["pnl"].sum()
    top5 = trades["pnl"].nlargest(5).sum()
    return {
        "n": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_win": wins["ret"].mean() if len(wins) else np.nan,
        "avg_loss": losses["ret"].mean() if len(losses) else np.nan,
        "profit_factor": wins["pnl"].sum() / -losses["pnl"].sum() if losses["pnl"].sum() < 0 else np.inf,
        "avg_days": trades["days_held"].mean(),
        "stops": int((trades["reason"] == "stop").sum()),
        "total_pnl": total_pnl,
        "top5_share": top5 / total_pnl if total_pnl > 0 else np.nan,
        "fees": (trades["entry_fee"] + trades["exit_fee"]).sum(),
        "slippage": trades["slippage"].sum(),
    }