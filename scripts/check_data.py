"""Phase 1: sanity-check the downloaded candles. Run after download_daily.py.

Flags: missing trading days, huge one-day moves (possible unadjusted splits/bonuses),
zero-volume days, broken OHLC values, stale or short histories.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import config  # noqa: E402
import universe  # noqa: E402

BIG_MOVE = 0.20          # 20% close-to-close
MAX_MISSING = 3          # tolerated missing trading days
STALE_DAYS = 5


def main() -> None:
    files = sorted(universe.DAILY_DIR.glob("*.csv"))
    if not files:
        raise SystemExit("No data found. Run scripts/download_daily.py first.")

    frames = {f.stem: pd.read_csv(f, parse_dates=["date"]) for f in files}

    # Reference calendar: dates on which most stocks traded.
    counts = Counter(d for df in frames.values() for d in df["date"])
    threshold = 0.7 * len(frames)
    calendar = pd.DatetimeIndex(sorted(d for d, n in counts.items() if n >= threshold))
    newest = max(df["date"].max() for df in frames.values())

    rows = []
    for symbol, df in frames.items():
        df = df.sort_values("date").reset_index(drop=True)
        flags = []

        expected = calendar[(calendar >= df["date"].min()) & (calendar <= df["date"].max())]
        missing = expected.difference(pd.DatetimeIndex(df["date"]))
        if len(missing) > MAX_MISSING:
            flags.append(f"missing {len(missing)} days")

        ret = df["close"].pct_change()
        worst = ret.abs().idxmax() if ret.notna().any() else None
        max_move, max_move_date = 0.0, ""
        if worst is not None:
            max_move = float(ret.loc[worst])
            max_move_date = str(df.loc[worst, "date"].date())
            if abs(max_move) > BIG_MOVE:
                flags.append(f"move {max_move:+.0%} on {max_move_date}")

        zero_vol = int((df["volume"] == 0).sum())
        if zero_vol:
            flags.append(f"{zero_vol} zero-volume days")

        bad = int(((df[["open", "high", "low", "close"]] <= 0).any(axis=1)
                   | (df["low"] > df["high"])
                   | (df["close"] > df["high"]) | (df["close"] < df["low"])
                   | (df["open"] > df["high"]) | (df["open"] < df["low"])).sum())
        if bad:
            flags.append(f"{bad} bad OHLC rows")

        if (newest - df["date"].max()).days > STALE_DAYS:
            flags.append(f"stale (last {df['date'].max().date()})")

        rows.append({
            "symbol": symbol, "rows": len(df),
            "first": df["date"].min().date(), "last": df["date"].max().date(),
            "missing_days": len(missing), "biggest_move": round(max_move, 4),
            "biggest_move_date": max_move_date, "zero_volume_days": zero_vol,
            "bad_ohlc_rows": bad, "flags": "; ".join(flags),
        })

    report = pd.DataFrame(rows)
    out = config.DATA_DIR / "data_report.csv"
    report.to_csv(out, index=False)

    flagged = report[report["flags"] != ""]
    print(f"{len(report)} stocks checked, {len(flagged)} flagged. Full report: {out}\n")
    if len(flagged):
        print(flagged[["symbol", "rows", "flags"]].to_string(index=False))
        print(
            "\nA one-day move near -50%, -66%, -80% (or +100%) in a large stock usually "
            "means a split or bonus that is NOT adjusted in the data. Check each such "
            "stock's corporate actions before trusting any backtest on it."
        )


if __name__ == "__main__":
    main()