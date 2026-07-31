#!/usr/bin/env python3
"""
apply_renovation.py — One-time UI renovation for scripts/build_dashboard.py.
Retro-80s CRT terminal aesthetic on the Dune identity + newsletter TL;DR strip.
Surgical patches only; idempotent.
"""

import re
import sys
from pathlib import Path

TARGET = Path("scripts/build_dashboard.py")

NEW_CSS = '''
:root {
  --bg: #060410;
  --surface: #0d0a1a;
  --surface2: #141024;
  --surface3: #1a1530;
  --border: #2b2247;
  --text: #E8DCC8;
  --muted: #8d80a8;
  --sand: #D4B078;
  --spice: #FF8A1E;
  --atreides: #4DC3FF;
  --bull: #3DFF8A;
  --bear: #FF3D5E;
  --glow-spice: 0 0 8px rgba(255,138,30,.45), 0 0 22px rgba(255,138,30,.18);
  --glow-sand: 0 0 10px rgba(212,176,120,.35);
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background:
    radial-gradient(ellipse 120% 60% at 50% -10%, rgba(255,138,30,.06) 0%, transparent 60%),
    radial-gradient(ellipse 100% 50% at 50% 110%, rgba(77,195,255,.05) 0%, transparent 60%),
    var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 16px; line-height: 1.6; min-height: 100vh; -webkit-text-size-adjust: 100%;
}
body::after {
  content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 999;
  background: repeating-linear-gradient(0deg, rgba(0,0,0,.14) 0px, rgba(0,0,0,.14) 1px, transparent 1px, transparent 3px);
  opacity: .5;
}
.container { max-width: 1100px; margin: 0 auto; padding: 0 1rem; width: 100%; }
.hero {
  text-align: center; padding: 3rem 1rem 2.25rem;
  border-bottom: 1px solid var(--spice);
  box-shadow: 0 1px 0 rgba(255,138,30,.25), 0 10px 40px -20px rgba(255,138,30,.35);
  background:
    linear-gradient(to top, rgba(255,138,30,.10) 0%, transparent 38%),
    repeating-linear-gradient(0deg, rgba(255,138,30,.10) 0px, rgba(255,138,30,.10) 1px, transparent 1px, transparent 14px),
    radial-gradient(ellipse at top, rgba(212,176,120,.10) 0%, transparent 65%);
}
.hawk-emblem { margin: 0 auto 1.25rem; color: var(--spice); filter: drop-shadow(0 0 6px rgba(255,138,30,.55)); opacity: .95; width: clamp(55px, 12vw, 88px); }
.hawk-emblem svg { width: 100%; height: auto; display: block; }
.hero h1 { font-family: 'Orbitron', 'Share Tech Mono', monospace; font-size: clamp(1.15rem, 4vw, 1.9rem); color: var(--sand); font-weight: 700; letter-spacing: .14em; text-transform: uppercase; text-shadow: var(--glow-sand); }
.hero-tagline { font-family: 'Share Tech Mono', monospace; font-size: clamp(.8rem, 2.5vw, .95rem); color: var(--spice); margin-top: .5rem; letter-spacing: .18em; text-transform: uppercase; text-shadow: var(--glow-spice); }
.hero-sub { font-family: 'Share Tech Mono', monospace; font-size: .74rem; color: var(--muted); margin-top: .45rem; letter-spacing: .08em; }
.tab-nav { display: flex; overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none; border-bottom: 1px solid var(--border); background: rgba(13,10,26,.92); backdrop-filter: blur(6px); position: sticky; top: 0; z-index: 50; }
.tab-nav::-webkit-scrollbar { display: none; }
.tab-btn { padding: 1rem 1.5rem; white-space: nowrap; background: none; border: none; border-bottom: 2px solid transparent; color: var(--muted); font-family: 'Share Tech Mono', monospace; font-size: .85rem; letter-spacing: .08em; text-transform: uppercase; cursor: pointer; min-height: 48px; transition: color .2s, border-color .2s, text-shadow .2s; }
.tab-btn.active { color: var(--spice); border-bottom-color: var(--spice); text-shadow: var(--glow-spice); }
.tab-btn:hover:not(.active) { color: var(--text); }
.tab-content { display: none; padding: 1.75rem 0 3rem; }
.tab-content.active { display: block; }
.tldr { background: linear-gradient(135deg, rgba(255,138,30,.08) 0%, var(--surface) 45%); border: 1px solid var(--spice); border-radius: 8px; box-shadow: 0 0 0 1px rgba(255,138,30,.15), 0 8px 30px -18px rgba(255,138,30,.5); padding: 1.25rem 1.4rem; margin-bottom: 1.5rem; }
.tldr-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem; margin-bottom: .7rem; }
.tldr-title { font-family: 'Share Tech Mono', monospace; color: var(--spice); font-size: .85rem; letter-spacing: .14em; text-transform: uppercase; text-shadow: var(--glow-spice); }
.regime-badge { font-family: 'Share Tech Mono', monospace; font-size: .7rem; letter-spacing: .12em; padding: .2rem .65rem; border-radius: 3px; border: 1px solid currentColor; text-transform: uppercase; }
.tldr-gist { font-size: .95rem; line-height: 1.65; color: var(--text); margin-bottom: .8rem; }
.tldr-items { list-style: none; margin: 0 0 .8rem; padding: 0; }
.tldr-items li { font-family: 'JetBrains Mono', monospace; font-size: .8rem; color: var(--sand); padding: .3rem 0 .3rem 1.4rem; position: relative; border-bottom: 1px dashed rgba(43,34,71,.8); }
.tldr-items li:last-child { border-bottom: none; }
.tldr-items li::before { content: "▸"; position: absolute; left: .2rem; color: var(--spice); }
.tldr-quote { font-style: italic; color: var(--sand); font-size: .85rem; border-left: 2px solid var(--spice); padding-left: .8rem; opacity: .9; }
.tldr-quote-attr { color: var(--muted); font-style: normal; font-size: .75rem; }
.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr)); gap: .75rem; margin-bottom: 1.5rem; }
.stat-card { background: linear-gradient(180deg, var(--surface2) 0%, var(--surface) 100%); border: 1px solid var(--border); border-top: 2px solid var(--spice); border-radius: 6px; padding: 1rem; }
.stat-label { font-family: 'Share Tech Mono', monospace; font-size: .64rem; color: var(--muted); text-transform: uppercase; letter-spacing: .12em; }
.stat-value { font-size: 1.45rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; margin-top: .25rem; word-break: break-all; text-shadow: 0 0 12px rgba(232,220,200,.15); }
.chart-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1.25rem; margin-bottom: 1.5rem; }
.chart-title { font-family: 'Share Tech Mono', monospace; font-size: .7rem; color: var(--atreides); margin-bottom: .75rem; text-transform: uppercase; letter-spacing: .12em; }
.chart-container { position: relative; height: 350px; width: 100%; }
.chart-container-sm { position: relative; height: 130px; width: 100%; }
.section-header { font-family: 'Share Tech Mono', monospace; font-size: .88rem; color: var(--spice); letter-spacing: .1em; text-transform: uppercase; text-shadow: var(--glow-spice); margin-bottom: .875rem; padding-bottom: .5rem; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: .5rem; }
.reports-grid { display: grid; gap: .75rem; }
.report-card { background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--border); border-radius: 6px; padding: 1.25rem; text-decoration: none; color: inherit; display: block; transition: border-color .2s, background .2s, box-shadow .2s; }
.report-card:hover { border-color: var(--spice); background: var(--surface2); box-shadow: 0 0 18px -6px rgba(255,138,30,.4); }
.card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem; margin-bottom: .5rem; }
.card-date { font-weight: 600; font-size: .92rem; font-family: 'JetBrains Mono', monospace; color: var(--sand); }
.card-themes { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .6rem; }
.theme { background: rgba(77,195,255,.07); color: var(--atreides); padding: .15rem .6rem; border-radius: 2px; font-family: 'Share Tech Mono', monospace; font-size: .68rem; letter-spacing: .04em; border: 1px solid rgba(77,195,255,.3); }
.card-summary { font-size: .84rem; color: var(--muted); line-height: 1.55; }
.table-wrap { overflow-x: auto; margin-bottom: 1.5rem; border-radius: 6px; border: 1px solid var(--border); -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; min-width: 540px; }
thead th { background: var(--surface3); color: var(--spice); font-family: 'Share Tech Mono', monospace; font-size: .66rem; text-transform: uppercase; letter-spacing: .12em; padding: .75rem 1rem; text-align: left; white-space: nowrap; border-bottom: 1px solid var(--spice); }
tbody td { padding: .75rem 1rem; border-bottom: 1px solid var(--border); font-size: .84rem; vertical-align: middle; color: var(--text); }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: rgba(255,138,30,.04); }
.empty-state { text-align: center; color: var(--muted); padding: 2.5rem 1rem; font-style: italic; font-size: .88rem; }
@media (max-width: 768px) {
  .mobile-card-table-wrap { border: none; background: transparent; overflow-x: visible; }
  .mobile-card-table { min-width: unset; width: 100%; }
  .mobile-card-table thead { display: none; }
  .mobile-card-table tbody tr { display: block; background: var(--surface2); margin-bottom: .75rem; border-radius: 6px; padding: .875rem; border: 1px solid var(--border); }
  .mobile-card-table tbody td { display: flex; justify-content: space-between; align-items: flex-start; padding: .3rem 0; border: none; font-size: .84rem; gap: .5rem; }
  .mobile-card-table tbody td::before { content: attr(data-label); font-weight: 600; color: var(--sand); white-space: nowrap; flex-shrink: 0; min-width: 90px; }
  .mobile-card-table tbody tr:last-child td { border: none; }
  .mobile-card-table td[colspan] { display: block; }
  .mobile-card-table td[colspan]::before { display: none; }
}
.bull { color: var(--bull); font-weight: 600; text-shadow: 0 0 10px rgba(61,255,138,.35); }
.bear { color: var(--bear); font-weight: 600; text-shadow: 0 0 10px rgba(255,61,94,.35); }
.neutral { color: var(--spice); }
.expand-btn { cursor: pointer; background: none; border: 1px solid var(--border); color: var(--spice); font-size: .7rem; width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border-radius: 3px; transition: background .15s, transform .2s; margin-right: .35rem; vertical-align: middle; flex-shrink: 0; }
.expand-btn:hover { background: var(--surface2); }
.expand-btn.open { transform: rotate(90deg); }
.thesis-row { display: none; }
.thesis-row.open { display: table-row; }
.thesis-content { padding: 1rem 1.25rem; background: var(--surface2); border-radius: 4px; font-size: .84rem; line-height: 1.65; color: var(--text); border: 1px solid var(--border); border-left: 2px solid var(--spice); }
.thesis-content p { margin-bottom: .5rem; }
.thesis-content p:last-child { margin-bottom: 0; }
.thesis-content strong { color: var(--sand); }
.journal-grid { display: grid; gap: .75rem; margin-bottom: 1.5rem; }
.journal-card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1.125rem; }
.journal-card-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem; margin-bottom: .75rem; }
.journal-date { font-size: .78rem; color: var(--muted); font-family: 'JetBrains Mono', monospace; }
.journal-type { font-family: 'Share Tech Mono', monospace; font-size: .64rem; padding: .18rem .6rem; border-radius: 2px; letter-spacing: .1em; text-transform: uppercase; border: 1px solid currentColor; }
.journal-note { font-size: .85rem; color: var(--text); line-height: 1.65; white-space: pre-wrap; word-break: break-word; }
.journal-note-preview { font-size: .85rem; color: var(--text); line-height: 1.65; word-break: break-word; }
.journal-note-full { font-size: .85rem; color: var(--text); line-height: 1.65; white-space: pre-wrap; word-break: break-word; display: none; }
.journal-read-more { display: inline-block; margin-top: .5rem; font-size: .75rem; color: var(--sand); cursor: pointer; background: none; border: none; padding: 0; font-family: inherit; text-decoration: underline; text-underline-offset: 2px; }
.journal-tags { display: flex; flex-wrap: wrap; gap: .35rem; margin-top: .75rem; }
.journal-tag { font-family: 'Share Tech Mono', monospace; font-size: .64rem; background: var(--surface2); color: var(--muted); padding: .18rem .55rem; border-radius: 2px; border: 1px solid var(--border); }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: .4rem; padding: .75rem 1.25rem; border-radius: 4px; font-family: 'Share Tech Mono', monospace; font-size: .85rem; letter-spacing: .06em; text-decoration: none; font-weight: 600; min-height: 44px; cursor: pointer; border: none; transition: opacity .2s, box-shadow .2s; white-space: nowrap; }
.btn-primary { background: var(--spice); color: #060410; box-shadow: var(--glow-spice); }
.btn-secondary { background: var(--surface2); color: var(--spice); border: 1px solid var(--spice); }
.btn:hover { opacity: .85; }
.btn-row { display: flex; flex-wrap: wrap; gap: .75rem; margin-bottom: 1.5rem; align-items: center; }
.footer { border-top: 1px solid var(--spice); box-shadow: 0 -1px 0 rgba(255,138,30,.2); padding: 2.5rem 1rem; text-align: center; color: var(--muted); font-size: .8rem; background: radial-gradient(ellipse at bottom, rgba(255,138,30,.05) 0%, transparent 65%); }
.dune-quote { font-style: italic; color: var(--sand); margin-bottom: .4rem; font-size: .88rem; opacity: .9; }
.dune-attribution { font-size: .72rem; color: var(--muted); opacity: .65; margin-bottom: .75rem; }
@media (max-width: 768px) {
  .container { padding: 0 .875rem; }
  .hero { padding: 1.75rem .875rem 1.5rem; }
  .stat-row { grid-template-columns: repeat(2, 1fr); gap: .6rem; }
  .chart-container { height: 250px; }
  .tab-btn { padding: .85rem 1rem; font-size: .78rem; }
  .section-header { font-size: .82rem; }
  .btn-row { flex-direction: column; }
  .btn { width: 100%; }
  tbody td { padding: .6rem .75rem; }
  .stat-value { font-size: 1.2rem; }
  .tldr { padding: 1rem; }
}
@media (max-width: 480px) {
  .hero h1 { font-size: 1.05rem; }
  .hero-tagline { font-size: .72rem; }
  .stat-row { grid-template-columns: repeat(2, 1fr); gap: .5rem; }
  .stat-card { padding: .75rem; }
  .stat-value { font-size: 1.05rem; }
  .tab-btn { padding: .75rem .85rem; font-size: .72rem; }
  .report-card, .journal-card { padding: .875rem; }
  .chart-container { height: 210px; }
}
'''

