#!/usr/bin/env python3
"""
Render the stats card from data/contributions.json: six tiles that slide in and
count up to the real numbers, then a monthly bar chart that grows underneath.

The canvas matches assets/ascii-portrait.svg (840 x 880) so the two sit side by
side at equal height in the README, where each is shown at half width -- font
sizes here are chosen for that ~0.5x display.

Count-up is a stack of pre-rendered frames switched with SMIL <set>: GitHub runs
SMIL/CSS inside <img> SVGs but not JS.

    python scripts/render_stats.py
"""
import datetime
import html
import random

from term import (BLUE, CYAN, INK, MUTED, PANEL, PANEL_EDGE, VIOLET, bar_height, load_data,
                  svg_open, window, write_svg)

W, H = 840, 880
SCALE = 1.6
PAD = 20
GAP = 16
COLS, ROWS = 2, 3
TILE_W = (W - 2 * PAD - GAP) / COLS
TILE_H = 146
TILES_TOP = bar_height(SCALE) + PAD
CHART_TOP = TILES_TOP + ROWS * TILE_H + (ROWS - 1) * GAP + GAP

STAGGER = 0.14
SLIDE = 0.45
COUNT = 1.3
FRAMES = 18
BARS_AT = STAGGER * COLS * ROWS + 0.5
BAR_STAGGER = 0.07
BAR_DUR = 0.6
GLYPHS = "#%&*+=<>/\\|01"


def short(d):
    d = datetime.date.fromisoformat(d)
    return f"{d:%b} {d.day}"


def span(s):
    return f'{short(s["start"])} – {short(s["end"])}' if s["length"] else "next commit starts one"


