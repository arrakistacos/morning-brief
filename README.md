# 📊 Morning Brief

AI-powered daily market intelligence — news analysis, causal reasoning, and trading signals delivered every morning before the market opens.

## What It Does

Every weekday at **6:00 AM ET**, this system:

1. Fetches overnight news from 17+ financial, geopolitical, and economic RSS feeds
2. Sends all headlines + summaries to Claude for deep macro analysis
3. Generates a structured briefing with causal chains, sector outlooks, commodity forecasts, and a specific watchlist
4. Emails the brief to your inbox
5. Publishes the full HTML report to the GitHub Pages dashboard
6. Tracks 30-day sentiment history with a sparkline chart

## Dashboard

**[https://arrakistacos.github.io/morning-brief/](https://arrakistacos.github.io/morning-brief/)**

## Setup

### 1. Add GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Description |
|--------|-------------|
| `CLAUDE_API_KEY` | Your Anthropic API key from [console.anthropic.com](https://console.anthropic.com) |
| `GMAIL_USER` | Gmail address used to send the brief (e.g. `you@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Gmail App Password — [create one here](https://myaccount.google.com/apppasswords) (requires 2FA) |

> **Note:** The recipient email is hardcoded as `capt.computermail@gmail.com`. To change it, update `RECIPIENT_EMAIL` in `config.py` or set it as a secret.

### 2. Trigger Your First Run

Go to **Actions → Morning Brief → Run workflow** to test immediately without waiting for the scheduled run.

### 3. Watch It Work

- The workflow runs, fetches news, calls Claude, and commits the report to `reports/`
- The Pages workflow triggers automatically and publishes the dashboard
- You'll receive an email with the brief

## Scheduled Time

The cron is set to `0 10 * * 1-5` — **10:00 AM UTC = 6:00 AM ET** on weekdays. This gives you 3.5 hours before the US market opens at 9:30 AM ET.

To change the time, edit `.github/workflows/morning-brief.yml`.

## Project Structure

```
morning-brief/
├── .github/workflows/
│   ├── morning-brief.yml   # Daily scheduler + analysis runner
│   └── pages.yml           # GitHub Pages deploy
├── scripts/
│   ├── analyze.py          # Claude AI analysis engine
│   ├── fetch_news.py       # RSS news aggregator (17 sources)
│   ├── generate_report.py  # HTML report + email generator
│   ├── send_email.py       # Gmail SMTP sender
│   └── build_dashboard.py  # GitHub Pages dashboard builder
├── reports/                # Auto-generated daily reports (JSON + HTML)
├── docs/                   # GitHub Pages source
├── main.py                 # Main orchestrator
├── config.py               # Non-secret configuration
└── requirements.txt
```

## Data Sources

**Financial:** Reuters Business, Reuters Markets, AP Business, CNBC, MarketWatch, Financial Times, Seeking Alpha, Benzinga, Investing.com, Yahoo Finance

**Geopolitical:** BBC World, Al Jazeera, Foreign Policy

**Economic:** Federal Reserve, Bureau of Labor Statistics, IMF

## Running Locally

```bash
pip install -r requirements.txt
export CLAUDE_API_KEY=your_key_here
export GMAIL_USER=your@gmail.com
export GMAIL_APP_PASSWORD=your_app_password
python main.py
```

---

*Powered by [Anthropic Claude](https://anthropic.com) · Built with GitHub Actions + GitHub Pages*
