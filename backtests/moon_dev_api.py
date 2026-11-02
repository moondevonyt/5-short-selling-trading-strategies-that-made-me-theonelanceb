"""
🌙 Moon Dev API helper (docs: https://moondev.com/docs)

Two real endpoints this repo uses:
  recent_liquidations(tf)   GET /api/liquidations/{tf}.json   Hyperliquid liquidations, latest 100 events
                            plus window stats (tf: 10m, 1h, 4h, 12h, 24h, 2d, 7d, 14d, 30d)
  near_liq_positions(coin)  GET /api/positions/all.json       large positions ($75k+) closest to their
                            liquidation price, 50 longs and 50 shorts per coin, 296 coins
  near_liq_totals()         same call, one row per coin: how many longs and shorts sit near liquidation
                            and how much money they hold (the "fuel" for a squeeze)

The key lives in .env as MOONDEV_API_KEY and is never printed. Get one at https://moondev.com
Wallet addresses that the API returns are dropped here, so nothing in this repo carries an address.
"""
# 🌙 Moon Dev API (docs: https://moondev.com/docs). The key lives in .env as MOONDEV_API_KEY and is never printed.
import os, requests
from dotenv import load_dotenv
load_dotenv("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/.env"); load_dotenv()   # Moon Dev's key first, then the reader's own .env
H = {"X-API-Key": os.getenv("MOONDEV_API_KEY")}

import pandas as pd

BASE = "https://api.moondev.com"
LIQ_COLS = ["timestamp", "coin", "side", "size", "price", "value_usd", "pnl"]
POS_COLS = ["coin", "side", "value", "entry_price", "current_price", "liq_price", "distance_pct", "leverage", "size", "pnl"]


def _get(path, **params):
    if not H["X-API-Key"]:
        raise SystemExit("Moon Dev: set MOONDEV_API_KEY in .env (https://moondev.com/docs)")
    r = requests.get(BASE + path, headers=H, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def recent_liquidations(tf="1h"):
    """Moon Dev: the latest 100 Hyperliquid liquidations as a DataFrame (newest first).
    df.attrs["stats"] holds the whole window's totals and the per coin split (long vs short value)."""
    j = _get(f"/api/liquidations/{tf}.json")
    df = pd.DataFrame(j["liquidations"])[LIQ_COLS]
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.attrs["stats"] = {k: v for k, v in j["stats"].items() if k != "largest"}  # Moon Dev: largest carries addresses, dropped
    df.attrs["tf"] = tf
    print(f"Moon Dev API: /api/liquidations/{tf}.json -> {len(df)} rows, {df['timestamp'].min()} to {df['timestamp'].max()}, "
          f"{j['stats']['total_count']:,} liquidations in the {tf} window")
    return df


def _positions_all():
    j = _get("/api/positions/all.json")
    print(f"Moon Dev API: /api/positions/all.json -> {j['total_symbols']} coins, updated {j['updated_at']}")
    return j


def near_liq_positions(coin=None):
    """Moon Dev: positions closest to liquidation (50 longs + 50 shorts per coin), one coin or every coin."""
    j = _positions_all()
    syms = {coin: j["symbols"][coin]} if coin else j["symbols"]
    rows = []
    for c, d in syms.items():
        for side in ("longs", "shorts"):
            for p in d[side]:
                rows.append({**p, "coin": c, "side": side[:-1]})
    df = pd.DataFrame(rows)[POS_COLS]
    df.attrs["updated_at"] = j["updated_at"]
    print(f"Moon Dev API: {len(df)} near liquidation positions for {len(syms)} coin(s)")
    return df


def near_liq_totals():
    """Moon Dev: one row per coin: count and dollar value of longs and shorts sitting near liquidation."""
    j = _positions_all()
    df = pd.DataFrame([{"coin": c, "longs": d["total_longs"], "shorts": d["total_shorts"],
                        "long_value": d["total_long_value"], "short_value": d["total_short_value"]}
                       for c, d in j["symbols"].items()]).set_index("coin")
    df.attrs["updated_at"] = j["updated_at"]
    return df


if __name__ == "__main__":
    liq = recent_liquidations("1h")
    print(liq.head())
    tot = near_liq_totals()
    print(tot.loc[["BTC", "ETH", "SOL", "XRP"]])
