#!/usr/bin/env python3
"""
Collect GitHub achievement state + progress numbers into data/achievements.json.

Two sources, merged so a badge never goes backwards:
  1. the public achievements tab -- which badges are earned and at what tier,
     read from the badge image names (pull-shark-bronze-*.png -> x2)
  2. the GraphQL API -- the numbers behind each badge (merged PRs, stars,
     accepted answers ...) so locked tiers can show a progress bar. Needs a
     token; the workflow passes the built-in GITHUB_TOKEN.

Whatever a source fails to provide is carried over from the previous run, and
a failing source is reported as a workflow warning instead of failing the job.

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

# slug -> tier thresholds (single-tier badges have one threshold of 1)
TIERS = {
    "pull-shark": [2, 16, 128, 1024],
    "starstruck": [16, 128, 512, 4096],
    "pair-extraordinaire": [1, 10, 24, 48],
    "galaxy-brain": [2, 8, 16, 32],
    "quickdraw": [1],
    "yolo": [1],
    "public-sponsor": [1],
}


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
  search(query: $q, type: ISSUE, first: 50, after: $cursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        reviews { totalCount }
        commits(first: 100) { nodes { commit { message } } }
      }
    }
  }
}"""


def merged_pr_stats():
    """Merged PR count, PRs with a co-authored commit, PRs merged without review."""
    q = f"type:pr author:{USER} is:merged"
    cursor, total, coauthored, unreviewed = None, 0, 0, 0
    for _ in range(20):  # search caps out at 1,000 results anyway
        page = graphql(PR_QUERY, q=q, cursor=cursor)["search"]
        total = page["issueCount"]
        for pr in page["nodes"]:
            if not pr:
                continue
            messages = (c["commit"]["message"] for c in pr["commits"]["nodes"])
            # trailer presence only -- GitHub additionally requires the co-author
            # to resolve to an account, so this can run slightly high
            coauthored += any("co-authored-by:" in m.lower() for m in messages)
            unreviewed += pr["reviews"]["totalCount"] == 0
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return total, coauthored, unreviewed


def top_repo():
    data = graphql("""
    query($login: String!) {
      user(login: $login) {
        repositories(first: 1, ownerAffiliations: OWNER, isFork: false,
                     orderBy: {field: STARGAZERS, direction: DESC}) {
          nodes { name stargazerCount }
        }
      }
    }""", login=USER)
    nodes = data["user"]["repositories"]["nodes"]
    return (nodes[0]["name"], nodes[0]["stargazerCount"]) if nodes else (None, 0)


def accepted_answers():
    data = graphql("""
    query($login: String!) {
      user(login: $login) { repositoryDiscussionComments(onlyAnswers: true) { totalCount } }
    }""", login=USER)
    return data["user"]["repositoryDiscussionComments"]["totalCount"]


def sponsoring():
    data = graphql("""
    query($login: String!) { user(login: $login) { sponsoring { totalCount } } }""", login=USER)
    return data["user"]["sponsoring"]["totalCount"]


def tier_for(slug, value):
    return sum(1 for t in TIERS.get(slug, [1]) if value is not None and value >= t)


def main():
    prev = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            prev = json.load(f).get("badges", {})
    badges = {slug: dict(prev.get(slug, {"tier": 0, "value": None})) for slug in set(TIERS) | set(prev)}

    try:
        scraped = scrape_earned()
        print("earned on profile:", ", ".join(f"{s} x{t}" for s, t in sorted(scraped.items())))
        for slug, tier in scraped.items():
            badges.setdefault(slug, {"tier": 0, "value": None})
            badges[slug]["tier"] = max(badges[slug]["tier"], tier)
    except Exception as e:  # noqa: BLE001 -- keep previous state
        warn(f"achievements tab: {e}")

    if TOKEN:
        metrics = [
            ("merged PRs", merged_pr_stats,
             lambda r: [("pull-shark", r[0]), ("pair-extraordinaire", r[1]), ("yolo", min(r[2], 1))]),
            ("top repo", top_repo, lambda r: [("starstruck", r[1])]),
            ("discussion answers", accepted_answers, lambda r: [("galaxy-brain", r)]),
            ("sponsoring", sponsoring, lambda r: [("public-sponsor", min(r, 1))]),
        ]
        for name, fn, assign in metrics:
            try:
                result = fn()
                print(f"{name}: {result}")
                if name == "top repo":
                    badges["starstruck"]["repo"] = result[0]
                for slug, value in assign(result):
                    badges[slug]["value"] = value
                    badges[slug]["tier"] = max(badges[slug]["tier"], tier_for(slug, value))
            except Exception as e:  # noqa: BLE001 -- keep previous numbers
                warn(f"{name}: {e}")
    else:
        warn("GITHUB_TOKEN not set -- progress numbers carried over from the last run")

    out = {
        "username": USER,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "badges": dict(sorted(badges.items())),
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("wrote data/achievements.json")


if __name__ == "__main__":
    main()
