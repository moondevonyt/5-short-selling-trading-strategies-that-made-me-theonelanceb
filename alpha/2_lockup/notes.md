# Package 2: IPO lockup expiry. Real dates, the full event curve, and the flip side

Built by Moon Dev. Video: TheOneLanceB, about 8:30 to 10:30.

**Verdict: BUSTED.** The -1.8% expiry week drop is not in 2015 to 2025 data. The short paid in 2015 to mid 2021
(+1.85% a trade, t 2.65) and loses since (-2.85% a trade, t -1.94). The move that does exist happens BEFORE the
date (day -20 to -1, -2.3%, t -2.3), which is his own front running warning. No window, no filter and no hedge
passes the edge bar out of sample. The long flip (his SpaceX point) beats the short in the later years but is
not proven either.

## What was built

| Step | Real data | Result |
|---|---|---|
| EDGAR 424B4 index, 2010 to 2025 (`edgar_ipos.py`) | 7,940 424B4 rows, 5,428 first filings per CIK, 3,921 dated 2015 to 2025, 2,871 after dropping Acquisition, trust, fund and note names | every one fetched and parsed |
| Filing text parse | IPO line found on 2,386; SIC 6770 (SPAC) dropped 310; direct listings 16; ADRs with no readable lockup 10 | 2,050 IPOs |
| Lock-up length read from the filing | 180 days: 1,169; 90: 72; 365: 12; 120: 5; a few 150, 270, 91, 181 | 1,176 parsed, 102 fell back to 180 (`lockup_guessed = true`) |
| Yahoo daily prices (`prices.py`) | 2,007 tickers found, 1,134 not on Yahoo (delisted, acquired, ticker reused) | 1,278 lockup events with IWM aligned, 772 dropped |
| Split | day 0 before 2021-07-01: 546 (in sample) | day 0 from 2021-07-01: 732 (out of sample) |

Day 0 = first trading day strictly after the prospectus date plus the lock-up length. The prospectus date is the
pricing day, the business day before the first Yahoo bar (the 424B4 can be filed 1 to 2 days later, so the filing
date is late). Check: BYND lands on 2019-10-29 and UBER on 2019-11-06, the dates the press reported.

The lock-up parser scores every "N days" number inside lock-up sentences: "180-day lock-up" counts most, the
officers and directors sentence counts extra, and side deals (private placement, cornerstone) lose points, since
Zoom's Salesforce 365 day standoff and Uber's PayPal 270 day lockup are not the market wide expiry. Unreadable
filings are flagged, never guessed from a number.

## The study claims, checked day by day (abnormal return vs IWM, close to close)

| Set | n | CAR day -2 to +2 | Expiry week day 0 to +4 | Day -20 to -1 (front run) | Day -10 to +10 | Volume week 0 to +4 over the 20 day average |
|---|---|---|---|---|---|---|
| All | 1,278 | +0.09% (t 0.14) | +0.77% (t 1.29) | -2.28% (t -2.29) | -1.98% (t -2.14) | median 1.06x, mean 7.7x, 53% above 1x |
| Parsed lockup only | 1,176 | -0.29% (t -0.57) | +0.34% (t 0.69) | -2.56% (t -2.84) | -2.00% (t -2.25) | median 1.07x |
| 2015 to mid 2021 | 546 | -0.63% (t -1.04) | -0.49% (t -1.00) | -2.51% (t -2.64) | -2.91% (t -3.47) | median 1.14x, mean 1.66x, 57% above 1x |
| Mid 2021 to 2025 | 732 | +0.62% (t 0.64) | +1.71% (t 1.76) | -2.11% (t -1.33) | -1.29% (t -0.86) | median 0.99x, mean 12.2x |

- The -1.8% expiry week: not there. The closest is 2015 to mid 2021 at -0.6% with t -1.0, not significant.
  Since mid 2021 the expiry week is positive (+1.7%, t 1.8). Day 0 itself is slightly positive in every set.
- The 40% volume jump: the median expiry week runs 6% above normal volume (14% in the early years, below normal
  since mid 2021). The mean is huge (7.7x) because a few micro caps print 100x volume days. The first pass saw
  the same shape (median +15%, mean +71%) on 55 names. His number is a mean on a different sample and era.
- Where the drop lives: the 20 days before the date. CAR day -20 to -1 is -2.3% with t -2.3 over all 1,278 events
  and -2.5% (t -2.6) in the early years. The market sells ahead of the unlock. That is his front running warning.
