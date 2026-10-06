#!/usr/bin/env python3
"""
Render the achievements panel: GitHub badges (earned ones glow, locked ones show
a lock) with a progress bar toward the next tier, a progress summary, and a row
of local achievements computed from data/contributions.json.

Reads data/achievements.json (fetch_achievements.py) and data/contributions.json.

    python scripts/render_achievements.py
"""
import datetime
import html
import json
import math
import os

from term import (BLUE, CYAN, INK, MUTED, PANEL, PANEL_EDGE, ROOT, TITLEBAR_H, load_data,
                  svg_open, window, write_svg)

W = 920
PAD = 22
GAP = 14
COLS = 4
CARD_W = (W - 2 * PAD - (COLS - 1) * GAP) / COLS
CARD_H = 144
LABEL_H = 30
MEDAL_R = 22
TEXT_CHARS = 25  # what fits on one card line at the progress font size

# tier index -> (label, light, dark)
TIER_STYLE = {
    1: ("UNLOCKED", "#7dd3fc", "#2563eb"),
    2: ("BRONZE x2", "#f6c08e", "#b4642a"),
    3: ("SILVER x3", "#f1f5f9", "#8a99ad"),
    4: ("GOLD x4", "#fde68a", "#e0950b"),
}
LOCKED = "#475569"

ICONS = {
    "fin": '<path d="M4 17C8 15 11 10 12.5 3C15 8 18.5 13 21 17Z"/>'
           '<path d="M2 20.5q2.5-2 5 0t5 0t5 0t5 0" fill="none" stroke="currentColor" stroke-width="1.8"/>',
    "star": '<polygon points="12,2 14.9,8.6 22,9.3 16.6,14 18.2,21 12,17.3 5.8,21 7.4,14 2,9.3 9.1,8.6"/>',
    "pair": '<circle cx="8.5" cy="8" r="3.2"/><circle cx="15.5" cy="8" r="3.2"/>'
            '<path d="M2.5 20c0-4 2.7-6.5 6-6.5s6 2.5 6 6.5z"/><path d="M9.5 20c0-4 2.7-6.5 6-6.5s6 2.5 6 6.5z"/>',
    "galaxy": '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)" fill="none" '
              'stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="3.2"/><circle cx="19.3" cy="6.6" r="1.5"/>',
    "bolt": '<polygon points="13,2 4,14 11,14 10,22 20,9.5 13,9.5"/>',
    "rocket": '<path d="M12 2c3.5 2.5 5 6.5 5 10.5l-2 3.5H9l-2-3.5C7 8.5 8.5 4.5 12 2z"/>'
              '<polygon points="9.5,17 12,22 14.5,17"/><polygon points="7,12.5 4,17.5 7.8,16"/>'
              '<polygon points="17,12.5 20,17.5 16.2,16"/>',
    "heart": '<path d="M12 21l-1.4-1.3C5.4 15 2 11.9 2 8.2 2 5.1 4.4 2.8 7.5 2.8c1.7 0 3.4.8 4.5 2.1 '
             '1.1-1.3 2.8-2.1 4.5-2.1 3.1 0 5.5 2.3 5.5 5.4 0 3.7-3.4 6.8-8.6 11.5z"/>',
    "burst": "<polygon points=\"{}\"/>".format(" ".join(
        f"{12 + (10.5 if i % 2 == 0 else 4.8) * math.cos(math.pi * i / 8 - math.pi / 2):.2f},"
        f"{12 + (10.5 if i % 2 == 0 else 4.8) * math.sin(math.pi * i / 8 - math.pi / 2):.2f}"
        for i in range(16))),
    "flame": '<path d="M12 2.5c.8 3.6 5.5 5.6 5.5 11a5.5 5.5 0 0 1-11 0c0-2.8 1.6-4.6 2.8-5.6 0 1.8.8 3 2 3.2-.6-3.2.2-6 .7-8.6z"/>',
    "bars": '<rect x="3" y="13" width="4.5" height="8" rx="1"/><rect x="9.75" y="8" width="4.5" height="13" rx="1"/>'
            '<rect x="16.5" y="3" width="4.5" height="18" rx="1"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="16.5" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/>'
                '<rect x="3" y="4.5" width="18" height="4.5" rx="1.5"/>'
                + "".join(f'<rect x="{x}" y="{y}" width="3" height="3" rx=".6"/>' for y in (11.5, 15.5) for x in (6, 10.5, 15)),
    "unknown": '<text x="12" y="17.5" font-size="15" font-weight="700" text-anchor="middle">?</text>',
}

