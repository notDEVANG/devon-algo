"""Run the pre-registered hypotheses H1 and H2 exactly as written in RESEARCH_LOG.md.

    python scripts/run_research.py

There are deliberately NO command-line parameters. Every run is appended to
research_runs.csv so reruns are counted. Do not edit the settings below after seeing
results: that would be a new trial, and it must be logged as one.
"""
import csv
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402
import data_loader  # noqa: E402
import report  # noqa: E402
from costs import CostModel  # noqa: E402
from rebalance_engine import MomentumConfig, run_monthly  # noqa: E402

CAPITAL = 500_000.0
DEV_END = pd.Timestamp("2025-10-23")
MIN_DEV_REBALANCES = 30      # amended from 40 on 2026-10-25, see RESEARCH_LOG.md
MAX_DD_GAP = 0.05
LOG = config.ROOT / "research_runs.csv"

HYPOTHESES = {
    "H1": [("base", MomentumConfig()),
           ("lookback 189", MomentumConfig(lookback=189)),
           ("lookback 315", MomentumConfig(lookback=315)),
           ("hold 8", MomentumConfig(n_hold=8)),
           ("hold 12", MomentumConfig(n_hold=12))],
    "H2": [("base", MomentumConfig(regime_len=200)),
           ("avg 150", MomentumConfig(regime_len=150)),
           ("avg 250", MomentumConfig(regime_len=250))],
}


def pct(x):
    return "   n/a" if x is None or np.isnan(x) else f"{x * 100:6.1f}%"


def evaluate(data, cfg, costs):
    res = run_monthly(data, cfg, costs, CAPITAL)
    eq = res.equity["equity"].loc[res.trade_start:]
    bench = report.benchmark(data, eq.index[0], CAPITAL).reindex(eq.index).ffill()
    dev_end = eq.index[eq.index <= DEV_END][-1]
    out = {
        "start": eq.index[0], "res": res,
        "dev": report.perf(eq.loc[:dev_end]), "dev_b": report.perf(bench.loc[:dev_end]),
        "hold": report.perf(eq.loc[dev_end:]), "hold_b": report.perf(bench.loc[dev_end:]),
        "full": report.perf(eq), "full_b": report.perf(bench),
        "dev_rebalances": sum(1 for d in res.rebalance_dates if d <= DEV_END),
    }
    tr = res.trades
    out["trades"] = len(tr)
    out["cost_pct"] = ((tr["entry_fee"] + tr["exit_fee"] + tr["slippage"]).sum() / CAPITAL
                       if len(tr) else 0.0)
    return out


def main() -> None:
    data, skipped = data_loader.load_universe()
    if not data:
        raise SystemExit("No data. Run scripts/download_daily.py first.")
    prior = 0
    if LOG.exists():
        prior = sum(1 for _ in open(LOG)) - 1
    if prior > 0:
        print(f"NOTE: research_runs.csv already has {prior} logged runs. Under the protocol "
              f"each rerun is a new trial and must be recorded in RESEARCH_LOG.md.\n")

    print(f"Universe: {len(data)} stocks. Development ends {DEV_END.date()}; "
          f"holdout = the year after. Costs on (costs.py defaults).\n")
    costs = CostModel()
    results = {}
    for hyp, variants in HYPOTHESES.items():
        for name, cfg in variants:
            results[(hyp, name)] = evaluate(data, cfg, costs)

    print(f"{'':<16}{'start':>11}{'dev CAGR':>10}{'bench':>8}{'holdout':>9}{'bench':>8}"
          f"{'MaxDD':>8}{'bench':>8}{'rebal':>6}{'trades':>7}{'costs':>7}")
    new_log = not LOG.exists()
    with open(LOG, "a", newline="") as fh:
        w = csv.writer(fh)
        if new_log:
            w.writerow(["timestamp", "hypothesis", "variant", "start", "dev_cagr",
                        "bench_dev_cagr", "holdout_cagr", "bench_holdout_cagr",
                        "maxdd", "bench_maxdd", "dev_rebalances", "trades"])
        for (hyp, name), r in results.items():
            print(f"{hyp + ' ' + name:<16}{r['start'].date()!s:>11}{pct(r['dev']['cagr']):>10}"
                  f"{pct(r['dev_b']['cagr']):>8}{pct(r['hold']['cagr']):>9}"
                  f"{pct(r['hold_b']['cagr']):>8}{pct(r['full']['maxdd']):>8}"
                  f"{pct(r['full_b']['maxdd']):>8}{r['dev_rebalances']:>6}{r['trades']:>7}"
                  f"{r['cost_pct']:>7.1%}")
            w.writerow([dt.datetime.now().isoformat(timespec="seconds"), hyp, name,
                        r["start"].date(), round(r["dev"]["cagr"], 4),
                        round(r["dev_b"]["cagr"], 4), round(r["hold"]["cagr"], 4),
                        round(r["hold_b"]["cagr"], 4), round(r["full"]["maxdd"], 4),
                        round(r["full_b"]["maxdd"], 4), r["dev_rebalances"], r["trades"]])

    print("\nPre-registered criteria (all must hold):")
    for hyp, variants in HYPOTHESES.items():
        base = results[(hyp, "base")]
        neighbours = [results[(hyp, n)] for n, _ in variants if n != "base"]
        checks = [
            ("net CAGR beats benchmark in development",
             base["dev"]["cagr"] > base["dev_b"]["cagr"]),
            ("net CAGR beats benchmark in holdout",
             base["hold"]["cagr"] > base["hold_b"]["cagr"]),
            (f"max drawdown no more than {MAX_DD_GAP:.0%} worse than benchmark (full window)",
             base["full"]["maxdd"] >= base["full_b"]["maxdd"] - MAX_DD_GAP),
            ("every neighbour beats the benchmark in development",
             all(n["dev"]["cagr"] > n["dev_b"]["cagr"] for n in neighbours)),
            (f"at least {MIN_DEV_REBALANCES} development rebalances",
             base["dev_rebalances"] >= MIN_DEV_REBALANCES),
        ]
        print(f"\n{hyp}:")
        for text, ok in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {text}")
        verdict = all(ok for _, ok in checks)
        print(f"  => {hyp} {'PASSES: earns forward paper trading, not live money' if verdict else 'REJECTED'}")

    print("\nReminder: stock list and benchmark are today's Nifty 100 (survivorship bias, "
          "which favours momentum), the sample is about 4 years, and the holdout is "
          "partly seen. Record these results in RESEARCH_LOG.md and stop.")


if __name__ == "__main__":
    main()