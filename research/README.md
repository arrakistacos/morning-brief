# Backtest behind the v2 rules (2026-10-10) the v3 checklist (2026-10-28) and the scale-out exit (2026-10-29)

Re-run with `python research/backtest.py`. Yahoo keeps ~60 trading days of intraday bars, so every run sees a window ending on the day it runs. Re-run every few weeks — the hold-out grows, and a growing hold-out is the only real test.

## Data and method

- **Window.** 56 sessions, 2026-07-23 → 10-09, the full span of 15- and 5-minute history Yahoo held on 10-10. This includes the 8 sessions the scheduler missed (09-29 → 10-07, 10-09).
- **Universe.** `data/universe.txt` as of 10-08, filtered per session with the scanner's own liquidity floor (price ≥ $3, 20-day dollar volume ≥ $5M) — ~2,830 names a day.
- **Setups.** Every stalk candidate rebuilt per session with the scanner's own code (`compute_levels`, `break_margin`, `rsi_series`, `score_cohort`): 4,831 dramatic red breaks, 916 sneaky-candle setups (green, body ≥ 5%, held candle 1's low, swing low intact), 818 of them with the old RSI V-trough. The rebuild matched the live cache's daily counts closely.
- **Simulation.** 5-minute bars from 10:00 ET. A 0.05% round-trip cost on every trade. When a bar touches both stop and target, the stop wins. On the bar a buy-stop fills, the stop counts if the low reaches it and the target only if the bar *closes* beyond it. Gaps fill at the open. A buy-stop is cancelled if price trades through the stop before it triggers. Flat at the last bar of the day.
- **Win** = the trade closed with R > 0 after costs. Mean R and % return are reported alongside, because a smaller target always raises the win rate.
- **Split.** Train = the 26 sessions to 08-27 (the window the old headroom band and projection were fitted on, plus July). Test = the 30 sessions from 08-28. Every new rule and threshold was chosen on train, then read once on test. CIs are session-clustered bootstraps (2,000 draws).

## 1. The old rules, out of sample

Entry at candle 2's close, stop at candle 1's low, target = projected move, flat by the close.

| | trades | win | mean R |
|---|---|---|---|
| train | 401 | 59.4% | −0.072 |
| **test** | 406 | **52.7%** | −0.065 |

Every published claim, re-tested on the 30 test sessions:

| claim | held up? | test sessions |
|---|---|---|
| 3–9% headroom band ranks better setups | **no** | in band 46.5% win, outside 57.3% |
| 9%+ headroom is damaged | yes | 36.8% win (train 34.8%) |
| momentum score sorts win probability | yes | top half 59.3%, bottom half 46.0% |
| momentum does not sort profit | yes | mean R flat across halves |
| RSI V-trough separates real resistance | **no** | with V 52.7%, without V 55.8% (train: 59.4% vs 66.7%) |
| projected target reached ~60% intraday | **partly** | 49.5% from the close entry; 66.7% from the candle-3 trigger with the v2 filters |

## 2. Entry, stop, target and hold — 224 variants

