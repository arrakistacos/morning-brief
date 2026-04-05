#!/usr/bin/env python3
"""
execute_trade.py — Execute a simulated paper trade at real-time market prices.

Rules enforced:
  - LONG-ONLY: BUY to open, SELL to close. No short selling ever.
  - T+2 settlement: sale proceeds are unsettled for 2 business days.
    Using unsettled cash for a BUY constitutes a "good faith violation" — blocked.
  - Max 3 concurrent open positions.
  - Max 30% of total portfolio value in any single position.
  - Market-open warning (does not block — this is a simulator with --force override).

Usage:
    python simulator/execute_trade.py --action BUY  --ticker AAPL --shares 10 \\
        --strategy "momentum breakout" \\
        --thesis "Breaking above 200DMA with volume, AI hardware tailwinds" \\
        --pattern "bull flag"

    python simulator/execute_trade.py --action SELL --ticker AAPL --shares 5 \\
        --strategy "partial profit" \\
        --thesis "Up 17%, taking half off at resistance"
"""

import argparse
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pytz

# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).parent.parent
PORTFOLIO_F = REPO_ROOT / "simulator" / "portfolio.json"
TRADES_F    = REPO_ROOT / "simulator" / "trades.json"
ET          = pytz.timezone("America/New_York")

US_HOLIDAYS = {
    "2025-01-01","2025-01-20","2025-02-17","2025-04-18",
    "2025-05-26","2025-06-19","2025-07-04","2025-09-01",
    "2025-11-27","2025-12-25",
    "2026-01-01","2026-01-19","2026-02-16","2026-04-03",
    "2026-05-25","2026-06-19","2026-07-03","2026-09-07",
    "2026-11-26","2026-12-25",
}
# ---------------------------------------------------------------------------


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def add_business_days(start_date: date, n: int) -> date:
    """Add n business days to start_date, skipping weekends and US holidays."""
    d = start_date
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime("%Y-%m-%d") not in US_HOLIDAYS:
            added += 1
    return d


def is_market_open() -> bool:
    from datetime import time as dtime
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    if now.strftime("%Y-%m-%d") in US_HOLIDAYS:
        return False
    t = now.time().replace(second=0, microsecond=0)
    return dtime(9, 30) <= t < dtime(16, 0)


def fetch_price(ticker: str) -> float:
    import yfinance as yf
    t = yf.Ticker(ticker.upper())
    try:
        price = t.fast_info.last_price
        if price and float(price) > 0:
            return round(float(price), 4)
    except Exception:
        pass
    try:
        hist = t.history(period="2d", interval="1m")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:
        pass
    try:
        info = t.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        if price:
            return round(float(price), 4)
    except Exception:
        pass
    raise ValueError(f"Could not fetch price for {ticker}")


def portfolio_total_value(portfolio: dict) -> float:
    """Settled cash + unsettled proceeds + current market value of positions."""
    total = portfolio["cash"]
    # Include unsettled cash in total value (it exists, just can't be used to buy)
    for u in portfolio.get("unsettled_cash", []):
        total += u["amount"]
    for pos in portfolio["positions"]:
        try:
            price = fetch_price(pos["ticker"])
            total += price * pos["shares"]
        except Exception:
            total += pos["avg_cost"] * pos["shares"]
    return round(total, 2)


def settle_pending_cash(portfolio: dict, today_str: str) -> float:
    """Move any unsettled cash whose settlement_date <= today into settled cash.
    Returns the amount settled."""
    settled_amount = 0.0
    remaining = []
    for u in portfolio.get("unsettled_cash", []):
        if u["settlement_date"] <= today_str:
            portfolio["cash"] = round(portfolio["cash"] + u["amount"], 2)
            settled_amount += u["amount"]
        else:
            remaining.append(u)
    portfolio["unsettled_cash"] = remaining
    return round(settled_amount, 2)


# ---------------------------------------------------------------------------
# BUY
# ---------------------------------------------------------------------------

