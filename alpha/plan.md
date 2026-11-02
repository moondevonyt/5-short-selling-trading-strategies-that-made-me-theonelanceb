# Moon Dev Edge Finder plan: 5 Short Selling Trading Strategies That Made Me Millions

Video: TheOneLanceB, https://www.youtube.com/watch?v=SvHhoD00jZI (all credit to him).
Built by Moon Dev. Exactly 3 packages, the 3 top ideas from `IDEAS.md`.

The first pass (`backtests/RESULTS.md`) already lost on all three:
- Right side of the V: 677 trades, -1.19% a trade (but beat "call the top" at -1.83%, and the last half of trades was +0.91%).
- Bouncy ball: 393 trades, -1.93% a trade (but beat "chase the crash" at -2.22%).
- Lockup expiry: 55 trades, -0.53% a trade (+1.99% in 2019 to mid 2021, -2.97% since).

So these packages do NOT repeat that test. The one question for each: is there a version of the idea with a real edge?
Change the filters, the market, the timeframe, the timing. Put every real cost in (fees, slippage, funding, borrow).

## Rules for every test agent

- Real data only. If a file or API is not there, fail loudly and write that into `notes.md`. Never fill a gap.
- Public repo. No keys, no `.env` contents, no wallet addresses anywhere in this folder. Load `MOONDEV_API_KEY`
  with `dotenv` from `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/.env` and never print it.
- Put "Moon Dev" in prints and comments. No em dashes or double dashes in any text you write.
- Reuse `backtests/moon_dev_common.py` (loader, equal weight portfolio, trade table) where it fits.
- backtesting.py: size with a fraction (0.95), never a big integer. Fees: 4.5 bp a side (Hyperliquid taker) unless the
  package says more.
- Hold out data. Pick the best knobs on the first part of history (in sample), then report the SAME knobs on the
  last part (out of sample). The headline number is always the out of sample one.
- The "edge" bar (what proves it): avg trade net of all costs > 0 with t-stat >= 2, profit factor >= 1.2, positive
  out of sample, positive on at least 55% of symbols that traded, and still positive at 2x costs.
  Anything short of that is "not proven". Say so plainly.
- About 30 minutes. If a grid is too big, cut the grid, not the cost model.

### result.json (same shape for all 3, so the dashboard can read them)
```
{
  "package": "1_right_side_v", "title": "...", "claim": "...", "claim_time": "3:00",
  "verdict": "VERIFIED | BUSTED | BETTER VERSION FOUND | NOT PROVEN",
  "headline": {"label": "...", "value": 0.0, "unit": "%"},
  "first_pass": {"trades": 677, "avg_trade_pct": -1.19},
  "best": {"params": {}, "in_sample": {...stats}, "out_of_sample": {...stats}},
  "stats keys": "trades, avg_trade_pct, median_trade_pct, t_stat, win_rate, profit_factor, total_return_pct,
                 sharpe, max_dd_pct, buy_hold_return_pct",
  "equity_curve": [{"t": "2024-01-01", "strategy": 1.0, "buy_hold": 1.0}],
  "trades": [{"symbol": "", "entry_time": "", "exit_time": "", "entry": 0, "exit": 0, "ret_pct": 0, "reason": ""}],
  "grid": [{"params": {...}, "trades": 0, "avg_trade_pct": 0, "t_stat": 0, "profit_factor": 0, "total_return_pct": 0}],
  "cost_curve": [{"cost_bp_per_side": 0, "avg_trade_pct": 0}],
  "by_year": [{"year": 2021, "trades": 0, "avg_trade_pct": 0}],
  "by_market": [{"market": "HL daily", "trades": 0, "avg_trade_pct": 0}],
  "replay": {"symbol": "", "bars": [{"t": "", "o": 0, "h": 0, "l": 0, "c": 0}], "trades": [...]},
  "data_used": ["exact paths and APIs"], "failed_parts": ["anything that could not run and why"]
}
```
Keep `trades` to the best version only (cap 2,000 rows), `replay` to one real example with about 200 bars around
2 to 5 real trades, and `grid` to every combo that ran. Every number must come from a run.


