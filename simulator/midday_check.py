#!/usr/bin/env python3
"""
midday_check.py — Midday portfolio check for the paper trading simulator.

Run at 12:00 PM ET Mon–Fri. Does four things:
  1. Checks open positions for stop-loss triggers (down ≥ 8% → SELL)
     and partial profit targets (up ≥ 15% + overbought/sell signal → SELL half)
  2. Scans for thesis-breaking news on held tickers
  3. Reviews morning watchlist for opportunistic entries (exception, not the rule)
  4. Logs a midday entry to strategy_log.json and appends an intraday
     performance snapshot via eod_snapshot.py --midday

Usage:
    python simulator/midday_check.py
    python simulator/midday_check.py --note "Added extra context for this check."
    python simulator/midday_check.py --dry-run   # Print actions without executing
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz
import yfinance as yf

from market_calendar import is_trading_day
from email_helper import build_midday_email, send_email_via_gmail_mcp

# ---------------------------------------------------------------------------
REPO_ROOT      = Path(__file__).parent.parent
PORTFOLIO_F    = REPO_ROOT / "simulator" / "portfolio.json"
TRADES_F       = REPO_ROOT / "simulator" / "trades.json"
PERFORMANCE_F  = REPO_ROOT / "simulator" / "performance.json"
STRATEGY_LOG_F = REPO_ROOT / "simulator" / "strategy_log.json"

ET = pytz.timezone("America/New_York")

STOP_LOSS_PCT   = -8.0   # Hard stop: sell 100% if down ≥ 8%
PROFIT_PCT      =  15.0  # Partial profit: sell 50% if up ≥ 15%
RSI_OVERBOUGHT  =  70    # RSI threshold for overbought sell signal
MAX_POSITIONS   =   3    # Never enter if ≥ 3 open positions
# ---------------------------------------------------------------------------


def load_json(path):
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_current_price(ticker: str) -> float:
    """Fetch intraday price via fetch_price.py subprocess, fallback to yfinance."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "simulator" / "fetch_price.py"), ticker],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return float(data["price"])
    except Exception:
        pass

    # Direct yfinance fallback
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
    raise ValueError(f"Could not fetch price for {ticker}")


def get_rsi(ticker: str) -> float | None:
    """Return the latest RSI(14) for ticker, or None on failure."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "simulator" / "chart_analysis.py"),
             "--ticker", ticker, "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("rsi", {}).get("value")
    except Exception:
        pass
    return None


def get_chart_signal(ticker: str) -> str | None:
    """Return composite signal string (e.g. STRONG_BUY, SELL) or None."""
    try:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "simulator" / "chart_analysis.py"),
             "--ticker", ticker, "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            return data.get("composite", {}).get("signal")
    except Exception:
        pass
    return None


def execute_trade(action: str, ticker: str, shares: int, strategy: str, thesis: str,
                  dry_run: bool = False) -> bool:
    """Execute a paper trade via execute_trade.py."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "simulator" / "execute_trade.py"),
        "--action", action,
        "--ticker", ticker,
        "--shares", str(shares),
        "--strategy", strategy,
        "--thesis", thesis,
        "--force",
    ]
    if dry_run:
        print(f"  [DRY RUN] Would execute: {' '.join(cmd)}")
        return True

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"  ❌ Trade failed: {result.stderr}")
        return False


# ---------------------------------------------------------------------------
# News search
# ---------------------------------------------------------------------------

def search_ticker_news(ticker: str) -> list[str]:
    """
    Use yfinance news feed for quick headline scan.
    Returns a list of recent headline strings (up to 5).
    """
    headlines = []
    try:
        t = yf.Ticker(ticker.upper())
        news = t.news
        if news:
            for item in news[:5]:
                title = item.get("content", {}).get("title", "") or item.get("title", "")
                if title:
                    headlines.append(title)
    except Exception:
        pass
    return headlines


