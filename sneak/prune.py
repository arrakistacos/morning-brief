#!/usr/bin/env python3
"""
prune.py — Drop stale per-session JSON from data/cache.

Age is read from the date in the FILENAME (stalk-2026-08-14.json), never from
the file's modification time. The workflow runs on a fresh checkout, where git
stamps every file with the checkout time — so the old `find -mtime +30` never
matched anything and the cache only ever grew.

newsrating-*.json is kept forever. It is a few KB a day and it is the only
record of what the news gate said live: Yahoo's headline feed cannot be
re-fetched for a past date, so those files are what any future test of the news
gate has to work from.

Usage:
    python -m sneak.prune              # keep 30 days
    python -m sneak.prune --days 45 --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta

from . import yahoo
from .prep import CACHE_DIR

PRUNE_PREFIXES = ("stalk", "strike", "levels", "news")   # not newsrating
_NAME = re.compile(r"^(?P<prefix>[a-z]+)-(?P<day>\d{4}-\d{2}-\d{2})\.json$")


def stale_files(today: date, keep_days: int) -> list:
    cutoff = today - timedelta(days=keep_days)
    out = []
    for p in sorted(CACHE_DIR.glob("*.json")):
        m = _NAME.match(p.name)
        if not m or m["prefix"] not in PRUNE_PREFIXES:
            continue
        try:
            d = date.fromisoformat(m["day"])
        except ValueError:
            continue
        if d < cutoff:
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Prune per-session cache files by filename date")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    files = stale_files(yahoo.now_et().date(), a.days)
    for p in files:
        if not a.dry_run:
            p.unlink()
    print(f"[prune] {'would remove' if a.dry_run else 'removed'} {len(files)} file(s) "
          f"older than {a.days} days", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
