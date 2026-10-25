# Indian Equity Backtesting Pipeline (Angel One SmartAPI)

A Python pipeline that downloads daily candles for the Nifty 100 from Angel One's SmartAPI,
validates the data, and backtests a swing-trading strategy with realistic Indian delivery
costs. **It is a research and engineering project. It does not trade, and the strategy it
tests did not beat buy-and-hold.** The result is reported honestly below.

> Not financial advice. Nothing here is a recommendation to buy or sell anything.

## Result

Strategy: long-only trend and breakout system on daily candles, fixed in advance
(rules in `strategy.py`). Universe: 94 Nifty 100 stocks (today's constituents). Trading
period: 2022-08-11 to 2026-10-23, split at 2024-09-17. Results are before tax.

| Period | Strategy CAGR | Max drawdown | Benchmark CAGR | Benchmark max drawdown |
|---|---|---|---|---|
| Full | 12.5% | -25.2% | 19.9% | -19.9% |
| First half | 38.0% | -18.9% | 43.3% | -11.1% |
| Second half | -8.3% | -25.2% | 0.3% | -19.9% |

The benchmark is an equal-weight, daily-rebalanced buy-and-hold of the same stocks.

- 222 closed trades, 39% win rate, profit factor 1.50, average hold 62 days.
- Fees, taxes and slippage cost roughly 15.8% of starting capital over the period.
- The five best trades made 88% of total profit, so the result depends on very few trades.
- A 27-setting sensitivity grid (entry 40/55/70, exit 10/20/30, stop 2/3/4 x ATR): every
  setting earned less than the benchmark over the full period (best 16.7% vs 19.9%), and
  none made money in the second half.

Conclusion: no edge was demonstrated. The strategy trailed buy-and-hold in both halves of the
data, so this is not just an overfitting or regime story. It was not taken to live trading.

## Follow-up: pre-registered momentum tests

After the trend strategy failed, two more hypotheses were written down in
`RESEARCH_LOG.md` before being run: monthly momentum (top 10 of 94 stocks), and the same
with a market-breadth cash filter. The log fixed the pass/fail criteria, a development
period (to 2025-10-23) and a holdout (the following year). Each ran once, and every run
is recorded in `research_runs.csv`.

| | Dev CAGR | Benchmark | Holdout | Benchmark | Max drawdown | Benchmark |
|---|---|---|---|---|---|---|
| H1 momentum | 43.9% | 28.1% | -15.2% | -3.8% | -25.1% | -19.9% |
| H2 momentum + filter | 34.4% | 28.1% | -15.6% | -3.8% | -25.1% | -19.9% |

Both were rejected. They beat the benchmark in development, including every neighbouring
setting, but lost to it in the holdout year and had deeper drawdowns. The development
figures are likely flattered by survivorship bias and should not be read as an edge. One
criterion (minimum number of rebalances, 40 to 30) was amended before any run because the
original could not be met with 5 years of data; the amendment is recorded in the log.

## Method

- **Data:** about 5 years of daily candles per stock from Angel One SmartAPI, fetched
  incrementally with retry and backoff (Angel's candle endpoint rate-limits aggressively).
- **Data checks** (`scripts/check_data.py`): missing trading days, one-day moves above 20%
  (possible unadjusted splits or bonuses), zero-volume days, broken OHLC rows. No
  split-sized jumps were found. Adjustment was not independently verified.
- **Strategy** (`strategy.py`): buy when the close is above the previous 55-day high and
  above the 200-day average; sell when the close falls below the previous 20-day low; fixed
  stop at 3 x ATR(20); risk 1% of equity per trade; at most 10 positions of 10%.
- **No look-ahead:** signals use the close of day t and orders fill at the open of day t+1.
  A stop that is gapped through fills at the open, not at the stop price.
- **Costs** (`costs.py`): STT 0.1% each side, stamp duty, exchange and SEBI charges, GST,
  DP charges, brokerage, plus an assumed 0.10% slippage per side. Rates were checked against
  published fee pages in October 2026 and should be compared with a real contract note.
- **Validation:** one chronological in-sample / out-of-sample split with parameters fixed
  beforehand (not walk-forward optimisation), plus the parameter sensitivity grid.
- **Engine tests:** hand-calculated scenarios (next-open fills, gap-through-stop exits,
  channel exits, fee arithmetic), a check that signals do not change when future data is
  removed, and an accounting check that final equity equals capital plus closed-trade P&L.

## Limitations

- **Survivorship bias:** the stock list and the benchmark both use today's Nifty 100, so
  stocks that fell out of the index are missing. This flatters both.
- **Short sample:** about 4 years of trading, mostly a rising market.
- **Single data source:** Angel One's candles; no cross-check against another vendor.
- **Taxes are not modelled.**
- **Slippage is an assumption,** not a measurement.
- The second-half result has been seen once and should not be reused for further tuning.

## Layout

```
broker.py        Angel One login (auto TOTP), instrument lookup, candle fetch with retry
config.py        loads secrets from .env
universe.py      Nifty 100 list (cached) and per-stock file paths
data_loader.py   loads candles, repairs tiny OHLC inconsistencies, filters short histories
strategy.py      indicators and rules, with the written hypothesis
costs.py         delivery cost and slippage model
engine.py        portfolio backtest engine (trend strategy)
rebalance_engine.py  monthly-rebalance engine (momentum hypotheses)
report.py        performance metrics and benchmark
notify.py        Telegram alerts
scripts/
  test_login.py, test_candles.py, test_telegram.py   connectivity checks
  download_daily.py   incremental download for the whole universe
  check_data.py       data quality report
  run_backtest.py     full backtest report
  sensitivity.py      parameter robustness grid
  run_research.py     pre-registered momentum tests (no parameters, runs logged)
RESEARCH_LOG.md  protocol, pre-registered hypotheses, trial log, outcome
```

## Setup

Requires Python 3.9 or newer, an Angel One account, and a SmartAPI app.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root (it is git-ignored; never commit it):

| Variable | Meaning |
|---|---|
| `ANGEL_API_KEY` | API key of your SmartAPI app |
| `ANGEL_CLIENT_CODE` | Angel One client ID |
| `ANGEL_PIN` | the PIN the API login asks for |
| `ANGEL_TOTP_SECRET` | secret from SmartAPI's enable-TOTP page |
| `TELEGRAM_BOT_TOKEN` | token from BotFather |
| `TELEGRAM_CHAT_ID` | your numeric chat ID |

## Run

```
python scripts/test_login.py
python scripts/test_candles.py
python scripts/download_daily.py --limit 5      # try a few first
python scripts/download_daily.py                # full universe, resumable
python scripts/check_data.py
python scripts/run_backtest.py
python scripts/sensitivity.py
```

## Notes on Angel One SmartAPI

- The candle endpoint frequently returns "Access denied because of exceeding access rate",
  even at low request rates. The downloader retries with backoff and can be rerun safely.
- Since April 2026, orders placed through broker APIs require a registered static IP and a
  daily 2FA login. This project only reads data and never places orders.

## Status

Data pipeline and both backtesters: done and tested. Three strategies tested (one trend,
two momentum); none beat buy-and-hold under the rules fixed in advance. Live trading was
deliberately not built. The project is closed.