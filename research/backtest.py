#!/usr/bin/env python3
"""
backtest.py — Re-run the sneaky-candle backtest behind the v2 rules.

Pulls everything Yahoo still holds (daily bars for a year, 15- and 5-minute bars
for ~60 trading days), rebuilds every stalk candidate for every session with the
scanner's own level and RSI code, simulates each trade on 5-minute bars, and
prints the old rules against the new ones on a train / test split.

    python research/backtest.py                       # fetch + report
    python research/backtest.py --split 2026-08-28    # change the hold-out start
    python research/backtest.py --no-fetch            # reuse research/data/*.pkl

Yahoo keeps only ~60 days of intraday history, so each run sees a window ending
today. Run it every few weeks: the hold-out keeps growing, and that is the only
way to find out whether the edge is real. Live news ratings are read from
data/cache/newsrating-*.json (headlines cannot be re-fetched for past dates).

Simulator rules (deliberately conservative):
  * 0.05% round-trip cost charged on every trade.
  * Within a 5-minute bar that touches both stop and target, the stop wins.
  * On the bar a buy-stop fills, the stop counts if the bar's low reaches it,
    the target only if the bar CLOSES beyond it.
  * Opens that gap through a level fill at the open, not the level.
  * A buy-stop is cancelled if price trades through the stop before triggering.
  * A "win" is a trade that closes with R > 0 after costs.
"""

from __future__ import annotations

import argparse
import glob
import json
import pickle
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sneak import yahoo                                     # noqa: E402
from sneak.levels import (compute_levels, headroom_pct,     # noqa: E402
                          projected_move_pct, rsi_series)
from sneak.market_calendar import _NYSE                     # noqa: E402
from sneak.momentum import score_cohort                     # noqa: E402
from sneak.scan_open import MIN_CANDLE_ATR, break_margin    # noqa: E402

DATA = ROOT / "research" / "data"
COST = 0.0005
ET = yahoo.ET


# ── data ─────────────────────────────────────────────────────────────────────

def _pack(bars):
    return {k: np.array([b[k] for b in bars], dtype=np.int64 if k in ("t", "v") else np.float64)
            for k in ("t", "o", "h", "l", "c", "v")}


def _unpack(a):
    return [{"t": int(a["t"][i]), "dt": datetime.fromtimestamp(int(a["t"][i]), ET),
             "o": a["o"][i], "h": a["h"][i], "l": a["l"][i], "c": a["c"][i], "v": int(a["v"][i])}
            for i in range(len(a["t"]))]


