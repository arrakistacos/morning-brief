#!/usr/bin/env python3
"""
executor.py — trades the morning's published orders. Runs on the laptop.

Task Scheduler starts it at ~08:30 CT on weekdays. It does exactly what the
dashboard says and makes no trading decisions of its own:

    09:50 ET  backup start: if no SNEAK run began in the last 15 minutes, start one
    10:00 ET  poll docs/orders.json (GitHub API) until today's list is published
              place a DAY buy-stop per row, sized like the dashboard's sizer
    -10:15    cancel an entry if price trades at/below its stop first; cancel all
              unfilled entries at 10:15:00 ET
    on fill   two OCO exits on the filled shares: the larger half at target 1,
              the rest at target 2, both with the red-candle stop
    T1 fills  cancel the target-2 exit and re-place it with the stop at the entry
    close-10  cancel everything, sell what is left at market
    close+1   journal the day, last heartbeat, exit

Modes (config "mode"): dry = read-only, logs what it would place · paper =
Alpaca paper account · live = refused until a Schwab adapter exists.

Every order carries a dated client id, sneak-YYYY-MM-DD-SYM-leg. A restart
adopts orders it already placed instead of placing them twice.

Commands:
    python -m sneak.executor setup      # one-time: config + keys (Windows Credential Manager)
    python -m sneak.executor check      # verify keys, GitHub feed and heartbeats
    python -m sneak.executor run        # the trading day (Task Scheduler runs this)
    python -m sneak.executor selftest   # replay scripted days against a fake broker
"""

from __future__ import annotations

import argparse
import csv
import getpass
import json
import logging
import math
import sys
import threading
import time as _time
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

HOME = Path.home() / ".sneak"
CONFIG = HOME / "config.json"
LOGS = HOME / "logs"
JOURNAL = HOME / "journal.csv"
KILL_FILE = HOME / "KILL"

KEYRING_ALPACA = "sneak-alpaca-paper"
KEYRING_GITHUB = "sneak-github"

DEFAULTS = {
    "mode": "dry",               # dry | paper | live
    "cash": 5000.0,              # what the sizer may commit, like the dashboard's "Cash today"
    "base_risk_pct": 1.0,        # % of cash risked on a Normal-tier trade
    "max_entries": 5,
    "max_daily_loss_r": 3.0,     # realised loss in R that stops the day
    "hc_ping_key": "",           # Healthchecks.io project ping key
    "repo": "arrakistacos/morning-brief",
}

BACKUP_DISPATCH = time(9, 50)    # ET (08:50 CT)
WINDOW_OPEN = time(10, 0)
POLL_FROM = time(10, 0, 20)
WINDOW_END = time(10, 15)
LAST_POLL = time(10, 14, 30)
FLATTEN_BEFORE_CLOSE = timedelta(minutes=10)
STOP_CHECK_EVERY = 15            # seconds between stop-through checks per entry

HC_SCAN, HC_LAPTOP, HC_ORDERS, HC_DAY = "sneak-scan", "sneak-laptop", "sneak-orders", "sneak-day"

log = logging.getLogger("sneak.executor")


# ── config and secrets ───────────────────────────────────────────────────────

def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text()))
    return cfg