TLDR_CODE = '''    # ── TL;DR strip (newsletter-style, from latest report) ────────────────────
    tldr_section = ""
    if reports_json:
        r0 = reports_json[0]
        s0 = r0.get("summary", {}) or {}
        gist = s0.get("gist", "") or (r0.get("executive_summary", "") or "")[:280]
        items = s0.get("actionable_items", []) or []
        quote = s0.get("stoic_quote", {}) or {}
        regime = r0.get("regime", "") or ""
        regime_cls = {"RISK_ON": "bull", "RISK_OFF": "bear"}.get(regime, "neutral")
        items_html = ""
        for it in items[:6]:
            if isinstance(it, dict):
                it = " — ".join(str(v) for v in it.values() if v)
            items_html += f"<li>{it}</li>"
        quote_html = ""
        if isinstance(quote, dict) and quote.get("text"):
            quote_html = ('<div class="tldr-quote">&ldquo;' + str(quote.get("text")) +
                          '&rdquo;<span class="tldr-quote-attr"> &mdash; ' +
                          str(quote.get("attribution", "")) + "</span></div>")
        regime_html = ""
        if regime:
            regime_html = ('<span class="regime-badge ' + regime_cls + '">' +
                           regime.replace("_", "-") + "</span>")
        tldr_section = ('<div class="tldr"><div class="tldr-head">'
                        '<span class="tldr-title">&#9626; TL;DR &mdash; ' +
                        fmt_report_date(r0.get("_filename", "")) + "</span>" + regime_html +
                        '</div><p class="tldr-gist">' + str(gist) + "</p>" +
                        ('<ul class="tldr-items">' + items_html + "</ul>" if items_html else "") +
                        quote_html + "</div>")

'''