def fetch(workers: int = 16) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    syms = [l.strip() for l in (ROOT / "data" / "universe.txt").read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    print(f"[fetch] daily bars for {len(syms)} symbols…", flush=True)
    daily = {s: _pack(b) for s, b in yahoo.charts(syms, rng="1y", interval="1d", workers=workers).items()}
    pickle.dump(daily, open(DATA / "daily.pkl", "wb"))
    b15 = {}
    for s, b in yahoo.charts(syms, rng="60d", interval="15m", workers=workers).items():
        b15[s] = _pack(b)
    print(f"[fetch] 15m bars for {len(b15)} symbols", flush=True)
    pickle.dump(b15, open(DATA / "bars_15m.pkl", "wb"))


def sessions_available(b15: dict) -> list[date]:
    first = min(datetime.fromtimestamp(int(a["t"][0]), ET).date() for a in b15.values() if len(a["t"]))
    last = max(datetime.fromtimestamp(int(a["t"][-1]), ET).date() for a in b15.values() if len(a["t"]))
    days = [d.date() for d in _NYSE.schedule(first.isoformat(), last.isoformat()).index]
    return days[5:]          # the first five seed RSI


def build_setups(sessions: list[date]) -> pd.DataFrame:
    daily = pickle.load(open(DATA / "daily.pkl", "rb"))
    b15 = pickle.load(open(DATA / "bars_15m.pkl", "rb"))
    by_day = {}
    for s, a in b15.items():
        d = defaultdict(list)
        for b in _unpack(a):
            if 570 <= b["dt"].hour * 60 + b["dt"].minute < 960:
                d[b["dt"].date()].append(b)
        by_day[s] = d
    rows = []
    for s, a in daily.items():
        dd = by_day.get(s)
        if not dd:
            continue
        dbars = _unpack(a)
        for day in sessions:
            if day not in dd or len(dd[day]) < 3:
                continue
            b1, b2 = dd[day][0], dd[day][1]
            if (b1["dt"].hour, b1["dt"].minute) != (9, 30) or (b2["dt"].hour, b2["dt"].minute) != (9, 45):
                continue
            if not b1["c"] < b1["o"]:
                continue                     # cheap test first: the candle must be red
            lv = compute_levels(s, dbars, today=day)
            if not lv or lv["prev_close"] < 3 or lv["avg_dollar_vol20"] < 5_000_000:
                continue
            atr = lv.get("atr14") or 0
            if not (round(b1["l"], 4) <= lv["range_low"] - break_margin(lv["range_low"])):
                continue
            if atr <= 0 or (b1["h"] - b1["l"]) / atr < MIN_CANDLE_ATR:
                continue
            prior = sorted(d for d in dd if d < day)[-4:]
            hist = [b for d in prior for b in dd[d]] + dd[day]
            r14 = rsi_series([b["c"] for b in hist], 14)
            r7 = rsi_series([b["c"] for b in hist], 7)
            i1 = len(hist) - len(dd[day])
            sw = lv.get("swing_low")
            rows.append(dict(
                day=day, sym=s, o1=b1["o"], h1=b1["h"], l1=b1["l"], c1=b1["c"],
                o2=b2["o"], h2=b2["h"], l2=b2["l"], c2=b2["c"],
                range_high=lv["range_high"], range_low=lv["range_low"], atr=atr,
                atr_mult=(b1["h"] - b1["l"]) / atr, body1=(b1["o"] - b1["c"]) / max(b1["h"] - b1["l"], 1e-9),
                broke_swing=sw is not None and b1["l"] <= sw - break_margin(sw),
                green=b2["c"] > b2["o"], held=b2["l"] >= b1["l"],
                body2=(b2["c"] - b2["o"]) / max(b2["h"] - b2["l"], 1e-9),
                rsi_prior=r14[i1 - 1] if i1 > 0 else None, rsi_red=r14[i1], rsi_green=r14[i1 + 1],
                rsi7_green=r7[i1 + 1],
            ))
    df = pd.DataFrame(rows)
    df["trough"] = (df.rsi_red < df.rsi_prior) & (df.rsi_green > df.rsi_red)
    return df


# ── simulator ────────────────────────────────────────────────────────────────

def five_minute(symbols) -> dict:
    out = {}
    for s, bars in yahoo.charts(sorted(symbols), rng="60d", interval="5m", workers=16).items():
        d = defaultdict(lambda: defaultdict(list))
        for b in bars:
            m = b["dt"].hour * 60 + b["dt"].minute
            if 570 <= m < 960:
                day = d[b["dt"].date()]
                for k, v in (("m", m), ("o", b["o"]), ("h", b["h"]), ("l", b["l"]), ("c", b["c"])):
                    day[k].append(v)
        out[s] = {day: {k: np.array(v) for k, v in x.items()} for day, x in d.items()}
    return out


def simulate(r, B, entry: str) -> dict | None:
    """entry: 'close' (old rules) or 'break' (buy-stop above bar 2's high, 10:00-10:15 ET)."""
    d = B.get(r.day) if B else None
    if d is None:
        return None
    start = int(np.searchsorted(d["m"], 600))
    stop = r.l1
    if entry == "close":
        fill, fi, partial = r.c2, start, False
    else:
        trig, fill = r.h2 + 0.01, None
        for i in range(start, len(d["m"])):
            if d["m"][i] >= 615:
                break
            if d["l"][i] <= stop and d["h"][i] < trig:
                return None
            if d["h"][i] >= trig:
                fill, fi = max(trig, d["o"][i]), i
                break
        if fill is None:
            return None
        partial = True
    risk = fill - stop
    pm = projected_move_pct(headroom_pct(fill, r.range_high))
    if risk <= 0 or not pm:
        return None
    tgt = fill * (1 + pm / 100)
    exit_px = None
    for i in range(fi, len(d["m"])):
        o, h, l, c = d["o"][i], d["h"][i], d["l"][i], d["c"][i]
        first = partial and i == fi
        if not first and o <= stop:
            exit_px = o; break
        if not first and o >= tgt:
            exit_px = o; break
        if l <= stop:
            exit_px = stop; break
        if (not first and h >= tgt) or (first and c >= tgt):
            exit_px = tgt; break
    if exit_px is None:
        exit_px = d["c"][-1]
    R = (exit_px - fill) / risk - COST * fill / risk
    return {"R": R, "win": R > 0}


def report(df: pd.DataFrame, res: pd.DataFrame, mask, label: str, split: date) -> None:
    t = df[mask].join(res, how="inner")
    for name, m in (("all", t.day == t.day), ("train", t.day < split), ("test", t.day >= split)):
        x = t[m]
        if len(x) == 0:
            continue
        days = [g.win.astype(float).values for _, g in x.groupby("day")]
        rng = np.random.default_rng(0)
        bs = [np.concatenate([days[j] for j in rng.integers(0, len(days), len(days))]).mean()
              for _ in range(2000)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        n_sessions = df[(df.day >= split) if name == "test" else (df.day < split) if name == "train" else df.day == df.day].day.nunique()
        print(f"  {label:<10} {name:<5}  trades {len(x):4}  per day {len(x)/max(n_sessions,1):5.2f}  "
              f"win {x.win.mean():6.1%} [{lo:.0%}-{hi:.0%}]  mean R {x.R.mean():+.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sneaky-candle backtest, old rules vs v2")
    ap.add_argument("--split", default="2026-08-28", help="first session of the hold-out")
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()
    split = date.fromisoformat(a.split)
    if not a.no_fetch:
        fetch()
    b15 = pickle.load(open(DATA / "bars_15m.pkl", "rb"))
    sessions = sessions_available(b15)
    print(f"[backtest] {len(sessions)} sessions {sessions[0]} → {sessions[-1]}; hold-out from {split}")
    df = build_setups(sessions)
    pool = df[df.green & df.held & (df.body2 >= 0.05) & ~df.broke_swing].copy()
    for day, g in pool.groupby("day"):
        rows = [dict(mom_inputs=dict(rsi7_green=r.rsi7_green or r.rsi_green, rsi14_green=r.rsi_green,
                 rsi14_drop=(r.rsi_prior or 0) - (r.rsi_red or 0), body_frac=r.body1, range_atr=r.atr_mult))
                for r in g.itertuples()]
        score_cohort(rows)
        pool.loc[g.index, "momentum"] = [x["momentum"] for x in rows]
    trig = pool.h2 + 0.01
    pool["hd_trig"] = (pool.range_high - trig) / trig * 100
    pm = pool.hd_trig.map(lambda h: (projected_move_pct(h) or 0) / 100)
    pool["rr_pre"] = (trig * pm) / (trig - pool.l1)
    print(f"[backtest] {len(df)} stalk candidates, {len(pool)} sneaky-candle setups; pulling 5m bars…")
    B5 = five_minute(set(pool.sym))
    res = {}
    for entry in ("close", "break"):
        out = {}
        for r in pool.itertuples():
            x = simulate(r, B5.get(r.sym), entry)
            if x:
                out[r.Index] = x
        res[entry] = pd.DataFrame(out).T.astype({"R": float, "win": float})
    old = pool.trough
    new = (pool.rsi_green >= 40) & (pool.hd_trig > 0) & (pool.hd_trig < 9) & (pool.rr_pre >= 0.35)
    print("\nwin = closed with R > 0 after a 0.05% round-trip cost; [95% session-bootstrap CI]")
    report(pool, res["close"], old, "old rules", split)
    report(pool, res["break"], new, "v2 rules", split)

    recs = []
    for p in glob.glob(str(ROOT / "data" / "cache" / "newsrating-*.json")):
        d = date.fromisoformat(Path(p).stem.split("newsrating-")[1])
        for sym, v in json.load(open(p))["tickers"].items():
            recs.append((d, sym, v["rating"]))
    if recs:
        N = {(d, s): r for d, s, r in recs}
        t = pool.join(res["break"], how="inner")
        t["rating"] = [N.get((d, s)) for d, s in zip(t.day, t.sym)]
        t = t[t.rating.notna()]
        print(f"\nlive news ratings, candle-3 entry, {t.day.nunique()} sessions:")
        for lab, m in (("no headlines (quiet)", t.rating == "quiet"), ("any headlines", t.rating != "quiet")):
            print(f"  {lab:<22} n={int(m.sum()):4}  win {t[m].win.mean():6.1%}  mean R {t[m].R.mean():+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