- BYND on 2019-10-29: still true. Best window short on BYND made +39.3%, the first pass window +16.6%.

## Short window grid (entry at the open of day E, cover at the close of day X, 4.5 bp fee + 10 bp slippage a side, 10% borrow a year, IWM hedged pays the same per side cost)

Picked in sample on t-stat: **IWM hedged, open day -10 to close day +5, 10% borrow.**

| | Trades | Avg trade | t-stat | Win rate | Profit factor | Total return (10% of equity a trade) |
|---|---|---|---|---|---|---|
| In sample, 2015 to mid 2021 | 546 | +1.85% | 2.65 | 57.1% | 1.37 | +155% |
| Out of sample, mid 2021 to 2025 | 732 | **-2.85%** | -1.94 | 50.7% | 0.77 | -94% |
| Out of sample at 2x costs | 732 | -4.02% | | | | |

Edge bar out of sample: FAIL on every check (avg, t, profit factor, 55% of symbols, 2x costs). Each IPO is one
trade, so "symbols positive" equals the win rate.

Entry timing (hedged, 10% borrow, avg trade):

| Entry day | In sample, exit +5 | Out of sample, exit +5 | Out of sample, exit +10 |
|---|---|---|---|
| -20 | +2.34% | -1.06% | +2.60% (t 1.52) |
| -10 | +1.85% | -2.85% | -0.35% |
| -5 | +1.46% | -3.28% | -0.83% |
| -2 | +0.75% | -2.81% | -0.38% |
| -1 | +0.50% | -2.32% | -0.22% |
| 0 | +0.16% | -3.10% | -1.10% |

In sample, the earlier the entry the better, in a clean staircase. That is the front run again. Out of sample
every cell is negative except entry day -20, and the best of those (unhedged, -20 to +10: +3.0%, t 1.74, PF 1.25,
62% winners) made -0.04% in sample, so it was never pickable and fails t >= 2 anyway.

First pass window rerun (open day -2 to close day +2, unhedged, 10% borrow) on the big universe: -0.56% a trade
over 1,278 (first pass: -0.53% over 55), +0.19% in sample, -1.13% out of sample. Same answer, 23x the sample.

## His filters (on the best window, every input measured at the close before entry, no look ahead)

| Filter | In sample n, avg, t | Out of sample n, avg, t |
|---|---|---|
| His combo: gain over 100% since IPO and locked shares over 20 day volume in the top tercile (the in sample winner) | 75, +6.89%, 3.37 | 123, **-7.56%**, -1.55 |
| Gain since IPO over 300% | 161, +4.73%, 3.27 | 222, -4.27%, -1.30 |
| Gain since IPO 100 to 300% | 54, +7.90%, 3.16 | 48, +9.10%, 1.65 |
| Gain since IPO 0 to 100% | 181, -0.39% | 164, -2.89% |
| Gain since IPO under 0% | 137, -0.71% | 290, -3.56% |
| Locked shares over volume, high tercile | 106, +4.45%, 2.56 | 162, -8.68%, -1.97 |
| Locked shares over volume, mid tercile | 118, +2.18% | 149, +0.62% |
| Market cap, high tercile | 179, +4.49%, 3.27 | 193, -3.82% |
| Market cap, low tercile | 136, +0.53% | 236, -6.31% |
| Run into the lockup up | 223, +2.77%, 2.38 | 257, -3.18% |
| Run into the lockup down | 323, +1.21% | 473, -2.53% |
| ADR only | 102, +3.47%, 2.02 | 66, +11.27%, 3.59 |
| Non ADR | 444, +1.48% | 666, -4.24%, -2.70 |
| Lockup parsed only | 532, +1.80%, 2.56 | 644, -1.91% |
| Lockup guessed (180 d fallback) only | | all 102: -7.85% |

His filters worked, then flipped. The big gain plus big locked supply names were the best shorts in 2015 to 2021
and the worst since: in 2024 and 2025 the $4 micro cap IPOs (ANPA, TWG, PLRZ and friends) tripled straight
through their lockups. Gain 100 to 300% stays positive out of sample (+9.1%) but on 48 trades with t 1.65, under
the bar. ADR only is the one row that would pass every number out of sample, but it ranked 9th in sample so it was
not pickable by the protocol, the names are tiny foreign listings (Cayman and Hong Kong $4 IPOs) that are often
impossible to borrow, and 66 trades is thin. It is a lead for a separate test, not a result. Using the real
lock-up length matters: the guessed 180 day rows lose -7.9% a trade vs -0.2% for the parsed ones.

