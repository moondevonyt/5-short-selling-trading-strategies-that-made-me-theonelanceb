"""
Moon Dev backtest 3: Short hot IPOs into the lockup expiry (strategy 5 in the video)

THE CLAIM (TheOneLanceB, about 8:30 to 10:30): when the IPO lockup ends, insider shares can hit the
market. He cites a study of 3,200+ lockups: volume up about 40% in expiry week and an abnormal return
of about -1.8%. Beyond Meat (BYND) fell 20%+ on its Oct 29 2019 lockup day. He also warns the trade
is crowded and can be priced in (SpaceX gapped down then rallied).

WHAT THIS TESTS:
  Universe : 55 US IPOs from 2019 to 2025 that had normal underwriter lockups (no direct listings,
             no SPACs). IPO day = first daily bar on Yahoo.
  Lockup   : day 0 = first trading day on or after IPO + 180 calendar days (the usual lockup).
             This is a guess. Some deals had early or staged releases, so some day 0s are off.
  Trade    : short at the open 2 days before day 0, cover at the open 2 days after (about 4 days).
  Checks   : (1) net return after 4.5 bp fees each side (borrow fee NOT included, and hot IPOs can be
             costly to borrow), (2) the same window on SPY (so we see the abnormal part),
             (3) volume in days -2..+2 vs days -25..-6, (4) the BYND Oct 29 2019 day.
  Baseline : buy and hold each IPO from its first day to day +20 (same bars the test sees).

DATA: Yahoo Finance daily candles via yfinance (real, free). Cached in data_cache/ (gitignored).
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from backtesting import Backtest, Strategy
from moon_dev_common import summary, TAKER_FEE

TICKERS = [
    # 2019
    "LYFT", "PINS", "ZM", "UBER", "BYND", "CRWD", "CHWY", "FVRR", "PTON", "DDOG", "NET", "BILL", "PD",
    # 2020
    "SNOW", "U", "ABNB", "DASH", "AI", "LMND", "NCNO", "FROG",
    # 2021
    "AFRM", "BMBL", "CPNG", "OSCR", "APP", "PATH", "DLO", "MNDY", "DOCS", "FIGS", "DUOL", "HOOD",
    "TOST", "GTLB", "RIVN", "NU", "BROS",
    # 2023 to 2025
    "CAVA", "ARM", "CART", "KVYO", "BIRK", "RDDT", "ALAB", "TEM", "RBRK", "VIK", "ULS", "LINE",
    "CRWV", "CRCL", "CHYM", "ETOR", "FIG",
]
CACHE = Path(__file__).parent / "data_cache"
LOCKUP_DAYS = 180
ENTER_BEFORE = 2  # enter at the open of day -2
EXIT_AFTER = 2    # exit at the open of day +2


def get(ticker):
    """Moon Dev: real Yahoo daily data, cached so we do not hammer Yahoo."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{ticker}_1d.csv"
    if not f.exists():
        df = yf.download(ticker, period="max", interval="1d", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            raise ValueError(f"Moon Dev: Yahoo gave no data for {ticker}")
        df.to_csv(f)
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def lockup_index(df):
    target = df.index[0] + pd.Timedelta(days=LOCKUP_DAYS)
    return int(df.index.searchsorted(target))


class MoonDevLockupShort(Strategy):
    day0 = 0

    def init(self):
        pass

    def next(self):
        i = len(self.data) - 1  # today's bar index; orders fill at the next open
        if i == self.day0 - ENTER_BEFORE - 1 and not self.position:
            self.sell(size=0.95)
        elif i == self.day0 + EXIT_AFTER - 1 and self.position:
            self.position.close()


if __name__ == "__main__":
    print("Moon Dev: IPO lockup expiry short")
    spy = get("SPY")
    results, full, rows = {}, [], []
    for t in TICKERS:
        df = get(t)
        L = lockup_index(df)
        if L + 25 > len(df):
            print(f"Moon Dev: {t} has no lockup day in the data yet, skipped")
            continue
        sub = df.iloc[: L + 21]
        bt = Backtest(sub, MoonDevLockupShort, cash=10_000_000, commission=TAKER_FEE, exclusive_orders=True)
        stats = bt.run(day0=L)
        results[t] = (stats, sub)
        full.append(f"\n===== Moon Dev LOCKUP | {t} | IPO {df.index[0].date()} | day 0 {df.index[L].date()} =====\n{stats}")
        a, b = df.index[L - ENTER_BEFORE], df.index[L + EXIT_AFTER]
        spy_ret = spy.loc[b, "Open"] / spy.loc[a, "Open"] - 1
        stock_ret = df["Open"].iloc[L + EXIT_AFTER] / df["Open"].iloc[L - ENTER_BEFORE] - 1
        vol_jump = df["Volume"].iloc[L - 2:L + 3].mean() / df["Volume"].iloc[L - 25:L - 5].mean() - 1
        rows.append(dict(ticker=t, ipo=df.index[0].date(), day0=df.index[L].date(),
                         stock_pct=stock_ret * 100, spy_pct=spy_ret * 100,
                         abnormal_short_pct=-(stock_ret - spy_ret) * 100, vol_jump_pct=vol_jump * 100))

    text, trades = summary("LOCKUP short, day -2 to day +2", results, 252)
    ev = pd.DataFrame(rows)
    by = get("BYND")
    bynd = by.loc["2019-10-29", "Close"] / by.loc["2019-10-28", "Close"] - 1
    extra = [
        f"Avg abnormal short return vs SPY (before fees): {ev['abnormal_short_pct'].mean():.2f}%  "
        f"median {ev['abnormal_short_pct'].median():.2f}%  share positive {(ev['abnormal_short_pct'] > 0).mean() * 100:.0f}%",
        f"Volume days -2..+2 vs days -25..-6: mean {ev['vol_jump_pct'].mean():.0f}%  median {ev['vol_jump_pct'].median():.0f}%",
        f"BYND close to close on 2019-10-29: {bynd * 100:.1f}%",
        "", "Per event:", ev.round(2).to_string(index=False),
    ]
    print("\n".join(extra))
    for block in full:
        print(block)
    open("results/lockup_expiry_short.txt", "w").write(text + "\n" + "\n".join(extra) + "\n" + "\n".join(full) + "\n")
    print("Moon Dev: saved results/lockup_expiry_short.txt")
