"""
Moon Dev edge finder, package 3: the bouncy ball short, intraday, with a squeeze guard.

Claim (TheOneLanceB, about 7:10 to 8:20): after a crash, bounces get weaker, like a ball losing
energy. Short the failed bounce with a stop just above it. That beats chasing the crash.

The first pass (daily bars, 393 trades, -1.93% a trade) lost. This run asks: is there a version
with a real edge? Timeframes 15m, 1h, 4h (and daily for the comparison row), crash size, 2 or 3
bounces, bounce shrink rate, pivot width, exits, real funding, a slippage grid, and the squeeze guard.

Rule:
  crash  = close at least D under the highest high of the last N bars (N = 30 bars, or 30 clock days).
  pivots = swing highs and lows of width P bars each side, known P bars later (no look ahead).
  setup  = a crash within the last N bars, the last B swing highs inside the window each lower,
           each bounce (swing high minus the swing low before it) at most R times the bounce before,
           close under the newest swing high. Short at the next open. Stop = swing high x 1.003.
  chase  = short the next open after the first close that is D under the N bar high (the baseline).
           Stop = entry x (1 + 0.375 D) (15% for a 40% crash, same as the first pass).
  exits  = 2R, 3R, the crash low, ATR(14) x 3 trail, time stop 15 or 40 bars. Target style exits
           also die at 200 bars so no trade lives forever. A bar that touches stop and target counts
           as the stop.
  costs  = 4.5 bp fee a side, slippage 0 / 10 / 25 bp a side, real funding per event while held
           (shorts earn positive funding, pay negative funding).

Engine: a vectorized bar walker (numpy), not backtesting.py, because the grid is about 2,800 combos
on multi year 15m bars. Trades never overlap on one symbol (the next entry waits for the exit).
Holdout: knobs picked on trades entered before 2024-07-01, reported after. Headline = out of sample.
"""
import json
import sys
import time
from itertools import product
from pathlib import Path
import numpy as np
import pandas as pd
import moon_dev_bouncy_data as dat

HERE = Path(__file__).resolve().parent
FEE = 0.00045
STOP_PAD = 1.003
SPLIT = pd.Timestamp("2024-07-01")
CAP_BARS = 200
TF_MIN = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
GRID = dict(D=[0.20, 0.30, 0.40, 0.60], N=["30bars", "30days"], B=[2, 3], R=[1.0, 0.7, 0.5], P=[2, 3, 5],
            exit=["2R", "3R", "crash_low", "atr3_trail", "time15", "time40"])
HEADLINE_SLIP = 0.0010


# ------------------------------------------------------------ signals
def pivots(high, low, P):
    """Moon Dev: swing highs and lows of width P. Strict on the left, loose on the right, so flat tops give one pivot."""
    n = len(high)
    sh = np.zeros(n, bool)
    sl = np.zeros(n, bool)
    for k in range(1, P + 1):
        left_h = np.roll(high, k)
        right_h = np.roll(high, -k)
        left_l = np.roll(low, k)
        right_l = np.roll(low, -k)
        cond_h = (high > left_h) & (high >= right_h)
        cond_l = (low < left_l) & (low <= right_l)
        sh = cond_h if k == 1 else sh & cond_h
        sl = cond_l if k == 1 else sl & cond_l
    sh[:P] = sh[n - P:] = False
    sl[:P] = sl[n - P:] = False
    return np.flatnonzero(sh), np.flatnonzero(sl)


def roll_max(x, n):
    return pd.Series(x).rolling(n, min_periods=n).max().values


def roll_min(x, n):
    return pd.Series(x).rolling(n, min_periods=n).min().values


def atr14(df):
    h, l, c = df["High"].values, df["Low"].values, df["Close"].values
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(14, min_periods=14).mean().values


