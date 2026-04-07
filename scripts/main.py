#!/usr/bin/env python3
"""
scripts/main.py — Trade signal queuing for the morning brief (Phase 1).

Called after the morning analysis is complete. Reads the analysis JSON output,
identifies BUY/STRONG_BUY candidates from the watchlist, runs chart analysis
to confirm signals, sizes positions, and writes candidates to
simulator/pending_trades.json for Phase 2 execution at market open (8:35 AM CT).

Trades are NOT executed here — they are queued. Actual execution happens in
simulator/market_open_execution.py at 8:35 AM CT using real market-open prices.

Usage:
    # Queue from the most recent analysis report:
    python3 scripts/main.py

    # Queue from a specific analysis JSON:
    python3 scripts/main.py --analysis-file reports/2026-04-07.json

    # Dry run — show what would be queued without writing:
    python3 scripts/main.py --dry-run

    # Queue a specific ticker manually (overrides analysis file):
    python3 scripts/main.py --ticker NVDA --signal STRONG_BUY --condition opens_above --threshold 875.00

Position sizing:
    ~10% of available settled cash per trade, max 3 new positions total.
    Skips tickers already held. Skips if settled cash insufficient.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz
import yfinance as yf

REPO_ROOT        = Path(__file__).parent.parent
PORTFOLIO_F      = REPO_ROOT / "simulator" / "portfolio.json"
PENDING_TRADES_F = REPO_ROOT / "simulator" / "pending_trades.json"
REPORTS_DIR      = REPO_ROOT / "reports"

CT = pytz.timezone("America/Chicago")

POSITION_SIZE_PCT = 0.10   # 10% of settled cash per trade
MAX_NEW_POSITIONS = 3      # never queue more than 3 trades at once
MAX_TOTAL_POSITIONS = 3    # hard cap including existing positions

# Chart signals eligible for queuing (strongest first)
ELIGIBLE_SIGNALS = {"STRONG_BUY", "BUY"}

# Watchlist actions from the morning brief analysis that are candidates
ELIGIBLE_ACTIONS = {"WATCH_LONG"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> list | dict:
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def get_latest_analysis() -> dict | None:
    """Return the most recent analysis JSON from reports/, or None."""
    if not REPORTS_DIR.exists():
        return None
    json_files = sorted(REPORTS_DIR.glob("*.json"), reverse=True)
    for f in json_files:
        try:
            data = load_json(f)
            if isinstance(data, dict) and "watchlist" in data:
                return data
        except Exception:
            continue
    return None


def get_chart_signal(ticker: str) -> tuple[str | None, dict]:
    """
    Run chart_analysis.py and return (signal_str, full_data_dict).
    signal_str is one of: STRONG_BUY, BUY, NEUTRAL, SELL, STRONG_SELL, or None on error.
    """
    script = REPO_ROOT / "simulator" / "chart_analysis.py"
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--ticker", ticker, "--json"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout.strip())
            signal = data.get("composite", {}).get("signal")
            return signal, data
    except Exception:
        pass
    return None, {}


def fetch_price(ticker: str) -> float | None:
    """Fetch last known price via yfinance."""
    try:
        t = yf.Ticker(ticker.upper())
        price = t.fast_info.last_price
        if price and float(price) > 0:
            return round(float(price), 4)
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
    return None


def compute_shares(settled_cash: float, price: float, pct: float = POSITION_SIZE_PCT) -> int:
    """Return the number of whole shares for a given cash percentage."""
    if price <= 0:
        return 0
    target_value = settled_cash * pct
    return max(1, int(target_value // price))


# ---------------------------------------------------------------------------
# Core queuing logic
# ---------------------------------------------------------------------------

def build_pending_trades(
    watchlist_candidates: list[dict],
    portfolio: dict,
    dry_run: bool = False,
) -> list[dict]:
    """
    Evaluate watchlist candidates, run chart analysis, and build the list of
    pending trades to write to pending_trades.json.

    watchlist_candidates: list of dicts with keys:
        ticker, action (WATCH_LONG), catalyst, entry_idea, risk
        (from the analysis JSON watchlist section)

    portfolio: current portfolio dict (portfolio.json)
    """
    now_ct   = datetime.now(CT)
    gen_at   = now_ct.strftime("%Y-%m-%dT%H:%M:%S")

    settled_cash      = portfolio.get("cash", 0)
    existing_positions = {p["ticker"].upper() for p in portfolio.get("positions", [])}
    open_count         = len(existing_positions)

    pending_trades  = []
    queued_count    = 0
    cash_committed  = 0.0

    print(f"\n🔍 Trade Signal Queuing — {gen_at}")
    print(f"   Settled cash:     ${settled_cash:,.2f}")
    print(f"   Open positions:   {open_count} / {MAX_TOTAL_POSITIONS}")
    print(f"   Candidates:       {len(watchlist_candidates)}")
    print("=" * 62)

    for candidate in watchlist_candidates:
        ticker    = candidate.get("ticker", "").upper()
        action_raw = candidate.get("action", "").upper()
        catalyst  = candidate.get("catalyst", "")
        entry_idea = candidate.get("entry_idea", "")
        risk      = candidate.get("risk", "")

        if not ticker:
            continue

        # Only process WATCH_LONG signals (we're long-only)
        if action_raw not in ELIGIBLE_ACTIONS:
            print(f"  ⬜ {ticker}: skipped (action={action_raw}, not WATCH_LONG)")
            continue

        # Skip if already holding this ticker
        if ticker in existing_positions:
            print(f"  ⬜ {ticker}: already in portfolio — skipping")
            continue

        # Check max position count (existing + already queued)
        slots_used = open_count + queued_count
        if slots_used >= MAX_TOTAL_POSITIONS:
            print(f"  🚫 {ticker}: max positions reached ({slots_used}/{MAX_TOTAL_POSITIONS}) — stopping")
            break

        if queued_count >= MAX_NEW_POSITIONS:
            print(f"  🚫 {ticker}: max new queued trades reached ({MAX_NEW_POSITIONS}) — stopping")
            break

        print(f"\n  🔎 {ticker}: checking chart signal...")

        # Run chart analysis
        signal, chart_data = get_chart_signal(ticker)
        rsi      = chart_data.get("rsi", {}).get("value")
        pattern  = chart_data.get("pattern", "")

        print(f"     Chart signal: {signal}   RSI: {rsi}")

        if signal not in ELIGIBLE_SIGNALS:
            print(f"     ⏭  Signal '{signal}' not eligible (need STRONG_BUY or BUY)")
            continue

        # Avoid overbought entries on RSI
        if rsi is not None and float(rsi) > 70:
            print(f"     ⚠️  RSI {rsi:.1f} is overbought (>70) — skipping to wait for pullback")
            continue

        # Fetch current pre-market price for sizing
        price = fetch_price(ticker)
        if not price:
            print(f"     ⚠️  Could not fetch price for {ticker} — skipping")
            continue

        print(f"     Pre-market price: ${price:.2f}")

        # Position sizing: 10% of settled cash (minus already-committed cash)
        available_cash = settled_cash - cash_committed
        shares = compute_shares(available_cash, price, POSITION_SIZE_PCT)
        cost   = round(shares * price, 2)

        if cost > available_cash:
            print(f"     ⚠️  Insufficient cash for {shares}sh × ${price:.2f} = ${cost:,.2f} "
                  f"(available ${available_cash:,.2f})")
            continue

        if shares <= 0:
            print(f"     ⚠️  Computed 0 shares — insufficient cash")
            continue

        # Determine entry condition from entry_idea text
        # Common patterns: "above $X", "breaks $X", "opens above $X"
        entry_condition = "opens_above"
        entry_threshold = None

        import re
        threshold_match = re.search(
            r'(?:above|breaks?|over)\s+\$?([\d,]+(?:\.\d+)?)',
            entry_idea, re.IGNORECASE
        )
        if threshold_match:
            try:
                entry_threshold = float(threshold_match.group(1).replace(",", ""))
            except ValueError:
                pass

        if entry_threshold is None:
            # No specific threshold found — use market_open (execute unconditionally)
            entry_condition = "market_open"
            entry_threshold = price  # informational only

        # Compute stop/target prices
        stop_loss_pct = 8.0
        target_pct    = 15.0
        stop_price    = round(price * (1 - stop_loss_pct / 100), 2)
        target_price  = round(price * (1 + target_pct / 100), 2)

        trade_record = {
            "ticker":                ticker,
            "action":                "BUY",
            "entry_condition":       entry_condition,
            "entry_price_threshold": entry_threshold,
            "shares":                shares,
            "estimated_price":       price,
            "estimated_cost":        cost,
            "stop_loss_pct":         stop_loss_pct,
            "stop_price_estimate":   stop_price,
            "target_pct":            target_pct,
            "target_price_estimate": target_price,
            "setup_type":            pattern or "morning_brief_signal",
            "timeframe":             "swing",
            "signal_strength":       signal,
            "catalyst":              catalyst,
            "entry_idea":            entry_idea,
            "risk":                  risk,
            "generated_at":          gen_at,
        }

        print(f"     ✅ QUEUED: BUY {shares}sh @ ~${price:.2f}  "
              f"(${cost:,.2f}  |  condition: {entry_condition}  "
              f"threshold: ${entry_threshold:.2f})")

        pending_trades.append(trade_record)
        cash_committed += cost
        queued_count   += 1

    print(f"\n{'=' * 62}")
    print(f"Queuing complete: {queued_count} trade(s) queued")
    if queued_count:
        print(f"  Estimated cash commitment: ${cash_committed:,.2f}")
        print(f"  Remaining settled cash:    ${settled_cash - cash_committed:,.2f}")

    return pending_trades


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Queue morning brief trade signals to simulator/pending_trades.json"
    )
    parser.add_argument(
        "--analysis-file", default=None,
        help="Path to analysis JSON file (default: most recent reports/YYYY-MM-DD.json)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be queued without writing pending_trades.json"
    )
    # Manual override: queue a specific ticker directly
    parser.add_argument("--ticker",     default=None, help="Manual: specific ticker to queue")
    parser.add_argument("--signal",     default="BUY", help="Manual: signal strength (BUY|STRONG_BUY)")
    parser.add_argument("--condition",  default="market_open", help="Manual: entry condition")
    parser.add_argument("--threshold",  default=None, type=float, help="Manual: entry price threshold")
    parser.add_argument("--shares",     default=None, type=int, help="Manual: number of shares")
    args = parser.parse_args()

    # ── Manual ticker mode ───────────────────────────────────────────────────
    if args.ticker:
        ticker = args.ticker.upper()
        now_ct = datetime.now(CT)
        gen_at = now_ct.strftime("%Y-%m-%dT%H:%M:%S")

        if args.shares:
            shares = args.shares
            price  = fetch_price(ticker) or 0.0
        else:
            price  = fetch_price(ticker) or 0.0
            portfolio = load_json(PORTFOLIO_F)
            settled_cash = portfolio.get("cash", 0)
            shares = compute_shares(settled_cash, price) if price > 0 else 0

        pending = [{
            "ticker":                ticker,
            "action":                "BUY",
            "entry_condition":       args.condition,
            "entry_price_threshold": args.threshold or price,
            "shares":                shares,
            "estimated_price":       price,
            "stop_loss_pct":         8.0,
            "target_pct":            15.0,
            "setup_type":            "manual",
            "timeframe":             "swing",
            "signal_strength":       args.signal,
            "generated_at":          gen_at,
        }]

        print(f"Manual queue: {ticker} — {shares}sh, condition={args.condition}, "
              f"threshold=${args.threshold or price:.2f}")

        if not args.dry_run:
            save_json(PENDING_TRADES_F, pending)
            print(f"✅ Written to {PENDING_TRADES_F}")
        else:
            print("[DRY RUN] Would write:")
            print(json.dumps(pending, indent=2))
        return

    # ── Analysis-driven mode ─────────────────────────────────────────────────
    if args.analysis_file:
        analysis = load_json(Path(args.analysis_file))
    else:
        analysis = get_latest_analysis()

    if not analysis:
        print("❌ No analysis JSON found. Run the morning brief first, or pass --analysis-file.")
        sys.exit(1)

    watchlist = analysis.get("watchlist", [])
    if not watchlist:
        print("⚠️  No watchlist in analysis — nothing to queue.")
        if not args.dry_run:
            save_json(PENDING_TRADES_F, [])
        return

    # Load portfolio
    try:
        portfolio = load_json(PORTFOLIO_F)
    except FileNotFoundError:
        print(f"❌ Could not read portfolio from {PORTFOLIO_F}")
        sys.exit(1)

    # Build pending trades
    pending_trades = build_pending_trades(watchlist, portfolio, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN] Would write to pending_trades.json:")
        print(json.dumps(pending_trades, indent=2))
        return

    # Write to pending_trades.json
    save_json(PENDING_TRADES_F, pending_trades)
    print(f"\n✅ {len(pending_trades)} trade(s) written to {PENDING_TRADES_F}")
    print("   Phase 2 execution runs at 8:35 AM CT via market_open_execution.py")

    if pending_trades:
        print("\n   Queued:")
        for t in pending_trades:
            print(f"   • {t['ticker']}: BUY {t['shares']}sh  "
                  f"condition={t['entry_condition']}  "
                  f"threshold=${t['entry_price_threshold']:.2f}  "
                  f"signal={t['signal_strength']}")


if __name__ == "__main__":
    main()
