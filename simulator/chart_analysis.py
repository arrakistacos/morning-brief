#!/usr/bin/env python3
"""
chart_analysis.py — Technical analysis and chart pattern detection.

Uses yfinance to pull OHLCV data and computes:
  - Price vs 20/50/200 DMA
  - RSI (14-day)
  - MACD (12/26/9 EMA) — bullish/bearish crossover
  - Volume trend (20d avg vs recent)
  - Support / Resistance levels
  - Pattern detection (bull flag, bear flag, cup & handle, double top/bottom,
    ascending triangle, head & shoulders)
  - Composite signal: STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL

Usage:
    python simulator/chart_analysis.py --ticker AAPL
    python simulator/chart_analysis.py --ticker TSLA --period 180d
    python simulator/chart_analysis.py --ticker SPY NVDA AMD --period 90d
"""

import argparse
import json
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------

def compute_rsi(closes: pd.Series, period: int = 14) -> float:
    delta  = closes.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def compute_macd(closes: pd.Series):
    ema12  = closes.ewm(span=12, adjust=False).mean()
    ema26  = closes.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal

    recent_cross = "none"
    if len(hist) >= 3:
        # Bullish crossover: histogram crosses from negative to positive
        if hist.iloc[-3] < 0 and hist.iloc[-1] > 0:
            recent_cross = "bullish_crossover"
        elif hist.iloc[-3] > 0 and hist.iloc[-1] < 0:
            recent_cross = "bearish_crossover"
        elif hist.iloc[-1] > hist.iloc[-2] > hist.iloc[-3]:
            recent_cross = "bullish_momentum"
        elif hist.iloc[-1] < hist.iloc[-2] < hist.iloc[-3]:
            recent_cross = "bearish_momentum"

    return {
        "macd":           round(float(macd.iloc[-1]), 4),
        "signal":         round(float(signal.iloc[-1]), 4),
        "histogram":      round(float(hist.iloc[-1]), 4),
        "crossover":      recent_cross,
        "bias":           "bullish" if macd.iloc[-1] > signal.iloc[-1] else "bearish",
    }


def compute_volume_trend(df: pd.DataFrame) -> dict:
    avg_20d = float(df["Volume"].iloc[-21:-1].mean())
    today   = float(df["Volume"].iloc[-1])
    ratio   = round(today / avg_20d, 2) if avg_20d > 0 else 1.0
    return {
        "avg_20d":       int(avg_20d),
        "today":         int(today),
        "ratio":         ratio,
        "above_average": ratio >= 1.0,
    }


def compute_dma(closes: pd.Series, price: float) -> dict:
    def dma_info(n):
        if len(closes) < n:
            return None
        val = round(float(closes.iloc[-n:].mean()), 4)
        gap_pct = round(((price - val) / val) * 100, 2)
        return {"value": val, "above": price > val, "gap_pct": gap_pct}

    return {
        "dma20":  dma_info(20),
        "dma50":  dma_info(50),
        "dma200": dma_info(200),
    }


def find_support_resistance(df: pd.DataFrame, lookback: int = 60) -> dict:
    recent = df.tail(lookback)
    lows   = recent["Low"]
    highs  = recent["High"]
    price  = float(df["Close"].iloc[-1])

    # Find swing lows below current price (support)
    supports = []
    for i in range(2, len(lows) - 2):
        if (lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1] and
                lows.iloc[i] < lows.iloc[i-2] and lows.iloc[i] < lows.iloc[i+2]):
            supports.append(float(lows.iloc[i]))
    supports = [s for s in supports if s < price]
    nearest_support = round(max(supports), 4) if supports else round(float(lows.min()), 4)

    # Find swing highs above current price (resistance)
    resistances = []
    for i in range(2, len(highs) - 2):
        if (highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1] and
                highs.iloc[i] > highs.iloc[i-2] and highs.iloc[i] > highs.iloc[i+2]):
            resistances.append(float(highs.iloc[i]))
    resistances = [r for r in resistances if r > price]
    nearest_resistance = round(min(resistances), 4) if resistances else round(float(highs.max()), 4)

    support_dist_pct    = round(((price - nearest_support) / price) * 100, 2)
    resistance_dist_pct = round(((nearest_resistance - price) / price) * 100, 2)

    return {
        "support":              nearest_support,
        "support_dist_pct":     support_dist_pct,
        "resistance":           nearest_resistance,
        "resistance_dist_pct":  resistance_dist_pct,
        "risk_reward":          round(resistance_dist_pct / support_dist_pct, 2) if support_dist_pct > 0 else None,
    }


# ---------------------------------------------------------------------------
# Pattern detection (heuristic)
# ---------------------------------------------------------------------------

