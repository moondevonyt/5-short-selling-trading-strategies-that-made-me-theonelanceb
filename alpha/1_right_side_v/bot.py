"""
Moon Dev's Right Side of the V short bot (Hyperliquid). Built from TheOneLanceB's strategy 1 and 2.

STATUS: NOT PROVEN. See result.json and notes.md. The backtest did not clear Moon Dev's edge bar out of
sample, so this bot ships in DRY RUN mode (LIVE = False) as a clean example of the rule, not as a money maker.

Real backtest line for the knobs below (run_grid.py, fees 4.5 bp a side, 10 bp slippage a side, real funding):
    hl_1d K=1.5 N=10 lower high break, 2R target, stop above the lower high, 60 bar cap. Out of sample (after 2024-07-01):
    294 funded trades, avg +3.98% a trade, t-stat 2.61, win rate 42.9%, profit factor 1.43, 68% of coins positive.
    In sample (before): 59 funded trades, avg +3.53%, t-stat 1.08. Beats a blind short of the same coins by +2.89% a trade
    but only with t-stat 1.89, and only 43% of trades beat the blind short. That is why it is NOT PROVEN.

The rule (walk forward, only closed candles):
  1. Run: the high is at least K x the lowest low of the last N candles. That bar is the peak (a higher high resets it).
  2. The turn: after the peak, a green candle whose high stays under the peak is the lower high.
  3. Entry: a close under that candle's low AND under the 10 EMA. Short at the next open.
  4. Stop: just above the lower high. Target: 2R (twice the stop distance, the best exit in the grid). MAX_HOLD candles cap.

Keys: HYPERLIQUID_PRIVATE_KEY from the main repo .env via dotenv. Never printed. No wallet address in this file
(the SDK derives it from the key). Candles come from the public info endpoint, no key needed.
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import talib
from dotenv import load_dotenv

LIVE = False                     # Moon Dev: flip to True only after you read notes.md and accept NOT PROVEN
COIN = "WIF"                     # one coin per bot. Run several bots for several coins.
INTERVAL = "1d"                  # the market the knobs were picked on
K = 1.5                          # run size: high >= K x the N bar low (best in the grid)
N = 10                           # base window in candles
TARGET_R = 2.0                   # take profit at 2R, the stop distance times 2
MAX_HOLD = 60                    # candles, hard cap
PEAK_WINDOW = 20                 # candles after the peak we still take the setup
SIZE_USD = 25                    # notional per trade, small on purpose
LEVERAGE = 2
SLEEP_SEC = 60 * 15              # check every 15 minutes; only closed candles count
INFO_URL = "https://api.hyperliquid.xyz/info"
ENV_PATH = Path("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/.env")

load_dotenv(ENV_PATH)
PRIVATE_KEY = os.getenv("HYPER_LIQUID_KEY")   # Moon Dev: the same env name the main repo bots use. Never print this


def candles(coin, interval, n_bars=400):
    """Moon Dev: closed candles only, oldest first."""
    ms = {"1h": 3600_000, "4h": 4 * 3600_000, "8h": 8 * 3600_000, "1d": 24 * 3600_000}[interval]
    end = int(time.time() * 1000)
    body = {"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": end - n_bars * ms, "endTime": end}}
    for attempt in range(5):
        r = requests.post(INFO_URL, json=body, timeout=30)
        if r.status_code != 429:
            break
        print(f"Moon Dev: rate limited by Hyperliquid, retry {attempt + 1}")
        time.sleep(10)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df = df.rename(columns={"t": "time", "o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    df = df.set_index("time")[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    return df.iloc[:-1]  # drop the candle still forming


def setup(df):
    """Moon Dev: returns (signal, stop, lower_high_time) using the same walk forward as the backtest."""
    o, h, l, c = (df[k].values for k in ["Open", "High", "Low", "Close"])
    ema = talib.EMA(c, 10)
    base = pd.Series(l).rolling(N).min().values
    peak, peak_i, lh, lh_low, lh_i, fired = np.nan, -999, np.nan, np.nan, -1, True
    sig, stop = False, np.nan
    for i in range(N, len(c)):
        sig = False
        if h[i] >= base[i] * K and (np.isnan(peak) or h[i] > peak or i - peak_i > PEAK_WINDOW):
            peak, peak_i, lh, lh_low, lh_i, fired = h[i], i, np.nan, np.nan, -1, False
            continue
        if i - peak_i > PEAK_WINDOW or fired:
            continue
        if not np.isnan(lh) and c[i] < lh_low and c[i] < ema[i]:
            sig, stop, fired = True, lh, True
        if not fired and c[i] > c[i - 1] and h[i] < peak:
            lh, lh_low, lh_i = h[i], l[i], i
    return sig, stop, (df.index[lh_i] if lh_i >= 0 else None), ema[-1]


def exchange():
    """Moon Dev: the live Hyperliquid SDK, only built when LIVE is True."""
    from eth_account import Account
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    if not PRIVATE_KEY:
        raise SystemExit("Moon Dev: HYPERLIQUID_PRIVATE_KEY is not in the .env, cannot go live")
    return Exchange(Account.from_key(PRIVATE_KEY), constants.MAINNET_API_URL)


def main():
    print(f"Moon Dev Right Side of the V bot | {COIN} {INTERVAL} | K={K} N={N} target {TARGET_R}R | LIVE={LIVE}")
    print("Moon Dev: NOT PROVEN in the backtest. Dry run unless you flip LIVE after reading notes.md.")
    in_pos, entry_bar_time, stop, target = False, None, np.nan, np.nan
    ex = exchange() if LIVE else None
    if LIVE:
        ex.update_leverage(LEVERAGE, COIN)
    while True:
        df = candles(COIN, INTERVAL)
        last = df.index[-1]
        px = df["Close"].iloc[-1]
        if in_pos:
            held = int((df.index > entry_bar_time).sum())
            hit = df["High"].iloc[-1] >= stop or df["Low"].iloc[-1] <= target   # the exchange orders did the fill
            if hit or held >= MAX_HOLD:
                print(f"Moon Dev {last} {COIN}: trade over ({'stop or target hit' if hit else 'time cap'}), close {px:.5g}, held {held} bars")
                if LIVE and not hit:
                    ex.market_close(COIN)
                in_pos = False
            else:
                print(f"Moon Dev {last} {COIN}: short open, close {px:.5g}, stop {stop:.5g}, target {target:.5g}, held {held}")
        else:
            sig, stp, lh_time, ema10 = setup(df)
            if sig and stp > px:
                size = round(SIZE_USD / px, 4)
                tgt = px - TARGET_R * (stp - px)
                print(f"Moon Dev {last} {COIN}: SHORT signal. Close {px:.5g} broke the lower high low ({lh_time}), under EMA10 {ema10:.5g}. "
                      f"Stop {stp:.5g} ({(stp / px - 1) * 100:.1f}% away), target {tgt:.5g}, size {size}")
                if LIVE:
                    ex.market_open(COIN, False, size, None, 0.01)
                    ex.order(COIN, True, size, float(f"{stp:.5g}"), {"trigger": {"triggerPx": float(f"{stp:.5g}"), "isMarket": True, "tpsl": "sl"}}, reduce_only=True)
                    ex.order(COIN, True, size, float(f"{tgt:.5g}"), {"trigger": {"triggerPx": float(f"{tgt:.5g}"), "isMarket": True, "tpsl": "tp"}}, reduce_only=True)
                in_pos, entry_bar_time, stop, target = True, last, stp, tgt
            else:
                print(f"Moon Dev {last} {COIN}: no setup. Close {px:.5g}, EMA10 {ema10:.5g}")
        time.sleep(SLEEP_SEC)


if __name__ == "__main__":
    main()
