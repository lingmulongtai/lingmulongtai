#!/usr/bin/env python3
"""
Turn the profile photo into an ASCII-art SVG that "rains" in column by column,
then holds. Bright pixels become dense glyphs, so the LED wall in the photo
turns into a field of characters and the silhouette stays a clean void.

Brightness is the HSV value channel rather than luminance: the photo is mostly
saturated blue, which plain luminance would crush to near-black.

Not part of the daily workflow -- rerun by hand when the avatar changes:

    pip install -r scripts/requirements.txt
    python scripts/render_portrait.py [photo.jpg]   # defaults to the GitHub avatar
"""
import html
import io
import random
import sys
import urllib.request

from PIL import Image, ImageOps

from term import (CYAN, DISPLAY_NAME, GLOW, INK, MUTED, PROMPT, USER, VIOLET, FRAME, bar_height,
                  svg_open, window, write_svg)

W, H = 840, 880          # == assets/stats.svg, so the pair lines up in the README
SCALE = 1.6
PAD = 20
STATUS_H = 52
COLS = 150
RAMP = " .:-=+*#%@"      # sparse -> dense; bright pixels get dense glyphs
FLOOR = 0.16             # values below this become blank (the silhouette)
GAMMA = 0.9

ART_W = W - 2 * PAD
ART_TOP = bar_height(SCALE) + 14
CELL_W = ART_W / COLS
CELL_H = CELL_W * 1.8
ROWS = int((H - STATUS_H - 10 - ART_TOP) / CELL_H)
ART_H = ROWS * CELL_H

RAIN_START = (0.0, 2.0)  # seconds: random start window per column
RAIN_DUR = (1.3, 2.4)    # seconds: random fall time per column


def load_photo():
    if len(sys.argv) > 1:
        return Image.open(sys.argv[1])
    url = f"https://avatars.githubusercontent.com/{USER}?s=460"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return Image.open(io.BytesIO(resp.read()))


def to_rows(im):
    v = im.convert("RGB").convert("HSV").getchannel("V")
    # crop to the art's aspect, keeping the bottom (where the figure stands)
    target = ART_W / ART_H
    w, h = v.size
    if w / h < target:
        new_h = round(w / target)
        v = v.crop((0, h - new_h, w, h))
    else:
        new_w = round(h * target)
        v = v.crop(((w - new_w) // 2, 0, (w - new_w) // 2 + new_w, h))
    v = ImageOps.autocontrast(v, cutoff=1).resize((COLS, ROWS), Image.BOX)
    px = v.load()
    rows = []
    for y in range(ROWS):
        line = []
        for x in range(COLS):
            lum = (px[x, y] / 255) ** GAMMA
            line.append(" " if lum < FLOOR else RAMP[min(len(RAMP) - 1, int(lum * len(RAMP)))])
        rows.append("".join(line))
    return rows


rows = to_rows(load_photo())
rng = random.Random(USER)
bottom = ART_TOP + ART_H

parts = [
    svg_open(W, H, "@keyframes blink{50%{fill-opacity:0}}.cur{animation:blink 1s steps(1) infinite}"),
    window(W, H, "./portrait.sh", scale=SCALE),
    f'<defs><linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="{PAD}" y1="{ART_TOP}" '
    f'x2="{PAD + ART_W}" y2="{bottom}">'
    f'<stop offset="0" stop-color="#7dd3fc"/><stop offset="0.55" stop-color="#60a5fa"/>'
    f'<stop offset="1" stop-color="{VIOLET}"/></linearGradient>',
]

# one clip strip per column; each falls at its own pace
timings = [(rng.uniform(*RAIN_START), rng.uniform(*RAIN_DUR)) for _ in range(COLS)]
parts.append('<clipPath id="rain">')
for c, (begin, dur) in enumerate(timings):
    parts.append(
        f'<rect x="{PAD + c * CELL_W:.2f}" y="{ART_TOP:.1f}" width="{CELL_W + 0.4:.2f}" height="0">'
        f'<animate attributeName="height" to="{ART_H:.1f}" begin="{begin:.2f}s" dur="{dur:.2f}s" fill="freeze"/></rect>'
    )
parts.append("</clipPath></defs>")

font = CELL_W / 0.6
parts.append(f'<g clip-path="url(#rain)" fill="url(#ink)" font-size="{font:.2f}">')
for r, line in enumerate(rows):
    if not line.strip():
        continue
    y = ART_TOP + r * CELL_H + CELL_H * 0.78
    parts.append(
        f'<text xml:space="preserve" x="{PAD}" y="{y:.1f}" textLength="{ART_W}" '
        f'lengthAdjust="spacing">{html.escape(line)}</text>'
    )
parts.append("</g>")

# bright "drop" riding the leading edge of each column, gone once it lands
parts.append(f'<g fill="{GLOW}">')
for c, (begin, dur) in enumerate(timings):
    parts.append(
        f'<rect x="{PAD + c * CELL_W:.2f}" y="{ART_TOP - CELL_H:.1f}" width="{CELL_W:.2f}" height="{CELL_H:.1f}" opacity="0">'
        f'<animate attributeName="y" to="{bottom - CELL_H:.1f}" begin="{begin:.2f}s" dur="{dur:.2f}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0.9" begin="{begin:.2f}s"/>'
        f'<set attributeName="opacity" to="0" begin="{begin + dur:.2f}s"/></rect>'
    )
parts.append("</g>")

# status bar: whoami + blinking block cursor
line_y = H - STATUS_H
fs = 13 * SCALE
parts.append(f'<line x1="0" y1="{line_y}" x2="{W}" y2="{line_y}" stroke="{FRAME}"/>')
parts.append(
    f'<text x="{PAD}" y="{line_y + STATUS_H / 2 + fs * 0.35:.1f}" font-size="{fs:g}" fill="{MUTED}">'
    f'<tspan fill="{CYAN}">{PROMPT}</tspan>:~$ whoami <tspan fill="{INK}">{DISPLAY_NAME}</tspan> '
    f'<tspan class="cur" fill="{INK}">█</tspan></text>'
)

parts.append("</svg>")
write_svg("ascii-portrait.svg", "".join(parts))
