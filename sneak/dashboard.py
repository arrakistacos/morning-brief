#!/usr/bin/env python3
"""
dashboard.py — Build docs/index.html (and an archived copy per session).

Reads data/cache/{levels,stalk,strike,news,newsrating}-YYYY-MM-DD.json and
renders one self-contained page: no CDN, no build step, all SVG inline. It has
to open fast on a phone at 08:45 and again at 09:00, so nothing blocks on a
network round-trip.

Usage:
    python -m sneak.dashboard                 # today
    python -m sneak.dashboard --date 2026-08-14
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

from . import yahoo
from .news import load_ratings
from .prep import CACHE_DIR
from .quotes import quote_for

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SESSIONS = DOCS / "sessions"

TOP_CARDS = 25

# Ratings that survive the final gate.
#
# `clear` alone. It means headlines were found, read, and judged harmless —
# checked and fine. `quiet` (no headlines at all) is NOT clear: nobody checked
# anything, there was nothing to check. Absence of news is not a clean bill of
# health, so those are held back with caution and flagged.
CLEAR_RATINGS = {"clear"}

SHURIKEN = (
    '<svg viewBox="0 0 100 100" fill="none" aria-hidden="true">'
    '<path d="M50 4 L61 39 L96 50 L61 61 L50 96 L39 61 L4 50 L39 39 Z" '
    'fill="currentColor" opacity=".92"/>'
    '<circle cx="50" cy="50" r="9" fill="#0A0F0D"/>'
    '<circle cx="50" cy="50" r="4" fill="currentColor"/>'
    "</svg>"
)

CSS = """
:root{
  --bg:#0A0F0D; --s1:#101614; --s2:#16201C; --s3:#1C2925;
  --border:#1F2E28; --border2:#2A3D36;
  --ink:#D8E6DF; --muted:#7E9A90; --dim:#5C736B;
  --phos:#4DFFB0; --phos-dim:#14AD6E;
  --bull:#35C98A; --bear:#D6455C;
  --c1:#14AD6E; --c2:#2B8CE8; --c3:#C4870A; --c4:#A85CE8;
  --good:#14AD6E; --warn:#C4870A; --crit:#D6455C;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Roboto Mono",monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{
  background:
    radial-gradient(ellipse 90% 45% at 50% -8%, rgba(77,255,176,.07) 0%, transparent 62%),
    radial-gradient(ellipse 70% 40% at 50% 108%, rgba(43,140,232,.05) 0%, transparent 60%),
    var(--bg);
  color:var(--ink); font-family:var(--mono); font-size:15px; line-height:1.6; min-height:100vh;
}
body::after{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:999;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.13) 0 1px,transparent 1px 3px);
  opacity:.45;
}
.wrap{max-width:1080px;margin:0 auto;padding:0 1rem;width:100%}
a{color:var(--c2)}

.hero{text-align:center;padding:2.4rem 1rem 1.6rem;border-bottom:1px solid var(--phos-dim);
  box-shadow:0 1px 0 rgba(20,173,110,.3),0 12px 44px -26px rgba(77,255,176,.5);
  background:linear-gradient(to top,rgba(20,173,110,.09),transparent 42%);}
.emblem{width:clamp(46px,10vw,64px);margin:0 auto .9rem;color:var(--phos);
  filter:drop-shadow(0 0 8px rgba(77,255,176,.55));animation:spin 14s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.emblem{animation:none}}
.hero h1{font-size:clamp(1.05rem,3.6vw,1.7rem);letter-spacing:.22em;text-transform:uppercase;
  color:var(--phos);text-shadow:0 0 14px rgba(77,255,176,.4);font-weight:700}
.hero .tag{color:var(--phos-dim);letter-spacing:.16em;text-transform:uppercase;font-size:.72rem;margin-top:.5rem}
.hero .sub{color:var(--dim);font-size:.7rem;margin-top:.35rem;letter-spacing:.06em}

.strip{display:flex;flex-wrap:wrap;gap:.5rem;justify-content:center;padding:.9rem 1rem;
  border-bottom:1px solid var(--border);background:var(--s1)}
