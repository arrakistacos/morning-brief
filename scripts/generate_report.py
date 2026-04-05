import json
from datetime import datetime


def sentiment_color(sentiment):
    colors = {
        "BULLISH": "#00c853",
        "BEARISH": "#ff1744",
        "NEUTRAL": "#78909c",
        "MIXED": "#ff8f00",
        "UP": "#00c853",
        "DOWN": "#ff1744",
        "FLAT": "#78909c",
        "STRONGER": "#00c853",
        "WEAKER": "#ff1744",
    }
    for key, color in colors.items():
        if key in str(sentiment).upper():
            return color
    return "#78909c"


def generate_summary_card_html(analysis: dict) -> str:
    """Generate the prominent executive summary card HTML for the full report."""
    summary = analysis.get("summary", {})
    if not summary:
        return ""

    gist = summary.get("gist", "")
    actionable_items = summary.get("actionable_items", [])
    stoic = summary.get("stoic_quote", {})
    stoic_text = stoic.get("text", "")
    stoic_attr = stoic.get("attribution", "")

    items_html = "".join([
        f'<li class="action-item"><span class="action-check">☐</span>{item}</li>'
        for item in actionable_items
    ])

    return f"""
  <div class="exec-card">
    <div class="exec-card-header">
      <span class="exec-card-label">⚡ EXECUTIVE SUMMARY</span>
    </div>

    <div class="exec-gist-section">
      <div class="exec-section-label">THE GIST</div>
      <p class="exec-gist-text">{gist}</p>
    </div>

    <div class="exec-actions-section">
      <div class="exec-section-label">ACTIONABLE ITEMS</div>
      <ul class="action-list">{items_html}</ul>
    </div>

    <blockquote class="stoic-quote">
      <p class="stoic-text">"{stoic_text}"</p>
      <footer class="stoic-attr">— {stoic_attr}</footer>
    </blockquote>
  </div>"""


def generate_summary_card_email_html(analysis: dict) -> str:
    """Generate the prominent executive summary card HTML for the email version."""
    summary = analysis.get("summary", {})
    if not summary:
        return ""

    gist = summary.get("gist", "")
    actionable_items = summary.get("actionable_items", [])
    stoic = summary.get("stoic_quote", {})
    stoic_text = stoic.get("text", "")
    stoic_attr = stoic.get("attribution", "")

    items_html = "".join([
        f'<li style="margin:6px 0;font-size:13px;color:#e2e8f0;padding-left:4px">'
        f'<span style="color:#f59e0b;margin-right:6px">☐</span>{item}</li>'
        for item in actionable_items
    ])

    return f"""
  <!-- Executive Summary Card -->
  <div style="background:#1e2d47;border:1px solid #2d4a6e;border-radius:10px;padding:24px;margin-bottom:24px;position:relative">
    <div style="font-size:10px;font-weight:700;color:#60a5fa;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:16px">
      ⚡ Executive Summary
    </div>

    <!-- The Gist -->
    <div style="margin-bottom:18px">
      <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px">The Gist</div>
      <p style="margin:0;font-size:14px;line-height:1.7;color:#e2e8f0;font-weight:500">{gist}</p>
    </div>

    <!-- Actionable Items -->
    <div style="margin-bottom:18px">
      <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px">Actionable Items</div>
      <ul style="margin:0;padding:0;list-style:none">{items_html}</ul>
    </div>

    <!-- Stoic Quote -->
    <div style="border-left:3px solid #f59e0b;padding:12px 16px;background:#0f1a2e;border-radius:0 6px 6px 0">
      <p style="margin:0 0 6px;font-style:italic;color:#fcd34d;font-size:13px;line-height:1.6">"{stoic_text}"</p>
      <footer style="font-size:11px;color:#94a3b8;font-style:normal">— {stoic_attr}</footer>
    </div>
  </div>"""


