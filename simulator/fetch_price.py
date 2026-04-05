#!/usr/bin/env python3
"""
fetch_price.py — Fetch real-time price for a ticker using yfinance.
Checks US market hours (9:30–16:00 ET Mon–Fri, excluding major holidays).

Usage:
    python simulator/fetch_price.py AAPL
    python simulator/fetch_price.py TSLA --quiet

Output:
    {"ticker": "AAPL", "price": 172.50, "timestamp": "2026-04-05T09:45:00-04:00", "market_open": true}
"""

import sys
import json
import argparse
from datetime import datetime, time as dtime
import pytz
import yfinance as yf

# Major US market holidays (add/update as needed)
US_MARKET_HOLIDAYS = {
    # 2025
    "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
    "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03",
    "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
}

MARKET_OPEN  = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)
ET = pytz.timezone("America/New_York")


def is_market_open() -> bool:
    """Return True if the US equity market is currently open."""
    now_et = datetime.now(ET)
    # Weekend
    if now_et.weekday() >= 5:
        return False
    # Holiday
    date_str = now_et.strftime("%Y-%m-%d")
    if date_str in US_MARKET_HOLIDAYS:
        return False
    # Time window
    current_time = now_et.time().replace(second=0, microsecond=0)
    return MARKET_OPEN <= current_time < MARKET_CLOSE


def fetch_price(ticker: str) -> dict:
    """Fetch current/last price for ticker. Returns dict with price info."""
    t = yf.Ticker(ticker.upper())
    # Try fast_info first (real-time quote)
    try:
        fast = t.fast_info
        price = fast.last_price
        if price and price > 0:
            ts = datetime.now(ET).isoformat()
            return {
                "ticker": ticker.upper(),
                "price": round(float(price), 4),
                "timestamp": ts,
                "market_open": is_market_open(),
                "source": "fast_info"
            }
    except Exception:
        pass

    # Fallback: 1-day history, last close
    try:
        hist = t.history(period="2d", interval="1m")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            ts = datetime.now(ET).isoformat()
            return {
                "ticker": ticker.upper(),
                "price": round(price, 4),
                "timestamp": ts,
                "market_open": is_market_open(),
                "source": "history"
            }
    except Exception:
        pass

    # Last resort: info dict
    try:
        info = t.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if price:
            ts = datetime.now(ET).isoformat()
            return {
                "ticker": ticker.upper(),
                "price": round(float(price), 4),
                "timestamp": ts,
                "market_open": is_market_open(),
                "source": "info"
            }
    except Exception:
        pass

    raise ValueError(f"Could not fetch price for {ticker}")


def main():
    parser = argparse.ArgumentParser(description="Fetch current stock price")
    parser.add_argument("ticker", help="Stock ticker symbol (e.g. AAPL)")
    parser.add_argument("--quiet", action="store_true", help="Suppress extra output")
    args = parser.parse_args()

    result = fetch_price(args.ticker)
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
