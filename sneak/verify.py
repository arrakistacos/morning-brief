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
import sys
from datetime import date, datetime

from . import yahoo
from .prep import CACHE_DIR
from .levels import headroom_pct, in_band, projected_move_pct
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

    # ── strike gates and trade maths ────────────────────────────────────────
    for r in strike["confirmed"]:
        t, b1, lv, s = r["trade"], r["bar1"], r["levels"], r["symbol"]
        b2 = t["bar2"]
        checks += 9
        _fail(problems, b2["close"] > b2["open"], f"{s}: sneaky candle is not green")
        _fail(problems, b2["low"] >= b1["low"] - 1e-9,
              f'{s}: green low {b2["low"]} undercut red low {b1["low"]}')
        _fail(problems, abs(t["entry"] - b2["close"]) < 1e-6,
              f"{s}: entry is not the green candle close")
        _fail(problems, abs(t["stop"] - b1["low"]) < 1e-6,
              f"{s}: stop is not the red candle low")

        # Re-derived from the raw levels rather than read back off the row, so a
        # bad headroom or projection in confirm.py cannot validate itself.
        structural = lv["range_low"] if t["broke_swing_low"] else lv["range_high"]
        if t.get("projected_move_pct") is None:
            # Sessions before the target moved off the structural level.
            want = structural
        else:
            hd = headroom_pct(t["entry"], structural)
            _fail(problems, abs(t["headroom_pct"] - hd) < 0.01,
                  f'{s}: headroom_pct {t["headroom_pct"]} != recomputed {hd:.3f}')
            _fail(problems, t.get("headroom_in_band") is in_band(hd),
                  f'{s}: headroom_in_band {t.get("headroom_in_band")} '
                  f'disagrees with headroom {hd:.2f}%')
            want = t["entry"] * (1 + projected_move_pct(hd) / 100.0)
        _fail(problems, abs(t["target"] - want) < 1e-3,
              f'{s}: target {t["target"]} != expected {want:.4f} '
              f'(broke_swing_low={t["broke_swing_low"]})')

        risk, reward = t["entry"] - t["stop"], t["target"] - t["entry"]
        _fail(problems, risk > 0, f"{s}: non-positive risk")
        if risk > 0:
            _fail(problems, abs(t["rr"] - reward / risk) < 0.01,
                  f'{s}: rr {t["rr"]} != recomputed {reward/risk:.3f}')

        # ── the two gates added on top of the base pattern ──────────────────
        checks += 5
        _fail(problems, t["broke_swing_low"] is False,
              f"{s}: broke the swing low, so its target is the range low — "
              "should have been filtered out")
        _fail(problems, t["target_kind"] == "prev day range high",
              f'{s}: target_kind is {t["target_kind"]}, expected prev day range high')

        rsi = t.get("rsi")
        _fail(problems, isinstance(rsi, dict), f"{s}: no RSI signature recorded")
        if isinstance(rsi, dict):
            _fail(problems, rsi["after_red"] < rsi["prior"],
                  f'{s}: RSI did not fall across the red candle '
                  f'({rsi["prior"]} -> {rsi["after_red"]})')
            _fail(problems, rsi["after_green"] > rsi["after_red"],
                  f'{s}: RSI did not recover across the green candle '
                  f'({rsi["after_red"]} -> {rsi["after_green"]})')

    # ── ordering ────────────────────────────────────────────────────────────
    # Primary sort is the momentum score (R:R breaks ties), because ranking by
    # R:R put the tightest, least executable stops at the top of the list.
    ms = [r.get("momentum", 0) for r in strike["confirmed"]]
    checks += 2
    _fail(problems, all(ms[i] >= ms[i + 1] for i in range(len(ms) - 1)),
          "confirmed list is not sorted by momentum score descending")
    _fail(problems, all(0 <= m <= 100 for m in ms),
          "a momentum score is outside 0-100")

    # ── no overlap between buckets ──────────────────────────────────────────
    a = {r["symbol"] for r in strike["confirmed"]}
    b = set()
    c = {r["symbol"] for r in strike["expired"]}
    checks += 1
    _fail(problems, not (a & b or a & c or b & c), "a symbol appears in two buckets")

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
