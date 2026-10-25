# Research log and protocol

Written on 2026-10-25, BEFORE any of the tests below were run. Do not edit the
hypotheses or success criteria after seeing results; add new entries instead.

## Why this exists

Trial 0 (trend/breakout) lost to buy-and-hold. Every extra strategy tried on the same
data raises the chance that one looks good by luck. This file limits the number of
tries, fixes the pass/fail rules in advance, and counts every run.

## Rules

1. **At most two hypotheses (H1, H2).** Each runs once with the parameters written
   below. A third idea is a new trial, logged here, and makes the bar higher.
2. **Neighbour check:** each parameter is also run one step either side, and all of
   them are reported. Neighbours are for robustness, never for picking a winner.
3. **Development data:** everything up to 2025-10-23.
   **Holdout:** 2025-10-24 to 2026-10-23, looked at once, after development is done.
   Caveat: Trial 0 already showed this period (benchmark roughly flat, trend system
   weak), so it is only partly unseen. The only fully clean test is paper trading
   forward from today.
4. **Costs always on** (defaults in `costs.py`). No zero-cost headline numbers.
5. **Benchmark:** equal-weight buy-and-hold of the same stocks (also survivorship-biased).
6. **A hypothesis passes only if ALL of these hold:**
   - net CAGR beats the benchmark in the development period AND in the holdout;
   - max drawdown is no more than 5 points worse than the benchmark's;
   - every neighbour setting is also above the benchmark in development;
   - at least 40 monthly rebalances in the development period.
7. **If any criterion fails, the hypothesis is rejected.** No re-tuning, no "almost".
8. **A pass is not proof.** It earns a minimum of 3 months of forward paper trading
   before any real money is considered.
9. **Time box:** one weekend. If H1 and H2 are not both finished, the project closes
   as it stands.
10. **Stopping rule:** if both fail, update the README with both results and stop.

## Hypotheses

### H1: monthly cross-sectional momentum
Stocks that outperformed over the past year (skipping the most recent month) keep
outperforming over the next few months, and a monthly low-turnover version keeps
costs far below Trial 0's.
- Score: close(t-21) / close(t-252) - 1
- Hold the top 10 stocks, equal weight (10% each)
- Rebalance on the first trading day of each month, at the open
- Sell a holding only when it falls out of the top 20
- Neighbours: lookback 189 and 315 days; hold 8 and 12 stocks

### H2: H1 plus a breadth filter
H1 loses most in broad market downtrends. Moving to cash when the market is below
its long-term average cuts those drawdowns without losing the upside.
- Market proxy: equal-weight index of the same stocks (built from our own data)
- At each rebalance: if the proxy is below its 200-day average, hold cash
- Everything else as H1
- Neighbours: 150-day and 250-day average

## Trial log

| # | Date | Strategy | Runs | Result | Verdict |
|---|---|---|---|---|---|
| 0 | 2026-10-23 | 55/20-day trend breakout | 1 main + 27 grid | 12.5% CAGR vs 19.9% benchmark; 0 of 27 positive out-of-sample | Rejected |
| 1 | 2026-10-25 | H1 monthly momentum, top 10 of 94 | 5 (base + 4 neighbours) | Dev 43.9% vs 28.1% benchmark; holdout -15.2% vs -3.8%; max drawdown -25.1% vs -19.9% | Rejected: failed holdout and drawdown criteria |
| 2 | 2026-10-25 | H2 momentum + breadth filter | 3 (base + 2 neighbours) | Dev 34.4% vs 28.1%; holdout -15.6% vs -3.8%; max drawdown -25.1% vs -19.9% | Rejected: failed holdout and drawdown criteria |

Total runs so far: 36 (28 + 8).

## Amendments (made on 2026-10-25, before any H1/H2 run)

1. **Rule 6, fourth criterion: "at least 40 monthly rebalances" is now "at least 30".**
   My mistake. We only have data from 2021-10-25, and H1 needs 252 + 21 trading days
   of history before its first signal. That leaves about 35 development months for the
   base setting and fewer for the 315-day neighbour, so 40 could never have been met.
2. **Rule 6, second criterion (drawdown):** clarified to be measured over the full window
   (development plus holdout), on the same dates for strategy and benchmark.
3. **Neighbour check:** the benchmark is compared over each variant's own start date,
   because longer lookbacks start later.
4. **Mechanics fixed in code (rebalance_engine.py):** winners are not trimmed between
   rebalances; empty slots are filled from the highest-ranked stocks not held; scores use
   the last close before the rebalance day and trades fill at that day's open.

## Outcome (2026-10-25)

Both hypotheses failed the pre-registered criteria. Rule 10 applies: the project is closed.

- Both beat the benchmark in development, including every neighbouring setting, but lost
  to it by about 11 points in the holdout year and had deeper drawdowns.
- H2's market filter did not help: it gave up return in development (34.4% vs 43.9% for H1)
  and left the maximum drawdown unchanged at -25.1%.
- The development numbers are likely flattered by survivorship bias (today's index members)
  and are not evidence of an edge.
- Nothing was retuned after seeing results. Any further idea is Trial 3, and this data has
  no clean holdout left for it. Only forward paper trading would be a clean test, and
  nothing passed that earns it.