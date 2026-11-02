"""
Moon Dev's shared helpers for the TheOneLanceB short selling backtests.

- Loads REAL daily candles. No fake data. If a file is missing, it fails.
- Runs one backtesting.py test per coin or stock, then rolls them into one
  equal weight portfolio so we can compare with buy and hold on the same days.
"""
from pathlib import Path
import numpy as np
import pandas as pd

# Moon Dev's local data (Hyperliquid daily candles). Point this at your own copy.
DATA_DIR = Path("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data")
TAKER_FEE = 0.00045  # Hyperliquid main dex taker, 4.5 bp per side


def load_hl_daily():
    """Moon Dev: every Hyperliquid daily file (midcap + meme), one frame per coin."""
    files = {}
    for sub in ["hyperliquid_meme", "hyperliquid_midcap"]:  # midcap wins on overlap (longer history)
        for f in sorted((DATA_DIR / sub).glob("*_1d_hl.csv")):
            files[f.name.split("_")[0]] = f
    out = {}
    for coin, f in files.items():
        df = pd.read_csv(f, parse_dates=["datetime"]).set_index("datetime").sort_index()
        df = df.rename(columns=str.capitalize)[["Open", "High", "Low", "Close", "Volume"]]
        df = df[~df.index.duplicated()]
        if len(df) >= 120:
            out[coin] = df
    print(f"Moon Dev: loaded {len(out)} Hyperliquid daily files from {DATA_DIR}")
    return out


def portfolio(results, periods_per_year):
    """Moon Dev: equal weight portfolio of every symbol's strategy equity vs buy and hold.

    results = {symbol: (stats, df)}. Each day, the portfolio return is the average
    of the symbols that have data that day (flat days count as 0 for the strategy).
    """
    strat, hold = [], []
    for sym, (stats, df) in results.items():
        eq = stats["_equity_curve"]["Equity"]
        strat.append(eq.pct_change().rename(sym))
        hold.append(df["Close"].pct_change().rename(sym))
    s = pd.concat(strat, axis=1).mean(axis=1).fillna(0)
    h = pd.concat(hold, axis=1).mean(axis=1).fillna(0)

    def metrics(r):
        eq = (1 + r).cumprod()
        sharpe = r.mean() / r.std() * np.sqrt(periods_per_year) if r.std() > 0 else 0
        dd = (eq / eq.cummax() - 1).min()
        return (eq.iloc[-1] - 1) * 100, sharpe, dd * 100

    return metrics(s), metrics(h), s, h


def trade_table(results):
    """Moon Dev: every closed trade from every symbol in one table."""
    rows = []
    for sym, (stats, df) in results.items():
        t = stats["_trades"].copy()
        if len(t):
            t["Symbol"] = sym
            rows.append(t)
    return pd.concat(rows, ignore_index=True).sort_values("EntryTime").reset_index(drop=True) if rows else pd.DataFrame()


def summary(name, results, periods_per_year):
    """Moon Dev: print the pooled numbers that go into RESULTS.md."""
    (sr, ss, sd), (hr, hs, hd), s, h = portfolio(results, periods_per_year)
    t = trade_table(results)
    lines = [f"===== Moon Dev summary: {name} ====="]
    if len(t):
        rp = t["ReturnPct"] * 100
        wins, losses = rp[rp > 0].sum(), -rp[rp < 0].sum()
        tstat = rp.mean() / (rp.std() / np.sqrt(len(rp))) if len(rp) > 1 else 0
        lines += [
            f"Trades: {len(t)}  Symbols traded: {t['Symbol'].nunique()} of {len(results)}",
            f"Avg trade (net of fees): {rp.mean():.2f}%  Median: {rp.median():.2f}%  t-stat: {tstat:.2f}",
            f"Win rate: {(rp > 0).mean() * 100:.1f}%  Profit factor: {wins / losses if losses else float('inf'):.2f}",
            f"Sum of trade returns: {rp.sum():.1f}%",
        ]
        half = len(t) // 2
        lines.append(f"First half of trades (by date) avg: {rp.iloc[:half].mean() if half else 0:.2f}% | "
                     f"Second half avg: {rp.iloc[half:].mean():.2f}%")
    else:
        lines.append("Trades: 0")
    lines += [
        f"Equal weight portfolio: return {sr:.1f}%  Sharpe {ss:.2f}  Max DD {sd:.1f}%",
        f"Buy and hold same symbols: return {hr:.1f}%  Sharpe {hs:.2f}  Max DD {hd:.1f}%",
        f"Date range: {s.index.min().date()} to {s.index.max().date()}",
    ]
    text = "\n".join(lines)
    print(text)
    return text, t
