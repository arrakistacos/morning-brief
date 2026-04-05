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

BUY orders now capture full trade setup at entry time:
  stop_loss_price, stop_loss_pct, target_price, target_pct,
  risk_reward_ratio, risk_per_trade, setup_type, timeframe,
  entry_trigger, exit_plan

Usage:
    python simulator/execute_trade.py --action BUY  --ticker AAPL --shares 10 \\
        --strategy "momentum breakout" \\
        --thesis "Breaking above 200DMA with volume, AI hardware tailwinds" \\
        --pattern "bull flag" \\
        --setup-type "bull flag breakout" \\
        --timeframe "3-7 days" \\
        --entry-trigger "Price broke above $175 resistance with 2x avg volume" \\
        --exit-plan "Sell half at $198 (+15%), trail stop on remainder. Hard stop at $161." \\
        --stop-loss-pct 8.0 \\
        --target-pct 15.0

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
# Default stop/target percentages (can be overridden per trade)
DEFAULT_STOP_LOSS_PCT = 8.0
DEFAULT_TARGET_PCT    = 15.0
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


def compute_trade_setup(price: float, shares: int, args) -> dict:
    """
    Compute and return trade setup fields for a BUY order.
    All values are calculated from the entry price unless explicitly provided.
    """
    stop_pct   = float(args.stop_loss_pct)  if args.stop_loss_pct  else DEFAULT_STOP_LOSS_PCT
    target_pct = float(args.target_pct)     if args.target_pct     else DEFAULT_TARGET_PCT

    # Prices
    stop_price   = round(price * (1 - stop_pct / 100), 4)
    target_price = round(price * (1 + target_pct / 100), 4)

    # Override if explicit prices were passed
    if args.stop_loss_price:
        stop_price = float(args.stop_loss_price)
        stop_pct   = round(((price - stop_price) / price) * 100, 2)
    if args.target_price:
        target_price = float(args.target_price)
        target_pct   = round(((target_price - price) / price) * 100, 2)

    risk_per_trade   = round((price - stop_price) * shares, 2)
    risk_reward_ratio = round(target_pct / stop_pct, 3) if stop_pct > 0 else None

    return {
        "stop_loss_price":  stop_price,
        "stop_loss_pct":    round(stop_pct, 2),
        "target_price":     target_price,
        "target_pct":       round(target_pct, 2),
        "risk_reward_ratio": risk_reward_ratio,
        "risk_per_trade":   risk_per_trade,
        "setup_type":       args.setup_type   or "",
        "timeframe":        args.timeframe    or "",
        "entry_trigger":    args.entry_trigger or "",
        "exit_plan":        args.exit_plan    or (
            f"Sell half at ${target_price:.2f} (+{target_pct:.1f}%), "
            f"trail stop on remainder. Hard stop at ${stop_price:.2f} (-{stop_pct:.1f}%)."
        ),
    }


# ---------------------------------------------------------------------------
# BUY
# ---------------------------------------------------------------------------

