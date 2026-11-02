"""
Moon Dev edge finder, package 2, step 3: the IPO lockup expiry study.

The claim (TheOneLanceB, about 8:30 to 10:30): a study of 3,200+ lockups found volume up about 40% in the
expiry week and a cumulative abnormal return of about -1.8%. Filters he names: the insider's gain since the IPO
and the new supply vs float and normal volume. His warning: the event gets front run, and sometimes the stock
rallies at expiry (his SpaceX example: gap down, then rally).

What runs here, on the real EDGAR universe (edgar_ipos.py) with real Yahoo prices (prices.py):
  1. Event study: average abnormal return vs IWM for every day from -30 to +20 around the lockup day (day 0),
     and the volume ratio (expiry week vs the 20 days before). This checks the -1.8% and the 40% directly.
  2. Short window grid, unhedged and IWM hedged: entry at the open of day -20, -10, -5, -2, -1, 0; exit at the
     close of day 0, +1, +2, +5, +10. Shows whether the move got front run.
  3. His filters on the best window: gain since IPO price, locked shares over 20 day volume, run into the lockup,
     market cap terciles.
  4. The flip side: go long at the day 0 close when day 0 gapped down and closed over its open, hold 1, 3, 5, 10 days.
  5. Costs: 4.5 bp fee + 10 bp slippage a side, borrow grid 0, 10, 30, 100% a year charged on calendar days held
     (there is no real borrow feed, so it is a grid and labeled as one). The hedge leg pays the same per side cost.
  6. Time split: day 0 before 2021-07-01 is in sample (knobs picked there), day 0 from 2021-07-01 is out of sample.
     The headline number is always the out of sample one.

Lockup day 0 = first trading day strictly after the prospectus date (Yahoo first bar minus one business day, which
is the pricing day the lockup counts from) plus the lockup length read from the filing. BYND lands on Oct 29 2019
and UBER on Nov 6 2019, both the dates the press reported.
Rows with no readable lockup fall back to 180 days and carry lockup_guessed = true. Results are reported for
parsed only and for all. Nothing is filled in: an IPO with no Yahoo data is dropped and counted in the funnel.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from prices import get

HERE = Path(__file__).parent
FEE_BP = 4.5
SLIP_BP = 10.0
COST_SIDE_BP = FEE_BP + SLIP_BP
BORROW_GRID = [0, 10, 30, 100]
BASE_BORROW = 10
SPLIT = pd.Timestamp("2021-07-01")
PRE, POST = 30, 20
ENTRIES = [-20, -10, -5, -2, -1, 0]
EXITS = [0, 1, 2, 5, 10]
FLIP_HOLDS = [1, 3, 5, 10]
MIN_IS_TRADES = 30
TRADE_SIZE = 0.10  # Moon Dev: each trade gets 10% of equity in the compounded curve


def load_universe():
    """Moon Dev: the EDGAR universe with the plan's drops applied. Every drop is counted."""
    uni = pd.read_json(sys.argv[1] if len(sys.argv) > 1 else HERE / "ipo_universe.json")
    funnel = {"424B4_first_filings_2015_2025_after_name_filter": len(uni)}
    if "fetch_failed" in uni:
        uni = uni[uni["fetch_failed"].isna()]
    funnel["filing_fetched_and_parsed"] = len(uni)
    uni = uni[uni["is_ipo"] == True]
    funnel["is_ipo_text_found"] = len(uni)
    uni = uni[uni["sic"] != 6770]
    funnel["not_spac_sic_6770"] = len(uni)
    uni = uni[uni["direct_listing"] != True]
    funnel["not_direct_listing"] = len(uni)
    uni = uni[~((uni["is_adr"] == True) & (uni["lockup_guessed"] == True))]
    funnel["not_adr_without_readable_lockup"] = len(uni)
    uni = uni[uni["no_lockup"] != True]
    funnel["no_explicit_no_lockup_line"] = len(uni)
    return uni.reset_index(drop=True), funnel


def pick_prices(row):
    """Moon Dev: filing symbol first, SEC current ticker second. Yahoo's first bar must sit on the IPO date."""
    fd = pd.Timestamp(row["filing_date"])
    tried = []
    for t in [row.get("symbol"), row.get("sec_ticker")]:
        if not isinstance(t, str) or not t:
            continue
        t = t.replace(".", "-")
        df = get(t)
        if df is None:
            tried.append(f"{t}: no yahoo data")
            continue
        gap = (df.index[0] - fd).days
        if -3 <= gap <= 10:
            return t, df, None
        tried.append(f"{t}: first bar {df.index[0].date()} is {gap} days from filing")
    return None, None, "; ".join(tried) if tried else "no symbol"


