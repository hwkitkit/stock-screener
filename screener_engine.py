#!/usr/bin/env python3
"""
Quality / Value / Moat screener engine
=======================================
Mirrors the methodology of the interactive screener, but pulls LIVE fundamentals
and ranks across the whole S&P 500 / NASDAQ-100 universe — so a stock's rank is
its real position (e.g. #50 of 500), not its position within a hand-picked list.

Data source: yfinance (free, no API key). It wraps Yahoo Finance. It can be a bit
flaky / rate-limited; for heavier use, swap in Financial Modeling Prep (notes below).

USAGE
-----
    pip install yfinance pandas numpy lxml requests

    # Rank the whole S&P 500 and save to CSV:
    python screener_engine.py rank --universe sp500 --out ranked.csv

    # Check one ticker and see where it lands in the universe:
    python screener_engine.py check NVDA --universe sp500

    # See what's trending on StockTwits (momentum feed, separate from quality):
    python screener_engine.py trending

NOTE: ROIC is not exposed directly by Yahoo, so it is computed from the financial
statements when available, with a Return-on-Assets proxy as a flagged fallback.
Treat all outputs as a relative screen, not precise valuations or advice.
"""

import sys
import argparse
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ENGINE_VERSION = "1.3"   # matches the artifact's methodology version

def run_stamp():
    """Timestamp for the moment of THIS pull (the 'button press')."""
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

try:
    import yfinance as yf
except ImportError:
    sys.exit("Install dependencies first:  pip install yfinance pandas numpy lxml requests")

# ----------------------------------------------------------------------------
# 1. METHODOLOGY  (same fixed-range normalization as the interactive tool)
# ----------------------------------------------------------------------------
# Each metric: weight, and the (lo, hi) range it is normalized against.
# For leverage, lo > hi because lower net-debt/EBITDA is better (inverted scale).
METRICS = {
    "roic":        {"w": 25, "lo": 0,   "hi": 50},
    "fcf_margin":  {"w": 20, "lo": -20, "hi": 50},
    "gross_margin":{"w": 12, "lo": 0,   "hi": 100},
    "rev_growth":  {"w": 13, "lo": -10, "hi": 40},
    "net_debt_ebitda": {"w": 10, "lo": 3, "hi": -1},  # inverted
    "moat_trend":  {"w": 20, "lo": -2,  "hi": 2},
}

# Moat trend is a JUDGMENT — it cannot be pulled from data. Set your own views
# here (ticker -> -2 eroding ... +2 widening). Anything not listed defaults to 0.
MOAT_TREND = {
    "CDNS": 2, "SNPS": 2, "ASML": 2,
    "NVDA": 1, "MA": 1, "LLY": 1, "KLAC": 1, "MSFT": 1, "FICO": 1, "TSM": 1,
    "ADBE": -1,
}

def clamp01(x):
    return max(0.0, min(1.0, x))

def normalize(val, lo, hi):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return clamp01((val - lo) / (hi - lo)) * 100.0

# ----------------------------------------------------------------------------
# 2. DATA PULL  (one ticker -> metric dict)
# ----------------------------------------------------------------------------
def _safe(d, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            return v
    return None

def compute_roic(t, info):
    """Try a real ROIC from statements; fall back to ROA proxy (flagged)."""
    try:
        fin = t.financials            # income statement (cols = periods)
        bs = t.balance_sheet
        ebit = fin.loc["EBIT"].iloc[0] if "EBIT" in fin.index else None
        if ebit is None and "Operating Income" in fin.index:
            ebit = fin.loc["Operating Income"].iloc[0]
        tax_rate = 0.21
        debt = None
        for k in ["Total Debt", "Long Term Debt"]:
            if k in bs.index:
                debt = bs.loc[k].iloc[0]; break
        equity = None
        for k in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]:
            if k in bs.index:
                equity = bs.loc[k].iloc[0]; break
        cash = None
        for k in ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]:
            if k in bs.index:
                cash = bs.loc[k].iloc[0]; break
        if ebit and equity:
            invested = (debt or 0) + equity - (cash or 0)
            if invested and invested > 0:
                return round(ebit * (1 - tax_rate) / invested * 100, 1), False
    except Exception:
        pass
    # fallback: Return on Assets (flagged as proxy)
    roa = _safe(info, "returnOnAssets")
    if roa is not None:
        return round(roa * 100, 1), True
    roe = _safe(info, "returnOnEquity")
    return (round(roe * 100, 1), True) if roe is not None else (None, True)

