"""
broker_alpaca.py — the few Alpaca REST calls the executor needs, nothing more.

Paper:  https://paper-api.alpaca.markets   (keys from the paper dashboard)
Live:   https://api.alpaca.markets         (not used — live trading goes through
                                            Schwab once the paper phase passes)
Market data for the stop-through check comes from the free IEX feed.

Every method returns plain dicts as Alpaca sends them, so the executor and the
self-test's fake broker share one shape.
"""

from __future__ import annotations

import time
from datetime import date, datetime

import requests

PAPER_URL = "https://paper-api.alpaca.markets"
DATA_URL = "https://data.alpaca.markets"

TERMINAL = {"filled", "canceled", "expired", "rejected", "replaced", "done_for_day"}


class BrokerError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


class Alpaca:
    def __init__(self, key_id: str, secret: str, base_url: str = PAPER_URL, timeout: float = 10):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret})

    # ── plumbing ────────────────────────────────────────────────────────────
    def _req(self, method: str, url: str, **kw):
        for attempt in range(3):
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
            except requests.RequestException as e:
                if attempt == 2:
                    raise BrokerError(0, f"network: {e}")
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
            if r.status_code >= 400:
                try:
                    msg = r.json().get("message") or r.text
                except Exception:
                    msg = r.text
                raise BrokerError(r.status_code, msg[:300])
            if r.status_code == 204 or not r.content:
                return None
            return r.json()
        raise BrokerError(0, "unreachable")

    def _get(self, path: str, **params):
        return self._req("GET", self.base + path, params=params or None)

    # ── account and calendar ────────────────────────────────────────────────
    def account(self) -> dict:
        return self._get("/v2/account")

    def clock(self) -> dict:
        return self._get("/v2/clock")

    def calendar(self, day: date) -> dict | None:
        """{'date','open','close'} for `day`, or None on a market holiday/weekend."""
        rows = self._get("/v2/calendar", start=day.isoformat(), end=day.isoformat()) or []
        return next((r for r in rows if r.get("date") == day.isoformat()), None)

    # ── orders ──────────────────────────────────────────────────────────────
    def submit(self, order: dict) -> dict:
        return self._req("POST", self.base + "/v2/orders", json=order)

    def order_by_client_id(self, cid: str) -> dict | None:
        try:
            return self._get("/v2/orders:by_client_order_id", client_order_id=cid)
        except BrokerError as e:
            if e.status == 404:
                return None
            raise

    def orders_since(self, after: datetime) -> list[dict]:
        """Every order created since `after`, legs nested under their parent."""
        return self._get("/v2/orders", status="all", after=after.isoformat(),
                         limit=500, nested="true", direction="asc") or []

    def cancel(self, order_id: str) -> None:
        try:
            self._req("DELETE", f"{self.base}/v2/orders/{order_id}")
        except BrokerError as e:
            if e.status in (404, 422):   # already filled / already cancelled
                return
            raise

    # ── positions and fills ─────────────────────────────────────────────────
    def positions(self) -> dict[str, float]:
        return {p["symbol"]: float(p["qty"]) for p in (self._get("/v2/positions") or [])}

    def close_position(self, symbol: str) -> dict | None:
        try:
            return self._req("DELETE", f"{self.base}/v2/positions/{symbol}")
        except BrokerError as e:
            if e.status == 404:
                return None
            raise

    def fills(self, day: date) -> list[dict]:
        """Today's executions: [{'symbol','side','qty','price'}]."""
        rows = self._get("/v2/account/activities/FILL", date=day.isoformat(), page_size=100) or []
        return [{"symbol": r["symbol"], "side": r["side"], "qty": float(r["qty"]),
                 "price": float(r["price"])} for r in rows]

    # ── market data ─────────────────────────────────────────────────────────
    def low_since(self, symbol: str, start: datetime) -> float | None:
        """Lowest 1-minute low since `start` on the free IEX feed (None if no bars)."""
        r = self._req("GET", f"{DATA_URL}/v2/stocks/{symbol}/bars",
                      params={"timeframe": "1Min", "start": start.isoformat(), "feed": "iex",
                              "limit": 100})
        bars = (r or {}).get("bars") or []
        return min(b["l"] for b in bars) if bars else None
