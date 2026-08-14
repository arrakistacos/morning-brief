#!/usr/bin/env python3
"""
confirm.py — 09:00 CT · THE STRIKE.

The second 15-minute candle (09:45–10:00 ET) has closed. Of everything the
08:45 stalk flagged, keep only the names where the drop has visibly hit
resistance — the sneaky candle.

Confirmation gate:
    bar2.close > bar2.open      the candle is green
    bar2.low  >= bar1.low       its wick never took out the red candle's low

Trade maths (long only — cash account, no shorting):

    entry   = green candle's close
    stop    = low of the initial red candle          (that wick IS the stop)
    target  = previous day RANGE LOW   if the red candle broke the swing low
              previous day RANGE HIGH  if it only broke the range low

    risk    = entry - stop
    reward  = target - entry
    R:R     = reward / risk

Sorted by R:R, best first. Setups whose target already sits at or below the
entry are separated out as `expired` rather than shown with a negative ratio.

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
from .prep import CACHE_DIR
from .scan_open import wait_for_bar

BAR2_OPEN_ET = (9, 45)
BAR2_CLOSE_ET = (10, 0)

# Below this the "green candle" is really a doji and the resistance read is noise.
MIN_GREEN_BODY_PCT = 0.05

# Tradability floors on the stop distance.
#
# When the green candle closes a penny above the red candle's low, the maths
# says 20:1 — but the stop is then sitting inside the bid/ask spread and normal
# noise takes it out before the trade breathes. Those setups are real pattern
# hits, so they are not discarded; they are bucketed as `hair_trigger` and kept
# out of the main ranking so they cannot crowd out genuinely tradable ratios.
MIN_RISK_PCT = 0.50        # stop at least 0.5% below entry
MIN_RISK_VS_RED_RANGE = 0.08   # and at least 8% of the red candle's own range
MIN_RISK_ABS = 0.05            # and at least a nickel in absolute terms


def load_stalk(day: date) -> dict:
    p = CACHE_DIR / f"stalk-{day.isoformat()}.json"
    if not p.exists():
        raise SystemExit(f"[strike] no stalk file for {day} — run `python -m sneak.scan_open` first.")
    return json.loads(p.read_text())


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

    ch = yahoo.charts(list(cands), rng="1d", interval="15m", workers=workers)

    confirmed, expired, hair_trigger = [], [], []
    rejected = {"no_bar2": 0, "not_green": 0, "doji": 0, "undercut_red_low": 0}

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

        trade = _evaluate(cand, bar1, bar2)
        row = {
            "symbol": sym,
            "levels": cand["levels"],
            "bar1": cand["bar1"],
            "stalk_score": cand["stalk_score"],
            "trade": trade,
        }
        red_range = max(bar1["h"] - bar1["l"], 1e-9)
        too_tight = (
            trade["risk_pct"] is None
            or trade["risk_pct"] < MIN_RISK_PCT
            or trade["risk_per_share"] < MIN_RISK_ABS
            or trade["risk_per_share"] / red_range < MIN_RISK_VS_RED_RANGE
        )
        trade["risk_vs_red_range"] = round(trade["risk_per_share"] / red_range, 4)

        if trade["rr"] is None or trade["rr"] <= 0:
            row["expired_reason"] = (
                "target already reached by the green candle"
                if trade["reward_per_share"] <= 0
                else "no risk distance (entry at stop)"
            )
            expired.append(row)
        elif too_tight:
            row["note"] = (
                f"stop only {trade['risk_pct']:.2f}% below entry — inside the spread; "
                "ratio is arithmetically true but not executable"
            )
            hair_trigger.append(row)
        else:
            confirmed.append(row)

    confirmed.sort(key=lambda r: (-r["trade"]["rr"], r["bar1"]["wick_pct"]))
    hair_trigger.sort(key=lambda r: -r["trade"]["rr"])
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
        "hair_trigger_count": len(hair_trigger),
        "risk_floor": {"min_risk_pct": MIN_RISK_PCT, "min_risk_vs_red_range": MIN_RISK_VS_RED_RANGE},
        "elapsed_sec": round(time.time() - t0, 1),
        "stalk_meta": {k: stalk[k] for k in ("scanned", "quoted", "narrowed", "generated_at")},
        "confirmed": confirmed,
        "hair_trigger": hair_trigger,
        "expired": expired,
    }

    out = CACHE_DIR / f"strike-{day.isoformat()}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(
        f"[strike] {len(confirmed)} confirmed, {len(hair_trigger)} hair-trigger, {len(expired)} expired · "
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
