"""
Moon Dev's edge finder dashboard builder.
Reads the 3 real result.json files in ../alpha, packs them into one JSON blob, and bakes it into index.html
(from template.html). Every number on the page comes from these files. Nothing is made up.
Run: python3 build_dashboard.py
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALPHA = HERE.parent / "alpha"


def load(name):
    return json.load(open(ALPHA / name / "result.json"))


def r2(x, n=3):
    return None if x is None else round(float(x), n)


def stats(s, keys=("trades", "avg_trade_pct", "median_trade_pct", "t_stat", "win_rate", "profit_factor",
                   "symbols_positive_pct", "total_return_pct", "sharpe", "max_dd_pct", "buy_hold_return_pct")):
    if s is None:
        return None
    return {k: s.get(k) for k in keys if k in s}


def downsample(curve, n=420):
    step = max(1, len(curve) // n)
    out = [[c["t"][:10], r2(c["strategy"], 4)] for c in curve[::step]]
    if out[-1][0] != curve[-1]["t"][:10]:
        out.append([curve[-1]["t"][:10], r2(curve[-1]["strategy"], 4)])
    return out


def compact_trades(trades, split):
    rows = sorted(trades, key=lambda t: t["entry_time"])
    return [[t["symbol"], t["entry_time"][:10], t["exit_time"][:10], r2(t["ret_pct"], 2), t.get("reason", ""),
             1 if (split and t["entry_time"][:10] >= split) else 0, 1 if t.get("funded", True) else 0] for t in rows]


def replay(rp):
    bars = [[b["t"][:10], b["o"], b["h"], b["l"], b["c"]] for b in rp["bars"]]
    tr = [{"entry_time": t["entry_time"][:10], "exit_time": t["exit_time"][:10], "entry": t["entry"], "exit": t["exit"],
           "stop": t.get("stop"), "ret_pct": r2(t["ret_pct"], 2), "reason": t.get("reason", "")} for t in rp["trades"]]
    return {"symbol": rp["symbol"], "bars": bars, "trades": tr, "day0": rp.get("day0")}


# Moon Dev: package 1, right side of the V
p1r = load("1_right_side_v")
b = p1r["best"]
p1_grid = []
for g in p1r["grid"]:
    p = g["params"]
    i, ia, o = g["in_sample"], g["in_sample_all_trades"], g["out_of_sample"]
    p1_grid.append([p["market"], p["K"], p["N"], p["entry"], p["exit"], i["trades"], i["avg_trade_pct"], i["t_stat"],
                    ia["trades"], ia["avg_trade_pct"], ia["t_stat"], o["trades"], o["avg_trade_pct"], o["t_stat"],
                    o.get("profit_factor"), o.get("symbols_positive_pct")])
exit_means = defaultdict(list)
for g in p1r["grid"]:
    if g["out_of_sample"]["trades"] >= 30:
        exit_means[g["params"]["exit"]].append(g["out_of_sample"]["avg_trade_pct"])
p1 = {
    "verdict": p1r["verdict"], "claim": p1r["claim"], "claim_time": p1r["claim_time"], "title": p1r["title"],
    "first_pass": p1r["first_pass"], "params": b["params"],
    "is": stats(b["in_sample"]), "oos": stats(b["out_of_sample"]), "oos2x": stats(b["at_2x_costs"]["out_of_sample"]),
    "all": stats(b["all"]), "edge": b["edge_bar_out_of_sample"], "regime": b["regime_check_vs_blind_short"],
    "is_all_trades": p1r["best_lower_high_combo"]["in_sample_all_trades"],
    "no_funding_oos": {"trades": b["out_of_sample"]["no_funding_trades"], "avg": b["out_of_sample"]["no_funding_avg_trade_pct"]},
    "equity": downsample(p1r["equity_curve"]), "split": "2024-07-01",
    "trades": compact_trades(p1r["trades"], "2024-07-01"),
    "grid": p1_grid, "cost_curve": p1r["cost_curve"], "by_year": p1r["by_year"], "by_market": p1r["by_market"],
    "filters": [{"filter": r["filter"], "is": stats(r["in_sample"]), "oos": stats(r["out_of_sample"])} for r in p1r["filters"][0]["rows"]],
    "entry_order": [{"market": x["market"], "knobs": x["knobs"], "entry": x["entry"], "is": stats(x["in_sample"]), "oos": stats(x["out_of_sample"])}
                    for x in p1r["lower_high_vs_call_top"]],
    "regime_periods": p1r["regime_check"]["periods"],
    "exit_means": {k: [len(v), r2(statistics.mean(v), 2)] for k, v in exit_means.items()},
    "replay": replay(p1r["replay"]), "failed_parts": p1r["failed_parts"],
    "bot": (ALPHA / "1_right_side_v" / "bot.py").read_text(),
}

# Moon Dev: package 2, IPO lockup
p2r = load("2_lockup")
p2_grid, p2_filters = [], []
for g in p2r["grid"]:
    p = g["params"]
    i, o = g["in_sample"], g["out_of_sample"]
    row = [1 if p["hedged"] else 0, p["entry_day"], p["exit_day"], p["borrow_pct"], i["trades"], i["avg_trade_pct"], i["t_stat"],
           o["trades"], o["avg_trade_pct"], o["t_stat"], o.get("profit_factor")]
    if "filter" in p:
        p2_filters.append([p["filter"]] + row)
    else:
        p2_grid.append(row)
fl = p2r["flip_long"]
p2 = {
    "verdict": p2r["verdict"], "claim": p2r["claim"], "claim_time": p2r["claim_time"], "title": p2r["title"],
    "first_pass": p2r["first_pass"], "params": p2r["best"]["params"],
    "is": stats(p2r["best"]["in_sample"]), "oos": stats(p2r["best"]["out_of_sample"]),
    "oos2x": stats(p2r["best"]["out_of_sample_at_2x_costs"]), "edge": p2r["best"]["edge_bar_out_of_sample"],
    "best_filter": {"label": p2r["best_filter"]["params"]["filter"], "is": stats(p2r["best_filter"]["in_sample"]),
                    "oos": stats(p2r["best_filter"]["out_of_sample"])},
    "first_pass_rerun": {k: stats(p2r["first_pass_window_rerun"][k]) for k in ("all", "in_sample", "out_of_sample")},
    "event_curve": p2r["event_curve"], "event_windows": p2r["event_windows"],
    "flip": {h: {k: stats(v[k]) for k in ("all", "in_sample", "out_of_sample")} | {"base_oos": stats(v["baseline_long_every_day0_close"]["out_of_sample"])}
             for h, v in fl["by_hold"].items()},
    "flip_rule": fl["rule"],
    "equity": downsample(p2r["equity_curve"]), "split": p2r["split_date"],
    "trades": compact_trades(p2r["trades"], None),
    "grid": p2_grid, "filters": p2_filters, "cost_curve": p2r["cost_curve"], "borrow_curve": p2r["borrow_curve"],
    "by_year": p2r["by_year"], "by_market": p2r["by_market"], "funnel": p2r["universe_funnel"],
    "replay": replay(p2r["replay"]), "failed_parts": p2r["failed_parts"],
    "lockup_parsed": p2r["lockup_parsed_count"], "lockup_guessed": p2r["lockup_guessed_count"],
}
bars = p2r["replay"]["bars"]
for k, x in enumerate(bars):
    if x["t"][:10] == p2r["replay"]["day0"]:
        p2["bynd_day0_pct"] = r2((x["c"] / bars[k - 1]["c"] - 1) * 100, 1)

# Moon Dev: package 3, bouncy ball
p3r = load("3_bouncy_ball")
b3 = p3r["best"]
p3_grid = []
for g in p3r["grid"]:
    p = g["params"]
    p3_grid.append([p["market"], p["mode"], p["D"], p["N"], p["B"], p["R"], p["P"], p["exit"], g["is_trades"], g["is_avg_trade_pct"],
                    g["is_t_stat"], g["oos_trades"], g["oos_avg_trade_pct"], g["oos_t_stat"], g["oos_profit_factor"]])
knob_means = {}
daily_ball = [g for g in p3r["grid"] if g["params"]["market"] == "hl_1d" and g["params"]["mode"] == "ball" and g["oos_trades"] >= 100]
for key in ("B", "R", "exit"):
    m = defaultdict(list)
    for g in daily_ball:
        m[str(g["params"][key])].append(g["oos_avg_trade_pct"])
    knob_means[key] = {k: [len(v), r2(statistics.mean(v), 2)] for k, v in m.items()}
combos_pos = {}
for mk in p3r["markets"]:
    for mode in ("ball", "chase"):
        gg = [g for g in p3r["grid"] if g["params"]["market"] == mk and g["params"]["mode"] == mode and g["oos_trades"] >= 100]
        combos_pos[f"{mk}|{mode}"] = [len(gg), sum(g["oos_avg_trade_pct"] > 0 for g in gg)]
p3 = {
    "verdict": p3r["verdict"], "claim": p3r["claim"], "claim_time": p3r["claim_time"], "title": p3r["title"],
    "first_pass": p3r["first_pass"], "params": b3["params"],
    "is": stats(b3["in_sample"]), "oos": stats(b3["out_of_sample"]), "oos2x": stats(b3["out_of_sample_2x_costs"]),
    "all": stats(b3["all"]), "chase_is": stats(b3["chase_same_knobs"]["in_sample"]), "chase_oos": stats(b3["chase_same_knobs"]["out_of_sample"]),
    "passes": b3["passes_edge_bar"], "edge_rule": p3r["edge_bar"]["rule"],
    "intraday": {"params": p3r["best_intraday"]["params"], "is": stats(p3r["best_intraday"]["in_sample"]), "oos": stats(p3r["best_intraday"]["out_of_sample"])},
    "funding": {k: v for k, v in p3r["funding_coverage_best"].items() if k != "with_funding_only"} |
               {"with_funding_oos": stats(p3r["funding_coverage_best"]["with_funding_only"]["out_of_sample"])},
    "equity": downsample(p3r["equity_curve"]), "split": "2024-07-01",
    "trades": compact_trades(p3r["trades"], "2024-07-01"),
    "grid": p3_grid, "cost_curve": p3r["cost_curve"], "by_year": p3r["by_year"], "by_market": p3r["by_market"],
    "by_timeframe": [{"market": x["market"], "timeframe": x["timeframe"], "symbols": x["symbols"], "span": x["span"],
                      "ball_is": stats(x["ball"]["in_sample"]), "ball_oos": stats(x["ball"]["out_of_sample"]),
                      "chase_oos": stats(x["chase"]["out_of_sample"])} for x in p3r["by_timeframe"]],
    "squeeze": [{"guard": s["guard"], "before": stats(s["before"]["out_of_sample"]), "after": stats(s["after"]["out_of_sample"]),
                 "lift": s.get("oos_lift_pct"), "improves": s.get("improves")} for s in p3r["squeeze_guard"]["ball"]],
    "knob_means": knob_means, "combos_pos": combos_pos, "markets": p3r["markets"],
    "replay": replay(p3r["replay"]), "caveats": p3r["caveats"], "failed_parts": p3r["failed_parts"],
}

# Moon Dev API panel: real rows pulled at build time from https://api.moondev.com (docs https://moondev.com/docs).
# Key from .env as MOONDEV_API_KEY, never printed, never baked in. If the key or the API is missing this build FAILS, no fake rows.
import sys
from datetime import datetime, timezone
sys.path.insert(0, str(HERE.parent / "backtests"))
from moon_dev_api import recent_liquidations, near_liq_totals, near_liq_positions

API_COINS = ["BTC", "ETH", "SOL", "XRP"]
SNIPPET = (HERE.parent / "backtests" / "moon_dev_api.py").read_text().split("# 🌙 Moon Dev API (docs")[1]
SNIPPET = "# 🌙 Moon Dev API (docs" + SNIPPET.split("\nimport pandas")[0].rstrip() + "\n\n" \
          "r = requests.get(\"https://api.moondev.com/api/liquidations/1h.json\", headers=H, timeout=60)\n" \
          "liqs = r.json()[\"liquidations\"]   # latest 100 Hyperliquid liquidations, plus r.json()[\"stats\"] for the window\n" \
          "near = requests.get(\"https://api.moondev.com/api/positions/all.json\", headers=H, timeout=60).json()[\"symbols\"]\n" \
          "print(near[\"BTC\"][\"total_short_value\"], \"of BTC shorts sit near liquidation right now\")"
pulled_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
liq = recent_liquidations("1h")
st = liq.attrs["stats"]
tot = near_liq_totals()
pos = near_liq_positions()
pos = pos[pos["coin"].isin(API_COINS)]
by_coin = sorted(st["by_coin"].items(), key=lambda kv: -kv[1]["total_value_usd"])[:10]
api = {
    "pulled_at": pulled_at, "docs": "https://moondev.com/docs",
    "endpoints": ["GET https://api.moondev.com/api/liquidations/1h.json", "GET https://api.moondev.com/api/positions/all.json"],
    "snippet": SNIPPET,
    "liq_rows": [[t.strftime("%H:%M:%S"), c, sd, r2(v, 0), p] for t, c, sd, v, p in
                 zip(liq["timestamp"], liq["coin"], liq["side"], liq["value_usd"], liq["price"])],
    "liq_window": [liq["timestamp"].min().strftime("%Y-%m-%d %H:%M:%S"), liq["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S")],
    "liq_stats": {k: st[k] for k in ("total_count", "total_value_usd", "long_value_usd", "short_value_usd", "long_count", "short_count")},
    "liq_by_coin": [[c, r2(v["long_value_usd"] / 1e6, 2), r2(v["short_value_usd"] / 1e6, 2), v["count"]] for c, v in by_coin],
    "fuel": [[c, int(tot.loc[c, "longs"]), int(tot.loc[c, "shorts"]), r2(tot.loc[c, "long_value"] / 1e6, 1), r2(tot.loc[c, "short_value"] / 1e6, 1)] for c in API_COINS],
    "fuel_updated": tot.attrs["updated_at"][:19].replace("T", " ") + " UTC",
    "nearest": [[c, sd, r2(x["distance_pct"], 2), r2(x["value"] / 1e6, 2), x["leverage"], x["liq_price"]] for c in API_COINS for sd in ("short", "long")
                for _, x in pos[(pos["coin"] == c) & (pos["side"] == sd)].nsmallest(3, "distance_pct").iterrows()],
    "where_used": ["alpha/3_bouncy_ball/moon_dev_bouncy_data.py (USE_LOCAL = False builds the liq spike guard from /api/liquidations/30d.json)",
                   "backtests/bouncy_ball_short.py (live squeeze snapshot from /api/positions/all.json, LIVE_SQUEEZE_GUARD)",
                   "dashboard/build_dashboard.py (this panel, pulled at build time)"],
}
print(f"Moon Dev API panel: {len(api['liq_rows'])} liquidations {api['liq_window'][0]} to {api['liq_window'][1]}, "
      f"{len(api['nearest'])} nearest positions for {API_COINS}, pulled {pulled_at}")

data = {"video": {"title": "5 Short Selling Trading Strategies That Made Me Millions", "channel": "TheOneLanceB",
                  "url": "https://www.youtube.com/watch?v=SvHhoD00jZI"}, "p1": p1, "p2": p2, "p3": p3, "api": api}
blob = json.dumps(data, separators=(",", ":"))
html = (HERE / "template.html").read_text().replace("__MOON_DEV_DATA__", blob.replace("</", "<\\/"))
(HERE / "index.html").write_text(html)
print(f"Moon Dev: wrote index.html, {len(html) / 1e6:.2f} MB, data from 3 real result.json files plus 2 live Moon Dev API calls")