def execute_buy(portfolio: dict, trades: list, args) -> dict:
    ticker   = args.ticker.upper()
    shares   = args.shares
    strategy = args.strategy or ""
    thesis   = args.thesis or ""
    pattern  = args.pattern or ""

    # Long-only: BUY only if we have a bullish thesis
    price = fetch_price(ticker)
    total = round(price * shares, 2)

    # T+2: Only settled cash available for purchases (good faith rule)
    settled_cash = portfolio["cash"]
    if total > settled_cash:
        unsettled_total = sum(u["amount"] for u in portfolio.get("unsettled_cash", []))
        msg = (f"Insufficient SETTLED cash. Need ${total:,.2f}, "
               f"have ${settled_cash:,.2f} settled")
        if unsettled_total > 0:
            msg += (f" (+ ${unsettled_total:,.2f} unsettled — using unsettled funds "
                    f"constitutes a good faith violation; wait for settlement)")
        raise ValueError(msg)

    # Max 3 positions
    open_tickers = {p["ticker"] for p in portfolio["positions"]}
    if ticker not in open_tickers and len(open_tickers) >= 3:
        raise ValueError(
            f"Max 3 open positions. Currently holding: {', '.join(sorted(open_tickers))}"
        )

    # 30% position size limit (of total portfolio value)
    port_value    = portfolio_total_value(portfolio)
    max_position  = port_value * 0.30
    existing      = next((p for p in portfolio["positions"] if p["ticker"] == ticker), None)
    existing_val  = (existing["shares"] * price) if existing else 0
    new_pos_val   = existing_val + total
    if new_pos_val > max_position:
        raise ValueError(
            f"Position size limit: ${new_pos_val:,.2f} exceeds 30% cap "
            f"(${max_position:,.2f}) of portfolio (${port_value:,.2f}). "
            f"Reduce share count."
        )

    # Update or create position
    now_et = datetime.now(ET)
    if existing:
        old_total     = existing["avg_cost"] * existing["shares"]
        existing["shares"]   += shares
        existing["avg_cost"]  = round((old_total + total) / existing["shares"], 4)
        existing["strategy"]  = strategy or existing["strategy"]
        existing["thesis"]    = thesis or existing["thesis"]
    else:
        portfolio["positions"].append({
            "ticker":     ticker,
            "shares":     shares,
            "avg_cost":   price,
            "entry_date": now_et.strftime("%Y-%m-%d"),
            "strategy":   strategy,
            "thesis":     thesis,
        })

    portfolio["cash"]         = round(portfolio["cash"] - total, 2)
    portfolio["last_updated"] = now_et.isoformat()

    # Trade record
    port_val  = portfolio_total_value(portfolio)
    trade_id  = max((t["id"] for t in trades), default=0) + 1
    trade = {
        "id":              trade_id,
        "date":            now_et.strftime("%Y-%m-%d"),
        "time":            now_et.strftime("%H:%M ET"),
        "ticker":          ticker,
        "action":          "BUY",
        "shares":          shares,
        "price":           price,
        "total":           total,
        "cash_after":      portfolio["cash"],
        "portfolio_value": port_val,
        "strategy":        strategy,
        "thesis":          thesis,
        "pattern":         pattern,
        "sentiment_score": args.sentiment_score,
    }
    trades.append(trade)
    return {"trade": trade, "portfolio": portfolio}


# ---------------------------------------------------------------------------
# SELL (close long position only)
# ---------------------------------------------------------------------------

