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
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

from . import yahoo
from .confirm import ENTRY_WINDOW_ET, rank_key
from .levels import HEADROOM_MAX, headroom_pct
from .news import load_ratings
from .prep import CACHE_DIR
from .quotes import quote_for

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SESSIONS = DOCS / "sessions"


# Ratings that survive the final gate.
#
# `quiet` (no headlines in 48h) and `clear` (headlines, but generic — nothing
# that explains the drop) publish. `caution` and `flagged` mean the drop has a
# company-specific reason, and those are held back. This used to be `clear`
# only, which excluded the no-news names — and over 31 live sessions the
# no-news names were the ones that bounced: 60% win vs 49% for names with
# headlines (candle-3 entry), session bootstrap P = 0.95. A drop with a reason
# tends to keep going; a drop without one tends to come back.
PUBLISH_RATINGS = {"quiet", "clear"}
V1_PUBLISH_RATINGS = {"clear"}          # sessions scanned before 2026-10-10

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
.banner{margin:0 0 1.2rem;padding:.8rem 1rem;border:1px solid var(--warn);border-radius:6px;
  background:rgba(196,135,10,.08);color:var(--ink);font-size:.82rem}
.banner b{color:var(--warn)}
.tag-tight{color:var(--warn);font-size:.68rem;margin-left:.3rem}
.why{color:var(--dim);font-size:.66rem;line-height:1.35;max-width:22ch;white-space:normal}

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

details.howto{margin:0 0 1.2rem;border:1px solid var(--border2);border-radius:6px;padding:.6rem .8rem;background:var(--s1)}
details.howto summary{cursor:pointer;color:var(--phos);font-size:.78rem;letter-spacing:.08em;text-transform:uppercase}
details.howto table.kv{margin-top:.6rem}
details.howto table.kv td:last-child{text-align:left;font-weight:400;color:var(--muted)}

table.kv{width:100%;border-collapse:collapse;font-size:.78rem}
table.kv td{padding:.3rem .4rem;border-bottom:1px solid var(--border)}
table.kv td:first-child{color:var(--dim);white-space:nowrap}
table.kv td:last-child{text-align:right;color:var(--ink);font-weight:600}

table.full{width:100%;border-collapse:collapse;font-size:.75rem;margin-top:.6rem}
table.full th{text-align:left;color:var(--dim);font-weight:600;font-size:.63rem;text-transform:uppercase;
  letter-spacing:.1em;padding:.4rem;border-bottom:1px solid var(--border2)}
table.full td{padding:.38rem .4rem;border-bottom:1px solid var(--border);color:var(--ink)}
table.full tr:hover td{background:var(--s2)}
.scroll{overflow-x:auto}

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


def _ct(h: int, m: int) -> str:
    """ET wall-clock to CT (always one hour behind, both sides of DST)."""
    return f"{h - 1:02d}:{m:02d}"


WINDOW_CT = f"{_ct(*ENTRY_WINDOW_ET[0])}–{_ct(*ENTRY_WINDOW_ET[1])} CT"


def _headroom(row: dict) -> float | None:
    """Headroom for a row, recomputed if the session predates the stored field."""
    t = row["trade"]
    h = t.get("headroom_pct")
    if h is not None:
        return h
    high = t.get("target_full") or (row.get("levels") or {}).get("range_high")
    return headroom_pct(t["entry"], high) if high else None


def _hd(row: dict) -> str:
    h = _headroom(row)
    return f"{h:.2f}%" if h is not None else "&mdash;"


def _money(x) -> str:
    return f"{x:,.2f}" if isinstance(x, (int, float)) else "&mdash;"


