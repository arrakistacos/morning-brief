#!/usr/bin/env python3
"""
email_helper.py — Shared email dispatch helper for the paper trading simulator.

Provides send_email_via_gmail_mcp(subject, html_body) which:
  1. Builds a pending_email.json artifact in the simulator directory
  2. Prints a sentinel line so the scheduled-task skill knows to pick it up
  3. The running Claude agent then calls gmail_create_draft (Gmail MCP) and
     uses Claude in Chrome to navigate to Gmail drafts and click Send.

To:  capt.computermail@gmail.com
"""

import json
from pathlib import Path

REPO_ROOT     = Path(__file__).parent.parent
PENDING_EMAIL = REPO_ROOT / "simulator" / "pending_email.json"
TO_EMAIL      = "capt.computermail@gmail.com"


def send_email_via_gmail_mcp(subject: str, html_body: str) -> None:
    """
    Write the email payload to pending_email.json and print the sentinel.
    The scheduled-task skill reads this file and calls gmail_create_draft +
    Claude in Chrome to complete delivery.

    Args:
        subject:   Email subject line.
        html_body: Full HTML body string (inline CSS, mobile-friendly).
    """
    payload = {
        "to":        TO_EMAIL,
        "subject":   subject,
        "html_body": html_body,
    }
    with open(PENDING_EMAIL, "w") as f:
        json.dump(payload, f, indent=2)

    # Sentinel parsed by the skill runner
    print(f"EMAIL_PENDING: {subject}")
    print(f"  → Written to {PENDING_EMAIL}")


# ---------------------------------------------------------------------------
# Shared HTML building blocks (Dune dark theme — matches morning brief style)
# ---------------------------------------------------------------------------

DUNE_STYLES = """
body{margin:0;padding:0;background:#0d0d0d;font-family:'Georgia',serif;color:#c8b89a;}
.wrapper{max-width:600px;margin:0 auto;background:#111;border:1px solid #2a2a1e;}
.header{background:#0a0a0a;border-bottom:2px solid #8b6914;padding:16px 24px;text-align:center;}
.header h1{margin:0;font-size:20px;color:#c8961e;letter-spacing:2px;text-transform:uppercase;}
.header p{margin:4px 0 0;font-size:11px;color:#6b5a3e;letter-spacing:1px;}
.section{padding:16px 24px;border-bottom:1px solid #1e1e14;}
.section h2{margin:0 0 10px;font-size:13px;color:#8b6914;letter-spacing:1px;text-transform:uppercase;
            border-bottom:1px solid #2a2a1e;padding-bottom:6px;}
.card{background:#0d0d08;border:1px solid #2a2a1e;border-left:3px solid #8b6914;
      padding:12px 14px;margin-bottom:10px;border-radius:2px;}
.card.stop-loss{border-left-color:#8b1414;}
.card.partial-profit{border-left-color:#b8860b;}
.card.new-entry{border-left-color:#148b14;}
.card.news-alert{border-left-color:#8b6914;}
.card .badge{display:inline-block;padding:2px 8px;font-size:10px;font-weight:bold;
             letter-spacing:1px;border-radius:2px;margin-bottom:6px;}
.badge-stop{background:#8b1414;color:#ffd0d0;}
.badge-profit{background:#4a3000;color:#f0c040;}
.badge-entry{background:#1a4a1a;color:#90ee90;}
.badge-news{background:#4a3a00;color:#c8a040;}
.card .ticker{font-size:18px;font-weight:bold;color:#c8961e;margin:0 0 4px;}
.card .detail{font-size:12px;color:#8a7a64;line-height:1.6;}
.card .pnl-pos{color:#90ee90;}
.card .pnl-neg{color:#ee9090;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{background:#0a0a0a;color:#8b6914;text-align:left;padding:6px 8px;
   border-bottom:1px solid #2a2a1e;letter-spacing:1px;font-size:10px;text-transform:uppercase;}
td{padding:6px 8px;border-bottom:1px solid #1a1a10;color:#b0a088;}
tr:last-child td{border-bottom:none;}
.summary-row{display:flex;justify-content:space-between;padding:4px 0;
             border-bottom:1px solid #1a1a10;font-size:12px;}
.summary-row .label{color:#6b5a3e;}
.summary-row .value{color:#c8b89a;font-weight:bold;}
.footer{padding:12px 24px;text-align:center;background:#0a0a0a;}
.footer p{margin:0;font-size:10px;color:#3a3020;font-style:italic;}
"""


