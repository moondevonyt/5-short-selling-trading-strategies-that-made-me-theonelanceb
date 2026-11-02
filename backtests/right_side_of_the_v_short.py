"""
Moon Dev backtest 1: Right side of the V short (strategies 1 and 2 in the video)

THE CLAIM (TheOneLanceB, about 2:40 to 4:40): after a parabolic run up, do not try to call the
exact top. Wait for the turn: a sharp break of the uptrend, a failed try to reclaim the highs
a lower high. "You might capture less of the total move but... your expected value actually goes up."

WHAT THIS TESTS (on crypto, the closest thing Moon Dev trades to a microcap runner):
  Run up   : the daily high is at least 2x the lowest low of the last 30 days (a 100%+ run).
  WAIT     : (the video's way) after the peak, a bounce day closes green but its high stays under
             the peak (lower high). Short when a later close breaks under that bounce day's low
             AND is under the 10 EMA. Stop above the lower high.
  TOP CALL : (the thing he says not to do) short the first red close within 3 days of the peak.
             Stop above the peak.
  Both exit on a close back above the 10 EMA, the stop, or after 30 days. Same exits, so the only
  change is the entry. Fees: 4.5 bp taker each side. Funding is NOT included.

DATA: Moon Dev's real Hyperliquid daily candles (moon-dev-trading-bots/data/hyperliquid_midcap +
hyperliquid_meme), about 130 coins, 2020 to Aug 2026. No synthetic data.
"""
import sys
import numpy as np
import pandas as pd
import talib
from backtesting import Backtest, Strategy
from moon_dev_common import load_hl_daily, summary, TAKER_FEE

RUN_MULT = 2.0      # high must be 2x the 30 day low
BASE_LOOKBACK = 30
PEAK_WINDOW = 20    # how long after the peak we still look for the short
MAX_HOLD = 30


def build_signals(df):
    """Moon Dev: walk forward bar by bar, only using data we would have had that day."""
    o, h, l, c = (df[k].values for k in ["Open", "High", "Low", "Close"])
    ema = talib.EMA(c, 10)
    base = pd.Series(l).rolling(BASE_LOOKBACK).min().values
    wait_sig, wait_stop = np.zeros(len(c)), np.full(len(c), np.nan)
    top_sig, top_stop = np.zeros(len(c)), np.full(len(c), np.nan)
    peak, peak_i, lh, lh_low, fired_w, fired_t = np.nan, -999, np.nan, np.nan, True, True
    for i in range(BASE_LOOKBACK, len(c)):
        if h[i] >= base[i] * RUN_MULT and (np.isnan(peak) or h[i] > peak or i - peak_i > PEAK_WINDOW):
            peak, peak_i, lh, lh_low, fired_w, fired_t = h[i], i, np.nan, np.nan, False, False
            continue
        if i - peak_i > PEAK_WINDOW:
            continue
        # TOP CALL: first red close within 3 days of the peak
        if not fired_t and i - peak_i <= 3 and c[i] < o[i]:
            top_sig[i], top_stop[i], fired_t = 1, peak, True
        # WAIT: entry first (uses the lower high set on an earlier day), then update the lower high
        if not fired_w and not np.isnan(lh) and c[i] < lh_low and c[i] < ema[i]:
            wait_sig[i], wait_stop[i], fired_w = 1, lh, True
        if not fired_w and c[i] > c[i - 1] and h[i] < peak:
            lh, lh_low = h[i], l[i]  # latest failed bounce (green day under the peak)
    return wait_sig, wait_stop, top_sig, top_stop, ema


class MoonDevVShort(Strategy):
    mode = "wait"

    def init(self):
        d = self.data.df
        ws, wst, ts, tst, ema = build_signals(d)
        sig, stop = (ws, wst) if self.mode == "wait" else (ts, tst)
        self.sig = self.I(lambda: sig, name="signal", plot=False)
        self.stp = self.I(lambda: stop, name="stop", plot=False)
        self.ema = self.I(lambda: ema, name="ema10", plot=False)

    def next(self):
        if self.position:
            t = self.trades[-1]
            if self.data.Close[-1] > self.ema[-1] or len(self.data) - t.entry_bar >= MAX_HOLD:
                self.position.close()
            return
        if self.sig[-1] == 1 and self.stp[-1] > self.data.Close[-1]:
            self.sell(size=0.95, sl=self.stp[-1])


def run(mode, data):
    results, full = {}, []
    for coin, df in data.items():
        bt = Backtest(df, MoonDevVShort, cash=10_000_000, commission=TAKER_FEE,
                      exclusive_orders=True)
        stats = bt.run(mode=mode)
        results[coin] = (stats, df)
        if stats["# Trades"] > 0:
            full.append(f"\n===== Moon Dev {mode.upper()} | {coin} =====\n{stats}")
    return results, full


if __name__ == "__main__":
    print("Moon Dev: right side of the V short, wait for the turn vs call the top")
    data = load_hl_daily()
    out = []
    for mode in ["wait", "top"]:
        results, full = run(mode, data)
        text, trades = summary(f"{mode.upper()} entry", results, 365)
        out.append(text)
        out.extend(full)
        for block in full:
            print(block)
    open("results/right_side_of_the_v_short.txt", "w").write("\n".join(out) + "\n")
    print("Moon Dev: saved results/right_side_of_the_v_short.txt")
