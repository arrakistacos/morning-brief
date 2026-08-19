#!/usr/bin/env python3
"""
momentum.py — The damage score.

Backtest finding (9,092 setups, 58 sessions, 2026-05-26 → 2026-08-18):

Within a single session, these five measures rank setups by probability of
success. Ranked by within-day Spearman correlation against realised R, the
score reaches t = +3.92 and is positive on 67% of sessions — it clears a
Bonferroni threshold of 3.9 across the 35 indicators that were tested.

Win rate sorts monotonically across all ten deciles:

    decile  1   33.9%          decile  6   52.1%
    decile  2   38.5%          decile  7   58.8%
    decile  3   43.2%          decile  8   63.4%
    decile  4   48.7%          decile  9   67.9%
    decile  5   49.8%          decile 10   73.4%

Ten out of ten in order is what real signal looks like; the feature scans that
failed produced sawtooth patterns instead.

What it measures: how much damage the opening drop did, and how convincingly it
recovered. Mild selloffs that turn momentum back up bounce. Violent ones keep
falling. Every component is deliberately scale-free so the score does NOT just
re-rank by stop distance — correlation with risk size is +0.17, against +0.47
for an earlier version that mixed in entry-position measures.

IMPORTANT — what this score does NOT do. It sorts win *probability*, not
expectancy. Mean R per decile stays flat near zero, because a higher hit rate
comes with a proportionally smaller payoff. Use it to choose BETWEEN setups on a
given morning, never as evidence that a setup is profitable in isolation.

The score is relative to the day's cohort: it is a percentile within this
morning's candidates, so 70 means "better than 70% of today's setups", not an
absolute quality bar.
"""

from __future__ import annotations

# (feature key, sign). Positive means higher is better.
COMPONENTS: list[tuple[str, int]] = [
    ("rsi7_green", +1),    # fast momentum after the sneaky candle
    ("rsi14_green", +1),   # standard momentum after the sneaky candle
    ("rsi14_drop", -1),    # how far the red candle knocked momentum down
    ("body_frac", -1),     # how much of the red candle was body (violence)
    ("range_atr", -1),     # red candle size relative to normal range
]


def _percentile_ranks(values: list[float]) -> list[float]:
    """0..1 rank within the cohort. Ties resolve by position; good enough here."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    for k, i in enumerate(order):
        out[i] = k / (n - 1)
    return out


def score_cohort(rows: list[dict]) -> None:
    """
    Attach a 0-100 `momentum` score to every row, in place.

    `rows` must be the whole day's candidate set — the score is a within-cohort
    percentile and is meaningless computed one setup at a time.

    Each row needs a `mom_inputs` dict carrying the five component values.
    """
    if not rows:
        return
    if len(rows) == 1:
        rows[0]["momentum"] = 50.0
        rows[0]["momentum_parts"] = {}
        return

    ranked: dict[str, list[float]] = {}
    for key, _ in COMPONENTS:
        ranked[key] = _percentile_ranks([r["mom_inputs"].get(key, 0.0) or 0.0 for r in rows])

    for i, r in enumerate(rows):
        total = 0.0
        parts = {}
        for key, sign in COMPONENTS:
            pr = ranked[key][i]
            contrib = pr if sign > 0 else (1.0 - pr)
            parts[key] = round(contrib * 100, 1)
            total += contrib
        r["momentum"] = round(total / len(COMPONENTS) * 100, 1)
        r["momentum_parts"] = parts
