"""
Moon Dev edge finder, package 2, step 1: build the IPO universe from SEC EDGAR 424B4 filings.

What it does (all real, public data, no key):
  1. Pulls the quarterly form index (form.gz) from EDGAR full-index for 2010 to 2025 and keeps every 424B4 row.
     2010 to 2014 are only there so a company that already had a 424B4 before 2015 is not counted as a 2015+ IPO.
  2. Keeps the FIRST 424B4 per CIK with a filing date in 2015 to 2025. A second 424B4 is a follow on, not an IPO.
  3. Drops SPAC style names (Acquisition), trusts, funds and notes before fetching anything.
  4. Streams each remaining filing (only the first document, the prospectus, not the graphics) and parses:
     SIC code (6770 = blank check, dropped), the "no public market" IPO line, the ticker symbol, the IPO price,
     shares offered, shares outstanding after the offering, the lock-up length in days (all numbers seen in
     lock-up sentences, and the most common one), early release language, ADS (ADR) and direct listing flags.
  5. Writes ipo_universe.json next to this file (small, safe to commit) and a per filing cache in data_cache/.

SEC asks for a User-Agent with a contact. It comes from the env var SEC_CONTACT (dotenv on the main repo .env)
and falls back to a generic string. Nothing personal is hard coded. Max 10 requests a second, we use about 6.
If a lock-up cannot be read, the row is kept with lockup_days = null and lockup_guessed = true. Never guessed here.
"""
import gzip
import html
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).parent
CACHE = HERE / "data_cache"
PARSED = CACHE / "edgar_parsed"
load_dotenv("/Users/md/Dropbox/dev/github/moon-dev-trading-bots/.env")
CONTACT = os.getenv("SEC_CONTACT", "research-contact@example.com")
UA = {"User-Agent": f"Moon Dev research {CONTACT}", "Accept-Encoding": "gzip, deflate"}
BASE = "https://www.sec.gov/Archives/"
START, END = "2015-01-01", "2025-12-31"
REQ_PER_SEC = 6.0
_lock = threading.Lock()
_last = [0.0]
SKIP_NAME = re.compile(r"acquisition|\btrust\b|\bfund\b|\betf\b|\betn\b|\bnotes?\b|\bcapital corp\b|\bholdings? trust\b|\bincome\b|\breit\b", re.I)


def throttle():
    """Moon Dev: shared token so the whole process stays under the SEC rate limit."""
    with _lock:
        wait = _last[0] + 1.0 / REQ_PER_SEC - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def get(url, stream=False):
    throttle()
    r = requests.get(url, headers=UA, timeout=60, stream=stream)
    if r.status_code == 429 or r.status_code == 403:
        print(f"Moon Dev: EDGAR said {r.status_code} on {url}, sleeping 20s and retrying once")
        time.sleep(20)
        throttle()
        r = requests.get(url, headers=UA, timeout=60, stream=stream)
    r.raise_for_status()
    return r


def load_index():
    """Moon Dev: every 424B4 row from the quarterly form indexes, cached to one file."""
    f = CACHE / "424b4_index.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"])
    rows = []
    for year in range(2010, 2026):
        for q in range(1, 5):
            url = f"{BASE}edgar/full-index/{year}/QTR{q}/form.gz"
            try:
                r = get(url)
            except requests.HTTPError as e:
                print(f"Moon Dev: no index for {year} Q{q} ({e}), skipped")
                continue
            text = gzip.GzipFile(fileobj=io.BytesIO(r.content)).read().decode("latin1")
            n = 0
            for line in text.splitlines():
                if line.startswith("424B4 "):
                    parts = re.split(r"\s{2,}", line.strip())
                    if len(parts) >= 5:
                        rows.append(dict(form=parts[0], name=parts[1], cik=int(parts[2]), date=parts[3], path=parts[4]))
                        n += 1
            print(f"Moon Dev: {year} Q{q}: {n} 424B4 filings")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_csv(f, index=False)
    return df


def candidates(idx):
    first = idx.sort_values("date").groupby("cik").head(1)
    inwin = first[(first["date"] >= START) & (first["date"] <= END)].copy()
    print(f"Moon Dev: {len(idx)} 424B4 rows, {len(first)} first filings per CIK, {len(inwin)} in 2015 to 2025")
    keep = inwin[~inwin["name"].str.contains(SKIP_NAME)]
    print(f"Moon Dev: {len(keep)} after dropping SPAC, trust, fund and note names")
    return keep.reset_index(drop=True)


