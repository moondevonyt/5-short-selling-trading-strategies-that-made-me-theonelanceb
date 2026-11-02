# Moon Dev backtest results: 5 Short Selling Strategies (TheOneLanceB)

Real data only. Fees: 4.5 bp taker each side. Crypto tests skip funding. Stock test skips borrow fees.
Portfolio = equal weight across every symbol, flat days count as 0. Buy and hold = the same symbols, same days.

| # | Idea | Data | Return | Buy and hold | Sharpe | Max DD | Trades | Avg trade | Win rate | Verdict |
|---|------|------|--------|--------------|--------|--------|--------|-----------|----------|---------|
| 1 | Right side of the V short (wait for the lower high break) | 123 Hyperliquid coins, daily, 2020 to Aug 2026 | -28.1% | +302.0% | -0.53 | -34.2% | 677 | -1.19% | 35.5% | FAIL. Loses after fees. But it beats calling the top (below), so his "wait" point holds. Last half of trades averaged +0.91%, worth a deeper look |
| 1b | Same, but short the first red day at the top | same | -34.2% | +302.0% | -0.77 | -36.4% | 1194 | -1.83% | 42.4% | FAIL. Worst of the lot. Do not call tops |
| 2 | Bouncy ball short (weaker bounces after a 40% crash) | 123 Hyperliquid coins, daily. Live squeeze snapshot from the Moon Dev API `GET /api/positions/all.json` (near liquidation short fuel vs long fuel per coin, optional `LIVE_SQUEEZE_GUARD`) | -9.5% | +302.0% | -0.33 | -16.8% | 393 | -1.93% | 40.7% | FAIL. Loses less than chasing, still loses |
| 2b | Chase the crash (short the first 40% down close) | same | -36.2% | +302.0% | -0.54 | -37.4% | 1378 | -2.22% | 37.2% | FAIL. He is right: chasing is a donation |
| 3 | Short the IPO lockup expiry (day -2 to day +2) | 55 US IPOs 2019 to 2025, Yahoo daily | -18.4% | +104.0% | -0.40 | -28.3% | 55 | -0.53% | 43.6% | FAIL now, WEAK then. First half (2019 to mid 2021) averaged +1.99%, second half -2.97%. Looks crowded out, just like he warned |

Fact checks from the video:
- BYND on Oct 29 2019 (lockup day): -22.2% close to close. His "fell more than 20%" is TRUE.
- Volume around lockup day vs the month before: median +15%, mean +71% (a few huge spikes). The 40% claim is in the right zone.
- Abnormal return vs SPY over our 4 day window: -0.39% for the short (the study he cites says about +1.8% for a short). Not there in 2019 to 2025 data.

Full stats for every symbol: `results/*.txt`.
