"""
Shared palette + terminal-window chrome for every SVG on the profile, so the
contribution graph, the portrait and the stats card read as one set.

The palette follows the profile photo (blue LED rain) instead of GitHub green.
"""
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_PATH = os.path.join(ROOT, "data", "contributions.json")
ASSETS = os.path.join(ROOT, "assets")

USER = os.environ.get("GH_PROFILE_USER", "lingmulongtai")
PROMPT = "ryuta@github"
DISPLAY_NAME = "Ryuta Suzuki"

FONT = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

BG_TOP = "#0f172a"
BG_BOTTOM = "#0a0f1e"
FRAME = "#1e293b"
PANEL = "#0f1a30"
PANEL_EDGE = "#22304a"
MUTED = "#8492a6"
INK = "#e2e8f0"
CYAN = "#38bdf8"
BLUE = "#3b82f6"
VIOLET = "#a78bfa"
GLOW = "#e0f2fe"

# contribution levels 0..4
LEVELS = ["#1a2338", "#1d3f9a", "#2563eb", "#4f9dff", "#93e0ff"]

TITLEBAR_H = 32


def load_data():
    with open(DATA_PATH) as f:
        return json.load(f)


def svg_open(w, h, style=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
        f'viewBox="0 0 {w:g} {h:g}" font-family="{FONT}">'
        + (f"<style>{style}</style>" if style else "")
    )


def bar_height(scale=1.0):
    return round(TITLEBAR_H * scale)


def window(w, h, title, right="", scale=1.0):
    """Rounded dark window with traffic lights and a centered title.

    `scale` enlarges the chrome for cards that are shown at half size in the
    README, so their title bars stay readable.
    """
    bar = bar_height(scale)
    fs = 13 * scale
    parts = [
        '<defs><linearGradient id="winbg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{BG_TOP}"/><stop offset="1" stop-color="{BG_BOTTOM}"/>'
        "</linearGradient></defs>",
        f'<rect width="{w:g}" height="{h:g}" rx="{12 * scale:g}" fill="url(#winbg)"/>',
        f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{12 * scale:g}" fill="none" stroke="{FRAME}"/>',
        f'<line x1="0" y1="{bar}" x2="{w:g}" y2="{bar}" stroke="{FRAME}"/>',
    ]
    for i, dot in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(f'<circle cx="{(20 + i * 17) * scale:g}" cy="{bar / 2:g}" r="{5.5 * scale:g}" fill="{dot}"/>')
    parts.append(
        f'<text x="{w / 2:g}" y="{bar / 2 + fs * 0.35:g}" fill="{MUTED}" font-size="{fs:g}" '
        f'text-anchor="middle">{PROMPT}: ~$ {title}</text>'
    )
    if right:
        parts.append(
            f'<text x="{w - 18 * scale:g}" y="{bar / 2 + fs * 0.35:g}" fill="{MUTED}" font-size="{fs * 0.9:g}" '
            f'text-anchor="end" opacity="0.75">{right}</text>'
        )
    return "".join(parts)


def write_svg(name, svg):
    os.makedirs(ASSETS, exist_ok=True)
    path = os.path.join(ASSETS, name)
    with open(path, "w") as f:
        f.write(svg)
    print(f"wrote assets/{name} ({len(svg) // 1024} KB)")