def ball_entries(df, piv, D, nbars, B, R, P):
    """Moon Dev: every bouncy ball setup. Returns the signal bar i (short at open of i+1), the stop, the crash low."""
    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    hh = roll_max(high, nbars)
    crash = close <= hh * (1 - D)
    crash_recent = pd.Series(crash).rolling(nbars, min_periods=1).max().values.astype(bool)
    crash_low = roll_min(low, nbars)
    sh_idx, sl_idx = piv
    if len(sh_idx) <= B:
        return np.empty(0, int), np.empty(0), np.empty(0)
    sh_val = high[sh_idx]
    # the last confirmed swing low before each swing high (must sit after the previous swing high)
    prev_low_pos = np.searchsorted(sl_idx, sh_idx) - 1
    has_low = prev_low_pos >= 0
    low_idx = np.where(has_low, sl_idx[np.clip(prev_low_pos, 0, None)], -1)
    bounce = np.where(has_low, sh_val - low[np.clip(low_idx, 0, None)], np.nan)
    k = np.arange(B - 1, len(sh_idx))
    i = sh_idx[k] + P  # confirmation bar
    ok = i < len(close) - 1
    ok &= crash_recent[np.clip(i, 0, len(close) - 1)]
    ok &= sh_idx[k - (B - 1)] > i - nbars
    ok &= close[np.clip(i, 0, len(close) - 1)] < sh_val[k]
    for b in range(1, B):
        ok &= sh_val[k - b + 1] < sh_val[k - b]
        ok &= low_idx[k - b + 1] > sh_idx[k - b]
        ok &= bounce[k - b + 1] <= R * bounce[k - b]
    ok &= ~np.isnan(crash_low[np.clip(i, 0, len(close) - 1)])
    sel = k[ok]
    return i[ok], sh_val[sel] * STOP_PAD, crash_low[i[ok]]


def chase_entries(df, D, nbars):
    """Moon Dev: the baseline. Signal bar = first close that is D under the N bar high."""
    high, low, close = df["High"].values, df["Low"].values, df["Close"].values
    crash = close <= roll_max(high, nbars) * (1 - D)
    onset = crash & ~np.roll(crash, 1)
    onset[0] = False
    i = np.flatnonzero(onset)
    i = i[i < len(close) - 1]
    crash_low = roll_min(low, nbars)
    return i, df["Open"].values[i + 1] * (1 + 0.375 * D), crash_low[i]


# ------------------------------------------------------------ simulator
def simulate(df, sig, stop, crash_low, exit_mode, atr):
    """Moon Dev: walk every entry forward in one 2D numpy pass, then drop overlaps on this symbol."""
    o, h, l, c = (df[x].values for x in ["Open", "High", "Low", "Close"])
    H = {"time15": 15, "time40": 40}.get(exit_mode, CAP_BARS)
    n = len(c)
    keep = sig + 1 + H < n
    sig, stop, crash_low = sig[keep], stop[keep], crash_low[keep]
    if len(sig) == 0:
        return pd.DataFrame()
    e = sig + 1
    entry = o[e]
    stop = np.maximum(stop, entry * 1.0005)
    risk = stop - entry
    if exit_mode == "2R":
        target = entry - 2 * risk
    elif exit_mode == "3R":
        target = entry - 3 * risk
    elif exit_mode == "crash_low":
        target = crash_low
    else:
        target = np.full(len(e), -1.0)
    good = target < entry * 0.999
    if exit_mode in ("2R", "3R", "crash_low"):
        e, entry, stop, risk, target, sig = e[good], entry[good], stop[good], risk[good], target[good], sig[good]
    if len(e) == 0:
        return pd.DataFrame()
    idx = e[:, None] + np.arange(H)[None, :]  # bars after entry, entry bar itself can hit the stop too
    hw, lw, cw, ow = h[idx], l[idx], c[idx], o[idx]
    if exit_mode == "atr3_trail":
        a = atr[e]
        trail = np.minimum(stop[:, None], np.minimum.accumulate(cw, axis=1) + 3 * a[:, None])
        trail = np.concatenate([stop[:, None], trail[:, :-1]], axis=1)  # the stop used on bar t comes from bars before t
        stop_hit = hw >= trail
        stop_px = np.maximum(trail, ow)
    else:
        stop_hit = hw >= stop[:, None]
        stop_px = np.maximum(stop[:, None], ow)
    tgt_hit = lw <= target[:, None]
    tgt_px = np.minimum(target[:, None], ow)
    first_stop = np.where(stop_hit.any(1), stop_hit.argmax(1), H)
    first_tgt = np.where(tgt_hit.any(1), tgt_hit.argmax(1), H)
    t_exit = np.minimum(np.minimum(first_stop, first_tgt), H - 1)
    rows = np.arange(len(e))
    reason = np.where(first_stop <= first_tgt, "stop", "target")
    reason = np.where((first_stop >= H) & (first_tgt >= H), "time", reason)
    exit_px = np.where(reason == "stop", stop_px[rows, np.clip(t_exit, 0, H - 1)],
                       np.where(reason == "target", tgt_px[rows, np.clip(t_exit, 0, H - 1)], cw[rows, H - 1]))
    exit_bar = e + t_exit
    # no overlapping trades on one symbol
    kept, last_exit = [], -1
    for r in range(len(e)):
        if e[r] > last_exit:
            kept.append(r)
            last_exit = exit_bar[r]
    kept = np.array(kept, int)
    t = df.index.values
    return pd.DataFrame({"entry_bar": e[kept], "exit_bar": exit_bar[kept], "entry_time": t[e[kept]],
                         "exit_time": t[exit_bar[kept]], "entry": entry[kept], "exit": exit_px[kept],
                         "stop": stop[kept], "reason": reason[kept],
                         "gross": (entry[kept] - exit_px[kept]) / entry[kept]})


