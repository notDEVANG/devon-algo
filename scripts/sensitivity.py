"""Phase 2: how much does the result depend on the exact parameters?

Runs the strategy over a grid of neighbouring settings. This is a ROBUSTNESS check,
not a search for the best row. If only one corner of the grid works, you have noise.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import itertools  # noqa: E402

import data_loader  # noqa: E402
import report  # noqa: E402
from costs import CostModel  # noqa: E402
from engine import run_backtest  # noqa: E402
from strategy import Params  # noqa: E402

ENTRY = [40, 55, 70]
EXIT = [10, 20, 30]
ATR = [2.0, 3.0, 4.0]
CAPITAL = 500_000.0


def main() -> None:
    data, _ = data_loader.load_universe()
    costs = CostModel()
    print(f"{'entry':>5}{'exit':>5}{'atr':>5} | {'CAGR':>7}{'MaxDD':>8}{'OOS CAGR':>10}"
          f"{'trades':>8} | {'bench CAGR':>11}")
    positive, total = 0, 0
    for e, x, a in itertools.product(ENTRY, EXIT, ATR):
        res = run_backtest(data, Params(entry_len=e, exit_len=x, atr_mult=a), costs, CAPITAL)
        eq = res.equity["equity"].loc[res.trade_start:]
        mid = eq.index[len(eq) // 2]
        full, oos = report.perf(eq), report.perf(eq.loc[mid:])
        bench = report.benchmark(data, eq.index[0], CAPITAL).reindex(eq.index).ffill()
        bfull = report.perf(bench)
        total += 1
        positive += oos["cagr"] > 0
        print(f"{e:>5}{x:>5}{a:>5.1f} | {full['cagr']:>7.1%}{full['maxdd']:>8.1%}"
              f"{oos['cagr']:>10.1%}{len(res.trades):>8} | {bfull['cagr']:>11.1%}")
    print(f"\n{positive} of {total} settings made money in the out-of-sample half.")
    print("Do not pick the best row. Look for a broad, stable region, and compare "
          "every row with the benchmark column.")


if __name__ == "__main__":
    main()