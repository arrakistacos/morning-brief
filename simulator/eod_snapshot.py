#!/usr/bin/env python3
"""
eod_snapshot.py — End-of-day snapshot for the paper trading simulator.

Run at 4:05 PM ET Mon–Fri. Does three things:
  1. Settles any T+2 funds whose settlement date has passed
  2. Fetches closing prices → updates performance.json
  3. Appends EOD reflection to strategy_log.json

Usage:
    python simulator/eod_snapshot.py
    python simulator/eod_snapshot.py --note "Volatile day; held through dip on conviction."
"""

import argparse
import json
from datetime import datetime, date, timedelta
from pathlib import Path

import pytz
import yfinance as yf

# ---------------------------------------------------------------------------
REPO_ROOT      = Path(__file__).parent.parent
PORTFOLIO_F    = REPO_ROOT / "simulator" / "portfolio.json"
TRADES_F       = REPO_ROOT / "simulator" / "trades.json"
PERFORMANCE_F  = REPO_ROOT / "simulator" / "performance.json"
STRATEGY_LOG_F = REPO_ROOT / "simulator" / "strategy_log.json"

ET = pytz.timezone("America/New_York")

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


def fetch_close(ticker: str) -> float:
    t = yf.Ticker(ticker.upper())
    try:
        price = t.fast_info.last_price
        if price and float(price) > 0:
            return round(float(price), 4)
    except Exception:
        pass
    try:
        hist = t.history(period="2d", interval="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception:
        pass
    try:
        info = t.info
        price = (info.get("regularMarketPrice") or
                 info.get("currentPrice") or
                 info.get("previousClose"))
        if price:
            return round(float(price), 4)
    except Exception:
        pass
    raise ValueError(f"Could not fetch closing price for {ticker}")


def settle_pending_cash(portfolio: dict, today_str: str) -> float:
    """Move matured unsettled lots into settled cash. Returns total settled."""
    settled_amount = 0.0
    remaining = []
    for lot in portfolio.get("unsettled_cash", []):
        if lot["settlement_date"] <= today_str:
            portfolio["cash"] = round(portfolio["cash"] + lot["amount"], 2)
            settled_amount += lot["amount"]
            print(f"  💵 Settled ${lot['amount']:,.2f} from {lot['ticker']} sale (trade #{lot['trade_id']})")
        else:
            remaining.append(lot)
    portfolio["unsettled_cash"] = remaining
    return round(settled_amount, 2)


def take_snapshot(extra_note: str = "") -> dict:
    now_et   = datetime.now(ET)
    date_str = now_et.strftime("%Y-%m-%d")

    portfolio   = load_json(PORTFOLIO_F)
    performance = load_json(PERFORMANCE_F)
    trades      = load_json(TRADES_F)

    # Step 1: Settle matured T+2 funds
    settled = settle_pending_cash(portfolio, date_str)
    if settled > 0:
        print(f"  Total settled today: ${settled:,.2f}")

    # Step 2: Fetch closing prices for open positions
    positions_value  = 0.0
    position_details = []
    for pos in portfolio["positions"]:
        ticker = pos["ticker"]
        try:
            close_price = fetch_close(ticker)
        except Exception as e:
            print(f"  ⚠️  Could not fetch {ticker}: {e} — using avg_cost")
            close_price = pos["avg_cost"]

        mkt_value  = round(close_price * pos["shares"], 2)
        unrealized = round((close_price - pos["avg_cost"]) * pos["shares"], 2)
        unr_pct    = round(((close_price - pos["avg_cost"]) / pos["avg_cost"]) * 100, 2)
        positions_value += mkt_value
        position_details.append({
            "ticker":          ticker,
            "shares":          pos["shares"],
            "avg_cost":        pos["avg_cost"],
            "close_price":     close_price,
            "market_value":    mkt_value,
            "unrealized_pnl":  unrealized,
            "unrealized_pct":  unr_pct,
        })
        sign = "+" if unrealized >= 0 else ""
        print(f"  {ticker}: {pos['shares']}sh × ${close_price:.2f} = "
              f"${mkt_value:,.2f}  (P&L: {sign}${unrealized:,.2f} / {sign}{unr_pct:.2f}%)")

    settled_cash    = portfolio["cash"]
    unsettled_total = sum(u["amount"] for u in portfolio.get("unsettled_cash", []))
    total_cash      = round(settled_cash + unsettled_total, 2)
    portfolio_value = round(total_cash + positions_value, 2)
    starting_capital = portfolio["starting_capital"]
    total_pnl        = round(portfolio_value - starting_capital, 2)
    total_pnl_pct    = round((total_pnl / starting_capital) * 100, 2)

    # Daily P&L
    if performance:
        prev_value = performance[-1]["portfolio_value"]
        daily_pnl  = round(portfolio_value - prev_value, 2)
    else:
        daily_pnl = 0.0

    snapshot = {
        "date":              date_str,
        "portfolio_value":   portfolio_value,
        "settled_cash":      settled_cash,
        "unsettled_cash":    unsettled_total,
        "total_cash":        total_cash,
        "positions_value":   round(positions_value, 2),
        "daily_pnl":         daily_pnl,
        "total_pnl":         total_pnl,
        "total_pnl_pct":     total_pnl_pct,
        "positions":         position_details,
        "unsettled_lots":    portfolio.get("unsettled_cash", []),
    }

    # Upsert by date
    existing_dates = {s["date"] for s in performance}
    if date_str in existing_dates:
        for i, s in enumerate(performance):
            if s["date"] == date_str:
                performance[i] = snapshot
                break
    else:
        performance.append(snapshot)

    save_json(PERFORMANCE_F, performance)

    # Update portfolio timestamp and persist
    portfolio["last_updated"] = now_et.isoformat()
    save_json(PORTFOLIO_F, portfolio)

    # Step 3: Strategy log entry
    strategy_log = load_json(STRATEGY_LOG_F)
    today_trades = [t for t in trades if t.get("date") == date_str]

    trade_lines = []
    for t in today_trades:
        if t["action"] == "SELL" and "realized_pnl" in t:
            sign = "+" if t["realized_pnl"] >= 0 else ""
            trade_lines.append(
                f"{t['action']} {t['shares']}× {t['ticker']} @ ${t['price']:.2f} "
                f"({sign}${t['realized_pnl']:,.2f} / {sign}{t.get('realized_pnl_pct',0):.2f}%) "
                f"[settles {t.get('settlement_date','?')}]"
            )
        else:
            trade_lines.append(
                f"{t['action']} {t['shares']}× {t['ticker']} @ ${t['price']:.2f}"
            )

    trade_summary = (
        "Trades today: " + " | ".join(trade_lines)
        if trade_lines
        else "No trades today — held positions / cash preservation."
    )

    pos_lines = [
        f"{p['ticker']}: {'+' if p['unrealized_pnl']>=0 else ''}${p['unrealized_pnl']:,.2f} "
        f"({'+' if p['unrealized_pct']>=0 else ''}{p['unrealized_pct']:.2f}%)"
        for p in position_details
    ]
    pos_summary = ("Open positions: " + " | ".join(pos_lines)) if pos_lines else "No open positions."

    daily_sign = "+" if daily_pnl >= 0 else ""
    total_sign = "+" if total_pnl >= 0 else ""
    auto_note = (
        f"EOD {date_str} | Portfolio: ${portfolio_value:,.2f} "
        f"({daily_sign}${daily_pnl:,.2f} today, "
        f"{total_sign}${total_pnl:,.2f} total / {total_sign}{total_pnl_pct:.2f}%) | "
        f"Cash: ${settled_cash:,.2f} settled"
        + (f" + ${unsettled_total:,.2f} unsettled" if unsettled_total > 0 else "")
        + f" | {trade_summary} | {pos_summary}"
    )
    if extra_note:
        auto_note += f" | Reflection: {extra_note}"

    log_entry = {
        "date":     date_str,
        "type":     "eod_snapshot",
        "note":     auto_note,
        "snapshot": snapshot,
        "tags":     ["eod", "daily-review"],
    }
    strategy_log.append(log_entry)
    save_json(STRATEGY_LOG_F, strategy_log)

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="EOD portfolio snapshot with T+2 settlement")
    parser.add_argument("--note", default="", help="Manual reflection note")
    args = parser.parse_args()

    print(f"\n📸 EOD Snapshot — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    print("-" * 62)

    snapshot = take_snapshot(args.note)

    print("-" * 62)
    daily_sign = "+" if snapshot["daily_pnl"] >= 0 else ""
    total_sign = "+" if snapshot["total_pnl"] >= 0 else ""
    print(f"✅ Snapshot saved to simulator/performance.json")
    print(f"   Portfolio value  : ${snapshot['portfolio_value']:,.2f}")
    print(f"   Settled cash     : ${snapshot['settled_cash']:,.2f}")
    if snapshot["unsettled_cash"] > 0:
        print(f"   Unsettled cash   : ${snapshot['unsettled_cash']:,.2f}")
        for lot in snapshot.get("unsettled_lots", []):
            print(f"     • ${lot['amount']:,.2f} from {lot['ticker']} — settles {lot['settlement_date']}")
    print(f"   Positions value  : ${snapshot['positions_value']:,.2f}")
    print(f"   Daily P&L        : {daily_sign}${snapshot['daily_pnl']:,.2f}")
    print(f"   Total P&L        : {total_sign}${snapshot['total_pnl']:,.2f} ({total_sign}{snapshot['total_pnl_pct']:.2f}%)")


if __name__ == "__main__":
    main()
