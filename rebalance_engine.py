"""Monthly-rebalance engine for the momentum hypotheses H1 and H2 (see RESEARCH_LOG.md).

No look-ahead: scores and the regime flag use data up to the LAST CLOSE BEFORE the
rebalance day; trades fill at that rebalance day's OPEN, with the same cost model and
slippage as the trend backtest.

Rules (fixed in RESEARCH_LOG.md before any run):
  score    = close(t-skip) / close(t-lookback) - 1, t = last close before the rebalance
  rebalance on the first trading day of each month
  sell a holding only if it falls out of the top n_keep (or in risk-off)
  fill empty slots from the highest-ranked stocks not held, each 1/n_hold of equity
  no trimming of winners (weights drift between rebalances)
  H2 (regime_len > 0): if the equal-weight market proxy closed below its regime_len-day
  average, sell everything and hold cash until the next rebalance
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from costs import CostModel


@dataclass
class MomentumConfig:
    lookback: int = 252
    skip: int = 21
    n_hold: int = 10
    n_keep: int = 20
    regime_len: int = 0      # 0 = H1 (no filter); 200 = H2


@dataclass
class MonthlyResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    trade_start: pd.Timestamp
    rebalance_dates: list
    open_positions: int
    holdings: list


def market_proxy(closes: pd.DataFrame) -> pd.Series:
    """Equal-weight, daily-rebalanced index built from the stocks themselves."""
    filled = closes.ffill()
    daily = filled.pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0.0)
    return (1 + daily).cumprod()


def run_monthly(data: dict, cfg: MomentumConfig, costs: CostModel,
                capital: float = 500_000.0) -> MonthlyResult:
    closes = pd.DataFrame({s: df["close"] for s, df in data.items()}).sort_index()
    opens = pd.DataFrame({s: df["open"] for s, df in data.items()}).reindex(closes.index)
    filled = closes.ffill()
    syms, dates = list(closes.columns), closes.index
    O, C = opens.to_numpy(float), filled.to_numpy(float)
    score = (filled.shift(cfg.skip) / filled.shift(cfg.lookback) - 1).to_numpy(float)

    regime_on = None
    if cfg.regime_len:
        proxy = market_proxy(closes)
        regime_on = (proxy > proxy.rolling(cfg.regime_len).mean()).to_numpy(bool)

    first_of_month = (pd.Series(np.arange(len(dates)), index=dates)
                      .groupby([dates.year, dates.month]).first().to_numpy())
    rebalance_idx = {int(i) for i in first_of_month if i >= 1}

    cash = capital
    pos, trades, rows, rebalance_dates = {}, [], [], []
    trade_start = None

    def sell(j, d, ref, reason):
        nonlocal cash
        q = pos.pop(j)
        fill = costs.fill_price("sell", ref)
        value = q["shares"] * fill
        fee = costs.fees("sell", value)
        cash += value - fee
        basis = q["shares"] * q["entry_price"] + q["entry_fee"]
        pnl = value - fee - basis
        trades.append({
            "symbol": syms[j], "entry_date": q["entry_date"], "exit_date": d,
            "shares": q["shares"], "entry_price": q["entry_price"], "exit_price": fill,
            "entry_fee": q["entry_fee"], "exit_fee": fee,
            "slippage": q["shares"] * ((q["entry_price"] - q["entry_ref"]) + (ref - fill)),
            "pnl": pnl, "ret": pnl / basis, "reason": reason,
            "days_held": (d - q["entry_date"]).days,
        })

    for i, d in enumerate(dates):
        if i in rebalance_idx:
            s = i - 1
            sc = score[s]
            if np.isfinite(sc).sum() >= 0.5 * len(syms):
                if trade_start is None:
                    trade_start = d
                rebalance_dates.append(d)
                order = [int(j) for j in np.argsort(-np.where(np.isfinite(sc), sc, -np.inf),
                                                    kind="stable") if np.isfinite(sc[j])]
                rank = {j: r for r, j in enumerate(order)}
                risk_off = regime_on is not None and not regime_on[s]

                for j in list(pos):
                    out = risk_off or rank.get(j, 10 ** 9) >= cfg.n_keep
                    if out and np.isfinite(O[i, j]):
                        sell(j, d, O[i, j], "risk-off" if risk_off else "dropped out")

                if not risk_off:
                    equity_est = cash + sum(q["shares"] * C[s, j] for j, q in pos.items())
                    target = equity_est / cfg.n_hold
                    for j in order:
                        if len(pos) >= cfg.n_hold:
                            break
                        if j in pos or not np.isfinite(O[i, j]):
                            continue
                        ref = O[i, j]
                        fill = costs.fill_price("buy", ref)
                        n = int(min(target / fill, cash / (fill * 1.005)))
                        while n > 0 and n * fill + costs.fees("buy", n * fill) > cash:
                            n -= 1
                        if n < 1:
                            continue
                        fee = costs.fees("buy", n * fill)
                        cash -= n * fill + fee
                        pos[j] = {"shares": n, "entry_ref": ref, "entry_price": fill,
                                  "entry_fee": fee, "entry_date": d}

        invested = sum(q["shares"] * C[i, j] for j, q in pos.items())
        rows.append({"date": d, "equity": cash + invested, "cash": cash,
                     "positions": len(pos), "invested": invested})

    equity = pd.DataFrame(rows).set_index("date")
    return MonthlyResult(equity, pd.DataFrame(trades),
                         trade_start if trade_start is not None else dates[-1],
                         rebalance_dates, len(pos), sorted(syms[j] for j in pos))