def compact(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


data = load_data()
cur, lng, best, wd = data["current_streak"], data["longest_streak"], data["best_day"], data["busiest_weekday"]
n_days = len(data["days"])
updated = "updated " + short(data["generated_at"][:10])

# (label, value, suffix, caption, color)
tiles = [
    ("contributions", data["total_contributions"], "", "in the last year", CYAN),
    ("best day", best["count"], "", short(best["date"]), INK),
    ("longest streak", lng["length"], " days", span(lng), INK),
    ("current streak", cur["length"], " days", span(cur), INK),
    ("active days", data["active_days"], f" / {n_days}", f'{data["active_days"] / n_days:.0%} of the year', INK),
    ("busiest weekday", wd["name"], "", f'avg {wd["avg"]:g} / day', VIOLET),
]


def frame_text(k, value):
    """Text shown in count-up frame k of FRAMES."""
    p = k / FRAMES
    if isinstance(value, str):  # decode effect: letters lock in left to right
        rng = random.Random(f"{value}{k}")
        locked = int(len(value) * p)
        return html.escape(value[:locked] + "".join(rng.choice(GLYPHS) for _ in value[locked:]))
    v = value * (1 - (1 - p) ** 3)  # ease-out into the real number
    return f"{int(round(v)):,}"


style = (
    f".t{{opacity:0;animation:in {SLIDE}s ease-out both}}"
    "@keyframes in{0%{opacity:0;transform:translateY(14px)}100%{opacity:1;transform:translateY(0)}}"
    f".b{{transform-box:fill-box;transform-origin:bottom;transform:scaleY(0);animation:grow {BAR_DUR}s ease-out both}}"
    "@keyframes grow{to{transform:scaleY(1)}}"
    "@media (prefers-reduced-motion:reduce){.t,.b{opacity:1!important;transform:none!important;animation:none!important}}"
)
parts = [
    svg_open(W, H, style),
    window(W, H, "./stats.sh", right=updated, scale=SCALE),
    '<defs><linearGradient id="peak" x1="0" y1="1" x2="0" y2="0">'
    f'<stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CYAN}"/></linearGradient></defs>',
]

# ---- tiles -----------------------------------------------------------------
for i, (label, value, suffix, caption, color) in enumerate(tiles):
    x = PAD + (i % COLS) * (TILE_W + GAP)
    y = TILES_TOP + (i // COLS) * (TILE_H + GAP)
    start = i * STAGGER
    count_at = start + SLIDE * 0.6
    parts.append(f'<g class="t" style="animation-delay:{start:.2f}s">')
    parts.append(f'<rect x="{x:.1f}" y="{y}" width="{TILE_W:.1f}" height="{TILE_H}" rx="10" fill="{PANEL}" stroke="{PANEL_EDGE}"/>')
    parts.append(f'<text x="{x + 24:.1f}" y="{y + 40}" fill="{MUTED}" font-size="22">$ {label}</text>')
    for k in range(1, FRAMES + 1):
        anim = f'<set attributeName="opacity" to="1" begin="{count_at + COUNT * (k - 1) / FRAMES:.3f}s"/>'
        if k < FRAMES:
            anim += f'<set attributeName="opacity" to="0" begin="{count_at + COUNT * k / FRAMES:.3f}s"/>'
        parts.append(
            f'<text x="{x + 24:.1f}" y="{y + 98}" opacity="0" font-size="52" font-weight="700" fill="{color}">'
            f'{frame_text(k, value)}<tspan font-size="24" font-weight="400" fill="{MUTED}">{suffix}</tspan>{anim}</text>'
        )
    parts.append(f'<text x="{x + 24:.1f}" y="{y + 130}" fill="{MUTED}" font-size="20">{caption}</text>')
    parts.append("</g>")

# ---- monthly bars ----------------------------------------------------------
monthly = data["monthly"]
cx, cw, ch = PAD, W - 2 * PAD, H - PAD - CHART_TOP
parts.append(f'<g class="t" style="animation-delay:{BARS_AT - 0.3:.2f}s">')
parts.append(f'<rect x="{cx}" y="{CHART_TOP}" width="{cw}" height="{ch}" rx="10" fill="{PANEL}" stroke="{PANEL_EDGE}"/>')
parts.append(f'<text x="{cx + 24}" y="{CHART_TOP + 40}" fill="{MUTED}" font-size="22">$ contributions / month</text>')
parts.append("</g>")

plot_top, plot_bot = CHART_TOP + 92, CHART_TOP + ch - 44
plot_l, plot_r = cx + 24, cx + cw - 24
slot = (plot_r - plot_l) / len(monthly)
bar_w = slot * 0.6
peak = max(m["total"] for m in monthly) or 1
for i, m in enumerate(monthly):
    h = max(3, (plot_bot - plot_top) * m["total"] / peak)
    bx = plot_l + i * slot + (slot - bar_w) / 2
    mid = bx + bar_w / 2
    delay = BARS_AT + i * BAR_STAGGER
    fill = "url(#peak)" if m["total"] == peak else BLUE
    parts.append(
        f'<rect class="b" x="{bx:.1f}" y="{plot_bot - h:.1f}" width="{bar_w:.1f}" height="{h:.1f}" rx="3" '
        f'fill="{fill}" style="animation-delay:{delay:.2f}s"/>'
    )
    parts.append(
        f'<text class="t" style="animation-delay:{delay + BAR_DUR:.2f}s" x="{mid:.1f}" y="{plot_bot - h - 10:.1f}" '
        f'fill="{INK if m["total"] == peak else MUTED}" font-size="17" text-anchor="middle">{compact(m["total"])}</text>'
    )
    month = datetime.date.fromisoformat(m["month"] + "-01").strftime("%b")[0]
    parts.append(
        f'<text class="t" style="animation-delay:{BARS_AT - 0.3:.2f}s" x="{mid:.1f}" y="{plot_bot + 30}" '
        f'fill="{MUTED}" font-size="18" text-anchor="middle">{month}</text>'
    )

parts.append("</svg>")
write_svg("stats.svg", "".join(parts))
