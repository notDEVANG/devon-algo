"""Portfolio backtest engine: daily bars, long-only, fills at the next open.

No look-ahead: a signal computed from day t's close is acted on at day t+1's open.
Gaps are handled honestly: a stop that is gapped through fills at the open.
"""
import math
from dataclasses import dataclass

import pandas as pd

from costs import CostModel
from strategy import Params, add_indicators


class _Sym:
    __slots__ = ("o", "h", "l", "c", "entry", "exit", "atr", "mom", "idx")


@dataclass
class Result:
    equity: pd.DataFrame
    trades: pd.DataFrame
    trade_start: pd.Timestamp
    open_positions: int


def _prepare(data, p):
    sdata, sma_valid = {}, {}
    for sym, df in data.items():
        ind = add_indicators(df, p)
        sd = _Sym()
        sd.o = ind["open"].to_numpy(float)
        sd.h = ind["high"].to_numpy(float)
        sd.l = ind["low"].to_numpy(float)
        sd.c = ind["close"].to_numpy(float)
        sd.entry = ind["entry"].to_numpy(bool)
        sd.exit = ind["exit"].to_numpy(bool)
        sd.atr = ind["atr"].to_numpy(float)
        sd.mom = ind["mom"].to_numpy(float)
        sd.idx = {d: i for i, d in enumerate(ind.index)}
        sdata[sym] = sd
        sma_valid[sym] = ind["sma"].notna()
    valid = pd.concat(sma_valid, axis=1).fillna(False).sum(axis=1)
    ready = valid[valid >= 0.5 * len(data)]
    trade_start = ready.index[0] if len(ready) else valid.index[-1]
    return sdata, trade_start


def run_backtest(data, p: Params, costs: CostModel, capital: float = 500_000.0) -> Result:
    sdata, trade_start = _prepare(data, p)
    dates = sorted(set().union(*(sd.idx.keys() for sd in sdata.values())))

    cash = capital
    pos, last_close = {}, {}
    pending_exit, pending_entry = set(), []
    trades, rows = [], []

    def close_position(sym, d, ref, reason):
        nonlocal cash
        q = pos.pop(sym)
        fill = costs.fill_price("sell", ref)
        value = q["shares"] * fill
        fee = costs.fees("sell", value)
        cash += value - fee
        cost_basis = q["shares"] * q["entry_price"] + q["entry_fee"]
        pnl = value - fee - cost_basis
        trades.append({
            "symbol": sym, "entry_date": q["entry_date"], "exit_date": d,
            "shares": q["shares"], "entry_ref": q["entry_ref"],
            "entry_price": q["entry_price"], "exit_ref": ref, "exit_price": fill,
            "entry_fee": q["entry_fee"], "exit_fee": fee,
            "slippage": q["shares"] * ((q["entry_price"] - q["entry_ref"]) + (ref - fill)),
            "pnl": pnl, "ret": pnl / cost_basis, "reason": reason,
            "days_held": (d - q["entry_date"]).days,
        })

    for d in dates:
        today = {s: sd.idx[d] for s, sd in sdata.items() if d in sd.idx}

        # 1) exits decided at yesterday's close, filled at today's open
        for s in list(pending_exit):
            if s in pos and s in today:
                close_position(s, d, sdata[s].o[today[s]], "signal")
        pending_exit = {s for s in pending_exit if s in pos}

        # 2) entries decided at yesterday's close, filled at today's open
        equity_now = cash + sum(q["shares"] * last_close.get(s, q["entry_price"])
                                for s, q in pos.items())
        for s, atr in pending_entry:
            if len(pos) >= p.max_positions:
                break
            if s in pos or s not in today:
                continue
            ref = sdata[s].o[today[s]]
            fill = costs.fill_price("buy", ref)
            stop_dist = p.atr_mult * atr
            shares = int(min(p.risk_pct * equity_now / stop_dist,
                             p.max_pos_pct * equity_now / fill,
                             cash / (fill * 1.005)))
            while shares > 0 and shares * fill + costs.fees("buy", shares * fill) > cash:
                shares -= 1
            if shares < 1:
                continue
            fee = costs.fees("buy", shares * fill)
            cash -= shares * fill + fee
            pos[s] = {"shares": shares, "entry_ref": ref, "entry_price": fill,
                      "stop": fill - stop_dist, "entry_date": d, "entry_fee": fee}

        # 3) protective stops during today's session (incl. positions opened today)
        for s in list(pos):
            if s in today:
                i = today[s]
                if sdata[s].l[i] <= pos[s]["stop"]:
                    ref = min(sdata[s].o[i], pos[s]["stop"])   # gap through stop -> open
                    close_position(s, d, ref, "stop")
                    pending_exit.discard(s)

        # 4) mark to market at the close
        for s, i in today.items():
            last_close[s] = sdata[s].c[i]
        invested = sum(q["shares"] * last_close[s] for s, q in pos.items())
        rows.append({"date": d, "equity": cash + invested, "cash": cash,
                     "positions": len(pos), "invested": invested})

        # 5) signals from today's close, to be acted on at the next open
        for s in pos:
            if s in today and sdata[s].exit[today[s]]:
                pending_exit.add(s)
        cands = []
        for s, i in today.items():
            sd = sdata[s]
            if s not in pos and sd.entry[i] and sd.atr[i] > 0:
                m = sd.mom[i]
                cands.append((-(m if m == m else -1e9), s, sd.atr[i]))
        cands.sort()
        pending_entry = [(s, atr) for _, s, atr in cands]

    equity = pd.DataFrame(rows).set_index("date")
    return Result(equity, pd.DataFrame(trades), trade_start, len(pos))