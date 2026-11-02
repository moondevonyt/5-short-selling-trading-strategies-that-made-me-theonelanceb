# Moon Dev notes, package 3: the bouncy ball short

Claim (TheOneLanceB, about 7:10): after a crash the bounces shrink like a ball losing energy. Short the failed
bounce, stop just above it. That beats chasing the crash. First pass (daily, 393 trades, -1.93% a trade) lost.

## Verdict: BETTER VERSION FOUND, on daily bars only. Intraday is busted.

Best knobs picked in sample (trades before 2024-07-01, highest t-stat with at least 100 trades, over Binance 15m,
1h, 4h and the Hyperliquid daily set): Hyperliquid daily, 123 alts, crash 20% under the 30 day high, 2 lower
swing highs with pivot width 5, second bounce at most 0.7x the first, 15 day time stop with the stop just above
the swing high. Costs: 4.5 bp fee and 10 bp slippage a side, real funding where we have it.

| window | trades | avg trade | t-stat | win rate | profit factor | symbols positive | 2x costs |
|---|---|---|---|---|---|---|---|
| in sample (2020-08 to 2024-06) | 580 | +2.30% | 3.19 | 43.6% | 1.40 | 68.6% | |
| out of sample (2024-07 to 2026-08) | 941 | +1.89% | 3.44 | 49.3% | 1.33 | 57.9% | +1.60% (t 2.92) |
| chase the crash, same knobs, out of sample | 2762 | -0.35% | -1.46 | 30.4% | 0.93 | 42.3% | |

Edge bar (OOS avg > 0, t >= 2, PF >= 1.2, 55%+ of symbols positive, positive at 2x costs): passed, just. Symbols
positive drops to 54.5% at 2x costs. Slippage slider OOS: 0 bp +2.09%, 10 bp +1.89%, 25 bp +1.59%. Avg trade hits
zero near 100 bp a side.

## Does intraday beat daily? No. It loses.

Best in sample pick per market, same knobs reported out of sample (ball vs chase):

| market | symbols | span | ball IS | ball OOS | chase OOS |
|---|---|---|---|---|---|
| Binance 15m | 16 | 2020 to 2026 | 138 trades, +1.28% | 33 trades, -3.16% (t -4.4) | 44 trades, -0.33% |
| Binance 1h | 16 | 2020 to 2026 | 148 trades, +1.52% | 56 trades, -1.56% (t -3.0) | 162 trades, -2.25% |
| Binance 4h | 16 | 2020 to 2026 | 536 trades, +0.92% | 394 trades, -0.38% (t -1.0) | 433 trades, +1.03% |
| Hyperliquid daily | 123 | 2020 to 2026 | 580 trades, +2.30% | 941 trades, +1.89% (t 3.4) | 2762 trades, -0.35% |
| Hyperliquid 15m (52 days, sanity) | 74 | Jul to Aug 2026 | no in sample | 988 trades, -0.28% (t -4.5) | 300 trades, -0.50% |
| Hyperliquid 4h (meme) | 22 | May 2024 to Aug 2026 | 12 trades | 1066 trades, +0.17% (t 0.7) | 931 trades, +0.06% |

Across every ball combo with 100+ out of sample trades: Binance 15m 0 of 384 combos positive, 1h 27%, 4h 40%,
Hyperliquid 15m 1%, Hyperliquid daily 85% (mean +2.37%), Hyperliquid 4h 89% (mean +0.82%, but tiny t-stats).
The intraday fail is the clean part of this result. His "I trade this mostly intraday" does not show up in crypto perps.

## What the knobs say (daily, OOS, combos with 100+ trades)
- Two bounces beat three: B=2 mean +3.03% (350 combos), B=3 mean +0.43% (120 combos). The third weaker bounce
  does NOT help. Fewer trades, worse trades.
- Decay R barely matters: 0.5 gives +2.53%, 0.7 gives +2.34%, 1.0 gives +2.30%. "Just lower" is enough.
- Exits: 3R +3.39%, crash low +2.79%, 2R +2.71%, time 40 +2.25%, ATR trail +2.31%, time 15 +0.92%. The in sample
  pick (time 15) is the weakest exit family out of sample, and still held. A target exit would have done better,
  but that is a hindsight pick, so it is not the headline.
- Bounce vs chase: on the same daily set chase was positive in 70% of combos out of sample too (mean +0.92%).
  Shorting alts in 2024 to 2026 paid by itself. The ball adds about +1.5% to +2.2% a trade on top of chase.