# slug -> (name, icon, unit, hint shown while a single-tier badge is locked)
GITHUB = {
    "pull-shark": ("Pull Shark", "fin", "merged PRs", None),
    "starstruck": ("Starstruck", "star", "★", None),
    "pair-extraordinaire": ("Pair Extraordinaire", "pair", "co-authored PRs", None),
    "galaxy-brain": ("Galaxy Brain", "galaxy", "accepted answers", None),
    "quickdraw": ("Quickdraw", "bolt", None, "close an issue in < 5 min"),
    "yolo": ("YOLO", "rocket", None, "merge a PR without review"),
    "public-sponsor": ("Public Sponsor", "heart", None, "sponsor someone on GitHub"),
}
TIERS = {
    "pull-shark": [2, 16, 128, 1024],
    "starstruck": [16, 128, 512, 4096],
    "pair-extraordinaire": [1, 10, 24, 48],
    "galaxy-brain": [2, 8, 16, 32],
}


def tier_of(value, tiers):
    return sum(1 for t in tiers if value >= t)


def progress(tier, value, tiers, unit):
    """(bar ratio 0..1, progress text) toward the next tier."""
    if not tiers:  # single-tier badge
        return (1.0, "unlocked") if tier else (0.0, None)
    if tier >= len(tiers):
        shown = f"{value:,}" if value is not None else f"{tiers[-1]:,}+"
        return 1.0, f"{shown} {unit} · MAX"
    nxt = tiers[tier]
    if value is None:
        floor = tiers[tier - 1] if tier else 0
        return floor / nxt, f"{floor:,}{'+' if tier else ''} / {nxt:,} {unit}"
    if value >= nxt:  # threshold met, GitHub hasn't awarded it yet
        return 1.0, f"{value:,} / {nxt:,} · {'x' + str(tier + 1) if tier else 'unlock'} pending"
    return value / nxt, f"{value:,} / {nxt:,} {unit}"


def clip(text):
    return text if len(text) <= TEXT_CHARS else text[:TEXT_CHARS - 1] + "…"


# ---- assemble the card list --------------------------------------------------
contrib = load_data()
with open(os.path.join(ROOT, "data", "achievements.json")) as f:
    ach = json.load(f)

github_cards = []
for slug, state in ach["badges"].items():
    name, icon, unit, hint = GITHUB.get(slug, (slug.replace("-", " ").title(), "unknown", None, None))
    tiers = TIERS.get(slug, [])
    value, tier = state.get("value"), state.get("tier", 0)
    if value is not None and tiers and tier and value < tiers[min(tier, len(tiers)) - 1]:
        value = None  # API sees less than the badge proves (e.g. private repos): show "16+"
    if slug == "starstruck" and state.get("repo"):
        unit = f"★ {state['repo']}"
    ratio, text = progress(tier, value, tiers, unit)
    github_cards.append({"name": name, "icon": icon, "tier": min(tier, 4), "ratio": ratio,
                         "text": text or hint or "", "group": "github", "max_tier": len(tiers) or 1})
for slug, (name, icon, unit, hint) in GITHUB.items():  # catalog badges missing from the data file
    if slug not in ach["badges"]:
        github_cards.append({"name": name, "icon": icon, "tier": 0, "ratio": 0.0,
                             "text": hint or f"? / {TIERS[slug][0]} {unit}", "group": "github",
                             "max_tier": len(TIERS.get(slug, [])) or 1})
# earned first (highest tier first), then locked by how close they are
github_cards.sort(key=lambda c: (c["tier"] == 0, -c["tier"], -c["ratio"]))

local_defs = [
    ("Big Bang", "burst", contrib["best_day"]["count"], [50, 200, 500, 1000], "in one day"),
    ("Streak Runner", "flame", contrib["longest_streak"]["length"], [7, 14, 30, 100], "day streak"),
    ("Year in Code", "bars", contrib["total_contributions"], [500, 1000, 2500, 5000], "contribs"),
    ("Daily Driver", "calendar", contrib["active_days"], [50, 100, 200, 300], "active days"),
]
local_cards = []
for name, icon, value, tiers, unit in local_defs:
    tier = tier_of(value, tiers)
    ratio, text = progress(tier, value, tiers, unit)
    local_cards.append({"name": name, "icon": icon, "tier": tier, "ratio": ratio, "text": text,
                        "group": "local", "max_tier": len(tiers), "value": value, "tiers": tiers, "unit": unit})

# closest next tier across everything with a number behind it
candidates = [c for c in github_cards + local_cards if 0 < c["ratio"] < 1]
closest = max(candidates, key=lambda c: c["ratio"], default=None)
gh_unlocked = sum(1 for c in github_cards if c["tier"])
local_unlocked = sum(1 for c in local_cards if c["tier"])

