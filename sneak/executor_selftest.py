"""
executor_selftest.py — run the executor through scripted trading days against a
fake broker. No network, no keys, ~2 seconds.

    python -m sneak.executor selftest

Each scenario is one symbol with a price path (ET time -> price). The fake
broker fills a buy-stop when price reaches it, works OCO exits (limit first if
both touch, like the backtest's ordering on a rising path), and closes positions
at the last price. The test asserts the executor's outcome, shares and P&L.
"""

from __future__ import annotations

import itertools
import tempfile
from pathlib import Path
from datetime import date, datetime, time, timedelta

from . import executor as ex
from .broker_alpaca import BrokerError

ET = ex.ET
DAY = date(2026, 11, 2)       # a Monday


def T(hh, mm, ss=0):
    return datetime.combine(DAY, time(hh, mm, ss), ET)


class Clock:
    def __init__(self, start, on_tick):
        self.t, self.on_tick = start, on_tick

    def now(self):
        return self.t

    def sleep(self, s):
        end = self.t + timedelta(seconds=s)
        while self.t < end:
            self.t = min(end, self.t + timedelta(seconds=1))
            self.on_tick(self.t)


class FakeBroker:
    def __init__(self, paths: dict[str, list[tuple[datetime, float]]], partial: set[str] = frozenset()):
        self.paths = paths
        self.partial = set(partial)
        self.orders: dict[str, dict] = {}
        self.pos: dict[str, float] = {}
        self.fill_log: list[dict] = []
        self.lows: dict[str, float] = {}
        self.last: dict[str, float] = {}
        self.ids = itertools.count(1)
        self.calls = 0

    # price feed
    def price(self, sym, t):
        p = None
        for when, px in self.paths[sym]:
            if when <= t:
                p = px
        return p

    def tick(self, t):
        for sym in self.paths:
            p = self.price(sym, t)
            if p is None:
                continue
            self.last[sym] = p
            if t >= T(10, 0):
                self.lows[sym] = min(self.lows.get(sym, p), p)
            self._match(sym, p)

    def _fill(self, o, qty, px):
        o["filled_qty"] = str(int(float(o.get("filled_qty") or 0)) + qty)
        o["filled_avg_price"] = str(px)
        o["status"] = "filled" if int(o["filled_qty"]) >= int(o["qty"]) else "partially_filled"
        sign = 1 if o["side"] == "buy" else -1
        self.pos[o["symbol"]] = self.pos.get(o["symbol"], 0) + sign * qty
        if not self.pos[o["symbol"]]:
            del self.pos[o["symbol"]]
        self.fill_log.append({"symbol": o["symbol"], "side": o["side"], "qty": qty, "price": px})

    def _match(self, sym, p):
        for o in list(self.orders.values()):
            if o["symbol"] != sym or o["status"] not in ("new", "partially_filled"):
                continue
            if o["side"] == "buy" and o["type"] == "stop" and p >= float(o["stop_price"]):
                q = int(o["qty"]) - int(float(o.get("filled_qty") or 0))
                if sym in self.partial:
                    q = max(1, q // 2)
                    self.partial.discard(sym)
                self._fill(o, q, p)
            elif o.get("order_class") == "oco":
                leg = o["legs"][0]
                if p >= float(o["limit_price"]):
                    self._fill(o, int(o["qty"]), float(o["limit_price"]))
                    leg["status"] = "canceled"
                elif p <= float(leg["stop_price"]):
                    self._fill(leg, int(leg["qty"]), p)
                    o["status"] = "canceled"

    # the Alpaca surface the executor uses
    def account(self):
        return {"status": "ACTIVE", "trading_blocked": False, "buying_power": "100000", "cash": "100000"}

    def clock(self):
        return {"timestamp": "", "is_open": True}

    def calendar(self, day):
        return {"date": day.isoformat(), "open": "09:30", "close": "16:00"}

    def submit(self, order):
        self.calls += 1
        if any(o["client_order_id"] == order["client_order_id"] for o in self.orders.values()):
            raise BrokerError(422, "client_order_id must be unique")
        oid = f"o{next(self.ids)}"
        o = {"id": oid, "status": "new", "filled_qty": "0", "filled_avg_price": None,
             "symbol": order["symbol"], "side": order["side"], "qty": order["qty"],
             "type": order["type"], "client_order_id": order["client_order_id"],
             "order_class": order.get("order_class", "simple"), "legs": []}
        if order["type"] == "stop":
            o["stop_price"] = order["stop_price"]
        if order.get("order_class") == "oco":
            held = sum(int(x["qty"]) for x in self.orders.values()
                       if x["symbol"] == order["symbol"] and x["side"] == "sell"
                       and x["status"] in ("new", "partially_filled"))
            if held + int(order["qty"]) > self.pos.get(order["symbol"], 0):
                raise BrokerError(403, "insufficient qty available for order")
            o["limit_price"] = order["take_profit"]["limit_price"]
            o["legs"] = [{"id": oid + "s", "status": "new", "type": "stop", "side": "sell",
                          "symbol": order["symbol"], "qty": order["qty"], "filled_qty": "0",
                          "stop_price": order["stop_loss"]["stop_price"]}]
        self.orders[oid] = o
        self._match(o["symbol"], self.last.get(o["symbol"], 0) or 0) if o["side"] == "sell" else None
        return o

    def order_by_client_id(self, cid):
        return next((o for o in self.orders.values() if o["client_order_id"] == cid), None)

    def orders_since(self, after):
        return list(self.orders.values())

    def cancel(self, oid):
        o = self.orders.get(oid)
        if o and o["status"] in ("new", "partially_filled"):
            o["status"] = "canceled"
            for leg in o.get("legs") or []:
                if leg["status"] == "new":
                    leg["status"] = "canceled"

    def positions(self):
        return dict(self.pos)

    def close_position(self, sym):
        q = int(self.pos.get(sym, 0))
        if q:
            o = {"id": f"o{next(self.ids)}", "symbol": sym, "side": "sell", "qty": str(q),
                 "type": "market", "status": "new", "filled_qty": "0", "client_order_id": f"close-{sym}"}
            self.orders[o["id"]] = o
            self._fill(o, q, self.last[sym])

    def fills(self, day):
        return list(self.fill_log)

    def low_since(self, sym, start):
        return self.lows.get(sym)


class FakeFeed:
    authed = False

    def __init__(self, rows):
        self.rows = rows

    def orders(self):
        return {"session": DAY.isoformat(), "strike_done": True, "published_after_window": False,
                "orders": self.rows}

    def killed(self):
        return False


def row(sym, trig, stop, t1, t2, mult=1.0):
    return {"symbol": sym, "trigger": trig, "stop": stop, "target1": t1, "target2": t2,
            "scale_out": 0.5, "risk_mult": mult}


# Every scenario: trigger 10.00, stop 9.50 (risk 0.50), T1 10.20, T2 10.60.
SCENARIOS = {
    # sym: (path, expected outcome, expected R sign or value check)
    "WIN2": ([(T(9, 59), 9.9), (T(10, 3), 10.0), (T(10, 20), 10.25), (T(11, 0), 10.65)],
             "target 1 + target 2"),
    "BEVN": ([(T(9, 59), 9.9), (T(10, 3), 10.0), (T(10, 20), 10.25), (T(11, 0), 9.99)],
             "target 1 + break-even"),
    "STOP": ([(T(9, 59), 9.9), (T(10, 3), 10.0), (T(10, 30), 9.49)],
             "stopped out"),
    "THRU": ([(T(9, 59), 9.9), (T(10, 4), 9.45), (T(10, 10), 10.05)],
             "traded below the stop first"),
    "NOFL": ([(T(9, 59), 9.9), (T(10, 20), 10.05)],
             "no fill by 09:15 CT"),
    "FLAT": ([(T(9, 59), 9.9), (T(10, 3), 10.0), (T(10, 30), 10.1)],
             "flat at close"),
    "HALF": ([(T(9, 59), 9.9), (T(10, 3), 10.0), (T(10, 20), 10.25), (T(11, 0), 10.65)],
             "target 1 + target 2"),
}


def main() -> int:
    ex.JOURNAL = Path(tempfile.mkdtemp()) / "journal.csv"   # never touch the real journal
    rows = [row(s, 10.00, 9.50, 10.20, 10.60) for s in SCENARIOS]
    paths = {s: p for s, (p, _) in SCENARIOS.items()}
    broker = FakeBroker(paths, partial={"HALF"})
    clock = Clock(T(8, 30), broker.tick)
    cfg = dict(ex.DEFAULTS, mode="paper", cash=100000.0, base_risk_pct=0.5, max_entries=10)
    e = ex.Executor(cfg, broker, FakeFeed(rows), ex.Pinger(""), now=clock.now,
                    sleep=clock.sleep, heartbeat=False)
    rc = e.run()
    pnl = e.pnl_by_symbol()
    failures = []
    for t in e.trades:
        want = SCENARIOS[t.symbol][1]
        r = pnl.get(t.symbol, 0) / (t.risk_per_share * t.filled) if t.filled else 0.0
        ok = t.outcome == want
        print(f"  {'ok ' if ok else 'BAD'} {t.symbol:5s} filled {t.filled:4d}  {t.outcome:28s} "
              f"{r:+.2f}R" + ("" if ok else f"   (wanted: {want})"))
        if not ok:
            failures.append(t.symbol)
    if broker.pos:
        failures.append(f"positions left open: {broker.pos}")
    stray = [o for o in broker.orders.values() if o["status"] in ("new", "partially_filled")]
    if stray:
        failures.append(f"orders left open: {[o['client_order_id'] for o in stray]}")
    # restart safety: a second executor the same day must adopt, not double-place
    before = broker.calls
    e2 = ex.Executor(cfg, broker, FakeFeed(rows), ex.Pinger(""), now=clock.now,
                     sleep=clock.sleep, heartbeat=False)
    e2.place_entries(FakeFeed(rows).orders())
    if broker.calls != before:
        failures.append("restart placed new entries instead of adopting")
    print(f"\nselftest {'PASSED' if not failures and rc == 0 else 'FAILED: ' + str(failures)}")
    return 0 if not failures and rc == 0 else 1
