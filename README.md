# 🥷 SNEAK — opening range sneaky-buy scanner

**[📊 Live dashboard](https://arrakistacos.github.io/morning-brief/)**

Two lists, every trading morning, on the dot:

| Time (CT) | Stage | What lands on the dashboard |
|---|---|---|
| **08:45** | **Stalk** | Every liquid US stock whose first 15-minute candle is a dramatic **red break below the previous day's range low**. |
| **09:00** | **Strike** | The subset where the second candle came back **green without undercutting the red candle's low** — the sneaky candle — ranked by risk/reward, with a news red-herring rating. |

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
- **R:R** — `(target − entry) / (entry − stop)`, sorted best first

### Level definitions

| Term | Meaning |
|---|---|
| Range high / low | Previous completed session's daily high / low |
| Swing low | Nearest fractal pivot low *below* the range low, over the last 60 sessions — the first real structural support beneath yesterday's floor |
| Universe | All US-listed common stock from the Nasdaq Trader directory (no ETFs, warrants, units, rights, preferreds), price ≥ $3, 20-day average dollar volume ≥ $5M — about 2,800 names |

### Hair-trigger bucket

A green candle closing a penny above the red candle's low is arithmetically 20:1 and practically untradable — the stop sits inside the spread. Those are separated out rather than allowed to top the list. Floors: stop ≥ 0.5% below entry, ≥ $0.05, and ≥ 8% of the red candle's own range.

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
  charts.py      inline SVG — candles, ladders, funnel, histogram
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
python -m sneak.news --top 30 && python -m sneak.triage --top 12
python -m sneak.dashboard
```

Replay a past session with `--date YYYY-MM-DD` (intraday history is available for roughly 60 days).

## Dashboard notes

Single self-contained HTML file — no CDN, no JS charting library, every graphic is server-rendered inline SVG, so it opens instantly on a phone. Palette is validated for colour-vision deficiency against the dark surface; bull/bear additionally carry shape encoding (bear filled, bull hollow) so direction never depends on colour alone. Every card view has an equivalent table view.

---

*Not investment advice. Levels and candles come from Yahoo Finance and may be delayed.*
