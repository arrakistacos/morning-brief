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

    print("Done!")


if __name__ == "__main__":
    main()
