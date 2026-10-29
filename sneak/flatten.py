#!/usr/bin/env python3
"""
flatten.py — the cloud backup for the end of the day (stage `flatten`).

cron-job.org starts it at 14:55 CT. The laptop executor normally flattens at
14:50 CT, so on a good day this finds nothing. If the laptop died, it cancels
today's SNEAK orders and closes only the positions those orders opened — never
anything else in the account — and raises the sneak-day alert so you know.

Needs repository secrets ALPACA_KEY_ID and ALPACA_SECRET_KEY (paper keys).
HC_PING_KEY is optional.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time

from .broker_alpaca import PAPER_URL, Alpaca
from .executor import ET, HC_DAY, Pinger


def main() -> int:
    kid, sec = os.environ.get("ALPACA_KEY_ID"), os.environ.get("ALPACA_SECRET_KEY")
    if not kid or not sec:
        print("::notice::flatten: no Alpaca secrets configured — nothing to do")
        return 0
    b = Alpaca(kid, sec, PAPER_URL)
    hc = Pinger(os.environ.get("HC_PING_KEY", ""))
    if not b.clock().get("is_open"):
        print("::notice::flatten: market is closed — orders would queue for tomorrow, so nothing is sent")
        return 0
    today = datetime.now(ET).date()
    prefix = f"sneak-{today.isoformat()}-"
    mine = [o for o in b.orders_since(datetime.combine(today, time(0), ET))
            if str(o.get("client_order_id", "")).startswith(prefix)]
    syms = sorted({o["symbol"] for o in mine})
    for o in mine:
        if o.get("status") not in ("filled", "canceled", "expired", "rejected"):
            b.cancel(o["id"])
    pos = b.positions()
    closed = [s for s in syms if pos.get(s)]
    for s in closed:
        b.close_position(s)
    if closed:
        msg = f"cloud flatten closed {', '.join(closed)} — the laptop did not flatten them"
        print(f"::warning::{msg}")
        hc.ping(HC_DAY, "fail", msg)
    else:
        print(f"::notice::flatten: nothing open from today's {len(syms)} SNEAK symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
