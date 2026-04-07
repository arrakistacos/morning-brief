#!/usr/bin/env python3
import os
import json
import sys
from datetime import datetime
from pathlib import Path

from scripts.fetch_news import fetch_all_news
from scripts.analyze import analyze_news
from scripts.generate_report import generate_html_report, generate_email_html
from scripts.send_email import send_report


def main():
    print(f"[{datetime.now().isoformat()}] Morning Brief starting...")

    # Config from environment
    claude_api_key = os.environ.get("CLAUDE_API_KEY")
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL", "capt.computermail@gmail.com")

    if not claude_api_key:
        print("ERROR: CLAUDE_API_KEY not set")
        sys.exit(1)

    # 1. Fetch news
    print("Fetching news...")
    articles = fetch_all_news(hours_back=14)
    print(f"Fetched {len(articles)} articles")

    # 2. Analyze with Claude
    print("Analyzing with Claude...")
    analysis = analyze_news(articles, claude_api_key)

    # 3. Save JSON report
    date_str = datetime.now().strftime("%Y-%m-%d")
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    with open(reports_dir / f"{date_str}.json", "w") as f:
        json.dump(analysis, f, indent=2)
    print(f"Saved JSON report: reports/{date_str}.json")

    # 4. Generate full HTML report
    html_report = generate_html_report(analysis, articles)
    with open(reports_dir / f"{date_str}.html", "w") as f:
        f.write(html_report)
    print(f"Saved HTML report: reports/{date_str}.html")

    # 5. Send email
    if gmail_user and gmail_password:
        sentiment = analysis.get("overall_sentiment", "NEUTRAL")
        score = analysis.get("sentiment_score", 0)
        subject = f"📊 Morning Brief {date_str} — {sentiment} ({score:+d}/10)"
        email_html = generate_email_html(analysis)
        send_report(email_html, subject, recipient, gmail_user, gmail_password)
    else:
        print("WARNING: Gmail credentials not set, skipping email")

    # 6. Queue trade signals for Phase 2 market-open execution (8:35 AM CT)
    # Reads watchlist from the analysis, runs chart signals, and writes
    # simulator/pending_trades.json. Actual execution happens at market open.
    print("Queuing trade signals for market-open execution...")
    try:
        from scripts.main import build_pending_trades, get_chart_signal, fetch_price, compute_shares
        import pytz

        portfolio_path = Path("simulator/pending_trades.json")
        portfolio_data_path = Path("simulator/portfolio.json")

        if portfolio_data_path.exists():
            with open(portfolio_data_path) as f:
                portfolio = json.load(f)

            watchlist = analysis.get("watchlist", [])
            if watchlist:
                pending_trades = build_pending_trades(watchlist, portfolio)
                with open(portfolio_path, "w") as f:
                    json.dump(pending_trades, f, indent=2)
                print(f"Queued {len(pending_trades)} trade signal(s) to simulator/pending_trades.json")
                print("Phase 2 execution runs at 8:35 AM CT via simulator/market_open_execution.py")
            else:
                print("No watchlist signals in analysis — pending_trades.json not updated")
        else:
            print("WARNING: simulator/portfolio.json not found — skipping trade queuing")
    except Exception as e:
        # Non-fatal: analysis and email are the primary deliverables
        print(f"WARNING: Could not queue trade signals: {e}")

    print("Done!")


if __name__ == "__main__":
    main()
