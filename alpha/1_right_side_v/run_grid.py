"""
Moon Dev's Package 1 runner: Right side of the V, find the version that pays.

Runs the whole grid (run size K, base window N, 3 entries, 7 exits) on 4 crypto markets with fees,
slippage and REAL funding. Then the filters on the best base, the slippage slider, the hold out
(knobs picked before 2024-07-01, reported after), the regime check on the first pass's late trades,
and writes result.json + the stock side check if the IWM data is there.

Run: /opt/anaconda3/envs/tflow/bin/python run_grid.py
"""
import json
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

import engine as E

HERE = Path(__file__).parent
MARKETS = ["hl_1d", "hl_8h", "hl_4h", "bn_1h"]
PPY = {"hl_1d": 365, "hl_8h": 365 * 3, "hl_4h": 365 * 6, "bn_1h": 365 * 24, "stocks_1d": 252}
SLIP_BP = 10.0           # base case slippage per side; the slider shows 0, 10, 25, 50
MIN_IS_TRADES = 100      # a combo needs this many in sample trades (funding where known) before we trust its t-stat
KS, NS = [1.5, 2.0, 3.0, 5.0], [10, 30]
ENTRIES, EXITS = list(E.ENTRY), list(E.EXIT)


def clean(x):
    """Moon Dev: JSON safe (numpy types and NaN)."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if np.isnan(x) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp,)):
        return str(x)
    return x


def three_way(trades, bar_rets, market, prices):
    """Moon Dev: the stats for all, in sample and out of sample."""
    return {"all": E.trade_stats(trades, bar_rets, PPY[market], prices=prices),
            "in_sample": E.trade_stats(trades, bar_rets, PPY[market], end=E.OOS_START, prices=prices),
            "out_of_sample": E.trade_stats(trades, bar_rets, PPY[market], start=E.OOS_START, prices=prices)}


def passes_bar(s):
    """Moon Dev: the plan's edge bar on one stats block."""
    need = ["avg_trade_pct", "t_stat", "profit_factor", "symbols_positive_pct"]
    if any(s.get(k) is None for k in need):
        return False
    return s["avg_trade_pct"] > 0 and s["t_stat"] >= 2 and s["profit_factor"] >= 1.2 and s["symbols_positive_pct"] >= 55


