#!/usr/bin/env python3
"""
confirm.py — 09:00 CT · THE STRIKE.

The second 15-minute candle (09:45–10:00 ET) has closed. Of everything the
08:45 stalk flagged, keep only the names where the drop has visibly hit
resistance — the sneaky candle.

Confirmation gate — every condition must hold:
    bar2.close > bar2.open      the candle is green
    bar2.low  >= bar1.low       its wick never took out the red candle's low
    RSI(14) traces a V          momentum fell across the red candle and rose
                                across the green one
    target is the RANGE HIGH    i.e. the red candle broke the range low but
                                held above the swing low, so structure is intact

Trade maths (long only — cash account, no shorting):

    entry   = green candle's close
    stop    = low of the initial red candle          (that wick IS the stop)
    target  = previous day RANGE HIGH  (range-low targets are filtered out)

    risk    = entry - stop
    reward  = target - entry
    R:R     = reward / risk

Sorted by R:R, best first. Setups whose target already sits at or below the
entry are separated out as `expired` rather than shown with a negative ratio.

The dashboard applies one further gate the scanner cannot: the news rating must
come back `clear`. See sneak/dashboard.py.

Usage:
    python -m sneak.confirm                # waits for the 10:00 ET bar
    python -m sneak.confirm --no-wait --date 2026-08-14
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

from . import yahoo
from .levels import rsi_series
from .prep import CACHE_DIR
from .scan_open import wait_for_bar

BAR2_OPEN_ET = (9, 45)
BAR2_CLOSE_ET = (10, 0)

# Below this the "green candle" is really a doji and the resistance read is noise.
MIN_GREEN_BODY_PCT = 0.05

# RSI period, on the 15-minute series.
RSI_N = 14

# Reference threshold only — no longer used to bucket anything out. A stop
# closer than this to the entry sits inside the spread, so the row is tagged
# `tight_stop` and the dashboard marks it, but it still ranks on its R:R.
MIN_RISK_PCT = 0.50


def load_stalk(day: date) -> dict:
    p = CACHE_DIR / f"stalk-{day.isoformat()}.json"
    if not p.exists():
        raise SystemExit(f"[strike] no stalk file for {day} — run `python -m sneak.scan_open` first.")
    return json.loads(p.read_text())


def _rsi_signature(bars: list[dict], bar1: dict, bar2: dict) -> dict | None:
    """
    RSI(14) on the 15-minute series, read across the two opening candles.

    Returns the three readings plus `trough`: True when RSI fell across the red
    candle and rose across the green one — the V that marks momentum turning
    rather than merely pausing.

    `prior` is the last bar of the previous session, so the red candle's RSI
    move is measured against where momentum stood going into the open.
    """
    closes = [b["c"] for b in bars]
    if len(closes) < RSI_N + 3:
        return None
    series = rsi_series(closes, RSI_N)

    try:
        i1 = next(i for i, b in enumerate(bars) if b["t"] == bar1["t"])
        i2 = next(i for i, b in enumerate(bars) if b["t"] == bar2["t"])
    except StopIteration:
        return None
    if i1 == 0:
        return None

    prior, r1, r2 = series[i1 - 1], series[i1], series[i2]
    if prior is None or r1 is None or r2 is None:
        return None

    return {
        "prior": round(prior, 2),
        "after_red": round(r1, 2),
        "after_green": round(r2, 2),
        "drop": round(prior - r1, 2),
        "recovery": round(r2 - r1, 2),
        "trough": bool(r1 < prior and r2 > r1),
    }


def _evaluate(cand: dict, bar1: dict, bar2: dict) -> dict:
    lv = cand["levels"]
    b1 = cand["bar1"]

    entry = bar2["c"]
    stop = bar1["l"]
    risk = entry - stop
    broke_swing = b1["broke_swing_low"]
    target = lv["range_low"] if broke_swing else lv["range_high"]
    reward = target - entry
    rr = (reward / risk) if risk > 0 else None

    g_range = max(bar2["h"] - bar2["l"], 1e-9)
    g_body = bar2["c"] - bar2["o"]

    return {
        "entry": round(entry, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "target_kind": "prev day range low" if broke_swing else "prev day range high",
        "broke_swing_low": broke_swing,
        "risk_per_share": round(risk, 4),
        "reward_per_share": round(reward, 4),
        "risk_pct": round(risk / entry * 100, 3) if entry else None,
        "reward_pct": round(reward / entry * 100, 3) if entry else None,
        "rr": round(rr, 3) if rr is not None else None,
        "bar2": {
            "open": round(bar2["o"], 4),
            "high": round(bar2["h"], 4),
            "low": round(bar2["l"], 4),
            "close": round(bar2["c"], 4),
            "volume": int(bar2["v"]),
            "body_pct": round(g_body / g_range, 4),
            "reclaim_pct": round((bar2["c"] - bar1["l"]) / max(bar1["h"] - bar1["l"], 1e-9), 4),
            "held_above_red_low": bar2["l"] >= bar1["l"],
        },
    }


def run(day: date | None = None, wait: bool = True, workers: int = 24) -> dict:
    t0 = time.time()
    day = day or yahoo.now_et().date()
    stalk = load_stalk(day)
    cands = {c["symbol"]: c for c in stalk["candidates"]}
    print(f"[strike] {len(cands)} stalk candidates carried forward", flush=True)

    if wait:
        wait_for_bar(*BAR2_CLOSE_ET)

    # 5 days of 15-minute bars rather than 1: RSI(14) needs history behind the
    # open, otherwise the reading at 09:30 is unseeded. Same number of calls.
    ch = yahoo.charts(list(cands), rng="5d", interval="15m", workers=workers)

    confirmed, expired = [], []
    rejected = {
        "no_bar2": 0,
        "not_green": 0,
        "doji": 0,
        "undercut_red_low": 0,
        "rsi_no_trough": 0,
        "target_is_range_low": 0,
    }

    for sym, cand in cands.items():
        bars = ch.get(sym)
        if not bars:
            rejected["no_bar2"] += 1
            continue
        session = yahoo.session_bars(bars, day)
        if len(session) < 2:
            rejected["no_bar2"] += 1
            continue
        bar1, bar2 = session[0], session[1]
        if (bar2["dt"].hour, bar2["dt"].minute) != BAR2_OPEN_ET:
            rejected["no_bar2"] += 1
            continue
        if bar2["c"] <= bar2["o"]:
            rejected["not_green"] += 1
            continue
        if bar2["l"] < bar1["l"]:
            rejected["undercut_red_low"] += 1
            continue
        g_range = max(bar2["h"] - bar2["l"], 1e-9)
        if (bar2["c"] - bar2["o"]) / g_range < MIN_GREEN_BODY_PCT:
            rejected["doji"] += 1
            continue

        # ── RSI trough ──────────────────────────────────────────────────────
        # The red candle must push momentum DOWN and the green candle must pull
        # it back UP: a V in RSI across the two bars. A drop that rolls RSI over
        # and immediately recovers it is hitting real resistance; a drop that
        # keeps RSI sliding is still falling and the green bar is just a pause.
        rsi = _rsi_signature(bars, bar1, bar2)
        if rsi is None or not rsi["trough"]:
            rejected["rsi_no_trough"] += 1
            continue

        # ── target must be the previous day's range HIGH ─────────────────────
        # i.e. the red candle broke the range low but held above the swing low,
        # so the structure is intact and the full retrace is the play.
        if cand["bar1"]["broke_swing_low"]:
            rejected["target_is_range_low"] += 1
            continue

        trade = _evaluate(cand, bar1, bar2)
        trade["rsi"] = rsi
        row = {
            "symbol": sym,
            "levels": cand["levels"],
            "bar1": cand["bar1"],
            "stalk_score": cand["stalk_score"],
            "trade": trade,
        }
        red_range = max(bar1["h"] - bar1["l"], 1e-9)
        trade["risk_vs_red_range"] = round(trade["risk_per_share"] / red_range, 4)
        # Hair-trigger stops are no longer bucketed out — they rank alongside
        # everything else. `risk_pct` stays on the row so a stop sitting inside
        # the spread is still visible on the dashboard.
        trade["tight_stop"] = (
            trade["risk_pct"] is not None and trade["risk_pct"] < MIN_RISK_PCT
        )

        if trade["rr"] is None or trade["rr"] <= 0:
            row["expired_reason"] = (
                "target already reached by the green candle"
                if trade["reward_per_share"] <= 0
                else "no risk distance (entry at stop)"
            )
            expired.append(row)
        else:
            confirmed.append(row)

    confirmed.sort(key=lambda r: (-r["trade"]["rr"], r["bar1"]["wick_pct"]))
    expired.sort(key=lambda r: -r["stalk_score"])

    payload = {
        "stage": "strike",
        "session": day.isoformat(),
        "generated_at": datetime.now(yahoo.CT).isoformat(timespec="seconds"),
        "bar": "09:45-10:00 ET",
        "from_stalk": len(cands),
        "rejected": rejected,
        "confirmed_count": len(confirmed),
        "expired_count": len(expired),
        "filters": {"rsi_period": RSI_N, "rsi_trough_required": True,
                    "target_must_be": "prev day range high", "news_must_be": "clear"},
        "elapsed_sec": round(time.time() - t0, 1),
        "stalk_meta": {k: stalk[k] for k in ("scanned", "quoted", "narrowed", "generated_at")},
        "confirmed": confirmed,
        "expired": expired,
    }

    out = CACHE_DIR / f"strike-{day.isoformat()}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(
        f"[strike] {len(confirmed)} confirmed (RSI-V + range-high), {len(expired)} expired · "
        f"rejected {rejected} · {payload['elapsed_sec']}s → {out.name}",
        flush=True,
    )
    for r in confirmed[:20]:
        t = r["trade"]
        print(
            f"  {r['symbol']:<6} RR {t['rr']:>6.2f}  entry {t['entry']:>9.2f}  "
            f"stop {t['stop']:>9.2f} (-{t['risk_pct']:.2f}%)  tgt {t['target']:>9.2f} "
            f"(+{t['reward_pct']:.2f}%)  {t['target_kind']}",
            flush=True,
        )
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="09:00 CT sneaky-candle confirmation")
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else None
    run(day=day, wait=not a.no_wait, workers=a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
