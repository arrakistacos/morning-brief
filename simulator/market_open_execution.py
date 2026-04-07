#!/usr/bin/env python3
"""
market_open_execution.py — Phase 2 of two-phase trade execution.

Runs at 8:35 AM CT (5 minutes after NYSE open) on weekdays.

Design philosophy:
  Phase 1 (4:45 AM CT, morning brief): Analyze overnight news → identify
    high-conviction setups → write candidates to pending_trades.json.
    NO trades are executed at pre-market prices.

  Phase 2 (8:35 AM CT, this script): Read pending_trades.json → fetch real
    market-open prices → check entry conditions → execute or skip.
    All fills reflect ACTUAL current prices, including slippage.

Entry condition logic:
  "opens_above"  — Execute if current_price >= entry_price_threshold.
                   Adverse gap guard: if current_price > threshold * 1.03
                   (stock gapped >3% through the entry), SKIP and log
                   "adverse gap — chasing at this price is too risky".
                   Slippage: if price moved past threshold before 8:35
                   but within the 3% gap limit, still execute and log
                   the slippage honestly.
  "market_open"  — Always execute at whatever the current price is.
                   No condition check; just get the real open print.

Usage:
    python simulator/market_open_execution.py
    python simulator/market_open_execution.py --dry-run
    python simulator/market_open_execution.py --force   # skip holiday guard
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz
import yfinance as yf

from market_calendar import is_trading_day
from email_helper import send_email_via_gmail_mcp, DUNE_STYLES, _html_wrap

# ---------------------------------------------------------------------------
REPO_ROOT         = Path(__file__).parent.parent
PENDING_TRADES_F  = REPO_ROOT / "simulator" / "pending_trades.json"
PORTFOLIO_F       = REPO_ROOT / "simulator" / "portfolio.json"
STRATEGY_LOG_F    = REPO_ROOT / "simulator" / "strategy_log.json"
TRADES_F          = REPO_ROOT / "simulator" / "trades.json"

CT = pytz.timezone("America/Chicago")
ET = pytz.timezone("America/New_York")

# Adverse gap threshold: if price is more than this % above the threshold,
# the stock gapped too far — skip rather than chase.
ADVERSE_GAP_PCT = 3.0
# ---------------------------------------------------------------------------


def load_json(path: Path) -> list | dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_current_price(ticker: str) -> float:
    """Fetch the current market price via yfinance."""
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
        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if price:
            return round(float(price), 4)
    except Exception:
        pass
    raise ValueError(f"Could not fetch price for {ticker}")


def execute_trade_subprocess(
    action: str,
    ticker: str,
    shares: int,
    strategy: str,
    thesis: str,
    setup_type: str,
    timeframe: str,
    stop_loss_pct: float,
    target_pct: float,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """
    Call execute_trade.py as a subprocess.
    Returns (success: bool, output: str).
    """
    cmd = [
        sys.executable,
        str(REPO_ROOT / "simulator" / "execute_trade.py"),
        "--action", action,
        "--ticker", ticker,
        "--shares", str(shares),
        "--strategy", strategy,
        "--thesis", thesis,
        "--setup-type", setup_type,
        "--timeframe", timeframe,
        "--stop-loss-pct", str(stop_loss_pct),
        "--target-pct", str(target_pct),
        "--force",  # market-open check already done by this script
    ]
    if dry_run:
        return True, f"[DRY RUN] Would run: {' '.join(cmd)}"

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def check_entry_condition(
    trade: dict,
    current_price: float,
) -> tuple[bool, str, bool]:
    """
    Evaluate whether a pending trade's entry condition is met.

    Returns:
        (should_execute: bool, reason: str, is_adverse_gap: bool)

    should_execute=True  → go ahead and fill
    is_adverse_gap=True  → condition not met because of a big gap up (>3%)
    """
    condition   = trade.get("entry_condition", "market_open").lower()
    threshold   = trade.get("entry_price_threshold")

    if condition == "market_open" or threshold is None:
        return True, "market_open — no condition, buying at open price", False

    if condition == "opens_above":
        if current_price >= threshold:
            gap_pct = ((current_price - threshold) / threshold) * 100
            if gap_pct > ADVERSE_GAP_PCT:
                reason = (
                    f"adverse gap — stock opened {gap_pct:.1f}% above threshold "
                    f"(${current_price:.2f} vs ${threshold:.2f}); "
                    f"gap exceeds {ADVERSE_GAP_PCT:.0f}% limit — skipping to avoid chasing"
                )
                return False, reason, True
            # Slippage: price moved past threshold but within the gap limit
            if gap_pct > 0:
                reason = (
                    f"condition met with slippage — price ${current_price:.2f} is "
                    f"{gap_pct:.2f}% above threshold ${threshold:.2f} (slippage is real)"
                )
            else:
                reason = f"condition met — price ${current_price:.2f} >= threshold ${threshold:.2f}"
            return True, reason, False
        else:
            reason = (
                f"entry not triggered — price ${current_price:.2f} < threshold ${threshold:.2f}"
            )
            return False, reason, False

    if condition == "opens_below":
        if current_price <= threshold:
            reason = f"condition met — price ${current_price:.2f} <= threshold ${threshold:.2f}"
            return True, reason, False
        else:
            reason = (
                f"entry not triggered — price ${current_price:.2f} > threshold ${threshold:.2f}"
            )
            return False, reason, False

    # Unknown condition — treat as market_open (execute)
    return True, f"unknown condition '{condition}' — executing at market open price", False


def process_pending_trades(dry_run: bool = False) -> dict:
    """
    Core execution loop. Returns a results dict for email/logging.
    """
    now_ct   = datetime.now(CT)
    date_str = now_ct.strftime("%Y-%m-%d")
    time_str = now_ct.strftime("%H:%M CT")

    # ── Load pending trades ─────────────────────────────────────────────────
    if not PENDING_TRADES_F.exists():
        print("📭 No pending_trades.json found — nothing to execute.")
        return {
            "date": date_str,
            "time": time_str,
            "executed": [],
            "skipped": [],
            "errors": [],
        }

    pending = load_json(PENDING_TRADES_F)
    if not pending:
        print("📭 pending_trades.json is empty — nothing to execute.")
        _clear_pending(dry_run)
        return {
            "date": date_str,
            "time": time_str,
            "executed": [],
            "skipped": [],
            "errors": [],
        }

    print(f"\n🔔 Market-Open Execution — {date_str} {time_str}")
    print(f"   Processing {len(pending)} pending trade(s)...")
    print("=" * 62)

    executed = []   # list of result dicts
    skipped  = []   # list of result dicts
    errors   = []   # list of result dicts

    for trade in pending:
        ticker    = trade.get("ticker", "?").upper()
        action    = trade.get("action", "BUY").upper()
        shares    = trade.get("shares", 0)
        setup     = trade.get("setup_type", "morning_brief_signal")
        timeframe = trade.get("timeframe", "swing")
        stop_pct  = float(trade.get("stop_loss_pct", 8.0))
        tgt_pct   = float(trade.get("target_pct", 15.0))
        signal    = trade.get("signal_strength", "BUY")
        gen_at    = trade.get("generated_at", "unknown")

        print(f"\n  → {ticker}: {action} {shares} shares  (queued at {gen_at})")
        print(f"     Setup: {setup}  |  Signal: {signal}")

        # Fetch real market price
        try:
            current_price = fetch_current_price(ticker)
            print(f"     Current price: ${current_price:.2f}")
        except ValueError as e:
            msg = f"Could not fetch price: {e}"
            print(f"     ❌ ERROR: {msg}")
            errors.append({
                "ticker": ticker,
                "action": action,
                "shares": shares,
                "error": msg,
                "queued_at": gen_at,
            })
            continue

        # Evaluate entry condition
        should_execute, condition_reason, is_adverse_gap = check_entry_condition(
            trade, current_price
        )

        if not should_execute:
            tag = "adverse_gap" if is_adverse_gap else "entry_not_triggered"
            print(f"     ⏭  SKIPPED — {condition_reason}")
            skipped.append({
                "ticker":         ticker,
                "action":         action,
                "shares":         shares,
                "current_price":  current_price,
                "threshold":      trade.get("entry_price_threshold"),
                "reason":         condition_reason,
                "skip_type":      tag,
                "queued_at":      gen_at,
            })
            continue

        # ── Execute the trade ────────────────────────────────────────────────
        print(f"     ✅ Condition: {condition_reason}")
        thesis = (
            f"Market-open execution of morning brief signal. "
            f"Signal strength: {signal}. Setup: {setup}. "
            f"Entry condition: {condition_reason}. "
            f"Queued at {gen_at}, executed at {time_str}."
        )

        success, output = execute_trade_subprocess(
            action       = action,
            ticker       = ticker,
            shares       = shares,
            strategy     = f"morning_brief_{setup}",
            thesis       = thesis,
            setup_type   = setup,
            timeframe    = timeframe,
            stop_loss_pct= stop_pct,
            target_pct   = tgt_pct,
            dry_run      = dry_run,
        )

        if success:
            print(f"     🟢 EXECUTED: {action} {shares}× {ticker} @ ${current_price:.2f}")
            executed.append({
                "ticker":         ticker,
                "action":         action,
                "shares":         shares,
                "execution_price": current_price,
                "threshold":      trade.get("entry_price_threshold"),
                "condition_note": condition_reason,
                "setup":          setup,
                "signal":         signal,
                "queued_at":      gen_at,
                "executed_at":    time_str,
            })
        else:
            print(f"     ❌ Trade failed:\n{output}")
            errors.append({
                "ticker":         ticker,
                "action":         action,
                "shares":         shares,
                "current_price":  current_price,
                "error":          output,
                "queued_at":      gen_at,
            })

    # ── Clear pending_trades.json ────────────────────────────────────────────
    _clear_pending(dry_run)

    # ── Write to strategy_log.json ───────────────────────────────────────────
    _log_results(date_str, time_str, executed, skipped, errors, dry_run)

    return {
        "date":     date_str,
        "time":     time_str,
        "executed": executed,
        "skipped":  skipped,
        "errors":   errors,
    }


def _clear_pending(dry_run: bool) -> None:
    if dry_run:
        print("\n  [DRY RUN] Would clear pending_trades.json")
        return
    save_json(PENDING_TRADES_F, [])
    print(f"\n  🗑  pending_trades.json cleared")


def _log_results(
    date_str: str,
    time_str: str,
    executed: list,
    skipped: list,
    errors: list,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    try:
        strategy_log = load_json(STRATEGY_LOG_F)
        note_parts = []
        if executed:
            note_parts.append(
                "Executed: "
                + "; ".join(
                    f"{e['action']} {e['shares']}× {e['ticker']} @ ${e['execution_price']:.2f}"
                    for e in executed
                )
            )
        if skipped:
            note_parts.append(
                "Skipped: "
                + "; ".join(
                    f"{s['ticker']} ({s['reason'][:60]}...)" if len(s['reason']) > 60
                    else f"{s['ticker']} ({s['reason']})"
                    for s in skipped
                )
            )
        if errors:
            note_parts.append(
                "Errors: " + "; ".join(e['ticker'] for e in errors)
            )

        strategy_log.append({
            "date":     date_str,
            "type":     "market_open_execution",
            "note":     f"Market-open execution {date_str} {time_str}: "
                        + " | ".join(note_parts) if note_parts else "No trades processed.",
            "snapshot": {
                "time":     time_str,
                "executed": executed,
                "skipped":  skipped,
                "errors":   errors,
            },
            "tags": ["market-open", "execution", "phase2"],
        })
        save_json(STRATEGY_LOG_F, strategy_log)
        print("  📝 strategy_log.json updated")
    except Exception as e:
        print(f"  ⚠️  Could not write strategy log: {e}")


# ---------------------------------------------------------------------------
# Email builder
# ---------------------------------------------------------------------------

def build_execution_email(
    results: dict,
    portfolio_value: float,
    settled_cash: float,
) -> tuple[str, str]:
    """Build the market-open execution summary email."""
    date_str  = results["date"]
    time_str  = results["time"]
    executed  = results["executed"]
    skipped   = results["skipped"]
    errors    = results["errors"]

    # Subject
    if executed:
        first = executed[0]
        subj_action = (
            f"{first['action']} {first['shares']}× {first['ticker']} "
            f"@ ${first['execution_price']:.2f}"
        )
        if len(executed) > 1:
            subj_action += f" +{len(executed)-1} more"
        subject = f"📈 Market-Open Execution — {subj_action}"
    elif skipped:
        subject = (
            f"⏭ Market-Open — {len(skipped)} signal(s) skipped "
            f"({skipped[0]['ticker']}...)"
        )
    else:
        subject = f"📭 Market-Open Execution — No trades today ({date_str})"

    # Build cards
    cards_html = ""

    for e in executed:
        threshold = e.get("threshold")
        thresh_str = f" (threshold ${threshold:.2f})" if threshold else ""
        cards_html += f"""
