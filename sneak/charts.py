#!/usr/bin/env python3
"""
charts.py — Inline SVG for the dashboard. No JS charting library, no CDN:
every graphic is server-rendered SVG so the page is one self-contained file
that renders instantly on a phone at 8:45 in the morning.

Palette is validated (dataviz six-checks, dark surface #0A0F0D):

    categorical  #14AD6E  #2B8CE8  #C4870A  #A85CE8   all six checks PASS
    status trio  #14AD6E  #C4870A  #D6455C            all six checks PASS
    bull / bear  #35C98A  #D6455C   CVD ΔE 13.2 deutan, contrast PASS

Bull/bear is a semantic pair, not a categorical set, so the categorical
lightness band does not apply to it. It carries secondary encoding regardless —
bear candles are filled, bull candles are hollow — so direction never depends on
colour alone.
"""

from __future__ import annotations

from html import escape

BULL = "#35C98A"
BEAR = "#D6455C"
CAT = ["#14AD6E", "#2B8CE8", "#C4870A", "#A85CE8"]
GOOD, WARN, CRIT = "#14AD6E", "#C4870A", "#D6455C"
GRID = "#1F2E28"
INK = "#D8E6DF"
MUTED = "#7E9A90"
SURFACE = "#0A0F0D"

LVL_RANGE_HIGH = "#2B8CE8"
LVL_RANGE_LOW = "#C4870A"
LVL_SWING = "#A85CE8"


def _fmt(v: float) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}" if abs(v) >= 1 else f"{v:,.4f}"


def _dedupe_labels(marks: list[dict], min_gap: float = 10.5) -> list[dict]:
    """
    Nudge label baselines apart so text never overlaps.

    The target is by definition one of the previous-day levels, so the two sit
    at identical prices and their labels land on the same pixel. Coincident
    marks are merged into one line rather than stacked.
    """
    marks = sorted(marks, key=lambda m: m["y"])
    merged: list[dict] = []
    for m in marks:
        if merged and abs(m["y"] - merged[-1]["y"]) < 1.0:
            prev = merged[-1]
            a, b = prev["text"].rsplit(" ", 1), m["text"].rsplit(" ", 1)
            if len(a) == 2 and len(b) == 2 and a[1] == b[1]:
                prev["text"] = f"{a[0]} = {b[0]} {a[1]}"   # "TARGET = RANGE HI 69.72"
            elif m["text"] not in prev["text"]:
                prev["text"] = f'{prev["text"]} · {m["text"]}'
            prev["colour"] = m.get("priority_colour", prev["colour"])
            continue
        merged.append(dict(m))
    for i in range(1, len(merged)):
        if merged[i]["y"] - merged[i - 1]["y"] < min_gap:
            merged[i]["y"] = merged[i - 1]["y"] + min_gap
    return merged