## Squeeze guard (his "violent counter trend rally" risk)
Each guard is judged on the subset of trades where it is known, before vs after, out of sample.
- Funding not negative at entry: daily best, 251 trades +0.82% to 179 trades +1.20% (lift +0.38%, under the 0.5%
  bar). Intraday best (Binance 4h, 3 bounces, 3R): 394 trades -0.38% to 269 trades +0.18% (lift +0.56%, that is an
  "improves" by the plan's rule, but the result is still not an edge: t 0.5 range, fails the bar).
- Short liquidation spike (top 10% of 1 hour forced_buy_usd, BTC ETH SOL XRP, 2024-06 to 2025-12): only 15 daily
  and 46 intraday trades fall inside the liq window on those four coins. Skipping the spikes changed nothing on
  daily, and 45 to 43 trades on 4h. Too few trades to say anything. The data is there, the setup just rarely
  fires on the big four.
- BTC under its 50 day SMA: hurts. Daily 941 trades +1.89% to 544 trades +1.36%. Intraday -0.38% to -0.46%.
  The best bounce shorts came while BTC was still above its average and alts bled anyway.
- All three together: 0 daily trades, 18 intraday trades. Not a usable filter set.

## Caveats, read these
1. Funding: 95 of the 123 daily coins have no local Hyperliquid funding file, so those trades carry no funding.
   The public endpoint would need about 5,000 calls for 3 years of hourly funding and rate limited us, so it was
   not pulled for the daily set. On the 28 coins with funding, funding added +0.03% a trade in sample and about
   0.00% out of sample, so the missing piece is small. Those same 28 coins made +0.76% a trade OOS (255 trades,
   t 0.68), weaker than the full set, mostly because the meme coins in that group bounced harder.
2. Years are lumpy: 2022 +5.1%, 2023 -1.8%, 2024 -0.5%, 2025 +5.1%, 2026 +1.0%. This pays in alt bear years and
   bleeds in the others. 1,521 trades across 123 coins, 2 to 3 days of overlap between trades is common, so the
   t-stat overstates the independence a bit.
3. On daily bars "30 bars" and "30 days" are the same window, so each daily combo appears twice in the grid.
4. Engine: a vectorized numpy bar walker, not backtesting.py, because the grid is 912 combos per market on multi
   year 15m bars (5,472 grid rows in all). Entries at the next open, stop fills at the stop price or the gap open,
   a bar that touches both the stop and the target counts as the stop, no overlapping trades on one symbol.
   The chase stop is entry x (1 + 0.375 D), the same ratio as the first pass (15% for a 40% crash).
5. Equity curves: equal weight, each symbol gets 1/n of the capital, trades marked at the exit day.

## Failed parts
- Stocks side check (Yahoo hourly on IWM names that fell 40%+ in 30 days): the iShares and BlackRock holdings CSV
  endpoints returned HTML, the FTSE Russell PDFs 404, Vanguard VTWO 404. No universe, so no run. The script
  `moon_dev_stock_side_check.py` is ready and will run from a local `data_cache/IWM_holdings.csv` when one is
  dropped in. `stock_side_check.json` records the failure. Survivorship (today's list) would apply anyway.
- Daily funding for 95 coins, see caveat 1.
- The 1000PEPEUSDT Binance folder on the drive was being written by another agent during this run, so the Binance
  set is pinned to the 16 symbols the plan names.

## Data used (real only)
- Binance USDT perp 1m klines, `/Volumes/Moon 26/tick_data/binance/futures_klines_1m/<SYM>/<SYM>_1m_<start>_<end>.parquet`,
  16 symbols, resampled to 15m, 1h, 4h, 1d (cache in `data_cache/`, gitignored).
- Binance funding: local `/Volumes/Moon 26/tick_data/binance/funding/` for BTC ETH SOL XRP DOGE, public
  `fapi.binance.com/fapi/v1/fundingRate` (no key) for the other 11.
- Hyperliquid 15m (74 coins), 4h meme (22), daily (123, the first pass loader `backtests/moon_dev_common.py`).
- Hyperliquid funding: local midcap and meme files (28 coins), public `api.hyperliquid.xyz/info fundingHistory`
  (no key) for the 15m and 4h coins without a file.
- Liquidations: `data/moondev_api/liq_clean_{BTC,ETH,SOL,XRP}_5m.csv`, forced_buy_usd only, coin margin suspect
  bars dropped, raw liq prices never used as price.
- No API key was needed. Nothing from `.env` was read.

## Files
- `moon_dev_bouncy_data.py` loaders, `moon_dev_bouncy_ball_edge.py` signals, simulator, grid (run it with market
  names as arguments, or none for all six), `moon_dev_bouncy_report.py` picks the best knobs and writes
  `result.json`, `moon_dev_stock_side_check.py` the stock side check.