def execute_buy(portfolio: dict, trades: list, args) -> dict:
    ticker   = args.ticker.upper()
    shares   = args.shares
    strategy = args.strategy or ""
    thesis   = args.thesis or ""
    pattern  = args.pattern or ""

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

    # Compute trade setup (stop loss, target, R:R, etc.)
    setup = compute_trade_setup(price, shares, args)

    # Update or create position
    now_et = datetime.now(ET)
    if existing:
        old_total               = existing["avg_cost"] * existing["shares"]
        existing["shares"]     += shares
        existing["avg_cost"]    = round((old_total + total) / existing["shares"], 4)
        existing["strategy"]    = strategy or existing["strategy"]
        existing["thesis"]      = thesis or existing["thesis"]
        # Update stop/target on the position record too
        existing["stop_loss_price"] = setup["stop_loss_price"]
        existing["target_price"]    = setup["target_price"]
    else:
        portfolio["positions"].append({
            "ticker":           ticker,
            "shares":           shares,
            "avg_cost":         price,
            "entry_date":       now_et.strftime("%Y-%m-%d"),
            "strategy":         strategy,
            "thesis":           thesis,
            "stop_loss_price":  setup["stop_loss_price"],
            "target_price":     setup["target_price"],
        })

    portfolio["cash"]         = round(portfolio["cash"] - total, 2)
    portfolio["last_updated"] = now_et.isoformat()

    # Trade record
    port_val  = portfolio_total_value(portfolio)
    trade_id  = max((t["id"] for t in trades), default=0) + 1
    trade = {
        "id":               trade_id,
        "date":             now_et.strftime("%Y-%m-%d"),
        "time":             now_et.strftime("%H:%M ET"),
        "ticker":           ticker,
        "action":           "BUY",
        "shares":           shares,
        "price":            price,
        "total":            total,
        "cash_after":       portfolio["cash"],
        "portfolio_value":  port_val,
        "strategy":         strategy,
        "thesis":           thesis,
        "pattern":          pattern,
        "sentiment_score":  args.sentiment_score,
        # Trade setup fields
        "stop_loss_price":   setup["stop_loss_price"],
        "stop_loss_pct":     setup["stop_loss_pct"],
        "target_price":      setup["target_price"],
        "target_pct":        setup["target_pct"],
        "risk_reward_ratio": setup["risk_reward_ratio"],
        "risk_per_trade":    setup["risk_per_trade"],
        "setup_type":        setup["setup_type"],
        "timeframe":         setup["timeframe"],
        "entry_trigger":     setup["entry_trigger"],
        "exit_plan":         setup["exit_plan"],
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

    # Reference original trade setup if available on the position
    entry_stop   = pos.get("stop_loss_price")
    entry_target = pos.get("target_price")

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

    settled     = portfolio["cash"]
    unsettled   = sum(u["amount"] for u in portfolio["unsettled_cash"])
    total_cash  = round(settled + unsettled, 2)
    port_val    = portfolio_total_value(portfolio)

    trade = {
        "id":               trade_id,
        "date":             now_et.strftime("%Y-%m-%d"),
        "time":             now_et.strftime("%H:%M ET"),
        "ticker":           ticker,
        "action":           "SELL",
        "shares":           shares,
        "price":            price,
        "total":            total,
        "cash_after":       total_cash,
        "settled_cash":     settled,
        "unsettled_cash":   unsettled,
        "portfolio_value":  port_val,
        "realized_pnl":     realized_pnl,
        "realized_pnl_pct": realized_pct,
        "settlement_date":  settlement_str,
        "strategy":         strategy,
        "thesis":           thesis,
        "pattern":          pattern,
        "sentiment_score":  args.sentiment_score,
        # Reference entry setup prices for context
        "entry_stop_loss_price": entry_stop,
        "entry_target_price":    entry_target,
    }
    trades.append(trade)
    return {"trade": trade, "portfolio": portfolio}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Execute a paper trade (long-only, T+2 settlement)")
    parser.add_argument("--action",           required=True, choices=["BUY","SELL"])
    parser.add_argument("--ticker",           required=True)
    parser.add_argument("--shares",           required=True, type=int)
    parser.add_argument("--strategy",         default="")
    parser.add_argument("--thesis",           default="")
    parser.add_argument("--pattern",          default="")
    parser.add_argument("--sentiment-score",  default=0, type=int,
                        help="Morning brief sentiment score (-10 to +10)")
    parser.add_argument("--force",            action="store_true",
                        help="Suppress market-closed warning")
    # BUY-only trade setup fields
    parser.add_argument("--stop-loss-pct",    default=None, type=float,
                        help=f"Stop loss %% distance from entry (default: {DEFAULT_STOP_LOSS_PCT}%%)")
    parser.add_argument("--stop-loss-price",  default=None, type=float,
                        help="Explicit stop loss price (overrides --stop-loss-pct)")
    parser.add_argument("--target-pct",       default=None, type=float,
                        help=f"Profit target %% from entry (default: {DEFAULT_TARGET_PCT}%%)")
    parser.add_argument("--target-price",     default=None, type=float,
                        help="Explicit target price (overrides --target-pct)")
    parser.add_argument("--setup-type",       default="",
                        help='Chart setup type (e.g. "bull flag breakout", "support bounce")')
    parser.add_argument("--timeframe",        default="",
                        help='Expected hold duration (e.g. "2-5 days", "1-2 weeks")')
    parser.add_argument("--entry-trigger",    default="",
                        help='What specifically triggered the entry')
    parser.add_argument("--exit-plan",        default="",
                        help='Plain English exit strategy')
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

    try:
        if args.action == "BUY":
            result = execute_buy(portfolio, trades, args)
        else:
            result = execute_sell(portfolio, trades, args)
    except ValueError as e:
        print(f"\n❌ Trade rejected: {e}")
        sys.exit(1)

    save_json(PORTFOLIO_F, result["portfolio"])
    save_json(TRADES_F, trades)

    t     = result["trade"]
    emoji = "🟢" if t["action"] == "BUY" else "🔴"
    print(f"\n{emoji} TRADE EXECUTED — #{t['id']}")
    print(f"  {t['action']} {t['shares']}× {t['ticker']} @ ${t['price']:,.2f}")
    print(f"  Trade value:       ${t['total']:,.2f}")
    if t["action"] == "BUY":
        print(f"  Settled cash:      ${t['cash_after']:,.2f}")
        print(f"  Stop loss:         ${t['stop_loss_price']:,.2f}  (-{t['stop_loss_pct']:.1f}%)")
        print(f"  Target:            ${t['target_price']:,.2f}  (+{t['target_pct']:.1f}%)")
        if t["risk_reward_ratio"]:
            print(f"  Risk/Reward:       {t['risk_reward_ratio']:.2f}×")
        print(f"  Risk per trade:    ${t['risk_per_trade']:,.2f}")
        if t["setup_type"]:
            print(f"  Setup:             {t['setup_type']}")
        if t["timeframe"]:
            print(f"  Timeframe:         {t['timeframe']}")
        if t["entry_trigger"]:
            print(f"  Entry trigger:     {t['entry_trigger']}")
        if t["exit_plan"]:
            print(f"  Exit plan:         {t['exit_plan']}")
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
