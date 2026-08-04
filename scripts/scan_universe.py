#!/usr/bin/env python3
"""
scan_universe.py — Muad'Dib pre-market universe screener.

Scans data/universe.txt (~600 liquid US names) for playbook setups so the
morning watchlist draws from the whole market, not just news mentions.

Usage:
    python3 scripts/scan_universe.py                # top 20, human-readable
    python3 scripts/scan_universe.py --json         # machine-readable
    python3 scripts/scan_universe.py --top 30
    python3 scripts/scan_universe.py --limit 100    # scan only first N (testing)

Per candidate: setup tag (PULLBACK / BREAKOUT / DIP), scan score 0-5,
last, ATR14, RVOL, 1M RS vs SPY, distance to pivot. Liquidity floor:
price > $5 and 50d avg dollar volume > $50M.

Scan score (0-5): uptrend stack, RS leader (1M RS > 0), volume (RVOL >= 1.2),
clean level (near EMA20 or within 3% of 63d high), extra point for
RVOL >= 2 or RS > +5%. News catalyst is judged later by the analyst —
a scanner hit with a same-day catalyst is watchlist material.
"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pickle, datetime
import numpy as np, pandas as pd, yfinance as yf

CACHE = "/tmp/mb_scan_cache.pkl"

def _load_cache():
    try:
        st = pickle.load(open(CACHE, "rb"))
        if st.get("date") == datetime.date.today().isoformat():
            return st["frames"]
    except Exception:
        pass
    return {}

def _save_cache(frames):
    try:
        pickle.dump({"date": datetime.date.today().isoformat(), "frames": frames}, open(CACHE, "wb"))
    except Exception:
        pass
from strategy_engine import wilder_atr, rsi

CHUNK = 100
CHUNK_TIMEOUT = 75  # sec; Yahoo throttling -> skip chunk, keep going

def load_universe(limit=None):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "universe.txt")
    ticks = []
    for line in open(p):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        ticks += line.split()
    ticks = list(dict.fromkeys(ticks))
    return ticks[:limit] if limit else ticks

def fetch_chunked(tickers, period="6mo"):
    frames = _load_cache()          # resume same-day partial scans
    tickers = [t for t in tickers if t not in frames]
    if not tickers:
        return frames
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        try:
            data = yf.download(chunk, period=period, interval="1d",
                               group_by="ticker", auto_adjust=False,
                               progress=False, threads=8, timeout=15)
        except Exception as e:
            print(f"  chunk {i//CHUNK+1} skipped ({type(e).__name__})", file=sys.stderr, flush=True)
            continue
        for t in chunk:
            try:
                df = data[t].dropna() if len(chunk) > 1 else data.dropna()
                if len(df) >= 60:
                    frames[t] = df
            except Exception:
                pass
        _save_cache(frames)
        print(f"  chunk {i//CHUNK+1} done: {len(frames)} frames cached", file=sys.stderr, flush=True)
    return frames

def evaluate(t, df, spy_ret_1m):
    close = df["Close"]
    last = float(close.iloc[-1])
    if last < 5:
        return None
    vol = df["Volume"]
    avg_vol50 = float(vol.rolling(50).mean().iloc[-1])
    if not avg_vol50 or last * avg_vol50 < 50e6:   # liquidity floor
        return None
    atr = wilder_atr(df)
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    r2 = rsi(close, 2)
    rvol = float(vol.iloc[-1] / avg_vol50)
    rs_1m = None
    if len(close) >= 22 and spy_ret_1m is not None:
        rs_1m = round(((last / float(close.iloc[-22]) - 1) - spy_ret_1m) * 100, 2)
    hi63 = float(close.rolling(63).max().iloc[-1])
    dist_hi = (hi63 - last) / last
    near_ema20 = abs(last - ema20) / last < 0.02
    uptrend = last > sma50 and (sma200 is None or sma50 > sma200)

    setup = None
    if uptrend and near_ema20 and r2 < 30:
        setup = "PULLBACK"
    elif uptrend and dist_hi < 0.03 and rvol >= 1.2:
        setup = "BREAKOUT"
    elif r2 < 10 and sma200 and last > sma200:
        setup = "DIP"
    if setup is None:
        return None

    score = 0
    score += 1 if uptrend else 0
    score += 1 if (rs_1m is not None and rs_1m > 0) else 0
    score += 1 if rvol >= 1.2 else 0
    score += 1 if (near_ema20 or dist_hi < 0.03) else 0
    score += 1 if (rvol >= 2 or (rs_1m is not None and rs_1m > 5)) else 0

    return {
        "ticker": t, "setup": setup, "scan_score": score,
        "last": round(last, 2), "atr14": round(atr, 2),
        "atr_pct": round(atr / last * 100, 2),
        "rvol": round(rvol, 2), "rsi2": round(r2, 1),
        "rs_1m_vs_spy_pct": rs_1m,
        "pivot_63d_high": round(hi63, 2),
        "dist_to_pivot_pct": round(dist_hi * 100, 2),
        "ema20": round(ema20, 2), "sma50": round(sma50, 2),
        "dollar_vol_50d_m": round(last * avg_vol50 / 1e6),
    }

def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    top = int(args[args.index("--top") + 1]) if "--top" in args else 20
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None

    universe = load_universe(limit)
    frames = fetch_chunked(list(dict.fromkeys(universe + ["SPY"])))
    spy = frames.pop("SPY", None)
    spy_ret_1m = None
    if spy is not None and len(spy) >= 22:
        spy_ret_1m = float(spy["Close"].iloc[-1]) / float(spy["Close"].iloc[-22]) - 1

    hits = []
    for t, df in frames.items():
        try:
            card = evaluate(t, df, spy_ret_1m)
            if card:
                hits.append(card)
        except Exception:
            pass
    hits.sort(key=lambda c: (c["scan_score"], c["rvol"] or 0), reverse=True)
    hits = hits[:top]

    if as_json:
        print(json.dumps({"scanned": len(frames), "candidates": hits}, indent=1))
        return
    print(f"═══ UNIVERSE SCAN — {len(frames)} names analyzed, top {len(hits)} candidates ═══")
    print(f"{'TICKER':7}{'SETUP':10}{'SCORE':6}{'LAST':>9}{'ATR%':>6}{'RVOL':>6}{'RS1M%':>7}{'→PIVOT%':>9}")
    for c in hits:
        print(f"{c['ticker']:7}{c['setup']:10}{c['scan_score']}/5  {c['last']:>9}{c['atr_pct']:>6}"
              f"{c['rvol']:>6}{str(c['rs_1m_vs_spy_pct']):>7}{c['dist_to_pivot_pct']:>9}")

if __name__ == "__main__":
    main()
