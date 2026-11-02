"""
Moon Dev's Right Side of the V engine (TheOneLanceB strategy 1 and 2, about 2:40 to 4:40 in the video).

One fast walk forward simulator (numba) that runs his rule on any bar size, with every real cost:
fees, slippage, and the REAL funding paid or earned each bar held (shorts get paid when funding is positive).

Rule (his words, our numbers):
  run      : high >= K x the lowest low of the last N bars
  the turn : after the peak, a green bar whose high stays under the peak is the lower high
  entry    : lower high break = close under that bar's low and under the 10 EMA, short the next open
             call the top    = first red close within 3 bars of the peak (the thing he says NOT to do)
             ema cross       = first close under the 10 EMA after the peak, no lower high needed
  stop     : just above the lower high (or the peak for the other two entries)
  exits    : close over 10 EMA, close over 20 EMA, ATR(14) x 3 trailing stop, 2R, 3R, time stop 10 / 30 bars

Real data only. A bar with no funding data is tagged, never charged zero in silence.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import talib
from numba import njit

HERE = Path(__file__).parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "backtests"))
from moon_dev_common import load_hl_daily, DATA_DIR  # noqa: E402  (first pass loader, reused)

CACHE = HERE / "data_cache"
MOON26 = Path("/Volumes/Moon 26/tick_data/binance")
FEE_BP = 4.5             # Hyperliquid taker, per side
PEAK_WINDOW = 20         # bars after the peak we still look for the short
MAX_HOLD = 60            # hard cap on bars held, every exit mode
OOS_START = pd.Timestamp("2024-07-01")

ENTRY = {"lower_high": 0, "call_top": 1, "ema_cross": 2}
EXIT = {"ema10": 0, "ema20": 1, "atr3_trail": 2, "target_2R": 3, "target_3R": 4, "time_10": 5, "time_30": 6}
REASON = {0: "stop", 1: "ema", 2: "trail", 3: "target", 4: "time", 5: "max_hold", 6: "end"}
BARS_PER_DAY = {"hl_1d": 1, "hl_8h": 3, "hl_4h": 6, "bn_1h": 24, "stocks_1d": 1}
BAR_LEN = {"hl_1d": pd.Timedelta("1D"), "hl_8h": pd.Timedelta("8h"), "hl_4h": pd.Timedelta("4h"),
           "bn_1h": pd.Timedelta("1h"), "stocks_1d": pd.Timedelta("1D")}


# ----------------------------------------------------------------------------------------------- data
def _hl_csv(f):
    df = pd.read_csv(f, parse_dates=["datetime"]).set_index("datetime").sort_index()
    df = df.rename(columns=str.capitalize)[["Open", "High", "Low", "Close", "Volume"]]
    return df[~df.index.duplicated()]


def load_market(market):
    """Moon Dev: {symbol: OHLCV frame} for one market. Fails if the files are not there."""
    if market == "hl_1d":
        return load_hl_daily()
    if market == "hl_8h":
        out = {f.name.split("_")[0]: _hl_csv(f) for f in sorted((DATA_DIR / "hyperliquid_8h").glob("*_8h_hl.csv"))}
    elif market == "hl_4h":
        out = {f.name.split("_")[0]: _hl_csv(f) for f in sorted((DATA_DIR / "hyperliquid_meme").glob("*_4h_hl.csv"))}
    elif market == "bn_1h":
        out = {}
        for d in sorted(MOON26.glob("futures_klines_1m/*/")):
            allin = sorted(d.glob(f"{d.name}_1m_*.parquet"))
            if not allin:
                continue
            cache = CACHE / "bn_1h" / f"{d.name}_1h.parquet"
            if cache.exists():
                out[d.name] = pd.read_parquet(cache)
                continue
            m = pd.read_parquet(allin[-1], columns=["open_time", "open", "high", "low", "close", "volume"])
            m["open_time"] = pd.to_datetime(m["open_time"]).dt.tz_localize(None)
            m = m.set_index("open_time").sort_index()
            h = m.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
            h = h.rename(columns=str.capitalize)
            cache.parent.mkdir(parents=True, exist_ok=True)
            h.to_parquet(cache)
            out[d.name] = h
    elif market == "stocks_1d":
        out = {}
        for f in sorted((CACHE / "stocks").glob("*_1d.csv")):
            df = pd.read_csv(f, index_col=0, parse_dates=True).sort_index()
            out[f.name.split("_")[0]] = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    else:
        raise ValueError(market)
    out = {k: v for k, v in out.items() if len(v) >= 120}
    print(f"Moon Dev: loaded {len(out)} symbols for {market}")
    return out


def load_funding(symbol, market):
    """Moon Dev: hourly (HL) or 8h (Binance) funding rates as a Series, or None if no data anywhere."""
    if market.startswith("hl"):
        for f in [DATA_DIR / "hyperliquid_funding" / f"{symbol}_funding_hl.csv",
                  CACHE / "hl_funding" / f"{symbol}_funding_hl.csv"]:
            if f.exists():
                df = pd.read_csv(f, parse_dates=["datetime"])
                return df.set_index("datetime")["fundingRate"].astype(float).sort_index()
        f = DATA_DIR / "hyperliquid_meme" / f"{symbol}_funding_hl.csv"
        if f.exists():
            df = pd.read_csv(f)
            df["dt"] = pd.to_datetime(df["time"], unit="ms").dt.floor("h")
            return df.drop_duplicates("dt").set_index("dt")["fundingRate"].astype(float).sort_index()
        return None
    if market == "bn_1h":
        for f in [MOON26 / "funding" / f"{symbol}_funding.csv", CACHE / "binance_funding" / f"{symbol}_funding.csv"]:
            if f.exists():
                df = pd.read_csv(f)
                ts = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_localize(None).dt.floor("h")
                return pd.Series(df["rate"].astype(float).values, index=ts).sort_index()
        return None
    return None  # stocks: no funding, borrow is a grid in stocks.py


def funding_per_bar(index, bar_len, fr):
    """Moon Dev: sum of funding rates inside each bar [t, t + bar_len), and whether the bar is covered."""
    n = len(index)
    if fr is None or len(fr) == 0:
        return np.zeros(n), np.zeros(n, dtype=np.bool_)
    cs = fr.cumsum()
    start = np.searchsorted(fr.index.values, index.values, side="left")
    end = np.searchsorted(fr.index.values, (index + bar_len).values, side="left")
    tot = np.concatenate([[0.0], cs.values])
    per = tot[end] - tot[start]
    covered = (index.values >= fr.index.values[0]) & ((index + bar_len).values <= fr.index.values[-1] + pd.Timedelta("1h"))
    return per, covered


def btc_bear_flags(index, bar_len):
    """Moon Dev: True when BTC's last completed daily close is under its 50 day SMA."""
    btc = _hl_csv(DATA_DIR / "hyperliquid_midcap" / "BTC_1d_hl.csv")
    sma = btc["Close"].rolling(50).mean()
    bear = (btc["Close"] < sma).astype(float)
    bear.index = bear.index + pd.Timedelta("1D")  # known at that day's close
    close_times = pd.Series((index + bar_len).values)
    m = pd.merge_asof(pd.DataFrame({"t": close_times}), bear.rename("bear").reset_index().rename(columns={"datetime": "t"}),
                      on="t", direction="backward")
    return m["bear"].fillna(0).values.astype(np.bool_)