.pill{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;padding:.25rem .7rem;
  border:1px solid var(--border2);border-radius:99px;color:var(--muted)}
.pill b{color:var(--ink);font-weight:600}
.pill.live{border-color:var(--phos-dim);color:var(--phos)}
.pill.stale{border-color:var(--warn);color:var(--warn)}

.tabs{display:flex;overflow-x:auto;scrollbar-width:none;border-bottom:1px solid var(--border);
  background:rgba(16,22,20,.94);backdrop-filter:blur(6px);position:sticky;top:0;z-index:50}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:.85rem 1.15rem;white-space:nowrap;background:none;border:none;border-bottom:2px solid transparent;
  color:var(--muted);font-family:var(--mono);font-size:.76rem;letter-spacing:.12em;text-transform:uppercase;
  cursor:pointer;min-height:46px}
.tab[aria-selected="true"]{color:var(--phos);border-bottom-color:var(--phos);text-shadow:0 0 10px rgba(77,255,176,.35)}
.panel{display:none;padding:1.4rem 0 3rem}
.panel.on{display:block}

.quote{border-left:2px solid var(--phos-dim);padding:.55rem 0 .55rem .9rem;margin:0 0 1.3rem;
  color:var(--muted);font-style:italic;font-size:.86rem}
.quote span{display:block;font-style:normal;color:var(--dim);font-size:.72rem;margin-top:.3rem}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.7rem;margin-bottom:1.4rem}
.stat{background:linear-gradient(180deg,var(--s2),var(--s1));border:1px solid var(--border);
  border-top:2px solid var(--c1);border-radius:6px;padding:.85rem}
.stat .k{font-size:.6rem;color:var(--dim);text-transform:uppercase;letter-spacing:.14em}
.stat .v{font-size:1.35rem;font-weight:700;margin-top:.2rem;color:var(--ink)}
.stat .n{font-size:.65rem;color:var(--muted);margin-top:.15rem}

h2.sec{font-size:.8rem;color:var(--phos);letter-spacing:.14em;text-transform:uppercase;
  margin:1.6rem 0 .8rem;padding-bottom:.45rem;border-bottom:1px solid var(--border)}
.note{color:var(--muted);font-size:.78rem;margin-bottom:1rem}

.card{background:var(--s1);border:1px solid var(--border);border-left:3px solid var(--c1);
  border-radius:7px;padding:1rem;margin-bottom:.8rem}
.card.top{border-left-color:var(--phos);box-shadow:0 0 0 1px rgba(77,255,176,.13),0 10px 34px -24px rgba(77,255,176,.55)}
.chead{display:flex;flex-wrap:wrap;align-items:center;gap:.55rem;margin-bottom:.7rem}
.rank{font-size:.66rem;color:var(--bg);background:var(--phos);border-radius:4px;padding:.1rem .4rem;font-weight:700}
.sym{font-size:1.15rem;font-weight:700;letter-spacing:.06em;color:var(--ink)}
.rr{margin-left:auto;font-size:1.1rem;font-weight:700;color:var(--phos)}
.rr small{display:block;font-size:.58rem;color:var(--dim);letter-spacing:.12em;text-align:right;font-weight:400}

.chip{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;padding:.16rem .5rem;
  border-radius:4px;border:1px solid currentColor;display:inline-flex;align-items:center;gap:.3rem}
.chip.good{color:var(--good)} .chip.warn{color:var(--warn)} .chip.crit{color:var(--crit)}
.chip.info{color:var(--c2)} .chip.mut{color:var(--muted)}

.grid2{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,340px);gap:1rem;align-items:start}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}

table.kv{width:100%;border-collapse:collapse;font-size:.78rem}
table.kv td{padding:.3rem .4rem;border-bottom:1px solid var(--border)}
table.kv td:first-child{color:var(--dim);white-space:nowrap}
table.kv td:last-child{text-align:right;color:var(--ink);font-weight:600}
.tgt{color:var(--good)} .stp{color:var(--crit)} .ent{color:var(--ink)}

.meta{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.6rem}
.meta span{font-size:.65rem;color:var(--muted);background:var(--s2);border:1px solid var(--border);
  border-radius:4px;padding:.12rem .45rem}

