"""
Moon Dev edge finder, package 2, step 2: Yahoo daily prices for every IPO ticker plus IWM and SPY.

Reads the parsed EDGAR filings in data_cache/edgar_parsed/ (or ipo_universe.json when it exists), pulls the
symbol printed in each prospectus plus the SEC's current ticker for that CIK, and downloads daily candles with
yfinance (real, public, no key). One CSV per ticker in data_cache/ (gitignored, the folder is over 20 MB).
Tickers Yahoo does not know are written to data_cache/yahoo_missing.txt, never filled in.
Run it as often as you like, it only downloads what is not cached yet.
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).parent
CACHE = HERE / "data_cache"
PARSED = CACHE / "edgar_parsed"
MISSING = CACHE / "yahoo_missing.txt"


def load_universe():
    f = HERE / "ipo_universe.json"
    if f.exists():
        return pd.read_json(f)
    rows = [json.loads(p.read_text()) for p in PARSED.glob("*.json")]
    return pd.DataFrame(rows)


def wanted_tickers(df):
    """Moon Dev: filing symbol first, SEC current ticker second. Both get tried, the study picks the one that fits."""
    out = set()
    for col in ["symbol", "sec_ticker"]:
        if col in df:
            out |= set(df[col].dropna().astype(str))
    out = {t.replace(".", "-").strip() for t in out if 1 <= len(t) <= 6 and t.isascii()}
    return sorted(out)


def download(tickers, batch=60):
    """Moon Dev: batch download, save each ticker on its own so a re-run skips it."""
    missing = set(MISSING.read_text().split()) if MISSING.exists() else set()
    todo = [t for t in tickers if not (CACHE / f"{t}_1d.csv").exists() and t not in missing]
    print(f"Moon Dev: {len(tickers)} tickers wanted, {len(todo)} to download, {len(missing)} known missing")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        data = yf.download(chunk, period="max", interval="1d", auto_adjust=True, group_by="ticker",
                           threads=True, progress=False)
        for t in chunk:
            df = data[t] if len(chunk) > 1 else data
            df = df.dropna(subset=["Close"])
            if df.empty:
                missing.add(t)
                continue
            df[["Open", "High", "Low", "Close", "Volume"]].to_csv(CACHE / f"{t}_1d.csv")
        MISSING.write_text("\n".join(sorted(missing)))
        print(f"Moon Dev: {min(i + batch, len(todo))}/{len(todo)} done, missing so far {len(missing)}")
        time.sleep(1)
    return missing


def get(ticker):
    f = CACHE / f"{ticker}_1d.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return df[df["Volume"] >= 0]


if __name__ == "__main__":
    CACHE.mkdir(exist_ok=True)
    uni = load_universe()
    print(f"Moon Dev: {len(uni)} parsed filings loaded")
    tickers = wanted_tickers(uni) + ["IWM", "SPY"]
    missing = download(tickers)
    print(f"Moon Dev: done. Yahoo had no data for {len(missing)} tickers (listed in {MISSING})")
