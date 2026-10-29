#!/usr/bin/env python3
"""
checklist.py — the evidence behind the rules-v3 checklist (research/README.md §8).

Replays every sneaky-candle setup in the cached data with the candle-3 buy-stop,
scores the five checklist points, and compares v2 (RSI >= 40) with v3
(>= 3 of 5 points), both with the headroom 0-9% and R:R >= 0.35 gates.

    python research/checklist.py          # needs research/data from backtest.py
"""
from __future__ import annotations

import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "research")]
import backtest as bt                                     # noqa: E402
from sneak.levels import projected_move_pct               # noqa: E402

RECLAIM, SHALLOW, RSI_PT, SOLO, MIN_PTS = 0.10, 0.25, 45.0, 0.25, 3


def frame() -> pd.DataFrame:
    b15 = pickle.load(open(bt.DATA / "bars_15m.pkl", "rb"))
    daily = pickle.load(open(bt.DATA / "daily.pkl", "rb"))
    df = bt.build_setups(bt.sessions_available(b15))
    stalk_n = df.groupby("day").size()
    pool = df[df.green & df.held & (df.body2 >= 0.05) & ~df.broke_swing].copy()
    solo = (pool.groupby("day").size() / stalk_n).fillna(0)
    trig = pool.h2 + 0.01
    pool["hd"] = (pool.range_high - trig) / trig * 100
    pool["rr"] = trig * pool.hd.map(lambda h: (projected_move_pct(h) or 0) / 100) / (trig - pool.l1)
    pool["solo_frac"] = pool.day.map(solo)
    pool["reclaim_atr"] = (pool.c2 - pool.range_low) / pool.atr
    pool["depth_atr"] = (pool.range_low - pool.l1) / pool.atr

    def prior_ret(r):
        a = daily.get(r.sym)
        if a is None:
            return np.nan
        m = np.array([datetime.fromtimestamp(int(t), bt.ET).date() < r.day for t in a["t"]])
        c = a["c"][m]
        return (c[-1] / c[-2] - 1) * 100 if len(c) > 1 else np.nan
    pool["prior_ret"] = [prior_ret(r) for r in pool.itertuples()]

    pool["points"] = ((pool.reclaim_atr >= RECLAIM).astype(int) + (pool.prior_ret >= 0)
                      + (pool.depth_atr <= SHALLOW) + (pool.rsi_green >= RSI_PT)
                      + (pool.solo_frac <= SOLO))
    B5 = bt.five_minute(set(pool.sym))
    out = []
    for r in pool.itertuples():
        s = bt.simulate(r, B5.get(r.sym), "break")
        out.append((s["R"], float(s["win"])) if s else (np.nan, np.nan))
    pool["R"], pool["win"] = zip(*out)
    return pool[pool.R.notna()]


def ci(d: pd.DataFrame, n: int = 4000, seed: int = 0):
    rng = np.random.default_rng(seed)
    g = [x.win.values for _, x in d.groupby("day")]
    bs = [np.concatenate([g[i] for i in rng.integers(0, len(g), len(g))]).mean() for _ in range(n)]
    return np.percentile(bs, [2.5, 97.5])


def main() -> int:
    f = frame()
    gate = (f.hd > 0) & (f.hd < 9) & (f.rr >= 0.35)
    print(f"{len(f)} filled sneaky setups · {f.day.nunique()} sessions "
          f"({f.day.min()} → {f.day.max()}) · base win {f.win.mean():.1%}\n")
    print("points (all fills):")
    for p, g in f.groupby("points"):
        print(f"  {p}  n={len(g):3d}  win {g.win.mean():5.1%}  R {g.R.mean():+.3f}")
    for name, m in (("v2  RSI>=40", gate & (f.rsi_green >= 40)),
                    ("v3  points>=3", gate & (f.points >= MIN_PTS))):
        k = f[m]
        lo, hi = ci(k)
        print(f"\n{name}: {len(k)} trades · win {k.win.mean():.1%} [{lo:.0%}–{hi:.0%}] · "
              f"mean R {k.R.mean():+.3f} · {len(k) / f.day.nunique():.2f}/day")
    return 0


if __name__ == "__main__":
    sys.exit(main())