details.news{margin-top:.7rem;border-top:1px dashed var(--border2);padding-top:.5rem}
details.news summary{cursor:pointer;font-size:.7rem;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
details.news li{font-size:.75rem;color:var(--muted);margin:.35rem 0 .35rem 1rem}

table.full{width:100%;border-collapse:collapse;font-size:.75rem;margin-top:.6rem}
table.full th{text-align:left;color:var(--dim);font-weight:600;font-size:.63rem;text-transform:uppercase;
  letter-spacing:.1em;padding:.4rem;border-bottom:1px solid var(--border2)}
table.full td{padding:.38rem .4rem;border-bottom:1px solid var(--border);color:var(--ink)}
table.full tr:hover td{background:var(--s2)}
.scroll{overflow-x:auto}

.legend{display:flex;flex-wrap:wrap;gap:.8rem;font-size:.66rem;color:var(--muted);margin:.5rem 0 1rem}
.legend i{display:inline-block;width:16px;height:3px;border-radius:2px;margin-right:.35rem;vertical-align:middle}

.arch{display:grid;gap:.5rem}
.arch a{display:flex;justify-content:space-between;gap:1rem;background:var(--s1);border:1px solid var(--border);
  border-radius:6px;padding:.7rem .9rem;text-decoration:none;color:var(--ink);font-size:.8rem}
.arch a:hover{border-color:var(--phos-dim)}
.arch span{color:var(--muted);font-size:.72rem}

footer{border-top:1px solid var(--border);padding:1.4rem 1rem 2.4rem;text-align:center;
  color:var(--dim);font-size:.68rem;letter-spacing:.06em}
.empty{background:var(--s1);border:1px dashed var(--border2);border-radius:7px;padding:2rem 1rem;
  text-align:center;color:var(--muted);font-size:.85rem}
"""

JS = """
document.querySelectorAll('.tab').forEach(function(t){
  t.addEventListener('click', function(){
    document.querySelectorAll('.tab').forEach(function(x){x.setAttribute('aria-selected','false')});
    document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('on')});
    t.setAttribute('aria-selected','true');
    var el = document.getElementById(t.dataset.panel);
    if (el) el.classList.add('on');
  });
});
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def _load(prefix: str, day: date) -> dict | None:
    p = CACHE_DIR / f"{prefix}-{day.isoformat()}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _rating_chip(sym: str, news: dict, ratings: dict) -> str:
    r = ratings.get(sym) or {}
    level = (r.get("rating") or (news.get(sym, {}) or {}).get("preflag") or "unrated").lower()
    reason = r.get("reason") or ""
    label, cls, icon = {
        "green": ("news clear", "good", "✓"),
        "clear": ("news clear", "good", "✓"),
        "amber": ("news caution", "warn", "!"),
        "caution": ("news caution", "warn", "!"),
        "red": ("news flagged", "crit", "✕"),
        "flagged": ("news flagged", "crit", "✕"),
        "quiet": ("no news", "mut", "·"),
    }.get(level, ("unrated", "mut", "·"))
    title = f' title="{escape(reason)}"' if reason else ""
    return f'<span class="chip {cls}"{title}>{icon} {label}</span>'


