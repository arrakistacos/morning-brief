#!/usr/bin/env python3
"""
levels.py — Previous-session range and multi-day swing structure.

Level vocabulary (as used by the sneaky-buy playbook):

    range high / range low   Previous trading session's daily high / low.
    swing low                Nearest fractal pivot low BELOW the previous
                             session's range low. The first real structural
                             support underneath yesterday's floor.
    swing high               Nearest fractal pivot high ABOVE the previous
                             session's range high.

A fractal pivot low at bar i means low[i] is the strict minimum of the window
[i-k, i+k]. k=2 (a 5-bar fractal) is the standard definition and is what the
playbook's charts show.

Target rule this feeds:

    red candle broke BELOW swing low  ->  target = range low   (deep break,
                                          structure gone, take the bounce back
                                          to yesterday's floor)
    red candle broke range low only   ->  target = range high  (structure
                                          intact, play for the full retrace)
"""

from __future__ import annotations

from datetime import date
from typing import Any

PIVOT_K = 2          # 5-bar fractal
SWING_LOOKBACK = 60  # daily bars searched for structure
ATR_N = 14


# ── indicators ───────────────────────────────────────────────────────────────

def wilder_atr(bars: list[dict], n: int = ATR_N) -> float | None:
    """Wilder's ATR over the last n bars. Salvaged from the old strategy engine."""
    if len(bars) < n + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i]["h"], bars[i]["l"], bars[i - 1]["c"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    if len(trs) < n:
        return None
    atr = sum(trs[:n]) / n
    for tr in trs[n:]:
        atr = (atr * (n - 1) + tr) / n
    return atr


def pivot_lows(bars: list[dict], k: int = PIVOT_K) -> list[tuple[int, float]]:
    """
    Indices and prices of fractal pivot lows.

    The right-hand window is truncated near the end of the series (minimum one
    confirming bar). A strict k-bar-each-side rule would make the two most
    recent swings invisible, which is exactly the structure sitting closest to
    today's open and the structure a trader reads straight off the chart.
    """
    out = []
    n = len(bars)
    for i in range(k, n - 1):
        lo = bars[i]["l"]
        right = min(k, n - 1 - i)
        window = bars[i - k : i + right + 1]
        others = [b for j, b in enumerate(window) if (i - k + j) != i]
        if all(lo <= b["l"] for b in others) and any(lo < b["l"] for b in others):
            out.append((i, lo))
    return out


def pivot_highs(bars: list[dict], k: int = PIVOT_K) -> list[tuple[int, float]]:
    out = []
    n = len(bars)
    for i in range(k, n - 1):
        hi = bars[i]["h"]
        right = min(k, n - 1 - i)
        window = bars[i - k : i + right + 1]
        others = [b for j, b in enumerate(window) if (i - k + j) != i]
        if all(hi >= b["h"] for b in others) and any(hi > b["h"] for b in others):
            out.append((i, hi))
    return out


# ── level extraction ─────────────────────────────────────────────────────────

def compute_levels(sym: str, daily: list[dict], today: date | None = None) -> dict[str, Any] | None:
    """
    Build the level set for `sym` from daily OHLCV bars (oldest first).

    Every bar dated on or after `today` is dropped, so "previous day" always
    means the last COMPLETED session before the target date.
    """
    if not daily or len(daily) < ATR_N + PIVOT_K * 2 + 5:
        return None

    bars = list(daily)
    if today is not None:
        # Drop EVERY bar at or after the target date, not just the last one.
        # Live there is only ever one (today's in-progress bar), but replaying a
        # past date with --date leaves later sessions in the series, and taking
        # only the last one off makes the target day its own "previous day" —
        # a silent, total corruption of every level.
        bars = [b for b in bars if b["dt"].date() < today]
    if len(bars) < ATR_N + PIVOT_K * 2 + 5:
        return None

    prev = bars[-1]
    range_high, range_low, prev_close = prev["h"], prev["l"], prev["c"]

    window = bars[-SWING_LOOKBACK:] if len(bars) > SWING_LOOKBACK else bars

    # Nearest structural support below yesterday's floor. Fractal pivots first;
    # if the recent structure has none (e.g. a persistent downtrend making fresh
    # lows), fall back to the lowest low in the window.
    lows_below = [p for _, p in pivot_lows(window) if p < range_low]
    if lows_below:
        swing_low = max(lows_below)          # nearest one underneath
        swing_low_src = "pivot"
    else:
        floor = min(b["l"] for b in window)
        swing_low = floor if floor < range_low else None
        swing_low_src = "window_low" if swing_low is not None else "none"

    highs_above = [p for _, p in pivot_highs(window) if p > range_high]
    if highs_above:
        swing_high = min(highs_above)        # nearest one overhead
        swing_high_src = "pivot"
    else:
        ceil_ = max(b["h"] for b in window)
        swing_high = ceil_ if ceil_ > range_high else None
        swing_high_src = "window_high" if swing_high is not None else "none"

    atr = wilder_atr(bars)
    vols = [b["v"] for b in bars[-20:] if b["v"]]
    avg_vol = sum(vols) / len(vols) if vols else 0.0
    avg_dollar_vol = avg_vol * prev_close

    return {
        "symbol": sym,
        "prev_session": prev["dt"].date().isoformat(),
        "range_high": round(range_high, 4),
        "range_low": round(range_low, 4),
        "prev_close": round(prev_close, 4),
        "prev_open": round(prev["o"], 4),
        "swing_low": round(swing_low, 4) if swing_low is not None else None,
        "swing_low_src": swing_low_src,
        "swing_high": round(swing_high, 4) if swing_high is not None else None,
        "swing_high_src": swing_high_src,
        "atr14": round(atr, 4) if atr else None,
        "avg_vol20": int(avg_vol),
        "avg_dollar_vol20": int(avg_dollar_vol),
    }


def rsi_series(closes: list[float], n: int = 14) -> list[float | None]:
    """
    Wilder RSI across a close series. Index-aligned with `closes`; entries before
    the average is seeded are None.

    Used on 15-minute bars to test the sneaky-pivot RSI signature: momentum
    driven DOWN across the red opening candle, then back UP across the green
    one — a V-shaped trough. A drop that rolls momentum over and immediately
    recovers it is showing genuine resistance rather than a pause on the way
    lower.
    """
    if len(closes) < n + 1:
        return [None] * len(closes)

    out: list[float | None] = [None] * len(closes)
    gains, losses = [], []
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g, avg_l = sum(gains) / n, sum(losses) / n

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 100.0
        rs = g / l
        return 100.0 - (100.0 / (1.0 + rs))

    out[n] = _rsi(avg_g, avg_l)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0.0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0.0)) / n
        out[i] = _rsi(avg_g, avg_l)
    return out
