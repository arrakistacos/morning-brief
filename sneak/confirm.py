#!/usr/bin/env python3
"""
confirm.py — 09:00 CT · THE STRIKE.

The second 15-minute candle (09:45–10:00 ET) has just closed. Of everything the
08:45 stalk flagged, keep the names where the drop has visibly hit resistance —
the sneaky candle — and turn each one into a buy-stop order for candle 3.

Gates — every one must hold:

    bar2.close > bar2.open          the sneaky candle is green
    bar2 body >= 5% of its range    a real candle, not a doji
    bar2.low  >= bar1.low           its wick never took out the red candle's low
    RSI(14) after bar2 >= 40        momentum on the 15-minute series has turned
    bar1 held the swing low         structure intact — the range high is the objective
    0 < headroom < 9%               room to the range high, but not a damaged name
    reward / risk >= 0.35           the projected move is worth the stop

The order — candle 3 is the entry candle (long only, cash account):

    trigger = bar2.high + $0.01     buy-stop: fills only if price breaks the sneaky high
    stop    = bar1.low              the red candle's low, never moved
    target  = trigger x (1 + projected move for the headroom at the trigger)
    valid   10:00:00-10:15:00 ET    (09:00-09:15 CT) — cancel it unfilled after that,
                                    and cancel it if price trades through the stop first
    exit    flat by the close if neither the stop nor the target is hit

Why the break of the sneaky high rather than its close. In the 56-session
backtest (research/README.md) the buy-stop leaves ~40% of setups unfilled, and
those are disproportionately the ones that roll over. With the RSI floor and
the 9% headroom ceiling it lifted the win rate on the 30 sessions after the fit
window from 52.7% to 67.6% — but half of those trades risked 4x what they
could make, and that half lost money. The 0.35 reward/risk floor (chosen on the
first 26 sessions only) removes them: win rate is unchanged (65.8% on the test
sessions) and mean R moves from -0.02 to +0.13. The confidence interval on that
still spans zero; it is a better trade list, not a proven edge.

The list is ranked by momentum score. The dashboard applies one further gate:
the news read must be `quiet` or `clear`. See sneak/dashboard.py.

Usage:
    python -m sneak.confirm                # waits for the 10:00 ET bar
    python -m sneak.confirm --no-wait --date 2026-08-14
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import date, datetime

from . import yahoo
from .levels import HEADROOM_MAX, headroom_ok, headroom_pct, projected_move_pct, rsi_series
from .momentum import score_cohort
from .prep import CACHE_DIR
from .scan_open import wait_for_bar

BAR2_OPEN_ET = (9, 45)
BAR2_CLOSE_ET = (10, 0)

# Candle 3 is the entry candle. The buy-stop is live for exactly this window.
ENTRY_WINDOW_ET = ((10, 0), (10, 15))
TICK = 0.01

# Below this the "green candle" is really a doji and the resistance read is noise.
MIN_GREEN_BODY_PCT = 0.05

# RSI(14) on the 15-minute series, read after the green candle. Win rate climbs
# with the floor on BOTH halves of the backtest (test sessions: >=35 62%, >=40
# 65%, >=45 69%), so 40 is a point on a slope, not a lucky cut. 40 was the train
# median. RSI(7) feeds the momentum score.
RSI_N = 14
RSI_FAST = 7
RSI_MIN_AFTER_GREEN = 40.0

# Reward/risk floor, measured at the trigger before the order is placed. Chosen
# on the 26 training sessions (0.35 and 0.40 were best; 0.35 keeps more trades)
# and confirmed on the 30 test sessions. Below it the target is so close that
# the trade wins often and pays nothing: R:R under 0.35 was 70% of the setups
# and averaged -0.09R.
MIN_RR = 0.35

# Reference threshold only — nothing is bucketed out on it. A stop closer than
# this to the entry sits inside the spread, so the row is tagged `tight_stop`.
MIN_RISK_PCT = 0.50

# RSI is seeded from this many sessions of 15-minute history, the same depth a
# live `range=5d` request returns, so a replay computes the same numbers.
RSI_SESSIONS = 5


def load_stalk(day: date) -> dict:
    p = CACHE_DIR / f"stalk-{day.isoformat()}.json"
    if not p.exists():
        raise SystemExit(f"[strike] no stalk file for {day} — run `python -m sneak.scan_open` first.")
    return json.loads(p.read_text())


def _history(bars: list[dict], day: date, sessions: int = RSI_SESSIONS) -> list[dict]:
    """Regular-hours bars for the `sessions` trading days ending on `day`."""
    rth = [b for b in bars if b["dt"].date() <= day
           and 570 <= b["dt"].hour * 60 + b["dt"].minute < 960]
    keep = sorted({b["dt"].date() for b in rth})[-sessions:]
    return [b for b in rth if b["dt"].date() in keep]


def _rsi_signature(bars: list[dict], bar1: dict, bar2: dict) -> dict | None:
    """
    RSI(14) on the 15-minute series, read across the two opening candles.

    `after_green` is the gated value. `trough` (fell across the red candle, rose
    across the green one) is recorded for the record but no longer gates.
    `prior` is the last bar of the previous session.
    """
    closes = [b["c"] for b in bars]
    if len(closes) < RSI_N + 3:
        return None
    series = rsi_series(closes, RSI_N)
    fast = rsi_series(closes, RSI_FAST)

    try:
        i1 = next(i for i, b in enumerate(bars) if b["t"] == bar1["t"])
        i2 = next(i for i, b in enumerate(bars) if b["t"] == bar2["t"])
    except StopIteration:
        return None
    if i1 == 0:
        return None

    prior, r1, r2 = series[i1 - 1], series[i1], series[i2]
    if prior is None or r1 is None or r2 is None:
        return None

    f2 = fast[i2] if i2 < len(fast) else None
    return {
        "prior": round(prior, 2),
        "after_red": round(r1, 2),
        "after_green": round(r2, 2),
        "fast_after_green": round(f2, 2) if f2 is not None else None,
        "drop": round(prior - r1, 2),
        "recovery": round(r2 - r1, 2),
        "trough": bool(r1 < prior and r2 > r1),
    }


def trigger_price(bar2_high: float) -> float:
    """
    Buy-stop at the first whole cent above the sneaky candle's high.

    Yahoo prints sub-cent highs (15.145), and `round(high + 0.01, 2)` then lands
    on either side of a half-cent depending on float noise. Working in whole
    cents from the stored 4-decimal high makes the number reproducible — the
    audit in verify.py recomputes it from the artifact and must agree exactly.
    """
    cents = math.floor(round(bar2_high, 4) * 100 + 1e-6)
    return round((cents + 1) * TICK, 2)


def _evaluate(cand: dict, bar1: dict, bar2: dict) -> dict:
    lv = cand["levels"]

    trigger = trigger_price(bar2["h"])
    stop = round(bar1["l"], 4)
    risk = trigger - stop
    headroom = headroom_pct(trigger, lv["range_high"])
    projected = projected_move_pct(headroom)
    target = trigger * (1 + projected / 100.0) if projected else trigger
    reward = target - trigger
    rr = (reward / risk) if risk > 0 else None

    g_range = max(bar2["h"] - bar2["l"], 1e-9)
    g_body = bar2["c"] - bar2["o"]
    (f_h, f_m), (u_h, u_m) = ENTRY_WINDOW_ET

    return {
        "order": "buy_stop",
        "entry": trigger,                    # the fill price if the stop triggers
        "trigger": trigger,
        "valid_from_et": f"{f_h:02d}:{f_m:02d}",
        "valid_until_et": f"{u_h:02d}:{u_m:02d}",
        "green_close": round(bar2["c"], 4),  # for the record: the old close entry
        "stop": stop,
        "target": round(target, 4),
        "target_full": round(lv["range_high"], 4),
        "headroom_pct": round(headroom, 3) if headroom is not None else None,
        "projected_move_pct": round(projected, 3) if projected else None,
        "target_kind": "projected move toward prev day range high",
        "broke_swing_low": False,            # swing-low breaks are rejected before this
        "risk_per_share": round(risk, 4),
        "reward_per_share": round(reward, 4),
        "risk_pct": round(risk / trigger * 100, 3) if trigger else None,
        "reward_pct": round(reward / trigger * 100, 3) if trigger else None,
        "rr": round(rr, 3) if rr is not None else None,
        "bar2": {
            "open": round(bar2["o"], 4),
            "high": round(bar2["h"], 4),
            "low": round(bar2["l"], 4),
            "close": round(bar2["c"], 4),
            "volume": int(bar2["v"]),
            "body_pct": round(g_body / g_range, 4),
            "reclaim_pct": round((bar2["c"] - bar1["l"]) / max(bar1["h"] - bar1["l"], 1e-9), 4),
            "held_above_red_low": bar2["l"] >= bar1["l"],
        },
    }


def run(day: date | None = None, wait: bool = True, workers: int = 24) -> dict:
    t0 = time.time()
    day = day or yahoo.now_et().date()
    stalk = load_stalk(day)
    cands = {c["symbol"]: c for c in stalk["candidates"]}
    print(f"[strike] {len(cands)} stalk candidates carried forward", flush=True)

    if wait:
        wait_for_bar(*BAR2_CLOSE_ET)

    # RSI(14) needs history behind the open. Live, range=5d is exactly that.
    # A replay asks for the full 60-day intraday window and trims it back to the
    # same five sessions, otherwise anything older than a few days has no bars.
    replay = day != yahoo.now_et().date()
    ch = yahoo.charts(list(cands), rng="60d" if replay else "5d",
                      interval="15m", workers=workers)

    confirmed, mom_pool = [], []
    rejected = {
        "no_bar2": 0,
        "not_green": 0,
        "doji": 0,
        "undercut_red_low": 0,
        "rsi_below_floor": 0,
        "target_is_range_low": 0,
        "headroom_out_of_range": 0,
        "payoff_too_small": 0,
    }

    for sym, cand in cands.items():
        raw = ch.get(sym)
        if not raw:
            rejected["no_bar2"] += 1
            continue
        bars = _history(raw, day)
        session = yahoo.session_bars(bars, day)
        if len(session) < 2:
            rejected["no_bar2"] += 1
            continue
        bar1, bar2 = session[0], session[1]
        if (bar2["dt"].hour, bar2["dt"].minute) != BAR2_OPEN_ET:
            rejected["no_bar2"] += 1
            continue
        if bar2["c"] <= bar2["o"]:
            rejected["not_green"] += 1
            continue
        if bar2["l"] < bar1["l"]:
            rejected["undercut_red_low"] += 1
            continue
        g_range = max(bar2["h"] - bar2["l"], 1e-9)
        if (bar2["c"] - bar2["o"]) / g_range < MIN_GREEN_BODY_PCT:
            rejected["doji"] += 1
            continue

        rsi = _rsi_signature(bars, bar1, bar2)
        if rsi is None:
            rejected["rsi_below_floor"] += 1
            continue
        mom_inputs = {
            "rsi7_green": rsi.get("fast_after_green") or rsi["after_green"],
            "rsi14_green": rsi["after_green"],
            "rsi14_drop": rsi["drop"],
            "body_frac": cand["bar1"]["body_pct"],
            "range_atr": cand["bar1"].get("atr_mult") or 1.0,
        }
        # The momentum cohort is every sneaky-candle setup with its structure
        # intact, scored BEFORE the RSI floor and the payoff gates — the same
        # cohort the backtest ranked. Scoring only the survivors would make a
        # two-name list read 0 and 100 whatever their quality.
        if not cand["bar1"]["broke_swing_low"]:
            mom_pool.append({"symbol": sym, "mom_inputs": mom_inputs})

        # ── RSI floor ───────────────────────────────────────────────────────
        if rsi["after_green"] < RSI_MIN_AFTER_GREEN:
            rejected["rsi_below_floor"] += 1
            continue

        # ── structure: the red candle must have held the swing low ──────────
        if cand["bar1"]["broke_swing_low"]:
            rejected["target_is_range_low"] += 1
            continue

        trade = _evaluate(cand, bar1, bar2)
        if not headroom_ok(trade["headroom_pct"]):
            rejected["headroom_out_of_range"] += 1
            continue
        if trade["rr"] is None or trade["rr"] < MIN_RR:
            rejected["payoff_too_small"] += 1
            continue
        trade["rsi"] = rsi

        lv = cand["levels"]
        red_range = max(bar1["h"] - bar1["l"], 1e-9)
        trade["risk_vs_red_range"] = round(trade["risk_per_share"] / red_range, 4)
        trade["tight_stop"] = (
            trade["risk_pct"] is not None and trade["risk_pct"] < MIN_RISK_PCT
        )
        atr = lv.get("atr14") or 0
        trade["break_depth_atr"] = (
            round((lv["range_low"] - bar1["l"]) / atr, 3) if atr else None
        )
        confirmed.append({
            "symbol": sym,
            "levels": lv,
            "bar1": cand["bar1"],
            "stalk_score": cand["stalk_score"],
            "trade": trade,
            # Raw inputs for the momentum score, ranked across the whole day's
            # cohort in score_cohort(), so they are stored, not scored, here.
            "mom_inputs": mom_inputs,
        })

    # Momentum is a within-cohort percentile over mom_pool (see above). It still
    # separated winners out of sample inside the new rules (above the day's
    # median 69.5% vs 65.1% below, test sessions), so it is the primary key.
    # Shallower breaks of the range low break ties — deeper ones won less often
    # in both halves of the backtest.
    score_cohort(mom_pool)
    scores = {r["symbol"]: r for r in mom_pool}
    for row in confirmed:
        sc = scores.get(row["symbol"], {})
        row["momentum"] = sc.get("momentum", 50.0)
        row["momentum_parts"] = sc.get("momentum_parts", {})
    confirmed.sort(key=rank_key)

    now_ct = datetime.now(yahoo.CT)
    (u_h, u_m) = ENTRY_WINDOW_ET[1]
    window_closed = (not replay) and (yahoo.now_et().hour * 60 + yahoo.now_et().minute) >= u_h * 60 + u_m

    payload = {
        "stage": "strike",
        "version": 2,
        "session": day.isoformat(),
        "generated_at": now_ct.isoformat(timespec="seconds"),
        "replay": replay,
        "bar": "09:45-10:00 ET",
        "entry_window_et": [f"{h:02d}:{m:02d}" for h, m in ENTRY_WINDOW_ET],
        "published_after_window": window_closed,
        "from_stalk": len(cands),
        "rejected": rejected,
        "confirmed_count": len(confirmed),
        "momentum_cohort": len(mom_pool),
        "filters": {"rsi14_after_green_min": RSI_MIN_AFTER_GREEN,
                    "headroom_max_pct": HEADROOM_MAX, "rr_min": MIN_RR,
                    "entry": "buy-stop at sneaky high + $0.01, 10:00-10:15 ET",
                    "target_must_be": "prev day range high", "news_must_be": "quiet or clear"},
        "elapsed_sec": round(time.time() - t0, 1),
        "stalk_meta": {k: stalk.get(k) for k in ("scanned", "quoted", "narrowed", "generated_at", "coverage")},
        "confirmed": confirmed,
    }

    out = CACHE_DIR / f"strike-{day.isoformat()}.json"
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(
        f"[strike] {len(confirmed)} confirmed · rejected {rejected} · "
        f"{payload['elapsed_sec']}s → {out.name}",
        flush=True,
    )
    if window_closed:
        print("::warning::strike list built after the 10:15 ET entry window closed — "
              "today's orders are void; the list is for the record only", flush=True)
    for r in confirmed[:20]:
        t = r["trade"]
        print(
            f"  {r['symbol']:<6} mom {r.get('momentum', 0):>5.1f}  buy-stop {t['trigger']:>9.2f}  "
            f"stop {t['stop']:>9.2f} (-{t['risk_pct']:.2f}%)  tgt {t['target']:>9.2f} "
            f"(+{t['reward_pct']:.2f}%)  RSI {t['rsi']['after_green']:.1f}",
            flush=True,
        )
    return payload


def rank_key(r: dict):
    """Momentum first, then the shallower break of the range low."""
    bd = r["trade"].get("break_depth_atr")
    return (-(r.get("momentum") or 0), bd if bd is not None else 9e9, r["symbol"])


def main() -> int:
    ap = argparse.ArgumentParser(description="09:00 CT sneaky-candle confirmation")
    ap.add_argument("--date", type=str, default=None)
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--workers", type=int, default=24)
    a = ap.parse_args()
    day = datetime.strptime(a.date, "%Y-%m-%d").date() if a.date else None
    run(day=day, wait=not a.no_wait, workers=a.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