def prep_symbol(df, market, fr):
    """Moon Dev: every array the simulator needs, computed once per symbol."""
    c = df["Close"].values.astype(float)
    arrs = dict(o=df["Open"].values.astype(float), h=df["High"].values.astype(float),
                l=df["Low"].values.astype(float), c=c, v=df["Volume"].values.astype(float),
                ema10=np.nan_to_num(talib.EMA(c, 10), nan=np.inf), ema20=np.nan_to_num(talib.EMA(c, 20), nan=np.inf),
                atr=np.nan_to_num(talib.ATR(df["High"].values.astype(float), df["Low"].values.astype(float), c, 14), nan=0.0))
    arrs["base10"] = df["Low"].rolling(10).min().bfill().values.astype(float)
    arrs["base30"] = df["Low"].rolling(30).min().bfill().values.astype(float)
    fund, cov = funding_per_bar(df.index, BAR_LEN[market], fr)
    arrs["fund"], arrs["fund_cov"] = fund, cov
    win = 30 * BARS_PER_DAY[market]
    med = pd.Series(fund).rolling(win, min_periods=win // 2).median().values
    arrs["fund_hi"] = (fund > np.nan_to_num(med, nan=np.inf)) & cov
    arrs["btc_bear"] = btc_bear_flags(df.index, BAR_LEN[market]) if market != "stocks_1d" else np.zeros(len(c), dtype=np.bool_)
    return arrs


# ------------------------------------------------------------------------------------------ simulator
@njit(cache=True)
def simulate(o, h, l, c, v, ema10, ema20, atr, base, fund, fund_cov, btc_bear, fund_hi,
             K, entry_mode, exit_mode, use_btc, use_fund, vol_ratio, max_delay, fee, slip, peak_window, max_hold):
    """Moon Dev: walk forward, one bar at a time, only using what we knew at that bar's close."""
    n = len(c)
    cap = 4000
    t_entry_i = np.zeros(cap, np.int64); t_exit_i = np.zeros(cap, np.int64)
    t_entry = np.zeros(cap); t_exit = np.zeros(cap); t_stop = np.zeros(cap)
    t_ret = np.zeros(cap); t_fund = np.zeros(cap); t_cov = np.zeros(cap, np.bool_)
    t_reason = np.zeros(cap, np.int64); t_peak_i = np.zeros(cap, np.int64); t_lh_i = np.zeros(cap, np.int64)
    bar_ret = np.zeros(n)
    nt = 0
    peak = np.nan; peak_i = -999999; peak_vol = 0.0
    lh = np.nan; lh_low = np.nan; lh_i = -1; fired = True
    in_pos = False; pend_entry = False; pend_exit = False; pend_reason = 0
    sig_stop = 0.0; sig_peak_i = 0; sig_lh_i = 0
    entry_i = 0; entry_px = 0.0; stop = 0.0; target = np.inf; trail = np.inf
    fsum = 0.0; fcov = True; prev_mark = 0.0
    for i in range(30, n):
        # ---- fills at this bar's open (orders placed on the last close)
        if pend_entry:
            pend_entry = False
            if sig_stop > o[i]:
                in_pos = True; entry_i = i; entry_px = o[i] * (1.0 - slip); stop = sig_stop
                r = stop - entry_px
                target = entry_px - 2.0 * r if exit_mode == 3 else (entry_px - 3.0 * r if exit_mode == 4 else -np.inf)
                trail = stop
                fsum = 0.0; fcov = True; prev_mark = entry_px
        if in_pos:
            exit_px = -1.0; reason = 0
            if pend_exit:
                exit_px = o[i] * (1.0 + slip); reason = pend_reason; pend_exit = False
            elif h[i] >= stop:
                exit_px = (o[i] if o[i] >= stop else stop) * (1.0 + slip); reason = 0
            elif exit_mode == 2 and h[i] >= trail:
                exit_px = (o[i] if o[i] >= trail else trail) * (1.0 + slip); reason = 2
            elif (exit_mode == 3 or exit_mode == 4) and l[i] <= target:
                exit_px = (o[i] if o[i] <= target else target) * (1.0 + slip); reason = 3
            fsum += fund[i]
            if not fund_cov[i]:
                fcov = False
            if exit_px > 0:
                bar_ret[i] = -(exit_px / prev_mark - 1.0) - fee + fund[i]
                if i == entry_i:
                    bar_ret[i] -= fee
                ret = (entry_px - exit_px) / entry_px - 2.0 * fee + fsum
                t_entry_i[nt] = entry_i; t_exit_i[nt] = i; t_entry[nt] = entry_px; t_exit[nt] = exit_px
                t_stop[nt] = stop; t_ret[nt] = ret; t_fund[nt] = fsum; t_cov[nt] = fcov; t_reason[nt] = reason
                t_peak_i[nt] = sig_peak_i; t_lh_i[nt] = sig_lh_i
                nt += 1
                in_pos = False
                if nt >= cap:
                    break
            else:
                bar_ret[i] = -(c[i] / prev_mark - 1.0) + fund[i]
                if i == entry_i:
                    bar_ret[i] -= fee
                prev_mark = c[i]
                if exit_mode == 2:
                    t2 = l[i] + 3.0 * atr[i]
                    if t2 < trail:
                        trail = t2
                held = i - entry_i
                if held >= max_hold:
                    pend_exit = True; pend_reason = 5
                elif exit_mode == 0 and c[i] > ema10[i]:
                    pend_exit = True; pend_reason = 1
                elif exit_mode == 1 and c[i] > ema20[i]:
                    pend_exit = True; pend_reason = 1
                elif exit_mode == 5 and held >= 10:
                    pend_exit = True; pend_reason = 4
                elif exit_mode == 6 and held >= 30:
                    pend_exit = True; pend_reason = 4
        # ---- the setup: run, peak, lower high, break
        if h[i] >= base[i] * K and (np.isnan(peak) or h[i] > peak or i - peak_i > peak_window):
            peak = h[i]; peak_i = i; peak_vol = v[i]; lh = np.nan; lh_low = np.nan; lh_i = -1; fired = False
            continue
        if i - peak_i > peak_window or fired:
            continue
        sig = False
        if entry_mode == 1:
            if i - peak_i <= 3 and c[i] < o[i]:
                sig = True; sig_stop = peak; sig_lh_i = i
        elif entry_mode == 2:
            if c[i] < ema10[i]:
                sig = True; sig_stop = peak; sig_lh_i = i
        else:
            if not np.isnan(lh) and c[i] < lh_low and c[i] < ema10[i]:
                sig = True; sig_stop = lh; sig_lh_i = lh_i
                if vol_ratio > 0 and not (v[lh_i] < vol_ratio * peak_vol):
                    sig = False
                if max_delay > 0 and lh_i - peak_i > max_delay:
                    sig = False
                fired = True  # his rule fires once per peak, taken or not
            if not fired and c[i] > c[i - 1] and h[i] < peak:
                lh = h[i]; lh_low = l[i]; lh_i = i
        if sig:
            if entry_mode != 0:
                fired = True
            if use_btc and not btc_bear[i]:
                sig = False
            if use_fund and not fund_hi[i]:
                sig = False
        if sig and not in_pos and not pend_entry and i + 1 < n:
            pend_entry = True; sig_peak_i = peak_i
    if in_pos:  # still short at the end of the data: close at the last close
        exit_px = c[n - 1] * (1.0 + slip)
        ret = (entry_px - exit_px) / entry_px - 2.0 * fee + fsum
        t_entry_i[nt] = entry_i; t_exit_i[nt] = n - 1; t_entry[nt] = entry_px; t_exit[nt] = exit_px
        t_stop[nt] = stop; t_ret[nt] = ret; t_fund[nt] = fsum; t_cov[nt] = fcov; t_reason[nt] = 6
        t_peak_i[nt] = sig_peak_i; t_lh_i[nt] = sig_lh_i
        nt += 1
    return (t_entry_i[:nt], t_exit_i[:nt], t_entry[:nt], t_exit[:nt], t_stop[:nt], t_ret[:nt], t_fund[:nt],
            t_cov[:nt], t_reason[:nt], t_peak_i[:nt], t_lh_i[:nt], bar_ret)


def run_combo(prepped, K, N, entry, exit_, use_btc=False, use_fund=False, vol_ratio=0.0, max_delay=0,
              fee_bp=FEE_BP, slip_bp=10.0):
    """Moon Dev: one parameter combo over every symbol of a market. Returns (trade table, bar returns by symbol)."""
    rows, bar_rets = [], {}
    for sym, (df, a) in prepped.items():
        out = simulate(a["o"], a["h"], a["l"], a["c"], a["v"], a["ema10"], a["ema20"], a["atr"], a[f"base{N}"],
                       a["fund"], a["fund_cov"], a["btc_bear"], a["fund_hi"], float(K), ENTRY[entry], EXIT[exit_],
                       use_btc, use_fund, float(vol_ratio), int(max_delay), fee_bp / 1e4, slip_bp / 1e4,
                       PEAK_WINDOW, MAX_HOLD)
        ei, xi, ep, xp, st, rt, fs, cv, rs, pk, lh, br = out
        bar_rets[sym] = pd.Series(br, index=df.index)
        if len(ei):
            rows.append(pd.DataFrame({"symbol": sym, "entry_time": df.index[ei], "exit_time": df.index[xi], "entry": ep,
                                      "exit": xp, "stop": st, "ret_pct": rt * 100, "funding_pct": fs * 100,
                                      "funded": cv, "reason": [REASON[int(r)] for r in rs], "peak_time": df.index[pk],
                                      "lh_time": df.index[lh], "bars_held": xi - ei}))
    trades = pd.concat(rows, ignore_index=True).sort_values("entry_time").reset_index(drop=True) if rows else pd.DataFrame(
        columns=["symbol", "entry_time", "exit_time", "entry", "exit", "stop", "ret_pct", "funding_pct", "funded", "reason",
                 "peak_time", "lh_time", "bars_held"])
    return trades, bar_rets


# ----------------------------------------------------------------------------------------------- stats
def trade_stats(t, bar_rets=None, periods_per_year=365, start=None, end=None, prices=None, strict=True):
    """Moon Dev: the plan's stats keys. strict = only funded trades count (no funding data = reported apart).
    strict=False keeps every trade (funding where known) and is used only to pick knobs on the bigger sample."""
    if start is not None:
        t = t[t["entry_time"] >= start]
    if end is not None:
        t = t[t["entry_time"] < end]
    nf = t[~t["funded"]]
    if strict:
        t = t[t["funded"]]
    rp = t["ret_pct"]
    n = len(rp)
    wins, losses = rp[rp > 0].sum(), -rp[rp < 0].sum()
    s = {"trades": int(n), "avg_trade_pct": round(float(rp.mean()), 3) if n else None,
         "median_trade_pct": round(float(rp.median()), 3) if n else None,
         "t_stat": round(float(rp.mean() / (rp.std() / np.sqrt(n))), 2) if n > 2 and rp.std() > 0 else None,
         "win_rate": round(float((rp > 0).mean() * 100), 1) if n else None,
         "profit_factor": round(float(wins / losses), 2) if losses > 0 else (None if n == 0 else 99.0),
         "symbols_traded": int(t["symbol"].nunique()),
         "symbols_positive_pct": round(float((t.groupby("symbol")["ret_pct"].mean() > 0).mean() * 100), 1) if n else None,
         "avg_funding_pct": round(float(t["funding_pct"].mean()), 3) if n else None,
         "no_funding_trades": int(len(nf)),
         "no_funding_avg_trade_pct": round(float(nf["ret_pct"].mean()), 3) if len(nf) else None,
         "avg_bars_held": round(float(t["bars_held"].mean()), 1) if n else None}
    if bar_rets is not None:
        s.update(portfolio_stats(bar_rets, prices, periods_per_year, start, end))
    return s


def portfolio_stats(bar_rets, prices, periods_per_year, start=None, end=None):
    """Moon Dev: equal weight across symbols, flat = 0, same as the first pass. Buy and hold on the same symbols."""
    strat = pd.concat(bar_rets.values(), axis=1).sort_index()
    hold = pd.concat([p["Close"].pct_change().rename(k) for k, p in prices.items()], axis=1).sort_index()
    if start is not None:
        strat, hold = strat[strat.index >= start], hold[hold.index >= start]
    if end is not None:
        strat, hold = strat[strat.index < end], hold[hold.index < end]
    s = strat.mean(axis=1).fillna(0)
    h = hold.mean(axis=1).fillna(0)
    eq, heq = (1 + s).cumprod(), (1 + h).cumprod()
    sharpe = s.mean() / s.std() * np.sqrt(periods_per_year) if s.std() > 0 else 0.0
    return {"total_return_pct": round(float((eq.iloc[-1] - 1) * 100), 2), "sharpe": round(float(sharpe), 2),
            "max_dd_pct": round(float((eq / eq.cummax() - 1).min() * 100), 2),
            "buy_hold_return_pct": round(float((heq.iloc[-1] - 1) * 100), 2)}


def equity_curve(bar_rets, prices, step):
    """Moon Dev: strategy vs buy and hold, equal weight, sampled every `step` bars for the dashboard."""
    strat = pd.concat(bar_rets.values(), axis=1).sort_index().mean(axis=1).fillna(0)
    hold = pd.concat([p["Close"].pct_change().rename(k) for k, p in prices.items()], axis=1).sort_index().mean(axis=1).fillna(0)
    eq, heq = (1 + strat).cumprod(), (1 + hold).cumprod()
    out = [{"t": str(ts), "strategy": round(float(a), 4), "buy_hold": round(float(b), 4)}
           for ts, a, b in zip(eq.index[::step], eq.values[::step], heq.values[::step])]
    return out


def drift_baseline(prepped, bars, start=None, end=None):
    """Moon Dev: what a blind short held `bars` bars made on these coins (the regime, not the rule)."""
    vals = []
    for sym, (df, a) in prepped.items():
        c = df["Close"]
        fwd = -(c.shift(-bars) / c - 1) * 100
        if start is not None:
            fwd = fwd[fwd.index >= start]
        if end is not None:
            fwd = fwd[fwd.index < end]
        vals.append(fwd.dropna())
    allv = pd.concat(vals)
    return round(float(allv.mean()), 3), int(len(allv))


def excess_vs_drift(t, prepped, bars, start=None, end=None):
    """Moon Dev: the regime check. For each funded trade, subtract what a blind short of the SAME coin, held the
    same number of bars, made on average over the SAME period. What is left is the value of the entry timing."""
    if start is not None:
        t = t[t["entry_time"] >= start]
    if end is not None:
        t = t[t["entry_time"] < end]
    t = t[t["funded"]]
    drift = {}
    for sym in t["symbol"].unique():
        c = prepped[sym][0]["Close"]
        fwd = -(c.shift(-bars) / c - 1) * 100
        if start is not None:
            fwd = fwd[fwd.index >= start]
        if end is not None:
            fwd = fwd[fwd.index < end]
        drift[sym] = float(fwd.dropna().mean()) if fwd.notna().any() else 0.0
    ex = t["ret_pct"] - t["symbol"].map(drift)
    n = len(ex)
    return {"trades": int(n), "blind_short_bars": int(bars),
            "blind_short_avg_pct": round(float(t["symbol"].map(drift).mean()), 3) if n else None,
            "excess_avg_pct": round(float(ex.mean()), 3) if n else None,
            "excess_t_stat": round(float(ex.mean() / (ex.std() / np.sqrt(n))), 2) if n > 2 and ex.std() > 0 else None,
            "excess_positive_pct": round(float((ex > 0).mean() * 100), 1) if n else None}