def _html_wrap(title: str, subtitle: str, body_html: str,
               stoic_quote: str = "") -> str:
    """Wrap content sections in the standard Dune dark-theme envelope."""
    footer_html = ""
    if stoic_quote:
        footer_html = (
            f'<div class="footer"><p>"{stoic_quote}"</p></div>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{DUNE_STYLES}</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  {body_html}
  {footer_html}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Midday alert email builder
# ---------------------------------------------------------------------------

def build_midday_email(
    actions_taken: list[dict],
    portfolio_value: float,
    settled_cash: float,
    positions_value: float,
    daily_pnl: float,
    date_str: str,
    time_str: str,
) -> tuple[str, str]:
    """
    Build the midday alert email.

    actions_taken: list of dicts with keys:
        type          — "STOP_LOSS" | "NEW_ENTRY" | "NEWS_ALERT"
        ticker        — str
        price         — float
        pnl_pct       — float (signed, e.g. -8.2 or +6.1; 0 for entries)
        shares        — int
        reason        — str
    Returns (subject, html_body).
    """
    # Build subject from first action
    if not actions_taken:
        raise ValueError("build_midday_email called with no actions")

    first = actions_taken[0]
    if first["type"] == "STOP_LOSS":
        action_summary = f"STOP LOSS: {first['ticker']} sold at {first['pnl_pct']:+.1f}%"
    elif first["type"] == "PARTIAL_PROFIT":
        action_summary = f"Partial profit: {first['ticker']} at {first['pnl_pct']:+.1f}%"
    elif first["type"] == "NEW_ENTRY":
        action_summary = f"Entered {first['ticker']} (midday momentum)"
    else:
        action_summary = f"NEWS ALERT: {first['ticker']}"

    if len(actions_taken) > 1:
        action_summary += f" +{len(actions_taken)-1} more"

    subject = f"\u2694\ufe0f Midday Alert \u2014 {action_summary}"

    # Build action cards
    cards_html = ""
    for a in actions_taken:
        atype = a["type"]
        ticker = a["ticker"]
        price = a.get("price", 0)
        pnl_pct = a.get("pnl_pct", 0)
        shares = a.get("shares", 0)
        reason = a.get("reason", "")

        if atype == "STOP_LOSS":
            badge = '<span class="badge badge-stop">STOP LOSS</span>'
            card_class = "card stop-loss"
            pnl_class = "pnl-neg"
            detail = (
                f"Sold {shares} shares @ ${price:.2f} &nbsp;|&nbsp; "
                f'P&amp;L: <span class="{pnl_class}">{pnl_pct:+.2f}%</span>'
                f"<br>Reason: {reason}"
            )
        elif atype == "PARTIAL_PROFIT":
            badge = '<span class="badge badge-profit">PARTIAL PROFIT</span>'
            card_class = "card partial-profit"
            detail = (
                f"Sold {shares} shares @ ${price:.2f} &nbsp;|&nbsp; "
                f'P&amp;L: <span class="pnl-pos">{pnl_pct:+.2f}%</span>'
                f"<br>Reason: {reason}"
            )
        elif atype == "NEW_ENTRY":
            badge = '<span class="badge badge-entry">NEW ENTRY</span>'
            card_class = "card new-entry"
            detail = (
                f"Bought {shares} shares @ ${price:.2f}<br>Reason: {reason}"
            )
        else:  # NEWS_ALERT
            badge = '<span class="badge badge-news">NEWS ALERT</span>'
            card_class = "card news-alert"
            detail = f"Thesis-breaking news detected<br>{reason}"

        cards_html += f"""
<div class="{card_class}">
  {badge}
  <div class="ticker">{ticker}</div>
  <div class="detail">{detail}</div>
</div>"""

    # Portfolio summary
    daily_sign = "+" if daily_pnl >= 0 else ""
    daily_color = "#90ee90" if daily_pnl >= 0 else "#ee9090"

    summary_html = f"""
<div class="summary-row">
  <span class="label">Portfolio Value</span>
  <span class="value">${portfolio_value:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Cash</span>
  <span class="value">${settled_cash:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Positions</span>
  <span class="value">${positions_value:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Day P&amp;L</span>
  <span class="value" style="color:{daily_color};">{daily_sign}${daily_pnl:,.2f}</span>
</div>"""

    body_html = f"""
<div class="section">
  <h2>Actions Taken — {date_str} {time_str}</h2>
  {cards_html}
</div>
<div class="section">
  <h2>Portfolio Snapshot</h2>
  {summary_html}
</div>"""

    html = _html_wrap(
        title="\u2694\ufe0f Midday Alert",
        subtitle=f"{date_str} &nbsp;|&nbsp; {time_str}",
        body_html=body_html,
    )
    return subject, html


# ---------------------------------------------------------------------------
# EOD email builder
# ---------------------------------------------------------------------------

STOIC_QUOTES = [
    # Good-day quotes
    "The impediment to action advances action. What stands in the way becomes the way. — Marcus Aurelius",
    "Waste no more time arguing about what a good man should be. Be one. — Marcus Aurelius",
    "He who fears death will never do anything worthy of a man who is alive. — Seneca",
    "Luck is what happens when preparation meets opportunity. — Seneca",
    "Make the best use of what is in your power, and take the rest as it happens. — Epictetus",
    # Flat / bad day quotes
    "You have power over your mind, not outside events. Realize this, and you will find strength. — Marcus Aurelius",
    "If it is not right, do not do it; if it is not true, do not say it. — Marcus Aurelius",
    "We suffer more often in imagination than in reality. — Seneca",
    "The obstacle is the way. — Marcus Aurelius",
    "He suffers more than necessary, who suffers before it is necessary. — Seneca",
]


def build_eod_email(
    snapshot: dict,
    trades: list[dict],
    position_details: list[dict],
    extra_note: str,
    watchlist_tomorrow: list[dict],
    date_str: str,
) -> tuple[str, str]:
    """
    Build the EOD summary email.

    snapshot:           dict from take_snapshot() return value
    trades:             list of today's trade dicts from trades.json
    position_details:   list of position snapshot dicts
    extra_note:         manual reflection note (may be empty)
    watchlist_tomorrow: list of dicts with 'ticker' and optionally 'signal', 'note'
    date_str:           "YYYY-MM-DD"
    Returns (subject, html_body).
    """
    portfolio_value = snapshot["portfolio_value"]
    daily_pnl       = snapshot["daily_pnl"]
    total_pnl       = snapshot["total_pnl"]
    total_pnl_pct   = snapshot["total_pnl_pct"]
    settled_cash     = snapshot["settled_cash"]
    unsettled_cash   = snapshot.get("unsettled_cash", 0)
    positions_value  = snapshot["positions_value"]

    # Format date for display
    from datetime import datetime
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = dt.strftime("%b %-d")  # e.g. "Apr 7"
    except Exception:
        date_display = date_str

    # Subject
    daily_sign = "+" if daily_pnl >= 0 else ""
    daily_pct  = round((daily_pnl / (portfolio_value - daily_pnl)) * 100, 2) if (portfolio_value - daily_pnl) else 0
    subject = (
        f"\U0001f4ca EOD {date_display} \u2014 "
        f"${portfolio_value:,.0f} ({daily_sign}${daily_pnl:,.0f} / {daily_sign}{daily_pct:.2f}%)"
    )

    # ── Section 1: Portfolio Snapshot ──
    total_sign  = "+" if total_pnl >= 0 else ""
    daily_color = "#90ee90" if daily_pnl >= 0 else "#ee9090"
    total_color = "#90ee90" if total_pnl >= 0 else "#ee9090"

    snap_html = f"""
<div class="summary-row">
  <span class="label">Total Value</span>
  <span class="value">${portfolio_value:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Cash (settled)</span>
  <span class="value">${settled_cash:,.2f}</span>
</div>"""
    if unsettled_cash > 0:
        snap_html += f"""
<div class="summary-row">
  <span class="label">Cash (unsettled T+2)</span>
  <span class="value">${unsettled_cash:,.2f}</span>
</div>"""
    snap_html += f"""
<div class="summary-row">
  <span class="label">Positions Value</span>
  <span class="value">${positions_value:,.2f}</span>
</div>
<div class="summary-row">
  <span class="label">Day P&amp;L</span>
  <span class="value" style="color:{daily_color};">{daily_sign}${daily_pnl:,.2f} ({daily_sign}{daily_pct:.2f}%)</span>
</div>
<div class="summary-row">
  <span class="label">Total P&amp;L</span>
  <span class="value" style="color:{total_color};">{total_sign}${total_pnl:,.2f} ({total_sign}{total_pnl_pct:.2f}%)</span>
</div>"""

    # ── Section 2: Open Positions ──
    if position_details:
        rows = ""
        for p in position_details:
            unr  = p["unrealized_pnl"]
            upct = p["unrealized_pct"]
            sign = "+" if unr >= 0 else ""
            color = "#90ee90" if unr >= 0 else "#ee9090"
            stop  = p.get("stop_price", "—")
            target = p.get("target_price", "—")
            stop_s  = f"${stop:.2f}"  if isinstance(stop, float)  else stop
            target_s = f"${target:.2f}" if isinstance(target, float) else target
            rows += f"""
<tr>
  <td style="color:#c8961e;font-weight:bold;">{p['ticker']}</td>
  <td>{p['shares']}</td>
  <td>${p['avg_cost']:.2f}</td>
  <td>${p['close_price']:.2f}</td>
  <td style="color:{color};">{sign}{upct:.2f}%</td>
  <td>{stop_s}</td>
  <td>{target_s}</td>
</tr>"""
        positions_html = f"""
<table>
<tr>
  <th>Ticker</th><th>Shares</th><th>Avg Cost</th>
  <th>Close</th><th>Unr. P&amp;L</th><th>Stop</th><th>Target</th>
</tr>
{rows}
</table>"""
    else:
        positions_html = '<p style="color:#6b5a3e;font-size:12px;margin:0;">No open positions — fully in cash.</p>'

    # ── Section 3: Today's Trades ──
    if trades:
        trade_rows = ""
        for t in trades:
            action_color = "#90ee90" if t["action"] == "BUY" else "#ee9090"
            pnl_str = ""
            if t["action"] == "SELL" and "realized_pnl" in t:
                p = t["realized_pnl"]
                sign = "+" if p >= 0 else ""
                pnl_color = "#90ee90" if p >= 0 else "#ee9090"
                pnl_str = f'<span style="color:{pnl_color};">{sign}${p:,.2f}</span>'
            trade_rows += f"""
<tr>
  <td style="color:{action_color};font-weight:bold;">{t['action']}</td>
  <td style="color:#c8961e;">{t['ticker']}</td>
  <td>{t['shares']}</td>
  <td>${t['price']:.2f}</td>
  <td>{pnl_str}</td>
</tr>"""
        trades_html = f"""
<table>
<tr><th>Action</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Realized P&amp;L</th></tr>
{trade_rows}
</table>"""
    else:
        trades_html = '<p style="color:#6b5a3e;font-size:12px;margin:0;">No trades today — held positions.</p>'

    # ── Section 4: Daily Reflection ──
    if extra_note:
        reflection_text = extra_note
    else:
        # Auto-generate based on day performance
        if daily_pnl > 0:
            reflection_text = (
                f"Portfolio advanced ${daily_pnl:,.2f} today. "
                "Positions held per thesis; no reactive adjustments made. "
                "Discipline maintained."
            )
        elif daily_pnl < 0:
            reflection_text = (
                f"Portfolio pulled back ${abs(daily_pnl):,.2f} today. "
                "Stop losses monitored; no rules broken. "
                "The process is sound — results will follow."
            )
        else:
            reflection_text = (
                "Flat day. No significant moves. "
                "Patience is a position."
            )

    # ── Section 5: Tomorrow's Watchlist ──
    if watchlist_tomorrow:
        watch_rows = ""
        for w in watchlist_tomorrow[:5]:
            signal = w.get("signal", "—")
            note   = w.get("note", "")
            watch_rows += f"""
<tr>
  <td style="color:#c8961e;font-weight:bold;">{w['ticker']}</td>
  <td>{signal}</td>
  <td style="color:#8a7a64;">{note}</td>
</tr>"""
        watchlist_html = f"""
<table>
<tr><th>Ticker</th><th>Signal</th><th>Note</th></tr>
{watch_rows}
</table>"""
    else:
        watchlist_html = '<p style="color:#6b5a3e;font-size:12px;margin:0;">No watchlist data available.</p>'

    # ── Pick stoic quote based on day ──
    import hashlib
    idx = int(hashlib.md5(date_str.encode()).hexdigest(), 16) % len(STOIC_QUOTES)
    stoic = STOIC_QUOTES[idx]

    body_html = f"""
<div class="section">
  <h2>&#x1F4CA; Portfolio Snapshot</h2>
  {snap_html}
</div>
<div class="section">
  <h2>&#x1F4BC; Open Positions</h2>
  {positions_html}
</div>
<div class="section">
  <h2>&#x1F501; Today's Trades</h2>
  {trades_html}
</div>
<div class="section">
  <h2>&#x1F4D6; Daily Reflection</h2>
  <p style="font-size:13px;color:#b0a088;line-height:1.7;margin:0;">{reflection_text}</p>
</div>
<div class="section">
  <h2>&#x1F50D; Tomorrow's Watchlist</h2>
  {watchlist_html}
</div>"""

    html = _html_wrap(
        title=f"\U0001f4ca EOD Summary",
        subtitle=f"{date_display} &nbsp;|&nbsp; Paper Trading Simulator",
        body_html=body_html,
        stoic_quote=stoic,
    )
    return subject, html
