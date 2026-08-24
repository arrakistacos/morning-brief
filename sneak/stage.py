#!/usr/bin/env python3
"""
stage.py — Decide which stage this workflow firing should run.

Why this is state-based rather than clock-based
-----------------------------------------------
The first version mapped ET wall-clock time to a stage. That silently assumed
GitHub fires a cron roughly on time. It does not: measured launch delay on this
repo ran 42-46 minutes every day of the week of 2026-08-17.

The stalk cron is 09:20 ET and its window ended at 09:45, so it tolerated only
25 minutes of delay. On 2026-08-24 the delay was 46 minutes, the firing landed
inside the STRIKE window, strike aborted for lack of a stalk file, and no list
was published at all.

So the question a firing asks is no longer "what time is it" but "what has not
been done yet". stalk-YYYY-MM-DD.json and strike-YYYY-MM-DD.json are committed
to the repo (only levels-* and news-* are gitignored), so a fresh checkout can
see exactly how far today got and pick up from there. Any firing can complete
any outstanding stage, and an extra firing is a cheap no-op.

Running late still beats not running: the scanner reads a CLOSED candle, so a
stalk executed at 10:30 ET produces the same list it would have at 09:45, just
later. Hence the generous cutoffs.

Stage selection
---------------
    manual selftest / prep      always run (no market data needed)
    manual anything else        needs a trading day
    scheduled, not trading day  skip

    scheduled, trading day:
        stalk missing,  now < 12:00 ET   -> stalk   (sleeps if before 09:45:25)
        stalk present, strike missing,
                        now >= 09:45,
                        now < 12:30 ET   -> strike  (sleeps if before 10:00:25)
        everything done                  -> skip
        before 09:05 ET                  -> prep

Usage:
    python -m sneak.stage            # reads MANUAL env, writes $GITHUB_OUTPUT
    python -m sneak.stage --dry-run  # print the decision only
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

CALENDAR_FREE = {"selftest", "prep"}
KNOWN = {"selftest", "prep", "stalk", "strike", "publish", "all"}

PREP_BEFORE = 9 * 60 + 5      # 09:05 ET
STRIKE_FROM = 9 * 60 + 45     # 09:45 ET — the sneaky candle is forming
STALK_CUTOFF = 12 * 60        # 12:00 ET — past this, today is a write-off
STRIKE_CUTOFF = 12 * 60 + 30  # 12:30 ET


def _is_trading_day(now: datetime) -> tuple[bool, str]:
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from market_calendar import is_trading_day  # type: ignore

        return bool(is_trading_day(now.date())), "nyse-calendar"
    except Exception as e:  # pragma: no cover
        print(f"::warning::NYSE calendar unavailable ({e}); falling back to weekday check")
        return now.weekday() < 5, "weekday-fallback"


def _done(prefix: str, now: datetime) -> bool:
    return (CACHE / f"{prefix}-{now.date().isoformat()}.json").exists()


def decide(manual: str, now: datetime, trading: bool,
           have_stalk: bool, have_strike: bool) -> tuple[str, str]:
    """Pure and unit-testable: no clock, no filesystem, no environment."""
    manual = (manual or "").strip().lower()

    if manual and manual not in KNOWN:
        return "skip", f"unrecognised manual stage {manual!r}"
    if manual in CALENDAR_FREE:
        return manual, f"manual {manual} — runs regardless of market calendar"
    if manual:
        if not trading:
            return "skip", f"manual {manual} needs a trading day; NYSE closed {now:%Y-%m-%d}"
        return manual, f"manual {manual}"

    if not trading:
        return "skip", f"NYSE closed {now:%Y-%m-%d}"

    mins = now.hour * 60 + now.minute

    if not have_stalk:
        if mins < STALK_CUTOFF:
            if mins < PREP_BEFORE:
                return "prep", "before 09:05 ET and nothing scanned yet"
            late = "" if mins <= STRIKE_FROM else f" (late by {mins - STRIKE_FROM}m — cron drift)"
            return "stalk", f"no stalk list for today yet{late}"
        return "skip", f"no stalk list and it is {now:%H:%M} ET — too late to be useful"

    if not have_strike:
        if mins < STRIKE_FROM:
            return "skip", "stalk done; waiting for the 09:45 ET candle"
        if mins < STRIKE_CUTOFF:
            late = "" if mins <= 10 * 60 + 6 else f" (late by {mins - (10*60+6)}m — cron drift)"
            return "strike", f"stalk done, strike outstanding{late}"
        return "skip", f"strike outstanding but it is {now:%H:%M} ET — too late to be useful"

    return "skip", "stalk and strike both already published today"


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the workflow stage")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    now = datetime.now(ET)
    manual = os.environ.get("MANUAL", "")
    trading, how = _is_trading_day(now)
    hs, hk = _done("stalk", now), _done("strike", now)
    stage, reason = decide(manual, now, trading, hs, hk)

    print(f"::notice::stage={stage} · {reason} · {now:%Y-%m-%d %H:%M:%S %Z} · "
          f"calendar={how} · stalk={'yes' if hs else 'no'} strike={'yes' if hk else 'no'}")

    gh = os.environ.get("GITHUB_OUTPUT")
    if gh and not a.dry_run:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"stage={stage}\n")
    else:
        print(f"stage={stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
