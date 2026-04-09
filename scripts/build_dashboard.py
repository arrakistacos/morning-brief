#!/usr/bin/env python3
"""
build_dashboard.py — Generate the Muad'Dib Market Intelligence dashboard.

Reads:
  reports/           — Morning brief HTML/JSON reports
  simulator/*.json   — Paper trader portfolio/trades/performance/strategy data

Writes:
  docs/index.html    — Full dashboard (reports tab + paper trader tab)
  docs/reports/      — Individual report HTML files (copied from reports/)
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json_safe(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return (default if default is not None else {})


HAWK_SVG = (
    '<svg viewBox="0 0 120 75" xmlns="http://www.w3.org/2000/svg" '
    'fill="currentColor" aria-hidden="true">'
    '<path d="M60 22 C48 13 28 7 4 15 C16 17 30 22 38 27 '
    'C30 29 18 36 8 47 C22 39 38 35 46 36 L60 63 L74 36 '
    'C82 35 98 39 112 47 C102 36 90 29 82 27 '
    'C90 22 104 17 116 15 C92 7 72 13 60 22 Z"/>'
    '<ellipse cx="60" cy="15" rx="6" ry="7"/>'
    '<path d="M60 20 L65 24 L60 26 Z"/>'
    '</svg>'
)

# ── CSS (plain string — no f-string, so {} don't need escaping) ───────────────

CSS = """
:root {
  --bg: #0a0807;
  --surface: #13100c;
  --surface2: #1c1810;
  --surface3: #231e14;
  --border: #2d2315;
  --text: #E8DCC8;
  --muted: #8a7660;
  --sand: #C4A265;
  --spice: #E07B2A;
  --atreides: #4A8FCC;
  --bull: #6ECB63;
  --bear: #E05252;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 16px;
  line-height: 1.6;
  min-height: 100vh;
  -webkit-text-size-adjust: 100%;
}

/* Layout */
.container { max-width: 1100px; margin: 0 auto; padding: 0 1rem; width: 100%; }

/* Hero Header */
.hero {
  text-align: center;
  padding: 3rem 1rem 2rem;
  border-bottom: 1px solid var(--border);
  background: radial-gradient(ellipse at top, rgba(196,162,101,.08) 0%, transparent 65%);
}
.hawk-emblem {
  margin: 0 auto 1.5rem;
  color: var(--sand);
  opacity: .88;
  width: clamp(55px, 12vw, 88px);
}
.hawk-emblem svg { width: 100%; height: auto; display: block; }
.hero h1 {
  font-size: clamp(1.2rem, 4vw, 2rem);
  color: var(--sand);
  font-weight: 700;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.hero-tagline {
  font-size: clamp(.82rem, 2.5vw, 1rem);
  color: var(--spice);
  font-style: italic;
  margin-top: .5rem;
  opacity: .9;
}
.hero-sub { font-size: .8rem; color: var(--muted); margin-top: .3rem; }

/* Tab Navigation */
.tab-nav {
  display: flex;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky;
  top: 0;
  z-index: 50;
}
.tab-nav::-webkit-scrollbar { display: none; }
.tab-btn {
  padding: 1rem 1.5rem;
  white-space: nowrap;
  background: none;
  border: none;
  border-bottom: 3px solid transparent;
  color: var(--muted);
  font-size: .9rem;
  cursor: pointer;
  min-height: 48px;
  font-family: inherit;
  font-weight: 500;
  transition: color .2s, border-color .2s;
}
.tab-btn.active { color: var(--sand); border-bottom-color: var(--sand); }
.tab-btn:hover:not(.active) { color: var(--text); }
.tab-content { display: none; padding: 1.75rem 0 3rem; }
.tab-content.active { display: block; }

/* Stat Cards */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: .75rem;
  margin-bottom: 1.5rem;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem;
}
.stat-label {
  font-size: .68rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 600;
}
.stat-value {
  font-size: 1.45rem;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  margin-top: .25rem;
  word-break: break-all;
}

/* Charts */
.chart-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  margin-bottom: 1.5rem;
}
.chart-title {
  font-size: .73rem;
  color: var(--muted);
  margin-bottom: .75rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 600;
}
.chart-container { position: relative; height: 350px; width: 100%; }
.chart-container-sm { position: relative; height: 130px; width: 100%; }

/* Section Headers */
.section-header {
  font-size: .92rem;
  color: var(--sand);
  font-weight: 600;
  margin-bottom: .875rem;
  padding-bottom: .5rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: .5rem;
}