## Package 1: Right side of the V, find the version that pays

**Claim (about 2:40 to 4:40).** "Shorting an upside capitulation on what I call the right side of the V." Wait for
the turn: "a sharp break of the uptrend, a failed attempt to reclaim highs, or a lower high can give you something
concrete to risk against. And being later with better confirmation is often a very good trade-off." Also
(about 1:50): microcaps can move "50 or 100 percent, even hundreds of percent" in a day, and you short "the
backside of the move."

**What the first pass left open.** It only ran daily bars, one run size (2x the 30 day low), one exit (close over the
10 EMA). No funding. The last half of trades was +0.91% a trade. Was that a regime (alts bleeding in 2024 to 2026)
or a real edge?

**The test.**
1. Rebuild the base rule: run = high is at least K x the lowest low of the last N bars. After the peak, wait for a
   lower high (a bounce that fails under the peak). Short when a close breaks the low of the lower high bar and is
   under the 10 EMA. Stop just above the lower high. Short the next bar's open.
2. Grid (each combo runs on every market below):
   - run size K: 1.5x, 2x, 3x, 5x. Base window N: 10, 30 bars.
   - entry: lower high break (his rule) vs first red bar at the top (the "call the top" baseline) vs close under
     the 10 EMA with no lower high.
   - exit: close over 10 EMA, close over 20 EMA, ATR(14) x 3 trailing stop, fixed 2R and 3R targets, time stop
     10 / 30 bars.
3. Filters (one at a time on the best base, then the best pair):
   - BTC regime: BTC close under its 50 day SMA (shorting alts when the tide is out).
   - Crowded longs: funding at entry above its 30 day median (shorts get paid, longs are trapped).
   - Volume dry up: volume on the lower high bar under half the peak bar's volume.
   - Time since peak: lower high forms within 3, 5, 10 bars of the peak.
4. Costs: fees 4.5 bp a side, slippage grid 0, 10, 25, 50 bp a side, and REAL funding paid or earned each bar held
   (shorts receive when funding is positive). Show the cost slider: where does the avg trade go to zero?
5. Out of sample: pick knobs on trades before 2024-07-01, report the same knobs after.

**Markets and timeframes (the data to use).**
- Hyperliquid daily: `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_midcap/*_1d_hl.csv` and
  `.../data/hyperliquid_meme/*_1d_hl.csv` (same loader as the first pass, 123 coins).
- Hyperliquid 8h: `.../data/hyperliquid_8h/*_8h_hl.csv` (117 coins, back to 2022).
- Hyperliquid 4h: `.../data/hyperliquid_meme/*_4h_hl.csv` (22 meme coins).
- 1h: resample Binance USDT perp 1m klines from `/Volumes/Moon 26/tick_data/binance/futures_klines_1m/<SYM>/`
  (16 symbols, the all-in-one `<SYM>_1m_<start>_<end>.parquet`). Pumpers are what we want, so also pull up to
  15 meme perps (PEPE, WIF, BONK, FLOKI, SHIB style names that list on Binance futures) with
  `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/binance_1m_klines_to_moon26.py <SYMBOL>`. If the
  download fails, run on the 16 and say so.
- Funding: Hyperliquid `.../data/hyperliquid_funding/*_funding_hl.csv` and `.../data/hyperliquid_meme/*_funding_hl.csv`;
  for coins with no local file, pull the public Hyperliquid `fundingHistory` info endpoint (no key needed).
  Binance funding: `/Volumes/Moon 26/tick_data/binance/funding/`. Any coin with no funding gets tagged
  "no funding data" and is reported separately, not silently charged zero.