## The flip side (his SpaceX point): buy the day 0 close when day 0 gapped down and closed above its open

| Hold | All n, avg, t | In sample avg, t | Out of sample avg, t, PF, win rate | Baseline: long every day 0 close |
|---|---|---|---|---|
| +1 | 348, +0.20%, 0.4 | | 212, +0.77%, 0.97 | -0.31% |
| +3 | 348, +0.37%, 0.5 | | 212, +1.59%, 1.39 | -0.50% |
| +5 | 348, +0.67%, 0.7 | 136, -2.09%, -2.23 | 212, +2.43%, 1.56, PF 1.43, 48.6% | +0.38% |
| +10 | 348, -1.86%, -1.7 | | 212, -2.04%, -1.24 | -0.61% |

Loud and clear: in the later years the long flip (+2.4% at 5 days) beats every short window the plan listed
(best -10 to +5 short: -2.85%). But it is NOT proven: t 1.56, 49% winners, and it lost -2.1% in sample. The sign
flipped with the era, same as the short.

## Costs

| Per side cost (fee + slippage) | In sample avg | Out of sample avg |
|---|---|---|
| 0 bp | +2.43% | -2.27% |
| 14.5 bp (used) | +1.85% | -2.85% |
| 50 bp | +0.43% | -4.27% |
| 100 bp | -1.57% | -6.27% |

| Borrow (a year, grid, no real feed) | In sample avg | Out of sample avg |
|---|---|---|
| 0% | +2.45% | -2.25% |
| 10% (used) | +1.85% | -2.85% |
| 30% | +0.66% | -4.04% |
| 50% | -0.53% | -5.23% |
| 100% | -3.51% | -8.22% |

The in sample edge dies at about 40% a year borrow or about 55 bp a side. Out of sample it is dead at zero cost.
Hot IPOs at lockup are exactly the names with 30% to 100%+ borrow, so even the early years are optimistic.

## By year (best window)

2015 -0.4%, 2016 +1.0%, 2017 -0.1%, 2018 +0.8%, 2019 +1.8%, 2020 +2.6%, 2021 +1.5%, 2022 -2.2%, 2023 -4.0%,
2024 -6.9%, 2025 -5.2%, 2026 (74 trades so far) +4.4%. Eleven years, no year with t over 1.4.

## Caveats, all real

- Survivorship. Yahoo drops delisted names, so 1,134 tickers (most of the 772 dropped events) are gone. The
  IPOs that died are the ones missing, and those were likely the best shorts. The early period is understated,
  not overstated. The late period is dominated by 2021 to 2025 Nasdaq Capital Market $4 IPOs that are still listed.
- Yahoo prices are split adjusted. Names that later reverse split show odd levels (BYND at 3,660). Returns are
  ratios and are unaffected.
- One trade per IPO, so the "55% of symbols" bar is the win rate.
- Shares outstanding after the offering is parsed from text and approximate (some filings give one share class).
  Locked shares = outstanding minus offered, so the supply filter inherits that.
- Borrow is a grid, labeled as such. The hedge leg pays the same 14.5 bp a side as the stock, which is harsh for IWM.
- Both EDGAR and Yahoo were reached live on 2026-11-02. No key is used. The SEC User-Agent contact comes from the
  env var `SEC_CONTACT` with a generic fallback string, nothing personal in the code.
- The grid was picked on the in sample t-stat (546 trades), so the in sample numbers carry selection bias. The
  out of sample numbers are the only ones that count, and they are negative.

## Files

- `edgar_ipos.py`: EDGAR index and filing parser, writes `ipo_universe.json` (1.5 MB, committed) and a per filing
  cache in `data_cache/edgar_parsed/` (gitignored, holds the cover text and lock-up sentences for audit).
- `prices.py`: Yahoo downloader, one CSV per ticker in `data_cache/` (357 MB, gitignored), `data_cache/yahoo_missing.txt`.
- `lockup_study.py`: event study, grid, filters, flip, costs, split. Writes `result.json`.
- Run order: `edgar_ipos.py`, then `prices.py`, then `lockup_study.py`, with `/opt/anaconda3/envs/tflow/bin/python`.