def fetch_metrics(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return None
    if not info or _safe(info, "totalRevenue") is None:
        return None

    rev = _safe(info, "totalRevenue") or 0
    fcf = _safe(info, "freeCashflow")
    fcf_margin = round(fcf / rev * 100, 1) if (fcf and rev) else None
    gross = _safe(info, "grossMargins")
    gross_margin = round(gross * 100, 1) if gross is not None else None
    growth = _safe(info, "revenueGrowth")
    rev_growth = round(growth * 100, 1) if growth is not None else None

    debt = _safe(info, "totalDebt") or 0
    cash = _safe(info, "totalCash") or 0
    ebitda = _safe(info, "ebitda")
    net_debt_ebitda = round((debt - cash) / ebitda, 2) if (ebitda and ebitda > 0) else None

    roic, roic_proxy = compute_roic(t, info)

    fwd_pe = _safe(info, "forwardPE", "trailingPE")
    ps = _safe(info, "priceToSalesTrailing12Months")
    eps_growth = _safe(info, "earningsGrowth")
    eps_growth = round(eps_growth * 100, 1) if eps_growth is not None else None

    return {
        "ticker": ticker,
        "name": _safe(info, "shortName", "longName") or ticker,
        "roic": roic, "roic_is_proxy": roic_proxy,
        "fcf_margin": fcf_margin,
        "gross_margin": gross_margin,
        "rev_growth": rev_growth,
        "net_debt_ebitda": net_debt_ebitda,
        "fwd_pe": round(fwd_pe, 1) if fwd_pe else None,
        "ps": round(ps, 1) if ps else None,
        "eps_growth": eps_growth,
        "moat_trend": MOAT_TREND.get(ticker, 0),
    }

# ----------------------------------------------------------------------------
# 3. SCORING
# ----------------------------------------------------------------------------
def composite_score(row):
    total_w, acc = 0, 0.0
    for key, cfg in METRICS.items():
        n = normalize(row.get(key), cfg["lo"], cfg["hi"])
        if n is None:
            continue          # skip missing metric, renormalize on the rest
        acc += n * cfg["w"]
        total_w += cfg["w"]
    return round(acc / total_w, 1) if total_w else None

def value_score(row):
    """Lower = cheaper. n/m for loss-makers (no positive earnings growth/PE)."""
    pe, ps, g = row.get("fwd_pe"), row.get("ps"), row.get("eps_growth")
    if not pe or pe <= 0 or not g or g <= 0 or not ps:
        return None  # not meaningful
    peg = pe / g
    pn = clamp01((peg - 0.5) / (4.0 - 0.5))
    sn = clamp01((ps - 4) / (18 - 4))
    return round(0.6 * pn + 0.4 * sn, 3)

# ----------------------------------------------------------------------------
# 4. UNIVERSES
# ----------------------------------------------------------------------------
def _read_wiki_tables(url):
    """Fetch a Wikipedia page with a browser User-Agent (Wikipedia 403s the
    default urllib agent used by pd.read_html) and parse its HTML tables."""
    import io
    import requests
    r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))

def get_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = _read_wiki_tables(url)[0]
    return [s.replace(".", "-") for s in df["Symbol"].tolist()]

def get_nasdaq100():
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    tables = _read_wiki_tables(url)
    for tb in tables:
        for col in ("Ticker", "Symbol"):
            if col in tb.columns:
                return [s.replace(".", "-") for s in tb[col].tolist()]
    return []

# The 25 hand-picked companies captured in the frozen HTML snapshot
# (stock-quality-screener.html, "Snapshot v1.6"). Lets you re-pull live numbers
# for exactly that set via:  --universe snapshot25
SNAPSHOT25 = [
    "NVDA", "MA", "V", "AAPL", "LLY", "ADBE", "BKNG", "META", "CDNS", "GOOGL",
    "KLAC", "MSFT", "SNPS", "MCO", "INTU", "MNST", "ADP", "SPGI", "TXN", "KO",
    "ASML", "FICO", "VEEV", "CPRT", "TSM",
]

def build_universe(name):
    if name == "sp500":   return sorted(set(get_sp500()))
    if name == "nasdaq100": return sorted(set(get_nasdaq100()))
    if name == "both":    return sorted(set(get_sp500()) | set(get_nasdaq100()))
    if name == "snapshot25": return list(SNAPSHOT25)
    # otherwise treat as comma-separated custom list
    return [s.strip().upper() for s in name.split(",") if s.strip()]

# ----------------------------------------------------------------------------
# 5. RANK THE UNIVERSE
# ----------------------------------------------------------------------------
def rank_universe(tickers, pause=0.4):
    rows = []
    for i, tk in enumerate(tickers, 1):
        m = fetch_metrics(tk)
        if m and composite_score(m) is not None:
            m["composite"] = composite_score(m)
            m["value"] = value_score(m)
            rows.append(m)
        if i % 25 == 0:
            print(f"  ...{i}/{len(tickers)} pulled", file=sys.stderr)
        time.sleep(pause)  # be gentle with Yahoo
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values("composite", ascending=False).reset_index(drop=True)
    df["q_rank"] = df.index + 1
    # value rank: meaningful ones ranked low-to-high, n/m sent to the back
    df["value_rank"] = df["value"].rank(method="min", na_option="bottom")
    return df

