#!/usr/bin/env python3
"""
exits.py — the evidence behind the scale-out exit (research/README.md §9).

For every filled sneaky-candle setup, replays the 5-minute path after the
candle-3 buy-stop fill under a set of exits and compares them with the single
projected-move target. Populations: v3 (the live rules), and the wider
checklist >= 3 set without the R:R floor (the floor is itself measured on the
target, so it is relaxed to give the comparison more trades).

    python research/exits.py          # needs research/data from backtest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "research")]
import backtest as bt                                   # noqa: E402
import checklist as ck                                  # noqa: E402
from sneak.levels import headroom_pct, projected_move_pct  # noqa: E402

COST = bt.COST


def paths() -> pd.DataFrame:
    import pickle
    b15 = pickle.load(open(bt.DATA / "bars_15m.pkl", "rb"))
    df = bt.build_setups(bt.sessions_available(b15))
    stalk_n = df.groupby("day").size()
    pool = df[df.green & df.held & (df.body2 >= 0.05) & ~df.broke_swing].copy()
    pool["solo_frac"] = pool.day.map((pool.groupby("day").size() / stalk_n).fillna(0))
    daily = pickle.load(open(bt.DATA / "daily.pkl", "rb"))
    from datetime import datetime

    def prior_ret(r):
        a = daily[r.sym]
        m = np.array([datetime.fromtimestamp(int(t), bt.ET).date() < r.day for t in a["t"]])
        c = a["c"][m]
        return (c[-1] / c[-2] - 1) * 100
    pool["prior_ret"] = [prior_ret(r) for r in pool.itertuples()]
    pool["points"] = (((pool.c2 - pool.range_low) / pool.atr >= ck.RECLAIM).astype(int)
                      + (pool.prior_ret >= 0) + ((pool.range_low - pool.l1) / pool.atr <= ck.SHALLOW)
                      + (pool.rsi_green >= ck.RSI_PT) + (pool.solo_frac <= ck.SOLO))
    B5 = bt.five_minute(set(pool.sym))
    rows = []
    for r in pool.itertuples():
        d = B5.get(r.sym, {}).get(r.day)
        if d is None:
            continue
        start, stop, trig, fill = int(np.searchsorted(d["m"], 600)), r.l1, r.h2 + 0.01, None
        for i in range(start, len(d["m"])):
            if d["m"][i] >= 615 or (d["l"][i] <= stop and d["h"][i] < trig):
                break
            if d["h"][i] >= trig:
                fill, fi = max(trig, d["o"][i]), i
                break
        if fill is None or fill <= stop:
            continue
        hd_t = headroom_pct(trig, r.range_high)
        rows.append(dict(day=r.day, sym=r.sym, fill=fill, stop=stop, risk=fill - stop,
                         pm=projected_move_pct(headroom_pct(fill, r.range_high)) or 0,
                         range_high=r.range_high, hd_trig=hd_t, points=r.points,
                         rr=trig * (projected_move_pct(hd_t) or 0) / 100 / (trig - stop),
                         path=[a[fi:] for a in (d["o"], d["h"], d["l"], d["c"])]))
    return pd.DataFrame(rows)


def exit_R(t, t1: float, t2: float | None, frac: float) -> float:
    """Sell `frac` at t1 (stop on the rest -> entry), the rest at t2 (None = the close).
    Same fill conventions as backtest.simulate: the stop wins ties, on the fill bar
    a target counts only if the bar closes beyond it, gaps fill at the open."""
    o, h, l, c = t.path
    stop, got1, ex = t.stop, None, None
    for i in range(len(o)):
        first = i == 0
        if not first and o[i] <= stop:
            ex = o[i]; break
        tgt = t1 if got1 is None else t2
        if tgt is not None and not first and o[i] >= tgt:
            if got1 is None and frac < 1:
                got1, stop = o[i], t.fill; continue
            ex = o[i]; break
        if l[i] <= stop:
            ex = stop; break
        if tgt is not None and ((not first and h[i] >= tgt) or (first and c[i] >= tgt)):
            if got1 is None and frac < 1:
                got1, stop = tgt, t.fill; continue
            ex = tgt; break
    if ex is None:
        ex = c[-1]
    px = ex if got1 is None else frac * got1 + (1 - frac) * ex
    return (px - t.fill) / t.risk - COST * t.fill / t.risk


EXITS = {
    "single target (v3 until 10-29)": lambda t: exit_R(t, t.fill * (1 + t.pm / 100), None, 1.0),
    "no target, flat at close":       lambda t: exit_R(t, None, None, 1.0),
    "half T1 / half range high":      lambda t: exit_R(t, t.fill * (1 + t.pm / 100), t.range_high, 0.5),
    "third T1 / rest range high":     lambda t: exit_R(t, t.fill * (1 + t.pm / 100), t.range_high, 1 / 3),
    "half T1 / half 2.5x projection": lambda t: exit_R(t, t.fill * (1 + t.pm / 100),
                                                       t.fill * (1 + 2.5 * t.pm / 100), 0.5),
    "half T1 / half to the close":    lambda t: exit_R(t, t.fill * (1 + t.pm / 100), None, 0.5),
}


def main() -> int:
    P = paths()
    days = sorted(P.day.unique()); k = len(days) // 3
    P["third"] = P.day.map({d: (0 if i < k else 1 if i < 2 * k else 2) for i, d in enumerate(days)})
    gate = (P.hd_trig > 0) & (P.hd_trig < 9) & (P.points >= ck.MIN_PTS)
    for name, m in (("v3 (R:R >= 0.35)", gate & (P.rr >= 0.35)), ("checklist >= 3, no R:R floor", gate)):
        S = P[m]
        print(f"\n{name}: {len(S)} trades, {S.day.nunique()} sessions")
        print(f"  {'exit':34s} mean R   win    total   by third")
        for label, f in EXITS.items():
            v = np.array([f(t) for t in S.itertuples()])
            th = " ".join(f"{v[(S.third == i).values].mean():+.2f}" for i in range(3))
            print(f"  {label:34s} {v.mean():+.3f} {(v > 0).mean():6.1%} {v.sum():+7.2f}R  {th}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
