# Muad'Dib Market Intelligence

Automated daily trading intelligence, paper trading simulator, and market dashboard.

## Live Dashboard & Data

**[📊 Dashboard](https://arrakistacos.github.io/morning-brief/)** | **[📊 Google Sheet](https://docs.google.com/spreadsheets/d/1SptFol_qs9fmxLmCB5z_ELkOK0oZXBJbSa8VfZ-JEVg/edit)**

## What This Is

Every weekday this system delivers a structured morning brief covering overnight news, sentiment analysis, and causal reasoning across macro, geopolitical, and sector-level inputs. It also runs a paper trading simulator with a $25k starting portfolio, executing swing trades with full chart analysis and bracket orders. Three scheduled tasks at **4:45 AM**, **12:00 PM**, and **3:15 PM CT** keep the briefing, position monitoring, and end-of-day review automated.

## 📱 Schwab Android Execution Guide

[📱 Schwab Android Execution Guide](docs/schwab-execution-guide.md)

Translates every simulator trade signal (entry price, stop loss, take profit, OCO bracket orders) into step-by-step Charles Schwab Android app instructions.

## Schedule

| Task | Time (CT) | Description |
|------|-----------|-------------|
| Morning Brief | 4:45 AM Mon-Fri | News analysis, trading decisions, email |
| Midday Check | 12:00 PM Mon-Fri | Stop-loss monitor, thesis check |
| EOD Review | 3:15 PM Mon-Fri | Closing prices, P&L snapshot, reflection |

## Simulator Rules

- $25k starting capital
- Longs only — no shorting
- Max 3 open positions at a time
- Max 30% of portfolio per position
- 8% hard stop loss on all positions
- T+2 settlement enforced
- NYSE holiday-aware scheduling

## Repo Structure

```
morning-brief/
├── .github/workflows/
│   ├── morning-brief.yml    # Daily scheduler + analysis runner
│   └── pages.yml            # GitHub Pages deploy
├── scripts/
│   ├── analyze.py           # Claude AI analysis engine
│   ├── fetch_news.py        # RSS news aggregator (17 sources)
│   ├── generate_report.py   # HTML report + email generator
│   ├── send_email.py        # Gmail SMTP sender
│   └── build_dashboard.py   # GitHub Pages dashboard builder
├── docs/
│   ├── index.html                        # GitHub Pages dashboard
│   └── schwab-execution-guide.md        # Schwab Android trade execution guide
├── reports/                 # Auto-generated daily reports (JSON + HTML)
├── main.py                  # Main orchestrator
├── config.py                # Non-secret configuration
└── requirements.txt
```

---

*Powered by [Anthropic Claude](https://anthropic.com) · Built with GitHub Actions + GitHub Pages*