class FundingBook:
    """Moon Dev: funding earned by a short between entry and exit, and the last rate at entry (the guard)."""

    def __init__(self, series):
        self.ok = series is not None and len(series) > 0
        if self.ok:
            self.t = series.index.values
            self.cum = np.concatenate([[0.0], np.cumsum(series.values)])
            self.rate = series.values

    def earned(self, entry_t, exit_t):
        if not self.ok:
            return np.full(len(entry_t), np.nan)
        a = np.searchsorted(self.t, entry_t, side="right")
        b = np.searchsorted(self.t, exit_t, side="right")
        return self.cum[b] - self.cum[a]

    def at_entry(self, entry_t):
        if not self.ok:
            return np.full(len(entry_t), np.nan)
        a = np.searchsorted(self.t, entry_t, side="right") - 1
        return np.where(a >= 0, self.rate[np.clip(a, 0, None)], np.nan)


def net_returns(tr, slip):
    fund = tr["funding"].fillna(0.0)
    return tr["gross"] - 2 * FEE - 2 * slip + fund


# ------------------------------------------------------------ stats
def stats(tr, n_symbols, slip=HEADLINE_SLIP, with_curve=False, closes=None):
    """Moon Dev: pooled trade stats plus an equal weight portfolio curve marked at the exit day."""
    if len(tr) == 0:
        return {"trades": 0, "avg_trade_pct": 0.0, "median_trade_pct": 0.0, "t_stat": 0.0, "win_rate": 0.0,
                "profit_factor": 0.0, "total_return_pct": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0,
                "buy_hold_return_pct": 0.0, "symbols_traded": 0, "symbols_positive_pct": 0.0}
    r = net_returns(tr, slip)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    sym_sum = r.groupby(tr["symbol"]).sum()
    out = {"trades": int(len(r)), "avg_trade_pct": round(r.mean() * 100, 3), "median_trade_pct": round(r.median() * 100, 3),
           "t_stat": round(float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if len(r) > 1 and r.std() > 0 else 0.0, 2),
           "win_rate": round((r > 0).mean() * 100, 1),
           "profit_factor": round(float(wins / losses), 2) if losses > 0 else 99.0,
           "symbols_traded": int(sym_sum.size), "symbols_positive_pct": round((sym_sum > 0).mean() * 100, 1)}
    daily = (r / n_symbols).groupby(pd.to_datetime(tr["exit_time"]).dt.floor("D")).sum()
    if closes is not None:
        hold = closes.pct_change(fill_method=None).mean(axis=1).fillna(0)
        hold = hold[(hold.index >= pd.Timestamp(tr["entry_time"].min()).floor("D")) & (hold.index <= daily.index.max())]
        daily = daily.reindex(hold.index, fill_value=0.0)
    else:
        hold = pd.Series(0.0, index=daily.index)
    eq = (1 + daily).cumprod()
    heq = (1 + hold).cumprod()
    out["total_return_pct"] = round((eq.iloc[-1] - 1) * 100, 2)
    out["sharpe"] = round(float(daily.mean() / daily.std() * np.sqrt(365)) if daily.std() > 0 else 0.0, 2)
    out["max_dd_pct"] = round(float((eq / eq.cummax() - 1).min() * 100), 2)
    out["buy_hold_return_pct"] = round((heq.iloc[-1] - 1) * 100, 2)
    if with_curve:
        out["_curve"] = [{"t": str(d.date()), "strategy": round(float(a), 5), "buy_hold": round(float(b), 5)}
                         for d, a, b in zip(eq.index, eq.values, heq.reindex(eq.index).ffill().values)]
    return out