/* Report Cards */
.reports-grid { display: grid; gap: .75rem; }
.report-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.25rem;
  text-decoration: none;
  color: inherit;
  display: block;
  transition: border-color .2s, background .2s;
}
.report-card:hover { border-color: var(--sand); background: var(--surface2); }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: .5rem;
  margin-bottom: .5rem;
}
.card-date {
  font-weight: 600;
  font-size: .92rem;
  font-family: 'JetBrains Mono', monospace;
}
.card-themes { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .6rem; }
.theme {
  background: var(--surface2);
  color: var(--atreides);
  padding: .15rem .6rem;
  border-radius: 12px;
  font-size: .72rem;
  font-weight: 500;
  border: 1px solid rgba(74,143,204,.2);
}
.card-summary { font-size: .84rem; color: var(--muted); line-height: 1.55; }

/* Tables */
.table-wrap {
  overflow-x: auto;
  margin-bottom: 1.5rem;
  border-radius: 10px;
  border: 1px solid var(--border);
  -webkit-overflow-scrolling: touch;
}
table { width: 100%; border-collapse: collapse; min-width: 540px; }
thead th {
  background: var(--surface2);
  color: var(--sand);
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .06em;
  padding: .75rem 1rem;
  text-align: left;
  white-space: nowrap;
  font-weight: 700;
}
tbody td {
  padding: .75rem 1rem;
  border-bottom: 1px solid var(--border);
  font-size: .84rem;
  vertical-align: middle;
  color: var(--text);
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: rgba(196,162,101,.03); }
.empty-state {
  text-align: center;
  color: var(--muted);
  padding: 2.5rem 1rem;
  font-style: italic;
  font-size: .88rem;
}

/* Mobile Card Table */
@media (max-width: 768px) {
  .mobile-card-table-wrap { border: none; background: transparent; overflow-x: visible; }
  .mobile-card-table { min-width: unset; width: 100%; }
  .mobile-card-table thead { display: none; }
  .mobile-card-table tbody tr {
    display: block;
    background: var(--surface2);
    margin-bottom: .75rem;
    border-radius: 10px;
    padding: .875rem;
    border: 1px solid var(--border);
  }
  .mobile-card-table tbody td {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: .3rem 0;
    border: none;
    font-size: .84rem;
    gap: .5rem;
  }
  .mobile-card-table tbody td::before {
    content: attr(data-label);
    font-weight: 600;
    color: var(--sand);
    white-space: nowrap;
    flex-shrink: 0;
    min-width: 90px;
  }
  .mobile-card-table tbody tr:last-child td { border: none; }
  .mobile-card-table td[colspan] { display: block; }
  .mobile-card-table td[colspan]::before { display: none; }
}

/* Sentiment Colors */
.bull { color: var(--bull); font-weight: 600; }
.bear { color: var(--bear); font-weight: 600; }
.neutral { color: var(--spice); }

/* Expandable Thesis Rows */
.expand-btn {
  cursor: pointer;
  background: none;
  border: 1px solid var(--border);
  color: var(--sand);
  font-size: .7rem;
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: background .15s, transform .2s;
  margin-right: .35rem;
  vertical-align: middle;
  flex-shrink: 0;
}
.expand-btn:hover { background: var(--surface2); }
.expand-btn.open { transform: rotate(90deg); }
.thesis-row { display: none; }
.thesis-row.open { display: table-row; }
.thesis-content {
  padding: 1rem 1.25rem;
  background: var(--surface2);
  border-radius: 6px;
  font-size: .84rem;
  line-height: 1.65;
  color: var(--text);
  border: 1px solid var(--border);
}
.thesis-content p { margin-bottom: .5rem; }
.thesis-content p:last-child { margin-bottom: 0; }
.thesis-content strong { color: var(--sand); }

