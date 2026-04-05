#!/usr/bin/env python3
"""
market_calendar.py — Shared NYSE market calendar utility for the paper trading simulator.

Uses pandas_market_calendars which contains the official NYSE holiday schedule,
including early-close days (day before Thanksgiving = 1 PM, Christmas Eve / July 4
eve when applicable, etc.).

Usage:
    from market_calendar import is_market_open, is_trading_day, next_trading_day, get_market_hours

    # Quick open/closed check right now
    if not is_market_open():
        sys.exit("Market is closed.")

    # Is a specific date a trading day?
    is_trading_day(date(2026, 1, 19))   # MLK Day → False
    is_trading_day()                     # today

    # Next trading day after a date
    next_trading_day(date(2026, 11, 26))  # Day after Thanksgiving → 2026-11-27

    # Market open/close times (returns timezone-aware datetimes in ET)
    open_dt, close_dt = get_market_hours()

Run as a script to verify today's status:
    python simulator/market_calendar.py
"""

from datetime import date, datetime, timedelta
from typing import Optional, Tuple

import pandas as pd
import pandas_market_calendars as mcal
import pytz

# ---------------------------------------------------------------------------
ET = pytz.timezone("America/New_York")
_NYSE = mcal.get_calendar("NYSE")
# ---------------------------------------------------------------------------


def _schedule_for_range(start: date, end: date) -> pd.DataFrame:
    """Return the NYSE schedule DataFrame for the given date range."""
    return _NYSE.schedule(
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )


def is_trading_day(check_date: Optional[date] = None) -> bool:
    """
    Return True if *check_date* (default: today ET) is a NYSE trading day.

    A day is NOT a trading day if:
      - It falls on a weekend
      - It is an NYSE holiday (including observed holidays)
    """
    if check_date is None:
        check_date = datetime.now(ET).date()

    schedule = _schedule_for_range(check_date, check_date)
    return not schedule.empty


def is_market_open(now: Optional[datetime] = None) -> bool:
    """
    Return True if the NYSE is currently open for regular trading.

    Handles:
      - Weekends
      - NYSE holidays
      - Early-close days (e.g. day before Thanksgiving closes at 1 PM ET,
        Christmas Eve / July 3 early closes when applicable)
    """
    if now is None:
        now = datetime.now(ET)
    elif now.tzinfo is None:
        now = ET.localize(now)

    today = now.date()
    schedule = _schedule_for_range(today, today)

    if schedule.empty:
        return False  # holiday or weekend

    market_open_utc  = schedule.iloc[0]["market_open"]
    market_close_utc = schedule.iloc[0]["market_close"]

    # pandas_market_calendars returns UTC-aware Timestamps
    now_utc = now.astimezone(pytz.utc)
    return pd.Timestamp(now_utc) >= market_open_utc and pd.Timestamp(now_utc) < market_close_utc


def get_market_hours(check_date: Optional[date] = None) -> Tuple[datetime, datetime]:
    """
    Return (market_open_dt, market_close_dt) as timezone-aware datetimes in ET
    for the given trading day.

    Raises ValueError if *check_date* is not a trading day.
    """
    if check_date is None:
        check_date = datetime.now(ET).date()

    schedule = _schedule_for_range(check_date, check_date)
    if schedule.empty:
        raise ValueError(f"{check_date} is not a NYSE trading day.")

    open_utc  = schedule.iloc[0]["market_open"].to_pydatetime()
    close_utc = schedule.iloc[0]["market_close"].to_pydatetime()

    open_et  = open_utc.astimezone(ET)
    close_et = close_utc.astimezone(ET)
    return open_et, close_et


def next_trading_day(after_date: Optional[date] = None) -> date:
    """
    Return the next NYSE trading day strictly after *after_date* (default: today ET).
    """
    if after_date is None:
        after_date = datetime.now(ET).date()

    candidate = after_date + timedelta(days=1)
    # Search up to 14 days ahead (covers any holiday cluster)
    for _ in range(14):
        schedule = _schedule_for_range(candidate, candidate)
        if not schedule.empty:
            return candidate
        candidate += timedelta(days=1)

    raise RuntimeError(f"Could not find next trading day within 14 days of {after_date}")


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    today_et   = datetime.now(ET)
    today_date = today_et.date()

    print(f"NYSE Market Calendar — {today_date.isoformat()} ({today_et.strftime('%A')})")
    print("-" * 55)

    trading = is_trading_day()
    print(f"  is_trading_day()  → {trading}")

    if trading:
        open_dt, close_dt = get_market_hours()
        print(f"  get_market_hours() → open={open_dt.strftime('%H:%M %Z')}  "
              f"close={close_dt.strftime('%H:%M %Z')}")
        open_now = is_market_open()
        print(f"  is_market_open()  → {open_now}")
        if open_now:
            print("  Status: 🟢 Market is OPEN right now")
        else:
            if today_et < open_dt:
                print(f"  Status: 🔵 Market opens at {open_dt.strftime('%H:%M %Z')}")
            else:
                print(f"  Status: 🔴 Market closed at {close_dt.strftime('%H:%M %Z')}")
    else:
        print(f"  is_market_open()  → False  (not a trading day)")
        print("  Status: 🔴 Market CLOSED today (holiday or weekend)")

    nxt = next_trading_day()
    print(f"  next_trading_day() → {nxt.isoformat()}")
    nxt_open, nxt_close = get_market_hours(nxt)
    print(f"  Next session hours → {nxt_open.strftime('%H:%M %Z')} – {nxt_close.strftime('%H:%M %Z')}")