4 entries (candle-2 close; buy-stop above candle 2's high good for 15, 30 or 60 minutes) × 2 stops (candle 1 low, candle 2 low) × 7 targets (projected move, previous close, range high, 1R, 1.5R, 2R, none) × 2 holds (flat by close, 3 days), on both the V-trough set and the full sneaky-candle set.

**No variant had non-negative mean R on the training sessions.** Exits alone cannot fix this setup. What the grid did show:

- **The break entry beats the close entry on win rate** with the same stop and target: +2.8 / +5.7 points (train / test) for the strict candle-3 window, +4.4 / +4.7 for 30 minutes. Mean R moved by less than ±0.02. About 40% of setups never trigger.
- **The candle-1 stop wins more often than the candle-2 stop** on both halves (strict candle-3 entry, test: 58.4% vs 54.1%) — the tighter stop gets hit by noise. Mean R was mixed between the two, so the documented stop stays.
- **A 3-day hold** raises the win rate ~4 points but not mean R, and ties up settled cash. Not adopted.

## 3. What predicts a win — feature screen

30 candidate features, Spearman against win and R on each half separately, using the candle-2-close and 30-minute-break versions. Only effects with the same sign on both halves are listed.

| feature | effect on win rate (tercile low / mid / high, test) | effect on mean R |
|---|---|---|
| RSI(14) after candle 2 | 46% / 53% / 62% (close entry) | none |
| RSI(7) after candle 2 | 43% / 57% / 62% | none |
| momentum score | 53% / 48% / 71% (break entry) | none |
| break depth below range low, in ATR | 72% / 59% / 42% (break entry) | none |
| headroom | 61% / 52% / 45% (close entry) | none |

Did **not** replicate: SPY / QQQ / IWM opening candles, gap size, market breadth (count of stalk names), volume burst, price level, liquidity.

Everything that predicts *wins* is close to zero against *R*. That is the same pattern `momentum.py` documents: these features find setups that reach a nearby target, and a nearby target pays little. The reward/risk floor (§5) is what deals with that.

## 4. RSI floor — a slope, not a cut

Headroom < 9%, 30-minute break entry, full sneaky-candle set (no V required):

| RSI(14) after candle 2 | train win | test win | test trades |
|---|---|---|---|
| any | 66.9% | 57.9% | 261 |
| ≥ 30 | 68.5% | 60.6% | 208 |
| ≥ 35 | 68.4% | 62.2% | 164 |
| **≥ 40** | 72.8% | 65.0% | 117 |
| ≥ 45 | 73.0% | 68.7% | 67 |
| ≥ 50 | 72.1% | 65.8% | 38 |

40 was the train median. Requiring the V on top of the floor changed nothing.

## 5. Reward/risk floor

With the candle-3 buy-stop, RSI ≥ 40 and headroom 0–9%, the median trade's target was only 0.25× its risk. Win rate barely moves with R:R, but money does:

| R:R at the trigger | trades | win | mean R |
|---|---|---|---|
| ≤ 0.20 | 95 | 73.7% | −0.075 |
| 0.20–0.35 | 83 | 66.3% | −0.116 |
| 0.35–0.50 | 35 | 71.4% | +0.078 |
| 0.50–0.75 | 32 | 71.9% | +0.127 |

The floor was chosen on train from {0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6}. 0.35 and 0.40 were best; 0.35 keeps more trades.

## 6. The news gate

Live ratings from `data/cache/newsrating-*.json` (30–31 sessions, only names the live scanner rated) joined to simulated outcomes, candle-3 entry:

| | trades | win | mean R |
|---|---|---|---|
| no headlines (`quiet`) | 81 | 60.5% | −0.040 |
| any headlines (`clear` / `caution` / `flagged`) | 96 | 49.0% | −0.213 |

Session bootstrap on the difference: P(quiet better) ≈ 0.95–0.97. Among names with headlines the model's grades did not separate outcomes (`clear` was the worst group, n≈20), and many of the Opus reads were about the trade's risk/reward rather than the news. So the gate now holds back company-specific news (`caution`, `flagged`) and publishes `quiet` and generic-headline `clear`. This is the least certain rule here. The sample is small, and it can only be tested going forward because past headlines cannot be re-fetched — which is why `newsrating-*.json` is never pruned.

## 7. v2, all together

Buy-stop above candle 2's high (10:00–10:15 ET) · RSI(14) ≥ 40 · headroom 0–9% · R:R ≥ 0.35 · candle-1 stop · projected target · flat by the close:

| | trades | per day | win | 95% CI | mean R | 95% CI |
|---|---|---|---|---|---|---|
| old rules, test | 406 | 13.5 | 52.7% | 47–60% | −0.065 | −0.19…+0.10 |
| **v2, train** | 46 | 1.8 | 71.7% | 58–84% | +0.109 | −0.07…+0.27 |
| **v2, test** | 38 | 1.3 | **65.8%** | 45–83% | **+0.130** | −0.19…+0.40 |
| v2, all 56 | 84 | 1.5 | 69.0% | 57–79% | +0.119 | −0.06…+0.27 |

Outcomes, all 84 trades: 54 targets, 14 stops, 16 flat at the close. At least one order on 39 of 56 sessions.

## 8. Rules v3 — the checklist (2026-10-28)

**Why.** Re-run on 55 sessions (08-12 → 10-28), v2 won 64.6% (65 trades) — 61.5% on the 13 trades after it was designed. The question was what lifts that.

**Search.** Every sneaky-candle setup (green, held, body ≥ 5%, swing low intact — 733 setups, 389 filled on the candle-3 buy-stop, 54 sessions with 5-minute data) was given ~60 features known by 10:00 ET: candle 1 and 2 shape, wicks, reclaim of the range low, volume (candle 2 vs 1, opening relative volume), VWAP, the 5-minute bars inside candle 2, trigger distance, RSI(14)/RSI(7) levels and change, momentum, yesterday's candle (return, close location, range vs ATR, inside day, NR7), 3/5/10/20-day returns, distance to the 20/50/200-day averages, daily RSI, 52-week position, down-streak, ATR %, liquidity, price, SPY/QQQ/IWM over the first 30 minutes, relative strength, day of week, and the share of the day's stalk names that printed a sneaky candle. Each feature's cutoff was chosen on sessions before 10-01 and read on the 19 after.

**Noise floor.** Shuffling wins within each session and re-running the screen, the best train-set win rate any feature reached by chance was 64% (median) to 70% (max). Most single features sit inside that band; volume, VWAP, intraday detail, trend, day of week and index direction did nothing reliable.

**What held.** Five features lifted the win rate in all three chronological thirds (all sneaky fills, base 58.4%):

| point | rule | n | win | excluded | thirds (kept) |
|---|---|---|---|---|---|
| reclaim | candle 2 close ≥ range low + 0.10 ATR | 176 | 70.5% | 48.4% | 63 / 67 / 81% |
| prior up | yesterday's close ≥ the close before | 154 | 68.2% | 51.9% | 57 / 69 / 77% |
| shallow | range low − candle-1 low ≤ 0.25 ATR | 150 | 70.0% | 51.0% | 64 / 70 / 75% |
| RSI 45 | RSI(14) after candle 2 ≥ 45 | 122 | 69.7% | 53.2% | 67 / 63 / 78% |
| solo | sneaky candles ÷ stalk names that day ≤ 0.25 | 227 | 64.8% | 49.4% | 63 / 52 / 80% |

Reclaim, shallow and RSI 45 are correlated (0.4–0.7); prior up and solo are independent of everything else.

**Points are monotonic** (all sneaky fills): 0 → 32.7%, 1 → 47.6%, 2 → 60.5%, 3 → 72.7%, 4 → 66.7%, 5 → 89.3%.

**The rule.** Headroom 0–9% and R:R ≥ 0.35 kept, RSI ≥ 40 dropped, checklist ≥ 3:

`research/checklist.py` (every filled setup, 437 fills):

| | trades | per day | win | 95% CI | mean R |
|---|---|---|---|---|---|
| v2 (same 54 sessions) | 65 | 1.20 | 64.6% | 50–79% | +0.094 |
| **v3** | 47 | 0.87 | **76.6%** | 62–88% | **+0.189** |

In the screening frame (389 fills — setups with a full 5-minute opening): v2 53 trades 60.4%, v3 40 trades 75.0%; the 26 trades only v2 took won 50.0% (−0.049R), the 13 only v3 took won 84.6%. v3 − v2: win +14.5 points (CI +2…+27, better in 99% of session resamples), mean R +0.15 (CI −0.04…+0.36, better in 94%). Across 243 nearby thresholds (reclaim 0/0.1/0.2, shallow 0.2/0.25/0.35, RSI 40/45/50, solo 0.2/0.25/0.3, prior-day return −0.5/0/+0.5%) the median win rate was 68.9% (5th–95th 62–78%) and 94% kept a positive mean R.

**Caveats specific to v3.** The five points were picked after seeing all 54 sessions, so 75% is optimistic — plan on 65–70%. 40 trades. About 0.75 orders a day. The live solo fraction matches the backtest's to within ~0.03 on the sessions compared (10-12 → 10-28). Re-run: `python research/checklist.py`.

## 9. The exit — scale out (2026-10-29)

**Question.** With the v3 entry fixed, is the projected-move target the best way out?

**Grid.** Every fill replayed on its 5-minute path with the same conventions as §7 (stop wins ties, target on the fill bar only if the bar closes beyond it, gaps fill at the open, 0.05% cost). Single targets: the projected move ×0.5–3, 25–100% of the headroom, 0.25–2R, 0.1–1 ATR, 0.5–3%, candle 1's open and high, yesterday's close, the range high, and none (close). Each with and without a 12:00 or 14:00 ET time exit, a break-even stop after +0.5R, and a 1R/0.5R trail. Then scale-outs: a first target (projection ×0.75/1/1.25) for ⅓, ½ or ⅔ of the shares, the stop on the rest moved to entry, and a runner to the projection ×1.5–3, the range high, or the close — 54 variants.

**Single targets trade win rate for R.** Bigger targets raise the v3 mean R (no target at all: +0.33R) but cut the win rate to 36–55%, and every one of them lost in the middle third of the sessions (−0.29 to −0.47R) where the projected move held flat. Break-even and trailing stops on a single target did nothing reliable.

**Scale-outs keep the win rate and add R.** A trade that reaches target 1 cannot lose afterwards, so the win rate is the single target's; the runner adds the tail. `research/exits.py`:

| exit | v3 (47) mean R | win | total | by third | checklist ≥ 3, no R:R floor (163) mean R | win |
|---|---|---|---|---|---|---|
| single target (until 10-29) | +0.189 | 76.6% | +8.9R | +0.07 / +0.01 / +0.39 | +0.008 | 74.8% |
| **½ at T1, ½ at the range high** | **+0.278** | **76.6%** | **+13.1R** | +0.10 / −0.06 / +0.63 | **+0.048** | 72.4% |
| ⅓ at T1, ⅔ at the range high | +0.308 | 76.6% | +14.5R | +0.11 / −0.09 / +0.70 | +0.061 | 69.3% |
| ½ at T1, ½ at 2.5× projection | +0.274 | 76.6% | +12.9R | +0.13 / −0.07 / +0.60 | +0.042 | 72.4% |
| ½ at T1, ½ to the close | +0.308 | 76.6% | +14.5R | +0.44 / −0.06 / +0.46 | +0.033 | 70.6% |
| no target, close | +0.331 | 53.2% | +15.6R | +0.86 / −0.47 / +0.48 | −0.026 | 42.3% |

- 81–83% of the 54 scale-out variants beat the single target on both populations; the projected move itself (×1) was the best first leg.
- ½ / range high beat the single target in 92% of session-bootstrap resamples on v3 (99% on the 163), and with the top three trades removed (+0.18 vs +0.14R), so it is not one outlier.
- Worst trade and worst drawdown unchanged (−1.32R, −1.54R vs −1.56R). Outcomes on v3: 8 stops, 4 flat at the close below target 1, 15 target 1 then break-even, 12 target 1 then flat at the close, 8 both targets.
- **Cost.** It gives back a little in the middle third (−0.06 vs +0.01R on v3): when price tags target 1 and fades, half the position now exits at entry instead of at target 1.
- ½ was chosen over ⅓ although ⅓ scored higher: the gap is inside the noise, and ½ leans less on the runner.

## Caveats

- **Small hold-out.** 38 test trades. The win-rate gain is consistent everywhere it was measured. The positive mean R is not significant.
- **Multiple testing.** ~250 exit variants and 30 features were looked at. The rule set was fixed on train, and the test half was read for that one rule set, but the researcher still saw the test half while deciding what to try next.
- **One regime.** July–October 2026 only.
- **Survivorship.** The universe is today's symbol list, so names delisted since July are absent.
- **Fills.** 5-minute bars, a flat 0.05% cost, and no queue position. Small caps with wide spreads will do worse than this.
- **News.** Not replayable. Only the names the live scanner rated on the sessions it actually ran.