def _secret(name: str, user: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(name, user)
    except Exception:
        return None


def alpaca_keys() -> tuple[str | None, str | None]:
    return _secret(KEYRING_ALPACA, "key_id"), _secret(KEYRING_ALPACA, "secret")


def github_token() -> str | None:
    return _secret(KEYRING_GITHUB, "token")


# ── prices ───────────────────────────────────────────────────────────────────

def cents(x: float) -> float:
    return round(x + 1e-9, 2)


def floor_cents(x: float) -> float:
    return math.floor(round(x, 6) * 100 + 1e-6) / 100


# ── heartbeats ───────────────────────────────────────────────────────────────

class Pinger:
    """Healthchecks.io pings by slug. Never raises: monitoring must not stop trading."""

    def __init__(self, key: str):
        self.key = key
        self.sent: list[tuple[str, str, str]] = []

    def ping(self, slug: str, kind: str = "", msg: str = "") -> None:
        self.sent.append((slug, kind, msg))
        if not self.key:
            return
        url = f"https://hc-ping.com/{self.key}/{slug}" + (f"/{kind}" if kind else "")
        try:
            requests.post(url, data=msg.encode()[:10_000], timeout=10)
        except Exception as e:
            log.warning("heartbeat %s/%s failed: %s", slug, kind, e)


# ── the GitHub side: orders feed, kill switch, backup start ──────────────────

class Feed:
    def __init__(self, repo: str, token: str | None):
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        self.authed = bool(token)

    def _file(self, path: str) -> dict | None:
        r = self.s.get(f"https://api.github.com/repos/{self.repo}/contents/{path}",
                       params={"ref": "main"},
                       headers={"Accept": "application/vnd.github.raw+json"}, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def orders(self) -> dict | None:
        return self._file("docs/orders.json")

    def killed(self) -> bool:
        try:
            k = self._file("control/kill.json")
        except Exception:
            return False
        return bool(k and k.get("kill"))

    def run_started_since(self, since: datetime) -> bool:
        r = self.s.get(f"https://api.github.com/repos/{self.repo}/actions/workflows/sneak.yml/runs",
                       params={"created": f">={since.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}",
                               "per_page": 5}, timeout=10)
        r.raise_for_status()
        return r.json().get("total_count", 0) > 0

    def dispatch(self) -> None:
        r = self.s.post(f"https://api.github.com/repos/{self.repo}/actions/workflows/sneak.yml/dispatches",
                        json={"ref": "main", "inputs": {"stage": "all"}}, timeout=10)
        r.raise_for_status()


# ── sizing — the dashboard's sizer, in Python ────────────────────────────────

def size_orders(rows: list[dict], cash: float, base_risk_pct: float,
                max_entries: int, buying_power: float | None = None) -> list[dict]:
    """
    Each row risks cash x base% x its tier multiplier; shares = risk / (trigger - stop).
    If the rows together need more than the cash, all shrink by one factor so the
    tier ratio holds and the total fits — the same rule as the page.
    """
    cap = min(cash, buying_power) if buying_power else cash
    rows = rows[:max_entries]
    raw = []
    for r in rows:
        per = r["trigger"] - r["stop"]
        raw.append(cash * base_risk_pct / 100 * r.get("risk_mult", 1.0) / per if per > 0 else 0)
    need = sum(sh * r["trigger"] for sh, r in zip(raw, rows))
    k = cap / need if need > cap else 1.0
    out = []
    for sh, r in zip(raw, rows):
        q = int(math.floor(sh * k))
        if q <= 0:
            continue
        out.append({**r, "qty": q})
    return out


def split_qty(qty: int, scale_out: float) -> tuple[int, int]:
    """Target-1 shares get the larger half; a single share goes to target 1."""
    if scale_out >= 1 or qty <= 1:
        return qty, 0
    s1 = int(math.ceil(qty * scale_out))
    return s1, qty - s1


# ── one trade's life ─────────────────────────────────────────────────────────

@dataclass
class Trade:
    symbol: str
    trigger: float
    stop: float
    target1: float
    target2: float | None
    scale_out: float
    qty: int
    state: str = "planned"        # planned entry cancelling exits be_cancelling done skipped
    entry_id: str | None = None
    filled: int = 0
    entry_px: float | None = None
    a_id: str | None = None
    b_id: str | None = None
    be_done: bool = False
    t1_hit: bool = False
    outcome: str = ""
    last_stop_check: float = -1e9
    notes: list[str] = field(default_factory=list)

    @property
    def risk_per_share(self) -> float:
        return (self.entry_px or self.trigger) - self.stop


class Executor:
    def __init__(self, cfg: dict, broker, feed: Feed, pinger: Pinger,
                 now=lambda: datetime.now(ET), sleep=_time.sleep, heartbeat: bool = True):
        self.cfg, self.broker, self.feed, self.hc = cfg, broker, feed, pinger
        self.now, self.sleep = now, sleep
        self.mode = cfg["mode"]
        self.day = self.now().date()
        self.prefix = f"sneak-{self.day.isoformat()}-"
        self.trades: list[Trade] = []
        self.status = "starting"
        self.no_new_entries = False
        self._hb = heartbeat
        self._hb_stop = threading.Event()

    # ── small helpers ───────────────────────────────────────────────────────
    def at(self, t: time) -> datetime:
        return datetime.combine(self.day, t, ET)

    def cid(self, sym: str, leg: str) -> str:
        return f"{self.prefix}{sym}-{leg}"

    def wait_until(self, when: datetime) -> None:
        while self.now() < when:
            self.sleep(min(30.0, max(0.5, (when - self.now()).total_seconds())))

    def say(self, msg: str) -> None:
        self.status = msg
        log.info(msg)

    def killed(self) -> bool:
        return KILL_FILE.exists() or self.feed.killed()

    def _heartbeat(self) -> None:
        while not self._hb_stop.wait(60):
            self.hc.ping(HC_LAPTOP, msg=f"{self.mode}: {self.status}")

    # ── the day ─────────────────────────────────────────────────────────────
    def run(self) -> int:
        if self._hb:
            self.hc.ping(HC_LAPTOP, msg=f"{self.mode}: executor started")
            threading.Thread(target=self._heartbeat, daemon=True).start()
        try:
            return self._run()
        except Exception:
            tb = traceback.format_exc()
            log.error(tb)
            self.hc.ping(HC_ORDERS, "fail", f"executor crashed:\n{tb[-3000:]}")
            self.hc.ping(HC_DAY, "fail", f"executor crashed — check the broker:\n{tb[-3000:]}")
            return 1
        finally:
            self._hb_stop.set()

    def _run(self) -> int:
        cal = self.broker.calendar(self.day)
        if not cal:
            self.say(f"{self.day} is not a trading day — idling so the heartbeats stay green")
            self.wait_until(self.at(time(10, 1)))      # pings land inside each check's window
            self.hc.ping(HC_ORDERS, msg="market closed today")
            self.wait_until(self.at(time(16, 1)))
            self.hc.ping(HC_DAY, msg="market closed today")
            return 0
        close = datetime.combine(self.day, time.fromisoformat(cal["close"]), ET)
        flatten_at = close - FLATTEN_BEFORE_CLOSE

        problems = self.preflight()
        if problems:
            self.no_new_entries = True
            self.hc.ping(HC_ORDERS, "fail", "no new entries today:\n- " + "\n- ".join(problems))
            log.warning("preflight: %s", problems)

        if self.now() < self.at(WINDOW_OPEN):
            self.wait_until(self.at(BACKUP_DISPATCH))
            self.backup_start()
        self.wait_until(self.at(POLL_FROM))

        feed = self.wait_for_orders()
        self.place_entries(feed)
        if not problems:
            self.hc.ping(HC_ORDERS, msg=self.summary_line("orders"))

        if self.mode != "dry":
            self.manage(flatten_at)
        self.wait_until(close + timedelta(minutes=1))
        self.journal()
        # On a half day the close is 13:00 ET; the sneak-day check expects its
        # ping after 15:00 CT, so hold the last ping until then.
        self.say("journal written · " + self.summary_line("day"))
        self.wait_until(max(close + timedelta(minutes=1), self.at(time(16, 1))))
        self.hc.ping(HC_DAY, msg=self.summary_line("day"))
        self.say("day done")
        return 0

    def preflight(self) -> list[str]:
        p = []
        if self.mode == "live":
            p.append("live mode has no broker adapter yet — set mode to paper or dry")
        try:
            acct = self.broker.account()
            if acct.get("status") != "ACTIVE" or acct.get("trading_blocked"):
                p.append(f"account not tradable: status={acct.get('status')}")
        except Exception as e:
            p.append(f"broker unreachable: {e}")
            return p
        mine = {o["symbol"] for o in self.broker.orders_since(self.at(time(0)))
                if str(o.get("client_order_id", "")).startswith(self.prefix)}
        stray = [s for s, q in self.broker.positions().items() if q and s not in mine]
        if stray:
            p.append(f"account not flat: open positions in {', '.join(stray)}")
        if self.killed():
            p.append("kill switch is on")
        try:
            ts = str(self.broker.clock().get("timestamp", ""))
            head, _, tail = ts.partition(".")
            tz = tail[-6:] if tail and tail[-6] in "+-" else ""
            broker_now = datetime.fromisoformat(head + tz) if ts else None
            if broker_now is not None:
                skew = abs((broker_now - self.now()).total_seconds())
                if skew > 5:
                    p.append(f"this computer's clock is off by {skew:.0f}s — sync it in Windows settings")
        except Exception as e:
            log.warning("clock check skipped: %s", e)
        return p

    def backup_start(self) -> None:
        if not self.feed.authed:
            return
        try:
            if self.feed.run_started_since(self.now() - timedelta(minutes=15)):
                self.say("scan run already started — no backup needed")
                return
            self.feed.dispatch()
            self.say("no scan run had started — dispatched the backup start")
            self.hc.ping(HC_SCAN, "log", "laptop dispatched the backup start at 08:50 CT")
        except Exception as e:
            log.warning("backup start failed: %s", e)

    def wait_for_orders(self) -> dict | None:
        deadline = self.at(LAST_POLL)
        while True:
            try:
                f = self.feed.orders()
            except Exception as e:
                f = None
                log.warning("orders feed: %s", e)
            if f and f.get("session") == self.day.isoformat() and f.get("strike_done"):
                return f
            if self.now() >= deadline:
                self.say("no orders published for today by 09:14:30 CT")
                return None
            # Unauthenticated GitHub API calls are capped at 60 an hour.
            self.sleep(10 if self.feed.authed else 30)

    # ── entries ─────────────────────────────────────────────────────────────
    def place_entries(self, feed: dict | None) -> None:
        rows = (feed or {}).get("orders") or []
        if feed and feed.get("published_after_window"):
            self.say("today's list was published after the entry window — nothing to place")
            rows = []
        if not rows:
            self.say("no orders today")
            return
        try:
            bp = float(self.broker.account().get("buying_power") or 0) or None
        except Exception:
            bp = None
        sized = size_orders(rows, float(self.cfg["cash"]), float(self.cfg["base_risk_pct"]),
                            int(self.cfg["max_entries"]), bp)
        late = self.now() >= self.at(WINDOW_END)
        for r in sized:
            t = Trade(r["symbol"], cents(r["trigger"]), floor_cents(r["stop"]), cents(r["target1"]),
                      cents(r["target2"]) if r.get("target2") else None,
                      float(r.get("scale_out") or 1.0), int(r["qty"]))
            self.trades.append(t)
            existing = self.broker.order_by_client_id(self.cid(t.symbol, "entry")) if self.mode != "dry" else None
            if existing:
                t.entry_id, t.state = existing["id"], "entry"
                self.say(f"{t.symbol}: adopted the entry placed earlier")
                continue
            if self.mode == "dry":
                s1, s2 = split_qty(t.qty, t.scale_out)
                t.state, t.outcome = "done", "dry run"
                self.say(f"DRY {t.symbol}: buy-stop {t.qty} @ {t.trigger}, stop {t.stop}, "
                         f"T1 {t.target1} x{s1}, T2 {t.target2} x{s2}")
                continue
            if late or self.no_new_entries:
                t.state, t.outcome = "skipped", "window closed" if late else "blocked by preflight"
                continue
            try:
                o = self.broker.submit({"symbol": t.symbol, "qty": str(t.qty), "side": "buy",
                                        "type": "stop", "stop_price": str(t.trigger),
                                        "time_in_force": "day",
                                        "client_order_id": self.cid(t.symbol, "entry")})
                t.entry_id, t.state = o["id"], "entry"
                self.say(f"{t.symbol}: buy-stop {t.qty} @ {t.trigger} placed")
            except Exception as e:
                t.state, t.outcome = "skipped", f"entry rejected: {e}"
                log.warning("%s entry rejected: %s", t.symbol, e)

    # ── management loop ─────────────────────────────────────────────────────
    def manage(self, flatten_at: datetime) -> None:
        start = self.at(time(0))
        last_kill = last_r = -1e9
        while True:
            now = self.now()
            live = [t for t in self.trades if t.state not in ("done", "skipped")]
            if not live:
                return
            if now >= flatten_at:
                self.flatten(live, "flat at close")
                return
            try:
                orders = self.broker.orders_since(start)
                pos = self.broker.positions()
            except Exception as e:
                log.warning("broker poll failed: %s", e)
                self.sleep(5)
                continue
            idx = {}
            for o in orders:
                idx[o["id"]] = o
                for leg in o.get("legs") or []:
                    idx[leg["id"]] = leg
            stamp = now.timestamp()
            if stamp - last_kill > 60:
                last_kill = stamp
                if self.killed():
                    self.no_new_entries = True
                    for t in live:
                        if t.state == "entry" and not t.filled:
                            self.broker.cancel(t.entry_id)
                            t.state, t.outcome = "cancelling", "kill switch"
            for t in live:
                try:
                    self.step(t, now, idx, pos)
                except Exception as e:
                    log.warning("%s step failed: %s", t.symbol, e)
            if stamp - last_r > 30 and any(t.state == "done" and t.filled for t in self.trades):
                last_r = stamp
                r_now = self.realised_r()
            else:
                r_now = 0.0
            if r_now <= -float(self.cfg["max_daily_loss_r"]):
                self.say("daily loss limit reached — flattening")
                self.flatten([t for t in self.trades if t.state not in ("done", "skipped")],
                             "daily loss limit")
                return
            self.sleep(2 if now < self.at(WINDOW_END) else 5)

    def step(self, t: Trade, now: datetime, idx: dict, pos: dict) -> None:
        if t.state == "entry":
            o = idx.get(t.entry_id) or {}
            filled = int(float(o.get("filled_qty") or 0))
            st = o.get("status")
            if st == "filled":
                self.on_filled(t, o)
            elif filled > 0:
                # A partial fill: stop buying and protect what we have.
                self.broker.cancel(t.entry_id)
                t.state = "cancelling"
            elif st in ("canceled", "expired", "rejected"):
                t.state, t.outcome = "done", t.outcome or f"entry {st}"
            elif now >= self.at(WINDOW_END):
                self.broker.cancel(t.entry_id)
                t.state, t.outcome = "cancelling", "no fill by 09:15 CT"
            elif now.timestamp() - t.last_stop_check >= STOP_CHECK_EVERY:
                t.last_stop_check = now.timestamp()
                low = self.broker.low_since(t.symbol, self.at(WINDOW_OPEN))
                if low is not None and low <= t.stop:
                    self.broker.cancel(t.entry_id)
                    t.state, t.outcome = "cancelling", "traded below the stop first"

        elif t.state == "cancelling":
            o = idx.get(t.entry_id) or {}
            if o.get("status") in ("canceled", "filled", "expired", "rejected"):
                if int(float(o.get("filled_qty") or 0)) > 0:
                    self.on_filled(t, o)
                else:
                    t.state = "done"

        elif t.state == "exits":
            a = self._oco(idx, t.a_id)
            b = self._oco(idx, t.b_id) if t.b_id else None
            if a["tp"] == "filled" and not t.t1_hit:
                t.t1_hit = True
                self.say(f"{t.symbol}: target 1 filled")
                if b and not t.be_done and b["tp"] not in ("filled",) and b["sl"] not in ("filled",):
                    self.broker.cancel(t.b_id)
                    t.state = "be_cancelling"
                    return
            if not pos.get(t.symbol):
                if self._all_done(idx, t):
                    self.finish(t, a, b)

        elif t.state == "be_cancelling":
            b = self._oco(idx, t.b_id)
            if b["tp"] in ("canceled", "filled", "expired") and b["sl"] in ("canceled", "filled", "expired", None):
                left = int(pos.get(t.symbol) or 0)
                if left > 0 and b["tp"] != "filled" and b["sl"] != "filled":
                    be = cents(t.entry_px)
                    try:
                        o = self._place_oco(t, "b2", left, t.target2, be)
                        t.b_id = o["id"]
                        self.say(f"{t.symbol}: stop on the last {left} moved to entry {be}")
                    except Exception as e:
                        log.warning("%s break-even exit rejected (%s) — selling the rest", t.symbol, e)
                        self.broker.close_position(t.symbol)
                t.be_done = True
                t.state = "exits"

    def on_filled(self, t: Trade, o: dict) -> None:
        t.filled = int(float(o.get("filled_qty") or 0))
        t.entry_px = float(o.get("filled_avg_price") or t.trigger)
        s1, s2 = split_qty(t.filled, t.scale_out)
        try:
            t.a_id = self._place_oco(t, "a", s1, t.target1, t.stop)["id"]
            if s2 and t.target2:
                t.b_id = self._place_oco(t, "b", s2, t.target2, t.stop)["id"]
            t.state = "exits"
            self.say(f"{t.symbol}: filled {t.filled} @ {t.entry_px:.2f}; exits {s1} @ {t.target1}"
                     + (f", {s2} @ {t.target2}" if s2 else "") + f", stop {t.stop}")
        except Exception as e:
            log.error("%s: exits rejected (%s) — closing the position", t.symbol, e)
            self.broker.close_position(t.symbol)
            t.state, t.outcome = "done", f"exits rejected, closed at market: {e}"
            self.hc.ping(HC_ORDERS, "fail", f"{t.symbol}: exit orders rejected — closed at market")

    def _place_oco(self, t: Trade, leg: str, qty: int, limit: float, stop: float) -> dict:
        cid = self.cid(t.symbol, leg)
        existing = self.broker.order_by_client_id(cid)
        if existing:
            return existing
        return self.broker.submit({
            "symbol": t.symbol, "qty": str(qty), "side": "sell", "type": "limit",
            "time_in_force": "day", "order_class": "oco", "client_order_id": cid,
            "take_profit": {"limit_price": str(cents(limit))},
            "stop_loss": {"stop_price": str(floor_cents(stop))},
        })

    @staticmethod
    def _oco(idx: dict, oid: str | None) -> dict:
        """Status of an OCO's take-profit and stop-loss legs."""
        o = idx.get(oid) or {}
        parts = [o] + list(o.get("legs") or [])
        tp = next((p for p in parts if p.get("type") == "limit"), {})
        sl = next((p for p in parts if p.get("type") in ("stop", "stop_limit")), {})
        return {"tp": tp.get("status"), "sl": sl.get("status")}

    def _all_done(self, idx: dict, t: Trade) -> bool:
        for oid in (t.a_id, t.b_id):
            if not oid:
                continue
            o = idx.get(oid) or {}
            for p in [o] + list(o.get("legs") or []):
                if p.get("status") not in ("filled", "canceled", "expired", "rejected", "replaced", None):
                    return False
        return True

    def finish(self, t: Trade, a: dict, b: dict | None) -> None:
        if t.outcome:
            pass
        elif t.t1_hit and b and b["tp"] == "filled":
            t.outcome = "target 1 + target 2"
        elif t.t1_hit and t.be_done:
            t.outcome = "target 1 + break-even"
        elif t.t1_hit:
            t.outcome = "target 1"
        else:
            t.outcome = "stopped out"
        t.state = "done"
        self.say(f"{t.symbol}: {t.outcome}")

    def flatten(self, live: list[Trade], why: str) -> None:
        for t in live:
            for oid in (t.entry_id, t.a_id, t.b_id):
                if oid:
                    self.broker.cancel(oid)
        self.sleep(2)
        for t in live:
            if self.broker.positions().get(t.symbol):
                self.broker.close_position(t.symbol)
                t.outcome = (f"target 1 + {why}" if t.t1_hit else why)
            elif not t.outcome:
                t.outcome = "no fill" if not t.filled else why
            t.state = "done"
        self.say(f"flattened: {why}")

    # ── results ─────────────────────────────────────────────────────────────
    def pnl_by_symbol(self) -> dict[str, float]:
        if self.mode == "dry":
            return {}
        out: dict[str, float] = {}
        try:
            for f in self.broker.fills(self.day):
                sign = 1 if f["side"] == "sell" else -1
                out[f["symbol"]] = out.get(f["symbol"], 0.0) + sign * f["qty"] * f["price"]
        except Exception as e:
            log.warning("fills: %s", e)
        return out

    def realised_r(self) -> float:
        done = [t for t in self.trades if t.state == "done" and t.filled]
        if not done:
            return 0.0
        pnl = self.pnl_by_symbol()
        return sum(pnl.get(t.symbol, 0) / (t.risk_per_share * t.filled)
                   for t in done if t.risk_per_share > 0)

    def summary_line(self, what: str) -> str:
        if not self.trades:
            return f"{self.mode}: no orders today"
        if what == "orders":
            return f"{self.mode}: " + ", ".join(f"{t.symbol} {t.qty}@{t.trigger} ({t.state})"
                                                for t in self.trades)
        pnl = self.pnl_by_symbol()
        parts = []
        for t in self.trades:
            r = (pnl.get(t.symbol, 0) / (t.risk_per_share * t.filled)
                 if t.filled and t.risk_per_share > 0 else 0.0)
            parts.append(f"{t.symbol} {t.outcome or t.state}" + (f" {r:+.2f}R" if t.filled else ""))
        return f"{self.mode}: " + "; ".join(parts)

    def journal(self) -> None:
        if not self.trades:
            return
        pnl = self.pnl_by_symbol()
        HOME.mkdir(parents=True, exist_ok=True)
        new = not JOURNAL.exists()
        with JOURNAL.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "mode", "symbol", "planned_qty", "filled", "trigger", "entry_px",
                            "stop", "target1", "target2", "outcome", "pnl_usd", "R"])
            for t in self.trades:
                p = pnl.get(t.symbol, 0.0)
                r = p / (t.risk_per_share * t.filled) if t.filled and t.risk_per_share > 0 else ""
                w.writerow([self.day, self.mode, t.symbol, t.qty, t.filled, t.trigger,
                            t.entry_px or "", t.stop, t.target1, t.target2 or "", t.outcome,
                            round(p, 2) if t.filled else "", round(r, 3) if r != "" else ""])