- Stocks (side check, his home market): Yahoo daily (yfinance) on the current iShares IWM holdings list. Same rule
  with K = 2x, 3x. Add a borrow cost grid of 5%, 25%, 100% a year (we have no real borrow feed, so it is a grid,
  labeled as such). Note survivorship (today's list) in notes.md.

**What proves, breaks, or improves it.** Proves: a combo passes the edge bar out of sample on crypto. Breaks: no combo
beats zero after funding and 10 bp slippage. Improves: any filter that lifts the out of sample avg trade by 0.5% or
more with at least 100 trades. Always report "lower high break vs call the top" side by side, since that is his main
point and the first pass backed it.

**Bot (this package also carries the bot example).** Write `bot.py`: a small, clean Hyperliquid short bot for the
best version found (or his base rule if nothing passes, marked NOT PROVEN at the top). Loop: pull candles, find the
run and the lower high, place the short with the stop above the lower high, manage the exit. Read keys only from
env via dotenv, never print them, no wallet addresses in the file. Dry run by default (`LIVE = False`). Put its real
backtest line in a comment at the top.

**Output.** `alpha/1_right_side_v/` with the code, `bot.py`, `result.json`, `notes.md`.


## Package 2: IPO lockup expiry, real dates, the full event curve, and the flip side

**Claim (about 8:30 to 10:30).** A study of "more than 3,200 IPO lockup agreements found that the average trading
volume increased roughly 40% during the expiration week and documented a cumulative abnormal return of approximately
negative 1.8%." BYND "fell more than 20% on the expiration day" (Oct 29 2019, first pass: TRUE, -22.2%). Filters he
names: the insider's gain since IPO ("a massive 500% gain"), and new supply "relative to the existing float and normal
trading volume." Warnings: "other traders can front run the event," and "sometimes the stock actually rallies when
the lockup expires" (his SpaceX example: gapped down, then rallied).

**What the first pass left open.** 55 hand picked IPOs, a guessed lockup date (IPO + 180 days), one window (day -2 to
day +2), no market hedge, no borrow cost. Buy and hold on that set was deeply negative, so part of any short "win" may
just be the IPO drift down, not the lockup.

**The test.**
1. Bigger, real universe: every US operating company IPO 2015 to 2025 found in SEC EDGAR form `424B4` filings
   (quarterly `form.idx` from `https://www.sec.gov/Archives/edgar/full-index/`, free, set a User-Agent with
   "Moon Dev research" and an email from the env, not hard coded, max 10 requests a second). Drop SPACs (names with
   "Acquisition" and SIC 6770), ADRs with no lockup, and direct listings.
2. Real lockup length: from each 424B4 text, parse the lockup period ("180 days", "90 days", staged releases).
   If it cannot be parsed, fall back to 180 days and flag the row `lockup_guessed = true`. Report results for parsed
   only and for all. Also parse shares outstanding after the offering and shares offered, so locked shares =
   outstanding minus offered.
3. Prices: Yahoo daily (yfinance) for each IPO ticker plus IWM and SPY. Cache to `alpha/2_lockup/data_cache/`
   (prices are public, fine to commit; if size is over 20 MB, gitignore it).
4. The event study first: average abnormal return vs IWM for every day from -30 to +20 around day 0, plus the
   volume ratio (week of day 0 vs the 20 days before). This checks the -1.8% and the 40% directly.
5. Window grid for the short (IWM hedged and unhedged): entry day -20, -10, -5, -2, -1, 0 (open); exit day 0
   (close), +1, +2, +5, +10. This shows if the move got front run (the edge moved earlier).
6. His filters: gain since IPO price (under 0%, 0 to 100%, 100 to 300%, over 300%), locked shares divided by the 20 day
   average volume (terciles), run into the lockup (day -20 to -2 return up vs down), market cap tercile.
7. The flip side (his SpaceX point): go LONG at the day 0 close when day 0 gapped down at the open and closed over
   its open; hold +1, +3, +5, +10 days.
8. Costs: fees 4.5 bp a side, slippage 10 bp a side, borrow grid 0%, 10%, 30%, 100% a year charged on days held
   (no real borrow feed, so it is a grid and labeled as one).
9. Time split: 2015 to mid 2021 vs mid 2021 to 2025 (the first pass saw the edge die). Report both always.

**Data to use.** SEC EDGAR full-index and filing text (public), Yahoo daily via yfinance. No API key needed.
If EDGAR blocks or the parse yields under 150 IPOs, fall back to the first pass list in
`backtests/lockup_expiry_short.py` plus any IPOs added by hand from EDGAR, and say so in `notes.md`.

**What proves, breaks, or improves it.** Verifies the study: abnormal return over the expiry week near -1.8% with
t-stat >= 2. Busts it: near zero or positive in 2021 to 2025. Better version: a window or filter (likely earlier entry,
or big gain plus big locked supply) that passes the edge bar after borrow at 10% a year, out of sample in the later
period. If the long flip beats the short, say that loud.

**Output.** `alpha/2_lockup/` with the code, `result.json` (add `event_curve`: day, avg abnormal return, volume ratio;
and `flip_long` stats), `notes.md`.


## Package 3: Bouncy ball short, go intraday and add the squeeze guard

**Claim (about 7:10 to 8:20).** "The first bounce is large, the second bounce is smaller, the third is smaller again,
and eventually the ball loses its energy." Short "the failed bounce with a much clearer level for my stop." It also
"can save you from one of the most common mistakes in short selling, chasing": you can be right "but still get
stopped out by a violent counter trend rally."

**What the first pass left open.** Daily bars only (he trades this mostly intraday), 2 shrinking bounces, a fixed 2R
target, no funding, no check on who is crowded.

**The test.**
1. Rule: crash = close is at least D under the highest high of the last N bars. Find swing highs (pivot width P bars
   each side). Setup = the last B swing highs after the crash are each lower, and each bounce (swing high minus the
   swing low before it) is at most R x the bounce before it. Short at the open after the newest swing high is
   confirmed. Stop just above that swing high.
2. Grid:
   - crash D: 20%, 30%, 40%, 60%; N: 30 bars on each timeframe, and also "30 days" in clock time.
   - bounces B: 2 or 3. Decay R: 1.0 (just smaller), 0.7, 0.5.
   - pivot P: 2, 3, 5.
   - exit: 2R, 3R, the crash low, ATR x 3 trail, time stop 15 and 40 bars.
3. Baseline side by side: "chase the crash" (short the first close that is D under the high). His point is that the
   bounce entry beats chasing. Keep it in every table.
4. Squeeze guard filters (his "violent counter trend rally" risk):
   - Funding: skip when funding is negative at entry (shorts already crowded).
   - Short liquidation spike: on BTC, ETH, SOL, XRP, skip when short liquidations (`forced_buy_usd`) in the last
     hour are in their top 10% (use `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/moondev_api/liq_clean_{BTC,ETH,SOL,XRP}_5m.csv`, read
     `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/moondev_api/LIQ_CLEAN_README.md` first; never use the raw liq OHLC as price).
   - BTC regime: BTC under its 50 day SMA.
5. Costs: fees 4.5 bp a side, slippage 0, 10, 25 bp, real funding per bar held.
6. Out of sample: knobs picked before 2024-07-01, reported after.

**Markets and timeframes (the data to use).**
- 15m: Binance perp 1m klines resampled, `/Volumes/Moon 26/tick_data/binance/futures_klines_1m/<SYM>/` (16 symbols,
  multi year). Plus Hyperliquid 15m `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_15m/`
  (74 coins, about 52 days, a recent sanity check only).
- 1h and 4h: the same Binance 1m resampled; Hyperliquid 4h from `.../data/hyperliquid_meme/*_4h_hl.csv`.
- Daily: the first pass Hyperliquid set (for the "does intraday beat daily" row).
- Funding: same sources as Package 1.
- Liquidations: local `/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/moondev_api/liq_clean_*_5m.csv`; if those are missing, the Moon Dev API
  (`api.py` `MoonDevAPI`, key from the main repo `.env` via dotenv) for recent windows only, and say which was used.
- Stocks side check: Yahoo hourly (yfinance, last 730 days) on current IWM holdings that fell 40%+ in 30 days.
  Borrow grid 5%, 25%, 100% a year. Note survivorship.

**What proves, breaks, or improves it.** Proves: a timeframe and decay combo passes the edge bar out of sample.
Breaks: every combo still loses after funding and 10 bp slippage. Improves: the third weaker bounce, or the squeeze
guard, lifts the out of sample avg trade by 0.5%+ with at least 100 trades. Always report bounce vs chase.

**Output.** `alpha/3_bouncy_ball/` with the code, `result.json` (add `by_timeframe`), `notes.md`.
