#!/usr/bin/env python3
"""
GitHub Profile README Stats Generator
Fetches live data from the GitHub API and auto-updates the Stats block in README.md.

Data sources:
    - WakaTime      : languages, coding-time distribution, day-of-week, editors, operating systems
    - GitHub API    : repo count, stars, and project categories
"""

import os
import re
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict

try:
    import requests
except ImportError:
    raise SystemExit("Missing dependency. Run: pip install requests")

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_USERNAME = "0x3EF8"
README_PATH     = "README.md"
BAR_WIDTH       = 10
START_YEAR      = 2020
MARKER_START    = "<!-- STATS:START -->"
MARKER_END      = "<!-- STATS:END -->"
MAIN_COL_WIDTH  = 72

# Philippines Standard Time = UTC+8 (no DST)
LOCAL_TZ = timezone(timedelta(hours=8))

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
WAKATIME_API_KEY = os.environ.get("WAKATIME_API_KEY") or ""
WAKATIME_BASE_URL = "https://wakatime.com/api/v1/users/current"
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# ── Helpers ───────────────────────────────────────────────────────────────────
def progress_bar(pct: float) -> str:
    filled = max(0, min(BAR_WIDTH, round(pct / 100 * BAR_WIDTH)))
    return "▰" * filled + "▱" * (BAR_WIDTH - filled)

BAR_LINE_PATTERN = re.compile(
    rf"^\s*(?P<label>.+?)\s+(?P<bar>[▰▱]{{{BAR_WIDTH}}})\s+"
    r"(?P<pct>\d+(?:\.\d+)?)\s*%(?:\s+.*)?$"
)

def _extract_section_percentages(block: str, start_title: str, end_title: str) -> list:
    values = []
    in_section = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped == start_title:
            in_section = True
            continue
        if in_section and stripped == end_title:
            break
        if not in_section:
            continue

        match = BAR_LINE_PATTERN.match(line)
        if match:
            values.append(float(match.group("pct")))
    return values

def validate_stats_block(block: str) -> None:
    errors = []
    checked_rows = 0

    for line_no, line in enumerate(block.splitlines(), start=1):
        match = BAR_LINE_PATTERN.match(line)
        if not match:
            continue

        checked_rows += 1
        pct = float(match.group("pct"))
        bar = match.group("bar")
        expected_filled = max(0, min(BAR_WIDTH, round(pct / 100 * BAR_WIDTH)))
        actual_filled = bar.count("▰")

        if not 0.0 <= pct <= 100.0:
            errors.append(f"line {line_no}: percentage out of bounds ({pct:.2f}%)")
        if actual_filled != expected_filled:
            errors.append(
                f"line {line_no}: bar mismatch (expected {expected_filled} filled, got {actual_filled})"
            )

    if checked_rows == 0:
        errors.append("no progress-bar rows were found in the generated stats block")

    time_values = _extract_section_percentages(
        block,
        start_title="I Code Most During",
        end_title="I Am Most Productive On",
    )
    day_values = _extract_section_percentages(
        block,
        start_title="I Am Most Productive On",
        end_title="Editors",
    )

    if len(time_values) != 4:
        errors.append(f"time-of-day section should have 4 rows, found {len(time_values)}")
    if len(day_values) != 7:
        errors.append(f"day-of-week section should have 7 rows, found {len(day_values)}")

    if time_values:
        time_sum = sum(time_values)
        has_time_activity = any(v > 0.0 for v in time_values)
        if has_time_activity and abs(time_sum - 100.0) > 0.25:
            errors.append(f"time-of-day percentages should sum to ~100, got {time_sum:.2f}")
    if day_values:
        day_sum = sum(day_values)
        has_day_activity = any(v > 0.0 for v in day_values)
        if has_day_activity and abs(day_sum - 100.0) > 0.25:
            errors.append(f"day-of-week percentages should sum to ~100, got {day_sum:.2f}")

    if errors:
        raise ValueError("Stats validation failed:\n  - " + "\n  - ".join(errors))

    print(f"Stats validation passed ({checked_rows} bar rows checked).")

def api_get(url: str, retries: int = 3) -> any:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 403 and "rate limit" in r.text.lower():
                wait = int(r.headers.get("Retry-After", 60))
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)