def main():
    src = TARGET.read_text(encoding="utf-8")

    if 'class="tldr"' in src or "tldr_section" in src:
        print("✅ Renovation already applied — nothing to do.")
        return 0

    ok = True

    new_src, n = re.subn(r'CSS = """.*?"""', 'CSS = """' + NEW_CSS + '"""', src,
                         count=1, flags=re.DOTALL)
    if n != 1:
        print("❌ CSS block not found"); ok = False
    src = new_src

    old_fonts = "Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap"
    new_fonts = ("Inter:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700"
                 "&family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap")
    if old_fonts in src:
        src = src.replace(old_fonts, new_fonts, 1)
    else:
        print("⚠️ fonts link not found (non-fatal)")

    anchor = "    # ── Assemble final HTML"
    if anchor in src:
        src = src.replace(anchor, TLDR_CODE + anchor, 1)
    else:
        print("❌ assembly anchor not found"); ok = False

    marker = "    <!-- Sentiment Stats -->"
    if marker in src:
        src = src.replace(marker, "    {tldr_section}\n\n" + marker, 1)
    else:
        print("❌ sentiment-stats marker not found"); ok = False

    src = src.replace("Daily market intelligence &middot; Updated at 6 AM ET &middot;",
                      "MARKET INTEL TERMINAL v2 &middot; PRE-MARKET DROP 04:00 CT &middot;", 1)

    if not ok:
        print("❌ Renovation aborted — anchors missing, file left unchanged on disk.")
        return 1

    TARGET.write_text(src, encoding="utf-8")
    print("✅ Renovation applied to scripts/build_dashboard.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