def generate_html_report(analysis: dict, articles: list) -> str:
    date = analysis.get("date", datetime.now().strftime("%A, %B %d, %Y"))
    sentiment = analysis.get("overall_sentiment", "NEUTRAL")
    score = analysis.get("sentiment_score", 0)

    # Score bar visualization
    score_pct = ((score + 10) / 20) * 100  # convert -10..10 to 0..100%
    score_color = "#00c853" if score > 2 else "#ff1744" if score < -2 else "#ff8f00"

    macro_events_html = ""
    for event in analysis.get("macro_events", []):
        sig_color = {"HIGH": "#ff1744", "MEDIUM": "#ff8f00", "LOW": "#78909c"}.get(event.get("significance", "LOW"), "#78909c")

        stocks_html = ""
        for stock in event.get("specific_stocks", []):
            dir_color = "#00c853" if stock["direction"] == "UP" else "#ff1744"
            stocks_html += f'<span class="stock-tag" style="border-color:{dir_color};color:{dir_color}">{stock["ticker"]} {"▲" if stock["direction"]=="UP" else "▼"}</span>'

        sectors_html = " ".join([f'<span class="tag">{s}</span>' for s in event.get("affected_sectors", [])])

        macro_events_html += f"""
        <div class="event-card">
          <div class="event-header">
            <span class="significance-badge" style="background:{sig_color}">{event.get('significance','')}</span>
            <span class="time-horizon">{event.get('time_horizon','')}</span>
          </div>
          <h3>{event.get('event','')}</h3>
          <div class="causal-chain">
            <strong>📊 Causal Analysis</strong>
            <p>{event.get('causal_chain','')}</p>
          </div>
          <div class="geo-dim">
            <strong>🌍 Geographic Dimension</strong>
            <p>{event.get('geographic_dimension','')}</p>
          </div>
          <div class="analog">
            <strong>📅 Historical Analog:</strong> {event.get('historical_analog','')}
          </div>
          <div class="counter">
            <strong>⚠️ Counterarguments:</strong> {event.get('counterarguments','')}
          </div>
          <div class="tags-row">Sectors: {sectors_html}</div>
          <div class="stocks-row">Stocks: {stocks_html}</div>
        </div>"""

    watchlist_html = ""
    for item in analysis.get("watchlist", []):
        action_color = {"WATCH_LONG": "#00c853", "WATCH_SHORT": "#ff1744", "AVOID": "#78909c"}.get(item.get("action", ""), "#78909c")
        watchlist_html += f"""
        <div class="watch-item">
          <div class="watch-ticker" style="color:{action_color}">{item.get('ticker','')} <span class="watch-action">{item.get('action','').replace('_',' ')}</span></div>
          <div class="watch-catalyst">{item.get('catalyst','')}</div>
          <div class="watch-entry"><strong>Entry idea:</strong> {item.get('entry_idea','')}</div>
          <div class="watch-risk"><strong>Risk:</strong> {item.get('risk','')}</div>
        </div>"""

    sector_rows = ""
    for sector, data in analysis.get("sector_outlook", {}).items():
        color = sentiment_color(data.get("sentiment", ""))
        sector_rows += f"""
        <tr>
          <td>{sector.replace('_', ' ').title()}</td>
          <td style="color:{color};font-weight:700">{data.get('sentiment','')}</td>
          <td>{data.get('reasoning','')}</td>
          <td>{', '.join(data.get('key_names',[]))}</td>
        </tr>"""

    summary_card = generate_summary_card_html(analysis)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief — {date}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0e1a;
    --surface: #111827;
    --surface2: #1a2236;
    --surface3: #1e2d47;
    --border: #1e2d47;
    --border2: #2d4a6e;
    --text: #e2e8f0;
    --muted: #64748b;
    --accent: #3b82f6;
    --bull: #00c853;
    --bear: #ff1744;
    --warn: #ff8f00;
    --gold: #f59e0b;
    --gold-light: #fcd34d;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif; line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px; }}

  .header {{ border-bottom: 1px solid var(--border); padding-bottom: 24px; margin-bottom: 32px; }}
  .header h1 {{ font-size: 1.8rem; font-weight: 700; color: #60cfff; }}
  .header .date {{ color: var(--muted); font-size: 0.95rem; margin-top: 4px; }}

  /* ── Executive Summary Card ── */
  .exec-card {{
    background: var(--surface3);
    border: 1px solid var(--border2);
    border-radius: 12px;
    padding: 28px;
    margin-bottom: 36px;
    position: relative;
  }}
  .exec-card-header {{
    margin-bottom: 20px;
  }}
  .exec-card-label {{
    font-size: 0.7rem;
    font-weight: 700;
    color: #60a5fa;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }}
  .exec-section-label {{
    font-size: 0.68rem;
    font-weight: 700;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }}
  .exec-gist-section {{
    margin-bottom: 20px;
  }}
  .exec-gist-text {{
    font-size: 0.97rem;
    line-height: 1.75;
    color: var(--text);
    font-weight: 500;
  }}
  .exec-actions-section {{
    margin-bottom: 20px;
  }}
  .action-list {{
    list-style: none;
    padding: 0;
  }}
  .action-item {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 6px 0;
    font-size: 0.875rem;
    color: var(--text);
    border-bottom: 1px solid #ffffff08;
  }}
  .action-item:last-child {{ border-bottom: none; }}
  .action-check {{
    color: var(--gold);
    flex-shrink: 0;
    margin-top: 1px;
  }}
  .stoic-quote {{
    border-left: 3px solid var(--gold);
    padding: 14px 18px;
    background: #0a0e1a;
    border-radius: 0 8px 8px 0;
    margin-top: 4px;
  }}
  .stoic-text {{
    font-style: italic;
    color: var(--gold-light);
    font-size: 0.92rem;
    line-height: 1.65;
    margin-bottom: 6px;
  }}
  .stoic-attr {{
    font-size: 0.78rem;
    color: var(--muted);
    font-style: normal;
  }}

  .sentiment-bar-wrap {{ display: flex; align-items: center; gap: 16px; margin: 24px 0; }}
  .sentiment-label {{ font-size: 1.4rem; font-weight: 700; }}
  .score-bar {{ flex: 1; height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; }}
  .score-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
  .score-num {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 1.1rem; }}

  .exec-summary {{ background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 8px; padding: 20px; margin-bottom: 32px; font-size: 0.95rem; line-height: 1.7; }}

  .section-title {{ font-size: 1.1rem; font-weight: 700; color: var(--accent); margin: 32px 0 16px; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}

  .event-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }}
  .event-header {{ display: flex; gap: 8px; margin-bottom: 10px; }}
  .significance-badge {{ padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; color: white; }}
  .time-horizon {{ padding: 2px 10px; border-radius: 4px; font-size: 0.75rem; background: var(--surface2); color: var(--muted); }}
  .event-card h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 12px; }}
  .causal-chain, .geo-dim, .analog, .counter {{ margin: 10px 0; font-size: 0.88rem; }}
  .causal-chain {{ background: var(--surface2); padding: 12px; border-radius: 6px; }}
  .analog, .counter {{ color: var(--muted); }}
  .tags-row, .stocks-row {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 0.8rem; color: var(--muted); }}
  .tag {{ background: var(--surface2); padding: 2px 8px; border-radius: 4px; }}
  .stock-tag {{ border: 1px solid; padding: 2px 8px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; font-weight: 700; }}

  .sector-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  .sector-table th {{ text-align: left; padding: 10px 12px; background: var(--surface); border-bottom: 2px solid var(--border); color: var(--muted); font-size: 0.8rem; text-transform: uppercase; }}
  .sector-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}

  .watch-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 10px; }}
  .watch-ticker {{ font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; }}
  .watch-action {{ font-size: 0.75rem; font-weight: 400; margin-left: 8px; }}
  .watch-catalyst {{ margin: 6px 0 4px; font-size: 0.88rem; }}
  .watch-entry, .watch-risk {{ font-size: 0.82rem; color: var(--muted); }}

  .risks-list {{ list-style: none; }}
  .risks-list li {{ background: var(--surface); border: 1px solid #ff174422; border-left: 3px solid var(--bear); border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; font-size: 0.9rem; }}

  .themes {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }}
  .theme-tag {{ background: var(--surface2); border: 1px solid var(--accent)44; color: var(--accent); padding: 4px 14px; border-radius: 20px; font-size: 0.85rem; }}

  .commodity-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }}
  .commodity-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }}
  .commodity-name {{ font-size: 0.8rem; color: var(--muted); text-transform: uppercase; }}
  .commodity-dir {{ font-size: 1rem; font-weight: 700; margin: 4px 0; }}
  .commodity-driver {{ font-size: 0.78rem; color: var(--muted); }}

  footer {{ margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 0.8rem; text-align: center; }}
  a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📊 Morning Brief</h1>
    <div class="date">{date} · Generated at {datetime.utcnow().strftime('%H:%M UTC')}</div>
  </div>

  {summary_card}

  <div class="themes">
    {''.join([f'<span class="theme-tag">{t}</span>' for t in analysis.get('top_themes',[])])}
  </div>

  <div class="sentiment-bar-wrap">
    <div class="sentiment-label" style="color:{sentiment_color(sentiment)}">{sentiment}</div>
    <div class="score-bar"><div class="score-fill" style="width:{score_pct}%;background:{score_color}"></div></div>
    <div class="score-num" style="color:{score_color}">{score:+d}/10</div>
  </div>

  <div class="exec-summary">{analysis.get('executive_summary','')}</div>

  <div class="section-title">🌐 Macro Events & Causal Analysis</div>
  {macro_events_html}

  <div class="section-title">📈 Sector Outlook</div>
  <table class="sector-table">
    <thead><tr><th>Sector</th><th>Sentiment</th><th>Reasoning</th><th>Key Names</th></tr></thead>
    <tbody>{sector_rows}</tbody>
  </table>

  <div class="section-title">🛢 Commodity Outlook</div>
  <div class="commodity-grid">
    {''.join([f"""<div class="commodity-card"><div class="commodity-name">{k.replace('_',' ')}</div>
    <div class="commodity-dir" style="color:{sentiment_color(v.get('direction',''))}">{v.get('direction','')}</div>
    <div class="commodity-driver">{v.get('key_driver','')}</div></div>"""
    for k, v in analysis.get('commodity_outlook',{}).items()])}
  </div>

  <div class="section-title">🎯 Watchlist</div>
  {watchlist_html}

  <div class="section-title">⚠️ Key Risks to Watch</div>
  <ul class="risks-list">
    {''.join([f'<li>{r}</li>' for r in analysis.get('risks_to_watch',[])])}
  </ul>

  <footer>Generated by Morning Brief · <a href="https://arrakistacos.github.io/morning-brief/">Dashboard</a> · Powered by Anthropic Claude</footer>
