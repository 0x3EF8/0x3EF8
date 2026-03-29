#!/usr/bin/env python3
"""
GitHub Profile README Stats Generator
Fetches live data from the GitHub API and auto-updates the Stats block in README.md.
"""

import os
import re
from datetime import datetime, timezone
from collections import defaultdict

try:
    import requests
except ImportError:
    raise SystemExit("Missing dependency. Run: pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_USERNAME = "0x3EF8"
README_PATH     = "README.md"
BAR_WIDTH       = 20
START_YEAR      = 2020
MARKER_START    = "<!-- STATS:START -->"
MARKER_END      = "<!-- STATS:END -->"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
HEADERS = {"Accept": "application/vnd.github.v3+json", "X-GitHub-Api-Version": "2022-11-28"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# ── Helpers ───────────────────────────────────────────────────────────────────
def progress_bar(pct: float) -> str:
    filled = max(0, min(BAR_WIDTH, round(pct / 100 * BAR_WIDTH)))
    return "▰" * filled + "▱" * (BAR_WIDTH - filled)

def paginate(url: str) -> list:
    results, next_url = [], url
    while next_url:
        r = requests.get(next_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        results.extend(r.json())
        next_url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
    return results

# ── Data fetching ─────────────────────────────────────────────────────────────
def fetch_repos() -> list:
    return paginate(
        f"https://api.github.com/users/{GITHUB_USERNAME}/repos"
        "?per_page=100&type=owner&sort=pushed"
    )

def fetch_events() -> list:
    results, url, pages = [], \
        f"https://api.github.com/users/{GITHUB_USERNAME}/events/public?per_page=100", 0
    while url and pages < 3:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        results.extend(r.json())
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
        pages += 1
    return results

# ── Stats computation ─────────────────────────────────────────────────────────
def language_stats(repos: list) -> tuple:
    counts: dict = defaultdict(int)
    for repo in repos:
        if not repo.get("fork") and repo.get("language"):
            counts[repo["language"]] += 1
    total = sum(counts.values())
    return dict(counts), total

def time_stats(events: list) -> tuple:
    hour_map = {"Morning": 0, "Daytime": 0, "Evening": 0, "Night": 0}
    day_map: dict = defaultdict(int)
    n = 0
    for evt in events:
        if evt.get("type") != "PushEvent":
            continue
        ts = evt.get("created_at", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            h = dt.hour
            bucket = ("Morning" if 6 <= h < 12 else
                      "Daytime" if 12 <= h < 18 else
                      "Evening" if 18 <= h < 24 else "Night")
            hour_map[bucket] += 1
            day_map[dt.strftime("%A")] += 1
            n += 1
        except (ValueError, AttributeError):
            pass
    return hour_map, dict(day_map), n

_CAT_RULES = [
    ("Bots & Messenger", ["bot", "messenger", "facebook", "nero", "gitbell", "gitchell"]),
    ("AI & Automation",  ["ai", "ml", "agent", "nexus", "aether", "moltbook", "auto", "gpt"]),
    ("Web Development",  ["web", "devpulse", "css", "edu", "design", "dashboard", "site", "pay"]),
    ("Tools & Scripts",  ["tool", "script", "downloader", "micro", "xampp", "util", "cli"]),
]

def categorize_repos(repos: list) -> dict:
    cats = {k: [] for k, _ in _CAT_RULES}
    cats["Other"] = []
    for repo in repos:
        if repo.get("fork"):
            continue
        combined = (repo["name"].lower() + " " +
                    (repo.get("description") or "").lower() + " " +
                    " ".join(repo.get("topics", [])))
        matched = False
        for cat_name, keywords in _CAT_RULES:
            if any(kw in combined for kw in keywords):
                cats[cat_name].append(repo["name"])
                matched = True
                break
        if not matched:
            cats["Other"].append(repo["name"])
    return cats

# ── Block generator ───────────────────────────────────────────────────────────
def build_stats_block(repos: list, events: list) -> str:
    own  = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in own)
    year  = datetime.now(timezone.utc).year
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    SEP   = "━" * 58

    lang_counts, lang_total = language_stats(repos)
    sorted_langs = sorted(lang_counts.items(), key=lambda x: -x[1])

    hour_map, day_map, n_push = time_stats(events)

    cats      = categorize_repos(repos)
    cat_total = sum(len(v) for v in cats.values()) or 1

    L = []
    L.append("0x3EF8 · Dev Metrics")
    L.append(f"From: {START_YEAR} - To: {year}   |   {len(own)}+ public repos   |   {stars} stars")
    L.append("")
    L.append(SEP)
    L.append("")

    # Languages
    L.append(" Languages")
    for lang, count in sorted_langs[:8]:
        pct  = count / lang_total * 100 if lang_total else 0
        word = "repos" if count != 1 else "repo "
        L.append(f" {lang:<17} {progress_bar(pct)}   {pct:5.2f} %   ({count} {word})")
    L.append("")
    L.append(SEP)
    L.append("")

    # Time of day
    L.append(" I Code Most During")
    L.append("")
    for slot, rng in [("Morning","06–12"),("Daytime","12–18"),("Evening","18–24"),("Night","00–06")]:
        c   = hour_map.get(slot, 0)
        pct = c / n_push * 100 if n_push else 0
        L.append(f" {slot:<10} ({rng})   {progress_bar(pct)}   {pct:5.2f} %")

    L.append("")
    L.append(" I Am Most Productive On")
    L.append("")
    day_total = sum(day_map.values()) or 1
    for day in ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]:
        pct = day_map.get(day, 0) / day_total * 100
        L.append(f" {day:<10} {progress_bar(pct)}   {pct:5.2f} %")
    L.append("")
    L.append(SEP)
    L.append("")

    # Editors (static)
    L.append(" Editors")
    for name, pct in [("VS Code",91.89),("Visual Studio",5.41),("Android Studio",2.70)]:
        L.append(f" {name:<17} {progress_bar(pct)}   {pct:5.2f} %")
    L.append("")
    L.append(" Operating Systems")
    for name, pct in [("Windows",95.00),("Linux",5.00)]:
        L.append(f" {name:<17} {progress_bar(pct)}   {pct:5.2f} %")
    L.append("")
    L.append(SEP)
    L.append("")

    # Project categories
    L.append(" Projects (by repo category)")
    for cat_name in ["AI & Automation","Web Development","Tools & Scripts","Bots & Messenger"]:
        repos_in = cats.get(cat_name, [])
        pct      = len(repos_in) / cat_total * 100
        sample   = ", ".join(repos_in[:3])
        suffix   = f"  ({sample} ...)" if sample else ""
        L.append(f" {cat_name:<17} {progress_bar(pct)}   {pct:5.2f} %{suffix}")
    L.append("")
    L.append(SEP)
    L.append(f" Languages from GitHub API · Time/Day from push activity · Updated: {now}")

    return "\n".join(L)

# ── README patcher ────────────────────────────────────────────────────────────
def patch_readme(block: str) -> bool:
    with open(README_PATH, "r", encoding="utf-8") as f:
        original = f.read()

    replacement = (
        f"{MARKER_START}\n"
        f"```text\n"
        f"{block}\n"
        f"```\n"
        f"{MARKER_END}"
    )
    new_content = re.sub(
        rf"{re.escape(MARKER_START)}.*?{re.escape(MARKER_END)}",
        replacement,
        original,
        flags=re.DOTALL,
    )
    if new_content == original:
        print("README unchanged — nothing to commit.")
        return False

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("✓ README.md updated.")
    return True

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print(f"→ Fetching repos for {GITHUB_USERNAME} …")
    repos  = fetch_repos()
    print(f"  {len(repos)} repos")

    print("→ Fetching public events …")
    events = fetch_events()
    push   = [e for e in events if e.get("type") == "PushEvent"]
    print(f"  {len(events)} events, {len(push)} push events")

    print("→ Building stats block …")
    block = build_stats_block(repos, events)

    print("→ Patching README.md …")
    patch_readme(block)

if __name__ == "__main__":
    main()