# ── commands ─────────────────────────────────────────────────────────────────

def _logging(to_file: bool) -> None:
    handlers = [logging.StreamHandler(sys.stdout)] if sys.stdout else []
    if to_file:
        LOGS.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(LOGS / f"{datetime.now(ET):%Y-%m-%d}.log", encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(message)s")


def _broker(cfg: dict):
    from .broker_alpaca import PAPER_URL, Alpaca
    kid, sec = alpaca_keys()
    if not kid or not sec:
        raise SystemExit("No Alpaca keys stored — run: python -m sneak.executor setup")
    return Alpaca(kid, sec, PAPER_URL)


def cmd_setup() -> int:
    import keyring
    cfg = load_config()
    print("SNEAK executor setup. Press Enter to keep the value in [brackets].\n")

    def ask(key, prompt, cast=str):
        v = input(f"{prompt} [{cfg[key]}]: ").strip()
        if v:
            cfg[key] = cast(v)
    ask("mode", "Mode — dry (log only) or paper")
    if cfg["mode"] not in ("dry", "paper"):
        raise SystemExit("mode must be dry or paper")
    ask("cash", "Cash the sizer may commit, $", float)
    ask("base_risk_pct", "Base risk per Normal trade, % of cash", float)
    ask("max_entries", "Most entries per day", int)
    ask("hc_ping_key", "Healthchecks.io project ping key")
    HOME.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))
    print(f"\nSaved {CONFIG}")

    if input("Store Alpaca PAPER keys now? [y/N]: ").strip().lower() == "y":
        keyring.set_password(KEYRING_ALPACA, "key_id", getpass.getpass("Alpaca paper API key ID: ").strip())
        keyring.set_password(KEYRING_ALPACA, "secret", getpass.getpass("Alpaca paper secret key: ").strip())
        print("Alpaca keys saved to Windows Credential Manager.")
    if input("Store the GitHub fine-grained token now? [y/N]: ").strip().lower() == "y":
        keyring.set_password(KEYRING_GITHUB, "token", getpass.getpass("GitHub token: ").strip())
        print("GitHub token saved to Windows Credential Manager.")
    print("\nNext: python -m sneak.executor check")
    return 0


