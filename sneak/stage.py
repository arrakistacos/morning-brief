#!/usr/bin/env python3
"""
stage.py — Decide which stage this workflow firing should run.

Lives here rather than inline in the YAML for two reasons: workflow files are
awkward to edit remotely, and shell-heredoc Python has a nasty failure mode —
anything printed to stdout lands in $GITHUB_OUTPUT when the step redirects,
so a single ``::notice::`` line corrupts the output file and fails the step.
Here the output file is written explicitly and stdout stays free for notices.

Stage selection
---------------
A manual dispatch wins over the calendar for the stages where that is sensible:

    selftest   always runs — its whole purpose is checking credentials, which
               has nothing to do with whether the market is open
    prep       always runs — levels come from the last COMPLETED session, so it
               is valid (and useful) on a weekend
    stalk      needs a trading day: there are no candles otherwise
    strike     needs a trading day
    all        needs a trading day

A scheduled firing always needs a trading day, and picks its stage from the ET
wall clock rather than from the cron string, so DST is handled by the calendar:

    before 09:05 ET   prep
    09:05 – 09:45     stalk    (scan_open then sleeps until 09:45:25)
    09:45 – 10:06     strike   (confirm then sleeps until 10:00:25)
    otherwise         skip

Usage:
    python -m sneak.stage            # reads MANUAL env, writes $GITHUB_OUTPUT
    python -m sneak.stage --dry-run  # print the decision only
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Manual stages that do not require the market to be open.
CALENDAR_FREE = {"selftest", "prep"}
KNOWN = {"selftest", "prep", "stalk", "strike", "publish", "all"}


def _is_trading_day(now: datetime) -> tuple[bool, str]:
    """(is_trading_day, how_we_decided). Falls back to weekday if the calendar is unavailable."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from market_calendar import is_trading_day  # type: ignore

        return bool(is_trading_day(now.date())), "nyse-calendar"
    except Exception as e:  # pragma: no cover - only on a broken install
        print(f"::warning::NYSE calendar unavailable ({e}); falling back to weekday check")
        return now.weekday() < 5, "weekday-fallback"


def decide(manual: str, now: datetime, trading: bool) -> tuple[str, str]:
    """Return (stage, human_reason). Pure — unit-testable without a runner."""
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
    if mins < 9 * 60 + 5:
        return "prep", "scheduled firing before 09:05 ET"
    if mins < 9 * 60 + 45:
        return "stalk", "scheduled firing in the 09:05–09:45 ET window"
    if mins < 10 * 60 + 6:
        return "strike", "scheduled firing in the 09:45–10:06 ET window"
    return "skip", f"fired at {now:%H:%M} ET — outside every stage window"


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve the workflow stage")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write GITHUB_OUTPUT")
    a = ap.parse_args()

    now = datetime.now(ET)
    manual = os.environ.get("MANUAL", "")
    trading, how = _is_trading_day(now)
    stage, reason = decide(manual, now, trading)

    # Notices go to stdout. The output file is written explicitly, so stdout is
    # never mistaken for it.
    print(f"::notice::stage={stage} · {reason} · {now:%Y-%m-%d %H:%M:%S %Z} · calendar={how}")

    gh = os.environ.get("GITHUB_OUTPUT")
    if gh and not a.dry_run:
        with open(gh, "a", encoding="utf-8") as f:
            f.write(f"stage={stage}\n")
    else:
        print(f"stage={stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