def execute_sell(portfolio: dict, trades: list, args) -> dict:
    ticker   = args.ticker.upper()
    shares   = args.shares
    strategy = args.strategy or ""
    thesis   = args.thesis or ""
    pattern  = args.pattern or ""

    # Long-only: can only sell shares we actually own
    pos_idx = next(
        (i for i, p in enumerate(portfolio["positions"]) if p["ticker"] == ticker),
        None
    )
    if pos_idx is None:
        raise ValueError(
            f"No open long position for {ticker}. "
            f"Short selling is not permitted in this simulator."
        )

    pos = portfolio["positions"][pos_idx]
    if shares > pos["shares"]:
        raise ValueError(
            f"Cannot sell {shares} shares of {ticker}; only holding {pos['shares']}. "
            f"Short selling is not permitted."
        )

    price        = fetch_price(ticker)
    total        = round(price * shares, 2)
    realized_pnl = round((price - pos["avg_cost"]) * shares, 2)
    realized_pct = round(((price - pos["avg_cost"]) / pos["avg_cost"]) * 100, 2)

    # Update position
    pos["shares"] -= shares
    if pos["shares"] == 0:
        portfolio["positions"].pop(pos_idx)

    now_et          = datetime.now(ET)
    today           = now_et.date()
    settlement_date = add_business_days(today, 2)
    settlement_str  = settlement_date.strftime("%Y-%m-%d")

    # T+2: proceeds go to unsettled cash
    trade_id = max((t["id"] for t in trades), default=0) + 1
    portfolio.setdefault("unsettled_cash", []).append({
        "amount":          total,
        "settlement_date": settlement_str,
        "trade_id":        trade_id,
        "ticker":          ticker,
    })
    portfolio["last_updated"] = now_et.isoformat()

    # Total cash available display (settled + unsettled)
    settled     = portfolio["cash"]
    unsettled   = sum(u["amount"] for u in portfolio["unsettled_cash"])
    total_cash  = round(settled + unsettled, 2)
    port_val    = portfolio_total_value(portfolio)

    trade = {
        "id":              trade_id,
        "date":            now_et.strftime("%Y-%m-%d"),
        "time":            now_et.strftime("%H:%M ET"),
        "ticker":          ticker,
        "action":          "SELL",
        "shares":          shares,
        "price":           price,
        "total":           total,
        "cash_after":      total_cash,
        "settled_cash":    settled,
        "unsettled_cash":  unsettled,
        "portfolio_value": port_val,
        "realized_pnl":    realized_pnl,
        "realized_pnl_pct": realized_pct,
        "settlement_date": settlement_str,
        "strategy":        strategy,
        "thesis":          thesis,
        "pattern":         pattern,
        "sentiment_score": args.sentiment_score,
    }
    trades.append(trade)
    return {"trade": trade, "portfolio": portfolio}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Execute a paper trade (long-only, T+2 settlement)")
    parser.add_argument("--action",          required=True, choices=["BUY","SELL"])
    parser.add_argument("--ticker",          required=True)
    parser.add_argument("--shares",          required=True, type=int)
    parser.add_argument("--strategy",        default="")
    parser.add_argument("--thesis",          default="")
    parser.add_argument("--pattern",         default="")
    parser.add_argument("--sentiment-score", default=0, type=int,
                        help="Morning brief sentiment score (-10 to +10)")
    parser.add_argument("--force",           action="store_true",
                        help="Suppress market-closed warning")
    args = parser.parse_args()

    now_et = datetime.now(ET)
    today  = now_et.strftime("%Y-%m-%d")

    if not is_market_open() and not args.force:
        print("⚠️  WARNING: Market is currently closed. Price is last known. "
              "Pass --force to suppress.")

    portfolio = load_json(PORTFOLIO_F)
    trades    = load_json(TRADES_F)

    # Auto-settle any funds whose settlement date has passed
    auto_settled = settle_pending_cash(portfolio, today)
    if auto_settled > 0:
        print(f"✅ Auto-settled ${auto_settled:,.2f} from previous trades")

    if args.action == "BUY":
        result = execute_buy(portfolio, trades, args)
    else:
        result = execute_sell(portfolio, trades, args)

    save_json(PORTFOLIO_F, result["portfolio"])
    save_json(TRADES_F, trades)

    t     = result["trade"]
    emoji = "🟢" if t["action"] == "BUY" else "🔴"
    print(f"\n{emoji} TRADE EXECUTED — #{t['id']}")
    print(f"  {t['action']} {t['shares']}× {t['ticker']} @ ${t['price']:,.2f}")
    print(f"  Trade value:       ${t['total']:,.2f}")
    if t["action"] == "BUY":
        print(f"  Settled cash:      ${t['cash_after']:,.2f}")
    else:
        pnl_sign = "+" if t["realized_pnl"] >= 0 else ""
        print(f"  Realized P&L:      {pnl_sign}${t['realized_pnl']:,.2f} ({pnl_sign}{t['realized_pnl_pct']:.2f}%)")
        print(f"  Settled cash:      ${t['settled_cash']:,.2f}")
        print(f"  Unsettled cash:    ${t['unsettled_cash']:,.2f}  (settles {t['settlement_date']})")
        print(f"  Total cash:        ${t['cash_after']:,.2f}")
    print(f"  Portfolio value:   ${t['portfolio_value']:,.2f}")
    print(f"  Strategy:          {t['strategy']}")
    print(f"  Thesis:            {t['thesis']}")


if __name__ == "__main__":
    main()