def _to_float(value: any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default

def format_hours(seconds: float) -> str:
    if seconds <= 0:
        return "n/a"
    return f"{seconds / 3600:5.2f} h"

def with_right(main_text: str, side_text: str = "") -> str:
    if not side_text:
        return main_text
    return f"{main_text:<{MAIN_COL_WIDTH}} | {side_text}"

def wakatime_get(resource: str, params: dict | None = None, retries: int = 3) -> any:
    url = f"{WAKATIME_BASE_URL}/{resource}"
    for attempt in range(retries):
        try:
            r = requests.get(url, auth=(WAKATIME_API_KEY, ""), params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 60))
                print(f"  WakaTime rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue

            r.raise_for_status()
            payload = r.json() if r.content else {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if data is None:
                print(f"  Unexpected WakaTime payload for {resource}; skipping.")
                return None
            return data
        except requests.RequestException as e:
            if attempt == retries - 1:
                print(f"  Failed to fetch WakaTime {resource}: {e}")
                return None
            time.sleep(2 ** attempt)

def fetch_wakatime_stats(retries: int = 3) -> any:
    if not WAKATIME_API_KEY:
        print("  WAKATIME_API_KEY not set; skipping WakaTime data.")
        return None

    data = wakatime_get("stats/last_7_days", retries=retries)
    if isinstance(data, dict):
        return data
    print("  Unexpected WakaTime stats shape; continuing without WakaTime stats.")
    return None

def fetch_wakatime_durations(days: int = 7, retries: int = 3) -> list:
    if not WAKATIME_API_KEY:
        return []

    durations = []
    today_local = datetime.now(LOCAL_TZ).date()
    for offset in range(days):
        target_date = (today_local - timedelta(days=offset)).isoformat()
        day_data = wakatime_get("durations", params={"date": target_date}, retries=retries)
        if isinstance(day_data, list):
            durations.extend(day_data)
    return durations

def extract_wakatime_percentages(
    wakatime_stats: any,
    key: str,
    limit: int = 0,
    fallback_total_seconds: float = 0.0,
) -> list:
    rows = []
    if not isinstance(wakatime_stats, dict):
        return rows

    for item in (wakatime_stats.get(key) or []):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "Unknown").strip() or "Unknown"
        pct = max(0.0, min(100.0, _to_float(item.get("percent"), 0.0)))
        total_seconds = _to_float(item.get("total_seconds"), 0.0)
        if total_seconds <= 0 and fallback_total_seconds > 0 and pct > 0:
            total_seconds = fallback_total_seconds * (pct / 100.0)
        rows.append((name, pct, total_seconds))

    rows.sort(key=lambda x: -x[1])
    return rows[:limit] if limit > 0 else rows

def wakatime_activity_stats(wakatime_durations: list) -> tuple:
    hour_map = {"Morning": 0.0, "Daytime": 0.0, "Evening": 0.0, "Night": 0.0}
    day_map: dict = defaultdict(float)
    hour_count_map = {"Morning": 0, "Daytime": 0, "Evening": 0, "Night": 0}
    day_count_map: dict = defaultdict(int)
    total_seconds = 0.0

    for item in wakatime_durations:
        if not isinstance(item, dict):
            continue

        start_ts = item.get("time")
        duration_sec = _to_float(item.get("duration"), 0.0)
        if duration_sec <= 0.0:
            continue

        try:
            local_dt = datetime.fromtimestamp(float(start_ts), tz=LOCAL_TZ)
        except (TypeError, ValueError, OSError):
            continue

        h = local_dt.hour
        bucket = (
            "Morning" if 6 <= h < 12 else
            "Daytime" if 12 <= h < 18 else
            "Evening" if 18 <= h < 24 else
            "Night"
        )
        hour_map[bucket] += duration_sec
        day_map[local_dt.strftime("%A")] += duration_sec
        hour_count_map[bucket] += 1
        day_count_map[local_dt.strftime("%A")] += 1
        total_seconds += duration_sec

    return hour_map, dict(day_map), total_seconds, hour_count_map, dict(day_count_map)

def wakatime_day_stats_from_summary(wakatime_stats: any) -> dict:
    day_map: dict = defaultdict(float)
    if not isinstance(wakatime_stats, dict):
        return dict(day_map)

    for item in (wakatime_stats.get("days_including_holidays") or []):
        if not isinstance(item, dict):
            continue

        date_text = item.get("date")
        total_seconds = _to_float(item.get("total_seconds"), 0.0)
        if total_seconds <= 0.0 or not date_text:
            continue

        try:
            day_name = datetime.fromisoformat(str(date_text)).strftime("%A")
        except ValueError:
            continue

        day_map[day_name] += total_seconds

    return dict(day_map)

def paginate(url: str) -> list:
    results, next_url = [], url
    while next_url:
        r = requests.get(next_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        results.extend(data if isinstance(data, list) else [data])
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
        combined = (
            repo["name"].lower() + " " +
            (repo.get("description") or "").lower() + " " +
            " ".join(repo.get("topics", []))
        )
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
def build_stats_block(repos: list, wakatime_stats: any, wakatime_durations: list) -> str:
    own   = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in own)
    year  = datetime.now(timezone.utc).year
    now   = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M PHT")
    SEP   = "━" * 58

    cats = categorize_repos(repos)
    cat_total = sum(len(v) for v in cats.values()) or 1

    hour_map, day_map, duration_total, hour_count_map, day_count_map = wakatime_activity_stats(
        wakatime_durations
    )

    wt_languages = extract_wakatime_percentages(
        wakatime_stats,
        "languages",
        limit=8,
        fallback_total_seconds=duration_total,
    )
    wt_editors = extract_wakatime_percentages(
        wakatime_stats,
        "editors",
        limit=5,
        fallback_total_seconds=duration_total,
    )
    wt_os = extract_wakatime_percentages(
        wakatime_stats,
        "operating_systems",
        limit=5,
        fallback_total_seconds=duration_total,
    )

    if sum(day_map.values()) == 0:
        day_map = wakatime_day_stats_from_summary(wakatime_stats)

    total_time = "n/a"
    daily_avg = "n/a"
    if isinstance(wakatime_stats, dict):
        total_time = wakatime_stats.get("human_readable_total") or "n/a"
        daily_avg = wakatime_stats.get("human_readable_daily_average") or "n/a"

    top_lang_name = "n/a"
    top_lang_pct = 0.0
    if wt_languages:
        top_lang_name, top_lang_pct, _ = wt_languages[0]

    if duration_total > 0:
        peak_slot, peak_slot_seconds = max(hour_map.items(), key=lambda x: x[1])
        peak_slot_pct = peak_slot_seconds / duration_total * 100
    else:
        peak_slot, peak_slot_pct = "n/a", 0.0

    day_total_for_peak = sum(day_map.values())
    if day_total_for_peak > 0:
        peak_day, peak_day_seconds = max(day_map.items(), key=lambda x: x[1])
        peak_day_pct = peak_day_seconds / day_total_for_peak * 100
    else:
        peak_day, peak_day_pct = "n/a", 0.0

    tracked_sessions = len(wakatime_durations)

    L = []
    L.append(with_right("0x3EF8 · Dev Metrics", "Quick Insights"))
    L.append(
        with_right(
            f"From: {START_YEAR} - To: {year}   |   {len(own)}+ public repos   |   {stars} stars",
            f"Top Lang : {top_lang_name} ({top_lang_pct:5.2f}%)",
        )
    )
    L.append(
        with_right(
            f"WakaTime (last 7d): {total_time} total · {daily_avg} daily avg",
            f"Peak Time: {peak_slot} ({peak_slot_pct:5.2f}%)",
        )
    )
    L.append(with_right("", f"Peak Day : {peak_day} ({peak_day_pct:5.2f}%)"))
    L.append(with_right("", f"Sessions : {tracked_sessions} tracked"))
    L.append("")
    L.append(SEP)
    L.append("")

    # Languages (WakaTime)
    L.append(" Languages")
    if wt_languages:
        for lang_name, lang_pct, lang_seconds in wt_languages:
            L.append(
                f" {lang_name:<17} {progress_bar(lang_pct)}   {lang_pct:5.2f} %   | {format_hours(lang_seconds):>7}"
            )
    else:
        L.append(" WakaTime data unavailable (set WAKATIME_API_KEY).")
    L.append("")
    L.append(SEP)
    L.append("")

    # Time of day (WakaTime durations)
    L.append(" I Code Most During")
    L.append("")
    for slot, rng in [("Morning", "06-12"), ("Daytime", "12-18"), ("Evening", "18-24"), ("Night", "00-06")]:
        seconds = hour_map.get(slot, 0.0)
        sessions = hour_count_map.get(slot, 0)
        pct = seconds / duration_total * 100 if duration_total else 0
        L.append(
            f" {slot:<10} ({rng})   {progress_bar(pct)}   {pct:5.2f} %   | {format_hours(seconds):>7} | {sessions:2d} sess"
        )

    L.append("")
    L.append(" I Am Most Productive On")
    L.append("")
    day_total = sum(day_map.values())
    for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        seconds = day_map.get(day, 0.0)
        sessions = day_count_map.get(day, 0)
        pct = seconds / day_total * 100 if day_total else 0
        L.append(
            f" {day:<10} {progress_bar(pct)}   {pct:5.2f} %   | {format_hours(seconds):>7} | {sessions:2d} sess"
        )
    L.append("")
    L.append(SEP)
    L.append("")

    # Editors (WakaTime)
    L.append(" Editors")
    for name, pct, seconds in (wt_editors or [("Unknown", 0.0, 0.0)]):
        L.append(f" {name:<17} {progress_bar(pct)}   {pct:5.2f} %   | {format_hours(seconds):>7}")
    L.append("")

    # Operating systems (WakaTime)
    L.append(" Operating Systems")
    for name, pct, seconds in (wt_os or [("Unknown", 0.0, 0.0)]):
        L.append(f" {name:<17} {progress_bar(pct)}   {pct:5.2f} %   | {format_hours(seconds):>7}")
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
    L.append(f" Languages/Time/Day/Editors/OS from WakaTime API · Projects from GitHub API · Updated: {now}")

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
    print("README.md updated.")
    return True

# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    print(f"Fetching repos for {GITHUB_USERNAME}...")
    repos = fetch_repos()
    own   = [r for r in repos if not r.get("fork")]
    print(f"  {len(own)} own repos ({len(repos) - len(own)} forks excluded)")

    print("Fetching WakaTime stats...")
    wakatime_stats = fetch_wakatime_stats()

    print("Fetching WakaTime durations...")
    wakatime_durations = fetch_wakatime_durations(days=7)
    print(f"  {len(wakatime_durations)} duration records")

    print("Building stats block...")
    block = build_stats_block(repos, wakatime_stats, wakatime_durations)

    print("Validating stats block...")
    validate_stats_block(block)

    print("Patching README.md...")
    patch_readme(block)

if __name__ == "__main__":
    main()