def _card(i: int, row: dict, news: dict, ratings: dict) -> str:
    t = row["trade"]
    b1, lv = row["bar1"], row["levels"]
    sym = row["symbol"]
    hl = (news.get(sym) or {}).get("headlines") or []

    meta = [
        f'drop {b1["drop_pct"]:.2f}%',
        f'wick {b1["wick_pct"]*100:.1f}% of candle',
        f'break {b1["break_depth_pct"]:.2f}% under range low',
    ]
    if b1.get("atr_mult"):
        meta.append(f'{b1["atr_mult"]:.2f}x ATR')
    if b1.get("vol_burst"):
        meta.append(f'open vol {b1["vol_burst"]*100:.0f}% of 20d avg')
    meta.append(f'reclaim {t["bar2"]["reclaim_pct"]*100:.0f}%')
    rsi = t.get("rsi") or {}
    if rsi:
        meta.append(
            f'RSI {rsi["prior"]:.0f} → {rsi["after_red"]:.0f} → {rsi["after_green"]:.0f}'
        )
    if t.get("tight_stop"):
        meta.append("tight stop — inside the spread")

    news_html = ""
    if hl:
        items = "".join(
            f'<li><a href="{escape(h["link"])}" target="_blank" rel="noopener">{escape(h["title"])}</a></li>'
            for h in hl[:5]
        )
        news_html = (
            f'<details class="news"><summary>{len(hl)} headline(s) · last 48h</summary>'
            f"<ul>{items}</ul></details>"
        )

    return f"""
<article class="card{' top' if i <= 3 else ''}">
  <div class="chead">
    <span class="rank">#{i}</span>
    <span class="sym">{escape(sym)}</span>
    {_rating_chip(sym, news, ratings)}
    <span class="chip mut">RSI V-trough</span>
    <span class="rr">{t['rr']:.2f}R<small>risk : reward</small></span>
  </div>
  <table class="kv">
    <tr><td>Entry — green candle close</td><td class="ent">{t['entry']:,.2f}</td></tr>
    <tr><td>Stop — red candle low</td><td class="stp">{t['stop']:,.2f} &nbsp;(-{t['risk_pct']:.2f}%)</td></tr>
    <tr><td>Target — {escape(t['target_kind'])}</td><td class="tgt">{t['target']:,.2f} &nbsp;(+{t['reward_pct']:.2f}%)</td></tr>
    <tr><td>Risk / reward per share</td><td>{t['risk_per_share']:,.2f} : {t['reward_per_share']:,.2f}</td></tr>
    <tr><td>Prev day range</td><td>{lv['range_low']:,.2f} – {lv['range_high']:,.2f}</td></tr>
    <tr><td>Prev day swing low</td><td>{f"{lv['swing_low']:,.2f}" if lv.get('swing_low') is not None else 'none in 60d'}</td></tr>
  </table>
  <div class="meta">{''.join(f'<span>{escape(m)}</span>' for m in meta)}</div>
  {news_html}
</article>"""


def _table(rows: list[dict], news: dict, ratings: dict) -> str:
    head = (
        "<tr><th>#</th><th>Symbol</th><th>R:R</th><th>Entry</th><th>Stop</th><th>Target</th>"
        "<th>Risk %</th><th>Reward %</th><th>RSI prior</th><th>after red</th>"
        "<th>after green</th><th>News</th></tr>"
    )
    body = []
    for i, r in enumerate(rows, 1):
        t = r["trade"]
        rsi = t.get("rsi") or {}
        rat = (ratings.get(r["symbol"]) or {}).get("rating") or (
            news.get(r["symbol"], {}) or {}
        ).get("preflag", "—")
        body.append(
            f"<tr><td>{i}</td><td><b>{escape(r['symbol'])}</b></td><td>{t['rr']:.2f}</td>"
            f"<td>{t['entry']:,.2f}</td><td>{t['stop']:,.2f}</td><td>{t['target']:,.2f}</td>"
            f"<td>{t['risk_pct']:.2f}%</td><td>{t['reward_pct']:.2f}%</td>"
            f"<td>{rsi.get('prior','—')}</td><td>{rsi.get('after_red','—')}</td>"
            f"<td>{rsi.get('after_green','—')}</td><td>{escape(str(rat))}</td></tr>"
        )
    return f'<div class="scroll"><table class="full"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def _stalk_table(cands: list[dict]) -> str:
    head = (
        "<tr><th>#</th><th>Symbol</th><th>Drop %</th><th>Wick %</th><th>ATR x</th>"
        "<th>Break depth %</th><th>Broke swing</th><th>Open vol vs 20d</th><th>Range low</th></tr>"
    )
    body = []
    for i, c in enumerate(cands, 1):
        b = c["bar1"]
        body.append(
            f"<tr><td>{i}</td><td><b>{escape(c['symbol'])}</b></td><td>{b['drop_pct']:.2f}</td>"
            f"<td>{b['wick_pct']*100:.1f}</td><td>{(b['atr_mult'] or 0):.2f}</td>"
            f"<td>{b['break_depth_pct']:.2f}</td><td>{'yes' if b['broke_swing_low'] else 'no'}</td>"
            f"<td>{(b['vol_burst'] or 0)*100:.0f}%</td><td>{c['levels']['range_low']:,.2f}</td></tr>"
        )
    return f'<div class="scroll"><table class="full"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