def passes_bar(iss, oos, oos_2x):
    """Moon Dev: the plan's edge bar, judged on the out of sample numbers."""
    return (oos["trades"] > 0 and oos["avg_trade_pct"] > 0 and oos["t_stat"] >= 2 and oos["profit_factor"] >= 1.2
            and oos["symbols_positive_pct"] >= 55 and oos_2x["avg_trade_pct"] > 0)


# ------------------------------------------------------------ markets
def market_set(name):
    """Moon Dev: one market = {symbol: df} plus funding books. Returns (data, funding, tf)."""
    if name.startswith("binance_"):
        tf = name.split("_")[1]
        data = dat.load_binance(tf)
        fund = {s: FundingBook(dat.binance_funding(s)) for s in data}
    elif name == "hl_15m":
        tf = "15m"
        data = dat.load_hl_15m()
        fund = {s: FundingBook(dat.hl_funding(s, df.index.min() - pd.Timedelta("1D"), df.index.max() + pd.Timedelta("1D")))
                for s, df in data.items()}
    elif name == "hl_4h":
        tf = "4h"
        data = dat.load_hl_4h()
        fund = {s: FundingBook(dat.hl_funding(s, df.index.min() - pd.Timedelta("1D"), df.index.max() + pd.Timedelta("1D")))
                for s, df in data.items()}
    elif name == "hl_1d":
        tf = "1d"
        data = dat.load_hl_daily()
        fund = {}
        for s in data:  # local funding files only for the 123 coin daily set, the rest is tagged no funding data
            f1 = dat.MOON / "hyperliquid_funding" / f"{s}_funding_hl.csv"
            f2 = dat.MOON / "hyperliquid_meme" / f"{s}_funding_hl.csv"
            fund[s] = FundingBook(dat.hl_funding(s, None, None)) if (f1.exists() or f2.exists()) else FundingBook(None)
    else:
        raise ValueError(name)
    return data, fund, tf


