"""
Moon Dev: pull REAL funding history for every coin that has no local funding file.

Hyperliquid: public info endpoint, type fundingHistory (hourly rates, 500 per call, no key).
Binance USDT perps: public fapi fundingRate (8 hour rates, 1000 per call, no key).
Saves to data_cache/ (gitignored). Nothing is made up: a coin that fails stays missing and
the backtest tags its trades "no funding data".
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).parent
CACHE = HERE / "data_cache"
DATA = Path("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data")
HL_URL = "https://api.hyperliquid.xyz/info"
BN_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def hl_coin_list():
    coins = set()
    for sub in ["hyperliquid_midcap", "hyperliquid_meme", "hyperliquid_8h"]:
        for f in (DATA / sub).glob("*_hl.csv"):
            if "funding" not in f.name:
                coins.add(f.name.split("_")[0])
    have = {f.name.split("_")[0] for f in (DATA / "hyperliquid_funding").glob("*_funding_hl.csv")}
    have |= {f.name.split("_")[0] for f in (DATA / "hyperliquid_meme").glob("*_funding_hl.csv")}
    need = coins - have
    prio = CACHE / "funding_priority.txt"   # Moon Dev: coins that fire the setup most go first
    order = [c for c in prio.read_text().split() if c in need] if prio.exists() else []
    return order + sorted(need - set(order))


def hl_fetch(coin):
    out = CACHE / "hl_funding" / f"{coin}_funding_hl.csv"
    if out.exists():
        return coin, "cached"
    start = int(pd.Timestamp("2022-06-01").timestamp() * 1000)
    end = int(time.time() * 1000)
    rows = []
    while start < end:
        time.sleep(0.5)  # Moon Dev: the endpoint allows about 1 call a second
        r = requests.post(HL_URL, json={"type": "fundingHistory", "coin": coin, "startTime": start, "endTime": end}, timeout=30)
        if r.status_code == 429:
            time.sleep(5)
            continue
        r.raise_for_status()
        chunk = r.json()
        if not chunk:
            break
        rows += chunk
        last = chunk[-1]["time"]
        if last <= start:
            break
        start = last + 1
        if len(chunk) < 500:
            break
    if not rows:
        return coin, "no funding data"
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["time"], unit="ms")
    df = df[["datetime", "fundingRate"]].drop_duplicates("datetime").sort_values("datetime")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return coin, f"{len(df)} rows"


def bn_fetch(sym):
    out = CACHE / "binance_funding" / f"{sym}_funding.csv"
    if out.exists():
        return sym, "cached"
    start = int(pd.Timestamp("2019-09-01").timestamp() * 1000)
    rows = []
    while True:
        r = requests.get(BN_URL, params={"symbol": sym, "startTime": start, "limit": 1000}, timeout=30)
        if r.status_code != 200:
            return sym, f"http {r.status_code}"
        chunk = r.json()
        if not chunk:
            break
        rows += chunk
        start = chunk[-1]["fundingTime"] + 1
        if len(chunk) < 1000:
            break
    if not rows:
        return sym, "no funding data"
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["fundingTime"], unit="ms")
    df["rate"] = df["fundingRate"].astype(float)
    df = df[["ts", "rate"]].drop_duplicates("ts").sort_values("ts")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return sym, f"{len(df)} rows"


if __name__ == "__main__":
    bn_syms = sys.argv[1:]
    print(f"Moon Dev: {len(bn_syms)} Binance symbols")
    for sym in bn_syms:
        print("Moon Dev Binance funding", *bn_fetch(sym), flush=True)
    coins = hl_coin_list()
    print(f"Moon Dev: {len(coins)} Hyperliquid coins need funding from the public endpoint (about 1 call a second allowed)", flush=True)
    with ThreadPoolExecutor(2) as ex:
        for coin, msg in ex.map(hl_fetch, coins):
            print(f"Moon Dev HL funding {coin}: {msg}", flush=True)
    print("Moon Dev: funding fetch done")