def assess_thesis_breaking(ticker: str, headlines: list[str], position: dict) -> tuple[bool, str]:
    """
    Heuristic check: are any headlines likely to break the original thesis?
    Returns (is_thesis_breaking, reason_str).
    """
    if not headlines:
        return False, ""

    thesis = (position.get("thesis") or "").lower()
    strategy = (position.get("strategy") or "").lower()

    # Keywords that often indicate thesis-breaking news
    negative_signals = [
        "earnings miss", "revenue miss", "guidance cut", "guidance lowered",
        "fraud", "sec investigation", "sec filing", "accounting irregularity",
        "fda rejection", "clinical trial failure", "bankruptcy", "chapter 11",
        "ceo resign", "ceo fired", "massive layoffs", "plant closure",
        "product recall", "safety recall", "major lawsuit", "class action",
    ]

    for headline in headlines:
        h_lower = headline.lower()
        for signal in negative_signals:
            if signal in h_lower:
                return True, f"Headline may break thesis: '{headline}'"

    # Sector-specific checks based on thesis keywords
    sector_breaks = {
        "oil": ["opec supply increase", "opec+ increase", "oil glut", "production increase"],
        "energy": ["rate hike", "energy regulation", "windfall tax"],
        "tech": ["antitrust", "breakup", "ban", "export restriction"],
        "pharma": ["fda", "trial failed", "rejection"],
        "bank": ["rate cut", "net interest margin", "credit loss"],
    }
    for sector_keyword, break_signals in sector_breaks.items():
        if sector_keyword in thesis or sector_keyword in strategy:
            for headline in headlines:
                h_lower = headline.lower()
                for sig in break_signals:
                    if sig in h_lower:
                        return True, f"Sector-relevant news may break thesis: '{headline}'"

    return False, ""


# ---------------------------------------------------------------------------
# Morning watchlist scan
# ---------------------------------------------------------------------------

