"""
Moon Dev: the stock side check data. Today's iShares IWM holdings list (survivorship: only
names alive today) and Yahoo daily bars for each via yfinance. Cached to data_cache/stocks/
(gitignored). Real data only: if iShares or Yahoo fail, this script fails.
"""
import io
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).parent
CACHE = HERE / "data_cache" / "stocks"
IWM_URL = ("https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax"
           "?fileType=csv&fileName=IWM_holdings&dataType=fund")


def iwm_tickers():
    """Moon Dev: iShares serves scripts an HTML bot wall. If that happens, save the CSV by hand from the IWM
    product page to data_cache/IWM_holdings.csv and this picks it up."""
    hand = HERE / "data_cache" / "IWM_holdings.csv"
    if hand.exists():
        text = hand.read_text(errors="ignore")
    else:
        r = requests.get(IWM_URL, headers={"User-Agent": "Mozilla/5.0 Moon Dev research"}, timeout=60)
        r.raise_for_status()
        text = r.text
    lines = text.splitlines()
    if not any(ln.startswith("Ticker") for ln in lines):
        raise SystemExit(f"Moon Dev: iShares returned a bot wall, not the CSV. Save it by hand to {hand} and rerun.")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("Ticker"))
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])))
    df = df[(df["Asset Class"] == "Equity") & df["Ticker"].notna()]
    ticks = sorted({t.strip().replace(".", "-") for t in df["Ticker"] if t.strip().isalnum() or "." in t})
    print(f"Moon Dev: {len(ticks)} IWM equity tickers from iShares")
    return ticks


if __name__ == "__main__":
    CACHE.mkdir(parents=True, exist_ok=True)
    ticks = iwm_tickers()
    (HERE / "data_cache" / "iwm_tickers.txt").write_text("\n".join(ticks))
    n = 0
    for i in range(0, len(ticks), 200):
        batch = ticks[i:i + 200]
        px = yf.download(batch, start="2018-01-01", auto_adjust=False, group_by="ticker", threads=True, progress=False)
        for t in batch:
            if t not in px.columns.get_level_values(0):
                continue
            df = px[t].dropna(subset=["Close"])
            if len(df) >= 120:
                df[["Open", "High", "Low", "Close", "Volume"]].to_csv(CACHE / f"{t}_1d.csv")
                n += 1
        print(f"Moon Dev: {i + len(batch)} of {len(ticks)} downloaded, {n} saved", flush=True)
    print(f"Moon Dev: stocks done, {n} files in {CACHE}")