def fetch_text(path, max_bytes=12_000_000):
    """Moon Dev: stream the full submission and stop after the first document (the prospectus)."""
    r = get(BASE + path, stream=True)
    buf = bytearray()
    for chunk in r.iter_content(1 << 17):
        buf += chunk
        if b"</DOCUMENT>" in buf or len(buf) > max_bytes:
            break
    r.close()
    raw = bytes(buf).decode("utf8", "ignore")
    head = raw[:6000]
    body = raw.split("</DOCUMENT>")[0]
    text = re.sub(r"<[^>]+>", " ", body)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return head, text


NUM = r"([\d,]{5,})"
WORDS = {"thirty": 30, "forty-five": 45, "forty five": 45, "sixty": 60, "ninety": 90, "one hundred twenty": 120,
         "one hundred eighty": 180, "one hundred and eighty": 180, "three hundred sixty-five": 365, "365": 365}


def parse(head, text):
    out = {}
    m = re.search(r"STANDARD INDUSTRIAL CLASSIFICATION:.*?\[(\d{4})\]", head)
    out["sic"] = int(m.group(1)) if m else None
    cover = text[:40000]
    out["is_ipo"] = bool(re.search(r"no (established )?public (trading )?market|initial public offering of|this is our initial public offering|our initial public offering", cover, re.I))
    out["direct_listing"] = bool(re.search(r"direct listing", cover, re.I))
    out["is_adr"] = bool(re.search(r"American Depositary Shares|ADSs", cover))
    m = re.search(r"under the (?:trading )?symbol\s*[\"“”']?\s*([A-Z]{1,5})(?:\.[A-Z])?\b", cover)
    out["symbol"] = m.group(1) if m else None
    m = re.search(r"under the symbol\s*[\"“”']?\s*([A-Z]{1,5})", text[40000:200000]) if not out["symbol"] else None
    if m:
        out["symbol"] = m.group(1)
    m = re.search(r"(?:Nasdaq|New York Stock Exchange|NYSE|NYSE American|NYSE MKT)[\w ]{0,40}", cover)
    out["exchange"] = m.group(0).strip() if m else None
    m = (re.search(r"(?:initial public )?offering price (?:is|of|will be|was) \$\s?(\d+(?:\.\d+)?)", cover, re.I)
         or re.search(r"(?:initial public offering|public offering) price[^$]{0,80}?\$\s?(\d+(?:\.\d+)?)", cover, re.I)
         or re.search(r"\$\s?(\d+(?:\.\d+)?) per (?:share|ADS|ordinary share|unit|common share)", cover, re.I))
    out["ipo_price"] = float(m.group(1)) if m else None
    out["cover_text"] = cover[:20000]
    out["lockup_sentences"] = [s[:400] for s in re.split(r"(?<=[.;])\s+", text) if re.search(r"lock-?up", s, re.I) and re.search(r"\d{2,3}[\s-]*days?", s)][:12]
    m = re.search(r"\b(\d{1,3}(?:,\d{3})+)\s+(?:Shares|American Depositary Shares|Ordinary Shares|Units|Class A)", cover[:8000])
    out["shares_offered"] = int(m.group(1).replace(",", "")) if m else None
    m = re.search(r"(?:to be )?outstanding (?:immediately )?after (?:this|the) offering[^0-9$]{0,250}?(\d{1,3}(?:,\d{3}){1,4})\s*(?:shares|ordinary|ADSs|$)", text, re.I)
    if not m:
        m = re.search(r"(\d{1,3}(?:,\d{3}){1,4}) (?:shares of (?:our )?(?:Class A )?common stock|ordinary shares)[^.]{0,80}outstanding (?:immediately )?after (?:this|the) offering", text, re.I)
    out["shares_outstanding_after"] = int(m.group(1).replace(",", "")) if m else None
    # Moon Dev: lock-up days. Look only inside sentences that mention lock-up or lockup.
    days = []
    for sent in re.split(r"(?<=[.;])\s+", text):
        if not re.search(r"lock-?up|market stand-?off|restricted period", sent, re.I):
            continue
        for mm in re.finditer(r"(\d{2,3})(?:st|nd|rd|th)?[\s-]*(?:calendar |trading )?days?", sent):
            d = int(mm.group(1))
            if 25 <= d <= 400:
                days.append(d)
        low = sent.lower()
        for w, d in WORDS.items():
            if re.search(rf"\b{w}\s*\(?\s*\d*\s*\)?[\s-]*days?", low):
                days.append(d)
    out["lockup_days_seen"] = sorted(set(days))
    if days:
        # Moon Dev: score each number by how tightly it sits next to the words lock-up.
        # "180-day lock-up" counts 3, "lock-up ... 180 days" counts 2, any mention in a lock-up sentence counts 1.
        score = {}
        for d in set(days):
            score[d] = (3 * len(re.findall(rf"\b{d}[\s-]*day lock-?up", text, re.I))
                        + 2 * len(re.findall(rf"lock-?up[^.]{{0,200}}?\b{d}(?:st|nd|rd|th)?[\s-]*(?:calendar )?days?\b", text, re.I))
                        + 5 * len(re.findall(rf"(?:officers|directors|substantially all of our|restricted period)[^.]{{0,400}}?\b{d}(?:st|nd|rd|th)?[\s-]*(?:calendar )?days? (?:after|from|following)", text, re.I))
                        + days.count(d))
        # Moon Dev: a side deal (private placement, cornerstone, concurrent sale) often has its own longer lockup.
        # Those sentences do not set the market wide expiry, so they lose points.
        for d in score:
            side = [s_ for s_ in re.split(r"(?<=[.;])\s+", text)
                    if re.search(rf"\b{d}(?:st|nd|rd|th)?[\s-]*days?", s_) and re.search(r"lock-?up", s_, re.I)
                    and re.search(r"private placement|concurrent|not be registered|cornerstone|anchor investor", s_, re.I)]
            score[d] -= 4 * len(side)
        best = max(score.values())
        out["lockup_days"] = int(max(d for d in score if score[d] == best))
        out["lockup_scores"] = {str(k): v for k, v in score.items()}
        out["lockup_guessed"] = False
    else:
        out["lockup_days"] = None
        out["lockup_guessed"] = True
    out["staged_release"] = len(set(d for d in days if d != 30)) > 1
    out["early_release"] = bool(re.search(r"early (?:lock-?up )?release|released? (?:from|early)[^.]{0,80}lock-?up|lock-?up[^.]{0,120}will (?:be )?(?:automatically )?(?:terminate|end|expire) (?:early|prior)", text, re.I))
    out["no_lockup"] = bool(re.search(r"(?:no|not entered into any) lock-?up agreements?", cover, re.I))
    return out


