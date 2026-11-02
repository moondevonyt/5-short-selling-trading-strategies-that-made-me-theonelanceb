"""
Moon Dev's data loaders for the bouncy ball edge test (package 3).

Real data only. Every loader reads a local file or a public endpoint with no key.
If a file is missing the loader raises, and the caller writes that into notes.md.

Sources:
  Binance USDT perp 1m klines (Moon 26 drive) resampled to 15m, 1h, 4h, 1d.
  Hyperliquid 15m (74 coins, about 52 days) and 4h (22 meme coins).
  Funding: local Binance and Hyperliquid files, else the public Binance fapi and
  Hyperliquid info endpoints. Coins that still have no funding are tagged.
  Liquidations: liq_clean_{BTC,ETH,SOL,XRP}_5m.csv (forced_buy_usd = short liqs).
"""
from pathlib import Path
import time
import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data_cache"
CACHE.mkdir(exist_ok=True)
MOON = Path("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data")
BIN_1M = Path("/Volumes/Moon 26/tick_data/binance/futures_klines_1m")
BIN_FUND = Path("/Volumes/Moon 26/tick_data/binance/funding")
LIQ_DIR = MOON / "moondev_api"
RULE = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
OHLC = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


# Moon Dev: the 16 symbols the plan names. Other folders on the drive may be mid download by another agent.
BIN_SYMBOLS = ["ARBUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT", "CRVUSDT", "DOGEUSDT", "ETHUSDT", "FILUSDT",
               "INITUSDT", "LINKUSDT", "SOLUSDT", "STRKUSDT", "SUIUSDT", "TIAUSDT", "XRPUSDT", "ZECUSDT"]


def binance_symbols():
    missing = [s for s in BIN_SYMBOLS if not (BIN_1M / s).is_dir()]
    if missing:
        raise FileNotFoundError(f"Moon Dev: Binance 1m folders missing: {missing}")
    return BIN_SYMBOLS


def load_binance(tf):
    """Moon Dev: every Binance symbol resampled from the all in one 1m parquet. Cached per timeframe."""
    out = {}
    for sym in binance_symbols():
        cache = CACHE / f"binance_{sym}_{tf}.parquet"
        if cache.exists():
            out[sym] = pd.read_parquet(cache)
            continue
        files = list((BIN_1M / sym).glob(f"{sym}_1m_20*.parquet"))
        if len(files) != 1:
            raise FileNotFoundError(f"Moon Dev: no all in one 1m parquet for {sym}")
        raw = pd.read_parquet(files[0], columns=["open_time", "open", "high", "low", "close", "volume"])
        raw["open_time"] = pd.to_datetime(raw["open_time"], utc=True).dt.tz_localize(None)
        raw = raw.set_index("open_time").sort_index()
        raw = raw[~raw.index.duplicated()].rename(columns=str.capitalize)
        df = raw.resample(RULE[tf]).agg(OHLC).dropna(subset=["Open"])
        df.to_parquet(cache)
        out[sym] = df
        print(f"Moon Dev: resampled {sym} 1m to {tf}: {len(df)} bars")
    print(f"Moon Dev: Binance {tf}: {len(out)} symbols")
    return out


def _hl_csv(f):
    df = pd.read_csv(f, parse_dates=["datetime"]).set_index("datetime").sort_index()
    df = df.rename(columns=str.capitalize)[["Open", "High", "Low", "Close", "Volume"]]
    return df[~df.index.duplicated()]


def load_hl_15m():
    files = sorted((MOON / "hyperliquid_15m").glob("*_15m_hl.csv"))
    if not files:
        raise FileNotFoundError("Moon Dev: no hyperliquid_15m files")
    out = {f.name.split("_")[0]: _hl_csv(f) for f in files}
    print(f"Moon Dev: Hyperliquid 15m: {len(out)} coins")
    return out


def load_hl_4h():
    files = sorted((MOON / "hyperliquid_meme").glob("*_4h_hl.csv"))
    if not files:
        raise FileNotFoundError("Moon Dev: no hyperliquid_meme 4h files")
    out = {f.name.split("_")[0]: _hl_csv(f) for f in files}
    print(f"Moon Dev: Hyperliquid 4h: {len(out)} coins")
    return out


def load_hl_daily():
    import sys
    sys.path.insert(0, str(HERE.parent.parent / "backtests"))
    from moon_dev_common import load_hl_daily as first_pass_loader
    return first_pass_loader()