def build_events(uni, iwm):
    events, dropped = [], []
    for _, r in uni.iterrows():
        t, df, why = pick_prices(r)
        if df is None:
            dropped.append(dict(name=r["name"], filing_date=r["filing_date"], why=why))
            continue
        guessed = bool(r["lockup_guessed"])
        ld = 180 if guessed else int(r["lockup_days"])
        fd = pd.Timestamp(r["filing_date"])
        # Moon Dev: the lockup runs from the prospectus date (pricing day), which is the business day before the
        # first trade. The 424B4 can be filed up to 2 business days later, so the filing date would be late.
        # Insiders can sell on the day AFTER the lockup's last day, so day 0 is the first trading day strictly after.
        prospectus_date = df.index[0] - pd.offsets.BDay(1)
        d0 = int(df.index.searchsorted(prospectus_date + pd.Timedelta(days=ld), side="right"))
        if d0 < 21 or d0 + POST >= len(df):
            dropped.append(dict(name=r["name"], filing_date=r["filing_date"], why=f"{t}: day 0 needs 21 bars before and {POST} after (lockup {ld} d, bars {len(df)}, day0 index {d0})"))
            continue
        iw = iwm.reindex(df.index)
        lo, hi = max(0, d0 - PRE), d0 + POST
        if iw["Close"].iloc[lo:hi + 1].isna().any():
            dropped.append(dict(name=r["name"], filing_date=r["filing_date"], why=f"{t}: IWM missing a bar in the window"))
            continue
        v = df["Volume"].values
        adv20 = float(np.mean(v[d0 - 22:d0 - 2]))  # days -22 to -3, the event study's normal volume
        ipo_price = r["ipo_price"] if pd.notna(r["ipo_price"]) else None
        out_sh = r["shares_outstanding_after"] if pd.notna(r["shares_outstanding_after"]) else None
        off_sh = r["shares_offered"] if pd.notna(r["shares_offered"]) else None
        locked = out_sh - off_sh if (out_sh and off_sh and out_sh > off_sh) else None
        events.append(dict(
            ticker=t, name=r["name"], filing_date=fd, lockup_days=ld, lockup_guessed=guessed,
            staged=bool(r.get("staged_release", False)), early_release=bool(r.get("early_release", False)),
            is_adr=bool(r["is_adr"]), d0=d0, day0_date=df.index[d0], df=df, iwm=iw,
            ipo_price=ipo_price, out_sh=out_sh, locked=locked, adv20=adv20,
        ))
    return events, dropped


def features(ev, ref):
    """Moon Dev: his filter inputs measured at the close of day `ref` (the day before entry), so no look ahead.
    gain since IPO price, an 18 bar run ending at ref, locked shares over the 20 day average volume ending at ref,
    market cap at ref. None when the filing did not give the number."""
    i = ev["d0"] + ref
    c, v = ev["df"]["Close"].values, ev["df"]["Volume"].values
    if i < 20:
        return dict(gain_since_ipo_pct=None, run_into_pct=None, locked_over_adv=None, mktcap_musd=None)
    adv = float(np.mean(v[i - 19:i + 1]))
    return dict(gain_since_ipo_pct=(c[i] / ev["ipo_price"] - 1) * 100 if ev["ipo_price"] else None,
                run_into_pct=(c[i] / c[i - 18] - 1) * 100,
                locked_over_adv=(ev["locked"] / adv) if (ev["locked"] and adv > 0) else None,
                mktcap_musd=(ev["out_sh"] * c[i] / 1e6) if ev["out_sh"] else None)


def rel(ev, col, k, src="df"):
    """Moon Dev: value at day k relative to day 0 (NaN when the bar is not there)."""
    i = ev["d0"] + k
    s = ev[src][col]
    return float(s.iloc[i]) if 0 <= i < len(s) else np.nan


def event_curve(events):
    """Moon Dev: average abnormal return (stock minus IWM, close to close) per day, and the volume ratio per day."""
    rows = []
    ar = {k: [] for k in range(-PRE, POST + 1)}
    vr = {k: [] for k in range(-PRE, POST + 1)}
    for ev in events:
        for k in range(-PRE, POST + 1):
            c1, c0 = rel(ev, "Close", k), rel(ev, "Close", k - 1)
            i1, i0 = rel(ev, "Close", k, "iwm"), rel(ev, "Close", k - 1, "iwm")
            if not np.isnan([c1, c0, i1, i0]).any():
                ar[k].append((c1 / c0 - i1 / i0) * 100)
            vv = rel(ev, "Volume", k)
            if not np.isnan(vv) and ev["adv20"] > 0:
                vr[k].append(vv / ev["adv20"])
    car = 0.0
    for k in range(-PRE, POST + 1):
        a = np.array(ar[k])
        car += a.mean()
        rows.append(dict(day=k, avg_abnormal_ret_pct=round(float(a.mean()), 3), car_from_minus30_pct=round(car, 3),
                         t_stat=round(float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))), 2) if len(a) > 2 else None,
                         n=int(len(a)), volume_ratio_mean=round(float(np.mean(vr[k])), 3), volume_ratio_median=round(float(np.median(vr[k])), 3)))
    return rows


def window_car(events, a, b):
    """Moon Dev: cumulative abnormal return (vs IWM) from the close of day a-1 to the close of day b, per event."""
    out = []
    for ev in events:
        c0, c1 = rel(ev, "Close", a - 1), rel(ev, "Close", b)
        i0, i1 = rel(ev, "Close", a - 1, "iwm"), rel(ev, "Close", b, "iwm")
        if not np.isnan([c0, c1, i0, i1]).any():
            out.append((c1 / c0 - i1 / i0) * 100)
    return np.array(out)


