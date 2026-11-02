# Moon Dev notes: Package 1, Right side of the V

Video: TheOneLanceB, about 2:40 to 4:40. "Wait for the turn: a lower high, a failed reclaim. Later with better
confirmation is a good trade off." The first pass lost (677 trades, -1.19% a trade) but beat calling the top.
This package asked one thing: is there a version with a real edge?

## Verdict: NOT PROVEN (passes the plan's edge bar, fails the regime check)

The best version found: Hyperliquid daily, run = high is 1.5x the 10 day low, short the next open after a close
breaks the lower high's low under the 10 EMA, stop above the lower high, take profit at 2R, 60 bar cap.
Fees 4.5 bp a side, slippage 10 bp a side, real funding every bar held.

| Window | Funded trades | Avg trade | Median | t-stat | Win rate | Profit factor | Coins positive |
|---|---|---|---|---|---|---|---|
| In sample (before 2024-07-01) | 59 | +3.53% | -9.65% | 1.08 | 39.0% | 1.39 | 55% |
| Out of sample (after) | 294 | +3.98% | -8.73% | 2.61 | 42.9% | 1.43 | 68% |
| Out of sample at 2x costs | 294 | +3.80% | | 2.48 | | 1.40 | |

Out of sample portfolio (equal weight, flat days 0): +35.8%, Sharpe 0.84, max drawdown -14.9%, while buy and
hold on the same coins was -48.4%.

Why it is still NOT PROVEN:
- Knobs were picked on in sample, where the best t-stat of any combo with 100+ trades was only 0.59 (all trades,
  funding where known). Nothing was good before mid 2024. The out of sample number is the first time it worked.
- The regime check: a blind short of the same coins held the same 17 bars made +1.08% a trade out of sample. The
  rule made +2.89% more than that, but t-stat 1.89 (under 2), and only 43% of trades beat the blind short. The
  average is carried by a fat right tail (median trade -8.7%, average +4.0%). 2024 to 2025 was alts bleeding.
- 2026 so far: 54 trades, -0.15% a trade.

## His main point holds: lower high break beats calling the top

Hyperliquid daily, his base knobs (K=2, N=30, close over 10 EMA exit), funded trades, out of sample:

| Entry | Trades | Avg trade | t-stat |
|---|---|---|---|
| Lower high break (his rule) | 191 | +0.37% | 0.35 |
| Call the top (first red bar) | 262 | -0.85% | -1.08 |
| 10 EMA cross, no lower high | 213 | -3.66% | -3.34 |

Same order on 8h, 4h and 1h, but all three lose there. Waiting for the turn costs less than guessing the top.
That is the one part of the claim the data backs every time.

## Was the first pass's late +0.91% real?

No. With real funding charged, the base rule after 2024-07-01 made +0.37% a trade (191 funded trades, t 0.35),
and the first pass's second half of trades drops from +0.91% to +0.06% on funded trades (134 trades, 53% of
coins positive). A blind 8 day short of the same coins made +0.08% in that period. The late "edge" was the alt
bear regime plus the missing funding cost.

## What moved the needle in the grid (672 combos, 4 markets)

- Exit is everything. By exit, out of sample avg trade across all combos with 30+ trades: 2R target +1.89%,
  3R +1.55%, 30 bar time stop +0.45%, ATR trail -0.97%, 20 EMA -1.26%, 10 bar time stop -2.13%, 10 EMA -2.84%.
  His "close over the 10 EMA" exit is the worst one. It covers on the first green day, which is exactly the
  bounce that then fails.
- Entry: lower high break wins on daily for every K and N. Call the top and the EMA cross lose.
- Timeframe (best knobs): daily +3.98% (t 2.61), 8h +1.83% (t 1.25), 4h -0.89%, 1h -3.89% (t -3.17). The
  intraday version does not work on crypto. Fees and funding eat the smaller moves.
- Run size K: 1.5x and 2x give trades. 3x and 5x give 10 to 70 trades, too few to say anything, though
  K=2 N=30 with the 2R target made +9.2% a trade out of sample on 178 trades (t 4.8). Its in sample was
  -0.08% on 300 trades. Same story: only works after mid 2024.

## Filters (on the best version)

| Filter | In sample trades, avg | Out of sample trades, avg, t-stat, coins positive |
|---|---|---|
| none | 59, +3.53% | 294, +3.98%, 2.61, 68% |
| BTC under its 50 day SMA | 20, +1.96% | 134, +1.98%, 0.95, 63% |
| Funding above its 30 day median | 21, +10.40% | 93, +1.75%, 0.65, 47% |
| Lower high bar volume under half the peak bar | 30, +5.84% | 179, +4.66%, 2.55, 75% |
| Lower high forms within 3 bars of the peak | 22, +4.61% | 129, +8.39%, 3.49, 81% |
| within 5 bars | 39, +1.86% | 202, +5.78%, 3.04, 78% |
| within 10 bars | 52, +5.01% | 270, +4.23%, 2.64, 76% |
| Pair: funding + volume (best two in sample) | 9, +12.39% | 50, -0.82%, -0.27, 42% |

