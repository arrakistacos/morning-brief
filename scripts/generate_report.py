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


def render_risk_sources(sources: list) -> str:
    """Render inline source citations for a risk item."""
    if not sources:
        return ""
    parts = []
    for s in sources:
        title = s.get("title", "")
        outlet = s.get("outlet", "")
        url = s.get("url")
        label = outlet if outlet else title
        if url:
            parts.append(f'<a href="{url}" target="_blank" rel="noopener" class="risk-source-link">[{label}]</a>')
        else:
            parts.append(f'<span class="risk-source-plain">[{label}]</span>')
    return ' '.join(parts)


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
    """Generate mobile-friendly executive summary card for email (table-based, inline CSS)."""
    summary = analysis.get("summary", {})
    if not summary:
        return ""

    gist = summary.get("gist", "")
    actionable_items = summary.get("actionable_items", [])
    stoic = summary.get("stoic_quote", {})
    stoic_text = stoic.get("text", "")
    stoic_attr = stoic.get("attribution", "")

    items_html = ""
    for item in actionable_items:
        items_html += (
            f'<tr><td style="padding:7px 0;font-size:14px;color:#e2e8f0;font-family:Arial,sans-serif;'
            f'border-bottom:1px solid #1e2d47;line-height:1.5;">'
            f'<span style="color:#C4A265;margin-right:8px;">&#9634;</span>{item}</td></tr>'
        )

    return f"""
  <!-- Executive Summary Card -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#1e2d47;border:1px solid #2d4a6e;border-radius:10px;margin-bottom:20px;">
    <tr>
      <td style="padding:20px 20px 16px;">
        <div style="font-size:10px;font-weight:700;color:#60a5fa;text-transform:uppercase;letter-spacing:2px;font-family:Arial,sans-serif;margin-bottom:14px;">&#9889; EXECUTIVE SUMMARY</div>
        <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;margin-bottom:8px;">THE GIST</div>
        <p style="margin:0 0 16px;font-size:15px;line-height:1.6;color:#e2e8f0;font-family:Arial,sans-serif;font-weight:500;">{gist}</p>
        <div style="font-size:10px;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;margin-bottom:8px;">ACTIONABLE ITEMS</div>
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
          {items_html}
        </table>
      </td>
    </tr>
    <tr>
      <td style="padding:0 20px 20px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="border-left:3px solid #C4A265;padding:10px 14px;background-color:#0f1a2e;border-radius:0 6px 6px 0;">
              <p style="margin:0 0 6px;font-style:italic;color:#fcd34d;font-size:13px;line-height:1.6;font-family:Arial,sans-serif;">&#8220;{stoic_text}&#8221;</p>
              <div style="font-size:11px;color:#94a3b8;font-family:Arial,sans-serif;">&#8212; {stoic_attr}</div>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>"""


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
        <div class="event-card section-cell">
          <div class="event-header">
            <span class="significance-badge badge" style="background:{sig_color}">{event.get('significance','')}</span>
            <span class="time-horizon badge">{event.get('time_horizon','')}</span>
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
        <div class="watch-item section-cell">
          <div class="watch-ticker watchlist-ticker" style="color:{action_color}">{item.get('ticker','')} <span class="watch-action">{item.get('action','').replace('_',' ')}</span></div>
          <div class="watch-catalyst">{item.get('catalyst','')}</div>
          <div class="watch-entry"><strong>Entry idea:</strong> {item.get('entry_idea','')}</div>
          <div class="watch-risk"><strong>Risk:</strong> {item.get('risk','')}</div>
        </div>"""

    sector_rows = ""
    for sector, data in analysis.get("sector_outlook", {}).items():
        color = sentiment_color(data.get("sentiment", ""))
        sector_rows += f"""
        <tr class="sector-row">
          <td class="sector-cell">{sector.replace('_', ' ').title()}</td>
          <td class="sector-cell" style="color:{color};font-weight:700">{data.get('sentiment','')}</td>
          <td class="sector-cell hide-mobile">{data.get('reasoning','')}</td>
          <td class="sector-cell hide-mobile">{', '.join(data.get('key_names',[]))}</td>
        </tr>"""

    # Build risks HTML — supports both old (string) and new (object) formats
    risks_html = ""
    for risk in analysis.get("risks_to_watch", []):
        if isinstance(risk, str):
            # Legacy format: plain string
            risks_html += f'<li><div class="risk-text">{risk}</div></li>'
        else:
            # New format: object with risk, severity, causal_chain, sources
            sev = risk.get("severity", "")
            sev_color = {
                "CRITICAL": "#ff1744",
                "HIGH": "#ff8f00",
                "MEDIUM": "#f59e0b",
                "LOW": "#78909c",
            }.get(sev, "#78909c")
            causal = risk.get("causal_chain", "")
            sources_html = render_risk_sources(risk.get("sources", []))
            sources_block = (
                f'<div class="risk-sources">Sources: {sources_html}</div>'
                if sources_html else ""
            )
            risks_html += f"""<li class="risk-row">
              <div class="risk-severity" style="color:{sev_color}">⚠️ {sev}</div>
              <div class="risk-text"><strong>{risk.get('risk','')}</strong></div>
              <div class="risk-causal">{causal}</div>
              {sources_block}
            </li>"""

    summary_card = generate_summary_card_html(analysis)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief — {date}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  /* Browser-only responsive overrides — email clients ignore this entire <style> block */
  * {{ box-sizing: border-box; }}
  body {{ background: #0A0E1A !important; }}

  /* Container */
  .container {{ width: 100% !important; max-width: 600px !important; margin: 0 auto !important; }}

  /* Typography */
  body, td, th, p {{ font-family: Arial, sans-serif !important; }}
  p {{ font-size: 15px !important; line-height: 1.6 !important; margin: 8px 0 !important; }}

  /* Responsive layout */
  @media only screen and (max-width: 620px) {{
    .container {{ width: 100% !important; padding: 0 !important; }}
    table {{ width: 100% !important; }}
    td {{ display: block !important; width: 100% !important; }}

    /* Make stat cells 2-up on mobile */
    .stat-cell {{ display: inline-block !important; width: 48% !important; vertical-align: top !important; }}

    /* Full width sections */
    .section-cell {{ width: 100% !important; padding: 12px 16px !important; }}

    /* Tables that should scroll horizontally on mobile */
    .scroll-table {{ display: block !important; overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }}

    /* Hide less critical columns on mobile */
    .hide-mobile {{ display: none !important; }}

    /* Larger touch targets for links */
    a {{ padding: 2px 0 !important; display: inline-block !important; }}

    /* Header scaling */
    .header-title {{ font-size: 20px !important; }}
    .header-subtitle {{ font-size: 14px !important; }}

    /* Badges */
    .badge {{ font-size: 10px !important; padding: 2px 6px !important; }}

    /* Risk cards */
    .risk-row td {{ padding: 10px 14px !important; }}

    /* Watchlist table: stack on mobile */
    .watchlist-table td {{ display: block !important; border-bottom: none !important; }}
    .watchlist-ticker {{ font-size: 16px !important; font-weight: bold !important; }}
  }}

  /* Desktop styles for the browser view */
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

  /* ── Key Risks ── */
  .risks-list {{ list-style: none; }}
  .risks-list li {{
    background: var(--surface);
    border: 1px solid #ff174422;
    border-left: 3px solid var(--bear);
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 10px;
  }}
  .risk-severity {{
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
  }}
  .risk-text {{
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 4px;
  }}
  .risk-causal {{
    font-size: 0.82rem;
    color: var(--muted);
    margin-top: 4px;
    line-height: 1.5;
  }}
  .risk-sources {{
    margin-top: 6px;
    font-size: 0.75rem;
    color: #9CA3AF;
  }}
  .risk-source-link {{
    color: #9CA3AF;
    text-decoration: none;
    border-bottom: 1px dotted #9CA3AF44;
    margin-right: 4px;
  }}
  .risk-source-link:hover {{
    color: var(--accent);
    border-bottom-color: var(--accent);
  }}
  .risk-source-plain {{
    color: #9CA3AF;
    margin-right: 4px;
  }}

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
<div style="background:#0A0E1A;">
<div class="container">
  <div class="header">
    <h1 class="header-title">📊 Morning Brief</h1>
    <div class="header-subtitle date">{date} · Generated at {datetime.utcnow().strftime('%H:%M UTC')}</div>
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
  <div class="scroll-table"><table class="sector-table">
    <thead><tr><th>Sector</th><th>Sentiment</th><th class="hide-mobile">Reasoning</th><th class="hide-mobile">Key Names</th></tr></thead>
    <tbody>{sector_rows}</tbody>
  </table></div>

  <div class="section-title">🛢 Commodity Outlook</div>
  <div class="commodity-grid">
    {''.join([f"""<div class="commodity-card"><div class="commodity-name">{k.replace('_',' ')}</div>
    <div class="commodity-dir" style="color:{sentiment_color(v.get('direction',''))}">{v.get('direction','')}</div>
    <div class="commodity-driver">{v.get('key_driver','')}</div></div>"""
    for k, v in analysis.get('commodity_outlook',{}).items()])}
  </div>

  <div class="section-title">🎯 Watchlist</div>
  {watchlist_html}

  <div class="section-title">⚠️ Key Risks to Monitor</div>
  <ul class="risks-list">
    {risks_html}
  </ul>

  <footer>Generated by Morning Brief · <a href="https://arrakistacos.github.io/morning-brief/">Dashboard</a> · Powered by Anthropic Claude</footer>
</div>
</div>
</body>
</html>"""


