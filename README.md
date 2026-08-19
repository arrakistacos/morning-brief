# 🥷 SNEAK — opening range sneaky-buy scanner

**[📊 Live dashboard](https://arrakistacos.github.io/morning-brief/)**

Two lists, every trading morning, on the dot:

| Time (CT) | Stage | What lands on the dashboard |
|---|---|---|
| **08:45** | **Stalk** | Every liquid US stock whose first 15-minute candle is a dramatic **red break below the previous day's range low**. |
| **09:00** | **Strike** | The subset that clears **all four gates** — green sneaky candle, RSI V-trough, range-high target, clear news — ranked by risk/reward. |

Long only. Cash account, no shorting.

## The setup

```
        prev day range high ──────────────  ← target if only the range low broke
        prev day range low  ──────────────  ← target if the swing low ALSO broke
   ┃                                          and the level that must be broken
   ┃ ▼ 09:30  the dramatic red candle
   ┃    low  ─────────────────────────────  ← STOP. always. short wick = tight stop
        ▲ 09:45  the sneaky green candle
             close ────────────────────────  ← ENTRY
        prev day swing low ───────────────
```

- **Entry** — close of the green sneaky candle
- **Stop** — low of the initial red candle (that wick *is* the stop, so a short wick ranks higher)
- **Target** — previous day **range low** if the red candle broke below the previous day **swing low**; otherwise the previous day **range high**
- **R:R** — `(target − entry) / (entry − stop)`

### Ranking: the momentum score

The list is **ranked by momentum score, not by R:R**. Ranking by R:R put the tightest, least executable stops at the top — a stop a penny under entry reads as 20:1 and is untradable.

The score is a 0–100 percentile within the day's own candidates, built from five scale-free measures of how much damage the opening drop did and how convincingly it recovered: RSI(7) and RSI(14) after the green candle (higher better), how far RSI fell across the red candle, the red candle's body fraction, and its size relative to ATR (all lower better).

Backtested over 9,092 setups and 58 sessions, it sorts win rate monotonically across all ten deciles:

| decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| win rate | 33.9% | 38.5% | 43.2% | 48.7% | 49.8% | 52.1% | 58.8% | 63.4% | 67.9% | 73.4% |

Within-day rank correlation against realised R reaches t = +3.92, clearing a Bonferroni threshold of 3.9 across the 35 indicators tested, and is positive on 67% of sessions.

**It ranks probability, not profit.** Mean R per decile stays flat near zero — a higher hit rate comes with a proportionally smaller payoff. Use it to choose between setups on a given morning, never as evidence that a setup is profitable on its own.

### Two targets

| | level | reached | use |
|---|---|---|---|
| **Target A** | previous day's close | ~47% same day | if you are flat by 16:00 |
| **Target B** | previous day's range high | ~13% same day | hold up to 3 trading days |

Target A is blank when the entry is already above the previous close, which is common for the highest-momentum names.

**The 3-day plan.** Entry = green candle close. Stop = red candle low, unmoved. Target = previous day's range high. Hold up to three trading days and exit at the close of day 3 if neither level is touched. This was the only configuration in 58 sessions with positive expectancy (+0.105R, +0.74% per trade, with a 0.5% risk floor and a 10R cap). It is **not statistically significant** — t = 1.61, and ~91 sessions would be needed for t > 2. Size it as an experiment.

### The four gates

A name is published only if every one holds:

1. **Sneaky candle** — candle 2 is green and its low never undercuts candle 1's low.
2. **RSI V-trough** — RSI(14) on the 15-minute series falls across the red candle and rises across the green one. Momentum rolling over and immediately recovering is what separates real resistance from a pause on the way lower.
3. **Target is the range high** — the red candle broke the range low but held above the swing low, so structure is intact. Setups that broke the swing low (target = range low) are filtered out.
4. **News is clear** — the red-herring read comes back `clear`, meaning headlines were found, read, and judged harmless. Everything else is held back and listed separately.

| Rating | Meaning | Published |
|---|---|---|
| `clear` | Headlines read, nothing material against the trade | ✅ |
| `caution` | Earnings, downgrade, litigation or similar in the last 48h | ❌ |
| `flagged` | Offering, guidance cut, failed trial, fraud probe, going concern | ❌ |
| `quiet` | **No headlines found at all** | ❌ |

`quiet` is deliberately not `clear`. No coverage is the absence of evidence, not evidence of absence — nothing was checked because there was nothing to check. Tickers with no headlines are pinned at `quiet` and never sent to a model, since a model asked to rate an empty list will invent reassurance. This is a real filter: on a typical session more than half the qualifying setups are small caps with no news coverage at all, and they do not get published.

### Level definitions

| Term | Meaning |
|---|---|
| Range high / low | Previous completed session's daily high / low |
| Swing low | Nearest fractal pivot low *below* the range low, over the last 60 sessions — the first real structural support beneath yesterday's floor |
| Universe | All US-listed common stock from the Nasdaq Trader directory (no ETFs, warrants, units, rights, preferreds), price ≥ $3, 20-day average dollar volume ≥ $5M — about 2,800 names |

### Tight stops

A green candle closing a penny above the red candle's low is arithmetically 20:1 and practically untradable — the stop sits inside the spread. These are no longer held back; they rank on their R:R like anything else, but any row with a stop under 0.5% from entry is tagged **tight stop — inside the spread** so it is visible at a glance.

## How it runs

Everything is a GitHub Actions cron in `.github/workflows/sneak.yml`. Nothing depends on a local machine being awake.

```
prep    ~08:00 ET   universe refresh + previous-day levels for ~2,800 names   (~30s)
stalk   ~09:20 ET   sleeps until 09:45:25 ET, then scans the tape            (~10s)
strike  ~09:50 ET   sleeps until 10:00:25 ET, confirms, rates news, publishes (~15s)
```

**Timing.** GitHub's cron is UTC-only and drifts under load, so each stage is scheduled twice — once for CDT, once for CST — starting ~25 minutes early. A guard step reads the ET wall clock and exits whichever firing is wrong for the current offset; the scanner then *sleeps* until the exact second the candle closes. Drift costs idle runner time, never a late list. DST needs no maintenance.

**Speed.** Scanning ~2,800 names for one 15-minute candle in under a minute uses two passes: Yahoo's `spark` endpoint (20 symbols per call, ~140 calls, ~15s) gets every first-bar close and narrows to the few hundred trading under their range low; only those get a full OHLCV `chart` call. Measured ~25 req/s at 24 workers.

## Model usage

Deliberately lopsided — the model is spent only where it changes a decision.

| Step | Engine | Why |
|---|---|---|
| Universe, levels, candle classification, targets, R:R | **Plain Python** | Deterministic arithmetic. A model here would add cost, latency and error. |
| Per-ticker news triage | **Haiku** | Bulk classification of short headline text, one cheap call per candidate, run in parallel. |
| Final red-herring adjudication | **Opus** | One call over the top candidates, seeing the trade maths and the junior reads together. The judgement that actually gates a trade. |

Needs the `CLAUDE_API_KEY` repo secret. Without it the deterministic keyword flagger still runs (offerings, guidance cuts, failed trials, fraud probes, downgrades) and the dashboard says the ratings are keyword-derived.

Verify the key any time with **Actions → SNEAK → Run workflow → stage: `selftest`**. It exercises both tiers on a throwaway prompt and prints which model answered, so you can confirm the wiring without waiting for a session that has candidates in it. A green tick means both tiers answered; a red X means the key or the model access is wrong, and the log says which. Roughly 2–3¢ per trading day in normal use.

## Layout

```
sneak/
  yahoo.py       Yahoo chart/spark client — browser UA, retry/backoff, thread pool
  levels.py      previous-day range + fractal swing pivots + ATR
  prep.py        universe refresh, level cache, liquidity floor
  scan_open.py   08:45 CT — the stalk
  confirm.py     09:00 CT — the strike, targets and R:R
  news.py        per-ticker headline pull + keyword pre-flags
  triage.py      Haiku fan-out + Opus adjudication
  charts.py      unused — SVG helpers kept from the pre-tables dashboard
  dashboard.py   builds docs/index.html
  quotes.py      stoic line of the day
  market_calendar.py   NYSE calendar incl. holidays and early closes
bin/sneak.sh     one entry point per stage (local runs)
docs/            GitHub Pages output — index.html + sessions/ + archive.json
legacy/          the previous morning-brief system, kept for reference
```

## Running it by hand

```bash
pip install -r requirements.txt
python -m sneak.prep                                  # build today's levels
python -m sneak.scan_open --no-wait                   # stalk (skip the sleep)
python -m sneak.confirm  --no-wait                    # strike
python -m sneak.news --top 200 && python -m sneak.triage --top 200
python -m sneak.dashboard
```

Replay a past session with `--date YYYY-MM-DD` (intraday history is available for roughly 60 days).

## Dashboard notes

Single self-contained HTML file — no CDN, no JS, no charts. Numbers are presented as cards and tables only. It opens instantly on a phone and every value is selectable text.

---

*Not investment advice. Levels and candles come from Yahoo Finance and may be delayed.*