/* Strategy Journal */
.journal-grid { display: grid; gap: .75rem; margin-bottom: 1.5rem; }
.journal-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1.125rem;
}
.journal-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: .5rem;
  margin-bottom: .75rem;
}
.journal-date {
  font-size: .78rem;
  color: var(--muted);
  font-family: 'JetBrains Mono', monospace;
}
.journal-type {
  font-size: .68rem;
  padding: .18rem .6rem;
  border-radius: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.journal-note { font-size: .85rem; color: var(--text); line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
.journal-note-preview { font-size: .85rem; color: var(--text); line-height: 1.65; word-break: break-word; }
.journal-note-full { font-size: .85rem; color: var(--text); line-height: 1.65; white-space: pre-wrap; word-break: break-word; display: none; }
.journal-read-more {
  display: inline-block;
  margin-top: .5rem;
  font-size: .75rem;
  color: var(--gold, #C4A265);
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  font-family: inherit;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.journal-tags { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .75rem; }
.journal-tag {
  font-size: .68rem;
  background: var(--surface2);
  color: var(--muted);
  padding: .18rem .55rem;
  border-radius: 10px;
  border: 1px solid var(--border);
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  padding: .75rem 1.25rem;
  border-radius: 8px;
  font-size: .88rem;
  font-family: inherit;
  text-decoration: none;
  font-weight: 600;
  min-height: 44px;
  cursor: pointer;
  border: none;
  transition: opacity .2s;
  white-space: nowrap;
}
.btn-primary { background: var(--sand); color: #0a0807; }
.btn-secondary {
  background: var(--surface2);
  color: var(--sand);
  border: 1px solid var(--border);
}
.btn:hover { opacity: .82; }
.btn-row {
  display: flex;
  flex-wrap: wrap;
  gap: .75rem;
  margin-bottom: 1.5rem;
  align-items: center;
}

/* Footer */
.footer {
  border-top: 1px solid var(--border);
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: .8rem;
  background: radial-gradient(ellipse at bottom, rgba(196,162,101,.04) 0%, transparent 65%);
}
.dune-quote { font-style: italic; color: var(--sand); margin-bottom: .4rem; font-size: .88rem; opacity: .85; }
.dune-attribution { font-size: .72rem; color: var(--muted); opacity: .65; margin-bottom: .75rem; }

/* Responsive — 768px breakpoint */
@media (max-width: 768px) {
  .container { padding: 0 .875rem; }
  .hero { padding: 1.75rem .875rem 1.5rem; }
  .stat-row { grid-template-columns: repeat(2, 1fr); gap: .6rem; }
  .chart-container { height: 250px; }
  .tab-btn { padding: .85rem 1rem; font-size: .84rem; }
  .section-header { font-size: .86rem; }
  .btn-row { flex-direction: column; }
  .btn { width: 100%; }
  tbody td { padding: .6rem .75rem; }
  .stat-value { font-size: 1.2rem; }
}

/* Responsive — 480px breakpoint */
@media (max-width: 480px) {
  .hero h1 { font-size: 1.1rem; }
  .hero-tagline { font-size: .8rem; }
  .stat-row { grid-template-columns: repeat(2, 1fr); gap: .5rem; }
  .stat-card { padding: .75rem; }
  .stat-value { font-size: 1.05rem; }
  .tab-btn { padding: .75rem .85rem; font-size: .78rem; }
  .report-card, .journal-card { padding: .875rem; }
  .chart-container { height: 210px; }
}
"""

# ── JavaScript (plain string — no f-string) ───────────────────────────────────

JS_CODE = """
// Tab switching
function initTabs() {
  const btns = document.querySelectorAll('.tab-btn');
  const panels = document.querySelectorAll('.tab-content');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      btns.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected','false'); });
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      btn.setAttribute('aria-selected','true');
      const panel = document.getElementById('tab-' + tab);
      if (panel) panel.classList.add('active');
      if (window.perfChart) window.perfChart.resize();
      if (window.sparkChart) window.sparkChart.resize();
    });
  });
}

// Expandable thesis rows
function toggleThesis(id) {
  const row = document.getElementById('thesis-' + id);
  const btn = document.querySelector('[data-trade-id="' + id + '"]');
  if (!row) return;
  const isOpen = row.classList.toggle('open');
  if (btn) btn.classList.toggle('open', isOpen);
}

// Sentiment sparkline (small Chart.js line chart)
function initSparkline(scoreData) {
  const canvas = document.getElementById('sparkline');
  if (!canvas || scoreData.length < 2) return;
  window.sparkChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: scoreData.map(d => d[0]),
      datasets: [{
        data: scoreData.map(d => d[1]),
        borderColor: '#C4A265',
        backgroundColor: 'rgba(196,162,101,0.08)',
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: scoreData.map(d => d[1] > 2 ? '#6ECB63' : d[1] < -2 ? '#E05252' : '#E07B2A'),
        tension: 0.35,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1c1810', titleColor: '#C4A265',
          bodyColor: '#E8DCC8', borderColor: '#2d2315', borderWidth: 1,
        }
      },
      scales: {
        x: { ticks: { color: '#8a7660', font: { size: 10 }, maxRotation: 45 }, grid: { color: '#2d2315' } },
        y: { ticks: { color: '#8a7660', font: { size: 10 } }, grid: { color: '#2d2315' }, suggestedMin: -10, suggestedMax: 10 }
      }
    }
  });
}