</div>
</body>
</html>"""


def generate_email_html(analysis: dict) -> str:
    """Simplified email-friendly HTML version."""
    date = analysis.get("date", "")
    sentiment = analysis.get("overall_sentiment", "NEUTRAL")
    score = analysis.get("sentiment_score", 0)
    score_color = "#00c853" if score > 2 else "#ff1744" if score < -2 else "#ff8f00"

    summary_card = generate_summary_card_email_html(analysis)

    watchlist_rows = ""
    for item in analysis.get("watchlist", [])[:8]:
        action_color = {"WATCH_LONG": "#00c853", "WATCH_SHORT": "#ff1744", "AVOID": "#888"}.get(item.get("action", ""), "#888")
        watchlist_rows += f"""
        <tr>
          <td style="font-family:monospace;font-weight:700;color:{action_color}">{item.get('ticker','')}</td>
          <td>{item.get('action','').replace('_',' ')}</td>
          <td>{item.get('catalyst','')}</td>
        </tr>"""

    macro_html = ""
    for event in analysis.get("macro_events", [])[:5]:
        sig = event.get("significance", "")
        sig_color = {"HIGH": "#ff1744", "MEDIUM": "#ff8f00", "LOW": "#888"}.get(sig, "#888")
        macro_html += f"""
        <div style="background:#1a2236;border-left:3px solid {sig_color};padding:12px 16px;margin:10px 0;border-radius:4px">
          <div style="font-size:11px;color:{sig_color};font-weight:700;margin-bottom:6px">{sig} IMPACT · {event.get('time_horizon','')}</div>
          <div style="font-weight:600;margin-bottom:8px">{event.get('event','')}</div>
          <div style="font-size:13px;color:#aac8ff">{event.get('causal_chain','')[:400]}...</div>
        </div>"""

    return f"""
