#!/usr/bin/env python3
import json
import os
from pathlib import Path
from datetime import datetime


def build_dashboard():
    reports_dir = Path("reports")
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    # Load all JSON reports
    reports = []
    for json_file in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            with open(json_file) as f:
                data = json.load(f)
                data["_filename"] = json_file.stem
                reports.append(data)
        except Exception:
            pass

    # Build report cards for dashboard
    cards_html = ""
    for r in reports:
        date = r.get("date", r["_filename"])
        sentiment = r.get("overall_sentiment", "NEUTRAL")
        score = r.get("sentiment_score", 0)
        score_color = "#00c853" if score > 2 else "#ff1744" if score < -2 else "#ff8f00"
        summary = r.get("executive_summary", "")[:200] + "..."
        themes = r.get("top_themes", [])
        themes_html = " ".join([f'<span class="theme">{t}</span>' for t in themes[:3]])
        cards_html += f"""
        <a href="reports/{r['_filename']}.html" class="report-card">
          <div class="card-header">
            <span class="card-date">{date}</span>
            <span class="card-sentiment" style="color:{score_color}">{sentiment} ({score:+d})</span>
          </div>
          <div class="card-themes">{themes_html}</div>
          <div class="card-summary">{summary}</div>
        </a>"""

    # Score sparkline data
    score_data = [(r.get("_filename", ""), r.get("sentiment_score", 0)) for r in reversed(reports[-30:])]
    sparkline_js = f"const scoreData = {json.dumps(score_data)};"

    # Pre-compute conditional values to avoid nested f-string issues
    secrets_display = "none" if reports else "block"
    latest_sentiment = reports[0].get("overall_sentiment", "—") if reports else "—"
    latest_color = "#00c853" if reports and reports[0].get("sentiment_score", 0) > 2 else "#ff1744" if reports and reports[0].get("sentiment_score", 0) < -2 else "#ff8f00"
    avg_score = f'{sum(r.get("sentiment_score", 0) for r in reports[:30]) / max(len(reports[:30]), 1):+.1f}' if reports else "—"
    bullish_count = sum(1 for r in reports[:30] if r.get("overall_sentiment") == "BULLISH")
    bearish_count = sum(1 for r in reports[:30] if r.get("overall_sentiment") == "BEARISH")
    report_count = len(reports)
    last_updated = datetime.now().strftime("%b %d, %Y")
    chart_section = """
  <div class="chart-wrap">
    <div class="chart-title">30-Day Sentiment Score</div>
    <canvas id="sparkline"></canvas>
  </div>""" if reports else ""
    no_reports_msg = '<div style="color:var(--muted);text-align:center;padding:40px">No reports yet. Trigger the workflow to generate your first brief.</div>'
    reports_content = cards_html if cards_html else no_reports_msg

    dashboard_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#0a0e1a;--surface:#111827;--surface2:#1a2236;--border:#1e2d47;--text:#e2e8f0;--muted:#64748b;--accent:#3b82f6;--bull:#00c853;--bear:#ff1744; }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;line-height:1.6}}
  .container{{max-width:1100px;margin:0 auto;padding:32px 20px}}
  .header{{border-bottom:1px solid var(--border);padding-bottom:24px;margin-bottom:32px;display:flex;justify-content:space-between;align-items:flex-end}}
  .header h1{{font-size:1.8rem;font-weight:700;color:#60cfff}}
  .header p{{color:var(--muted);font-size:0.9rem;margin-top:4px}}
  .stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:32px}}
  .stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:16px}}
  .stat-label{{font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:0.05em}}
  .stat-value{{font-size:1.6rem;font-weight:700;font-family:'JetBrains Mono',monospace;margin-top:4px}}
  .chart-wrap{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:32px}}
  .chart-title{{font-size:0.85rem;color:var(--muted);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.05em}}
  canvas{{width:100%;height:80px}}
  .reports-grid{{display:grid;gap:12px}}
  .report-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px;text-decoration:none;color:inherit;transition:border-color 0.2s;display:block}}
  .report-card:hover{{border-color:var(--accent)}}
  .card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
  .card-date{{font-weight:600;font-size:0.95rem}}
  .card-sentiment{{font-family:'JetBrains Mono',monospace;font-weight:700;font-size:0.9rem}}
  .card-themes{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}}
  .theme{{background:var(--surface2);color:var(--accent);padding:2px 10px;border-radius:12px;font-size:0.75rem}}
  .card-summary{{font-size:0.85rem;color:var(--muted);line-height:1.5}}
  .secrets-notice{{background:#1a1500;border:1px solid #ff8f0066;border-radius:8px;padding:16px;margin-bottom:24px;font-size:0.88rem;display:{secrets_display}}}
  .secrets-notice h3{{color:#ff8f00;margin-bottom:8px}}
  code{{background:#111;padding:2px 6px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:0.85em}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>&#128202; Morning Brief</h1>
      <p>AI-powered market intelligence &middot; Updated daily at 6 AM ET</p>
    </div>
    <div style="color:var(--muted);font-size:0.85rem">
      {report_count} reports &middot; Last updated {last_updated}
    </div>
  </div>

  <div class="secrets-notice">
    <h3>&#9881;&#65039; Setup Required</h3>
    <p>No reports yet. Add these GitHub Secrets to activate the daily brief:</p>
    <ul style="margin:8px 0 0 16px;line-height:2">
      <li><code>CLAUDE_API_KEY</code> &mdash; from console.anthropic.com</li>
      <li><code>GMAIL_USER</code> &mdash; your Gmail address for sending</li>
      <li><code>GMAIL_APP_PASSWORD</code> &mdash; Gmail app password (myaccount.google.com &rarr; Security &rarr; App passwords)</li>
    </ul>
    <p style="margin-top:8px">Then trigger the workflow manually: Actions &rarr; Morning Brief &rarr; Run workflow</p>
  </div>

  <div class="stat-row">
    <div class="stat-card">
      <div class="stat-label">Total Reports</div>
      <div class="stat-value" style="color:var(--accent)">{report_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Latest Sentiment</div>
      <div class="stat-value" style="color:{latest_color}">{latest_sentiment}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">30-Day Avg Score</div>
      <div class="stat-value">{avg_score}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Bullish Days (30d)</div>
      <div class="stat-value" style="color:var(--bull)">{bullish_count}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Bearish Days (30d)</div>
      <div class="stat-value" style="color:var(--bear)">{bearish_count}</div>
    </div>
  </div>

  {chart_section}

  <div class="reports-grid">
    {reports_content}
  </div>
</div>

<script>
{sparkline_js}
const canvas = document.getElementById('sparkline');
if (canvas && scoreData.length > 1) {{
  const ctx = canvas.getContext('2d');
  canvas.width = canvas.offsetWidth * window.devicePixelRatio;
  canvas.height = 80 * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  const w = canvas.offsetWidth, h = 80;
  const min = -10, max = 10;
  const pts = scoreData.map((d,i) => [i/(scoreData.length-1)*w, h/2 - (d[1]/(max-min))*h*0.8]);
  ctx.strokeStyle='#3b82f6';ctx.lineWidth=2;ctx.beginPath();
  pts.forEach((p,i)=>i===0?ctx.moveTo(...p):ctx.lineTo(...p));ctx.stroke();
  ctx.fillStyle='rgba(59,130,246,0.1)';ctx.beginPath();
  pts.forEach((p,i)=>i===0?ctx.moveTo(...p):ctx.lineTo(...p));
  ctx.lineTo(w,h/2);ctx.lineTo(0,h/2);ctx.closePath();ctx.fill();
  ctx.strokeStyle='#1e2d47';ctx.lineWidth=1;ctx.setLineDash([4,4]);
  ctx.beginPath();ctx.moveTo(0,h/2);ctx.lineTo(w,h/2);ctx.stroke();
}}
</script>
</body>
</html>"""

    with open(docs_dir / "index.html", "w") as f:
        f.write(dashboard_html)

    # Copy individual HTML reports to docs/reports/
    docs_reports = docs_dir / "reports"
    docs_reports.mkdir(exist_ok=True)
    import shutil
    for html_file in reports_dir.glob("*.html"):
        shutil.copy(html_file, docs_reports / html_file.name)

    print(f"Dashboard built with {len(reports)} reports")


if __name__ == "__main__":
    build_dashboard()