def run_grid(name, data, fund, tf, grid_rows, trade_store):
    """Moon Dev: every combo on every symbol of one market. Stores trades keyed by the combo for later slicing."""
    t0 = time.time()
    nsym = len(data)
    piv_cache = {(s, P): pivots(data[s]["High"].values, data[s]["Low"].values, P) for s in data for P in GRID["P"]}
    atr_cache = {s: atr14(df) for s, df in data.items()}
    combos = list(product(GRID["D"], GRID["N"], GRID["B"], GRID["R"], GRID["P"]))
    chase_combos = list(product(GRID["D"], GRID["N"]))
    done = 0
    for mode, combo_list in [("ball", combos), ("chase", chase_combos)]:
        for combo in combo_list:
            if mode == "ball":
                D, N, B, R, P = combo
            else:
                D, N = combo
                B, R, P = 0, 0.0, 0
            per_exit = {ex: [] for ex in GRID["exit"]}
            for s, df in data.items():
                nbars = 30 if N == "30bars" else int(30 * 1440 / TF_MIN[tf])
                if nbars >= len(df):
                    continue
                if mode == "ball":
                    sig, stop, clow = ball_entries(df, piv_cache[(s, P)], D, nbars, B, R, P)
                else:
                    sig, stop, clow = chase_entries(df, D, nbars)
                if len(sig) == 0:
                    continue
                for ex in GRID["exit"]:
                    tr = simulate(df, sig, stop, clow, ex, atr_cache[s])
                    if len(tr):
                        tr["symbol"] = s
                        tr["funding"] = fund[s].earned(tr["entry_time"].values, tr["exit_time"].values)
                        tr["funding_at_entry"] = fund[s].at_entry(tr["entry_time"].values)
                        per_exit[ex].append(tr)
            for ex in GRID["exit"]:
                params = {"market": name, "tf": tf, "mode": mode, "D": D, "N": N, "B": B, "R": R, "P": P, "exit": ex}
                key = json.dumps(params, sort_keys=True)
                tr = pd.concat(per_exit[ex], ignore_index=True) if per_exit[ex] else pd.DataFrame()
                trade_store[key] = tr
                iss = tr[tr["entry_time"] < SPLIT] if len(tr) else tr
                oos = tr[tr["entry_time"] >= SPLIT] if len(tr) else tr
                a, i_, o_ = stats(tr, nsym), stats(iss, nsym), stats(oos, nsym)
                grid_rows.append({"params": params, "trades": a["trades"], "avg_trade_pct": a["avg_trade_pct"],
                                  "t_stat": a["t_stat"], "profit_factor": a["profit_factor"],
                                  "total_return_pct": a["total_return_pct"],
                                  "is_trades": i_["trades"], "is_avg_trade_pct": i_["avg_trade_pct"], "is_t_stat": i_["t_stat"],
                                  "oos_trades": o_["trades"], "oos_avg_trade_pct": o_["avg_trade_pct"], "oos_t_stat": o_["t_stat"],
                                  "oos_profit_factor": o_["profit_factor"], "no_funding_trades": int(tr["funding"].isna().sum()) if len(tr) else 0})
            done += 1
            if done % 60 == 0:
                print(f"Moon Dev: {name} {done}/{len(combos) + len(chase_combos)} combos, {time.time() - t0:.0f}s")
    print(f"Moon Dev: {name} grid done in {time.time() - t0:.0f}s, {nsym} symbols")


if __name__ == "__main__":
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    markets = only or ["binance_15m", "binance_1h", "binance_4h", "hl_15m", "hl_4h", "hl_1d"]
    pkl = HERE / "data_cache" / "grid_store.pkl"
    old = pd.read_pickle(pkl) if pkl.exists() else {"grid": [], "store": {}, "meta": {}}
    grid_rows = [r for r in old["grid"] if r["params"]["market"] not in markets]
    store = {k: v for k, v in old["store"].items() if json.loads(k)["market"] not in markets}
    meta = {k: v for k, v in old["meta"].items() if k not in markets}
    for m in markets:
        data, fund, tf = market_set(m)
        meta[m] = {"tf": tf, "n_symbols": len(data), "start": str(min(df.index.min() for df in data.values()).date()),
                   "end": str(max(df.index.max() for df in data.values()).date()),
                   "no_funding_symbols": [s for s in data if not fund[s].ok]}
        run_grid(m, data, fund, tf, grid_rows, store)
        closes = pd.concat({s: df["Close"].resample("1D").last() for s, df in data.items()}, axis=1)
        closes.to_parquet(HERE / "data_cache" / f"closes_{m}.parquet")
        pd.to_pickle({"grid": grid_rows, "store": store, "meta": meta}, pkl)  # save after every market
        print(f"Moon Dev: grid saved to data_cache/grid_store.pkl after {m}")
