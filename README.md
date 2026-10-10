# 🥷 SNEAK — opening range sneaky-buy scanner

**[📊 Live dashboard](https://arrakistacos.github.io/morning-brief/)**

One click, every trading morning — **Actions → SNEAK → [Run workflow](https://github.com/arrakistacos/morning-brief/actions/workflows/sneak.yml) → `all` at ~08:55 CT** — and two lists land together at ~09:01 CT:

| Candle (CT) | Stage | What lands on the dashboard |
|---|---|---|
| **08:30–08:45** | **Stalk** | Every liquid US stock whose first 15-minute candle is a **dramatic red break below the previous day's range low** — the candle must span at least **0.75× ATR14**. |
| **08:45–09:00** | **Orders** | The subset where the second candle is a **sneaky candle** and every gate holds, each turned into a **buy-stop order for candle 3**, ranked by momentum. |
| **09:00–09:15** | **Entry window** | Candle 3. Buy-stops are live; cancel anything unfilled at 09:15. |

Long only. Cash account, no shorting.

## The setup

```
        prev day range high ──────────────  ← headroom is measured up to here
                                               (target = projected move toward it)
   ┃
   ┃ ▼ 09:30  candle 1 — the dramatic red candle, breaks the range low
        prev day range low  ──────────────
   ┃    low  ─────────────────────────────  ← STOP. always.
        ▲ 09:45  candle 2 — the sneaky green candle
             high ─────────────────────────  ← BUY-STOP one cent above (candle 3)
        prev day swing low ───────────────  ← must NOT be broken by candle 1
```

- **Candle 1 (09:30–09:45 ET)** — the opening range: red, its low breaks yesterday's range low, its range is ≥ 0.75× ATR14
- **Candle 2 (09:45–10:00 ET)** — the sneaky candle: green, holds above candle 1's low
- **Candle 3 (10:00–10:15 ET)** — the entry candle: **buy-stop at the first cent above candle 2's high**, live for this candle only (09:00–09:15 CT). Cancel it if unfilled at the close of candle 3, or if price trades below the stop first.
- **Stop** — the low of candle 1. Never moved.
- **Target** — the buy-stop price plus the **projected move** for its headroom: the median excursion that much headroom has historically produced, about a third of the way to the range high. Flat by the close if neither is hit.
- **R:R** — `(target − buy stop) / (buy stop − stop)`

### The gates

A name becomes an order only if every one holds:

1. **Dramatic red break** — candle 1 is red, its low clears yesterday's range low by a cent (or 2bp), its range ≥ 0.75× ATR14.
2. **Sneaky candle** — candle 2 is green, its body is ≥ 5% of its range, and its low never undercuts candle 1's low.
3. **RSI floor** — RSI(14) on the 15-minute series, read after candle 2, is **≥ 40**.
4. **Structure intact** — candle 1 broke the range low but held above the swing low.
5. **Headroom** — from the buy-stop up to yesterday's range high is **above 0 and under 9%**.
6. **Payoff** — the projected reward is at least **0.35× the risk**.
7. **News** — the headline read comes back `quiet` or `clear` (see below).

Then the list is **ranked by momentum score**; shallower breaks of the range low break ties. Stops under 0.5% from entry are tagged *tight stop*, not removed.

### What the backtest says

56 sessions (2026-07-23 → 10-09), every setup replayed on 5-minute bars with a 0.05% round-trip cost. The rules were chosen on the first 26 sessions and checked on the last 30. A *win* is a trade that closes with R > 0. Full method, every variant tested and the caveats are in [`research/README.md`](research/README.md); re-run it with `python research/backtest.py`.

| | old rules | **v2 rules** |
|---|---|---|
| Entry | candle 2 close | buy-stop above candle 2's high, candle 3 only |
| Win rate, all 56 sessions | 56.0% | **69.0%** |
| Win rate, 30 held-out sessions | 52.7% | **65.8%** (95% CI 45–83%) |
| Mean R, held-out | −0.065 | **+0.130** (95% CI −0.19…+0.40) |
| Orders per day | ~14 | ~1.5 (none on ~30% of days) |

**Read the confidence intervals.** The win-rate improvement is consistent across both halves of the data and across every variant tested. The positive mean R is not yet statistically distinguishable from zero. Treat v2 as a better list, not a proven edge, and size it as an experiment.

### Why each rule is there

- **Candle-3 buy-stop.** About 40% of setups never trigger, and those are disproportionately the ones that roll over. With the same stop and target, the break entry won ~3–6 points more often than the close entry on both halves.
- **RSI(14) ≥ 40 after the green candle** replaced the old RSI *V-trough*. The V added nothing — setups without it won as often as setups with it. The RSI *level* was the strongest single filter, and the win rate climbs with the threshold on the held-out sessions (≥35: 62%, ≥40: 65%, ≥45: 69%), so 40 is a point on a slope, not a lucky cut.
- **Headroom under 9%.** Setups at 9%+ won ~35% in both halves. The old *3–9% band* that used to rank the list did **not** survive: on the held-out sessions in-band setups won 46.5% against 57.3% outside it. It no longer ranks anything.
- **Reward/risk ≥ 0.35.** Without it, half of the qualifying trades risked 4× what they could make — they won often and lost money. The floor (chosen on the training sessions) keeps the win rate where it was and moves mean R from −0.02 to +0.13 on the held-out sessions.
- **Momentum ranks, it does not gate.** Above the day's median it won 69.5% against 65.1% below (held-out, within v2). It ranks *probability*, not profit.

### The news gate

| Rating | Meaning | Published |
|---|---|---|
| `quiet` | No headlines in the last 48h | ✅ |
| `clear` | Headlines, but generic — market wraps, listicles, routine PR; nothing that explains the drop | ✅ |
| `caution` | A company-specific event in the window: earnings, downgrade, deal, litigation, management change | ❌ |
| `flagged` | A structural repricing: offering, guidance cut, failed trial/CRL, fraud probe, going concern | ❌ |

This is the reverse of the old gate, which published `clear` only and treated `quiet` as a risk. The live record says the opposite. Over 31 sessions of live ratings, setups whose drop came with company-specific headlines won ~10 points less often than setups with no headlines at all (60% vs 49% with the candle-3 entry; session bootstrap P ≈ 0.95). A drop with a reason tends to keep going; a drop without one tends to come back. Without a model read, a name with unread headlines stays `caution`.

### Level definitions

| Term | Meaning |
|---|---|
| Range high / low | Previous completed session's daily high / low |
| Swing low | Nearest fractal pivot low *below* the range low, over the last 60 sessions — the first real structural support beneath yesterday's floor |
| Headroom | Distance from the buy-stop price up to the range high, as a percent of the price |
| Universe | All US-listed common stock from the Nasdaq Trader directory (no ETFs, warrants, units, rights, preferreds), price ≥ $3, 20-day average dollar volume ≥ $5M — about 2,800 names |

## How it runs

Everything runs in GitHub Actions via `.github/workflows/sneak.yml`, started by hand. **Actions → SNEAK → [Run workflow](https://github.com/arrakistacos/morning-brief/actions/workflows/sneak.yml) → `all`** at about **08:55 CT**. One job does the whole morning:

```
08:55:00 CT  click — runner up, dependencies installed                 ~25s
08:55:50     prep (universe + levels for ~2,800 names) and stalk done  ~30s
09:00:25     strike reads the closed 09:45–10:00 ET candle — it sleeps until then
09:00:45     news + model read + commit                                ~20s
09:01:15     Pages live; the buy-stop window runs to 09:15 CT
```

Measured on the manual runs of 09-10, 09-16 and 10-08. `sneak/stage.py` reads the clock and the committed state and either runs or explains why not:

| You click `all` … | What happens |
|---|---|
| 07:55 – 08:59 CT | Runs and sleeps to each candle close; on time |
| 09:00 – 09:14 CT | Runs immediately; the list is a minute or two later |
| after 09:15 CT | Runs, but the page is stamped *published after the entry window* — today's orders are void |
| before 07:55 CT | **Refused** with a red X: the sleep would outlive the 75-minute job timeout |
| a second time | Skips — today is already published (use `publish` to rebuild the page) |
| weekend / holiday | Skips |

**Why there is no cron.** GitHub's scheduler started this repo's runs 3½–6 hours late from late August on, so every on-time session already came from a manual start. To automate later, have an external clock (cron-job.org or similar) `POST` to `https://api.github.com/repos/arrakistacos/morning-brief/actions/workflows/sneak.yml/dispatches` with `{"ref":"main","inputs":{"stage":"all"}}` at 08:30–08:55 America/Chicago on weekdays, using a fine-grained token with *Actions: write* on this repo. A click on top of it is a no-op, so the two can coexist.

## Model usage

Deliberately lopsided — the model is spent only where it changes a decision, and it reads news, never the trade.

| Step | Engine | Why |
|---|---|---|
| Universe, levels, candles, gates, targets, R:R, ranking | **Plain Python** | Deterministic arithmetic. A model here would add cost, latency and error. |
| Per-ticker headline read | **Haiku** | Bulk classification of short headline text, one cheap call per ticker that has headlines, run in parallel. |
| Final headline adjudication | **Opus** | One call over every ticker with headlines, seeing the headlines and the Haiku reads together. |

The models are shown headlines only. When Opus was also shown the trade maths it rated on risk/reward instead of news, and the published list was empty on 19 of 21 sessions from 08-28 to 10-08. Reward/risk is now a deterministic gate in the scanner.

Needs the `CLAUDE_API_KEY` repo secret. Without it, keyword flags still catch red flags (offerings, guidance cuts, failed trials, fraud probes), names with no headlines still publish as `quiet`, and names with unread headlines are held back as `caution`.

The model IDs are a hard-coded fallback chain in `sneak/triage.py` — the next one is only tried if the previous one errors, and **the list does not update itself**. Check which tier answers with **Actions → SNEAK → Run workflow → stage: `selftest`**. Roughly 2–3¢ per trading day.

## Layout

```
sneak/
  yahoo.py       Yahoo chart/spark client — browser UA, retry/backoff, thread pool
  levels.py      previous-day range, fractal swing pivots, ATR, headroom, projected move, RSI
  prep.py        universe refresh, level cache, liquidity floor
  scan_open.py   08:45 CT — the stalk (with a Yahoo coverage check)
  confirm.py     09:00 CT — the strike: gates, buy-stop orders, ranking
  momentum.py    the within-day momentum score
  news.py        per-ticker headline pull + keyword pre-flags
  triage.py      Haiku fan-out + Opus adjudication (headlines only)
  dashboard.py   builds docs/index.html
  quotes.py      stoic line of the day
  stage.py       decides which stage a firing should run
  prune.py       drops per-session cache files older than 30 days (by filename date)
  verify.py      independent re-derivation of a session's numbers (manual audit)
  market_calendar.py   NYSE calendar incl. holidays and early closes
research/
  backtest.py    the 5-minute backtest behind the v2 rules
  README.md      method, results, every variant tested, caveats
docs/            GitHub Pages output — index.html + sessions/ + archive.json
```

`data/cache/` keeps 30 days of stalk/strike JSON. `newsrating-*.json` is kept forever: it is a few KB a day and the only record of what the news gate said live — headlines cannot be re-fetched for a past date.

## Running it by hand

```bash
pip install -r requirements.txt
python -m sneak.prep                                  # build today's levels
python -m sneak.scan_open --no-wait                   # stalk (skip the sleep)
python -m sneak.confirm  --no-wait                    # strike
python -m sneak.news --top 200 && python -m sneak.triage --top 200
python -m sneak.dashboard
python -m sneak.verify                                # audit today's numbers
```

Replay a past session with `--date YYYY-MM-DD` on prep, scan_open, confirm, dashboard and verify. Yahoo keeps about 60 days of 15-minute history. Headlines are always *today's*, so a replay's news read means nothing.

## Dashboard notes

Single self-contained HTML file — no CDN, no charts. It opens instantly on a phone and every value is selectable text. Each session renders under the rules it was scanned with, so old pages and the archive keep what was actually published that morning.

---

*Not investment advice. Levels and candles come from Yahoo Finance and may be delayed.*
