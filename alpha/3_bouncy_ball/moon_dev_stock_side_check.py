"""
Moon Dev's stock side check for the bouncy ball short (package 3).

Universe: today's iShares IWM holdings (survivorship: it is the current list).
Screen: daily yfinance, keep tickers that closed 40% or more under the 30 day high.
Test: hourly bars (Yahoo caps 1h at 730 days). Bouncy ball short vs chase the crash.
Costs: 4.5 bp fee and 10 bp slippage a side, plus a borrow GRID (5, 25, 100 pct a year).
Real data only. Anything that fails goes in failed_parts and the run moves on.
Writes stock_side_check.json next to this file. Cache lives in data_cache/.
"""
import io
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

HERE = Path(__file__).resolve().parent
CACHE = HERE / "data_cache"
CACHE.mkdir(exist_ok=True)
OUT = HERE / "stock_side_check.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"}
IWM_URLS = [
    "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
    "https://www.blackrock.com/us/individual/products/239710/ishares-russell-2000-etf/1464253357814.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
]
D = 0.40
P = 3
FEE = 0.00045
SLIP = 0.0010
BORROW_GRID = [5, 25, 100]
TIME_STOP = 40
SPLIT = pd.Timestamp("2025-07-01")

failed = []
data_used = []


def parse_ishares_csv(text):
    """Moon Dev: skip the header lines, keep Equity rows, return tickers."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("Ticker,")), None)
    if start is None:
        raise ValueError("no Ticker header in body")
    df = pd.read_csv(io.StringIO("\n".join(lines[start:])), on_bad_lines="skip")
    df = df[df["Asset Class"] == "Equity"]
    tick = df["Ticker"].astype(str).str.strip()
    tick = tick[tick.str.fullmatch(r"[A-Z]{1,5}")].unique().tolist()
    return tick


def load_universe():
    """Moon Dev: try the public holdings CSVs, then a local copy in data_cache."""
    for url in IWM_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=30)
            body = r.text
        except Exception as e:
            failed.append(f"universe {url[:40]}: {e}")
            continue
        if r.status_code != 200 or body.lstrip().startswith("<"):
            failed.append(f"universe {url.split('/')[2]}: status {r.status_code}, body is HTML not CSV")
            continue
        tick = parse_ishares_csv(body)
        (CACHE / "IWM_holdings.csv").write_text(body)
        data_used.append(f"iShares IWM holdings CSV from {url.split('/')[2]}")
        return tick
    local = CACHE / "IWM_holdings.csv"
    if local.exists():
        tick = parse_ishares_csv(local.read_text())
        data_used.append("iShares IWM holdings CSV, local copy in data_cache")
        return tick
    failed.append("universe: every IWM holdings source failed and no local copy in data_cache")
    return []


def crash_flag(close, high, n):
    return close <= (1 - D) * high.rolling(n).max()


def screen_daily(tickers):
    """Moon Dev: 2 years daily, keep names that closed 40 pct under the trailing 30 day high."""
    keep = []
    for i in range(0, len(tickers), 200):
        batch = tickers[i:i + 200]
        try:
            raw = yf.download(batch, period="2y", interval="1d", auto_adjust=True, threads=True,
                              group_by="ticker", progress=False)
        except Exception as e:
            failed.append(f"daily batch {i}: {e}")
            continue
        for t in batch:
            if t not in raw.columns.get_level_values(0):
                continue
            df = raw[t].dropna(subset=["Close"])
            if len(df) < 60:
                continue
            if crash_flag(df["Close"], df["High"], 30).any():
                keep.append(t)
        print(f"Moon Dev: daily batch {i // 200 + 1}, screened so far {len(keep)}")
    data_used.append("yfinance daily 2y auto_adjust for the screen")
    return keep


def load_hourly(tickers):
    out = {}
    for i in range(0, len(tickers), 100):
        batch = tickers[i:i + 100]
        try:
            raw = yf.download(batch, period="730d", interval="1h", auto_adjust=True, threads=True,
                              group_by="ticker", progress=False)
        except Exception as e:
            failed.append(f"hourly batch {i}: {e}")
            continue
        for t in batch:
            if t not in raw.columns.get_level_values(0):
                failed.append(f"hourly {t}: not returned")
                continue
            df = raw[t].dropna(subset=["Close"])
            if len(df) < 300:
                failed.append(f"hourly {t}: only {len(df)} bars")
                continue
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
            out[t] = df[["Open", "High", "Low", "Close"]]
            df.to_parquet(CACHE / f"yf_{t}_1h.parquet")
    data_used.append("yfinance hourly period 730d (Yahoo caps 1h history at 730 days)")
    return out


def pivots(high, low):
    """Moon Dev: swing high or low with P bars each side, known P bars later. Returns index of confirm bar."""
    h = high.values
    l = low.values
    n = len(h)
    sh = np.zeros(n, bool)
    sl = np.zeros(n, bool)
    for i in range(P, n - P):
        win_h = h[i - P:i + P + 1]
        win_l = l[i - P:i + P + 1]
        if h[i] == win_h.max() and (win_h == h[i]).sum() == 1:
            sh[i] = True
        if l[i] == win_l.min() and (win_l == l[i]).sum() == 1:
            sl[i] = True
    return sh, sl


def run_trade(df, i_entry, stop, time_stop):
    """Moon Dev: short at open of bar i_entry. Returns exit index, exit price, gross return."""
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    entry = o[i_entry]
    target = entry - 2 * (stop - entry)
    last = min(i_entry + time_stop - 1, len(df) - 1)
    for j in range(i_entry, last + 1):
        if h[j] >= stop:
            return j, stop
        if l[j] <= target:
            return j, target
    return last, c[last]


def ball_trades(df, n, b, r_max):
    sh, sl = pivots(df["High"], df["Low"])
    crash = crash_flag(df["Close"], df["High"], n).values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    trades = []
    i = 0
    N = len(df)
    while i < N - P - 1:
        k = i - P
        if k < 0 or not sh[k]:
            i += 1
            continue
        # a swing high at k just got confirmed at bar i
        if not crash[max(0, i - n + 1):i + 1].any():
            i += 1
            continue
        highs = [j for j in range(max(0, k - n), k + 1) if sh[j]]
        if len(highs) < b + 1:
            i += 1
            continue
        seq = highs[-(b + 1):]
        if not all(h[seq[m + 1]] < h[seq[m]] for m in range(b)):
            i += 1
            continue
        lows_before = [j for j in range(seq[-2], seq[-1]) if sl[j]]
        lows_before2 = [j for j in range(seq[-3] if b >= 2 else max(0, seq[-2] - n), seq[-2]) if sl[j]]
        if not lows_before or not lows_before2:
            i += 1
            continue
        bounce_new = h[seq[-1]] - l[lows_before[-1]]
        bounce_old = h[seq[-2]] - l[lows_before2[-1]]
        if bounce_old <= 0 or bounce_new > r_max * bounce_old or c[i] >= h[k]:
            i += 1
            continue
        stop = h[k] * 1.003
        j, px = run_trade(df, i + 1, stop, TIME_STOP)
        trades.append((df.index[i + 1], df.index[j], df["Open"].values[i + 1], px))
        i = j + 1
    return trades


def chase_trades(df, n):
    crash = crash_flag(df["Close"], df["High"], n).values
    trades = []
    i = 1
    N = len(df)
    while i < N - 1:
        if crash[i] and not crash[i - 1]:
            entry = df["Open"].values[i + 1]
            j, px = run_trade(df, i + 1, entry * 1.15, TIME_STOP)
            trades.append((df.index[i + 1], df.index[j], entry, px))
            i = j + 1
        else:
            i += 1
    return trades


def net_returns(trades, sym, borrow_pct):
    rows = []
    for t_in, t_out, entry, exit_px in trades:
        gross = (entry - exit_px) / entry
        hours = max((t_out - t_in).total_seconds() / 3600, 1.0)
        borrow = borrow_pct / 100 * hours / (365 * 24)
        rows.append({"symbol": sym, "entry_time": t_in, "ret": gross - 2 * (FEE + SLIP) - borrow})
    return rows


def stats(name, n, borrow_pct, rows):
    df = pd.DataFrame(rows)
    out = {"name": name, "N": n, "borrow_pct_year": borrow_pct, "trades": len(df)}
    if df.empty:
        out.update({k: 0 for k in ["avg_trade_pct", "median_trade_pct", "t_stat", "win_rate", "profit_factor",
                                   "symbols_traded", "symbols_positive_pct", "pre_2025_07_avg",
                                   "post_2025_07_avg", "pre_trades", "post_trades"]})
        return out
    r = df["ret"]
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    by_sym = df.groupby("symbol")["ret"].sum()
    pre = df[df["entry_time"] < SPLIT]["ret"]
    post = df[df["entry_time"] >= SPLIT]["ret"]
    out.update({
        "avg_trade_pct": round(r.mean() * 100, 4),
        "median_trade_pct": round(r.median() * 100, 4),
        "t_stat": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))), 3) if len(r) > 1 else 0,
        "win_rate": round((r > 0).mean(), 4),
        "profit_factor": round(wins / losses, 3) if losses > 0 else None,
        "symbols_traded": int(by_sym.size),
        "symbols_positive_pct": round((by_sym > 0).mean(), 4),
        "pre_2025_07_avg": round(pre.mean() * 100, 4) if len(pre) else 0,
        "post_2025_07_avg": round(post.mean() * 100, 4) if len(post) else 0,
        "pre_trades": int(len(pre)),
        "post_trades": int(len(post)),
    })
    return out


def main():
    t0 = time.time()
    print("Moon Dev: stock side check for the bouncy ball short")
    universe = load_universe()
    result = {"universe_size": len(universe), "screened": 0, "hourly_loaded": 0,
              "survivorship_note": "Universe is today's IWM holdings list, so names that left the index "
                                   "(delisted, acquired, promoted) are missing. Survivorship bias is present.",
              "notes": ["Borrow cost is a grid of 5, 25, 100 pct a year, not a real borrow feed.",
                        "Yahoo caps hourly bars at 730 days, so the test covers about 2 years.",
                        "Holdout line is 2025-07-01."],
              "variants": [], "data_used": data_used, "failed_parts": failed}
    if not universe:
        print("Moon Dev: no universe, stopping. Failures:", failed)
        OUT.write_text(json.dumps(result, indent=2, default=str))
        return
    screened = screen_daily(universe)
    result["screened"] = len(screened)
    print(f"Moon Dev: {len(screened)} of {len(universe)} screened in")
    hourly = load_hourly(screened)
    result["hourly_loaded"] = len(hourly)
    print(f"Moon Dev: hourly loaded for {len(hourly)} tickers")

    specs = [("ball_B2_R1.0", 2, 1.0), ("ball_B3_R0.7", 3, 0.7)]
    for n in (30, 210):
        raw = {name: {} for name, _, _ in specs}
        raw["chase"] = {}
        for sym, df in hourly.items():
            for name, b, rr in specs:
                raw[name][sym] = ball_trades(df, n, b, rr)
            raw["chase"][sym] = chase_trades(df, n)
        for name, per_sym in raw.items():
            for bp in BORROW_GRID:
                rows = []
                for sym, tr in per_sym.items():
                    rows += net_returns(tr, sym, bp)
                result["variants"].append(stats(name, n, bp, rows))
    for v in result["variants"]:
        print(f"Moon Dev: {v['name']:14s} N={v['N']:3d} borrow={v['borrow_pct_year']:3d} trades={v['trades']:5d} "
              f"avg={v['avg_trade_pct']:.3f}% t={v['t_stat']} win={v['win_rate']} pf={v['profit_factor']}")
    OUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"Moon Dev: wrote {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
