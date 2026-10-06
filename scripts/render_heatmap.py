#!/usr/bin/env python3
"""
Render data/contributions.json as an animated contribution graph inside a
terminal window: a scan line sweeps left -> right, cells pop in behind it, and
today's cell keeps a blinking cursor ring. CSS animations only -- GitHub runs
CSS/SMIL inside <img> SVGs but never JS.

    python scripts/render_heatmap.py
"""
import datetime

from term import CYAN, GLOW, INK, LEVELS, MUTED, TITLEBAR_H, load_data, svg_open, window, write_svg

CELL, GAP = 13, 3
STEP = CELL + GAP
PAD = 22
LABEL_W = 34
MONTH_H = 22
FOOTER_H = 40

REVEAL = 2.8  # seconds for the sweep to cross the grid
POP = 0.5
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

data = load_data()
days = data["days"]
first = datetime.date.fromisoformat(days[0]["date"])
week0 = first - datetime.timedelta(days=(first.weekday() + 1) % 7)  # Sunday on/before the first day


def slot(date_str):
    d = datetime.date.fromisoformat(date_str)
    return (d - week0).days // 7, (d.weekday() + 1) % 7  # (column, row) with Sunday as row 0


n_weeks = slot(days[-1]["date"])[0] + 1
grid_x = PAD + LABEL_W
grid_y = TITLEBAR_H + PAD + MONTH_H
grid_w = n_weeks * STEP - GAP
grid_h = 7 * STEP - GAP
W = grid_x + grid_w + PAD
H = grid_y + grid_h + FOOTER_H + PAD - 6

style = (
    f".c{{transform-box:fill-box;transform-origin:center;opacity:0;animation:pop {POP}s ease-out both}}"
    f".on{{animation:pop {POP}s ease-out both,flash {POP + 0.3}s ease-out both}}"
    "@keyframes pop{0%{opacity:0;transform:scale(.2)}60%{opacity:1;transform:scale(1.15)}100%{opacity:1;transform:scale(1)}}"
    "@keyframes flash{0%,40%{filter:brightness(2.2)}100%{filter:brightness(1)}}"
    f".scan{{opacity:0;animation:scan {REVEAL + POP}s linear both}}"
    f"@keyframes scan{{0%{{opacity:0;transform:translateX(0)}}6%,90%{{opacity:1}}"
    f"100%{{opacity:0;transform:translateX({grid_w + 24}px)}}}}"
    f".ring{{opacity:0;animation:blink 1.1s steps(1) {REVEAL + POP}s infinite}}"
    "@keyframes blink{0%{opacity:1}50%{opacity:0}}"
    ".fade{opacity:0;animation:fade .8s ease-out both}"
    "@keyframes fade{to{opacity:1}}"
    "@media (prefers-reduced-motion:reduce){.c,.fade{opacity:1!important;animation:none!important}"
    ".scan{display:none}.ring{opacity:1;animation:none}}"
)

parts = [svg_open(W, H, style), window(W, H, "./contributions.sh")]

# month + weekday labels
last_month = None
for col in range(n_weeks):
    month_days = [week0 + datetime.timedelta(days=col * 7 + r) for r in range(7)]
    firsts = [d for d in month_days if d.day == 1 and d >= first]
    label = firsts[0].month if firsts else (month_days[-1].month if col == 0 else None)
    if label and label != last_month and col <= n_weeks - 2:
        last_month = label
        parts.append(f'<text x="{grid_x + col * STEP}" y="{grid_y - 9}" fill="{MUTED}" font-size="12">{MONTHS[label - 1]}</text>')
for name, row in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
    parts.append(f'<text x="{PAD}" y="{grid_y + row * STEP + CELL - 2}" fill="{MUTED}" font-size="12">{name}</text>')

# cells
for d in days:
    col, row = slot(d["date"])
    x, y = grid_x + col * STEP, grid_y + row * STEP
    delay = (col + row * 0.35) / (n_weeks + 2.1) * REVEAL
    cls = "c on" if d["level"] else "c"
    parts.append(
        f'<rect class="{cls}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" '
        f'fill="{LEVELS[d["level"]]}" style="animation-delay:{delay:.2f}s"/>'
    )

# scan line riding the reveal edge
parts.append(
    '<defs><linearGradient id="scan" x1="0" y1="0" x2="1" y2="0">'
    f'<stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
    f'<stop offset="0.8" stop-color="{CYAN}" stop-opacity="0.35"/>'
    f'<stop offset="1" stop-color="{GLOW}" stop-opacity="0.9"/></linearGradient></defs>'
    f'<rect class="scan" x="{grid_x - 26}" y="{grid_y - 4}" width="26" height="{grid_h + 8}" fill="url(#scan)"/>'
)

# blinking cursor ring on the latest day
col, row = slot(days[-1]["date"])
parts.append(
    f'<rect class="ring" x="{grid_x + col * STEP - 1.5}" y="{grid_y + row * STEP - 1.5}" '
    f'width="{CELL + 3}" height="{CELL + 3}" rx="3.5" fill="none" stroke="{CYAN}" stroke-width="1.5"/>'
)

# footer: total on the left, legend on the right
foot_y = grid_y + grid_h + 30
parts.append(
    f'<g class="fade" style="animation-delay:{REVEAL * 0.6:.2f}s">'
    f'<text x="{grid_x}" y="{foot_y}" fill="{INK}" font-size="15" font-weight="700">'
    f'{data["total_contributions"]:,}<tspan fill="{MUTED}" font-weight="400"> contributions in the last year</tspan></text>'
)
lx = grid_x + grid_w - 36 - (5 * STEP - GAP)  # leaves room for "more"
parts.append(f'<text x="{lx - 8}" y="{foot_y}" fill="{MUTED}" font-size="12" text-anchor="end">less</text>')
for i, color in enumerate(LEVELS):
    parts.append(f'<rect x="{lx + i * STEP}" y="{foot_y - 11}" width="{CELL}" height="{CELL}" rx="2.5" fill="{color}"/>')
parts.append(f'<text x="{grid_x + grid_w}" y="{foot_y}" fill="{MUTED}" font-size="12" text-anchor="end">more</text></g>')

parts.append("</svg>")
write_svg("contrib-heatmap.svg", "".join(parts))