def generate_email_html(analysis: dict) -> str:
    """
    Mobile-first email HTML using table-based layout and fully inline CSS.
    Renders correctly in Gmail Android, iOS Mail, and Outlook.
    Rules enforced:
      - All CSS inline (no <style> blocks except a <head> media-query block for Apple Mail/Outlook)
      - Table-based layout only — no flexbox, no CSS grid
      - Max width 600px, 100% on mobile
      - No web fonts (Arial / Georgia only)
      - Images get explicit width/height
      - Touch-friendly links (padding on anchors)
      - Min 14px body text, 1.5-1.6 line-height
    """
    date = analysis.get("date", "")
    sentiment = analysis.get("overall_sentiment", "NEUTRAL")
    score = analysis.get("sentiment_score", 0)
    score_color = "#00c853" if score > 2 else "#ff1744" if score < -2 else "#ff8f00"
    score_display = f"{score:+d}"

    # Preheader text (hidden in body but visible in inbox preview)
    risks_list = analysis.get("risks_to_watch", [])
    top_risk_obj = risks_list[0] if risks_list else None
    if isinstance(top_risk_obj, dict):
        top_risk_label = top_risk_obj.get("risk", "")[:70]
    elif isinstance(top_risk_obj, str):
        top_risk_label = top_risk_obj[:70]
    else:
        top_risk_label = ""
    preheader = f"{date} \u2014 Sentiment: {score:+d}/10 \u2014 {top_risk_label}"

    summary_card = generate_summary_card_email_html(analysis)

    # ── Macro events (max 5) ──────────────────────────────────────────────────
    macro_rows = ""
    for event in analysis.get("macro_events", [])[:5]:
        sig = event.get("significance", "")
        sig_color = {
            "CRITICAL": "#ff1744", "HIGH": "#ff8f00",
            "MEDIUM": "#f59e0b", "LOW": "#78909c",
        }.get(sig, "#78909c")
        causal = event.get("causal_chain", "")
        if len(causal) > 420:
            causal = causal[:420] + "&#8230;"
        time_horizon = event.get("time_horizon", "")
        event_title = event.get("event", "")
        macro_rows += f"""
        <tr><td style="padding:0 0 12px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-left:3px solid {sig_color};border-radius:0 4px 4px 0;background-color:#1a2236;">
            <tr><td style="padding:12px 14px;">
              <div style="font-size:11px;font-weight:700;color:{sig_color};text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;margin-bottom:5px;">{sig} &middot; {time_horizon}</div>
              <div style="font-size:14px;font-weight:700;color:#e2e8f0;font-family:Arial,sans-serif;line-height:1.5;margin-bottom:7px;">{event_title}</div>
              <div style="font-size:13px;color:#93c5fd;font-family:Arial,sans-serif;line-height:1.6;">{causal}</div>
            </td></tr>
          </table>
        </td></tr>"""

    # ── Sector outlook rows ───────────────────────────────────────────────────
    sector_rows = ""
    for sector, data in analysis.get("sector_outlook", {}).items():
        color = sentiment_color(data.get("sentiment", ""))
        sector_name = sector.replace("_", " ").title()
        sentiment_val = data.get("sentiment", "")
        reasoning = data.get("reasoning", "")
        reasoning_short = (reasoning[:120] + "&#8230;") if len(reasoning) > 120 else reasoning
        sector_rows += f"""
        <tr>
          <td style="padding:9px 10px 9px 0;border-bottom:1px solid #1e2d47;font-size:13px;color:#e2e8f0;font-family:Arial,sans-serif;font-weight:600;">{sector_name}</td>
          <td style="padding:9px 10px;border-bottom:1px solid #1e2d47;font-size:13px;color:{color};font-family:Arial,sans-serif;font-weight:700;white-space:nowrap;">{sentiment_val}</td>
          <td class="hide-mobile" style="padding:9px 8px;border-bottom:1px solid #1e2d47;font-size:12px;color:#94a3b8;font-family:Arial,sans-serif;line-height:1.5;">{reasoning_short}</td>
        </tr>"""

    # ── Watchlist rows ────────────────────────────────────────────────────────
    watchlist_rows = ""
    for item in analysis.get("watchlist", [])[:8]:
        action = item.get("action", "")
        action_color = {
            "WATCH_LONG": "#00c853", "WATCH_SHORT": "#ff1744", "AVOID": "#888888",
        }.get(action, "#888888")
        ticker = item.get("ticker", "")
        catalyst = item.get("catalyst", "")
        watchlist_rows += f"""
        <tr>
          <td style="padding:10px 8px 10px 0;border-bottom:1px solid #1e2d47;font-family:Arial,sans-serif;font-weight:700;font-size:14px;color:{action_color};white-space:nowrap;">{ticker}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #1e2d47;font-family:Arial,sans-serif;font-size:13px;color:#94a3b8;white-space:nowrap;">{action.replace('_', ' ')}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #1e2d47;font-family:Arial,sans-serif;font-size:13px;color:#e2e8f0;line-height:1.5;">{catalyst}</td>
        </tr>"""

    # ── Key risks (max 4) ─────────────────────────────────────────────────────
    risks_rows = ""
    for risk in risks_list[:4]:
        if isinstance(risk, str):
            risks_rows += f"""
        <tr><td style="padding:0 0 10px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-left:3px solid #ff1744;border-radius:0 4px 4px 0;background-color:#1a1f2e;">
            <tr><td style="padding:10px 14px;font-size:14px;color:#e2e8f0;font-family:Arial,sans-serif;line-height:1.5;">{risk}</td></tr>
          </table>
        </td></tr>"""
        else:
            sev = risk.get("severity", "")
            sev_color = {
                "CRITICAL": "#ff1744", "HIGH": "#ff8f00",
                "MEDIUM": "#f59e0b", "LOW": "#78909c",
            }.get(sev, "#78909c")
            risk_title = risk.get("risk", "")
            causal = risk.get("causal_chain", "")
            # Source links — touch-friendly padding
            src_parts = []
            for s in risk.get("sources", []):
                outlet = s.get("outlet", s.get("title", ""))
                url = s.get("url")
                if url:
                    src_parts.append(
                        f'<a href="{url}" target="_blank" rel="noopener" '
                        f'style="color:#9CA3AF;text-decoration:none;padding:3px 0;display:inline-block;">[{outlet}]</a>'
                    )
                else:
                    src_parts.append(f'<span style="color:#9CA3AF;font-family:Arial,sans-serif;">[{outlet}]</span>')
            sources_row = ""
            if src_parts:
                sources_row = (
                    f'<div style="margin-top:6px;font-size:12px;color:#9CA3AF;font-family:Arial,sans-serif;">'
                    f'Sources: {" ".join(src_parts)}</div>'
                )
            risks_rows += f"""
        <tr><td style="padding:0 0 10px 0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-left:3px solid {sev_color};border-radius:0 4px 4px 0;background-color:#1a1f2e;">
            <tr><td style="padding:12px 14px;">
              <div style="font-size:11px;font-weight:700;color:{sev_color};text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;margin-bottom:4px;">&#9888; {sev}</div>
              <div style="font-size:14px;font-weight:700;color:#e2e8f0;font-family:Arial,sans-serif;line-height:1.5;margin-bottom:5px;">{risk_title}</div>
              <div style="font-size:13px;color:#94a3b8;font-family:Arial,sans-serif;line-height:1.5;">{causal}</div>
              {sources_row}
            </td></tr>
          </table>
        </td></tr>"""

    exec_summary_text = analysis.get("executive_summary", "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
  <title>Morning Brief &#8212; {date}</title>
  <style>
    /* Media queries for Apple Mail and Outlook — Gmail ignores these */
    @media only screen and (max-width: 600px) {{
      .container {{ width: 100% !important; }}
      .stat-cell {{ width: 50% !important; display: inline-block !important; }}
      .full-mobile {{ width: 100% !important; display: block !important; }}
      .hide-mobile {{ display: none !important; }}
      .td-pad {{ padding-left: 14px !important; padding-right: 14px !important; }}
      h1 {{ font-size: 20px !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:#0A0E1A;font-family:Arial,sans-serif;">

  <!-- Preheader (hidden preview text) -->
  <div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:#0A0E1A;mso-hide:all;">{preheader}&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;</div>

  <!-- ═══════════ OUTER WRAPPER ═══════════ -->
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#0A0E1A;">
    <tr>
      <td align="center" style="padding:20px 10px;">

        <!-- ═══════════ INNER CONTAINER (max 600px) ═══════════ -->
        <table class="container" width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background-color:#111827;border-radius:8px;">

          <!-- ── HEADER ── -->
          <tr>
            <td style="background-color:#0D1B2A;padding:22px 24px 18px;border-radius:8px 8px 0 0;border-bottom:1px solid #1e2d47;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td valign="middle">
                    <div style="font-size:10px;font-weight:700;color:#C4A265;text-transform:uppercase;letter-spacing:2px;font-family:Arial,sans-serif;margin-bottom:5px;">Morning Brief</div>
                    <div style="font-size:22px;font-weight:700;color:#FFFFFF;font-family:Arial,sans-serif;line-height:1.2;">MUAD&#8217;DIB MARKET INTELLIGENCE</div>
                    <div style="font-size:14px;color:#C4A265;font-family:Arial,sans-serif;margin-top:4px;font-style:italic;">The Sleeper Has Awakened</div>
                    <div style="font-size:12px;color:#64748b;font-family:Arial,sans-serif;margin-top:8px;">{date}</div>
                  </td>
                  <td align="right" valign="middle" style="padding-left:12px;">
                    <table cellpadding="0" cellspacing="0" border="0"
                           style="background-color:#1a1f2e;border:2px solid {score_color};border-radius:8px;text-align:center;">
                      <tr><td style="padding:10px 14px;">
                        <div style="font-size:30px;font-weight:800;color:{score_color};font-family:Arial,sans-serif;line-height:1;">{score_display}</div>
                        <div style="font-size:10px;font-weight:700;color:{score_color};font-family:Arial,sans-serif;text-transform:uppercase;letter-spacing:1px;margin-top:2px;">{sentiment}</div>
                        <div style="font-size:10px;color:#94a3b8;font-family:Arial,sans-serif;">/10</div>
                      </td></tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- ── BODY ── -->
          <tr>
            <td class="td-pad" style="padding:20px 24px;">

              {summary_card}

              <!-- Executive summary paragraph -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
                <tr>
                  <td style="background-color:#1a2236;border-left:4px solid #3b82f6;border-radius:0 6px 6px 0;padding:14px 16px;">
                    <p style="margin:0;font-size:14px;line-height:1.6;color:#e2e8f0;font-family:Arial,sans-serif;">{exec_summary_text}</p>
                  </td>
                </tr>
              </table>

              <!-- ── MACRO EVENTS ── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:4px;">
                <tr>
                  <td style="padding:0 0 12px;border-bottom:1px solid #1e2d47;">
                    <span style="font-size:12px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;">&#127760; Key Macro Events</span>
                  </td>
                </tr>
                <tr><td style="padding-top:12px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    {macro_rows}
                  </table>
                </td></tr>
              </table>

              <!-- ── SECTOR OUTLOOK ── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
                <tr>
                  <td style="padding:14px 0 10px;border-bottom:1px solid #1e2d47;">
                    <span style="font-size:12px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;">&#128200; Sector Outlook</span>
                  </td>
                </tr>
                <tr><td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding:6px 10px 6px 0;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Sector</td>
                      <td style="padding:6px 10px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Outlook</td>
                      <td class="hide-mobile" style="padding:6px 8px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Notes</td>
                    </tr>
                    {sector_rows}
                  </table>
                </td></tr>
              </table>

              <!-- ── WATCHLIST ── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:20px;">
                <tr>
                  <td style="padding:14px 0 10px;border-bottom:1px solid #1e2d47;">
                    <span style="font-size:12px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;">&#127919; Today&#8217;s Watchlist</span>
                  </td>
                </tr>
                <tr><td>
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding:6px 8px 6px 0;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Ticker</td>
                      <td style="padding:6px 8px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Action</td>
                      <td style="padding:6px 8px;font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;border-bottom:1px solid #1e2d47;">Catalyst</td>
                    </tr>
                    {watchlist_rows}
                  </table>
                </td></tr>
              </table>

              <!-- ── KEY RISKS ── -->
              <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
                <tr>
                  <td style="padding:14px 0 12px;border-bottom:1px solid #1e2d47;">
                    <span style="font-size:12px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;font-family:Arial,sans-serif;">&#9888; Key Risks to Monitor</span>
                  </td>
                </tr>
                <tr><td style="padding-top:12px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0">
                    {risks_rows}
                  </table>
                </td></tr>
              </table>

            </td>
          </tr>

          <!-- ── FOOTER ── -->
          <tr>
            <td style="background-color:#0D1B2A;padding:16px 24px;border-top:1px solid #1e2d47;border-radius:0 0 8px 8px;text-align:center;">
              <p style="margin:0 0 6px;font-size:12px;color:#64748b;font-family:Arial,sans-serif;">
                <a href="https://arrakistacos.github.io/morning-brief/" target="_blank"
                   style="color:#C4A265;text-decoration:none;padding:4px 0;display:inline-block;">View Full Dashboard</a>
                &nbsp;&middot;&nbsp; Powered by Anthropic Claude
              </p>
              <p style="margin:0;font-size:11px;color:#374151;font-family:Arial,sans-serif;">Not financial advice. For informational purposes only.</p>
            </td>
          </tr>

        </table><!-- /inner container -->
      </td>
    </tr>
  </table><!-- /outer wrapper -->

</body>
</html>"""