ARCHIVE_INDEX = DOCS / "archive.json"


def _update_archive(day: date, confirmed: list[dict], stalk_n: int) -> dict:
    """
    Maintain docs/archive.json so the archive survives cache pruning — the
    per-session JSON only sticks around for 30 days, the index forever.
    """
    idx = {}
    if ARCHIVE_INDEX.exists():
        try:
            idx = json.loads(ARCHIVE_INDEX.read_text())
        except Exception:
            idx = {}
    idx[day.isoformat()] = {
        "confirmed": len(confirmed),
        "stalked": stalk_n,
        "best_rr": confirmed[0]["trade"]["rr"] if confirmed else None,
        "top": [r["symbol"] for r in confirmed[:5]],
    }
    DOCS.mkdir(parents=True, exist_ok=True)
    ARCHIVE_INDEX.write_text(json.dumps(idx, indent=1, sort_keys=True))
    return idx


def _archive_links(idx: dict) -> str:
    if not idx:
        return '<p class="note">No archived sessions yet.</p>'
    out = []
    for d in sorted(idx, reverse=True)[:250]:
        e = idx[d] or {}
        bits = [f'{e.get("confirmed", 0)} confirmed']
        if e.get("best_rr"):
            bits.append(f'best {e["best_rr"]:.2f}R')
        if e.get("top"):
            bits.append(" ".join(e["top"][:4]))
        out.append(
            f'<a href="sessions/{d}.html"><b>{escape(d)}</b>'
            f'<span>{escape(" · ".join(bits))}</span></a>'
        )
    return f'<div class="arch">{"".join(out)}</div>'


PLAYBOOK = """
<h2 class="sec">The setup</h2>
<p class="note">Long only — cash account, no shorting, no options.</p>
<table class="full">
<tr><td><b>08:45 CT · The stalk</b></td><td>First 15-minute candle (09:30–09:45 ET) closes. Keep every liquid US stock whose candle is <b>red</b> and whose <b>low broke under the previous day's range low</b>. The shorter the lower wick the better — that wick is the stop.</td></tr>
<tr><td><b>09:00 CT · The strike</b></td><td>Second candle (09:45–10:00 ET) closes. Keep only names where it is <b>green</b> and its <b>low never went below the red candle's low</b>. That is the sneaky candle: the drop hit resistance.</td></tr>
<tr><td><b>Entry</b></td><td>Close of the green candle.</td></tr>
<tr><td><b>Stop</b></td><td>Low of the initial red candle. Always.</td></tr>
<tr><td><b>Target</b></td><td>If the red candle broke below the previous day <b>swing low</b> → target is the previous day <b>range low</b>. If it broke the range low but held above the swing low → target is the previous day <b>range high</b>.</td></tr>
<tr><td><b>Ranking</b></td><td>Sorted by risk/reward, best first. Setups whose stop lands inside the spread (&lt;0.5% or &lt;8% of the red candle's range) are held back as <i>hair-trigger</i> — the ratio is arithmetically true but not executable.</td></tr>
<tr><td><b>News check</b></td><td>Each candidate's last 48h of headlines is pulled and triaged. A dilutive offering, a guidance cut, a failed trial or a fraud probe means the bounce is a red herring, whatever the candle says.</td></tr>
</table>
<h2 class="sec">Level definitions</h2>
<table class="full">
<tr><td><b>Range high / low</b></td><td>Previous completed session's daily high and low.</td></tr>
<tr><td><b>Swing low</b></td><td>Nearest fractal pivot low <i>below</i> the range low, searched over the last 60 sessions. The first real structural support underneath yesterday's floor.</td></tr>
<tr><td><b>Universe</b></td><td>All US-listed common stock from the Nasdaq Trader directory (ETFs, warrants, units, rights and preferreds excluded), filtered to price ≥ $3 and 20-day average dollar volume ≥ $5M.</td></tr>
</table>
"""