<html><body style="background:#0a0e1a;color:#e2e8f0;font-family:Inter,Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px">
  <div style="border-bottom:1px solid #1e2d47;padding-bottom:16px;margin-bottom:20px">
    <h1 style="color:#60cfff;font-size:1.4rem;margin:0">📊 Morning Brief — {date}</h1>
  </div>

  {summary_card}

  <div style="background:#111827;border-radius:8px;padding:16px;margin-bottom:20px">
    <div style="font-size:1.3rem;font-weight:700;color:{score_color}">{sentiment} ({score:+d}/10)</div>
    <p style="margin:10px 0 0;font-size:14px;line-height:1.6">{analysis.get('executive_summary','')}</p>
  </div>

  <h2 style="color:#3b82f6;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.05em">Key Macro Events</h2>
  {macro_html}

  <h2 style="color:#3b82f6;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.05em;margin-top:24px">Today's Watchlist</h2>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <tr style="color:#64748b;font-size:11px;text-transform:uppercase">
      <td style="padding:6px">Ticker</td><td>Action</td><td>Catalyst</td>
    </tr>
    {watchlist_rows}
  </table>

  <div style="margin-top:24px;font-size:12px;color:#64748b;text-align:center">
    <a href="https://arrakistacos.github.io/morning-brief/" style="color:#3b82f6">View Full Dashboard</a>
    &nbsp;·&nbsp; Powered by Anthropic Claude
  </div>
</body></html>"""
