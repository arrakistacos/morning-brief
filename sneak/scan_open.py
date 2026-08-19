#!/usr/bin/env python3
"""
scan_open.py — 08:45 CT · THE STALK.

The first 15-minute candle (09:30–09:45 ET) has just closed. Find every liquid
US stock whose opening candle is a dramatic red break BELOW the previous
session's range low.

Speed strategy — the whole market in under a minute:

    1. spark  (20 symbols/call, ~280 calls, ~15s) gets the first bar's CLOSE
       for every tradable name. Narrow to those trading at or under the range
       low. Thousands -> low hundreds.
    2. chart  (full OHLCV) only for the narrowed set. Now we can apply the real
       gate, which needs the candle's low and open, not just its close.

Hard gates:
    bar1.low < prev range low       the break actually happened, with margin
    bar1.close < bar1.open          the candle is red
    bar1 range >= 0.75x ATR14       the drop is DRAMATIC, not a drift

That third gate matters more than it looks. Without it the scan returns ~124
names a day averaging a 0.28% drop at 0.36x ATR — genuine range-low breaks that
are invisible on a chart and are not the setup being traded. With it the list is
~28 names averaging 1.1x ATR.

Wick tightness and volume burst remain ranking inputs, not filters.

Usage:
    python -m sneak.scan_open              # waits for the bar to close, then scans
    python -m sneak.scan_open --no-wait    # scan immediately (replay / testing)
    python -m sneak.scan_open --date 2026-08-14 --no-wait
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from . import yahoo
from .prep import CACHE_DIR, load_levels

# Pre-narrow buffer: keep names whose first-bar CLOSE is within 1% above the
# range low, since a candle can pierce the level intrabar and close back above.
NARROW_BUFFER = 1.01

# "Dramatic and significant" — the playbook's words, now an actual gate.
#
# Measured as the opening candle's full range divided by the stock's 14-day ATR,
# so it scales to how much that name normally moves rather than using a flat
# percentage. Without this the scan fills with 0.3% drops at 0.36x ATR: real
# breaks of the range low, but not the setup being traded, and invisible on a
# chart. At 0.75 the surviving candles average 1.1x ATR and the list runs
# ~28 names a day instead of ~124.
#
# Set to 0.0 to disable.
MIN_CANDLE_ATR = 0.75

# A break must actually break. Floating-point noise and sub-cent prints make a
# candle that merely TOUCHES yesterday's low look like it pierced it, which is a
# different setup entirely. Require a real margin: one cent, or 2bp of the
# level, whichever is larger.
def break_margin(level: float) -> float:
    return max(0.01, 0.0002 * level)


BAR1_OPEN_ET = (9, 30)
BAR1_CLOSE_ET = (9, 45)
SETTLE_SECONDS = 25   # let Yahoo finalise the bar before we read it


def wait_for_bar(hour: int, minute: int, settle: int = SETTLE_SECONDS, quiet: bool = False) -> None:
    """Block until `settle` seconds past the given ET wall-clock time."""
    now = yahoo.now_et()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(seconds=settle)
    delta = (target - now).total_seconds()
    if delta <= 0:
        return
    if not quiet:
        print(f"[stalk] waiting {delta:.0f}s for the {hour:02d}:{minute:02d} ET bar to settle…", flush=True)
    while True:
        remaining = (target - yahoo.now_et()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5))


def _metrics(bar: dict, lv: dict) -> dict:
    # Round once, up front. Every downstream comparison and the stored artifact
    # then agree exactly — otherwise a raw 57.0999999 and a stored 57.10 can
    # land on opposite sides of a level and the audit disagrees with the scan.
    o, h, l, c = (round(bar[k], 4) for k in ("o", "h", "l", "c"))
    v = bar["v"]
    rng = max(h - l, 1e-9)
    body = o - c                       # positive on a red candle
    lower_wick = c - l                 # red candle: close down to the low
    atr = lv.get("atr14") or 0.0
    avg_vol = lv.get("avg_vol20") or 0

    swing_low = lv.get("swing_low")
    broke_swing = swing_low is not None and l <= swing_low - break_margin(swing_low)
    target = lv["range_low"] if broke_swing else lv["range_high"]

    # Provisional R:R using the red close as a stand-in entry. The real number
    # is computed at 09:00 off the green candle's close.
    #
    # A candle that closes exactly on its low has zero nominal risk here, which
    # would divide by ~0 and rocket to the top of the list. That is an artifact
    # of the proxy entry, not a free trade: the actual entry is the green
    # candle's close, which sits above the low. Floor the risk at 15bp — about
    # one spread — and cap the result so the ranking stays sane.
    risk = max(c - l, 0.0015 * c)
    prospective_rr = min((target - c) / risk, 20.0)

    return {
        "open": round(o, 4),
        "high": round(h, 4),
        "low": round(l, 4),
        "close": round(c, 4),
        "volume": int(v),
        "body": round(body, 4),
        "candle_range": round(rng, 4),
        "lower_wick": round(lower_wick, 4),
        "wick_pct": round(lower_wick / rng, 4),
        "body_pct": round(body / rng, 4),
        "drop_pct": round((o - c) / o * 100, 3) if o else None,
        "gap_pct": round((o - lv["prev_close"]) / lv["prev_close"] * 100, 3),
        "atr_mult": round(rng / atr, 3) if atr else None,
        "vol_burst": round(v / avg_vol, 3) if avg_vol else None,
        "broke_swing_low": broke_swing,
        "break_depth_pct": round((lv["range_low"] - l) / lv["range_low"] * 100, 3),
        "target": round(target, 4),
        "target_kind": "range_low" if broke_swing else "range_high",
        "prospective_rr": round(prospective_rr, 3),
    }


def _stalk_score(m: dict) -> float:
    """
    Ranking only. Tight wick and a decisive body are what make the setup
    tradable; volume confirms the move is real rather than a thin drift.
    """
    score = 0.0
    score += max(0.0, 1.0 - m["wick_pct"]) * 3.0          # short wick = tight stop
    score += min(m["body_pct"], 1.0) * 2.0                 # decisive, not indecisive
    if m.get("atr_mult"):
        score += min(m["atr_mult"], 2.0)                   # dramatic for THIS name
    if m.get("vol_burst"):
        score += min(m["vol_burst"] / 2.0, 1.5)            # real participation
    score += min(max(m["prospective_rr"], 0.0), 5.0) * 0.4
    return round(score, 3)


def run(day: date | None = None, wait: bool = True, workers: int = 24) -> dict:
    t0 = time.time()
    day = day or yahoo.now_et().date()

    cache = load_levels(day)
    if cache is None:
        raise SystemExit(
            f"[stalk] no level cache for {day} — run `python -m sneak.prep` first."
        )
    levels = cache["levels"]
    symbols = list(levels)
    print(f"[stalk] {len(symbols)} tradable names loaded from level cache", flush=True)

    if wait:
        wait_for_bar(*BAR1_CLOSE_ET)

    # ── stage 1: bulk close scan ────────────────────────────────────────────
    # range=1d returns the CURRENT session whatever --date says, so replaying a
    # past day needs a wider window and an explicit lookup of that day's 09:30
    # bar. Live runs stay on the cheap 1d path.
    replay = day != yahoo.now_et().date()
    print(f"[stalk] stage 1 · bulk close scan{' (replay)' if replay else ''}…", flush=True)
    sp = yahoo.spark_closes(symbols, rng="1mo" if replay else "1d",
                            interval="15m", workers=workers)
    want_open = day.strftime("%Y-%m-%d")
    narrowed = []
    for sym, s in sp.items():
        lv = levels.get(sym)
        if not lv:
            continue
        if replay:
            first = None
            for ts, c in zip(s["timestamp"], s["close"]):
                if c is None:
                    continue
                d = datetime.fromtimestamp(int(ts), yahoo.ET)
                if d.strftime("%Y-%m-%d") == want_open and (d.hour, d.minute) == BAR1_OPEN_ET:
                    first = c
                    break
            if first is None:
                continue
        else:
            closes = [c for c in s["close"] if c is not None]
            if not closes:
                continue
            first = closes[0]
        if first <= lv["range_low"] * NARROW_BUFFER:
            narrowed.append(sym)
    print(
        f"[stalk] stage 1 · {len(sp)} quoted → {len(narrowed)} at/under range low "
        f"({time.time()-t0:.0f}s)",
        flush=True,
    )

    # ── stage 2: real candles ───────────────────────────────────────────────
    print("[stalk] stage 2 · pulling opening candles…", flush=True)
    ch = yahoo.charts(narrowed, rng="1mo" if replay else "1d",
                      interval="15m", workers=workers)

    candidates, rejected = [], {"not_red": 0, "no_break": 0, "no_bar": 0, "not_dramatic": 0}
    for sym in narrowed:
        bars = ch.get(sym)
        if not bars:
            rejected["no_bar"] += 1
            continue
        session = yahoo.session_bars(bars, day)
        if not session:
            rejected["no_bar"] += 1
            continue
        bar1 = session[0]
        if bar1["dt"].hour != BAR1_OPEN_ET[0] or bar1["dt"].minute != BAR1_OPEN_ET[1]:
            rejected["no_bar"] += 1
            continue
        lv = levels[sym]
        if round(bar1["l"], 4) > lv["range_low"] - break_margin(lv["range_low"]):
            rejected["no_break"] += 1
            continue
        if not bar1["c"] < bar1["o"]:
            rejected["not_red"] += 1
            continue
        atr = lv.get("atr14") or 0.0
        if MIN_CANDLE_ATR > 0 and atr > 0:
            if (bar1["h"] - bar1["l"]) / atr < MIN_CANDLE_ATR:
                rejected["not_dramatic"] += 1
                continue
        m = _metrics(bar1, lv)
        candidates.append(
            {
                "symbol": sym,
                "levels": {k: lv[k] for k in
                           ("range_high", "range_low", "prev_close", "swing_low",
                            "swing_high", "atr14", "avg_vol20", "prev_session")},
                "bar1": m,
                "stalk_score": _stalk_score(m),
            }
        )

    candidates.sort(key=lambda c: (-c["bar1"]["prospective_rr"], -c["stalk_score"]))

    payload = {
        "stage": "stalk",
        "session": day.isoformat(),
        "generated_at": datetime.now(yahoo.CT).isoformat(timespec="seconds"),
        "bar": "09:30-09:45 ET",
        "scanned": len(symbols),
        "quoted": len(sp),
        "narrowed": len(narrowed),
        "rejected": rejected,
        "elapsed_sec": round(time.time() - t0, 1),
        "candidates": candidates,
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"stalk-{day.isoformat()}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(
        f"[stalk] {len(candidates)} red breaks · rejected {rejected} · "
        f"{payload['elapsed_sec']}s → {out.name}",
        flush=True,
    )
    for c in candidates[:15]:
        b = c["bar1"]
        print(
            f"  {c['symbol']:<6} drop {b['drop_pct']:>6.2f}%  wick {b['wick_pct']*100:>5.1f}%  "
            f"atr {b['atr_mult'] or 0:>4.2f}x  {'SWING' if b['broke_swing_low'] else 'range'}  "
            f"pRR {b['prospective_rr']:>5.2f}",
            flush=True,
        )
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="08:45 CT opening-drop scanner")
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else None
    run(day=day, wait=not a.no_wait, workers=a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