def candle_setup_svg(row: dict, w: int = 340, h: int = 200) -> str:
    """
    Two panels sharing one price axis.

    LEFT  — the two candles, scaled to the candles themselves so wick and body
            shape stay legible. Wick length is the whole point: it is the stop.
    RIGHT — the trade ladder, scaled stop -> target, so the visual gap between
            the marks IS the risk/reward ratio.

    Splitting them is what keeps both readable. On one shared scale a 29% target
    squashes a 15-minute candle into a two-pixel sliver.
    """
    b1, lv = row["bar1"], row["levels"]
    tr = row.get("trade")

    pt, pb = 14, 22
    plot_h = h - pt - pb
    lx0, lx1 = 4, 132          # candle panel
    rx0 = 152                  # ladder panel

    # ── left panel scale: candles (+ range low, which they just broke) ──────
    pts = [b1["high"], b1["low"], lv["range_low"]]
    if tr:
        pts += [tr["bar2"]["high"], tr["bar2"]["low"]]
    clo, chi = min(pts), max(pts)
    cpad = (chi - clo) * 0.16 or 0.5
    clo, chi = clo - cpad, chi + cpad

    def cy(v: float) -> float:
        return pt + plot_h * (chi - v) / (chi - clo)

    out = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="Setup for {escape(row["symbol"])}: red opening candle, green sneaky candle, '
        f'and the stop-to-target ladder" '
        f'style="display:block;font-family:ui-monospace,monospace">'
    ]

    # range low reference inside the candle panel
    yrl = cy(lv["range_low"])
    out.append(
        f'<line x1="{lx0}" y1="{yrl:.1f}" x2="{lx1}" y2="{yrl:.1f}" stroke="{LVL_RANGE_LOW}" '
        f'stroke-width="1.4" stroke-dasharray="4 3" opacity=".95"/>'
        f'<text x="{lx0}" y="{yrl-4:.1f}" fill="{LVL_RANGE_LOW}" font-size="8">PREV RANGE LOW</text>'
    )

    cw = 26
    x1 = lx0 + 34
    x2 = x1 + cw + 34

    def candle(cx, o, hgh, lw, c, bear: bool):
        col = BEAR if bear else BULL
        out.append(
            f'<line x1="{cx}" y1="{cy(hgh):.1f}" x2="{cx}" y2="{cy(lw):.1f}" '
            f'stroke="{col}" stroke-width="1.8"/>'
        )
        top, bot = cy(max(o, c)), cy(min(o, c))
        out.append(
            f'<rect x="{cx-cw/2:.1f}" y="{top:.1f}" width="{cw}" height="{max(bot-top,2.5):.1f}" '
            f'fill="{col if bear else "none"}" stroke="{col}" stroke-width="2" rx="2"/>'
        )

    candle(x1, b1["open"], b1["high"], b1["low"], b1["close"], True)
    out.append(
        f'<text x="{x1}" y="{h-11}" fill="{BEAR}" font-size="8" text-anchor="middle">▼ 09:30</text>'
        f'<text x="{x1}" y="{h-3}" fill="{MUTED}" font-size="7.5" text-anchor="middle">RED</text>'
    )
    if tr:
        b2 = tr["bar2"]
        candle(x2, b2["open"], b2["high"], b2["low"], b2["close"], False)
        out.append(
            f'<text x="{x2}" y="{h-11}" fill="{BULL}" font-size="8" text-anchor="middle">▲ 09:45</text>'
            f'<text x="{x2}" y="{h-3}" fill="{MUTED}" font-size="7.5" text-anchor="middle">SNEAKY</text>'
        )

    # ── right panel: the trade ladder, stop -> target ───────────────────────
    if tr:
        rlo, rhi = tr["stop"], tr["target"]
        span = max(rhi - rlo, 1e-9)
        rpad = span * 0.10
        rlo_p, rhi_p = rlo - rpad, rhi + rpad

        def ry(v: float) -> float:
            return pt + plot_h * (rhi_p - v) / (rhi_p - rlo_p)

        y_stop, y_entry, y_tgt = ry(tr["stop"]), ry(tr["entry"]), ry(tr["target"])
        bar_x = rx0 + 6
        out.append(
            f'<rect x="{bar_x}" y="{y_entry:.1f}" width="9" height="{max(y_stop-y_entry,1):.1f}" '
            f'rx="2" fill="{CRIT}" opacity=".92"><title>risk</title></rect>'
            f'<rect x="{bar_x}" y="{y_tgt:.1f}" width="9" height="{max(y_entry-y_tgt-2,1):.1f}" '
            f'rx="2" fill="{GOOD}" opacity=".92"><title>reward</title></rect>'
        )

        marks = [
            {"y": y_tgt, "colour": GOOD,
             "text": f'TARGET {_fmt(tr["target"])}', "priority_colour": GOOD},
            {"y": y_entry, "colour": INK, "text": f'ENTRY {_fmt(tr["entry"])}'},
            {"y": y_stop, "colour": CRIT, "text": f'STOP {_fmt(tr["stop"])}'},
        ]
        for val, col, txt in (
            (lv["range_high"], LVL_RANGE_HIGH, f'RANGE HI {_fmt(lv["range_high"])}'),
            (lv["range_low"], LVL_RANGE_LOW, f'RANGE LO {_fmt(lv["range_low"])}'),
            (lv.get("swing_low"), LVL_SWING,
             f'SWING LO {_fmt(lv.get("swing_low"))}' if lv.get("swing_low") else None),
        ):
            if val is None or txt is None:
                continue
            if rlo_p <= val <= rhi_p:
                marks.append({"y": ry(val), "colour": col, "text": txt})

        for m in _dedupe_labels(marks):
            out.append(
                f'<line x1="{bar_x+9}" y1="{m["y"]:.1f}" x2="{bar_x+16}" y2="{m["y"]:.1f}" '
                f'stroke="{m["colour"]}" stroke-width="1"/>'
                f'<text x="{bar_x+19}" y="{m["y"]+3:.1f}" fill="{m["colour"]}" font-size="8.5">'
                f'{escape(m["text"])}</text>'
            )
        out.append(
            f'<text x="{rx0+6}" y="{h-3}" fill="{MUTED}" font-size="7.5">'
            f'LADDER · {tr["rr"]:.2f}R</text>'
        )

    out.append("</svg>")
    return "".join(out)


