#!/usr/bin/env python3
"""
yahoo.py — Thin, fast Yahoo Finance chart client.

Why not yfinance: from a datacenter IP Yahoo returns HTTP 429 unless a browser
User-Agent is present, and yfinance's curl_cffi transport gets connection-reset.
This client sets a real UA, retries with jittered backoff, and pools connections
across a thread pool. Measured ~25 req/s at 32 workers with zero non-200s.

Two endpoints are used:

  spark  — /v8/finance/spark?symbols=A,B,...  (HARD CAP: 20 symbols per call)
           Returns timestamp[] + close[] only. Cheap. Used to narrow thousands
           of tickers down to a few hundred before pulling real candles.

  chart  — /v8/finance/chart/SYM?range=..&interval=..
           Full OHLCV. Used for daily levels and for confirmed candidates.
"""

from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

import requests

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

SPARK_URL = "https://query1.finance.yahoo.com/v8/finance/spark"
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

SPARK_MAX = 20          # Yahoo rejects batches larger than this
DEFAULT_WORKERS = 24
MAX_RETRIES = 4


class _Pool:
    """One requests.Session per worker thread, reused across calls."""

    def __init__(self) -> None:
        self._local = __import__("threading").local()

    def session(self) -> requests.Session:
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Accept": "application/json"})
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=8, pool_maxsize=8, max_retries=0
            )
            s.mount("https://", adapter)
            self._local.s = s
        return s


_POOL = _Pool()


def _get_json(url: str, params: dict, timeout: float = 20.0) -> dict | None:
    """GET with jittered exponential backoff. Returns parsed JSON or None."""
    for attempt in range(MAX_RETRIES):
        try:
            r = _POOL.session().get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            # 404 = symbol genuinely does not exist; do not burn retries on it.
            if r.status_code == 404:
                return None
            if r.status_code in (429, 502, 503, 504):
                time.sleep((0.6 * 2**attempt) + random.uniform(0, 0.4))
                continue
            return None
        except Exception:
            time.sleep((0.4 * 2**attempt) + random.uniform(0, 0.3))
    return None


def _map(fn: Callable, items: Sequence, workers: int) -> list:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


# ── spark ────────────────────────────────────────────────────────────────────

def spark_closes(
    symbols: Iterable[str],
    rng: str = "1d",
    interval: str = "15m",
    workers: int = DEFAULT_WORKERS,
) -> dict[str, dict]:
    """
    Bulk-fetch close series. Returns {symbol: {"timestamp": [...], "close": [...]}}.

    Symbols that Yahoo does not know are simply absent from the result — a bad
    ticker inside a batch does not poison the batch.
    """
    syms = [s for s in dict.fromkeys(symbols) if s]
    batches = [syms[i : i + SPARK_MAX] for i in range(0, len(syms), SPARK_MAX)]

    def one(batch: list[str]) -> dict:
        j = _get_json(
            SPARK_URL,
            {"symbols": ",".join(batch), "range": rng, "interval": interval},
        )
        if not isinstance(j, dict):
            return {}
        out = {}
        for sym, payload in j.items():
            if not isinstance(payload, dict):
                continue
            ts, cl = payload.get("timestamp"), payload.get("close")
            if ts and cl:
                out[sym] = {"timestamp": ts, "close": cl}
        return out

    merged: dict[str, dict] = {}
    for part in _map(one, batches, workers):
        merged.update(part)
    return merged


# ── chart (full OHLCV) ───────────────────────────────────────────────────────

def _parse_chart(j: Any) -> list[dict] | None:
    try:
        res = j["chart"]["result"][0]
    except Exception:
        return None
    ts = res.get("timestamp") or []
    try:
        q = res["indicators"]["quote"][0]
    except Exception:
        return None
    o, h, l, c, v = (
        q.get("open") or [],
        q.get("high") or [],
        q.get("low") or [],
        q.get("close") or [],
        q.get("volume") or [],
    )
    bars = []
    for i, t in enumerate(ts):
        try:
            if o[i] is None or h[i] is None or l[i] is None or c[i] is None:
                continue
            bars.append(
                {
                    "t": int(t),
                    "dt": datetime.fromtimestamp(int(t), ET),
                    "o": float(o[i]),
                    "h": float(h[i]),
                    "l": float(l[i]),
                    "c": float(c[i]),
                    "v": int(v[i] or 0),
                }
            )
        except Exception:
            continue
    return bars


def chart(sym: str, rng: str, interval: str, prepost: bool = False) -> list[dict] | None:
    """OHLCV bars for one symbol, oldest first. None if unavailable."""
    j = _get_json(
        CHART_URL.format(sym=sym),
        {
            "range": rng,
            "interval": interval,
            "includePrePost": "true" if prepost else "false",
        },
    )
    if j is None:
        return None
    return _parse_chart(j)


def charts(
    symbols: Iterable[str],
    rng: str,
    interval: str,
    workers: int = DEFAULT_WORKERS,
    prepost: bool = False,
) -> dict[str, list[dict]]:
    """Parallel chart fetch. Symbols with no usable data are omitted."""
    syms = [s for s in dict.fromkeys(symbols) if s]

    def one(sym: str):
        return sym, chart(sym, rng, interval, prepost)

    out: dict[str, list[dict]] = {}
    for sym, bars in _map(one, syms, workers):
        if bars:
            out[sym] = bars
    return out


# ── helpers ──────────────────────────────────────────────────────────────────

def session_bars(bars: list[dict], day: "datetime.date") -> list[dict]:
    """Regular-hours bars (09:30–16:00 ET) belonging to a given calendar day."""
    out = []
    for b in bars:
        d = b["dt"]
        if d.date() != day:
            continue
        mins = d.hour * 60 + d.minute
        if 9 * 60 + 30 <= mins < 16 * 60:
            out.append(b)
    return out


def now_et() -> datetime:
    return datetime.now(ET)


def now_ct() -> datetime:
    return datetime.now(CT)
