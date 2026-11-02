"""
Moon Dev backtest 2: The bouncy ball short (strategy 4 in the video)

THE CLAIM (TheOneLanceB, about 7:10 to 8:20): after an extreme drop, each bounce gets weaker,
like a rubber ball. Short the failed weak bounce with a clear stop above it. This beats "chasing",
which is smashing the short button at the lows after the crash.

WHAT THIS TESTS:
  Crash   : close is 40%+ under the highest high of the last 30 days.
  Bounces : swing highs and lows (a bar higher/lower than the 2 bars on each side, only known
            2 bars later, so no peeking). A bounce = swing high / the swing low before it.
  BALL    : (the video's way) in a crash, the 2 latest bounces both made LOWER swing highs and the
            newest bounce is SMALLER than the one before. Short when that weak swing high is
            confirmed. Stop just above that swing high. Target 2R. Exit after 15 days if neither hit.
  CHASE   : (what he says not to do) short the first close that is 40% under the 30 day high.
            Stop 15% above entry, target 30% under (2R). Same 15 day time stop.
  Fees: 4.5 bp taker each side. Funding is NOT included.

DATA: Moon Dev's real Hyperliquid daily candles (about 123 coins, 2020 to Aug 2026). No synthetic data.
"""
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
from moon_dev_common import load_hl_daily, summary, TAKER_FEE

DROP = 0.40
LOOKBACK = 30
PIV = 2
MAX_HOLD = 15


def build_signals(df):
    """Moon Dev: bouncy ball and chase signals, walking forward with no look ahead."""
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    hh = pd.Series(h).rolling(LOOKBACK).max().values
    crash = c <= hh * (1 - DROP)
    ball, ball_stop = np.zeros(len(c)), np.full(len(c), np.nan)
    chase = np.zeros(len(c))
    pivots = []  # (bar, "H" or "L", price), added only when confirmed
    for i in range(LOOKBACK, len(c)):
        j = i - PIV  # the bar that can be confirmed today
        if h[j] == h[j - PIV:j + PIV + 1].max():
            pivots.append((j, "H", h[j]))
            # bouncy ball check on the newly confirmed swing high
            if crash[i] or crash[j]:
                hs = [p for p in pivots if p[1] == "H" and p[0] > i - LOOKBACK]
                if len(hs) >= 3:
                    sizes = []
                    for ph in hs[-2:]:
                        lows = [p for p in pivots if p[1] == "L" and p[0] < ph[0]]
                        sizes.append(ph[2] / lows[-1][2] - 1 if lows else np.nan)
                    lower_highs = hs[-1][2] < hs[-2][2] < hs[-3][2]
                    weaker = not np.isnan(sizes).any() and sizes[1] < sizes[0]
                    if lower_highs and weaker and c[i] < hs[-1][2]:
                        ball[i], ball_stop[i] = 1, hs[-1][2] * 1.005
        if l[j] == l[j - PIV:j + PIV + 1].min():
            pivots.append((j, "L", l[j]))
        if crash[i] and not crash[i - 1]:
            chase[i] = 1
    return ball, ball_stop, chase


class MoonDevBouncyBall(Strategy):
    mode = "ball"

    def init(self):
        ball, stop, chase = build_signals(self.data.df)
        self.sig = self.I(lambda: ball if self.mode == "ball" else chase, name="signal", plot=False)
        self.stp = self.I(lambda: stop, name="stop", plot=False)

    def next(self):
        if self.position:
            if len(self.data) - self.trades[-1].entry_bar >= MAX_HOLD:
                self.position.close()
            return
        if self.sig[-1] != 1:
            return
        px = self.data.Close[-1]
        stop = self.stp[-1] if self.mode == "ball" else px * 1.15
        if stop <= px:
            return
        risk = stop - px
        tp = px - 2 * risk
        if tp > 0:
            self.sell(size=0.95, sl=stop, tp=tp)


def run(mode, data):
    results, full = {}, []
    for coin, df in data.items():
        bt = Backtest(df, MoonDevBouncyBall, cash=10_000_000, commission=TAKER_FEE, exclusive_orders=True)
        stats = bt.run(mode=mode)
        results[coin] = (stats, df)
        if stats["# Trades"] > 0:
            full.append(f"\n===== Moon Dev {mode.upper()} | {coin} =====\n{stats}")
    return results, full


if __name__ == "__main__":
    print("Moon Dev: bouncy ball short vs chasing the crash")
    data = load_hl_daily()
    out = []
    for mode in ["ball", "chase"]:
        results, full = run(mode, data)
        text, trades = summary(f"{mode.upper()} entry", results, 365)
        out.append(text)
        out.extend(full)
        for block in full:
            print(block)
    open("results/bouncy_ball_short.txt", "w").write("\n".join(out) + "\n")
    print("Moon Dev: saved results/bouncy_ball_short.txt")
