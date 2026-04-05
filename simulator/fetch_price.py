#!/usr/bin/env python3
"""
fetch_price.py — Fetch real-time price for a ticker using yfinance.
Checks US market hours via market_calendar.py (NYSE official calendar,
including holidays and early-close days).

Usage:
    python simulator/fetch_price.py AAPL
    python simulator/fetch_price.py TSLA --quiet

Output:
    {"ticker": "AAPL", "price": 172.50, "timestamp": "2026-04-05T09:45:00-04:00", "market_open": true}
"""

import sys
import json
import argparse
from datetime import datetime
import pytz
import yfinance as yf

from market_calendar import is_market_open

ET = pytz.timezone("America/New_York")


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