// Portfolio performance chart
function initPerfChart(labels, values, startingCapital) {
  const canvas = document.getElementById('perfChart');
  if (!canvas || values.length < 1) return;
  window.perfChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Portfolio Value',
          data: values,
          borderColor: '#C4A265',
          backgroundColor: 'rgba(196,162,101,0.07)',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: values.map(v => v >= startingCapital ? '#6ECB63' : '#E05252'),
          tension: 0.3,
          fill: true,
        },
        {
          label: 'Starting Capital',
          data: values.map(() => startingCapital),
          borderColor: '#3d3020',
          borderWidth: 1,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, labels: { color: '#8a7660', font: { size: 11 }, boxWidth: 14 } },
        tooltip: {
          backgroundColor: '#1c1810', titleColor: '#C4A265',
          bodyColor: '#E8DCC8', borderColor: '#2d2315', borderWidth: 1,
          callbacks: {
            label: ctx => {
              const v = ctx.raw;
              if (ctx.datasetIndex === 0) {
                const diff = v - startingCapital;
                const pct = startingCapital ? ((diff / startingCapital) * 100).toFixed(2) : 0;
                const sign = diff >= 0 ? '+' : '';
                return ' $' + v.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) + ' (' + sign + pct + '%)';
              }
              return ' $' + v.toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2}) + ' (baseline)';
            }
          }
        }
      },
      scales: {
        x: { ticks: { color: '#8a7660', font: { size: 10 }, maxRotation: 45 }, grid: { color: '#2d2315' } },
        y: {
          ticks: {
            color: '#8a7660', font: { size: 10 },
            callback: v => '$' + v.toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0})
          },
          grid: { color: '#2d2315' }
        }
      }
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  if (typeof SCORE_DATA !== 'undefined') initSparkline(SCORE_DATA);
  if (typeof PERF_LABELS !== 'undefined' && typeof PERF_VALUES !== 'undefined') {
    initPerfChart(PERF_LABELS, PERF_VALUES, STARTING_CAPITAL);
  }
});
"""


# ── Main build function ───────────────────────────────────────────────────────

def build_dashboard():
    reports_dir = Path("reports")
    docs_dir = Path("docs")
    simulator_dir = Path("simulator")
    docs_dir.mkdir(exist_ok=True)

    # ── Load simulator data ────────────────────────────────────────────────────
    portfolio = load_json_safe(simulator_dir / "portfolio.json", {
        "cash": 0, "starting_capital": 25000, "positions": [], "unsettled_cash": []
    })
    trades = load_json_safe(simulator_dir / "trades.json", [])
    performance = load_json_safe(simulator_dir / "performance.json", [])
    strategy_log = load_json_safe(simulator_dir / "strategy_log.json", [])

    # ── Load report files ──────────────────────────────────────────────────────
    reports_json = []
    for json_file in sorted(reports_dir.glob("*.json"), reverse=True):
        try:
            with open(json_file) as f:
                data = json.load(f)
                data["_filename"] = json_file.stem
                reports_json.append(data)
        except Exception:
            pass

    html_reports_list = []
    if not reports_json:
        for html_file in sorted(reports_dir.glob("*.html"), reverse=True):
            html_reports_list.append({"date": html_file.stem, "filename": html_file.name})

    all_reports_count = len(reports_json) + len(html_reports_list)
    last_updated = datetime.now().strftime("%b %d, %Y")

    # ── Portfolio stats ────────────────────────────────────────────────────────
    cash = portfolio.get("cash", 0)
    starting_capital = portfolio.get("starting_capital", 25000)
    positions = portfolio.get("positions", [])
    unsettled_items = portfolio.get("unsettled_cash", [])
    unsettled_total = sum(u.get("amount", 0) for u in unsettled_items)

    # Latest performance snapshot
    eod_entries = [p for p in performance if not p.get("type")]
    midday_entries = [p for p in performance if p.get("type") == "midday"]
    latest_perf = eod_entries[-1] if eod_entries else (midday_entries[-1] if midday_entries else None)
    total_value = latest_perf.get("portfolio_value", cash + unsettled_total) if latest_perf else (cash + unsettled_total)
    total_pnl = total_value - starting_capital
    total_pnl_pct = (total_pnl / starting_capital * 100) if starting_capital else 0
    pnl_color = "var(--bull)" if total_pnl >= 0 else "var(--bear)"
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_pct_sign = "+" if total_pnl_pct >= 0 else ""

    num_trades = len(trades)
    num_sells = sum(1 for t in trades if t.get("action") == "SELL")
    realized_wins = sum(1 for t in trades if t.get("action") == "SELL" and (t.get("realized_pnl") or 0) > 0)
    win_rate = f"{(realized_wins / num_sells * 100):.0f}%" if num_sells else "—"

    # ── Sentiment stats ────────────────────────────────────────────────────────
    latest_sentiment = reports_json[0].get("overall_sentiment", "—") if reports_json else "—"
    latest_score = reports_json[0].get("sentiment_score", 0) if reports_json else 0
    if latest_score > 2:
        latest_sent_color = "var(--bull)"
    elif latest_score < -2:
        latest_sent_color = "var(--bear)"
    else:
        latest_sent_color = "var(--spice)"

    scores_30 = [r.get("sentiment_score", 0) for r in reports_json[:30]]
    avg_score = sum(scores_30) / len(scores_30) if scores_30 else None
    avg_score_str = f"{avg_score:+.1f}" if avg_score is not None else "—"
    bullish_count = sum(1 for r in reports_json[:30] if r.get("overall_sentiment") == "BULLISH")
    bearish_count = sum(1 for r in reports_json[:30] if r.get("overall_sentiment") == "BEARISH")

    score_data = [(r.get("_filename", ""), r.get("sentiment_score", 0))
                  for r in reversed(reports_json[-30:])]

    # ── Performance chart data ─────────────────────────────────────────────────
    chart_labels = []
    chart_values = []
    for p in eod_entries[-60:]:
        chart_labels.append(p.get("date", ""))
        chart_values.append(p.get("portfolio_value", 0))
    if len(chart_labels) < 2:
        for p in sorted(performance, key=lambda x: (x.get("date", ""), x.get("time", ""))):
            lbl = p.get("date", "")
            if p.get("time"):
                lbl += " " + p["time"]
            chart_labels.append(lbl)
            chart_values.append(p.get("portfolio_value", 0))

    # ── Report cards HTML ──────────────────────────────────────────────────────
    def fmt_report_date(stem: str) -> str:
        """Format a YYYY-MM-DD filename stem as 'Apr 7, 2026'."""
        try:
            d = datetime.strptime(stem, "%Y-%m-%d")
            return f"{d.strftime('%b')} {d.day}, {d.year}"
        except Exception:
            return stem

    report_cards_html = ""
    for r in reports_json:
        date = fmt_report_date(r["_filename"])
        sentiment = r.get("overall_sentiment", "")
        score = r.get("sentiment_score", 0)
        if score > 2:
            sc = "var(--bull)"
        elif score < -2:
            sc = "var(--bear)"
        else:
            sc = "var(--spice)"
        summary = (r.get("executive_summary", "") or "")[:200]
        if len(r.get("executive_summary", "") or "") > 200:
            summary += "…"
        themes = r.get("top_themes", [])
        themes_html = "".join(f'<span class="theme">{t}</span>' for t in themes[:4])
        score_badge = (
            f'<span style="color:{sc};font-family:\'JetBrains Mono\',monospace;font-size:.85rem;font-weight:700">'
            f'{sentiment} ({score:+d})</span>'
        ) if sentiment else ""

        report_cards_html += f"""
        <a href="reports/{r['_filename']}.html" class="report-card">
          <div class="card-header">
            <span class="card-date">{date}</span>
            {score_badge}
          </div>
          {"<div class='card-themes'>" + themes_html + "</div>" if themes_html else ""}
          <div class="card-summary">{summary if summary else "View full report →"}</div>
        </a>"""

    for r in html_reports_list:
        report_cards_html += f"""
        <a href="reports/{r['filename']}" class="report-card">
          <div class="card-header">
            <span class="card-date">{fmt_report_date(r['date'])}</span>
          </div>
          <div class="card-summary">View full report →</div>
        </a>"""

    if not report_cards_html:
        report_cards_html = '<div class="empty-state">No reports yet. The spice will flow soon.</div>'

    # ── Sparkline section ──────────────────────────────────────────────────────
    sparkline_section = ""
    if len(score_data) >= 2:
        sparkline_section = """
  <div class="chart-wrap">
    <div class="chart-title">30-Day Sentiment Score Trend</div>
    <div class="chart-container-sm">
      <canvas id="sparkline"></canvas>
    </div>
  </div>"""

    # ── Positions table rows ───────────────────────────────────────────────────
    positions_rows = ""
    if positions:
        for pos in positions:
            ticker = pos.get("ticker", "—")
            shares = pos.get("shares", 0)
            avg_cost = pos.get("avg_cost", 0)
            entry_date = pos.get("entry_date", "—")
            stop_p = pos.get("stop_loss_price")
            target_p = pos.get("target_price")
            cost_basis = avg_cost * shares
            strategy = pos.get("strategy", "—")
            stop_str = f"${stop_p:.2f}" if stop_p else "—"
            target_str = f"${target_p:.2f}" if target_p else "—"
            positions_rows += f"""
              <tr>
                <td data-label="Ticker"><strong style="color:var(--sand)">{ticker}</strong></td>
                <td data-label="Shares">{shares}</td>
                <td data-label="Avg Cost">${avg_cost:.2f}</td>
                <td data-label="Cost Basis">${cost_basis:,.2f}</td>
                <td data-label="Entry">{entry_date}</td>
                <td data-label="Stop">{stop_str}</td>
                <td data-label="Target">{target_str}</td>
                <td data-label="Strategy">{strategy}</td>
              </tr>"""
    else:
        positions_rows = '<tr><td colspan="8" class="empty-state">No open positions — fully in cash. Walk without rhythm.</td></tr>'

    # ── Trade history rows ─────────────────────────────────────────────────────
    trades_rows = ""
    for trade in reversed(trades):
        tid = trade.get("id", "")
        tdate = trade.get("date", "")
        ticker = trade.get("ticker", "")
        action = trade.get("action", "")
        act_cls = "bull" if action == "BUY" else "bear"
        shares = trade.get("shares", 0)
        price = trade.get("price", 0)
        total = trade.get("total", 0)
        strategy = trade.get("strategy", "—")

        # P&L display
        realized_pnl = trade.get("realized_pnl")
        realized_pct = trade.get("realized_pnl_pct")
        rr = trade.get("risk_reward_ratio")
        if action == "SELL" and realized_pnl is not None:
            p_sign = "+" if realized_pnl >= 0 else ""
            p_col = "var(--bull)" if realized_pnl >= 0 else "var(--bear)"
            pnl_cell = (f'<span style="color:{p_col}">'
                        f'{p_sign}${realized_pnl:,.2f} ({p_sign}{realized_pct:.1f}%)</span>')
        elif action == "BUY" and rr:
            pnl_cell = f'<span style="color:var(--muted)">R:R {rr:.2f}×</span>'
        else:
            pnl_cell = '<span style="color:var(--muted)">—</span>'

        # Thesis details
        thesis_parts = []
        if trade.get("thesis"):
            thesis_parts.append(f"<p><strong>Thesis:</strong> {trade['thesis']}</p>")
        if trade.get("pattern"):
            thesis_parts.append(f"<p><strong>Pattern:</strong> {trade['pattern']}</p>")
        if trade.get("setup_type"):
            thesis_parts.append(f"<p><strong>Setup:</strong> {trade['setup_type']}</p>")
        if trade.get("timeframe"):
            thesis_parts.append(f"<p><strong>Timeframe:</strong> {trade['timeframe']}</p>")
        if trade.get("entry_trigger"):
            thesis_parts.append(f"<p><strong>Entry Trigger:</strong> {trade['entry_trigger']}</p>")
        if trade.get("exit_plan"):
            thesis_parts.append(f"<p><strong>Exit Plan:</strong> {trade['exit_plan']}</p>")
        if action == "BUY":
            sl = trade.get("stop_loss_price")
            tgt = trade.get("target_price")
            sl_pct = trade.get("stop_loss_pct")
            tgt_pct = trade.get("target_pct")
            if sl:
                thesis_parts.append(
                    f"<p><strong>Stop Loss:</strong> ${sl:.2f} (-{sl_pct:.1f}%)</p>")
            if tgt:
                thesis_parts.append(
                    f"<p><strong>Target:</strong> ${tgt:.2f} (+{tgt_pct:.1f}%)</p>")
        if action == "SELL":
            sd = trade.get("settlement_date")
            if sd:
                thesis_parts.append(f"<p><strong>Settlement:</strong> {sd}</p>")

        expand_btn = ""
        thesis_row_html = ""
        if thesis_parts:
            expand_btn = (
                f'<button class="expand-btn" data-trade-id="{tid}" '
                f'onclick="toggleThesis({tid})" title="View thesis details" '
                f'aria-label="Toggle thesis for trade {tid}">▶</button>'
            )
            thesis_row_html = (
                f'<tr class="thesis-row" id="thesis-{tid}">'
                f'<td colspan="9"><div class="thesis-content">'
                + "".join(thesis_parts) +
                f'</div></td></tr>'
            )

        trades_rows += f"""
            <tr>
              <td data-label="ID">{expand_btn}#{tid}</td>
              <td data-label="Date">{tdate}</td>
              <td data-label="Action"><span class="{act_cls}">{action}</span></td>
              <td data-label="Ticker"><strong style="color:var(--sand)">{ticker}</strong></td>
              <td data-label="Shares">{shares}</td>
              <td data-label="Price">${price:.2f}</td>
              <td data-label="Total">${total:,.2f}</td>
              <td data-label="P&amp;L / R:R">{pnl_cell}</td>
              <td data-label="Strategy">{strategy}</td>
            </tr>
            {thesis_row_html}"""

    if not trades_rows:
        trades_rows = '<tr><td colspan="9" class="empty-state">No trades yet. The patient hunter waits for the right moment.</td></tr>'

    # ── Unsettled cash table ───────────────────────────────────────────────────
    unsettled_section = ""
    if unsettled_items:
        rows = ""
        for u in unsettled_items:
            rows += (
                f'<tr>'
                f'<td data-label="Ticker">{u.get("ticker","—")}</td>'
                f'<td data-label="Amount">${u.get("amount",0):,.2f}</td>'
                f'<td data-label="Trade #">#{u.get("trade_id","—")}</td>'
                f'<td data-label="Settles">{u.get("settlement_date","—")}</td>'
                f'</tr>'
            )
        unsettled_section = f"""
      <div class="section-header">⏳ Unsettled Cash (T+2)</div>
      <div class="table-wrap mobile-card-table-wrap">
        <table class="mobile-card-table">
          <thead><tr><th>Ticker</th><th>Amount</th><th>Trade #</th><th>Settles</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>"""

    # ── Strategy journal ───────────────────────────────────────────────────────
    journal_html = ""
    type_colors = {
        "initialization": ("#4A8FCC", "#0d1f35"),
        "trade_decision": ("#C4A265", "#2a1f10"),
        "midday_check": ("#8a7660", "#1c1810"),
        "trade": ("#6ECB63", "#0d2010"),
        "note": ("#8a7660", "#1c1810"),
    }
    for entry in reversed(strategy_log[-25:]):
        e_date = entry.get("date", "")
        e_type = entry.get("type", "note")
        note = entry.get("note", "")
        tags = entry.get("tags", [])
        tc, tbg = type_colors.get(e_type, ("#8a7660", "#1c1810"))
        tags_html = "".join(f'<span class="journal-tag">{t}</span>' for t in tags)
        import html as _html
        note_escaped = _html.escape(note)
        PREVIEW_LEN = 400
        if len(note) > PREVIEW_LEN:
            preview = _html.escape(note[:PREVIEW_LEN].rstrip())
            note_block = f"""<span class="journal-note-preview">{preview}…</span><span class="journal-note-full" style="display:none;white-space:pre-wrap;">{note_escaped}</span><button onclick="var full=this.previousElementSibling;var preview=full.previousElementSibling;if(full.style.display==='none'){{full.style.display='inline';preview.style.display='none';this.textContent='Read less ↑';}}else{{full.style.display='none';preview.style.display='inline';this.textContent='Read more ↓';}}" style="background:none;border:none;color:#E8841A;cursor:pointer;font-size:14px;padding:4px 0;min-height:44px;display:block;">Read more ↓</button>"""
        else:
            note_block = f'<div class="journal-note">{note_escaped}</div>'
        journal_html += f"""
        <div class="journal-card">
          <div class="journal-card-header">
            <span class="journal-date">{e_date}</span>
            <span class="journal-type" style="color:{tc};background:{tbg}">{e_type.replace('_',' ').title()}</span>
          </div>
          {note_block}
          {"<div class='journal-tags'>" + tags_html + "</div>" if tags_html else ""}
        </div>"""
    if not journal_html:
        journal_html = '<div class="empty-state">No journal entries yet.</div>'

    # ── Performance chart section ──────────────────────────────────────────────
    perf_chart_section = ""
    if chart_values:
        perf_chart_section = """
      <div class="chart-wrap">
        <div class="chart-title">Portfolio Value Over Time</div>
        <div class="chart-container">
          <canvas id="perfChart"></canvas>
        </div>
      </div>"""

    # ── JS data injection ──────────────────────────────────────────────────────
    js_data = (
        f"const SCORE_DATA = {json.dumps(score_data)};\n"
        f"const PERF_LABELS = {json.dumps(chart_labels)};\n"
        f"const PERF_VALUES = {json.dumps(chart_values)};\n"
        f"const STARTING_CAPITAL = {json.dumps(starting_capital)};\n"
    )

    # ── Assemble final HTML ────────────────────────────────────────────────────
    dashboard_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="#0a0807">
  <meta name="description" content="Muad'Dib Market Intelligence — AI-powered daily market brief and paper trader dashboard">
  <title>Muad'Dib Market Intelligence</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>
