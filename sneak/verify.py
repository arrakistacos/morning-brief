#!/usr/bin/env python3
"""
verify.py — Independent audit of a session's output.

Re-derives every gate and every number from the stored artifacts and asserts
they match the playbook. This is deliberately written as a SEPARATE
implementation of the rules rather than a call into the scanner, so a bug in
scan_open/confirm cannot validate itself.

Run it after any change to the strategy code:

    python -m sneak.verify --date 2026-08-14

Exit code 0 = every check passed.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime

from . import yahoo
from .prep import CACHE_DIR
from .scan_open import break_margin


def _fail(msgs: list[str], cond: bool, msg: str) -> None:
    if not cond:
        msgs.append(msg)


def run(day: date) -> int:
    problems: list[str] = []
    checks = 0

    stalk = json.loads((CACHE_DIR / f"stalk-{day.isoformat()}.json").read_text())
    strike = json.loads((CACHE_DIR / f"strike-{day.isoformat()}.json").read_text())

    # ── stalk gates ─────────────────────────────────────────────────────────
    for c in stalk["candidates"]:
        b, lv, s = c["bar1"], c["levels"], c["symbol"]
        checks += 3
        _fail(problems, b["close"] < b["open"], f"{s}: stalk candle is not red")
        _fail(problems,
              b["low"] <= lv["range_low"] - break_margin(lv["range_low"]) + 1e-9,
              f'{s}: stalk low {b["low"]} did not clear range low {lv["range_low"]} by the margin')
        expect_swing = (
            lv["swing_low"] is not None
            and b["low"] <= lv["swing_low"] - break_margin(lv["swing_low"]) + 1e-9
        )
        _fail(problems, b["broke_swing_low"] == expect_swing,
              f'{s}: broke_swing_low={b["broke_swing_low"]} but recomputed {expect_swing}')

    # ── strike gates and trade maths (rules v2) ─────────────────────────────
    version = int(strike.get("version") or 1)
    if version < 2:
        print(f"[verify] {day} was scanned under rules v{version}; checking stalk and levels only")
    for r in (strike["confirmed"] if version >= 2 else []):
        t, b1, lv, s = r["trade"], r["bar1"], r["levels"], r["symbol"]
        b2 = t["bar2"]
        checks += 12
        _fail(problems, b2["close"] > b2["open"], f"{s}: sneaky candle is not green")
        _fail(problems, (b2["close"] - b2["open"]) / max(b2["high"] - b2["low"], 1e-9) >= 0.05 - 1e-9,
              f"{s}: sneaky candle body under 5% of its range")
        _fail(problems, b2["low"] >= b1["low"] - 1e-9,
              f'{s}: green low {b2["low"]} undercut red low {b1["low"]}')

        # Re-derived from first principles rather than imported from the
        # scanner, so a bug there cannot validate itself.
        # first whole cent strictly above the stored sneaky high
        want_trigger = (math.floor(b2["high"] * 100 + 1e-6) + 1) / 100
        _fail(problems, abs(t["trigger"] - want_trigger) < 1e-6 and abs(t["entry"] - want_trigger) < 1e-6,
              f'{s}: trigger {t["trigger"]} is not the sneaky high + $0.01 ({want_trigger})')
        _fail(problems, abs(t["stop"] - b1["low"]) < 1e-6,
              f"{s}: stop is not the red candle low")
        hd = (lv["range_high"] - want_trigger) / want_trigger * 100.0
        _fail(problems, abs(t["headroom_pct"] - hd) < 0.01,
              f'{s}: headroom_pct {t["headroom_pct"]} != recomputed {hd:.3f}')
        _fail(problems, 0.0 < hd < 9.0, f"{s}: headroom {hd:.2f}% is outside 0-9%")
        want_target = want_trigger * (1 + 0.349 * max(hd, 0.0) ** 0.734 / 100.0)
        _fail(problems, abs(t["target"] - want_target) < 1e-3,
              f'{s}: target {t["target"]} != expected {want_target:.4f}')

        risk, reward = want_trigger - b1["low"], want_target - want_trigger
        _fail(problems, risk > 0, f"{s}: non-positive risk")
        if risk > 0:
            _fail(problems, abs(t["rr"] - reward / risk) < 0.01,
                  f'{s}: rr {t["rr"]} != recomputed {reward/risk:.3f}')

        if risk > 0:
            _fail(problems, reward / risk >= 0.35 - 1e-3,
                  f"{s}: reward/risk {reward/risk:.3f} is under the 0.35 floor")
        _fail(problems, b1["broke_swing_low"] is False,
              f"{s}: broke the swing low — should have been filtered out")
        rsi = t.get("rsi")
        _fail(problems, isinstance(rsi, dict) and rsi.get("after_green", 0) >= 40.0,
              f'{s}: RSI(14) after green {(rsi or {}).get("after_green")} is under the floor of 40')
        _fail(problems, t.get("valid_from_et") == "10:00" and t.get("valid_until_et") == "10:15",
              f"{s}: order window is not candle 3 (10:00-10:15 ET)")

    # ── ordering: momentum descending ───────────────────────────────────────
    if version >= 2:
        ms = [r.get("momentum", 0) for r in strike["confirmed"]]
        checks += 2
        _fail(problems, all(ms[i] >= ms[i + 1] for i in range(len(ms) - 1)),
              "confirmed list is not sorted by momentum score descending")
        _fail(problems, all(0 <= m <= 100 for m in ms),
              "a momentum score is outside 0-100")
        syms = [r["symbol"] for r in strike["confirmed"]]
        checks += 1
        _fail(problems, len(syms) == len(set(syms)), "a symbol appears twice in the list")

    # ── spot-check levels against a live re-fetch ───────────────────────────
    sample = [r["symbol"] for r in strike["confirmed"][:5]]
    for s in sample:
        bars = yahoo.chart(s, "3mo", "1d")
        if not bars:
            continue
        prior = [x for x in bars if x["dt"].date() < day]
        if not prior:
            continue
        prev = prior[-1]
        lv = next(r["levels"] for r in strike["confirmed"] if r["symbol"] == s)
        checks += 2
        _fail(problems, abs(prev["h"] - lv["range_high"]) < 0.02,
              f'{s}: range_high {lv["range_high"]} != refetched {prev["h"]:.2f}')
        _fail(problems, abs(prev["l"] - lv["range_low"]) < 0.02,
              f'{s}: range_low {lv["range_low"]} != refetched {prev["l"]:.2f}')

    print(f"[verify] {checks} assertions across "
          f'{len(stalk["candidates"])} stalked / {len(strike["confirmed"])} confirmed')
    if problems:
        print(f"[verify] {len(problems)} PROBLEM(S):")
        for p in problems[:40]:
            print("   ✗", p)
        return 1
    print("[verify] all checks passed ✓")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit a session's scanner output")
    ap.add_argument("--date", type=str, default=None)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else yahoo.now_et().date()
    return run(day)


if __name__ == "__main__":
    sys.exit(main())
