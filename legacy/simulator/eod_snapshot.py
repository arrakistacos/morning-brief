#!/usr/bin/env python3
"""
eod_snapshot.py — End-of-day snapshot for the paper trading simulator.

Run at 4:05 PM ET Mon–Fri. Does three things:
  1. Settles any T+2 funds whose settlement date has passed
  2. Fetches closing prices → updates performance.json
  3. Appends EOD reflection to strategy_log.json

With --midday flag: takes an intraday snapshot without T+2 settlement processing.
  Appends to performance.json with "type": "midday" so the dashboard can
  differentiate intraday datapoints from official daily closes.

Holiday / early-close handling:
  - If today is not a NYSE trading day (holiday or weekend), the script skips
    all processing and logs "market closed" to strategy_log.json.
  - For EOD mode, get_market_hours() is used to determine the actual close time.
    If the script runs after close (including early-close days like the day before
    Thanksgiving), it proceeds. If it runs before close, it warns and exits.

Usage:
    python simulator/eod_snapshot.py
    python simulator/eod_snapshot.py --note "Volatile day; held through dip on conviction."
    python simulator/eod_snapshot.py --midday
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import pytz
import yfinance as yf

from market_calendar import is_trading_day, get_market_hours
from email_helper import build_eod_email, send_email_via_gmail_mcp

# ---------------------------------------------------------------------------
REPO_ROOT      = Path(__file__).parent.parent
PORTFOLIO_F    = REPO_ROOT / "simulator" / "portfolio.json"
TRADES_F       = REPO_ROOT / "simulator" / "trades.json"
PERFORMANCE_F  = REPO_ROOT / "simulator" / "performance.json"
STRATEGY_LOG_F = REPO_ROOT / "simulator" / "strategy_log.json"

ET = pytz.timezone("America/New_York")
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


def get_tomorrow_watchlist(strategy_log: list, date_str: str) -> list[dict]:
    """
    Build a tomorrow watchlist by scanning today's morning watchlist tickers
    through chart_analysis.py.  Returns up to 5 dicts with ticker/signal/note.
    """
    # Find today's morning-analysis entry to get watchlist tickers
    tickers = []
    for entry in reversed(strategy_log):
        if entry.get("date") == date_str and "morning" in " ".join(entry.get("tags", [])):
            wl = entry.get("watchlist", [])
            if wl:
                tickers = [w["ticker"] for w in wl if "ticker" in w]
            else:
                note = entry.get("note", "")
                for word in note.split():
                    clean = word.strip(".,;:()")
                    if clean.isupper() and 1 <= len(clean) <= 5 and clean.isalpha():
                        tickers.append(clean)
                tickers = tickers[:5]
            break

    if not tickers:
        return []

    results = []
    for ticker in tickers[:5]:
        try:
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "simulator" / "chart_analysis.py"),
                 "--ticker", ticker, "--json"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                data   = json.loads(result.stdout.strip())
                signal = data.get("composite", {}).get("signal", "—")
                rsi    = data.get("rsi", {}).get("value")
                note   = f"RSI {rsi:.0f}" if rsi else ""
                results.append({"ticker": ticker, "signal": signal, "note": note})
            else:
                results.append({"ticker": ticker, "signal": "—", "note": "scan failed"})
        except Exception as e:
            results.append({"ticker": ticker, "signal": "—", "note": str(e)[:40]})

    return results


def take_snapshot(extra_note: str = "", midday: bool = False) -> dict:
    now_et   = datetime.now(ET)
    date_str = now_et.strftime("%Y-%m-%d")
    time_str = now_et.strftime("%H:%M ET")
    snap_type = "midday" if midday else "eod"

    # ── Market holiday guard ─────────────────────────────────────────────────
    if not is_trading_day():
        msg = f"Market closed today ({date_str}) — {'midday snapshot' if midday else 'EOD snapshot'} skipped."
        print(f"🔴 {msg}")
        try:
            strategy_log = load_json(STRATEGY_LOG_F)
            strategy_log.append({
                "date":  date_str,
                "type":  "snapshot_skipped",
                "note":  msg,
                "tags":  ["market-closed", "holiday", snap_type],
            })
            save_json(STRATEGY_LOG_F, strategy_log)
        except Exception:
            pass
        return {}
    # ─────────────────────────────────────────────────────────────────────────

    # ── Early-close guard (EOD mode only) ───────────────────────────────────
    # Use get_market_hours() so early-close days (e.g. day before Thanksgiving,
    # July 3 when July 4 falls on a weekend, Christmas Eve) are respected.
    if not midday:
        try:
            _, market_close_et = get_market_hours()
            if now_et < market_close_et:
                print(f"⚠️  Market hasn't closed yet (closes {market_close_et.strftime('%H:%M %Z')}). "
                      f"Run EOD snapshot after market close.")
                return {}
        except Exception:
            pass  # If we can't get hours, proceed anyway
    # ─────────────────────────────────────────────────────────────────────────

    portfolio   = load_json(PORTFOLIO_F)
    performance = load_json(PERFORMANCE_F)
    trades      = load_json(TRADES_F)

    # Step 1: Settle matured T+2 funds (EOD only — T+2 runs once per day at close)
    if not midday:
        settled = settle_pending_cash(portfolio, date_str)
        if settled > 0:
            print(f"  Total settled today: ${settled:,.2f}")
    else:
        print(f"  ⏭  Midday mode — skipping T+2 settlement (runs at EOD only)")

    # Step 2: Fetch current prices for open positions
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

    # Daily P&L vs previous EOD snapshot (compare to last EOD, not last midday)
    eod_snapshots = [s for s in performance if s.get("type", "eod") == "eod"]
    if eod_snapshots:
        prev_value = eod_snapshots[-1]["portfolio_value"]
        daily_pnl  = round(portfolio_value - prev_value, 2)
    elif performance:
        prev_value = performance[-1]["portfolio_value"]
        daily_pnl  = round(portfolio_value - prev_value, 2)
    else:
        daily_pnl = 0.0

    snapshot = {
        "date":              date_str,
        "time":              time_str,
        "type":              snap_type,
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

    # For EOD: upsert by date (one official record per day)
    # For midday: always append (multiple intraday points allowed)
    if not midday:
        existing_dates = {s["date"] for s in performance if s.get("type", "eod") == "eod"}
        if date_str in existing_dates:
            for i, s in enumerate(performance):
                if s["date"] == date_str and s.get("type", "eod") == "eod":
                    performance[i] = snapshot
                    break
        else:
            performance.append(snapshot)
    else:
        # Midday: replace any existing midday snapshot for same date+time window,
        # or append new one
        existing_midday_idx = None
        for i, s in enumerate(performance):
            if s.get("date") == date_str and s.get("type") == "midday":
                existing_midday_idx = i
                break
        if existing_midday_idx is not None:
            performance[existing_midday_idx] = snapshot
        else:
            performance.append(snapshot)

    save_json(PERFORMANCE_F, performance)

    # Update portfolio timestamp and persist (EOD only — midday doesn't update portfolio file)
    if not midday:
        portfolio["last_updated"] = now_et.isoformat()
        save_json(PORTFOLIO_F, portfolio)

    # Step 3: Strategy log entry (EOD only — midday_check.py writes its own log entries)
    if not midday:
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

        # ── EOD Email — always send on trading days ──────────────────────
        print("\n📧 Building EOD summary email...")
        try:
            watchlist_tomorrow = get_tomorrow_watchlist(strategy_log, date_str)
            subj, html_body = build_eod_email(
                snapshot=snapshot,
                trades=today_trades,
                position_details=position_details,
                extra_note=extra_note,
                watchlist_tomorrow=watchlist_tomorrow,
                date_str=date_str,
            )
            send_email_via_gmail_mcp(subj, html_body)
            print("  ✅ EOD email queued (pending_email.json written)")
        except Exception as e:
            print(f"  ⚠️  Could not build EOD email: {e}")
        # ─────────────────────────────────────────────────────────────────

    return snapshot


def main():
    parser = argparse.ArgumentParser(description="EOD portfolio snapshot with T+2 settlement")
    parser.add_argument("--note",   default="", help="Manual reflection note (EOD only)")
    parser.add_argument("--midday", action="store_true",
                        help="Intraday snapshot: skip T+2 settlement, mark type=midday in performance.json")
    args = parser.parse_args()

    if args.midday:
        print(f"\n📸 Midday Snapshot — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    else:
        print(f"\n📸 EOD Snapshot — {datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}")
    print("-" * 62)

    snapshot = take_snapshot(args.note, midday=args.midday)

    if not snapshot:
        # Skipped (holiday, weekend, or pre-close)
        return

    print("-" * 62)
    daily_sign = "+" if snapshot["daily_pnl"] >= 0 else ""
    total_sign = "+" if snapshot["total_pnl"] >= 0 else ""
    label = "Midday" if args.midday else "EOD"
    print(f"✅ {label} snapshot saved to simulator/performance.json (type={snapshot['type']})")
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