def _table(rows: list[dict], news: dict, ratings: dict, rating_of) -> str:
    head = (
        "<tr><th>#</th><th>Symbol</th><th>Momentum</th><th>Buy stop</th><th>Stop</th>"
        "<th>Target</th><th>Risk %</th><th>Reward %</th><th>R:R</th><th>Headroom</th>"
        "<th>RSI after green</th><th>News</th></tr>"
    )
    body = []
    for i, r in enumerate(rows, 1):
        t = r["trade"]
        rsi = t.get("rsi") or {}
        sym = r["symbol"]
        reason = (ratings.get(sym) or {}).get("reason") or ""
        tight = '<span class="tag-tight">tight stop</span>' if t.get("tight_stop") else ""
        rr = t.get("rr")
        rr_cell = f"{rr:.2f}" if rr is not None else "&mdash;"
        body.append(
            f"<tr><td>{i}</td><td><b>{escape(sym)}</b></td>"
            f"<td><b>{(r.get('momentum') or 0):.0f}</b></td>"
            f"<td><b>{_money(t.get('trigger', t.get('entry')))}</b></td>"
            f"<td>{_money(t.get('stop'))}</td><td>{_money(t.get('target'))}</td>"
            f"<td>{(t.get('risk_pct') or 0):.2f}%{tight}</td>"
            f"<td>+{(t.get('reward_pct') or 0):.2f}%</td>"
            f"<td>{rr_cell}</td>"
            f"<td>{_hd(r)}</td><td>{rsi.get('after_green', '—')}</td>"
            f'<td>{escape(rating_of(sym))}'
            + (f'<div class="why">{escape(reason)}</div>' if reason else "")
            + "</td></tr>"
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


HOWTO = f"""
<details class="howto"><summary>How to trade a row &mdash; the candle-3 order</summary>
<table class="kv">
<tr><td><b>Order</b></td><td>A <b>buy-stop</b> at the Buy stop price &mdash; one cent above the
high of the 09:45&ndash;10:00 ET green candle. It fills only if price breaks the sneaky
candle&rsquo;s high during candle 3.</td></tr>
<tr><td><b>Window</b></td><td><b>{WINDOW_CT}</b> (10:00&ndash;10:15 ET). Cancel anything still
unfilled at 09:15 CT. Cancel it early if price trades below the Stop before it fills &mdash;
the setup is broken.</td></tr>
<tr><td><b>Stop</b></td><td>Low of the 09:30 red candle. Never moves. Attach it as soon as
the buy-stop fills.</td></tr>
<tr><td><b>Target</b></td><td>The projected move: the median excursion this much headroom
has produced, about a third of the way to yesterday&rsquo;s range high. A limit sell there.</td></tr>
<tr><td><b>Exit</b></td><td>Flat by the close if neither the stop nor the target is hit.</td></tr>
<tr><td><b>Momentum</b></td><td>0&ndash;100 percentile within today&rsquo;s list; the list is
sorted by it. It ranks <i>probability</i>, not profit &mdash; use it to choose between rows.</td></tr>
</table>
<p class="note">In the 56-session backtest (5-minute bars, 0.05% round-trip cost) these rules
won 69% of filled trades &mdash; 65.8% on the 30 sessions after the rules were chosen,
against 52.7% for the old rules &mdash; and averaged +0.13R per trade on those sessions. That
is about 1.5 orders a day, and the confidence interval on the +0.13R still spans zero:
a better list, not a proven edge. Size accordingly. Long only, cash account. Not
investment advice.</p>
</details>
"""


ARCHIVE_INDEX = DOCS / "archive.json"


def _update_archive(day: date, confirmed: list[dict], stalk_n: int, version: int) -> dict:
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
        "rules": f"v{version}",
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
        bits = [f'{e.get("confirmed", 0)} published']
        if e.get("rules"):
            bits.append(f'rules {e["rules"]}')
        if e.get("top"):
            bits.append(" ".join(e["top"][:4]))
        out.append(
            f'<a href="sessions/{d}.html"><b>{escape(d)}</b>'
            f'<span>{escape(" · ".join(bits))}</span></a>'
        )
    return f'<div class="arch">{"".join(out)}</div>'


PLAYBOOK = f"""
<h2 class="sec">The setup</h2>
<p class="note">Long only — cash account, no shorting, no options.</p>
<table class="full">
<tr><td><b>08:45 CT · The stalk</b></td><td>First 15-minute candle (09:30–09:45 ET) closes. Keep every liquid US stock whose candle is <b>red</b>, whose <b>low broke under the previous day's range low</b>, and whose range is at least <b>0.75× its 14-day ATR</b> — a dramatic break, not a drift.</td></tr>
<tr><td><b>09:00 CT · The strike</b></td><td>Second candle (09:45–10:00 ET) closes. Keep the names where it is <b>green</b> (body ≥ 5% of its range), its <b>low never went below the red candle's low</b>, <b>RSI(14) after it is ≥ 40</b>, the red candle <b>held the swing low</b>, and the headroom to yesterday's range high is <b>above 0 and under {HEADROOM_MAX:g}%</b>, and the projected reward is at least <b>0.35× the risk</b>.</td></tr>
<tr><td><b>Entry · candle 3</b></td><td>Buy-stop one cent above the green candle's high, live {WINDOW_CT} only.</td></tr>
<tr><td><b>Stop</b></td><td>Low of the initial red candle. Always.</td></tr>
<tr><td><b>Target</b></td><td>Buy-stop price plus the projected move for its headroom (median excursion, fitted). Flat by the close otherwise.</td></tr>
<tr><td><b>Ranking</b></td><td>Momentum score, a 0–100 percentile within the day's list. Shallower breaks of the range low break ties. Stops under 0.5% from entry are tagged <i>tight stop</i>, not removed.</td></tr>
<tr><td><b>News check</b></td><td>The last 48h of headlines are read by model. <b>Published:</b> <i>quiet</i> (no headlines) and <i>clear</i> (generic headlines that explain nothing). <b>Held back:</b> <i>caution</i> (a company-specific event — earnings, downgrade, deal, litigation) and <i>flagged</i> (offering, guidance cut, failed trial, fraud probe, going concern). Drops with a reason tend to keep going.</td></tr>
</table>
<h2 class="sec">Level definitions</h2>
<table class="full">
<tr><td><b>Range high / low</b></td><td>Previous completed session's daily high and low.</td></tr>
<tr><td><b>Swing low</b></td><td>Nearest fractal pivot low <i>below</i> the range low, searched over the last 60 sessions. The first real structural support underneath yesterday's floor.</td></tr>
<tr><td><b>Headroom</b></td><td>Distance from the buy-stop price up to yesterday's range high, as a percent of the price.</td></tr>
<tr><td><b>Universe</b></td><td>All US-listed common stock from the Nasdaq Trader directory (ETFs, warrants, units, rights and preferreds excluded), filtered to price ≥ $3 and 20-day average dollar volume ≥ $5M.</td></tr>
</table>
"""


def _latest_session_with_data(before_or_on: date) -> date | None:
    """Most recent session that actually has a stalk file on disk."""
    days = []
    for p in CACHE_DIR.glob("stalk-*.json"):
        try:
            d = date.fromisoformat(p.stem.split("stalk-", 1)[1])
        except Exception:
            continue
        if d <= before_or_on:
            days.append(d)
    return max(days) if days else None


def build(day: date | None = None, explicit: bool = False) -> Path:
    day = day or yahoo.now_et().date()
    strike = _load("strike", day)
    stalk = _load("stalk", day)

    # Nothing scanned for `day` yet — pre-open, a weekend, or a holiday. Fall
    # back to the last session that has data instead of publishing a blank page
    # over a good one.
    if not strike and not stalk and not explicit:
        prior = _latest_session_with_data(day)
        if prior and prior != day:
            print(f"[dashboard] no data for {day}; showing last session {prior}", flush=True)
            day = prior
            strike = _load("strike", day)
            stalk = _load("stalk", day)
    newsd = (_load("news", day) or {}).get("tickers", {}) or {}
    ratings = load_ratings(day)
    version = int((strike or {}).get("version") or 1)

    passed = (strike or {}).get("confirmed", []) or []
    stalk_c = (stalk or {}).get("candidates", []) or []

    # Final gate. A model rating wins; without one, fall back to the keyword
    # pre-flag — where only "no headlines at all" can be trusted as quiet, and
    # anything with unread headlines stays held back.
    def _rating(sym: str) -> str:
        r = (ratings.get(sym) or {}).get("rating")
        if r:
            return str(r).lower()
        pre = (newsd.get(sym, {}) or {}).get("preflag")
        if pre == "quiet":
            return "quiet"
        if pre == "red":
            return "flagged"
        return "caution" if pre else "unrated"

    # A session is always rendered under the rules it was scanned with, so a
    # rebuild of an old date reproduces what was published that morning and
    # leaves its archive entry alone.
    publish = PUBLISH_RATINGS if version >= 2 else V1_PUBLISH_RATINGS
    confirmed = [r for r in passed if _rating(r["symbol"]) in publish]
    held_back = [r for r in passed if _rating(r["symbol"]) not in publish]
    confirmed = sorted(confirmed, key=rank_key)
    held_back = sorted(held_back, key=rank_key)

    archive_idx = _update_archive(day, confirmed, len(stalk_c), version)
    qt, qa = quote_for(day)
    rating_meta = _load("newsrating", day) or {}
    session_note = rating_meta.get("session_note") or ""
    gen = (strike or stalk or {}).get("generated_at", "—")
    try:
        gen = datetime.fromisoformat(gen).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    coverage = (stalk or {}).get("coverage")

    # stage freshness
    pills = [f'<span class="pill">session <b>{day.isoformat()}</b></span>']
    pills.append(
        f'<span class="pill {"live" if stalk else "stale"}">08:45 stalk '
        f'<b>{len(stalk_c)}</b></span>'
    )
    pills.append(
        f'<span class="pill {"live" if strike else "stale"}">09:00 orders '
        f'<b>{len(confirmed)}</b></span>'
    )
    if strike:
        pills.append(f'<span class="pill">scan <b>{(strike.get("stalk_meta") or {}).get("scanned") or 0:,}</b> names</span>')
    if coverage is not None and coverage < 0.95:
        pills.append(f'<span class="pill stale">partial data <b>{coverage:.0%}</b></span>')
    pills.append(f'<span class="pill">built <b>{escape(str(gen))}</b></span>')

    stats = [
        ("Orders today" if version >= 2 else "Published", f"{len(confirmed)}", "passed every gate"),
        ("Entry window", WINDOW_CT, "buy-stop, then cancel") if version >= 2
        else ("Entry", "green close", "old rules"),
        ("Stalked at 08:45", f"{len(stalk_c)}", "red break under range low"),
        ("Universe scanned", f'{((strike or {}).get("stalk_meta") or {}).get("scanned") or (stalk or {}).get("scanned") or 0:,}', "liquid US common stock"),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
        f'<div class="n">{escape(n)}</div></div>'
        for k, v, n in stats
    )

    banners = []
    if strike and strike.get("published_after_window"):
        banners.append(
            f'<div class="banner"><b>Published after the entry window.</b> This list was built '
            f'at {escape(str(gen))}, after the {WINDOW_CT} buy-stop window closed, so today&rsquo;s '
            f'orders are void. Listed for the record only.</div>'
        )
    if coverage is not None and coverage < 0.95:
        banners.append(
            f'<div class="banner"><b>Partial data.</b> Yahoo answered for {coverage:.0%} of the '
            f'universe this morning, so some qualifying names may be missing.</div>'
        )
    if version >= 2:
        criteria = (
            '<p class="note">Every row cleared all the gates: a dramatic red break of yesterday&rsquo;s '
            'low, a green sneaky candle holding above it, RSI(14) after it at 40 or better, the swing '
            f'low intact, headroom under {HEADROOM_MAX:g}%, reward at least 0.35× the risk, and no '
            'company-specific news behind the drop. '
            '<b>Ranked by momentum.</b> Each row is a buy-stop order for candle 3.</p>'
            + HOWTO
        )
    else:
        banners.append(
            '<div class="banner"><b>Older rules.</b> This session was scanned before 2026-10-10: '
            'entry at the green candle&rsquo;s close (shown in the Buy stop column), an RSI V-trough '
            'instead of the RSI floor, no reward/risk floor, and only <i>clear</i> news published. '
            'It lists the names published that morning, re-ranked by momentum.</div>'
        )
        criteria = ""
    if session_note:
        criteria += f'<p class="note"><b>News desk:</b> {escape(session_note)}</p>'

    if confirmed:
        strike_body = "".join(banners) + criteria + _table(confirmed, newsd, ratings, _rating)
    else:
        strike_body = "".join(banners) + criteria + (
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
            f'<p class="note">The chart qualified, but the drop came with company-specific news '
            f'({escape(detail)}). The reason sits under each rating. Listed for the record, not for trading.</p>'
            f"{_table(held_back, newsd, ratings, _rating)}"
        )

    funnel_rows = []
    if strike:
        rej = strike.get("rejected", {})
        meta = strike.get("stalk_meta") or {}
        n = strike.get("from_stalk", 0)
        funnel_rows = [
            ("Universe scanned", meta.get("scanned")),
            ("Close within reach of prev range low", meta.get("narrowed")),
            ("Red break confirmed (08:45)", n),
        ]
        n -= sum(rej.get(k, 0) for k in ("not_green", "undercut_red_low", "doji", "no_bar2"))
        funnel_rows.append(("Green sneaky candle (09:00)", n))
        if version >= 2:
            n -= rej.get("rsi_below_floor", 0)
            funnel_rows.append(("RSI(14) after green ≥ 40", n))
            n -= rej.get("target_is_range_low", 0)
            funnel_rows.append(("Swing low held", n))
            n -= rej.get("headroom_out_of_range", 0)
            funnel_rows.append((f"Headroom 0–{HEADROOM_MAX:g}%", n))
            n -= rej.get("payoff_too_small", 0)
            funnel_rows.append(("Reward/risk ≥ 0.35", n))
        else:
            n -= rej.get("rsi_no_trough", 0)
            funnel_rows.append(("RSI V-trough (old rule)", n))
            n -= rej.get("target_is_range_low", 0)
            funnel_rows.append(("Swing low held", n))
        funnel_rows.append(("News quiet or clear" if version >= 2 else "News clear", len(confirmed)))
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
        f'<p class="note">Everything that broke the previous day range low on a dramatic red opening '
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
<meta name="description" content="Sneaky-buy opening range scanner — {len(confirmed)} candle-3 orders for {day.isoformat()}">
<style>{CSS}</style>
</head>
<body>
<header class="hero">
  <div class="emblem">{SHURIKEN}</div>
  <h1>Sneak</h1>
  <div class="tag">opening range · sneaky buy protocol</div>
  <div class="sub">08:45 stalk → 09:00 orders → 09:15 window closes · long only · central time</div>
</header>
<div class="strip">{''.join(pills)}</div>
<nav class="tabs" role="tablist">
  <button class="tab" role="tab" aria-selected="true" data-panel="p-strike">09:00 Orders</button>
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
    build(day, explicit=bool(a.date))
    return 0


if __name__ == "__main__":
    sys.exit(main())
