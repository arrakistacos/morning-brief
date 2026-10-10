#!/usr/bin/env python3
"""
stage.py — Decide what this workflow run should do.

The morning is started by hand: Actions → SNEAK → Run workflow → `all` at
~08:55 CT. One job runs prep, the stalk and the strike, sleeping to each candle
close, and publishes once at ~09:01 CT.

Manual stages
-------------
    all, not a trading day                  skip
    all, today already published            skip   (a second click, or a backup
                                                     trigger, is a no-op; use
                                                     `publish` to rebuild the page)
    any stage that would sleep longer        FAIL   (red X straight away rather
      than the job timeout allows                    than a run killed mid-sleep)
    all after 10:15 ET                      run, with a warning: the candle-3
                                             window has closed, so the list is
                                             for the record only
    selftest, prep                          run on any day (no market data)

Scheduled runs
--------------
The workflow has no cron schedule. GitHub's scheduler started this repo's runs
3.5-6 hours late from late August, so a schedule could not hit a 09:00 CT
candle. The scheduled branch of decide() is kept, state-based, in case a
schedule is ever added back:

    scheduled, not a trading day / already published / before 09:00 ET /
    after 12:00 ET                          skip
    scheduled, 09:00-12:00 ET               all

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

BAR1_CLOSE = 9 * 60 + 45      # 09:45 ET — the stalk candle closes (08:45 CT)
BAR2_CLOSE = 10 * 60          # 10:00 ET — the strike candle closes (09:00 CT)
WINDOW_CLOSE = 10 * 60 + 15   # 10:15 ET — the candle-3 buy-stop window closes

# Job timeout is 75 minutes. A stage may not sleep longer than this, leaving
# room for setup and the work after the bar closes.
MAX_SLEEP_MIN = 65
SLEEPS_TO = {"all": BAR2_CLOSE, "strike-publish": BAR2_CLOSE, "strike": BAR2_CLOSE,
             "prep-stalk": BAR1_CLOSE, "stalk": BAR1_CLOSE}

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


def _hhmm(mins: float) -> str:
    m = int(mins)
    return f"{m // 60:02d}:{m % 60:02d}"


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
        mins = now.hour * 60 + now.minute + now.second / 60
        target = SLEEPS_TO.get(manual)
        if target is not None and target - mins > MAX_SLEEP_MIN:
            return "refuse", (f"manual {manual} at {now:%H:%M} ET would sleep "
                              f"{target - mins:.0f}m to the candle — longer than the job "
                              f"timeout allows. Start it after {_hhmm(target - MAX_SLEEP_MIN - 60)} CT.")
        if manual == "all" and have_stalk and have_strike:
            return "skip", ("today is already published — run `publish` to rebuild "
                            "the page, or `strike-publish` to redo the strike")
        if manual == "all" and mins >= WINDOW_CLOSE:
            return "all", (f"manual all at {now:%H:%M} ET — the candle-3 window closed at "
                           "09:15 CT, so today's list is for the record only")
        if target is not None and mins < target:
            return manual, (f"manual {manual} — sleeping {target - mins:.0f}m until the "
                            f"candle closes at {_hhmm(target - 60)} CT")
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

    level = {"refuse": "error"}.get(stage, "warning" if "for the record" in reason else "notice")
    print(f"::{level}::stage={stage} · {reason} · {now:%Y-%m-%d %H:%M:%S %Z} · "
          f"calendar={how} · stalk={'yes' if hs else 'no'} strike={'yes' if hk else 'no'}"
          f"{' · cron=' + sched if sched else ''}")

    # A refused start writes `skip` so no later step runs, and exits non-zero so
    # the run goes red immediately instead of dying at the timeout.
    out = "skip" if stage == "refuse" else stage
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh and not a.dry_run:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"stage={out}\n")
    else:
        print(f"stage={out}")
    return 1 if stage == "refuse" else 0


if __name__ == "__main__":
    sys.exit(main())
