#!/usr/bin/env python3
"""
Collect GitHub achievement state + progress numbers into data/achievements.json.

Two sources:
  1. the public achievements tab -- the only source of truth for which badges
     are earned and at what tier, read from the badge image names
     (pull-shark-bronze-*.png -> x2). Each successful scrape replaces the
     previous public badge state.
  2. the GraphQL API -- the numbers behind each badge (merged PRs, stars,
     accepted answers ...) for the progress bars. They never raise a tier on
     their own: GitHub awards tiers with a delay and by its own counting. Needs
     a token; the workflow passes the built-in GITHUB_TOKEN.

Failed sources are reported as workflow warnings. Unavailable metrics are not
invented, and a failed public-page scrape hides the GitHub badge panel.

    GITHUB_TOKEN=... python scripts/fetch_achievements.py
"""
import datetime
import json
import os
import re
import urllib.request

from term import ROOT, USER

OUT_PATH = os.path.join(ROOT, "data", "achievements.json")
TOKEN = os.environ.get("GITHUB_TOKEN")
TIER_BY_IMAGE = {"default": 1, "bronze": 2, "silver": 3, "gold": 4}

CATALOG = ["pull-shark", "starstruck", "pair-extraordinaire", "galaxy-brain",
           "quickdraw", "yolo", "public-sponsor"]


def warn(msg):
    print(f"::warning::{msg}")


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": f"{USER}-profile-readme/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def graphql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": f"{USER}-profile-readme/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "?") for e in payload["errors"]))
    return payload["data"]


def scrape_earned():
    """{slug: tier} from the badge images on the achievements tab."""
    html = get(f"https://github.com/{USER}?tab=achievements")
    linked = set(re.findall(r"achievement=([a-z0-9-]+)", html))
    earned = {}
    for slug, kind in re.findall(r"/([a-z0-9-]+?)-(default|bronze|silver|gold)-[0-9a-f]+\.png", html):
        if slug in linked:  # ignore unrelated *-default-*.png assets on the page
            earned[slug] = max(earned.get(slug, 0), TIER_BY_IMAGE[kind])
    if not earned:
        raise ValueError("no achievement badges found -- markup may have changed")
    return earned


PR_QUERY = """
query($q: String!, $cursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        reviews { totalCount }
      }
    }
  }
}"""


def merged_pr_stats():
    """Merged PR count and PRs merged without review.

    No co-author count for Pair Extraordinaire: GitHub's tally doesn't match
    anything the API exposes (it ignores most AI co-authors, for one), so that
    card shows only the tier GitHub reports.
    """
    q = f"type:pr author:{USER} is:merged is:public"
    cursor, total, unreviewed = None, 0, 0
    for _ in range(20):  # search caps out at 1,000 results anyway
        page = graphql(PR_QUERY, q=q, cursor=cursor)["search"]
        total = page["issueCount"]
        for pr in page["nodes"]:
            if pr:
                unreviewed += pr["reviews"]["totalCount"] == 0
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return total, unreviewed


def top_repo():
    data = graphql("""
    query($login: String!) {
      user(login: $login) {
        repositories(first: 1, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                     orderBy: {field: STARGAZERS, direction: DESC}) {
          nodes { name stargazerCount }
        }
      }
    }""", login=USER)
    nodes = data["user"]["repositories"]["nodes"]
    return (nodes[0]["name"], nodes[0]["stargazerCount"]) if nodes else (None, 0)


def main():
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    badges = {}
    available = False
    try:
        scraped = scrape_earned()
        print("earned on profile:", ", ".join(f"{s} x{t}" for s, t in sorted(scraped.items())))
        badges = {slug: {"tier": 0, "value": None} for slug in CATALOG}
        for slug, tier in scraped.items():
            badges[slug] = {"tier": tier, "value": None}
        available = True
    except Exception as e:  # noqa: BLE001 -- hide unavailable public badge data
        warn(f"achievements tab: {e}")

    if TOKEN and available:
        metrics = [
            ("merged PRs", merged_pr_stats,
             lambda r: [("pull-shark", r[0]), ("yolo", min(r[1], 1))]),
            ("top repo", top_repo, lambda r: [("starstruck", r[1])]),
        ]
        for name, fn, assign in metrics:
            try:
                result = fn()
                print(f"{name}: {result}")
                if name == "top repo" and badges["starstruck"]["tier"]:
                    badges["starstruck"]["repo"] = result[0]
                for slug, value in assign(result):
                    if badges[slug]["tier"]:
                        badges[slug]["value"] = value
            except Exception as e:  # noqa: BLE001 -- leave unavailable metrics unknown
                warn(f"{name}: {e}")
    elif not TOKEN:
        warn("GITHUB_TOKEN not set -- public progress numbers are unavailable")

    out = {
        "username": USER,
        "generated_at": now,
        "earned_at": now if available else None,
        "available": available,
        "badges": dict(sorted(badges.items())),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("wrote data/achievements.json")


if __name__ == "__main__":
    main()