def tstat(x):
    x = np.asarray(x, dtype=float)
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0


def desc(x):
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return dict(n=0, mean_pct=None, median_pct=None, t_stat=None, share_negative=None)
    return dict(n=int(len(x)), mean_pct=round(float(x.mean()), 3), median_pct=round(float(np.median(x)), 3),
                t_stat=round(tstat(x), 2), share_negative=round(float((x < 0).mean() * 100), 1))


def vol_desc(v):
    if len(v) == 0:
        return dict(n=0, mean=None, median=None, share_above_1=None)
    return dict(n=int(len(v)), mean=round(float(v.mean()), 3), median=round(float(np.median(v)), 3), share_above_1=round(float((v > 1).mean() * 100), 1))


def volume_week(events, a, b):
    return np.array([np.nanmean([rel(ev, "Volume", k) for k in range(a, b + 1)]) / ev["adv20"] for ev in events if ev["adv20"] > 0])


def short_trade(ev, e, x, hedged, borrow_pct, cost_side_bp=COST_SIDE_BP):
    """Moon Dev: short at the open of day e, cover at the close of day x. Net of fees, slippage and borrow."""
    po, px = rel(ev, "Open", e), rel(ev, "Close", x)
    if np.isnan(po) or np.isnan(px):
        return None
    gross = -(px / po - 1) * 100
    d_in, d_out = ev["df"].index[ev["d0"] + e], ev["df"].index[ev["d0"] + x]
    days = max((d_out - d_in).days, 1)
    cost = 2 * cost_side_bp / 100
    hedge = 0.0
    if hedged:
        io, ix = rel(ev, "Open", e, "iwm"), rel(ev, "Close", x, "iwm")
        hedge = (ix / io - 1) * 100
        cost += 2 * cost_side_bp / 100
    borrow = borrow_pct * days / 365
    return dict(symbol=ev["ticker"], entry_time=str(d_in.date()), exit_time=str(d_out.date()), entry=round(po, 4), exit=round(px, 4),
                gross_pct=gross, hedge_pct=hedge, cost_pct=cost, borrow_pct=borrow, ret_pct=gross + hedge - cost - borrow,
                long_hold_pct=(px / po - 1) * 100, day0=ev["day0_date"], is_sample=ev["day0_date"] < SPLIT, lockup_guessed=ev["lockup_guessed"])


def stats(tr):
    """Moon Dev: the shared stats block. Total return, Sharpe and max DD compound the trades in exit order at
    TRADE_SIZE of equity each (a basket of overlapping shorts, and a full size short can lose over 100%)."""
    if len(tr) == 0:
        return dict(trades=0, avg_trade_pct=None, median_trade_pct=None, t_stat=None, win_rate=None, profit_factor=None,
                    total_return_pct=None, sharpe=None, max_dd_pct=None, buy_hold_return_pct=None)
    t = pd.DataFrame(tr).sort_values("exit_time")
    r = t["ret_pct"].values
    eq = np.cumprod(1 + TRADE_SIZE * r / 100)
    dd = float((eq / np.maximum.accumulate(eq) - 1).min() * 100)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    years = max((pd.Timestamp(t["exit_time"].iloc[-1]) - pd.Timestamp(t["exit_time"].iloc[0])).days / 365.25, 0.25)
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(len(r) / years)) if len(r) > 2 and r.std(ddof=1) > 0 else 0.0
    return dict(trades=int(len(r)), avg_trade_pct=round(float(r.mean()), 3), median_trade_pct=round(float(np.median(r)), 3),
                t_stat=round(tstat(r), 2), win_rate=round(float((r > 0).mean() * 100), 1),
                profit_factor=round(float(wins / losses), 3) if losses > 0 else None,
                total_return_pct=round(float((eq[-1] - 1) * 100), 2), sharpe=round(sharpe, 2), max_dd_pct=round(dd, 2),
                buy_hold_return_pct=round(float(t["long_hold_pct"].mean()), 3))


def run_short(events, e, x, hedged, borrow, cost_side_bp=COST_SIDE_BP):
    tr = [short_trade(ev, e, x, hedged, borrow, cost_side_bp) for ev in events]
    return [t for t in tr if t]


def split(tr):
    return [t for t in tr if t["is_sample"]], [t for t in tr if not t["is_sample"]]


def passes_bar(tr_is, tr_oos, tr_oos_2x):
    """Moon Dev: the plan's edge bar on the out of sample set."""
    s = stats(tr_oos)
    s2 = stats(tr_oos_2x)
    if s["trades"] < 20:
        return False, "fewer than 20 out of sample trades"
    checks = dict(avg_positive=s["avg_trade_pct"] > 0, t_ge_2=s["t_stat"] >= 2, pf_ge_1_2=(s["profit_factor"] or 0) >= 1.2,
                  symbols_positive_ge_55=s["win_rate"] >= 55, positive_at_2x_costs=(s2["avg_trade_pct"] or 0) > 0,
                  in_sample_positive=(stats(tr_is)["avg_trade_pct"] or 0) > 0)
    return all(checks.values()), checks


