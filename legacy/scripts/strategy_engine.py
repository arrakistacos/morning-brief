#!/usr/bin/env python3
"""
strategy_engine.py — Muad'Dib regime check + ATR risk engine + setup flags.

One yfinance batch call replaces the ad-hoc per-ticker price snippets in all
four scheduled routines. Cheap, deterministic, and every level is ATR-anchored.

Usage:
    python3 scripts/strategy_engine.py --regime            # regime only
    python3 scripts/strategy_engine.py NVDA MSFT XOM       # regime + ticker cards
    python3 scripts/strategy_engine.py --json NVDA MSFT    # machine-readable

Per ticker: last price, prev close, %chg, ATR14 (Wilder), EMA20/SMA50/SMA200,
RSI(2), RVOL vs 50d avg, 1M relative strength vs SPY, and ATR-based levels:
    swing stop  = entry − 1.5×ATR14     (playbook S1/S2/S3)
    swing target= entry + 3.0×ATR14     (true 1:2 R:R)
    dip stop    = entry − 2.0×ATR14     (playbook S5 disaster stop)
"""

import sys
import json
import math

import numpy as np
import pandas as pd
import yfinance as yf


def wilder_atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    return float(atr.iloc[-1])


def rsi(close: pd.Series, n: int = 2) -> float:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    val = 100 - 100 / (1 + rs)
    return float(val.iloc[-1]) if not math.isnan(float(val.iloc[-1])) else 100.0


def fetch(tickers, period="1y"):
    data = yf.download(tickers, period=period, interval="1d",
                       group_by="ticker", auto_adjust=False, progress=False,
                       threads=True)
    out = {}
    for t in tickers:
        try:
            df = data[t].dropna() if len(tickers) > 1 else data.dropna()
            if len(df) >= 30:
                out[t] = df
        except Exception:
            pass
    return out


def regime_check():
    frames = fetch(["SPY", "^VIX"], period="1y")
    spy = frames.get("SPY")
    vix = frames.get("^VIX")
    if spy is None:
        return {"regime": "UNKNOWN", "reason": "SPY fetch failed"}
    close = float(spy["Close"].iloc[-1])
    sma50 = float(spy["Close"].rolling(50).mean().iloc[-1])
    sma200 = float(spy["Close"].rolling(200).mean().iloc[-1])
    vix_last = float(vix["Close"].iloc[-1]) if vix is not None else None

    if close > sma50 and (vix_last is None or vix_last < 20):
        regime = "RISK_ON"
    elif close < sma200 or (vix_last is not None and vix_last > 25):
        regime = "RISK_OFF"
    else:
        regime = "CAUTION"
    return {
        "regime": regime,
        "spy": round(close, 2),
        "spy_sma50": round(sma50, 2),
        "spy_sma200": round(sma200, 2),
        "vix": round(vix_last, 2) if vix_last is not None else None,
        "rules": {
            "RISK_ON": "full size (1% risk/trade), all setups live",
            "CAUTION": "half size, 5/5-score setups only",
            "RISK_OFF": "no new swing longs; ORB-5 / DIP half size only",
        }[regime],
    }


def ticker_card(t, df, spy_df):
    close = df["Close"]
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    atr = wilder_atr(df)
    ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1])
    sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    vol = df["Volume"]
    avg_vol50 = float(vol.rolling(50).mean().iloc[-1])
    rvol = float(vol.iloc[-1] / avg_vol50) if avg_vol50 else None
    rs_1m = None
    if spy_df is not None and len(close) >= 22 and len(spy_df) >= 22:
        stk = last / float(close.iloc[-22]) - 1
        spx = float(spy_df["Close"].iloc[-1]) / float(spy_df["Close"].iloc[-22]) - 1
        rs_1m = round((stk - spx) * 100, 2)

    card = {
        "ticker": t,
        "last": round(last, 2),
        "prev_close": round(prev, 2),
        "chg_pct": round((last / prev - 1) * 100, 2),
        "atr14": round(atr, 2),
        "atr_pct": round(atr / last * 100, 2),
        "ema20": round(ema20, 2),
        "sma50": round(sma50, 2),
        "sma200": round(sma200, 2) if sma200 else None,
        "rsi2": round(rsi(close, 2), 1),
        "rvol": round(rvol, 2) if rvol else None,
        "rs_1m_vs_spy_pct": rs_1m,
        "swing_stop_1_5atr": round(last - 1.5 * atr, 2),
        "swing_target_3atr": round(last + 3.0 * atr, 2),
        "dip_stop_2atr": round(last - 2.0 * atr, 2),
        "risk_reward": "1:2.0",
        "flags": {
            "uptrend_stack": bool(last > sma50 and (sma200 is None or sma50 > sma200)),
            "above_ema20": bool(last > ema20),
            "pullback_zone": bool(abs(last - ema20) / last < 0.02 and last > sma50),
            "dip_signal": bool(rsi(close, 2) < 10 and sma200 and last > sma200),
            "high_rvol": bool(rvol and rvol >= 2),
        },
    }
    return card


def main():
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    regime_only = "--regime" in args
    tickers = [a.upper() for a in args if not a.startswith("--")]

    reg = regime_check()
    result = {"regime_check": reg, "tickers": []}

    if not regime_only and tickers:
        frames = fetch(list(dict.fromkeys(tickers + ["SPY"])))
        spy_df = frames.get("SPY")
        for t in tickers:
            if t in frames:
                try:
                    result["tickers"].append(ticker_card(t, frames[t], spy_df))
                except Exception as e:
                    result["tickers"].append({"ticker": t, "error": str(e)})
            else:
                result["tickers"].append({"ticker": t, "error": "no data (try WebSearch for price)"})

    if as_json:
        print(json.dumps(result, indent=2))
        return

    r = reg
    print(f"═══ REGIME: {r['regime']} ═══  SPY {r.get('spy')} | 50DMA {r.get('spy_sma50')} | "
          f"200DMA {r.get('spy_sma200')} | VIX {r.get('vix')}")
    print(f"    → {r.get('rules', r.get('reason',''))}")
    for c in result["tickers"]:
        if "error" in c:
            print(f"\n{c['ticker']}: ERROR — {c['error']}")
            continue
        f = c["flags"]
        tags = " ".join(k.upper() for k, v in f.items() if v)
        print(f"\n{c['ticker']}: ${c['last']} ({c['chg_pct']:+.2f}%)  ATR14 ${c['atr14']} ({c['atr_pct']}%)  "
              f"RSI2 {c['rsi2']}  RVOL {c['rvol']}  RS1M {c['rs_1m_vs_spy_pct']}%")
        print(f"    EMA20 {c['ema20']} | SMA50 {c['sma50']} | SMA200 {c['sma200']}")
        print(f"    SWING: stop {c['swing_stop_1_5atr']} / target {c['swing_target_3atr']} (1:2)  "
              f"DIP-stop {c['dip_stop_2atr']}")
        if tags:
            print(f"    FLAGS: {tags}")


if __name__ == "__main__":
    main()