def detect_patterns(df: pd.DataFrame) -> list:
    patterns = []
    closes = df["Close"]
    highs  = df["High"]
    lows   = df["Low"]
    n = len(closes)

    if n < 30:
        return patterns

    recent_20 = closes.iloc[-20:]
    recent_10 = closes.iloc[-10:]
    price     = float(closes.iloc[-1])

    # --- Bull Flag ---
    # Prior strong uptrend (last 20-40 bars), then tight consolidation last 5-10 bars
    prior = closes.iloc[-40:-10]
    consol = closes.iloc[-10:]
    if len(prior) >= 10:
        prior_gain = (float(prior.iloc[-1]) - float(prior.iloc[0])) / float(prior.iloc[0])
        consol_range = (float(consol.max()) - float(consol.min())) / float(consol.min())
        if prior_gain > 0.05 and consol_range < 0.04:
            patterns.append({
                "name": "bull_flag",
                "confidence": "medium",
                "bias": "bullish",
                "description": f"Strong uptrend ({prior_gain*100:.1f}% gain) followed by tight consolidation ({consol_range*100:.1f}% range). Breakout above flag high is entry signal."
            })

    # --- Bear Flag ---
    if len(prior) >= 10:
        prior_drop = (float(prior.iloc[0]) - float(prior.iloc[-1])) / float(prior.iloc[0])
        if prior_drop > 0.05 and consol_range < 0.04:
            patterns.append({
                "name": "bear_flag",
                "confidence": "medium",
                "bias": "bearish",
                "description": f"Sharp downtrend ({prior_drop*100:.1f}% drop) followed by tight consolidation. Breakdown below flag low confirms continuation."
            })

    # --- Double Top ---
    window = closes.iloc[-40:]
    if len(window) >= 20:
        peak_idx  = window.idxmax()
        left_max  = float(window.loc[:peak_idx].iloc[:-5].max()) if len(window.loc[:peak_idx]) > 5 else 0
        right_max = float(window.loc[peak_idx:].iloc[5:].max()) if len(window.loc[peak_idx:]) > 5 else 0
        tol = float(window.max()) * 0.02
        if left_max > 0 and right_max > 0 and abs(left_max - right_max) < tol:
            valley = float(window.loc[peak_idx:].min()) if len(window.loc[peak_idx:]) > 1 else 0
            if valley < left_max * 0.97:
                patterns.append({
                    "name": "double_top",
                    "confidence": "medium",
                    "bias": "bearish",
                    "description": f"Two similar peaks near ${left_max:.2f} with valley between. Neckline break triggers measured move equal to pattern height."
                })

    # --- Double Bottom ---
    trough_idx = window.idxmin()
    left_min  = float(window.loc[:trough_idx].iloc[:-5].min()) if len(window.loc[:trough_idx]) > 5 else 0
    right_min = float(window.loc[trough_idx:].iloc[5:].min()) if len(window.loc[trough_idx:]) > 5 else 0
    if left_min > 0 and right_min > 0:
        tol = float(window.min()) * 0.02
        if abs(left_min - right_min) < tol:
            peak_between = float(window.loc[trough_idx:].max()) if len(window.loc[trough_idx:]) > 1 else 0
            if peak_between > left_min * 1.03:
                patterns.append({
                    "name": "double_bottom",
                    "confidence": "medium",
                    "bias": "bullish",
                    "description": f"Two similar troughs near ${left_min:.2f}. Neckline breakout signals reversal; target = neckline + pattern height."
                })

    # --- Ascending Triangle ---
    recent_highs = highs.iloc[-20:]
    recent_lows  = lows.iloc[-20:]
    high_range = (float(recent_highs.max()) - float(recent_highs.min())) / float(recent_highs.max())
    low_slope  = float(recent_lows.iloc[-1]) - float(recent_lows.iloc[0])
    if high_range < 0.025 and low_slope > 0:
        patterns.append({
            "name": "ascending_triangle",
            "confidence": "medium",
            "bias": "bullish",
            "description": f"Flat resistance near ${float(recent_highs.max()):.2f} with rising lows. Breakout above resistance typically resolves bullish."
        })

    # --- Cup and Handle ---
    if n >= 60:
        cup_data = closes.iloc[-60:]
        cup_left = float(cup_data.iloc[0])
        cup_min  = float(cup_data.min())
        cup_right = float(cup_data.iloc[-15])
        handle = closes.iloc[-15:]
        handle_drop = (float(handle.max()) - float(handle.min())) / float(handle.max())
        symmetry = abs(cup_left - cup_right) / cup_left if cup_left > 0 else 1
        depth = (cup_left - cup_min) / cup_left if cup_left > 0 else 0
        if depth > 0.10 and symmetry < 0.05 and handle_drop < 0.06 and price > cup_right * 0.98:
            patterns.append({
                "name": "cup_and_handle",
                "confidence": "high",
                "bias": "bullish",
                "description": f"Rounded U-shaped base ({depth*100:.1f}% depth) with tight handle consolidation ({handle_drop*100:.1f}% range). Breakout above cup rim is buy signal."
            })

    # --- Head and Shoulders (basic) ---
    if n >= 50:
        seg = closes.iloc[-50:]
        third = len(seg) // 3
        left_sh  = float(seg.iloc[:third].max())
        head     = float(seg.iloc[third:2*third].max())
        right_sh = float(seg.iloc[2*third:].max())
        if (head > left_sh * 1.02 and head > right_sh * 1.02 and
                abs(left_sh - right_sh) / left_sh < 0.04):
            neckline = float(min(seg.iloc[:third].min(), seg.iloc[2*third:].min()))
            if price < head * 0.98:
                patterns.append({
                    "name": "head_and_shoulders",
                    "confidence": "medium",
                    "bias": "bearish",
                    "description": f"Head (${head:.2f}) flanked by two lower shoulders (~${left_sh:.2f}). Neckline at ~${neckline:.2f}; break below triggers measured move."
                })

    return patterns