def main():
    t_start = time.time()
    failed, data_used = [], []
    prepped, prices = {}, {}
    for m in MARKETS:
        data = E.load_market(m)
        nofund = []
        pp = {}
        for s, df in data.items():
            fr = E.load_funding(s, m)
            if fr is None:
                nofund.append(s)
            pp[s] = (df, E.prep_symbol(df, m, fr))
        prepped[m], prices[m] = pp, data
        print(f"Moon Dev {m}: {len(pp)} symbols, {len(nofund)} with no funding file at all: {nofund[:12]}{'...' if len(nofund) > 12 else ''}")
        if nofund:
            failed.append(f"{m}: {len(nofund)} of {len(pp)} symbols have no funding data at all (tagged, not charged zero): {' '.join(nofund)}")
    data_used += [str(E.DATA_DIR / "hyperliquid_midcap/*_1d_hl.csv"), str(E.DATA_DIR / "hyperliquid_meme/*_1d_hl.csv"),
                  str(E.DATA_DIR / "hyperliquid_8h/*_8h_hl.csv"), str(E.DATA_DIR / "hyperliquid_meme/*_4h_hl.csv"),
                  str(E.MOON26 / "futures_klines_1m/<SYM>/<SYM>_1m_*.parquet (resampled to 1h, 16 majors + 15 meme perps pulled with binance_1m_klines_to_moon26.py)"),
                  str(E.DATA_DIR / "hyperliquid_funding/*_funding_hl.csv"), str(E.DATA_DIR / "hyperliquid_meme/*_funding_hl.csv"),
                  "Hyperliquid public info endpoint type=fundingHistory (no key) for coins with no local funding file, cached in data_cache/hl_funding/",
                  str(E.MOON26 / "funding/*_funding.csv"), "Binance public fapi/v1/fundingRate (no key) for the other Binance symbols, cached in data_cache/binance_funding/",
                  str(E.DATA_DIR / "hyperliquid_midcap/BTC_1d_hl.csv (BTC 50 day SMA regime)")]

    # ------------------------------------------------------------------ 1. the grid, every combo on every market
    grid, runs = [], {}
    for m in MARKETS:
        for K, N, entry, exit_ in product(KS, NS, ENTRIES, EXITS):
            tr, br = E.run_combo(prepped[m], K, N, entry, exit_, slip_bp=SLIP_BP)
            st = three_way(tr, br, m, prices[m])
            key = (m, K, N, entry, exit_)
            runs[key] = (tr, br)
            grid.append({"params": {"market": m, "K": K, "N": N, "entry": entry, "exit": exit_},
                         "trades": st["all"]["trades"], "avg_trade_pct": st["all"]["avg_trade_pct"],
                         "t_stat": st["all"]["t_stat"], "profit_factor": st["all"]["profit_factor"],
                         "total_return_pct": st["all"]["total_return_pct"],
                         "no_funding_trades": st["all"]["no_funding_trades"],
                         "in_sample": {k: st["in_sample"][k] for k in ["trades", "avg_trade_pct", "t_stat", "profit_factor"]},
                         "in_sample_all_trades": {k: v for k, v in E.trade_stats(tr, end=E.OOS_START, strict=False).items()
                                                  if k in ["trades", "avg_trade_pct", "t_stat", "profit_factor"]},
                         "out_of_sample": {k: st["out_of_sample"][k] for k in ["trades", "avg_trade_pct", "t_stat", "profit_factor", "symbols_positive_pct"]}})
        print(f"Moon Dev: grid done on {m} ({time.time() - t_start:.0f}s)")

    # ------------------------------------------------------------------ 2. pick the best on in sample only
    def is_score(g):
        s = g["in_sample_all_trades"]   # the funded only sample before mid 2024 is too thin to pick on
        return s["t_stat"] if (s["trades"] >= MIN_IS_TRADES and s["t_stat"] is not None) else -99

    ranked = sorted(grid, key=is_score, reverse=True)
    best_g = ranked[0]
    bp = best_g["params"]
    best_key = (bp["market"], bp["K"], bp["N"], bp["entry"], bp["exit"])
    best_tr, best_br = runs[best_key]
    best_stats = three_way(best_tr, best_br, bp["market"], prices[bp["market"]])
    print("Moon Dev BEST (in sample pick):", bp, "IS", best_g["in_sample"], "OOS", best_g["out_of_sample"])
    best_lh = next(g for g in ranked if g["params"]["entry"] == "lower_high")

    # ------------------------------------------------------------------ 3. filters, one at a time, then the best pair
    def filter_block(base_params, label):
        m = base_params["market"]
        args = dict(K=base_params["K"], N=base_params["N"], entry=base_params["entry"], exit_=base_params["exit"], slip_bp=SLIP_BP)
        tr0, br0 = E.run_combo(prepped[m], **args)
        base = three_way(tr0, br0, m, prices[m])
        rows = [{"filter": "none (base)", "in_sample": base["in_sample"], "out_of_sample": base["out_of_sample"]}]
        singles = {"btc_under_50sma": dict(use_btc=True), "funding_above_30d_median": dict(use_fund=True)}
        if base_params["entry"] == "lower_high":
            singles["volume_dry_up_half_peak"] = dict(vol_ratio=0.5)
            for d in [3, 5, 10]:
                singles[f"lower_high_within_{d}_bars"] = dict(max_delay=d)
        res = {}
        for name, kw in singles.items():
            tr, br = E.run_combo(prepped[m], **args, **kw)
            st = three_way(tr, br, m, prices[m])
            res[name] = kw
            rows.append({"filter": name, "in_sample": st["in_sample"], "out_of_sample": st["out_of_sample"]})
        # best pair: the two single filters with the best in sample avg trade (with at least 20 trades)
        ok = [r for r in rows[1:] if r["in_sample"]["trades"] >= 20 and r["in_sample"]["avg_trade_pct"] is not None]
        ok = sorted(ok, key=lambda r: r["in_sample"]["avg_trade_pct"], reverse=True)[:2]
        if len(ok) == 2:
            kw = {}
            for r in ok:
                kw.update(res[r["filter"]])
            tr, br = E.run_combo(prepped[m], **args, **kw)
            st = three_way(tr, br, m, prices[m])
            rows.append({"filter": "pair: " + " + ".join(r["filter"] for r in ok), "in_sample": st["in_sample"], "out_of_sample": st["out_of_sample"]})
        return {"base": base_params, "label": label, "rows": rows}

    filters = [filter_block(bp, "best base combo")]
    if bp["entry"] != "lower_high":
        filters.append(filter_block(best_lh["params"], "best lower high combo"))

    # ------------------------------------------------------------------ 4. costs: the slippage slider and 2x costs
    m = bp["market"]
    cost_curve = []
    for slip in [0, 10, 25, 50]:
        tr, br = E.run_combo(prepped[m], bp["K"], bp["N"], bp["entry"], bp["exit"], slip_bp=slip)
        st = three_way(tr, br, m, prices[m])
        cost_curve.append({"cost_bp_per_side": slip, "avg_trade_pct": st["all"]["avg_trade_pct"],
                           "oos_avg_trade_pct": st["out_of_sample"]["avg_trade_pct"], "is_avg_trade_pct": st["in_sample"]["avg_trade_pct"]})
    tr2, br2 = E.run_combo(prepped[m], bp["K"], bp["N"], bp["entry"], bp["exit"], fee_bp=2 * E.FEE_BP, slip_bp=2 * SLIP_BP)
    twice = three_way(tr2, br2, m, prices[m])
    # where does the avg trade cross zero (linear read of the slider, all trades)
    xs = [c["cost_bp_per_side"] for c in cost_curve]
    ys = [c["avg_trade_pct"] if c["avg_trade_pct"] is not None else 0 for c in cost_curve]
    zero_at = None
    for a, b in zip(range(len(xs) - 1), range(1, len(xs))):
        if ys[a] > 0 >= ys[b]:
            zero_at = round(xs[a] + (xs[b] - xs[a]) * ys[a] / (ys[a] - ys[b]), 1)
    if zero_at is None and ys[0] <= 0:
        zero_at = 0.0

    # ------------------------------------------------------------------ 5. his point: lower high break vs call the top, every market
    side_by_side = []
    for mk in MARKETS:
        for entry in ENTRIES:
            for K, N, ex in [(2.0, 30, "ema10"), (bp["K"], bp["N"], bp["exit"])]:
                tr, br = runs[(mk, K, N, entry, ex)]
                st = three_way(tr, br, mk, prices[mk])
                side_by_side.append({"market": mk, "knobs": f"K={K} N={N} exit={ex}", "entry": entry,
                                     "all": st["all"], "in_sample": st["in_sample"], "out_of_sample": st["out_of_sample"]})

    # ------------------------------------------------------------------ 6. by market, by year for the best knobs
    by_market = []
    for mk in MARKETS:
        tr, br = runs[(mk, bp["K"], bp["N"], bp["entry"], bp["exit"])]
        st = three_way(tr, br, mk, prices[mk])
        by_market.append({"market": mk, "trades": st["all"]["trades"], "avg_trade_pct": st["all"]["avg_trade_pct"],
                          "t_stat": st["all"]["t_stat"], "oos_trades": st["out_of_sample"]["trades"],
                          "oos_avg_trade_pct": st["out_of_sample"]["avg_trade_pct"], "oos_t_stat": st["out_of_sample"]["t_stat"],
                          "no_funding_trades": st["all"]["no_funding_trades"]})
    ft = best_tr[best_tr["funded"]]
    by_year = [{"year": int(y), "trades": int(len(g)), "avg_trade_pct": round(float(g["ret_pct"].mean()), 3)}
               for y, g in ft.groupby(ft["entry_time"].dt.year)]

    # ------------------------------------------------------------------ 7. were the first pass's late trades real? (regime check)
    base_tr, base_br = runs[("hl_1d", 2.0, 30, "lower_high", "ema10")]
    btc_tr, _ = E.run_combo(prepped["hl_1d"], 2.0, 30, "lower_high", "ema10", use_btc=True, slip_bp=SLIP_BP)
    regime = []
    for label, s, e in [("before 2024-07-01", None, E.OOS_START), ("after 2024-07-01", E.OOS_START, None)]:
        st = E.trade_stats(base_tr, start=s, end=e)
        stb = E.trade_stats(btc_tr, start=s, end=e)
        drift, nbars = E.drift_baseline(prepped["hl_1d"], 8, s, e)
        regime.append({"period": label, "base_rule_funded_trades": st["trades"], "base_rule_avg_trade_pct": st["avg_trade_pct"],
                       "base_rule_t_stat": st["t_stat"], "base_rule_no_funding_trades": st["no_funding_trades"],
                       "base_rule_no_funding_avg_pct": st["no_funding_avg_trade_pct"],
                       "blind_short_8_bars_avg_pct": drift, "blind_short_bars": nbars,
                       "btc_bear_filter_trades": stb["trades"], "btc_bear_filter_avg_trade_pct": stb["avg_trade_pct"]})
    # the first pass's exact split: all trades (funding where known), first half vs second half by date
    half = len(base_tr) // 2
    regime_note = {"first_half_avg_all_pct": round(float(base_tr["ret_pct"].iloc[:half].mean()), 3),
                   "second_half_avg_all_pct": round(float(base_tr["ret_pct"].iloc[half:].mean()), 3),
                   "second_half_funded_avg_pct": round(float(base_tr.iloc[half:].query("funded")["ret_pct"].mean()), 3),
                   "second_half_funded_trades": int(base_tr.iloc[half:]["funded"].sum()),
                   "second_half_symbols_positive_pct": round(float((base_tr.iloc[half:].groupby("symbol")["ret_pct"].mean() > 0).mean() * 100), 1)}

    # ------------------------------------------------------------------ 8. stocks side check (IWM list via yfinance), if the data is there
    stocks = None
    sdata = E.load_market("stocks_1d") if (E.CACHE / "stocks").exists() else {}
    if sdata:
        sp = {s: (df, E.prep_symbol(df, "stocks_1d", None)) for s, df in sdata.items()}
        stocks = []
        for K, entry in product([2.0, 3.0], ["lower_high", "call_top"]):
            tr, br = E.run_combo(sp, K, 30, entry, "ema10", slip_bp=SLIP_BP)
            tr["funded"] = True  # stocks have no funding; borrow is the grid below
            for borrow in [5, 25, 100]:
                t2 = tr.copy()
                t2["ret_pct"] = t2["ret_pct"] - borrow / 365 * t2["bars_held"] * (365 / 252)
                st = E.trade_stats(t2)
                stocks.append({"params": {"K": K, "entry": entry, "exit": "ema10", "borrow_pct_year": borrow},
                               "trades": st["trades"], "avg_trade_pct": st["avg_trade_pct"], "t_stat": st["t_stat"],
                               "profit_factor": st["profit_factor"], "symbols_positive_pct": st["symbols_positive_pct"]})
        data_used.append("Yahoo daily via yfinance on today's iShares IWM holdings (data_cache/stocks/)")
    else:
        failed.append("Stocks side check did not run: iShares serves its IWM holdings CSV behind a bot wall (HTML page to scripts). "
                      "Save the CSV by hand to data_cache/IWM_holdings.csv, run fetch_stocks.py, then run_grid.py again.")

    # ------------------------------------------------------------------ 9. replay, equity, trades, verdict
    m = bp["market"]
    bars_per_day = E.BARS_PER_DAY[m]
    sym = ft["symbol"].value_counts().index[0] if len(ft) else list(prices[m])[0]
    st_ = ft[ft["symbol"] == sym].sort_values("entry_time")
    df = prices[m][sym]
    if len(st_):
        i0 = max(0, df.index.get_loc(st_["entry_time"].iloc[0]) - 40)
        win = df.iloc[i0:i0 + 200]
    else:
        win = df.iloc[-200:]
    rt = st_[(st_["entry_time"] >= win.index[0]) & (st_["exit_time"] <= win.index[-1])].head(5)
    replay = {"symbol": sym, "market": m,
              "bars": [{"t": str(t), "o": float(r.Open), "h": float(r.High), "l": float(r.Low), "c": float(r.Close)} for t, r in win.iterrows()],
              "trades": [{"symbol": sym, "entry_time": str(r.entry_time), "exit_time": str(r.exit_time), "entry": float(r.entry),
                          "exit": float(r.exit), "stop": float(r.stop), "ret_pct": round(float(r.ret_pct), 3), "reason": r.reason,
                          "peak_time": str(r.peak_time), "lh_time": str(r.lh_time)} for r in rt.itertuples()]}
    step = max(1, len(next(iter(best_br.values())).index) // 600)
    eq = E.equity_curve(best_br, prices[m], step)
    trades_out = [{"symbol": r.symbol, "entry_time": str(r.entry_time), "exit_time": str(r.exit_time), "entry": float(r.entry),
                   "exit": float(r.exit), "ret_pct": round(float(r.ret_pct), 3), "funding_pct": round(float(r.funding_pct), 3),
                   "funded": bool(r.funded), "reason": r.reason} for r in best_tr.itertuples()][:2000]

    oos = best_stats["out_of_sample"]
    hold = int(round(best_stats["all"]["avg_bars_held"] or 10))
    regime_best = {"in_sample": E.excess_vs_drift(best_tr, prepped[m], hold, end=E.OOS_START),
                   "out_of_sample": E.excess_vs_drift(best_tr, prepped[m], hold, start=E.OOS_START)}
    bar = {"avg_trade_positive": bool(oos["avg_trade_pct"] is not None and oos["avg_trade_pct"] > 0),
           "t_stat_ge_2": bool(oos["t_stat"] is not None and oos["t_stat"] >= 2),
           "profit_factor_ge_1_2": bool(oos["profit_factor"] is not None and oos["profit_factor"] >= 1.2),
           "symbols_positive_ge_55pct": bool(oos["symbols_positive_pct"] is not None and oos["symbols_positive_pct"] >= 55),
           "positive_at_2x_costs": bool(twice["out_of_sample"]["avg_trade_pct"] is not None and twice["out_of_sample"]["avg_trade_pct"] > 0)}
    plan_bar_passed = all(bar.values())
    ro = regime_best["out_of_sample"]
    bar["beats_blind_short_same_coins_t_ge_2"] = bool(ro["excess_avg_pct"] is not None and ro["excess_avg_pct"] > 0
                                                      and ro["excess_t_stat"] is not None and ro["excess_t_stat"] >= 2)
    passed = all(bar.values())
    beats_zero = any(g["out_of_sample"]["avg_trade_pct"] is not None and g["out_of_sample"]["avg_trade_pct"] > 0
                     and g["out_of_sample"]["trades"] >= 30 for g in grid)
    if passed:
        verdict = "VERIFIED" if (bp["entry"] == "lower_high" and bp["K"] == 2.0 and bp["N"] == 30 and bp["exit"] == "ema10") else "BETTER VERSION FOUND"
    elif not beats_zero:
        verdict = "BUSTED"
    else:
        verdict = "NOT PROVEN" + (" (passes the plan bar, but not the regime check)" if plan_bar_passed else "")

    result = {
        "package": "1_right_side_v",
        "title": "Right side of the V: short the lower high break after a parabolic run",
        "claim": "Shorting an upside capitulation on the right side of the V: wait for a lower high or a failed reclaim, be later with better confirmation, and the expected value goes up.",
        "claim_time": "2:40",
        "verdict": verdict,
        "headline": {"label": f"Out of sample avg trade, best combo ({bp['market']} {bp['entry']} K={bp['K']} N={bp['N']} exit={bp['exit']}), after fees, 10 bp slippage and real funding",
                     "value": oos["avg_trade_pct"], "unit": "%"},
        "first_pass": {"trades": 677, "avg_trade_pct": -1.19},
        "best": {"params": {**bp, "fee_bp_per_side": E.FEE_BP, "slippage_bp_per_side": SLIP_BP, "funding": "real, per bar held",
                            "peak_window_bars": E.PEAK_WINDOW, "max_hold_bars": E.MAX_HOLD},
                 "in_sample": best_stats["in_sample"], "out_of_sample": best_stats["out_of_sample"], "all": best_stats["all"],
                 "at_2x_costs": {"in_sample": twice["in_sample"], "out_of_sample": twice["out_of_sample"]},
                 "edge_bar_out_of_sample": bar, "passes_plan_bar": plan_bar_passed, "passes_edge_bar": passed,
                 "regime_check_vs_blind_short": regime_best,
                 "selection": f"highest in sample t-stat (all trades, funding where known) with at least {MIN_IS_TRADES} in sample trades; the same knobs reported out of sample on funded trades only"},
        "best_lower_high_combo": best_lh,
        "stats keys": "trades, avg_trade_pct, median_trade_pct, t_stat, win_rate, profit_factor, total_return_pct, sharpe, max_dd_pct, buy_hold_return_pct, plus symbols_traded, symbols_positive_pct, avg_funding_pct, no_funding_trades, no_funding_avg_trade_pct, avg_bars_held",
        "equity_curve": eq,
        "trades": trades_out,
        "grid": grid,
        "cost_curve": cost_curve,
        "cost_zero_crossing_bp_per_side": zero_at,
        "by_year": by_year,
        "by_market": by_market,
        "filters": filters,
        "lower_high_vs_call_top": side_by_side,
        "regime_check": {"rule": "hl_1d K=2 N=30 lower_high ema10 (the first pass rule) with real funding", "periods": regime, "first_pass_split": regime_note},
        "stocks_side_check": stocks,
        "replay": replay,
        "data_used": data_used,
        "failed_parts": failed,
        "run_seconds": round(time.time() - t_start),
    }
    (HERE / "result.json").write_text(json.dumps(clean(result), indent=1))
    print(f"Moon Dev: wrote {HERE / 'result.json'} in {time.time() - t_start:.0f}s, verdict {verdict}")
    return result


if __name__ == "__main__":
    main()