def cmd_check() -> int:
    cfg = load_config()
    ok = True
    print(f"config  {CONFIG}  mode={cfg['mode']} cash=${cfg['cash']:,.0f} "
          f"risk={cfg['base_risk_pct']}% max_entries={cfg['max_entries']}")
    try:
        b = _broker(cfg)
        a = b.account()
        print(f"alpaca  OK  status={a.get('status')} cash=${float(a.get('cash', 0)):,.0f} "
              f"buying_power=${float(a.get('buying_power', 0)):,.0f}")
        c = b.clock()
        print(f"clock   market {'OPEN' if c.get('is_open') else 'closed'} · next open {c.get('next_open')}")
        pos = b.positions()
        print(f"        positions: {pos or 'none'}")
    except SystemExit as e:
        print(f"alpaca  MISSING  {e}"); ok = False
    except Exception as e:
        print(f"alpaca  FAILED  {e}"); ok = False
    tok = github_token()
    feed = Feed(cfg["repo"], tok)
    try:
        f = feed.orders()
        print(f"github  OK  token={'yes' if tok else 'no (backup start disabled)'} · "
              f"orders.json session={f.get('session') if f else 'not published yet'}")
        print(f"        kill switch {'ON' if feed.killed() or KILL_FILE.exists() else 'off'}")
    except Exception as e:
        print(f"github  FAILED  {e}"); ok = False
    if cfg["hc_ping_key"]:
        Pinger(cfg["hc_ping_key"]).ping(HC_LAPTOP, msg="executor check")
        print("health  sent a test ping to sneak-laptop — it should turn green on Healthchecks.io")
    else:
        print("health  no ping key set — run setup"); ok = False
    print("\nAll good." if ok else "\nFix the lines marked FAILED/MISSING.")
    return 0 if ok else 1


def cmd_run() -> int:
    _logging(True)
    cfg = load_config()
    ex = Executor(cfg, _broker(cfg), Feed(cfg["repo"], github_token()), Pinger(cfg["hc_ping_key"]))
    log.info("executor %s · mode=%s cash=%s risk=%s%%", ex.day, cfg["mode"], cfg["cash"],
             cfg["base_risk_pct"])
    return ex.run()


def main() -> int:
    ap = argparse.ArgumentParser(description="SNEAK order executor")
    ap.add_argument("command", choices=["setup", "check", "run", "selftest"])
    a = ap.parse_args()
    if a.command == "setup":
        return cmd_setup()
    if a.command == "check":
        return cmd_check()
    if a.command == "selftest":
        _logging(False)
        from .executor_selftest import main as st
        return st()
    return cmd_run()


if __name__ == "__main__":
    sys.exit(main())