The one that looks real: a lower high that forms fast (within 3 bars of the peak) lifts the out of sample avg by
+4.4% on 129 trades, 81% of coins positive. It fits his story (a sharp break right after the top). But it was
picked by looking at out of sample, so it is the next test, not a result. The BTC regime and crowded funding
filters, the two "smart" ones, both cut the edge in half. The best pair in sample was the worst out of sample.
Classic overfit.

## Costs

Slippage slider (out of sample avg trade): 0 bp +4.23%, 10 bp +3.98%, 25 bp +3.77%, 50 bp +3.09%. It never
crosses zero inside the grid; the trades are big enough (17 bars held) that costs are not the problem. Funding
paid the short +0.03% a trade on average out of sample, +0.91% in sample.

## Stocks side check: did not run

iShares serves its IWM holdings CSV behind a bot wall (every URL and header combo returned the HTML product page
to a script, twice). There is no local Russell 2000 list in the repo. `fetch_stocks.py` is ready: save the CSV by
hand from the IWM product page to `data_cache/IWM_holdings.csv`, run it, then `run_grid.py` again. The stock grid
(K 2x and 3x, borrow 5%, 25%, 100% a year as a labeled grid, survivorship from today's list) is wired in
`run_grid.py` and will show up in `result.json` under `stocks_side_check`.

## Data used (all real, nothing filled)

- Hyperliquid daily: 123 coins (midcap + meme folders, the first pass loader), 2020 to Aug 2026.
- Hyperliquid 8h: 117 coins from June 2022. Hyperliquid 4h: 22 meme coins from Jan 2025.
- Binance USDT perp 1m from the Moon 26 drive, resampled to 1h: 16 majors plus 15 meme perps pulled fresh with
  `binance_1m_klines_to_moon26.py` (1000PEPE, WIF, 1000BONK, 1000FLOKI, 1000SHIB, PNUT, POPCAT, MOODENG, TRUMP,
  FARTCOIN, BOME, GOAT, ACT, PENGU, TURBO). All 15 downloaded and checksum passed. 31 symbols in all.
- Funding: 28 local Hyperliquid files, 5 local Binance files, 26 Binance symbols pulled from the public
  fapi fundingRate endpoint (all complete), and the public Hyperliquid fundingHistory endpoint for the rest.
- A coin with no funding data is tagged, never charged zero. Its trades are reported apart
  (`no_funding_trades`, `no_funding_avg_trade_pct`) and never count toward a headline number.

## Gaps, said plainly

- Hyperliquid funding coverage. The public endpoint allows about 1 call a second and sends 500 hourly rates a
  call, so 97 coins take over an hour. When `run_grid.py` ran, 84 of 123 daily coins and 85 of 117 8h coins had
  no funding file. `fetch_funding.py` keeps running in the background and caches to `data_cache/hl_funding/`.
  Rerun `run_grid.py` after it finishes and every number above gets a bigger funded sample. The untagged trades
  point the same way (out of sample +4.73% a trade on 458 trades without funding vs +3.98% with), so the sign
  should hold, but the headline will move.
- Stocks: see above.
- Hyperliquid 4h is only 22 meme coins from 2025, so it has no in sample at all. 1h on Binance has only 31 coins
  and most of them are majors, not pumpers.
- The in sample side is thin everywhere because Hyperliquid funding history only starts mid 2022 and most
  coins listed in 2024 or later.

## Bot

`bot.py` is a dry run Hyperliquid short bot for the best version (K=1.5, N=10, lower high break, stop above the
lower high, 2R take profit, 60 bar cap). `LIVE = False`. It reads `HYPER_LIQUID_KEY` from the main repo `.env` via
dotenv, never prints it, and holds no wallet address. Marked NOT PROVEN at the top with the real backtest line.

## Files

- `engine.py`: the numba walk forward simulator, loaders, funding per bar, stats, the regime check.
- `run_grid.py`: the grid, filters, cost slider, hold out, side by side, stocks, writes `result.json`.
- `fetch_funding.py`: Hyperliquid and Binance public funding pulls to `data_cache/` (gitignored).
- `fetch_stocks.py`: IWM list plus Yahoo daily (needs the hand saved CSV).
- `result.json`: every number above comes from `run_grid.py` (run 2, 538 seconds).
