"""
Moon Dev edge finder, package 3: turn the grid store into result.json.

Reads data_cache/grid_store.pkl (written by moon_dev_bouncy_ball_edge.py), picks the best knobs
in sample (trades entered before 2024-07-01, at least 100 in sample trades, ranked by t-stat),
reports the same knobs out of sample, runs the squeeze guards and the cost slider on that
variant, and writes result.json in the shared dashboard layout. Chase the crash sits next to the
bouncy ball in every table.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import moon_dev_bouncy_data as dat
from moon_dev_bouncy_ball_edge import stats, net_returns, SPLIT, FEE, HEADLINE_SLIP, passes_bar

HERE = Path(__file__).resolve().parent
MIN_IS_TRADES = 100
COST_POINTS = [0.0, 4.5, 14.5, 29.0, 29.5, 50.0, 100.0]  # bp a side, fee plus slippage. 29.0 is 2x the headline cost


def cost_stats(tr, n_sym, bp_per_side):
    """Moon Dev: stats with one total cost per side (fee plus slippage) instead of the fixed fee."""
    t = tr.copy()
    t["gross"] = t["gross"] + 2 * FEE - 2 * bp_per_side / 10000  # undo the fee the stats function charges
    return stats(t, n_sym, slip=0.0)


def split(tr):
    return tr[tr["entry_time"] < SPLIT], tr[tr["entry_time"] >= SPLIT]


def guard_tables(tr, n_sym, liq, regime):
    """Moon Dev: each squeeze guard alone and all three together, on the subset where the guard is known."""
    out = []
    tr = tr.copy()
    et = pd.to_datetime(tr["entry_time"])
    tr["_day"] = et.dt.floor("D")
    tr["_btc_under"] = tr["_day"].map(regime).fillna(False).astype(bool)
    tr["_liq_spike"] = np.nan
    for sym, book in liq.items():
        m = tr["symbol"] == sym
        if not m.any():
            continue
        pos = np.searchsorted(book.index.values, et[m].values, side="left") - 1
        ok = (pos >= 0) & (et[m].values <= book.index.values[-1])
        vals = np.full(m.sum(), np.nan)
        vals[ok] = (book["short_liq_1h"].values[pos[ok]] > book["top10_thr"].values[pos[ok]]).astype(float)
        tr.loc[m, "_liq_spike"] = vals
    guards = {
        "funding_not_negative": (tr["funding_at_entry"].notna(), tr["funding_at_entry"] >= 0),
        "no_short_liq_spike_BTC_ETH_SOL_XRP": (tr["_liq_spike"].notna(), tr["_liq_spike"] == 0),
        "btc_under_50d_sma": (pd.Series(True, index=tr.index), tr["_btc_under"]),
    }
    known_all = guards["funding_not_negative"][0] & guards["no_short_liq_spike_BTC_ETH_SOL_XRP"][0]
    keep_all = known_all & guards["funding_not_negative"][1] & guards["no_short_liq_spike_BTC_ETH_SOL_XRP"][1] & tr["_btc_under"]
    guards["all_three"] = (known_all, keep_all)
    for name, (known, keep) in guards.items():
        base = tr[known]
        filt = tr[known & keep]
        b_is, b_oos = split(base)
        f_is, f_oos = split(filt)
        row = {"guard": name, "subset_trades": int(len(base)),
               "before": {"in_sample": stats(b_is, n_sym), "out_of_sample": stats(b_oos, n_sym)},
               "after": {"in_sample": stats(f_is, n_sym), "out_of_sample": stats(f_oos, n_sym)}}
        row["oos_lift_pct"] = round(row["after"]["out_of_sample"]["avg_trade_pct"] - row["before"]["out_of_sample"]["avg_trade_pct"], 3)
        row["improves"] = bool(row["oos_lift_pct"] >= 0.5 and row["after"]["out_of_sample"]["trades"] >= 100)
        out.append(row)
    return out


def replay_block(tr, market, sym):
    """Moon Dev: about 200 real bars around 2 to 5 real trades of the best variant."""
    tfname = market.split("_")[1]
    if market.startswith("binance"):
        df = pd.read_parquet(HERE / "data_cache" / f"binance_{sym}_{tfname}.parquet")
    else:
        data = {"hl_15m": dat.load_hl_15m, "hl_4h": dat.load_hl_4h, "hl_1d": dat.load_hl_daily}[market]()
        df = data[sym]
    t = tr[tr["symbol"] == sym].sort_values("entry_time")
    best, best_n = None, 0
    for _, row in t.iterrows():
        lo = int(row["entry_bar"]) - 40
        n = int(((t["entry_bar"] >= lo) & (t["exit_bar"] <= lo + 200)).sum())
        if 2 <= n <= 5 and n > best_n:
            best, best_n = lo, n
    if best is None:
        best = max(int(t["entry_bar"].iloc[-1]) - 100, 0)
    seg = df.iloc[max(best, 0):best + 200]
    inside = t[(t["entry_bar"] >= best) & (t["exit_bar"] <= best + 200)]
    return {"symbol": sym, "market": market,
            "bars": [{"t": str(i), "o": float(r.Open), "h": float(r.High), "l": float(r.Low), "c": float(r.Close)} for i, r in seg.iterrows()],
            "trades": trade_rows(inside)}


def trade_rows(t):
    r = net_returns(t, HEADLINE_SLIP) * 100
    return [{"symbol": s, "entry_time": str(a), "exit_time": str(b), "entry": float(e), "exit": float(x), "stop": float(st),
             "ret_pct": round(float(v), 3), "funding_pct": round(float(f) * 100, 4) if pd.notna(f) else None, "reason": str(rs)}
            for s, a, b, e, x, st, v, f, rs in zip(t["symbol"], t["entry_time"], t["exit_time"], t["entry"], t["exit"], t["stop"], r, t["funding"], t["reason"])]


if __name__ == "__main__":
    d = pd.read_pickle(HERE / "data_cache" / "grid_store.pkl")
    grid, store, meta = d["grid"], d["store"], d["meta"]
    g = pd.DataFrame([{**r["params"], **{k: v for k, v in r.items() if k != "params"}} for r in grid])
    nsym = {m: meta[m]["n_symbols"] for m in meta}
    closes = {m: pd.read_parquet(HERE / "data_cache" / f"closes_{m}.parquet") for m in meta}
    stock = json.load(open(HERE / "stock_side_check.json")) if (HERE / "stock_side_check.json").exists() else None

    # ---- pick the best knobs in sample, report out of sample. Selection markets have real in sample history.
    ball = g[(g["mode"] == "ball") & (g["is_trades"] >= MIN_IS_TRADES) & g["market"].isin(["binance_15m", "binance_1h", "binance_4h", "hl_1d"])]
    ball = ball.sort_values("is_t_stat", ascending=False)
    top = ball.iloc[0]
    best_params = {k: top[k] for k in ["market", "tf", "mode", "D", "N", "B", "R", "P", "exit"]}
    best_params = {k: (float(v) if isinstance(v, (np.floating,)) else int(v) if isinstance(v, (np.integer,)) else v) for k, v in best_params.items()}
    key = json.dumps(best_params, sort_keys=True)
    tr = store[key]
    tr_is, tr_oos = split(tr)
    m = best_params["market"]
    best_is = stats(tr_is, nsym[m], closes=closes[m])
    best_oos = stats(tr_oos, nsym[m], closes=closes[m])
    best_oos_2x = cost_stats(tr_oos, nsym[m], 29.0)
    best_all = stats(tr, nsym[m], with_curve=True, closes=closes[m])
    chase_params = {**best_params, "mode": "chase", "B": 0, "R": 0.0, "P": 0}
    ctr = store[json.dumps(chase_params, sort_keys=True)]
    c_is, c_oos = split(ctr)
    print(f"Moon Dev: best in sample {best_params}")
    print(f"  IS  {best_is}")
    print(f"  OOS {best_oos}")
    print(f"  OOS at 2x cost {best_oos_2x}")

    # ---- how much of the best variant ran with real funding, and what funding added where it is known
    fk = tr[tr["funding"].notna()]
    fk_is, fk_oos = split(fk)
    funding_known = {"trades_with_funding": int(len(fk)), "trades_without_funding": int(tr["funding"].isna().sum()),
                     "symbols_with_funding": int(fk["symbol"].nunique()), "symbols_without_funding": int(tr[tr["funding"].isna()]["symbol"].nunique()),
                     "avg_funding_earned_pct_per_trade": round(float(fk["funding"].mean() * 100), 4) if len(fk) else None,
                     "oos_avg_funding_earned_pct_per_trade": round(float(fk_oos["funding"].mean() * 100), 4) if len(fk_oos) else None,
                     "with_funding_only": {"in_sample": stats(fk_is, nsym[m]), "out_of_sample": stats(fk_oos, nsym[m])}}
    print(f"  funding known: {funding_known}")

    # ---- best intraday pick (Binance 15m, 1h, 4h only), same selection rule, with its chase twin
    intra = ball[ball["market"].isin(["binance_15m", "binance_1h", "binance_4h"])]
    ri = intra.iloc[0]
    intra_params = {k: ri[k] for k in ["market", "tf", "mode", "D", "N", "B", "R", "P", "exit"]}
    intra_params = {k: (float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else v) for k, v in intra_params.items()}
    itr = store[json.dumps(intra_params, sort_keys=True)]
    itr_is, itr_oos = split(itr)
    ictr = store[json.dumps({**intra_params, "mode": "chase", "B": 0, "R": 0.0, "P": 0}, sort_keys=True)]
    ic_is, ic_oos = split(ictr)
    mi = intra_params["market"]
    best_intraday = {"params": intra_params, "in_sample": stats(itr_is, nsym[mi], closes=closes[mi]), "out_of_sample": stats(itr_oos, nsym[mi], closes=closes[mi]),
                     "out_of_sample_2x_costs": cost_stats(itr_oos, nsym[mi], 29.0),
                     "chase_same_knobs": {"in_sample": stats(ic_is, nsym[mi]), "out_of_sample": stats(ic_oos, nsym[mi])}}
    best_intraday["passes_edge_bar"] = bool(passes_bar(best_intraday["in_sample"], best_intraday["out_of_sample"], best_intraday["out_of_sample_2x_costs"]))
    print(f"Moon Dev: best intraday {intra_params}")
    print(f"  IS  {best_intraday['in_sample']}")
    print(f"  OOS {best_intraday['out_of_sample']}")

    # ---- the ten best in sample picks, each with its out of sample line, so the dashboard shows the decay
    top10 = []
    for _, r in ball.head(10).iterrows():
        p = {k: r[k] for k in ["market", "tf", "mode", "D", "N", "B", "R", "P", "exit"]}
        p = {k: (float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else v) for k, v in p.items()}
        t = store[json.dumps(p, sort_keys=True)]
        a, b = split(t)
        top10.append({"params": p, "in_sample": stats(a, nsym[p["market"]]), "out_of_sample": stats(b, nsym[p["market"]])})

    # ---- by timeframe and market: best ball (in sample pick per market) vs chase with the same crash and exit
    by_tf = []
    for mk in meta:
        sub = g[(g["market"] == mk) & (g["mode"] == "ball")]
        if mk in ("hl_15m", "hl_4h"):
            # no real in sample history here: run the overall best knobs and show the market as a check
            p = {**best_params, "market": mk, "tf": meta[mk]["tf"]}
            pick_note = "overall best knobs applied (no in sample history on this market)"
        else:
            s2 = sub[sub["is_trades"] >= MIN_IS_TRADES].sort_values("is_t_stat", ascending=False)
            if len(s2) == 0:
                s2 = sub.sort_values("is_t_stat", ascending=False)
            r = s2.iloc[0]
            p = {k: r[k] for k in ["market", "tf", "mode", "D", "N", "B", "R", "P", "exit"]}
            p = {k: (float(v) if isinstance(v, np.floating) else int(v) if isinstance(v, np.integer) else v) for k, v in p.items()}
            pick_note = "best in sample on this market"
        t = store.get(json.dumps(p, sort_keys=True), pd.DataFrame())
        cp = {**p, "mode": "chase", "B": 0, "R": 0.0, "P": 0}
        ct = store.get(json.dumps(cp, sort_keys=True), pd.DataFrame())
        a, b = split(t)
        ca, cb = split(ct)
        by_tf.append({"market": mk, "timeframe": meta[mk]["tf"], "symbols": nsym[mk], "span": f"{meta[mk]['start']} to {meta[mk]['end']}",
                      "pick": pick_note, "params": p,
                      "ball": {"in_sample": stats(a, nsym[mk]), "out_of_sample": stats(b, nsym[mk])},
                      "chase": {"in_sample": stats(ca, nsym[mk]), "out_of_sample": stats(cb, nsym[mk])},
                      "no_funding_symbols": meta[mk]["no_funding_symbols"]})
    by_market = [{"market": f"{r['market']} ({r['timeframe']})", "trades": r["ball"]["out_of_sample"]["trades"],
                  "avg_trade_pct": r["ball"]["out_of_sample"]["avg_trade_pct"], "t_stat": r["ball"]["out_of_sample"]["t_stat"],
                  "chase_trades": r["chase"]["out_of_sample"]["trades"], "chase_avg_trade_pct": r["chase"]["out_of_sample"]["avg_trade_pct"],
                  "window": "out of sample"} for r in by_tf]

    # ---- squeeze guards on the best variant and on its chase twin
    liq = {}
    for coin in ["BTC", "ETH", "SOL", "XRP"]:
        book = dat.load_liq_1h(coin)
        liq[coin + "USDT"] = book
        liq[coin] = book
    regime = dat.btc_regime()
    guards = guard_tables(tr, nsym[m], liq, regime)
    guards_chase = guard_tables(ctr, nsym[m], liq, regime)
    guards_intraday = guard_tables(itr, nsym[mi], liq, regime)
    best_intraday["squeeze_guard"] = guards_intraday
    for gr in guards_intraday:
        print(f"  intraday guard {gr['guard']}: subset {gr['subset_trades']} OOS before {gr['before']['out_of_sample']['avg_trade_pct']} "
              f"({gr['before']['out_of_sample']['trades']}) after {gr['after']['out_of_sample']['avg_trade_pct']} ({gr['after']['out_of_sample']['trades']})")
    for gr in guards:
        print(f"  guard {gr['guard']}: subset {gr['subset_trades']} OOS before {gr['before']['out_of_sample']['avg_trade_pct']} "
              f"({gr['before']['out_of_sample']['trades']}) after {gr['after']['out_of_sample']['avg_trade_pct']} ({gr['after']['out_of_sample']['trades']})")

    # ---- cost slider, by year, equity, replay
    cost_curve = [{"cost_bp_per_side": c, "avg_trade_pct": cost_stats(tr_oos, nsym[m], c)["avg_trade_pct"],
                   "avg_trade_pct_all": cost_stats(tr, nsym[m], c)["avg_trade_pct"], "window": "out of sample"} for c in COST_POINTS]
    slip_grid = [{"slippage_bp_per_side": s, "in_sample": stats(tr_is, nsym[m], slip=s / 10000), "out_of_sample": stats(tr_oos, nsym[m], slip=s / 10000),
                  "chase_out_of_sample": stats(c_oos, nsym[m], slip=s / 10000)} for s in [0, 10, 25]]
    yrs = pd.to_datetime(tr["entry_time"]).dt.year
    by_year = []
    for y in sorted(yrs.unique()):
        s = stats(tr[yrs == y], nsym[m])
        cy = ctr[pd.to_datetime(ctr["entry_time"]).dt.year == y]
        cs = stats(cy, nsym[m])
        by_year.append({"year": int(y), "trades": s["trades"], "avg_trade_pct": s["avg_trade_pct"], "t_stat": s["t_stat"],
                        "chase_trades": cs["trades"], "chase_avg_trade_pct": cs["avg_trade_pct"]})
    oos_syms = tr_oos.groupby("symbol").size().sort_values(ascending=False)
    replay = replay_block(tr, m, oos_syms.index[0] if len(oos_syms) else tr["symbol"].iloc[0])

    # ---- verdict
    passed = passes_bar(best_is, best_oos, best_oos_2x)
    any_oos_positive = bool(((g["mode"] == "ball") & (g["oos_trades"] >= 100) & (g["oos_avg_trade_pct"] > 0)).any())
    verdict = "BETTER VERSION FOUND" if passed else ("NOT PROVEN" if any_oos_positive else "BUSTED")
    n_pos = int(((g["mode"] == "ball") & (g["oos_trades"] >= 100) & (g["oos_avg_trade_pct"] > 0)).sum())
    n_100 = int(((g["mode"] == "ball") & (g["oos_trades"] >= 100)).sum())
    failed = [f"stocks side check: {x}" for x in (stock or {}).get("failed_parts", [])]
    if stock is None:
        failed.append("stocks side check: stock_side_check.json not written")
    failed.append("hl_1d funding: only the 28 coins with local Hyperliquid funding files are charged real funding; the other daily coins are tagged no funding data (see by_timeframe.no_funding_symbols)")

    trades_out = tr.sort_values("entry_time")
    if len(trades_out) > 2000:
        trades_out = trades_out.tail(2000)
    result = {
        "package": "3_bouncy_ball",
        "title": "Bouncy ball short: intraday, shrinking bounces, squeeze guard",
        "claim": "After a crash each bounce is weaker, like a ball losing energy. Short the failed bounce with a stop just above it. That beats chasing the crash.",
        "claim_time": "7:10",
        "verdict": verdict,
        "headline": {"label": f"Out of sample avg trade, best in sample knobs ({best_params['market']}, fees 4.5 bp, slippage 10 bp, real funding)",
                     "value": best_oos["avg_trade_pct"], "unit": "%"},
        "first_pass": {"trades": 393, "avg_trade_pct": -1.93, "chase_trades": 1378, "chase_avg_trade_pct": -2.22},
        "best": {"params": best_params, "in_sample": best_is, "out_of_sample": best_oos, "out_of_sample_2x_costs": best_oos_2x,
                 "all": {k: v for k, v in best_all.items() if k != "_curve"},
                 "chase_same_knobs": {"in_sample": stats(c_is, nsym[m]), "out_of_sample": stats(c_oos, nsym[m])},
                 "passes_edge_bar": bool(passed), "selection": f"highest in sample t-stat with at least {MIN_IS_TRADES} in sample trades, markets binance_15m, binance_1h, binance_4h, hl_1d"},
        "best_intraday": best_intraday,
        "funding_coverage_best": funding_known,
        "top10_in_sample": top10,
        "edge_bar": {"rule": "OOS avg trade > 0, t-stat >= 2, profit factor >= 1.2, positive on 55%+ of traded symbols, positive at 2x costs (29 bp a side)",
                     "oos_combos_with_100_trades": n_100, "oos_combos_positive": n_pos},
        "equity_curve": best_all["_curve"][::max(1, len(best_all["_curve"]) // 1500)],
        "trades": trade_rows(trades_out),
        "grid": [{"params": r["params"], "trades": r["trades"], "avg_trade_pct": r["avg_trade_pct"], "t_stat": r["t_stat"],
                  "profit_factor": r["profit_factor"], "total_return_pct": r["total_return_pct"], "is_trades": r["is_trades"],
                  "is_avg_trade_pct": r["is_avg_trade_pct"], "is_t_stat": r["is_t_stat"], "oos_trades": r["oos_trades"],
                  "oos_avg_trade_pct": r["oos_avg_trade_pct"], "oos_t_stat": r["oos_t_stat"], "oos_profit_factor": r["oos_profit_factor"]} for r in grid],
        "cost_curve": cost_curve,
        "slippage_grid": slip_grid,
        "by_year": by_year,
        "by_market": by_market,
        "by_timeframe": by_tf,
        "squeeze_guard": {"ball": guards, "chase": guards_chase,
                          "note": "liq guard uses liq_clean_{BTC,ETH,SOL,XRP}_5m.csv forced_buy_usd summed over 1 hour vs its rolling 30 day 90th percentile, span 2024-06 to 2025-12, Binance BTC ETH SOL XRP only"},
        "stock_side_check": stock,
        "replay": replay,
        "data_used": [
            "/Volumes/Moon 26/tick_data/binance/futures_klines_1m/<SYM>/<SYM>_1m_<start>_<end>.parquet (16 symbols, resampled to 15m 1h 4h 1d)",
            "/Volumes/Moon 26/tick_data/binance/funding/{BTC,ETH,SOL,XRP,DOGE}USDT_funding.csv",
            "https://fapi.binance.com/fapi/v1/fundingRate (public, no key) for the other 11 Binance symbols",
            "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_15m/*_15m_hl.csv (74 coins)",
            "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_meme/*_4h_hl.csv (22 coins)",
            "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_{meme,midcap}/*_1d_hl.csv (first pass daily set)",
            "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/hyperliquid_funding/*_funding_hl.csv and hyperliquid_meme/*_funding_hl.csv",
            "https://api.hyperliquid.xyz/info fundingHistory (public, no key) for Hyperliquid coins with no local funding file",
            "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/data/moondev_api/liq_clean_{BTC,ETH,SOL,XRP}_5m.csv",
        ],
        "failed_parts": failed,
        "markets": meta,
    }
    json.dump(result, open(HERE / "result.json", "w"), indent=1, default=str)
    print(f"Moon Dev: wrote result.json, verdict {verdict}, grid rows {len(grid)}")