<div class="card new-entry">
  <span class="badge badge-entry">EXECUTED</span>
  <div class="ticker">{e['ticker']}</div>
  <div class="detail">
    {e['action']} {e['shares']} shares @ <strong>${e['execution_price']:.2f}</strong>{thresh_str}<br>
    Setup: {e['setup']} &nbsp;|&nbsp; Signal: {e['signal']}<br>
    <em style="color:#6b8a5a;">{e['condition_note']}</em>
  </div>
</div>"""

    for s in skipped:
        threshold = s.get("threshold")
        current   = s.get("current_price", 0)
        thresh_str = f"threshold ${threshold:.2f}" if threshold else "no threshold"
        skip_class = "card stop-loss" if s.get("skip_type") == "adverse_gap" else "card"
        badge_text = "ADVERSE GAP" if s.get("skip_type") == "adverse_gap" else "SKIPPED"
        badge_class = "badge-stop" if s.get("skip_type") == "adverse_gap" else "badge-news"
        cards_html += f"""
<div class="{skip_class}" style="border-left-color:#5a5a8b;">
  <span class="badge {badge_class}">{badge_text}</span>
  <div class="ticker">{s['ticker']}</div>
  <div class="detail">
    Opened at ${current:.2f} &nbsp;|&nbsp; {thresh_str}<br>
    <em style="color:#6b5a3e;">{s['reason']}</em>
  </div>