def rr_bar_svg(trade: dict, w: int = 170, h: int = 26) -> str:
    """Risk vs reward as one proportional bar. Risk left, reward right."""
    risk = max(trade["risk_pct"] or 0, 0.001)
    rew = max(trade["reward_pct"] or 0, 0)
    total = risk + rew
    rw = w * (risk / total)
    gap = 2
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="Risk {risk:.2f} percent versus reward {rew:.2f} percent" '
        f'style="display:block">'
        f'<rect x="0" y="6" width="{rw:.1f}" height="12" rx="3" fill="{CRIT}"/>'
        f'<rect x="{rw+gap:.1f}" y="6" width="{max(w-rw-gap,0):.1f}" height="12" rx="3" fill="{GOOD}"/>'
        f'<text x="2" y="{h-1}" font-size="8" fill="{MUTED}" font-family="ui-monospace,monospace">'
        f'-{risk:.2f}%</text>'
        f'<text x="{w-2}" y="{h-1}" font-size="8" fill="{MUTED}" text-anchor="end" '
        f'font-family="ui-monospace,monospace">+{rew:.2f}%</text>'
        f"</svg>"
    )


def funnel_svg(steps: list[tuple[str, int]], w: int = 560, h: int = 150) -> str:
    """How the whole market narrowed to today's list. Horizontal bars, log-ish."""
    if not steps:
        return ""
    mx = max(v for _, v in steps) or 1
    rowh = h / len(steps)
    bar_h = min(rowh - 10, 20)
    lab_w = 150
    out = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Scan funnel" '
        f'style="display:block;font-family:ui-monospace,monospace">'
    ]
    for i, (label, val) in enumerate(steps):
        yy = i * rowh + (rowh - bar_h) / 2
        bw = max((w - lab_w - 60) * (val / mx), 2)
        # One measure across stages, so one hue stepping darker — four
        # categorical hues would imply four different entities.
        op = 1.0 - 0.17 * i
        out.append(
            f'<text x="0" y="{yy+bar_h*0.75:.1f}" fill="{MUTED}" font-size="10">{escape(label)}</text>'
            f'<rect x="{lab_w}" y="{yy:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" rx="3" '
            f'fill="{CAT[0]}" opacity="{op:.2f}"/>'
            f'<text x="{lab_w+bw+7:.1f}" y="{yy+bar_h*0.75:.1f}" fill="{INK}" font-size="11" '
            f'font-weight="600">{val:,}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def rr_hist_svg(values: list[float], w: int = 560, h: int = 130, bins: int = 14) -> str:
    """Distribution of confirmed R:R ratios — shows where today's edge sits."""
    vals = [v for v in values if v is not None and v > 0]
    if not vals:
        return ""
    top = min(max(vals), 12.0)
    edges = [top * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for v in vals:
        k = min(int(v / top * bins), bins - 1) if top else 0
        counts[k] += 1
    mx = max(counts) or 1
    pl, pb = 6, 20
    bw = (w - pl * 2) / bins
    out = [
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="Distribution of risk reward ratios" '
        f'style="display:block;font-family:ui-monospace,monospace">'
    ]
    for i, c in enumerate(counts):
        bh = (h - pb - 8) * (c / mx)
        x = pl + i * bw
        out.append(
            f'<rect x="{x+1:.1f}" y="{h-pb-bh:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" '
            f'rx="3" fill="{CAT[0]}" opacity="{0.45 + 0.55*(c/mx):.2f}">'
            f"<title>{c} setups between {edges[i]:.1f} and {edges[i+1]:.1f} R:R</title></rect>"
        )
    for frac in (0, 0.5, 1.0):
        x = pl + (w - pl * 2) * frac
        out.append(
            f'<text x="{x:.1f}" y="{h-6}" fill="{MUTED}" font-size="9" '
            f'text-anchor="{"start" if frac==0 else "middle" if frac==0.5 else "end"}">'
            f"{top*frac:.1f}R</text>"
        )
    out.append("</svg>")
    return "".join(out)
