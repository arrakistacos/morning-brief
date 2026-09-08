#!/usr/bin/env python3
"""
stage.py — Decide what this workflow firing should do.

There is exactly one scheduled behaviour: run the whole morning in one pass.
prep, stalk and strike execute inside a single job, so a firing either does the
entire day or does nothing. No state is handed between runs.

Why a band of firings for a single behaviour
--------------------------------------------
GitHub's measured launch delay on this repo is 42-46 minutes, every day. A lone
cron at 08:55 CT would therefore start around 09:40 CT and publish ~40 minutes
late, and one dropped firing would mean no lists at all that day.

So the same rule is offered several chances. Crons fire across 09:00-09:55 ET;
whichever arrives first while the day is still unpublished runs `all`, and the
rest find the work done and skip. A firing that lands BEFORE the 10:00 ET strike
candle closes is the good case — the scanner sleeps and reads the tape the
instant the bar settles, publishing at ~09:01 CT. One that lands after is simply
late, not broken.

Arming cannot start before 09:00 ET: sleeping to 10:00:25 plus setup has to fit
inside the workflow's 75-minute timeout.

    scheduled, not a trading day        skip
    scheduled, both lists published     skip
    scheduled, before 09:00 ET          skip   (would outlive the timeout)
    scheduled, 09:00-12:00 ET           ALL    (sleeps to the candles if early)
    scheduled, after 12:00 ET           skip   (too stale to be useful)

Manual dispatch still reaches every individual stage for debugging; selftest and
prep need no market data, so they ignore the calendar.

Usage:
    python -m sneak.stage            # reads MANUAL env, writes $GITHUB_OUTPUT
    python -m sneak.stage --dry-run  # print the decision only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CACHE = Path(__file__).resolve().parent.parent / "data" / "cache"

# selftest and prep touch no market data, so they run any day.
CALENDAR_FREE = {"selftest", "prep"}
# Manual-only stages. A scheduled firing never resolves to any of these — it
# resolves to `all` or to `skip`, nothing else.
KNOWN = {"selftest", "prep", "stalk", "strike", "publish", "all",
         "prep-stalk", "strike-publish"}

BAR2_CLOSE = 10 * 60          # 10:00 ET — the strike candle closes (09:00 CT)

# Earliest a runner may arm. Sleeping from here to 10:00:25 ET is ~60 minutes,
# which fits the workflow's 75-minute timeout with room for setup.
ALL_ARM = 9 * 60              # 09:00 ET
ALL_CUTOFF = 12 * 60          # 12:00 ET — past this the morning is a write-off


def _is_trading_day(now: datetime) -> tuple[bool, str]:
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from market_calendar import is_trading_day  # type: ignore

        return bool(is_trading_day(now.date())), "nyse-calendar"
    except Exception as e:  # pragma: no cover
        print(f"::warning::NYSE calendar unavailable ({e}); falling back to weekday check")
        return now.weekday() < 5, "weekday-fallback"


def _firing_schedule() -> str:
    """Which cron launched this run, or "" for a manual dispatch. Diagnostics only."""
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            return str(json.load(f).get("schedule") or "").strip()
    except Exception:
        return ""


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
    if have_stalk and have_strike:
        return "skip", "already published today"

    mins = now.hour * 60 + now.minute
    if mins < ALL_ARM:
        return "skip", "before 09:00 ET — arming now would outlive the job timeout"
    if mins >= ALL_CUTOFF:
        return "skip", f"it is {now:%H:%M} ET — too late for today's open to matter"

    if mins <= BAR2_CLOSE:
        return "all", (f"whole morning in one pass — armed, sleeping "
                       f"{BAR2_CLOSE - mins}m to the 10:00 ET candle")
    return "all", f"whole morning in one pass (late by {mins - BAR2_CLOSE}m — cron drift)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the workflow stage")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    now = datetime.now(ET)
    manual = os.environ.get("MANUAL", "")
    trading, how = _is_trading_day(now)
    hs, hk = _done("stalk", now), _done("strike", now)
    sched = _firing_schedule()
    stage, reason = decide(manual, now, trading, hs, hk)

    print(f"::notice::stage={stage} · {reason} · {now:%Y-%m-%d %H:%M:%S %Z} · "
          f"calendar={how} · stalk={'yes' if hs else 'no'} strike={'yes' if hk else 'no'}"
          f"{' · cron=' + sched if sched else ''}")

    gh = os.environ.get("GITHUB_OUTPUT")
    if gh and not a.dry_run:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"stage={stage}\n")
    else:
        print(f"stage={stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
