"""Phase 2: backtest the strategy in strategy.py on the downloaded Nifty 100 data.

    python scripts/run_backtest.py
Parameters are FIXED in advance (see strategy.Params). Do not tune them to make the
numbers look better; scripts/sensitivity.py shows how much the result depends on them.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
import data_loader  # noqa: E402
import report  # noqa: E402
from costs import CostModel  # noqa: E402
from engine import run_backtest  # noqa: E402
from strategy import Params  # noqa: E402


def pct(x, nd=1):
    return "   n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:6.{nd}f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=500_000, help="placeholder, results are in %%")
    ap.add_argument("--entry", type=int, default=Params.entry_len)
    ap.add_argument("--exit", type=int, default=Params.exit_len)
    ap.add_argument("--atr-mult", type=float, default=Params.atr_mult)
    ap.add_argument("--slippage", type=float, default=CostModel.slippage_pct, help="per side, e.g. 0.001")
    ap.add_argument("--brokerage", choices=["zero", "capped"], default="capped")
    ap.add_argument("--min-rows", type=int, default=750)
    args = ap.parse_args()

    p = Params(entry_len=args.entry, exit_len=args.exit, atr_mult=args.atr_mult)
    costs = CostModel(slippage_pct=args.slippage, brokerage_mode=args.brokerage)

    data, skipped = data_loader.load_universe(min_rows=args.min_rows)
    if not data:
        raise SystemExit("No data. Run scripts/download_daily.py first.")
    print(f"Universe: {len(data)} stocks. Skipped {len(skipped)}: "
          + ", ".join(f"{s} ({r})" for s, r in skipped))

    res = run_backtest(data, p, costs, args.capital)
    eq = res.equity["equity"].loc[res.trade_start:]
    bench = report.benchmark(data, eq.index[0], args.capital)
    bench = bench.reindex(eq.index).ffill()
    mid = eq.index[len(eq) // 2]

    print(f"\nTrading period {eq.index[0].date()} to {eq.index[-1].date()} "
          f"(first {p.trend_len} days of every stock are warm-up). Split at {mid.date()}.")
    print(f"Rules: entry {p.entry_len}-day high, exit {p.exit_len}-day low, "
          f"stop {p.atr_mult} x ATR{p.atr_len}, trend SMA{p.trend_len}, "
          f"risk {p.risk_pct:.0%}/trade, max {p.max_positions} positions of "
          f"{p.max_pos_pct:.0%}")
    print(f"Costs: brokerage={costs.brokerage_mode}, slippage {costs.slippage_pct:.2%}/side, "
          f"STT {costs.stt_pct:.2%} each side, stamp, DP, GST. Taxes on profits NOT included.\n")

    print(f"{'Period':<14}{'Strat CAGR':>11}{'MaxDD':>9}{'Sharpe':>8}"
          f"{'|':>3}{'Bench CAGR':>11}{'MaxDD':>9}{'Sharpe':>8}")
    periods = {"Full": (eq.index[0], eq.index[-1]),
               "In-sample": (eq.index[0], mid),
               "Out-of-sample": (mid, eq.index[-1])}
    perfs = {}
    for name, (a, b) in periods.items():
        s, bm = report.perf(eq.loc[a:b]), report.perf(bench.loc[a:b])
        perfs[name] = (s, bm)
        print(f"{name:<14}{pct(s['cagr']):>11}{pct(s['maxdd']):>9}{s['sharpe']:>8.2f}"
              f"{'|':>3}{pct(bm['cagr']):>11}{pct(bm['maxdd']):>9}{bm['sharpe']:>8.2f}")

    print("\nCalendar years (first and last may be partial):")
    ys, yb = report.yearly(eq), report.yearly(bench)
    for y in ys.index:
        print(f"  {y}: strategy {pct(ys[y])}   benchmark {pct(yb.get(y, np.nan))}")

    tr = res.trades
    st = report.trade_stats(tr, args.capital)
    exposure = (res.equity.loc[res.trade_start:, "invested"]
                / res.equity.loc[res.trade_start:, "equity"]).mean()
    print(f"\nTrades: {st['n']}   open at end: {res.open_positions}   "
          f"avg exposure {exposure:.0%}")
    if st["n"]:
        print(f"  win rate {st['win_rate']:.0%}   avg win {pct(st['avg_win'])}   "
              f"avg loss {pct(st['avg_loss'])}   profit factor {st['profit_factor']:.2f}   "
              f"avg hold {st['avg_days']:.0f} days   stop exits {st['stops']}")
        print(f"  fees+taxes Rs {st['fees']:,.0f} and slippage Rs {st['slippage']:,.0f} "
              f"= {(st['fees'] + st['slippage']) / args.capital:.1%} of starting capital")
        print(f"  top-5 trades = {pct(st['top5_share'], 0).strip()} of total profit")

    print("\nFlags:")
    full_s, full_b = perfs["Full"]
    oos_s, oos_b = perfs["Out-of-sample"]
    flags = []
    if st["n"] < 100:
        flags.append(f"only {st['n']} trades: too few to trust any average.")
    if not (full_s["cagr"] > full_b["cagr"]):
        flags.append("full period: did NOT beat equal-weight buy-and-hold.")
    if not (oos_s["cagr"] > oos_b["cagr"]):
        flags.append("out-of-sample half: did NOT beat equal-weight buy-and-hold.")
    if not (oos_s["cagr"] > 0):
        flags.append("out-of-sample half lost money.")
    if st["n"] and st.get("top5_share", 0) and st["top5_share"] > 0.4:
        flags.append("a handful of trades produce most of the profit (fragile).")
    if abs(oos_s["maxdd"]) > abs(oos_b["maxdd"]):
        flags.append("out-of-sample drawdown is worse than buy-and-hold.")
    print("  " + ("\n  ".join(flags) if flags else "none triggered. That is not proof of an edge."))
    print("\nReminder: the benchmark and the stock list both use today's Nifty 100 "
          "(survivorship bias), and 2022-2026 was largely a rising market.")

    out_dir = config.DATA_DIR / "backtest"
    out_dir.mkdir(exist_ok=True)
    res.equity.to_csv(out_dir / "equity.csv")
    tr.to_csv(out_dir / "trades.csv", index=False)
    print(f"\nSaved trades.csv and equity.csv in {out_dir}")


if __name__ == "__main__":
    main()