# ---------------------------------------------------------------------------
# Composite signal
# ---------------------------------------------------------------------------

def compute_composite_signal(rsi, macd_data, dma_data, volume, patterns, sr):
    score = 0
    reasons = []

    # RSI
    if rsi < 30:
        score += 2
        reasons.append(f"RSI {rsi} — oversold (bullish)")
    elif rsi < 45:
        score += 1
        reasons.append(f"RSI {rsi} — approaching oversold")
    elif rsi > 70:
        score -= 2
        reasons.append(f"RSI {rsi} — overbought (bearish)")
    elif rsi > 55:
        score -= 1
        reasons.append(f"RSI {rsi} — elevated")
    else:
        reasons.append(f"RSI {rsi} — neutral zone")

    # MACD
    cross = macd_data["crossover"]
    if cross in ("bullish_crossover", "bullish_momentum"):
        score += 2
        reasons.append(f"MACD {cross} — bullish momentum")
    elif cross in ("bearish_crossover", "bearish_momentum"):
        score -= 2
        reasons.append(f"MACD {cross} — bearish momentum")
    elif macd_data["bias"] == "bullish":
        score += 1
        reasons.append("MACD above signal line — mild bullish")
    else:
        score -= 1
        reasons.append("MACD below signal line — mild bearish")

    # DMA alignment
    above_count = sum(1 for k in ["dma20","dma50","dma200"]
                      if dma_data.get(k) and dma_data[k]["above"])
    below_count = 3 - above_count
    if above_count == 3:
        score += 2
        reasons.append("Price above all three DMAs — strong bull structure")
    elif above_count == 2:
        score += 1
        reasons.append("Price above 2 of 3 DMAs — moderately bullish")
    elif below_count == 3:
        score -= 2
        reasons.append("Price below all three DMAs — weak structure")
    elif below_count == 2:
        score -= 1
        reasons.append("Price below 2 of 3 DMAs — moderately bearish")

    # Volume confirmation
    if volume["above_average"] and volume["ratio"] > 1.5:
        reasons.append(f"Volume {volume['ratio']}× average — strong conviction")
    elif volume["above_average"]:
        reasons.append(f"Volume {volume['ratio']}× average — above normal")
    else:
        reasons.append(f"Volume {volume['ratio']}× average — below normal (weak conviction)")

    # Pattern signals
    for p in patterns:
        if p["bias"] == "bullish":
            score += 1
            reasons.append(f"Pattern: {p['name']} ({p['confidence']} confidence, bullish)")
        elif p["bias"] == "bearish":
            score -= 1
            reasons.append(f"Pattern: {p['name']} ({p['confidence']} confidence, bearish)")

    # Risk/reward
    if sr.get("risk_reward") and sr["risk_reward"] > 2:
        score += 1
        reasons.append(f"Risk/reward {sr['risk_reward']:.1f}× favorable")
    elif sr.get("risk_reward") and sr["risk_reward"] < 1:
        score -= 1
        reasons.append(f"Risk/reward {sr['risk_reward']:.1f}× unfavorable (tight stop)")

    # Map score to signal
    if score >= 5:
        signal = "STRONG_BUY"
    elif score >= 2:
        signal = "BUY"
    elif score <= -5:
        signal = "STRONG_SELL"
    elif score <= -2:
        signal = "SELL"
    else:
        signal = "NEUTRAL"

    return {"signal": signal, "score": score, "reasons": reasons}


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_ticker(ticker: str, period: str = "90d") -> dict:
    t = yf.Ticker(ticker.upper())
    df = t.history(period=period)

    if df.empty or len(df) < 20:
        return {"ticker": ticker.upper(), "error": "Insufficient data"}

    closes = df["Close"]
    price  = round(float(closes.iloc[-1]), 4)

    rsi        = compute_rsi(closes)
    macd_data  = compute_macd(closes)
    volume     = compute_volume_trend(df)
    dma_data   = compute_dma(closes, price)
    sr         = find_support_resistance(df)
    patterns   = detect_patterns(df)
    composite  = compute_composite_signal(rsi, macd_data, dma_data, volume, patterns, sr)

    # RSI interpretation
    if rsi >= 70:
        rsi_label = "overbought"
    elif rsi <= 30:
        rsi_label = "oversold"
    elif rsi >= 60:
        rsi_label = "elevated"
    elif rsi <= 40:
        rsi_label = "depressed"
    else:
        rsi_label = "neutral"

    result = {
        "ticker":    ticker.upper(),
        "price":     price,
        "period":    period,
        "dma": {
            "dma20":  dma_data["dma20"],
            "dma50":  dma_data["dma50"],
            "dma200": dma_data["dma200"],
        },
        "rsi": {
            "value": rsi,
            "label": rsi_label,
        },
        "macd":    macd_data,
        "volume":  volume,
        "support_resistance": sr,
        "patterns":  patterns,
        "composite": composite,
    }

    return result


