#!/usr/bin/env python3
"""
news.py — Red-herring check for confirmed candidates.

The chart says "the drop found support." News says whether the drop had a
reason that is still live. A stock down 6% on a dilutive offering priced at
$4.00 is not going back to yesterday's range high just because a green candle
printed — that is the red herring hiding in the shadows.

This module only COLLECTS and pre-flags. The judgement call is made by the
model layer (Haiku triages each ticker in parallel, the top-ranked names get
adjudicated by the strong model), which writes ratings into
data/cache/newsrating-YYYY-MM-DD.json for the dashboard to merge.

A deterministic keyword pre-flag runs regardless, so the dashboard degrades
gracefully to something honest if the model step is skipped or fails.

Usage:
    python -m sneak.news --date 2026-08-14 --top 30
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from . import yahoo
from .prep import CACHE_DIR

RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"

# Things that make a bounce untrustworthy. Weighted: hard flags are structural
# and usually permanent repricings; soft flags need a human read.
HARD_FLAGS = {
    "offering": r"\b(public offering|secondary offering|registered direct|priced (an|its) offering|dilut\w+|shelf registration|atm offering)\b",
    "going_concern": r"\b(going concern|bankrupt\w*|chapter 11|delisting|deficiency letter|restat\w+)\b",
    "guidance_cut": r"\b(cuts? (its )?(full[- ]year |fy)?(guidance|outlook|forecast)|lowers? (its )?(guidance|outlook|forecast)|withdraws? (its )?(guidance|outlook))\b",
    "trial_failure": r"\b(fail\w* (to meet|the primary)|missed (the )?primary endpoint|clinical hold|crl\b|complete response letter|halts? (the )?trial)\b",
    "fraud": r"\b(sec (probe|investigation|charges)|doj (probe|investigation)|securities fraud|short[- ]seller report|accounting irregular\w+)\b",
}
SOFT_FLAGS = {
    "earnings": r"\b(q[1-4]|first|second|third|fourth)[- ]quarter\b|\bearnings\b|\bresults\b|\beps\b|\bbeats?\b|\bmisses\b",
    "downgrade": r"\b(downgrade[sd]?|cut to (sell|underweight|underperform)|lowers? price target|slashe[sd] target)\b",
    "litigation": r"\b(lawsuit|class action|litigation|sues?|patent (dispute|ruling))\b",
    "management": r"\b(ceo|cfo) (steps down|resigns|departs|to leave)|\b(resignation|abrupt departure)\b",
    "macro_sector": r"\b(tariff|sector[- ]wide|peers? (fall|slide|drop)|sympathy)\b",
}


def _fetch_rss(sym: str, hours: int = 48) -> list[dict]:
    try:
        r = requests.get(
            RSS.format(sym=sym), timeout=15, headers={"User-Agent": yahoo.UA}
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        pub = it.findtext("pubDate")
        when = None
        if pub:
            try:
                when = parsedate_to_datetime(pub)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except Exception:
                when = None
        if when and when < cutoff:
            continue
        items.append(
            {
                "title": html.unescape(title),
                "summary": html.unescape((it.findtext("description") or "").strip())[:400],
                "link": (it.findtext("link") or "").strip(),
                "published": when.isoformat() if when else None,
            }
        )
    return items[:12]


def _preflag(items: list[dict]) -> dict:
    blob = " ".join(f"{i['title']} {i['summary']}" for i in items).lower()
    hard = [k for k, pat in HARD_FLAGS.items() if re.search(pat, blob, re.I)]
    soft = [k for k, pat in SOFT_FLAGS.items() if re.search(pat, blob, re.I)]
    if hard:
        level = "red"
    elif soft:
        level = "amber"
    elif items:
        level = "green"
    else:
        level = "quiet"
    return {"preflag": level, "hard_flags": hard, "soft_flags": soft}


def run(day: date | None = None, top: int = 30, workers: int = 12) -> dict:
    day = day or yahoo.now_et().date()
    strike_path = CACHE_DIR / f"strike-{day.isoformat()}.json"
    if not strike_path.exists():
        raise SystemExit(f"[news] no strike file for {day}")
    strike = json.loads(strike_path.read_text())
    syms = [r["symbol"] for r in strike["confirmed"][:top]]
    print(f"[news] pulling headlines for top {len(syms)} candidates…", flush=True)

    from concurrent.futures import ThreadPoolExecutor

    def one(sym: str):
        items = _fetch_rss(sym)
        return sym, {"headlines": items, **_preflag(items)}

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for sym, rec in ex.map(one, syms):
            out[sym] = rec

    payload = {
        "session": day.isoformat(),
        "generated_at": datetime.now(yahoo.CT).isoformat(timespec="seconds"),
        "tickers": out,
    }
    p = CACHE_DIR / f"news-{day.isoformat()}.json"
    p.write_text(json.dumps(payload, indent=1))

    counts = {}
    for rec in out.values():
        counts[rec["preflag"]] = counts.get(rec["preflag"], 0) + 1
    print(f"[news] preflags {counts} → {p.name}", flush=True)
    return payload


def load_ratings(day: date) -> dict:
    """Model-written ratings, if the triage step ran."""
    p = CACHE_DIR / f"newsrating-{day.isoformat()}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()).get("tickers", {})
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="News red-herring collector")
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--top", type=int, default=30)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else None
    run(day=day, top=a.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