</div>"""

    for er in errors:
        cards_html += f"""
<div class="card stop-loss">
  <span class="badge badge-stop">ERROR</span>
  <div class="ticker">{er['ticker']}</div>
  <div class="detail">
    {er.get('error', 'Unknown error')[:200]}
  </div>
</div>"""

    if not cards_html:
        cards_html = '<p style="color:#6b5a3e;font-size:12px;margin:0;">No pending trades were queued by the morning brief today.</p>'

    # Portfolio snapshot
    snap_html = f"""
<div class="summary-row">
  <span class="label">Portfolio Value (approx)</span>
  <span class="value">${portfolio_value:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Settled Cash</span>
  <span class="value">${settled_cash:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Executed</span>
  <span class="value" style="color:#90ee90;">{len(executed)}</span>
</div>
<div class="summary-row">
  <span class="label">Skipped</span>
  <span class="value" style="color:#c8b89a;">{len(skipped)}</span>
</div>"""
    if errors:
        snap_html += f"""
<div class="summary-row">
  <span class="label">Errors</span>
  <span class="value" style="color:#ee9090;">{len(errors)}</span>
</div>"""

    body_html = f"""
<div class="section">
  <h2>📈 Execution Results — {date_str} {time_str}</h2>
  {cards_html}
</div>
<div class="section">
  <h2>💼 Portfolio Snapshot</h2>
  {snap_html}
</div>"""

    html = _html_wrap(
        title="📈 Market-Open Execution",
        subtitle=f"{date_str} &nbsp;|&nbsp; {time_str} &nbsp;|&nbsp; Phase 2 of 2",
        body_html=body_html,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Market-open Phase 2 execution — fill pending trades at real open prices"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned actions without writing files or executing trades"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Skip the NYSE holiday guard (useful for manual testing)"
    )
    args = parser.parse_args()

    now_ct   = datetime.now(CT)
    date_str = now_ct.strftime("%Y-%m-%d")

    # ── NYSE holiday guard ───────────────────────────────────────────────────
    if not args.force and not is_trading_day():
        msg = f"Market closed today ({date_str}) — skipping market-open execution."
        print(f"🔴 {msg}")
        # Note in log if pending_trades.json has anything
        if PENDING_TRADES_F.exists():
            try:
                pending = load_json(PENDING_TRADES_F)
                if pending:
                    strategy_log = load_json(STRATEGY_LOG_F)
                    strategy_log.append({
                        "date":   date_str,
                        "type":   "market_open_skipped",
                        "note":   f"{msg} {len(pending)} pending trade(s) were NOT executed.",
                        "tags":   ["market-open", "market-closed", "holiday"],
                    })
                    save_json(STRATEGY_LOG_F, strategy_log)
                    # Clear pending (they were for today's open — stale tomorrow)
                    save_json(PENDING_TRADES_F, [])
                    print(f"  ⚠️  {len(pending)} stale pending trade(s) cleared.")
            except Exception:
                pass
        return
    # ─────────────────────────────────────────────────────────────────────────

    # ── Run execution loop ───────────────────────────────────────────────────
    results = process_pending_trades(dry_run=args.dry_run)

    # ── Summary output ───────────────────────────────────────────────────────
    executed = results["executed"]
    skipped  = results["skipped"]
    errors   = results["errors"]

    print("\n" + "=" * 62)
    print(f"✅ Market-open execution complete — {results['date']} {results['time']}")
    print(f"   Executed : {len(executed)}")
    for e in executed:
        print(f"     🟢 {e['action']} {e['shares']}× {e['ticker']} @ ${e['execution_price']:.2f}")
    print(f"   Skipped  : {len(skipped)}")
    for s in skipped:
        print(f"     ⏭  {s['ticker']} — {s['reason'][:70]}")
    if errors:
        print(f"   Errors   : {len(errors)}")
        for er in errors:
            print(f"     ❌ {er['ticker']}: {er['error'][:60]}")

    # ── Send email (always — even if no trades, brief confirmation is useful) ─
    if not args.dry_run:
        try:
            portfolio = load_json(PORTFOLIO_F)
            settled_cash    = portfolio.get("cash", 0)
            unsettled_total = sum(u["amount"] for u in portfolio.get("unsettled_cash", []))
            # Quick portfolio value estimate (cost basis for positions, no live price fetch)
            positions_value = sum(
                p["avg_cost"] * p["shares"] for p in portfolio.get("positions", [])
            )
            portfolio_value = round(settled_cash + unsettled_total + positions_value, 2)

            subject, html_body = build_execution_email(results, portfolio_value, settled_cash)
            send_email_via_gmail_mcp(subject, html_body)
            print(f"\n📧 Email queued: {subject}")
        except Exception as e:
            print(f"\n⚠️  Could not build/queue execution email: {e}")
    else:
        print("\n  [DRY RUN] Would send execution summary email.")


if __name__ == "__main__":
    main()