# ----------------------------------------------------------------------------
# 6. CHECK A SINGLE TICKER vs the universe
# ----------------------------------------------------------------------------
def check_ticker(ticker, universe_name):
    ticker = ticker.upper()
    print(f"Pulling {ticker} ...", file=sys.stderr)
    m = fetch_metrics(ticker)
    if not m:
        sys.exit(f"Could not pull data for {ticker}")
    m["composite"] = composite_score(m)
    m["value"] = value_score(m)

    print(f"\n=== {ticker} — {m['name']} ===")
    print(f"  Live pull: {run_stamp()}  |  engine v{ENGINE_VERSION}")
    proxy = "  (ROA proxy — Yahoo lacked statements)" if m.get("roic_is_proxy") else ""
    print(f"  ROIC............. {m['roic']}%{proxy}")
    print(f"  FCF margin....... {m['fcf_margin']}%")
    print(f"  Gross margin..... {m['gross_margin']}%")
    print(f"  Revenue growth... {m['rev_growth']}%")
    print(f"  Net debt/EBITDA.. {m['net_debt_ebitda']}")
    print(f"  Fwd P/E.......... {m['fwd_pe']}   P/S {m['ps']}   EPS growth {m['eps_growth']}%")
    print(f"  Moat trend....... {m['moat_trend']:+d} (your setting; edit MOAT_TREND)")
    print(f"  ---------------------------------")
    print(f"  COMPOSITE SCORE.. {m['composite']}")
    print(f"  VALUE SCORE...... {m['value'] if m['value'] is not None else 'n/m'}")

    print(f"\nRanking against {universe_name} (this pulls the whole universe; takes a few min)...",
          file=sys.stderr)
    uni = build_universe(universe_name)
    if ticker not in uni:
        uni.append(ticker)
    df = rank_universe(uni)
    if df.empty:
        sys.exit("Universe pull failed.")
    row = df[df["ticker"] == ticker]
    if row.empty:
        print(f"\n{ticker} did not score (missing data).")
        return
    qr = int(row["q_rank"].iloc[0]); n = len(df)
    pct = round((1 - qr / n) * 100)
    print(f"\n>>> {ticker} ranks #{qr} of {n} on QUALITY ({pct}th percentile)")
    vr = row["value_rank"].iloc[0]
    if not np.isnan(vr) and m["value"] is not None:
        print(f">>> {ticker} ranks #{int(vr)} of {n} on VALUE (1 = cheapest vs. growth)")
    else:
        print(f">>> {ticker} VALUE is n/m (loss-making or no positive growth)")
    # show its neighbours
    lo, hi = max(0, qr - 4), min(n, qr + 3)
    print("\nNeighbourhood:")
    print(df.iloc[lo:hi][["q_rank", "ticker", "composite", "value", "roic", "fcf_margin"]]
          .to_string(index=False))

# ----------------------------------------------------------------------------
# 7. STOCKTWITS TRENDING  (momentum feed — keep separate from quality!)
# ----------------------------------------------------------------------------
def trending():
    import requests
    url = "https://api.stocktwits.com/api/2/trending/symbols.json"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        syms = [s["symbol"] for s in data.get("symbols", [])]
        print("StockTwits trending tickers (momentum, NOT a quality signal):")
        print("  " + ", ".join(syms) if syms else "  (none returned)")
        print("\nTip: feed these into  python screener_engine.py check <TICKER>")
        print("to see whether the crowd's hot name actually holds up on quality.")
    except Exception as e:
        print(f"StockTwits request failed ({e}).")
        print("X/Twitter's own API is paid+gated; StockTwits is the pragmatic free-ish proxy,")
        print("but they tighten access periodically. A paid social-sentiment API is the robust route.")

# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("rank"); r.add_argument("--universe", default="sp500"); r.add_argument("--out", default="ranked.csv")
    c = sub.add_parser("check"); c.add_argument("ticker"); c.add_argument("--universe", default="sp500")
    sub.add_parser("trending")
    args = ap.parse_args()

    if args.cmd == "rank":
        uni = build_universe(args.universe)
        stamp = run_stamp()
        print(f"Engine v{ENGINE_VERSION} | pull started {stamp}", file=sys.stderr)
        print(f"Pulling {len(uni)} tickers from '{args.universe}' ...", file=sys.stderr)
        df = rank_universe(uni)
        df["pulled_at"] = stamp
        df["engine_version"] = ENGINE_VERSION
        cols = ["q_rank","ticker","name","composite","value","value_rank",
                "roic","fcf_margin","gross_margin","rev_growth","net_debt_ebitda",
                "fwd_pe","ps","eps_growth","moat_trend","pulled_at","engine_version"]
        df[cols].to_csv(args.out, index=False)
        print(f"\n=== LIVE PULL — {stamp} (engine v{ENGINE_VERSION}) ===")
        print(f"Saved {len(df)} ranked companies to {args.out}")
        print(df[["q_rank","ticker","composite","value"]].head(25).to_string(index=False))
    elif args.cmd == "check":
        check_ticker(args.ticker, args.universe)
    elif args.cmd == "trending":
        trending()
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
