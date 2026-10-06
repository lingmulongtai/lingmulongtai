#!/usr/bin/env python3
"""
Fetch the last year of daily contribution counts and write data/contributions.json
with the raw days plus derived stats (streaks, best day, monthly and weekday totals).

Source order:
  1. github.com/users/<user>/contributions -- the public HTML fragment the
     profile page itself renders (no token needed)
  2. github-contributions-api.jogruber.de -- third-party mirror, used only if
     GitHub's markup changes or the request fails

Standard library only. Run daily by .github/workflows/update-profile-art.yml.

    python scripts/fetch_contributions.py
"""
import datetime
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

from term import DATA_PATH, USER

GITHUB_URL = f"https://github.com/users/{USER}/contributions"
MIRROR_URL = f"https://github-contributions-api.jogruber.de/v4/{USER}?y=last"
UA = {"User-Agent": f"{USER}-profile-readme/1.0"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def http_get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


class CalendarParser(HTMLParser):
    """Collects <td data-date data-level id> cells and the <tool-tip for=id> text."""

    def __init__(self):
        super().__init__()
        self.cells = []
        self.tips = {}
        self._tip_for = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "td" and a.get("data-date"):
            self.cells.append((a.get("id"), a["data-date"], int(a.get("data-level") or 0)))
        elif tag == "tool-tip":
            self._tip_for, self._buf = a.get("for"), []

    def handle_data(self, data):
        if self._tip_for is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self._tip_for is not None:
            self.tips[self._tip_for] = "".join(self._buf).strip()
            self._tip_for = None


def parse_calendar(html):
    p = CalendarParser()
    p.feed(html)
    days = []
    for cell_id, date, level in p.cells:
        m = re.match(r"([\d,]+) contributions?", p.tips.get(cell_id, ""))
        days.append({"date": date, "count": int(m.group(1).replace(",", "")) if m else 0, "level": level})
    if not days:
        raise ValueError("no calendar cells found")
    if any(d["level"] and not d["count"] for d in days):
        raise ValueError("tooltip text no longer carries counts")
    return days


def from_github():
    return parse_calendar(http_get(GITHUB_URL))


def from_mirror():
    payload = json.loads(http_get(MIRROR_URL))
    return [{"date": c["date"], "count": c["count"], "level": c["level"]} for c in payload["contributions"]]


def fetch_days():
    for name, fn in [("github", from_github), ("mirror", from_mirror)]:
        try:
            days = sorted(fn(), key=lambda d: d["date"])
            print(f"fetched {len(days)} days from {name}")
            return days, name
        except Exception as e:  # noqa: BLE001 -- any failure means try the next source
            print(f"{name} failed: {e}", file=sys.stderr)
    sys.exit("all contribution sources failed")


def streak(run):
    if not run:
        return {"length": 0, "start": None, "end": None}
    return {"length": len(run), "start": run[0]["date"], "end": run[-1]["date"]}


def current_streak(days):
    i = len(days) - 1
    if days[i]["count"] == 0:
        i -= 1  # today isn't over yet, so an empty today doesn't break the streak
    end = i
    while i >= 0 and days[i]["count"] > 0:
        i -= 1
    return streak(days[i + 1:end + 1])


def longest_streak(days):
    best, start = [], None
    for i, d in enumerate(days + [{"count": 0}]):
        if d["count"] > 0 and start is None:
            start = i
        elif d["count"] == 0 and start is not None:
            if i - start > len(best):
                best = days[start:i]
            start = None
    return streak(best)


def build(days, source):
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"])
    best = max(days, key=lambda d: d["count"])

    monthly, by_weekday, weekday_n = {}, [0] * 7, [0] * 7
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["count"]
        wd = datetime.date.fromisoformat(d["date"]).weekday()
        by_weekday[wd] += d["count"]
        weekday_n[wd] += 1
    top_wd = max(range(7), key=lambda i: by_weekday[i])

    return {
        "username": USER,
        "source": source,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active,
        "avg_per_active_day": round(total / active, 1) if active else 0,
        "current_streak": current_streak(days),
        "longest_streak": longest_streak(days),
        "best_day": {"date": best["date"], "count": best["count"]},
        "busiest_weekday": {
            "name": WEEKDAYS[top_wd],
            "total": by_weekday[top_wd],
            "avg": round(by_weekday[top_wd] / weekday_n[top_wd], 1) if weekday_n[top_wd] else 0,
        },
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items())],
        "days": days,
    }


if __name__ == "__main__":
    days, source = fetch_days()
    data = build(days, source)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(
        f"{data['total_contributions']:,} contributions, "
        f"current streak {data['current_streak']['length']}, "
        f"longest {data['longest_streak']['length']}"
    )