def process(row):
    f = PARSED / (row["path"].split("/")[-1].replace(".txt", ".json"))
    if f.exists():
        return json.loads(f.read_text())
    head, text = fetch_text(row["path"])
    out = parse(head, text)
    out.update(cik=int(row["cik"]), name=row["name"], filing_date=str(row["date"].date()), path=row["path"])
    f.write_text(json.dumps(out))
    return out


if __name__ == "__main__":
    print("Moon Dev: building the IPO universe from EDGAR 424B4 filings")
    CACHE.mkdir(exist_ok=True)
    PARSED.mkdir(exist_ok=True)
    idx = load_index()
    cand = candidates(idx)
    if "--index-only" in sys.argv:
        sys.exit(0)
    t0 = time.time()
    done = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(process, r): r for _, r in cand.iterrows()}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                done.append(fut.result())
            except Exception as e:
                r = futs[fut]
                print(f"Moon Dev: FAILED {r['name']} {r['path']}: {e}")
                done.append(dict(cik=int(r["cik"]), name=r["name"], filing_date=str(r["date"].date()), path=r["path"], fetch_failed=str(e)))
            if i % 100 == 0:
                print(f"Moon Dev: {i}/{len(cand)} filings parsed, {time.time() - t0:.0f}s")
    df = pd.DataFrame(done)
    # Moon Dev: current tickers by CIK from the SEC (one request), used when the filing symbol gives Yahoo nothing
    tk = get("https://www.sec.gov/files/company_tickers_exchange.json").json()
    tkdf = pd.DataFrame(tk["data"], columns=tk["fields"]).drop_duplicates("cik")
    df = df.merge(tkdf[["cik", "ticker", "exchange"]].rename(columns={"ticker": "sec_ticker", "exchange": "sec_exchange"}), on="cik", how="left")
    # Moon Dev: the committed table is small. Cover text and lock-up sentences stay in the gitignored cache.
    df.drop(columns=[c for c in ["cover_text", "lockup_sentences"] if c in df]).to_json(HERE / "ipo_universe.json", orient="records", indent=0)
    n = len(df)
    print(f"Moon Dev: parsed {n} filings. is_ipo {int(df['is_ipo'].sum())}, SIC 6770 {int((df['sic'] == 6770).sum())}, "
          f"direct listing {int(df['direct_listing'].sum())}, ADR {int(df['is_adr'].sum())}, "
          f"lockup parsed {int((~df['lockup_guessed'].fillna(True)).sum())}, symbol found {int(df['symbol'].notna().sum())}")
    print(df["lockup_days"].value_counts().head(10))
    print(f"Moon Dev: saved {HERE / 'ipo_universe.json'}")
