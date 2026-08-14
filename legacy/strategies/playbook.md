# Muad'Dib Trading Playbook v2 — "Precision Over Prediction"

Rules-based setups for regular-hours U.S. stocks. Swing-first, day-trade capable.
Every trade must clear **1:2 risk/reward minimum** before entry — computed, not guessed.
This file is the single source of truth for the morning brief, open check, midday check, and EOD scorecard.

> *"You must concentrate upon what you must do, and let the rest go."* — the discipline layer is the edge.

---

## 0. REGIME FILTER (check before anything else)

Run `python3 scripts/strategy_engine.py --regime` (fetches SPY vs 50/200DMA + VIX).

| Regime | Condition | Rules |
|---|---|---|
| **RISK_ON** | SPY > 50DMA **and** VIX < 20 | Full size (1% risk/trade). All setups live. |
| **CAUTION** | SPY > 200DMA but < 50DMA, **or** VIX 20–25 | Half size. Only setups scoring 5/5. |
| **RISK_OFF** | SPY < 200DMA **or** VIX > 25 | No new swing longs. Only ORB-5 day trades and DIP at half size. |

Evidence: regime/trend filters (200DMA + VIX sizing tiers) consistently reduce drawdown across bear markets; VIX tiers: full size 12–20, −30% size 20–30, −50% above 30.

---

## 1. THE FIVE SETUPS

### S1 · PULLBACK — Trend Pullback to Rising 20EMA (swing, 2–10 days)
- **Universe:** price > $10, 50d avg volume > 1M sh, price > 50DMA > 200DMA, positive 1M relative strength vs SPY.
- **Trigger:** orderly 3–8% pullback into the 20EMA zone on *declining* volume, then a reversal day. Enter on break of prior day's high.
- **Stop:** tighter of (pullback low − 0.1×ATR) or (entry − 1.5×ATR14).
- **Target:** T1 = entry + 2R → sell half, stop to breakeven. Trail rest: exit on close below 20EMA.
- **Stats:** 55–65% win rate in confirmed trends at 2:1+ R:R (backtested).

### S2 · BREAKOUT — Volatility-Contraction Breakout (swing, days–weeks)
- **Universe:** same as S1 + base of ≥15 sessions with visibly contracting ranges and volume dry-up near the end.
- **Trigger:** break of pivot high on volume ≥ 1.5× 50d average. Do NOT chase >2% past pivot.
- **Stop:** breakout-day low or entry − 1.5×ATR14, whichever is tighter.
- **Target:** T1 = entry + 2R → half off; trail rest with 10EMA.
- **Stats:** 60–70% on volume-validated breakouts; winners run.

### S3 · GAP-GO — Earnings Gap Continuation (swing, 1–5 days)
- **Universe:** gap up >4% on EPS **and** revenue beat, ideally raised guidance; pre-market volume > 500k.
- **Trigger:** break of the **first-30-minute high** (never buy the open print — let the gap prove itself).
- **Stop:** first-30-minute low. **Skip the trade if that stop makes R:R < 1:2** to the measured target.
- **Target:** 2R minimum; strong closers can be held for post-earnings drift (up to 5 sessions).

### S4 · ORB-5 — 5-Minute Opening Range Breakout on Stocks-in-Play (day trade)
- **Universe:** ONLY stocks-in-play — relative volume ≥ 2 at the open with a real catalyst. This filter is the whole edge.
- **Trigger:** break of the first-5-minute high (long) when the open gapped in that direction.
- **Stop:** first-5-minute low. **Skip if the 5-min range > 1×ATR14** (stop too wide).
- **Target:** 2R, or trail above VWAP. **Flat by 14:55 CT — no overnight.**
- **Stats:** Zarattini/Barbon/Aziz (2016–2023, 7,000+ stocks): top-20 RVOL names → Sharpe 2.81, ~41.6% annualized IRR, near-zero beta.

### S5 · DIP — RSI(2) Quality Dip (swing, 1–5 days)
- **Universe:** S&P 500 members above their 200DMA (quality only — no falling knives).
- **Trigger:** RSI(2) < 10 (A+ when < 5). Enter same-day close or next open.
- **Exit:** RSI(2) crosses above 50, or 5 sessions, whichever first.
- **Stop:** entry − 2×ATR14 (disaster stop; this is a high-win-rate/small-win setup — run at HALF size).
- **Stats:** Connors RSI(2) with 200DMA filter — historically ~70%+ win rate, small average winners.

---

## 2. POSITION SIZING & MANAGEMENT (non-negotiable)

- **Risk per trade:** 1% of total equity (0.5% in CAUTION / for S5). Shares = floor(risk$ ÷ (entry − stop)).
- **Max 4 open positions; max 2 per GICS sector.**
- **Never average down. Never widen a stop.**
- At **+1R**: stop to breakeven. At **+2R**: sell half. Then trail per setup rules.
- **Time stop:** swing trades dead-money after 10 sessions → exit, recycle capital.
- All stops/targets are **ATR-anchored** (1.5×ATR stop / 3×ATR target = true 1:2), not fixed percentages — a stop must live outside the stock's normal noise band.

## 3. PRECISION CHECKLIST (score every idea 0–5)

+1 each: ① regime-aligned ② relative-strength leader ③ volume confirms ④ clean level (obvious stop) ⑤ identifiable catalyst.
- **5/5 → A+ (STRONG_BUY eligible)** · **4/5 → tradeable (BUY)** · **≤3 → watch only.**

## 4. FEEDBACK LOOP

EOD task scores every triggered idea: **+2R hit = WIN, −1R hit = LOSS, else OPEN.**
Morning brief reads the trailing 10 `eod_scorecard` entries — any setup resolving <40% winners gets benched for the week. The playbook adapts to what is *currently* working, by measurement, not vibes.