# ---------------- funding ----------------
def _binance_funding_api(sym):
    """Moon Dev: public Binance fapi funding history, no key. 1000 rows a call."""
    rows, start = [], 1577836800000  # 2020-01-01
    while True:
        r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                         params={"symbol": sym, "startTime": start, "limit": 1000}, timeout=20)
        r.raise_for_status()
        chunk = r.json()
        if not chunk:
            break
        rows.extend(chunk)
        start = chunk[-1]["fundingTime"] + 1
        if len(chunk) < 1000:
            break
        time.sleep(0.15)
    df = pd.DataFrame(rows)
    return pd.Series(df["fundingRate"].astype(float).values,
                     index=pd.to_datetime(df["fundingTime"], unit="ms")).sort_index()


def binance_funding(sym):
    """Moon Dev: Binance funding series (rate per 8h event). Local file first, else public API, cached."""
    cache = CACHE / f"funding_binance_{sym}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["rate"]
    local = BIN_FUND / f"{sym}_funding.csv"
    if local.exists():
        f = pd.read_csv(local)
        s = pd.Series(f["rate"].values, index=pd.to_datetime(f["ts"], format="ISO8601", utc=True).dt.tz_localize(None)).sort_index()
        src = "local"
    else:
        s = _binance_funding_api(sym)
        src = "fapi"
    s = s[~s.index.duplicated()]
    s.rename("rate").to_frame().to_parquet(cache)
    print(f"Moon Dev: funding {sym}: {len(s)} events from {src}, {s.index.min()} to {s.index.max()}")
    return s


def _hl_funding_api(coin, start, end):
    """Moon Dev: public Hyperliquid fundingHistory, no key. Hourly, 500 a call."""
    rows, t0 = [], int(pd.Timestamp(start).timestamp() * 1000)
    t_end = int(pd.Timestamp(end).timestamp() * 1000)
    while t0 < t_end:
        for attempt in range(6):  # Moon Dev: the public endpoint rate limits, back off and try again
            r = requests.post("https://api.hyperliquid.xyz/info",
                              json={"type": "fundingHistory", "coin": coin, "startTime": t0, "endTime": t_end}, timeout=20)
            if r.status_code != 429:
                break
            time.sleep(3 * (attempt + 1))
        r.raise_for_status()
        chunk = r.json()
        if not chunk:
            break
        rows.extend(chunk)
        t0 = chunk[-1]["time"] + 1
        if len(chunk) < 500:
            break
        time.sleep(0.4)
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    return pd.Series(df["fundingRate"].astype(float).values, index=pd.to_datetime(df["time"], unit="ms")).sort_index()


def hl_funding(coin, start, end):
    """Moon Dev: Hyperliquid hourly funding. Local midcap or meme file first, else the public endpoint."""
    cache = CACHE / f"funding_hl_{coin}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)["rate"]
    f1, f2 = MOON / "hyperliquid_funding" / f"{coin}_funding_hl.csv", MOON / "hyperliquid_meme" / f"{coin}_funding_hl.csv"
    if f1.exists():
        d = pd.read_csv(f1)
        s = pd.Series(d["fundingRate"].values, index=pd.to_datetime(d["datetime"]))
        src = "local midcap"
    elif f2.exists():
        d = pd.read_csv(f2)
        s = pd.Series(d["fundingRate"].values, index=pd.to_datetime(d["dt"]).dt.floor("h"))
        src = "local meme"
    else:
        s = _hl_funding_api(coin, start, end)
        src = "hl api"
    s = s[~s.index.duplicated()].sort_index()
    s.rename("rate").to_frame().to_parquet(cache)
    print(f"Moon Dev: HL funding {coin}: {len(s)} events from {src}")
    return s


# ---------------- liquidations and regime ----------------
def load_liq_1h(coin):
    """Moon Dev: 1 hour rolling sum of short liquidations (forced_buy_usd) and its rolling 30 day 90th pct."""
    f = LIQ_DIR / f"liq_clean_{coin}_5m.csv"
    if not f.exists():
        raise FileNotFoundError(f"Moon Dev: missing {f}")
    d = pd.read_csv(f, usecols=["datetime", "forced_buy_usd", "coinm_suspect"], parse_dates=["datetime"]).set_index("datetime")
    d = d[~d["coinm_suspect"]]
    fb = d["forced_buy_usd"].rolling(12, min_periods=1).sum()
    thr = fb.rolling(12 * 24 * 30, min_periods=12 * 24 * 7).quantile(0.90)
    return pd.DataFrame({"short_liq_1h": fb, "top10_thr": thr}).dropna()


def btc_regime():
    """Moon Dev: BTC daily close under its 50 day SMA, known at the next day's open (shifted one day)."""
    btc = load_binance("1d")["BTCUSDT"]
    under = (btc["Close"] < btc["Close"].rolling(50).mean()).shift(1).fillna(False)
    return under.astype(bool)