<div class="container">

  <!-- ── Hero Header ───────────────────────────────────────────────────── -->
  <header class="hero">
    <div class="hawk-emblem">{HAWK_SVG}</div>
    <h1>Muad'Dib Market Intelligence</h1>
    <p class="hero-tagline">The Sleeper Has Awakened</p>
    <p class="hero-sub">Daily market intelligence &middot; Updated at 6 AM ET &middot; {last_updated}</p>
  </header>

  <!-- ── Tab Navigation ────────────────────────────────────────────────── -->
  <nav class="tab-nav" role="tablist" aria-label="Dashboard sections">
    <button class="tab-btn active" data-tab="reports" role="tab" aria-selected="true" aria-controls="tab-reports">
      &#128202; Daily Reports
    </button>
    <button class="tab-btn" data-tab="trader" role="tab" aria-selected="false" aria-controls="tab-trader">
      &#9876; Paper Trader
    </button>
  </nav>

  <!-- ══════════════════════════════════════════════════════════════════════ -->
  <!-- REPORTS TAB                                                           -->
  <!-- ══════════════════════════════════════════════════════════════════════ -->
  <div id="tab-reports" class="tab-content active" role="tabpanel" aria-labelledby="tab-reports-btn">

    <!-- Sentiment Stats -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">Total Reports</div>
        <div class="stat-value" style="color:var(--atreides)">{all_reports_count}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Latest Sentiment</div>
        <div class="stat-value" style="color:{latest_sent_color}">{latest_sentiment}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">30-Day Avg Score</div>
        <div class="stat-value">{avg_score_str}</div>
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

    {sparkline_section}

    <!-- Report Cards -->
    <div class="section-header">&#128203; Recent Reports</div>
    <div class="reports-grid">
      {report_cards_html}
    </div>

  </div><!-- /tab-reports -->

  <!-- ══════════════════════════════════════════════════════════════════════ -->
  <!-- PAPER TRADER TAB                                                      -->
  <!-- ══════════════════════════════════════════════════════════════════════ -->
  <div id="tab-trader" class="tab-content" role="tabpanel" aria-labelledby="tab-trader-btn">

    <!-- Portfolio Overview -->
    <div class="section-header">&#128176; Portfolio Overview</div>
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-label">Total Value</div>
        <div class="stat-value" style="color:var(--sand)">${total_value:,.2f}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Settled Cash</div>
        <div class="stat-value">${cash:,.2f}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total P&amp;L</div>
        <div class="stat-value" style="color:{pnl_color}">{pnl_sign}${abs(total_pnl):,.2f}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Return</div>
        <div class="stat-value" style="color:{pnl_color}">{pnl_pct_sign}{total_pnl_pct:.2f}%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Unsettled Cash</div>
        <div class="stat-value" style="color:var(--muted)">${unsettled_total:,.2f}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Open Positions</div>
        <div class="stat-value">{len(positions)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Trades</div>
        <div class="stat-value">{num_trades}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Win Rate</div>
        <div class="stat-value" style="color:var(--bull)">{win_rate}</div>
      </div>
    </div>

    <!-- Current Positions -->
    <div class="section-header">&#128200; Current Positions</div>
    <div class="table-wrap mobile-card-table-wrap">
      <table class="mobile-card-table">
        <thead>
          <tr>
            <th>Ticker</th><th>Shares</th><th>Avg Cost</th>
            <th>Cost Basis</th><th>Entry</th><th>Stop</th>
            <th>Target</th><th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          {positions_rows}
        </tbody>
      </table>
    </div>

    {perf_chart_section}

    <!-- Trade History -->
    <div class="section-header">&#128221; Trade History</div>
    <div class="table-wrap mobile-card-table-wrap">
      <table class="mobile-card-table">
        <thead>
          <tr>
            <th>ID</th><th>Date</th><th>Action</th><th>Ticker</th>
            <th>Shares</th><th>Price</th><th>Total</th>
            <th>P&amp;L / R:R</th><th>Strategy</th>
          </tr>
        </thead>
        <tbody>
          {trades_rows}
        </tbody>
      </table>
    </div>

    {unsettled_section}

    <!-- Strategy Journal -->
    <div class="section-header">&#128211; Strategy Journal</div>
    <div class="journal-grid">
      {journal_html}
    </div>

  </div><!-- /tab-trader -->

</div><!-- /container -->

<!-- ── Footer ──────────────────────────────────────────────────────────────── -->
<footer class="footer">
  <p class="dune-quote">&ldquo;I must not fear. Fear is the mind-killer. Fear is the little-death that brings total obliteration.&rdquo;</p>
  <p class="dune-attribution">&mdash; Frank Herbert, Dune</p>
  <p>Muad'Dib Market Intelligence &middot; {all_reports_count} reports &middot; {last_updated}</p>
</footer>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
{js_data}
{JS_CODE}
</script>
</body>
</html>"""

    with open(docs_dir / "index.html", "w") as f:
        f.write(dashboard_html)

    # Copy individual HTML reports to docs/reports/
    docs_reports = docs_dir / "reports"
    docs_reports.mkdir(exist_ok=True)
    for html_file in reports_dir.glob("*.html"):
        shutil.copy(html_file, docs_reports / html_file.name)

    print(f"✅ Dashboard built: {all_reports_count} reports, {len(positions)} positions, {num_trades} trades")


if __name__ == "__main__":
    build_dashboard()