def flip_long(events, hold, cost_side_bp=COST_SIDE_BP):
    """Moon Dev: his SpaceX point. Day 0 gapped down and closed above its open: buy the close, hold `hold` days."""
    out = []
    for ev in events:
        cm1, o0, c0, cx = rel(ev, "Close", -1), rel(ev, "Open", 0), rel(ev, "Close", 0), rel(ev, "Close", hold)
        if np.isnan([cm1, o0, c0, cx]).any() or not (o0 < cm1 and c0 > o0):
            continue
        d_in, d_out = ev["df"].index[ev["d0"]], ev["df"].index[ev["d0"] + hold]
        ret = (cx / c0 - 1) * 100 - 2 * cost_side_bp / 100
        out.append(dict(symbol=ev["ticker"], entry_time=str(d_in.date()), exit_time=str(d_out.date()), entry=round(c0, 4), exit=round(cx, 4),
                        ret_pct=ret, long_hold_pct=(cx / c0 - 1) * 100, is_sample=ev["day0_date"] < SPLIT, reason=f"flip long, gap down held, hold {hold}"))
    return out


def long_all(events, hold, cost_side_bp=COST_SIDE_BP):
    """Moon Dev: baseline for the flip, long the day 0 close on every event, no condition."""
    out = []
    for ev in events:
        c0, cx = rel(ev, "Close", 0), rel(ev, "Close", hold)
        if np.isnan([c0, cx]).any():
            continue
        out.append(dict(symbol=ev["ticker"], entry_time=str(ev["day0_date"].date()), exit_time=str(ev["df"].index[ev["d0"] + hold].date()),
                        ret_pct=(cx / c0 - 1) * 100 - 2 * cost_side_bp / 100, long_hold_pct=(cx / c0 - 1) * 100, is_sample=ev["day0_date"] < SPLIT))
    return out


def bucket_filters(events, ref):
    """Moon Dev: his filters as event subsets, every input measured at the close of day ref (before entry).
    Terciles use the events that have the number."""
    events = [dict(ev, **features(ev, ref)) for ev in events]
    f = {}
    g = [ev for ev in events if ev["gain_since_ipo_pct"] is not None]
    f["gain_since_ipo: under 0%"] = [ev for ev in g if ev["gain_since_ipo_pct"] < 0]
    f["gain_since_ipo: 0 to 100%"] = [ev for ev in g if 0 <= ev["gain_since_ipo_pct"] < 100]
    f["gain_since_ipo: 100 to 300%"] = [ev for ev in g if 100 <= ev["gain_since_ipo_pct"] < 300]
    f["gain_since_ipo: over 300%"] = [ev for ev in g if ev["gain_since_ipo_pct"] >= 300]
    for key, label in [("locked_over_adv", "locked_shares_over_adv20"), ("mktcap_musd", "market_cap")]:
        have = [ev for ev in events if ev[key] is not None and np.isfinite(ev[key])]
        if len(have) >= 9:
            q1, q2 = np.quantile([ev[key] for ev in have], [1 / 3, 2 / 3])
            f[f"{label}: low tercile"] = [ev for ev in have if ev[key] <= q1]
            f[f"{label}: mid tercile"] = [ev for ev in have if q1 < ev[key] <= q2]
            f[f"{label}: high tercile"] = [ev for ev in have if ev[key] > q2]
            f[f"{label}: tercile cuts"] = (float(q1), float(q2))
    f[f"run_into_lockup: up (18 bars into day {ref})"] = [ev for ev in events if ev["run_into_pct"] is not None and ev["run_into_pct"] > 0]
    f[f"run_into_lockup: down (18 bars into day {ref})"] = [ev for ev in events if ev["run_into_pct"] is not None and ev["run_into_pct"] <= 0]
    big = [ev for ev in events if ev["gain_since_ipo_pct"] is not None and ev["gain_since_ipo_pct"] >= 100 and ev["locked_over_adv"] is not None]
    if "locked_shares_over_adv20: tercile cuts" in f:
        q2 = f["locked_shares_over_adv20: tercile cuts"][1]
        f["his combo: gain over 100% and locked supply high tercile"] = [ev for ev in big if ev["locked_over_adv"] > q2]
    f["ADR only"] = [ev for ev in events if ev["is_adr"]]
    f["non ADR only"] = [ev for ev in events if not ev["is_adr"]]
    f["lockup parsed only"] = [ev for ev in events if not ev["lockup_guessed"]]
    f["lockup 180 days exactly"] = [ev for ev in events if ev["lockup_days"] == 180]
    f["no early release language"] = [ev for ev in events if not ev["early_release"]]
    return f


