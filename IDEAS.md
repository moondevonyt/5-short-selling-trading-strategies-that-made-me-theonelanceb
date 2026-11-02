# Moon Dev's ideas from 5 Short Selling Trading Strategies That Made Me Millions

Cooked up live while watching TheOneLanceB: https://www.youtube.com/watch?v=SvHhoD00jZI

## Ranked ideas (for the edge finder)

The video gives 5 short setups. All 5 share one idea: more supply than demand. Below they are ranked by how
testable they are and how close the first backtest came. First round numbers are in `backtests/RESULTS.md`.

### TOP 1: Right side of the V short (strategies 1 and 2, about 2:40 to 4:40)
- Market: Hyperliquid perps (alts and meme coins). Also fits small cap stocks.
- Timeframe: daily now. Next: 4h and 1h.
- Setup: the high is 2x the lowest low of the last 30 days (a 100%+ run).
- Entry: after the peak, a green day makes a lower high. Short when a later close breaks under that day's low and is under the 10 EMA.
- Stop: just above the lower high.
- Exit: close back above the 10 EMA, or 30 days.
- First result: 677 trades, -1.19% a trade, FAIL. But it beat "call the top" (-1.83% a trade). Last half of trades +0.91% a trade.
- Next tests: 4h bars, a bigger run filter (3x), include funding, add a trailing stop instead of the EMA exit.

### TOP 2: Short the IPO lockup expiry (strategy 5, about 8:30 to 10:30)
- Market: US stocks, hot IPOs with a normal 180 day lockup.
- Timeframe: daily.
- Entry: short at the open 2 days before the lockup day (IPO day + 180 calendar days).
- Exit: cover at the open 2 days after the lockup day.
- First result: 55 trades, -0.53% a trade, FAIL. 2019 to mid 2021 was +1.99% a trade, since then -2.97%.
- Next tests: real lockup dates (staged and early releases), enter earlier (day -10) to front run the crowd,
  only trade when the insider gain is big and new shares are large vs daily volume (his own filters),
  and the flip side: go LONG after day 0 when it gaps down and holds (his SpaceX example).

### TOP 3: Bouncy ball short (strategy 4, about 7:10 to 8:20)
- Market: Hyperliquid perps.
- Timeframe: daily now. Next: 1h and 4h (the pattern is usually intraday in stocks).
- Setup: close is 40%+ under the 30 day high.
- Entry: the last 3 swing highs are each lower, and the newest bounce is smaller than the one before. Short when that swing high is confirmed (2 bars later).
- Stop: just above that swing high. Target: 2R. Time stop: 15 bars.
- First result: 393 trades, -1.93% a trade, FAIL. Still better than chasing the crash (-2.22% a trade, 1378 trades).
- Next tests: intraday bars, a 3rd weaker bounce, a target at the crash low instead of 2R.

### 4: Microcap backside short (strategy 1)
- Market: US small caps that run 50% to 100%+ in a day. Needs a gapper list (not in our data yet).
- Entry: first lower high after the day's top, short the break of its low. Stop above the lower high.
- Exit: end of day or VWAP reclaim.

### 5: Offering short (strategy 3, about 5:00 to 7:00)
- Market: US small caps that announce a stock offering after a spike.
- Entry: short when price rallies toward the offering price and fails. Stop above the offering price.
- Needs an offerings data feed (SEC 424B filings). Not tested yet.

## BS check
- "$100M in verified profits": no proof shown in the video.
- CAR short story: no entry, stop or size given.
- The 3,200 lockup study: no name given. Our check found the volume jump, not the -1.8%.
- BYND -20% on Oct 29 2019: TRUE (-22.2%).

## Live ideas