def print_analysis(result: dict):
    if "error" in result:
        print(f"\n❌ {result['ticker']}: {result['error']}")
        return

    t = result
    sig = t["composite"]["signal"]
    sig_emoji = {"STRONG_BUY":"🟢🟢","BUY":"🟢","NEUTRAL":"⚪","SELL":"🔴","STRONG_SELL":"🔴🔴"}.get(sig,"⚪")

    print(f"\n{'='*60}")
    print(f"  {t['ticker']}  ${t['price']:,.2f}  {sig_emoji} {sig}  (score: {t['composite']['score']:+d})")
    print(f"{'='*60}")

    # DMA
    dma = t["dma"]
    print("\n📐 Moving Averages:")
    for k, label in [("dma20","20-DMA"),("dma50","50-DMA"),("dma200","200-DMA")]:
        d = dma.get(k)
        if d:
            arrow = "▲" if d["above"] else "▼"
            color_word = "above" if d["above"] else "below"
            print(f"  {label}: ${d['value']:,.2f}  {arrow} {color_word}  ({d['gap_pct']:+.2f}%)")

    # RSI
    rsi = t["rsi"]
    print(f"\n📊 RSI(14): {rsi['value']}  [{rsi['label'].upper()}]")

    # MACD
    m = t["macd"]
    print(f"\n📉 MACD: {m['macd']:+.4f}  Signal: {m['signal']:+.4f}  Hist: {m['histogram']:+.4f}")
    print(f"   Crossover: {m['crossover']}  |  Bias: {m['bias'].upper()}")

    # Volume
    v = t["volume"]
    flag = "✅" if v["above_average"] else "⚠️"
    print(f"\n📦 Volume: {v['today']:,} today  |  20d avg: {v['avg_20d']:,}  |  {v['ratio']}× avg {flag}")

    # Support / Resistance
    sr = t["support_resistance"]
    print(f"\n🎯 Support:    ${sr['support']:,.2f}  ({sr['support_dist_pct']:.2f}% below)")
    print(f"   Resistance: ${sr['resistance']:,.2f}  ({sr['resistance_dist_pct']:.2f}% above)")
    if sr.get("risk_reward"):
        print(f"   Risk/Reward: {sr['risk_reward']:.1f}×")

    # Patterns
    if t["patterns"]:
        print(f"\n🔍 Patterns Detected:")
        for p in t["patterns"]:
            emoji = "🟢" if p["bias"] == "bullish" else "🔴"
            print(f"  {emoji} {p['name'].upper()} ({p['confidence']}) — {p['description']}")
    else:
        print(f"\n🔍 Patterns: none detected")

    # Composite reasoning
    print(f"\n🧠 Signal: {sig_emoji} {sig} (score {t['composite']['score']:+d})")
    for r in t["composite"]["reasons"]:
        print(f"   • {r}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Chart pattern & technical analysis")
    parser.add_argument("--ticker", nargs="+", required=True, help="One or more ticker symbols")
    parser.add_argument("--period", default="90d",
                        help="History period (e.g. 90d, 180d, 1y). Default: 90d")
    parser.add_argument("--json",   action="store_true", help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    results = []
    for ticker in args.ticker:
        result = analyze_ticker(ticker, args.period)
        results.append(result)
        if not args.json:
            print_analysis(result)

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))

    return results


if __name__ == "__main__":
    main()