def build(day: date | None = None) -> Path:
    day = day or yahoo.now_et().date()
    strike = _load("strike", day)
    stalk = _load("stalk", day)
    newsd = (_load("news", day) or {}).get("tickers", {}) or {}
    ratings = load_ratings(day)

    passed = (strike or {}).get("confirmed", []) or []
    stalk_c = (stalk or {}).get("candidates", []) or []

    # Final gate: the news read must come back clear. `caution`, `flagged` and
    # anything unrated are held back — a chart that looks perfect on a name with
    # a live catalyst is the red herring this whole step exists to catch.
    def _rating(sym: str) -> str:
        r = (ratings.get(sym) or {}).get("rating")
        if r:
            return str(r).lower()
        return str((newsd.get(sym, {}) or {}).get("preflag") or "unrated").lower()

    confirmed = [r for r in passed if _rating(r["symbol"]) in CLEAR_RATINGS]
    held_back = [r for r in passed if _rating(r["symbol"]) not in CLEAR_RATINGS]

    archive_idx = _update_archive(day, confirmed, len(stalk_c))
    qt, qa = quote_for(day)
    rating_meta = _load("newsrating", day) or {}
    session_note = rating_meta.get("session_note") or ""
    best = confirmed[0]["trade"]["rr"] if confirmed else None
    gen = (strike or stalk or {}).get("generated_at", "—")

    # stage freshness
    pills = [f'<span class="pill">session <b>{day.isoformat()}</b></span>']
    pills.append(
        f'<span class="pill {"live" if stalk else "stale"}">08:45 stalk '
        f'<b>{len(stalk_c)}</b></span>'
    )
    pills.append(
        f'<span class="pill {"live" if strike else "stale"}">09:00 strike '
        f'<b>{len(confirmed)}</b></span>'
    )
    if strike:
        pills.append(f'<span class="pill">scan <b>{strike["stalk_meta"]["scanned"]:,}</b> names</span>')
    pills.append(f'<span class="pill">built <b>{escape(str(gen))}</b></span>')

    stats = [
        ("Qualifying setups", f"{len(confirmed)}", "passed all four gates"),
        ("Best risk/reward", f"{best:.2f}R" if best else "—", "top of the strike list"),
        ("Stalked at 08:45", f"{len(stalk_c)}", "red break under range low"),
        ("Universe scanned", f'{(strike or stalk or {}).get("stalk_meta", {}).get("scanned", (stalk or {}).get("scanned", 0)):,}', "liquid US common stock"),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
        f'<div class="n">{escape(n)}</div></div>'
        for k, v, n in stats
    )

    criteria = (
        '<p class="note">Every row below cleared all four gates: green sneaky candle '
        'holding above the red candle\u2019s low, RSI(14) tracing a V across the two '
        'candles, target on the previous day\u2019s <b>range high</b>, and a <b>clear</b> '
        'news read. Ranked by risk/reward, best first.</p>'
    )

    if confirmed:
        cards = "".join(_card(i, r, newsd, ratings) for i, r in enumerate(confirmed[:TOP_CARDS], 1))
        more = (
            f'<h2 class="sec">All {len(confirmed)} qualifying setups</h2>'
            f"{_table(confirmed, newsd, ratings)}"
        ) if len(confirmed) > TOP_CARDS else _table(confirmed, newsd, ratings)
        strike_body = criteria + cards + more
    else:
        strike_body = criteria + (
            '<div class="empty">Nothing cleared every gate this session.<br>'
            "Nothing to trade is a position.</div>"
        )

    if held_back:
        by = {}
        for r in held_back:
            by[_rating(r["symbol"])] = by.get(_rating(r["symbol"]), 0) + 1
        detail = ", ".join(f"{v} {k}" for k, v in sorted(by.items(), key=lambda kv: -kv[1]))
        strike_body += (
            f'<h2 class="sec">Held back by the news gate — {len(held_back)}</h2>'
            f'<p class="note">Chart and RSI qualified; the news read did not come back '
            f'clear ({escape(detail)}). Listed for the record, not for trading.</p>'
            f"{_table(held_back, newsd, ratings)}"
        )

    funnel_rows = []
    if strike:
        rej = strike.get("rejected", {})
        funnel_rows = [
            ("Universe scanned", strike["stalk_meta"]["scanned"]),
            ("Trading under prev range low", strike["stalk_meta"]["narrowed"]),
            ("Red break confirmed (08:45)", strike["from_stalk"]),
            ("Green sneaky candle (09:00)", strike["from_stalk"] - rej.get("not_green", 0)
             - rej.get("undercut_red_low", 0) - rej.get("doji", 0) - rej.get("no_bar2", 0)),
            ("RSI V-trough", None),
            ("Target = prev range high", None),
            ("News clear", len(confirmed)),
        ]
        funnel_rows[4] = ("RSI V-trough", funnel_rows[3][1] - rej.get("rsi_no_trough", 0))
        funnel_rows[5] = ("Target = prev range high",
                          funnel_rows[4][1] - rej.get("target_is_range_low", 0))
        funnel_rows = [(k, v) for k, v in funnel_rows if v is not None]

    funnel_html = ""
    if funnel_rows:
        funnel_html = (
            '<div class="scroll"><table class="full"><thead><tr><th>Stage</th>'
            "<th>Remaining</th></tr></thead><tbody>"
            + "".join(
                f"<tr><td>{escape(k)}</td><td>{v:,}</td></tr>" for k, v in funnel_rows
            )
            + "</tbody></table></div>"
        )

    intel = (
        '<h2 class="sec">How the market narrowed</h2>'
        + (funnel_html or '<p class="note">Not available.</p>')
        + PLAYBOOK
    )

    stalk_body = (
        f'<p class="note">Everything that broke the previous day range low on a red opening '
        f'candle. This is the 08:45 watch list before the sneaky candle filters it.</p>'
        + (_stalk_table(stalk_c[:150]) if stalk_c else '<div class="empty">No stalk data.</div>')
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>SNEAK · {day.isoformat()}</title>
<meta name="description" content="Sneaky-buy opening range scanner — {len(confirmed)} confirmed setups for {day.isoformat()}">
<style>{CSS}</style>
</head>
<body>
<header class="hero">
  <div class="emblem">{SHURIKEN}</div>
  <h1>Sneak</h1>
  <div class="tag">opening range · sneaky buy protocol</div>
  <div class="sub">08:45 stalk → 09:00 strike · long only · central time</div>
</header>
<div class="strip">{''.join(pills)}</div>
<nav class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-panel="p-strike">09:00 Strike list</button>
  <button class="tab" role="tab" aria-selected="false" data-panel="p-stalk">08:45 Stalk list</button>
  <button class="tab" role="tab" aria-selected="false" data-panel="p-intel">Intel</button>
  <button class="tab" role="tab" aria-selected="false" data-panel="p-arch">Archive</button>
</nav>
<main class="wrap">
  <section id="p-strike" class="panel on" role="tabpanel">
    <blockquote class="quote">{escape(qt)}<span>— {escape(qa)}</span></blockquote>
    <div class="stats">{stat_html}</div>
    {strike_body}
  </section>
  <section id="p-stalk" class="panel" role="tabpanel">{stalk_body}</section>
  <section id="p-intel" class="panel" role="tabpanel">{intel}</section>
  <section id="p-arch" class="panel" role="tabpanel">
    <h2 class="sec">Past sessions</h2>{_archive_links(archive_idx)}
  </section>
</main>
<footer>
  Not investment advice · levels and candles from Yahoo Finance, delayed data possible ·
  built {escape(str(gen))} CT
</footer>
<script>{JS}</script>
</body>
</html>"""

    DOCS.mkdir(parents=True, exist_ok=True)
    SESSIONS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html)
    (SESSIONS / f"{day.isoformat()}.html").write_text(html)
    print(f"[dashboard] wrote docs/index.html and docs/sessions/{day.isoformat()}.html "
          f"({len(html)//1024} KB)", flush=True)
    return DOCS / "index.html"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the SNEAK dashboard")
    ap.add_argument("--date", type=str, default=None)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else None
    build(day)
    return 0


if __name__ == "__main__":
    sys.exit(main())