# ---- layout ------------------------------------------------------------------
gh_rows = math.ceil((len(github_cards) + 1) / COLS)  # +1 slot for the summary card
local_rows = math.ceil(len(local_cards) / COLS)
top = TITLEBAR_H + 16
gh_top = top + LABEL_H
local_label = gh_top + gh_rows * (CARD_H + GAP) + 4
local_top = local_label + LABEL_H
H = local_top + local_rows * (CARD_H + GAP) - GAP + PAD


def slot_xy(i, y0):
    return PAD + (i % COLS) * (CARD_W + GAP), y0 + (i // COLS) * (CARD_H + GAP)


style = (
    ".t{opacity:0;animation:in .5s ease-out both}"
    "@keyframes in{0%{opacity:0;transform:translateY(12px)}100%{opacity:1;transform:translateY(0)}}"
    ".bar{transform-box:fill-box;transform-origin:left;transform:scaleX(0);animation:fill 1s ease-out both}"
    "@keyframes fill{to{transform:scaleX(1)}}"
    ".glow{animation:pulse 3.2s ease-in-out infinite}"
    "@keyframes pulse{0%,100%{opacity:.25}50%{opacity:.6}}"
    ".sh{animation:shine 6s ease-in-out infinite}"
    "@keyframes shine{0%{transform:translateX(-56px)}22%,100%{transform:translateX(56px)}}"
    "@media (prefers-reduced-motion:reduce){.t,.bar{opacity:1!important;transform:none!important;animation:none!important}"
    ".glow,.sh{animation:none}}"
)
updated = datetime.date.fromisoformat(ach["generated_at"][:10])
parts = [
    svg_open(W, H, style),
    window(W, H, "./achievements.sh", right=f"updated {updated:%b} {updated.day}"),
    '<defs><filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>',
]
for k, (_, light, dark) in TIER_STYLE.items():
    parts.append(f'<linearGradient id="t{k}" x1="0" y1="0" x2="1" y2="1">'
                 f'<stop offset="0" stop-color="{light}"/><stop offset="1" stop-color="{dark}"/></linearGradient>')
parts.append("</defs>")


def medal(i, cx, cy, card):
    out = []
    k = card["tier"]
    icon = ICONS[card["icon"]]
    s = 1.15
    place = f'transform="translate({cx - 12 * s:.1f} {cy - 12 * s:.1f}) scale({s})"'
    if k:
        out.append(f'<circle class="glow" style="animation-delay:{i * 0.4 % 3.2:.1f}s" cx="{cx:.1f}" cy="{cy}" '
                   f'r="{MEDAL_R + 4}" fill="{TIER_STYLE[k][2]}" filter="url(#blur)"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="{MEDAL_R}" fill="url(#t{k})"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="{MEDAL_R - 3}" fill="none" stroke="#ffffff" stroke-opacity=".35"/>')
        out.append(f'<g {place} fill="#0b1020" color="#0b1020">{icon}</g>')
        out.append(f'<clipPath id="m{i}"><circle cx="{cx:.1f}" cy="{cy}" r="{MEDAL_R}"/></clipPath>'
                   f'<g clip-path="url(#m{i})"><g transform="rotate(25 {cx:.1f} {cy})">'
                   f'<rect class="sh" style="animation-delay:{1.5 + i * 0.45:.2f}s" x="{cx - 6:.1f}" '
                   f'y="{cy - 40}" width="12" height="80" fill="#ffffff" opacity=".45"/></g></g>')
    else:
        out.append(f'<circle cx="{cx:.1f}" cy="{cy}" r="{MEDAL_R}" fill="#111a2e" stroke="#2a3a55" stroke-dasharray="3 3"/>')
        out.append(f'<g {place} fill="{LOCKED}" color="{LOCKED}" opacity=".8">{icon}</g>')
        lx, ly = cx + 16, cy + 15
        out.append(f'<circle cx="{lx:.1f}" cy="{ly}" r="8.5" fill="#0b1020" stroke="#2a3a55"/>'
                   f'<rect x="{lx - 3.6:.1f}" y="{ly - 1}" width="7.2" height="5.6" rx="1" fill="#8492a6"/>'
                   f'<path d="M{lx - 2.3:.1f} {ly - 1}v-1.6a2.3 2.3 0 0 1 4.6 0v1.6" fill="none" stroke="#8492a6" stroke-width="1.3"/>')
    return "".join(out)


def card_svg(i, x, y, card, delay):
    k = card["tier"]
    edge = f'stroke="{TIER_STYLE[k][1]}" stroke-opacity=".35"' if k else f'stroke="{PANEL_EDGE}"'
    label, color = (TIER_STYLE[k][0], TIER_STYLE[k][1]) if k else ("LOCKED", MUTED)
    if k and card["max_tier"] == 1:
        label = "UNLOCKED"
    sub = "github badge" if card["group"] == "github" else "local · from data"
    bar_w = CARD_W - 32
    fill = f"url(#t{k})" if k else BLUE
    out = [
        f'<g class="t" style="animation-delay:{delay:.2f}s">',
        f'<rect x="{x:.1f}" y="{y}" width="{CARD_W:.1f}" height="{CARD_H}" rx="10" fill="{PANEL}" {edge}/>',
        medal(i, x + 38, y + 40, card),
        f'<text x="{x + 72:.1f}" y="{y + 36}" fill="{color}" font-size="11.5" font-weight="700" letter-spacing="1">{label}</text>',
        f'<text x="{x + 72:.1f}" y="{y + 54}" fill="{MUTED}" font-size="11">{sub}</text>',
        f'<text x="{x + 16:.1f}" y="{y + 88}" fill="{INK if k else MUTED}" font-size="14" font-weight="700">{html.escape(card["name"])}</text>',
        f'<rect x="{x + 16:.1f}" y="{y + 99}" width="{bar_w:.1f}" height="6" rx="3" fill="#1a2338"/>',
    ]
    if card["ratio"] > 0:
        out.append(f'<rect class="bar" style="animation-delay:{delay + 0.35:.2f}s" x="{x + 16:.1f}" y="{y + 99}" '
                   f'width="{max(6, bar_w * card["ratio"]):.1f}" height="6" rx="3" fill="{fill}" '
                   f'opacity="{1 if k else .7}"/>')
    out.append(f'<text x="{x + 16:.1f}" y="{y + 127}" fill="{MUTED}" font-size="11.5">{html.escape(clip(card["text"]))}</text>')
    out.append("</g>")
    return "".join(out)


def summary_svg(x, y, delay):
    out = [
        f'<g class="t" style="animation-delay:{delay:.2f}s">',
        f'<rect x="{x:.1f}" y="{y}" width="{CARD_W:.1f}" height="{CARD_H}" rx="10" fill="{PANEL}" stroke="{PANEL_EDGE}"/>',
        f'<text x="{x + 16:.1f}" y="{y + 28}" fill="{MUTED}" font-size="13">$ progress</text>',
        f'<text x="{x + 16:.1f}" y="{y + 64}" fill="{CYAN}" font-size="30" font-weight="700">{gh_unlocked}/{len(github_cards)}'
        f'<tspan fill="{MUTED}" font-size="12" font-weight="400"> github</tspan></text>',
        f'<text x="{x + 16:.1f}" y="{y + 88}" fill="{INK}" font-size="15" font-weight="700">{local_unlocked}/{len(local_cards)}'
        f'<tspan fill="{MUTED}" font-size="12" font-weight="400"> local</tspan></text>',
    ]
    if closest:
        nxt = TIER_STYLE.get(closest["tier"] + 1, ("",))[0].split(" ")[-1] if closest["tier"] else "unlock"
        out.append(f'<text x="{x + 16:.1f}" y="{y + 112}" fill="{MUTED}" font-size="11.5">next → '
                   f'<tspan fill="{INK}">{html.escape(clip(closest["name"] + " " + nxt))}</tspan></text>')
        out.append(f'<text x="{x + 16:.1f}" y="{y + 130}" fill="{MUTED}" font-size="11.5">{html.escape(clip(closest["text"]))}</text>')
    out.append("</g>")
    return "".join(out)


parts.append(f'<text x="{PAD}" y="{top + 18}" fill="{MUTED}" font-size="13">$ gh achievements --progress</text>')
for i, card in enumerate(github_cards):
    x, y = slot_xy(i, gh_top)
    parts.append(card_svg(i, x, y, card, i * 0.08))
x, y = slot_xy(len(github_cards), gh_top)
parts.append(summary_svg(x, y, len(github_cards) * 0.08))

parts.append(f'<text x="{PAD}" y="{local_label + 18}" fill="{MUTED}" font-size="13">$ ./local-achievements</text>')
for j, card in enumerate(local_cards):
    x, y = slot_xy(j, local_top)
    i = len(github_cards) + 1 + j
    parts.append(card_svg(i, x, y, card, i * 0.08))

parts.append("</svg>")
write_svg("achievements.svg", "".join(parts))
