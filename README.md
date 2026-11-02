# 5 Short Selling Trading Strategies That Made Me Millions

By **TheOneLanceB**. Watch it: https://www.youtube.com/watch?v=SvHhoD00jZI

## What this is
Moon Dev watched this video live and pulled out the trading ideas worth testing. This repo holds the full transcript,
plus the backtests, bots and dashboards built while watching.

All credit for the video goes to TheOneLanceB. Go watch it and subscribe.

## Talk to the video with Claude Code
1. Clone this repo.
2. Open it with Claude Code.
3. Ask anything: "what is the main strategy?", "backtest the setup at 12 minutes", "build a bot from this".
   Claude reads `transcript.md` and answers from the real video.

Built by Moon Dev. I have helped 1,000+ people go from dead beginner to fully automated trader.

## Backtests (first round)
Moon Dev ran 3 real backtests of the video's top ideas. Real data only, fees in.
- Right side of the V short on 123 Hyperliquid coins: loses after fees, but waiting beats calling the top.
- Bouncy ball short on 123 Hyperliquid coins: loses, but less than chasing the crash.
- IPO lockup expiry short on 55 US IPOs: worked in 2019 to 2021, stopped working after.

See `backtests/RESULTS.md` for every number, and `IDEAS.md` for the ranked ideas.
Run any test with `python backtests/<name>.py` from inside `backtests/`. The crypto tests read Hyperliquid daily
candles from a local folder (change `DATA_DIR` in `backtests/moon_dev_common.py`). The stock test pulls Yahoo.

Need help implementing this or just want to be part of our group chat? Start here: https://moondev.com/t/github