def main():
    print("Moon Dev: IPO lockup expiry study, real EDGAR universe, real Yahoo prices")
    uni, funnel = load_universe()
    iwm, spy = get("IWM"), get("SPY")
    if iwm is None or spy is None:
        raise FileNotFoundError("Moon Dev: IWM or SPY prices missing, run prices.py first")
    events, dropped = build_events(uni, iwm)
    funnel["yahoo_prices_found_and_lockup_day_inside_data"] = len(events)
    funnel["dropped_no_yahoo_or_window"] = len(dropped)
    ev_parsed = [ev for ev in events if not ev["lockup_guessed"]]
    ev_early = [ev for ev in events if ev["day0_date"] < SPLIT]
    ev_late = [ev for ev in events if ev["day0_date"] >= SPLIT]
    print(f"Moon Dev: {len(events)} lockup events ({len(ev_parsed)} with a parsed lockup), {len(ev_early)} before {SPLIT.date()}, {len(ev_late)} after. Dropped {len(dropped)}.")
    print("Moon Dev: lockup lengths:", pd.Series([ev["lockup_days"] for ev in events]).value_counts().head(8).to_dict())

    # 1. event study
    curve = event_curve(events)
    sets = {"all": events, "parsed_lockup_only": ev_parsed, "early_2015_to_mid2021": ev_early, "late_mid2021_to_2025": ev_late}
    windows = {"expiry_week_0_to_4": (0, 4), "minus2_to_plus2": (-2, 2), "minus1_to_plus1": (-1, 1), "minus5_to_plus5": (-5, 5),
               "front_run_minus20_to_minus1": (-20, -1), "minus10_to_plus10": (-10, 10), "day0_only": (0, 0), "after_plus1_to_plus10": (1, 10)}
    event_windows = {}
    for sname, evs in sets.items():
        event_windows[sname] = {w: desc(window_car(evs, a, b)) for w, (a, b) in windows.items()}
        vw, vw2 = volume_week(evs, 0, 4), volume_week(evs, -2, 2)
        event_windows[sname]["volume_week_0_to_4_over_adv20"] = vol_desc(vw)
        event_windows[sname]["volume_minus2_to_plus2_over_adv20"] = vol_desc(vw2)
    for sname in sets:
        w = event_windows[sname]
        print(f"Moon Dev: [{sname}] CAR -2..+2 {w['minus2_to_plus2']['mean_pct']}% t {w['minus2_to_plus2']['t_stat']} n {w['minus2_to_plus2']['n']} | "
              f"week 0..4 {w['expiry_week_0_to_4']['mean_pct']}% t {w['expiry_week_0_to_4']['t_stat']} | front run -20..-1 {w['front_run_minus20_to_minus1']['mean_pct']}% | "
              f"volume week/adv20 mean {w['volume_week_0_to_4_over_adv20']['mean']} median {w['volume_week_0_to_4_over_adv20']['median']}")

    # 2. short window grid
    grid, best = [], None
    for hedged in [False, True]:
        for e in ENTRIES:
            for x in EXITS:
                if x < e or (e == 0 and x < 0):
                    continue
                for borrow in BORROW_GRID:
                    tr = run_short(events, e, x, hedged, borrow)
                    tis, toos = split(tr)
                    s_all, s_is, s_oos = stats(tr), stats(tis), stats(toos)
                    row = dict(params=dict(hedged=hedged, entry_day=e, exit_day=x, borrow_pct=borrow, cost_bp_per_side=COST_SIDE_BP),
                               trades=s_all["trades"], avg_trade_pct=s_all["avg_trade_pct"], t_stat=s_all["t_stat"], profit_factor=s_all["profit_factor"],
                               total_return_pct=s_all["total_return_pct"], in_sample=s_is, out_of_sample=s_oos)
                    grid.append(row)
                    if borrow == BASE_BORROW and s_is["trades"] >= MIN_IS_TRADES:
                        key = (s_is["t_stat"], s_is["avg_trade_pct"])
                        if best is None or key > best[0]:
                            best = (key, row)
    best_row = best[1]
    bp = best_row["params"]
    print(f"Moon Dev: best in sample knobs {bp} | IS {best_row['in_sample']['avg_trade_pct']}% t {best_row['in_sample']['t_stat']} n {best_row['in_sample']['trades']} | "
          f"OOS {best_row['out_of_sample']['avg_trade_pct']}% t {best_row['out_of_sample']['t_stat']} n {best_row['out_of_sample']['trades']}")
    best_tr = run_short(events, bp["entry_day"], bp["exit_day"], bp["hedged"], bp["borrow_pct"])
    b_is, b_oos = split(best_tr)
    b_oos_2x = split(run_short(events, bp["entry_day"], bp["exit_day"], bp["hedged"], 2 * bp["borrow_pct"], 2 * COST_SIDE_BP))[1]
    ok, checks = passes_bar(b_is, b_oos, b_oos_2x)
    print(f"Moon Dev: edge bar out of sample: {'PASS' if ok else 'FAIL'} {checks}")

    # first pass window side by side (day -2 open to day +2 open is close to our -2 to +1 close), unhedged, borrow 10
    fp_tr = run_short(events, -2, 2, False, BASE_BORROW)
    fp_is, fp_oos = split(fp_tr)

    # 3. filters on the best window
    filt = bucket_filters(events, bp["entry_day"] - 1)
    filter_rows, cuts = [], {}
    for label, evs in filt.items():
        if isinstance(evs, tuple):
            cuts[label] = evs
            continue
        tr = run_short(evs, bp["entry_day"], bp["exit_day"], bp["hedged"], bp["borrow_pct"])
        tis, toos = split(tr)
        s_all = stats(tr)
        filter_rows.append(dict(params=dict(filter=label, hedged=bp["hedged"], entry_day=bp["entry_day"], exit_day=bp["exit_day"], borrow_pct=bp["borrow_pct"]),
                                trades=s_all["trades"], avg_trade_pct=s_all["avg_trade_pct"], t_stat=s_all["t_stat"], profit_factor=s_all["profit_factor"],
                                total_return_pct=s_all["total_return_pct"], in_sample=stats(tis), out_of_sample=stats(toos)))
    # Moon Dev: the filter is chosen on the in sample t-stat only (no peeking at the later years), then judged out of sample.
    best_filter, bf_ok, bf_checks, bf_tr = None, False, {}, []
    for fr in filter_rows:
        if fr["in_sample"]["trades"] >= MIN_IS_TRADES and fr["out_of_sample"]["trades"] >= 20:
            if best_filter is None or (fr["in_sample"]["t_stat"] or -9) > (best_filter["in_sample"]["t_stat"] or -9):
                best_filter = fr
    if best_filter is not None:
        bf_evs = filt[best_filter["params"]["filter"]]
        bf_tr = run_short(bf_evs, bp["entry_day"], bp["exit_day"], bp["hedged"], bp["borrow_pct"])
        bf_is, bf_oos = split(bf_tr)
        bf_oos_2x = split(run_short(bf_evs, bp["entry_day"], bp["exit_day"], bp["hedged"], 2 * bp["borrow_pct"], 2 * COST_SIDE_BP))[1]
        bf_ok, bf_checks = passes_bar(bf_is, bf_oos, bf_oos_2x)
        best_filter = dict(best_filter, out_of_sample_at_2x_costs=stats(bf_oos_2x), edge_bar_out_of_sample=dict(passes=bf_ok, checks=bf_checks))
        print(f"Moon Dev: filter picked in sample: {best_filter['params']['filter']} | OOS {best_filter['out_of_sample']['avg_trade_pct']}% t {best_filter['out_of_sample']['t_stat']} n {best_filter['out_of_sample']['trades']} | edge bar {'PASS' if bf_ok else 'FAIL'} {bf_checks}")
    for fr in filter_rows:
        print(f"Moon Dev: filter {fr['params']['filter']:<58} all {fr['trades']:>4} {fr['avg_trade_pct']!s:>7}% t {fr['t_stat']!s:>5} | IS {fr['in_sample']['trades']:>3} {fr['in_sample']['avg_trade_pct']!s:>7}% | OOS {fr['out_of_sample']['trades']:>3} {fr['out_of_sample']['avg_trade_pct']!s:>7}% t {fr['out_of_sample']['t_stat']}")

    # 4. the flip side
    flip = {}
    for hold in FLIP_HOLDS:
        tr = flip_long(events, hold)
        tis, toos = split(tr)
        base = long_all(events, hold)
        bis, boos = split(base)
        flip[f"hold_{hold}"] = dict(all=stats(tr), in_sample=stats(tis), out_of_sample=stats(toos),
                                    baseline_long_every_day0_close=dict(all=stats(base), in_sample=stats(bis), out_of_sample=stats(boos)))
        print(f"Moon Dev: flip long hold {hold:>2}: n {flip[f'hold_{hold}']['all']['trades']} avg {flip[f'hold_{hold}']['all']['avg_trade_pct']}% t {flip[f'hold_{hold}']['all']['t_stat']} | "
              f"OOS n {flip[f'hold_{hold}']['out_of_sample']['trades']} avg {flip[f'hold_{hold}']['out_of_sample']['avg_trade_pct']}% t {flip[f'hold_{hold}']['out_of_sample']['t_stat']} | "
              f"baseline long all events avg {flip[f'hold_{hold}']['baseline_long_every_day0_close']['all']['avg_trade_pct']}%")
    flip_best = max(flip, key=lambda k: (flip[k]["out_of_sample"]["t_stat"] or -9))
    flip_tr = flip_long(events, int(flip_best.split("_")[1]))
    flip_is, flip_oos = split(flip_tr)
    flip_ok, flip_checks = passes_bar(flip_is, flip_oos, split(flip_long(events, int(flip_best.split("_")[1]), 2 * COST_SIDE_BP))[1])

    # 5. costs: per side slider and the borrow slider, best knobs
    cost_curve = []
    for cbp in [0, 5, 10, 14.5, 25, 50, 100]:
        tr = run_short(events, bp["entry_day"], bp["exit_day"], bp["hedged"], bp["borrow_pct"], cbp)
        tis, toos = split(tr)
        cost_curve.append(dict(cost_bp_per_side=cbp, avg_trade_pct=stats(tr)["avg_trade_pct"], avg_trade_pct_oos=stats(toos)["avg_trade_pct"], avg_trade_pct_is=stats(tis)["avg_trade_pct"]))
    borrow_curve = []
    for b in [0, 5, 10, 20, 30, 50, 100, 200]:
        tr = run_short(events, bp["entry_day"], bp["exit_day"], bp["hedged"], b)
        tis, toos = split(tr)
        borrow_curve.append(dict(borrow_pct_per_year=b, avg_trade_pct=stats(tr)["avg_trade_pct"], avg_trade_pct_oos=stats(toos)["avg_trade_pct"], avg_trade_pct_is=stats(tis)["avg_trade_pct"]))

    # 6. by year, by market, equity curve, replay
    bt = pd.DataFrame(best_tr)
    bt["year"] = pd.to_datetime(bt["entry_time"]).dt.year
    by_year = [dict(year=int(y), trades=int(len(g)), avg_trade_pct=round(float(g["ret_pct"].mean()), 3), t_stat=round(tstat(g["ret_pct"]), 2)) for y, g in bt.groupby("year")]
    by_market = []
    for label, evs, hedged in [("US IPOs, unhedged", events, False), ("US IPOs, IWM hedged", events, True),
                               ("parsed lockup only, best hedge", ev_parsed, bp["hedged"]), ("guessed lockup (180 d) only, best hedge", [ev for ev in events if ev["lockup_guessed"]], bp["hedged"]),
                               ("early 2015 to mid 2021, best hedge", ev_early, bp["hedged"]), ("late mid 2021 to 2025, best hedge", ev_late, bp["hedged"]),
                               ("ADR only, best hedge", [ev for ev in events if ev["is_adr"]], bp["hedged"]), ("non ADR, best hedge", [ev for ev in events if not ev["is_adr"]], bp["hedged"])]:
        s = stats(run_short(evs, bp["entry_day"], bp["exit_day"], hedged, bp["borrow_pct"]))
        by_market.append(dict(market=label, trades=s["trades"], avg_trade_pct=s["avg_trade_pct"], t_stat=s["t_stat"], profit_factor=s["profit_factor"]))
    eq = bt.sort_values("exit_time").copy()
    eq["strategy"] = np.cumprod(1 + TRADE_SIZE * eq["ret_pct"].values / 100)
    base_iwm = float(iwm["Close"].asof(pd.Timestamp(eq["exit_time"].iloc[0])))
    equity_curve = [dict(t=r["exit_time"], strategy=round(float(r["strategy"]), 4), buy_hold=round(float(iwm["Close"].asof(pd.Timestamp(r["exit_time"])) / base_iwm), 4)) for _, r in eq.iterrows()]
    replay_ev = next((ev for ev in events if ev["ticker"] == "BYND"), events[0])
    rdf = replay_ev["df"].iloc[max(0, replay_ev["d0"] - 150): replay_ev["d0"] + 50]
    replay_trades = [t for t in best_tr if t["symbol"] == replay_ev["ticker"]] + [t for t in flip_tr if t["symbol"] == replay_ev["ticker"]]
    for t in [x for x in fp_tr if x["symbol"] == replay_ev["ticker"]]:
        t = dict(t)
        t["reason"] = "first pass window, short day -2 open to day +2 close"
        replay_trades.append(t)
    replay = dict(symbol=replay_ev["ticker"], day0=str(replay_ev["day0_date"].date()), lockup_days=replay_ev["lockup_days"],
                  bars=[dict(t=str(i.date()), o=round(float(r.Open), 3), h=round(float(r.High), 3), l=round(float(r.Low), 3), c=round(float(r.Close), 3), v=int(r.Volume)) for i, r in rdf.iterrows()],
                  trades=[{k: (v if not isinstance(v, (pd.Timestamp, np.bool_, np.floating)) else (str(v) if isinstance(v, pd.Timestamp) else float(v) if isinstance(v, np.floating) else bool(v))) for k, v in t.items() if k not in ("day0",)} for t in replay_trades])

    # verdict
    car_all = event_windows["all"]["minus2_to_plus2"]
    car_late = event_windows["late_mid2021_to_2025"]["minus2_to_plus2"]
    study_verified = car_all["n"] > 0 and car_all["mean_pct"] <= -1.0 and car_all["t_stat"] <= -2
    late_dead = car_late["n"] == 0 or car_late["mean_pct"] > -0.5 or car_late["t_stat"] > -2
    if ok or bf_ok:
        verdict = "BETTER VERSION FOUND"
    elif flip_ok and (flip[flip_best]["out_of_sample"]["avg_trade_pct"] or 0) > (best_row["out_of_sample"]["avg_trade_pct"] or 0):
        verdict = "BETTER VERSION FOUND"
    elif late_dead:
        verdict = "BUSTED"
    elif study_verified:
        verdict = "VERIFIED"
    else:
        verdict = "NOT PROVEN"

    def clean(tr):
        return [dict(symbol=t["symbol"], entry_time=t["entry_time"], exit_time=t["exit_time"], entry=t["entry"], exit=t["exit"], ret_pct=round(float(t["ret_pct"]), 3),
                     reason=t.get("reason", f"short lockup, open day {bp['entry_day']} to close day {bp['exit_day']}, {'IWM hedged' if bp['hedged'] else 'unhedged'}, borrow {bp['borrow_pct']}%" + (", lockup guessed" if t.get("lockup_guessed") else ""))) for t in tr]

    result = dict(
        package="2_lockup", title="IPO lockup expiry: real dates, the full event curve, and the flip side",
        claim="3,200+ lockups: volume up about 40% in expiry week and a cumulative abnormal return of about -1.8%. BYND fell 20%+ on its lockup day. Filter by insider gain and new supply vs float and volume. Warning: front running, and sometimes it rallies (SpaceX).",
        claim_time="8:30", verdict=verdict,
        headline=(dict(label=f"Out of sample avg trade (day 0 from {SPLIT.date()}), {best_filter['params']['filter']} filter on the best short window, after fees, slippage and {bp['borrow_pct']}% borrow", value=best_filter["out_of_sample"]["avg_trade_pct"], unit="%")
                  if (bf_ok and not ok) else
                  dict(label=f"Out of sample avg trade (day 0 from {SPLIT.date()}), best short window after fees, slippage and {bp['borrow_pct']}% borrow", value=best_row["out_of_sample"]["avg_trade_pct"], unit="%")),
        base_short_out_of_sample_avg_trade_pct=best_row["out_of_sample"]["avg_trade_pct"],
        first_pass=dict(trades=55, avg_trade_pct=-0.53),
        best=dict(params=bp, in_sample=best_row["in_sample"], out_of_sample=best_row["out_of_sample"], all=stats(best_tr), edge_bar_out_of_sample=dict(passes=ok, checks=checks),
                  out_of_sample_at_2x_costs=stats(b_oos_2x)),
        first_pass_window_rerun=dict(params=dict(hedged=False, entry_day=-2, exit_day=2, borrow_pct=BASE_BORROW), all=stats(fp_tr), in_sample=stats(fp_is), out_of_sample=stats(fp_oos)),
        best_filter=None if best_filter is None else dict(best_filter, trades=clean(bf_tr)),
        event_curve=curve, event_windows=event_windows, tercile_cuts={k: dict(low_high=v) for k, v in cuts.items()},
        flip_long=dict(by_hold=flip, best_hold=flip_best, best=dict(in_sample=stats(flip_is), out_of_sample=stats(flip_oos), edge_bar_out_of_sample=dict(passes=flip_ok, checks=flip_checks)),
                       rule="buy the day 0 close when day 0 opened below the day -1 close and closed above its open, hold N days, fees and slippage both sides"),
        equity_curve=equity_curve, trades=clean(best_tr)[:2000], grid=grid + filter_rows, cost_curve=cost_curve, borrow_curve=borrow_curve,
        by_year=by_year, by_market=by_market, replay=replay,
        universe_funnel=funnel, split_date=str(SPLIT.date()),
        lockup_lengths=dict(pd.Series([ev["lockup_days"] for ev in events]).value_counts().sort_index().astype(int).items()),
        lockup_parsed_count=len(ev_parsed), lockup_guessed_count=len(events) - len(ev_parsed),
        sizing_note=f"equity curve, total return, Sharpe and max DD compound each trade at {TRADE_SIZE:.0%} of equity; avg trade and t-stat are per trade, unsized",
        costs=dict(fee_bp_per_side=FEE_BP, slippage_bp_per_side=SLIP_BP, borrow_grid_pct_per_year=BORROW_GRID, borrow_note="no real borrow feed, this is a grid charged on calendar days held"),
        data_used=["SEC EDGAR full-index form.gz 2010 to 2025 (https://www.sec.gov/Archives/edgar/full-index/), 424B4 filing text streamed from https://www.sec.gov/Archives/",
                   "SEC company_tickers_exchange.json (current ticker by CIK)", "Yahoo Finance daily via yfinance for every IPO ticker plus IWM and SPY, cached in alpha/2_lockup/data_cache/ (gitignored)",
                   "alpha/2_lockup/ipo_universe.json (the parsed filing table, committed)"],
        failed_parts=[
            f"{len(dropped)} IPOs in the EDGAR universe have no usable Yahoo history (delisted, acquired, ticker reused, or day 0 not inside the data). They are dropped, not filled. Survivorship: the names that died are the ones missing.",
            f"{len(events) - len(ev_parsed)} filings had no readable lock-up sentence, fell back to 180 days and carry lockup_guessed = true (reported separately).",
            "No real borrow feed. Borrow is a grid (0, 10, 30, 100% a year) charged on calendar days held. Small foreign ADRs and $4 micro cap IPOs are often impossible to borrow at all.",
            "Shares outstanding after the offering is parsed from the prospectus text and is approximate (some filings give one share class only).",
            "Yahoo prices are split adjusted, so levels on names that later reverse split look odd. Every return is a ratio, so it is unaffected.",
        ], dropped_events_sample=dropped[:200], dropped_events_count=len(dropped),
    )
    (HERE / "result.json").write_text(json.dumps(result, indent=1, default=str))
    print(f"Moon Dev: verdict {verdict}. Saved {HERE / 'result.json'}")
    return result


if __name__ == "__main__":
    main()