def get_morning_watchlist() -> list[dict]:
    """
    Read the most recent strategy_log.json entry tagged 'morning-analysis'
    to find the watchlist tickers from today's brief.
    Returns list of dicts with at least 'ticker' and optionally 'sentiment'.
    """
    try:
        strategy_log = load_json(STRATEGY_LOG_F)
        today_str = datetime.now(ET).strftime("%Y-%m-%d")
        # Look for today's morning analysis entry
        for entry in reversed(strategy_log):
            if entry.get("date") == today_str and "morning" in " ".join(entry.get("tags", [])):
                # Try to extract tickers from the note
                watchlist = entry.get("watchlist", [])
                if watchlist:
                    return watchlist
                # If no structured watchlist, parse note for capitalized ticker-like tokens
                note = entry.get("note", "")
                tickers = []
                for word in note.split():
                    clean = word.strip(".,;:()")
                    if clean.isupper() and 1 <= len(clean) <= 5 and clean.isalpha():
                        tickers.append({"ticker": clean, "sentiment": "bullish"})
                return tickers[:5]  # Cap at 5 candidates
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def run_midday_check(extra_note: str = "", dry_run: bool = False) -> dict:
    now_et   = datetime.now(ET)
    date_str = now_et.strftime("%Y-%m-%d")
    time_str = now_et.strftime("%H:%M ET")

    # ── Market holiday guard ─────────────────────────────────────────────────
    if not is_trading_day():
        msg = f"Market closed today ({date_str}) — no midday check needed."
        print(f"🔴 {msg}")
        if not dry_run:
            try:
                strategy_log = load_json(STRATEGY_LOG_F)
                strategy_log.append({
                    "date":    date_str,
                    "type":    "midday_skipped",
                    "note":    msg,
                    "tags":    ["midday", "market-closed", "holiday"],
                })
                save_json(STRATEGY_LOG_F, strategy_log)
            except Exception:
                pass
        return {"date": date_str, "skipped": True, "reason": "market_closed"}
    # ─────────────────────────────────────────────────────────────────────────

    print(f"\n🕛 Midday Check — {date_str} {time_str}")
    print("=" * 62)

    portfolio    = load_json(PORTFOLIO_F)
    strategy_log = load_json(STRATEGY_LOG_F)

    actions_taken = []
    observations  = []

    # ── 1. Stop-loss & profit target checks ─────────────────────────────────
    print("\n📊 Checking open positions...")
    positions = portfolio.get("positions", [])

    if not positions:
        print("  No open positions — fully in cash.")
        observations.append("No open positions — fully in cash.")
    else:
        for pos in list(positions):
            ticker   = pos["ticker"]
            avg_cost = pos["avg_cost"]
            shares   = pos["shares"]

            try:
                current_price = fetch_current_price(ticker)
            except Exception as e:
                print(f"  ⚠️  Could not fetch {ticker}: {e}")
                observations.append(f"Could not fetch live price for {ticker}.")
                continue

            pnl_pct = round(((current_price - avg_cost) / avg_cost) * 100, 2)
            mkt_val = round(current_price * shares, 2)
            sign    = "+" if pnl_pct >= 0 else ""
            print(f"  {ticker}: ${current_price:.2f}  (avg cost ${avg_cost:.2f})  "
                  f"P&L: {sign}{pnl_pct:.2f}%  — ${mkt_val:,.2f} market value")

            # ── Hard stop loss ──────────────────────────────────────────────
            if pnl_pct <= STOP_LOSS_PCT:
                original_thesis = pos.get("thesis", "No thesis recorded.")
                # Brief honest assessment of what failed
                assessment = (
                    "Price breached 8% hard stop. "
                    "Entry thesis invalidated by price action. "
                    "Rule-based exit — protecting capital."
                )
                log_note = (
                    f"STOP LOSS triggered on {ticker} at {pnl_pct:.2f}%. "
                    f"Entry thesis: {original_thesis}. "
                    f"What failed: {assessment}"
                )
                print(f"  🛑 STOP LOSS: {ticker} at {pnl_pct:.2f}% — executing SELL all {shares} shares")
                success = execute_trade(
                    action="SELL", ticker=ticker, shares=shares,
                    strategy="stop_loss",
                    thesis=log_note,
                    dry_run=dry_run,
                )
                if success:
                    actions_taken.append(f"STOP LOSS: SOLD {shares}× {ticker} at {pnl_pct:.2f}% loss")
                    # Log to strategy_log
                    strategy_log.append({
                        "date":    date_str,
                        "type":    "stop_loss",
                        "note":    log_note,
                        "snapshot": {"ticker": ticker, "pnl_pct": pnl_pct,
                                     "current_price": current_price, "shares": shares},
                        "tags":    ["stop-loss", "midday", "risk-management"],
                    })

            # ── Partial profit at 15% ───────────────────────────────────────
            elif pnl_pct >= PROFIT_PCT:
                rsi    = get_rsi(ticker)
                signal = get_chart_signal(ticker)
                print(f"  💰 {ticker} up {pnl_pct:.2f}% — checking for partial profit. "
                      f"RSI={rsi}, signal={signal}")

                should_sell_half = False
                reason = ""
                if rsi is not None and rsi > RSI_OVERBOUGHT:
                    should_sell_half = True
                    reason = f"RSI {rsi:.1f} (overbought > {RSI_OVERBOUGHT})"
                elif signal in ("SELL", "STRONG_SELL"):
                    should_sell_half = True
                    reason = f"Chart signal: {signal}"

                if should_sell_half:
                    half = max(1, shares // 2)
                    log_note = (
                        f"Partial profit on {ticker} at +{pnl_pct:.2f}%. "
                        f"Selling {half} of {shares} shares. Trigger: {reason}. "
                        f"Letting remaining half run with trailing stop."
                    )
                    print(f"  📤 Selling half: {half} shares of {ticker} — {reason}")
                    success = execute_trade(
                        action="SELL", ticker=ticker, shares=half,
                        strategy="partial_profit",
                        thesis=log_note,
                        dry_run=dry_run,
                    )
                    if success:
                        actions_taken.append(
                            f"PARTIAL PROFIT: SOLD {half}× {ticker} at +{pnl_pct:.2f}% ({reason})"
                        )
                        strategy_log.append({
                            "date":    date_str,
                            "type":    "partial_profit",
                            "note":    log_note,
                            "snapshot": {"ticker": ticker, "pnl_pct": pnl_pct,
                                         "rsi": rsi, "signal": signal,
                                         "shares_sold": half, "shares_remaining": shares - half},
                            "tags":    ["partial-profit", "midday", "profit-taking"],
                        })
                else:
                    obs = (f"{ticker} up {pnl_pct:.2f}% — flagged for profit but "
                           f"RSI={rsi} (not overbought) and signal={signal}. Holding.")
                    print(f"  🟡 {obs}")
                    observations.append(obs)

    # ── 2. Thesis-breaking news scan ─────────────────────────────────────────
    # Reload portfolio in case trades were just executed
    portfolio = load_json(PORTFOLIO_F)
    positions = portfolio.get("positions", [])

    print("\n📰 Scanning for thesis-breaking news...")
    if not positions:
        print("  No positions to scan.")
    else:
        for pos in positions:
            ticker = pos["ticker"]
            headlines = search_ticker_news(ticker)
            if not headlines:
                print(f"  {ticker}: No news found.")
                continue

            print(f"  {ticker} headlines:")
            for h in headlines:
                print(f"    • {h}")

            is_breaking, reason = assess_thesis_breaking(ticker, headlines, pos)
            if is_breaking:
                log_note = (
                    f"Thesis-breaking news detected for {ticker}: {reason}. "
                    f"Original thesis: {pos.get('thesis', 'N/A')}. "
                    f"Consider early exit even if not at stop-loss. "
                    f"Flagged for review — no automated exit taken."
                )
                print(f"  ⚠️  THESIS ALERT: {reason}")
                observations.append(f"THESIS ALERT on {ticker}: {reason}")
                strategy_log.append({
                    "date":    date_str,
                    "type":    "thesis_alert",
                    "note":    log_note,
                    "snapshot": {"ticker": ticker, "headlines": headlines[:3]},
                    "tags":    ["thesis-alert", "midday", "news"],
                })
            else:
                print(f"  {ticker}: No thesis-breaking news detected.")

    # ── 3. Opportunistic entries ──────────────────────────────────────────────
    print("\n🔍 Checking for opportunistic entries...")
    portfolio = load_json(PORTFOLIO_F)
    open_count     = len(portfolio.get("positions", []))
    settled_cash   = portfolio.get("cash", 0)
    existing_tickers = {p["ticker"] for p in portfolio.get("positions", [])}

    if open_count >= MAX_POSITIONS:
        print(f"  Skipping — already at max positions ({open_count}/{MAX_POSITIONS}).")
        observations.append(f"No entry scan — at max positions ({open_count}/{MAX_POSITIONS}).")
    elif settled_cash < 2000:
        print(f"  Skipping — insufficient settled cash (${settled_cash:,.2f}).")
        observations.append(f"No entry scan — low settled cash (${settled_cash:,.2f}).")
    else:
        watchlist = get_morning_watchlist()
        if not watchlist:
            print("  No morning watchlist found.")
            observations.append("No morning watchlist available for entry scan.")
        else:
            print(f"  Reviewing {len(watchlist)} morning watchlist candidates...")
            entered = False
            for candidate in watchlist:
                ticker = candidate.get("ticker", "")
                if not ticker or ticker in existing_tickers:
                    continue

                morning_sentiment = candidate.get("sentiment", "").lower()
                if morning_sentiment not in ("bullish", "strong_buy", "buy"):
                    continue

                signal = get_chart_signal(ticker)
                print(f"  {ticker}: morning sentiment={morning_sentiment}, signal={signal}")

                if signal == "STRONG_BUY":
                    try:
                        current_price = fetch_current_price(ticker)
                        # Size: ~20% of available settled cash, at least 1 share
                        position_size = min(settled_cash * 0.20, settled_cash * 0.30)
                        shares = max(1, int(position_size // current_price))
                        cost   = round(shares * current_price, 2)

                        if cost > settled_cash:
                            print(f"  Insufficient cash for {ticker} ({shares}sh × ${current_price:.2f} = ${cost:,.2f})")
                            continue

                        log_note = (
                            f"Midday entry: {ticker}. Morning sentiment: {morning_sentiment}. "
                            f"Intraday signal: {signal}. Entry price: ${current_price:.2f}. "
                            f"Shares: {shares}. Rationale: strong morning conviction confirmed by STRONG_BUY chart signal."
                        )
                        print(f"  ✅ OPPORTUNISTIC ENTRY: {ticker} — {shares}sh @ ${current_price:.2f}")
                        success = execute_trade(
                            action="BUY", ticker=ticker, shares=shares,
                            strategy="midday_momentum",
                            thesis=log_note,
                            dry_run=dry_run,
                        )
                        if success:
                            actions_taken.append(
                                f"MIDDAY ENTRY: BUY {shares}× {ticker} @ ${current_price:.2f} (STRONG_BUY signal)"
                            )
                            strategy_log.append({
                                "date":    date_str,
                                "type":    "midday_entry",
                                "note":    log_note,
                                "snapshot": {"ticker": ticker, "shares": shares,
                                             "price": current_price, "signal": signal},
                                "tags":    ["midday-entry", "opportunistic"],
                            })
                            entered = True
                            break  # Only one midday entry per session
                    except Exception as e:
                        print(f"  ⚠️  Could not process {ticker}: {e}")

            if not entered:
                print("  No strong-enough entry signal — holding cash.")
                observations.append("No midday entry — no STRONG_BUY signals on watchlist tickers.")

    # ── 4. Log midday summary and take snapshot ──────────────────────────────
    print("\n📝 Writing midday log entry...")

    if actions_taken:
        summary = "Actions taken: " + " | ".join(actions_taken)
    else:
        summary = "No action — held all positions."

    obs_str = " | ".join(observations) if observations else "All clear."

    # Recalculate current portfolio value for the log
    portfolio = load_json(PORTFOLIO_F)
    settled_cash   = portfolio.get("cash", 0)
    unsettled_total = sum(u["amount"] for u in portfolio.get("unsettled_cash", []))
    positions_value = 0.0
    for pos in portfolio.get("positions", []):
        try:
            price = fetch_current_price(pos["ticker"])
            positions_value += price * pos["shares"]
        except Exception:
            positions_value += pos["avg_cost"] * pos["shares"]
    portfolio_value = round(settled_cash + unsettled_total + positions_value, 2)

    midday_log = (
        f"MIDDAY {date_str} {time_str} | Portfolio: ${portfolio_value:,.2f} | "
        f"{summary} | Observations: {obs_str}"
    )
    if extra_note:
        midday_log += f" | Note: {extra_note}"

    strategy_log.append({
        "date":    date_str,
        "type":    "midday_check",
        "note":    midday_log,
        "snapshot": {
            "time":             time_str,
            "portfolio_value":  portfolio_value,
            "settled_cash":     settled_cash,
            "unsettled_cash":   unsettled_total,
            "positions_value":  round(positions_value, 2),
            "actions_taken":    actions_taken,
            "observations":     observations,
        },
        "tags": ["midday", "daily-review"],
    })

    if not dry_run:
        save_json(STRATEGY_LOG_F, strategy_log)
        print("  ✅ strategy_log.json updated")

    # Take midday performance snapshot
    print("\n📸 Taking midday performance snapshot...")
    if not dry_run:
        snap_result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "simulator" / "eod_snapshot.py"), "--midday"],
            capture_output=True, text=True
        )
        if snap_result.returncode == 0:
            print(snap_result.stdout)
        else:
            print(f"  ⚠️  Snapshot warning: {snap_result.stderr}")
    else:
        print("  [DRY RUN] Would run eod_snapshot.py --midday")

    # ── 5. Conditional email — only if an action was taken ──────────────────
    if actions_taken and not dry_run:
        print("\n📧 Actions detected — building midday alert email...")
        try:
            # Reload portfolio for accurate cash snapshot
            portfolio = load_json(PORTFOLIO_F)
            settled_cash_now   = portfolio.get("cash", 0)
            unsettled_now      = sum(u["amount"] for u in portfolio.get("unsettled_cash", []))

            # Parse actions_taken strings into structured dicts for email_helper
            email_actions = []
            for a_str in actions_taken:
                entry: dict = {"ticker": "?", "price": 0.0, "pnl_pct": 0.0, "shares": 0, "reason": a_str}
                if a_str.startswith("STOP LOSS:"):
                    entry["type"] = "STOP_LOSS"
                    # e.g. "STOP LOSS: SOLD 10× XOM at -8.20% loss"
                    parts = a_str.split()
                    for i, p in enumerate(parts):
                        if p.startswith("SOLD"):
                            pass
                        if "×" in p and i > 0:
                            try:
                                entry["shares"] = int(parts[i - 1])
                            except Exception:
                                pass
                            entry["ticker"] = parts[i + 1] if i + 1 < len(parts) else "?"
                        if p.startswith("-") and "%" in p:
                            try:
                                entry["pnl_pct"] = float(p.replace("%", ""))
                            except Exception:
                                pass
                    try:
                        entry["price"] = fetch_current_price(entry["ticker"])
                    except Exception:
                        pass
                    entry["reason"] = "8% hard stop triggered — price action invalidated thesis."
                elif a_str.startswith("PARTIAL PROFIT:"):
                    entry["type"] = "PARTIAL_PROFIT"
                    # Format: "PARTIAL PROFIT: SOLD 5× NVDA at +15.20% (reason)"
                    m = re.search(r'SOLD\s+(\d+)[×x]\s+(\w+)\s+at\s+([+-][\d.]+)%', a_str)
                    if m:
                        entry["shares"]  = int(m.group(1))
                        entry["ticker"]  = m.group(2)
                        entry["pnl_pct"] = float(m.group(3))
                    try:
                        entry["price"] = fetch_current_price(entry["ticker"])
                    except Exception:
                        pass
                    entry["reason"] = (
                        f"Partial profit at {entry.get('pnl_pct', 0):+.1f}% — "
                        "letting remainder run with trailing stop."
                    )
                elif a_str.startswith("MIDDAY ENTRY:"):
                    entry["type"] = "NEW_ENTRY"
                    # e.g. "MIDDAY ENTRY: BUY 5× NVDA @ $123.45 (STRONG_BUY signal)"
                    parts = a_str.split()
                    for i, p in enumerate(parts):
                        if "×" in p and i > 0:
                            try:
                                entry["shares"] = int(parts[i - 1])
                            except Exception:
                                pass
                            entry["ticker"] = parts[i + 1] if i + 1 < len(parts) else "?"
                        if p.startswith("$") and i > 0:
                            try:
                                entry["price"] = float(p.replace("$", "").replace(",", ""))
                            except Exception:
                                pass
                    entry["reason"] = "STRONG_BUY chart signal confirmed morning sentiment."
                else:
                    entry["type"] = "NEWS_ALERT"
                    entry["reason"] = a_str

                email_actions.append(entry)

            # Calculate day P&L vs previous EOD snapshot
            try:
                performance = load_json(PERFORMANCE_F)
                eod_snaps = [s for s in performance if s.get("type", "eod") == "eod"]
                prev_val  = eod_snaps[-1]["portfolio_value"] if eod_snaps else portfolio_value
                day_pnl   = round(portfolio_value - prev_val, 2)
            except Exception:
                day_pnl = 0.0

            subject, html_body = build_midday_email(
                actions_taken=email_actions,
                portfolio_value=portfolio_value,
                settled_cash=settled_cash_now,
                positions_value=round(positions_value, 2),
                daily_pnl=day_pnl,
                date_str=date_str,
                time_str=time_str,
            )
            send_email_via_gmail_mcp(subject, html_body)
            print("  ✅ Midday email queued (pending_email.json written)")
        except Exception as e:
            print(f"  ⚠️  Could not build midday email: {e}")
    elif not dry_run:
        # Log that no email was sent
        print("\n📭 No midday email sent — no actions taken")
        try:
            strategy_log = load_json(STRATEGY_LOG_F)
            strategy_log.append({
                "date": date_str,
                "type": "midday_email_skipped",
                "note": "No midday email sent — no actions taken",
                "tags": ["midday", "email", "no-action"],
            })
            save_json(STRATEGY_LOG_F, strategy_log)
        except Exception:
            pass

    print("\n" + "=" * 62)
    print(f"✅ Midday check complete")
    print(f"   Portfolio value : ${portfolio_value:,.2f}")
    print(f"   Actions taken   : {len(actions_taken)}")
    if actions_taken:
        for a in actions_taken:
            print(f"     • {a}")
    print(f"   Observations    : {len(observations)}")

    return {
        "date":            date_str,
        "time":            time_str,
        "portfolio_value": portfolio_value,
        "actions_taken":   actions_taken,
        "observations":    observations,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Midday portfolio check — stop loss, profit taking, news, opportunistic entries"
    )
    parser.add_argument("--note",    default="", help="Optional manual note appended to log")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned actions without executing trades or writing files")
    args = parser.parse_args()

    run_midday_check(extra_note=args.note, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
