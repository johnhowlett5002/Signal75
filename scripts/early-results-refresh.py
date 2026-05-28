#!/usr/bin/env python3
"""
Signal 75 — Early Results Refresh

Lightweight gatekeeper for daytime result checks. It only runs the normal
result updater when at least one unsettled race is 15+ minutes past off time.
The evening settlement remains the full safety net.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo


REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
LOG_FILE = os.path.expanduser("~/signal75-early-results-detail.log")
UK_TZ = ZoneInfo("Europe/London")
MINUTES_AFTER_RACE = 15
ACTIVE_START_HOUR = 12
ACTIVE_END_HOUR = 23


def log(message):
    stamp = datetime.now(UK_TZ).isoformat(timespec="seconds")
    line = f"[{stamp}] {message}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_picks():
    with open(PICKS_FILE) as f:
        return json.load(f)


def parse_race_datetime(picks_date, time_text):
    if not time_text:
        return None
    try:
        hour, minute = str(time_text).split(":")[:2]
        year, month, day = [int(part) for part in picks_date.split("-")]
        return datetime(year, month, day, int(hour), int(minute), tzinfo=UK_TZ)
    except Exception:
        return None


def result_is_settled(result):
    return str(result or "").upper() in {"WON", "PLACED", "LOST", "VOID", "NR"}


def collect_official_due(picks, now):
    due = []
    results = picks.get("results", {}) or {}
    race_date = picks.get("date") or date.today().isoformat()

    for tab in ("flat", "jumps"):
        tab_results = results.get(tab, []) or []
        for index, race in enumerate(picks.get(tab, []) or []):
            horses = race.get("horses") or []
            if not horses:
                continue
            existing = tab_results[index] if index < len(tab_results) else {}
            horse = horses[0]
            current_result = existing.get("result") or horse.get("result")
            if result_is_settled(current_result):
                continue
            race_time = parse_race_datetime(race_date, race.get("time"))
            if not race_time:
                continue
            check_time = race_time + timedelta(minutes=MINUTES_AFTER_RACE)
            if now >= check_time:
                due.append({
                    "type": "official",
                    "horse": horse.get("name"),
                    "course": race.get("course"),
                    "time": race.get("time"),
                    "check_time": check_time.isoformat(timespec="minutes"),
                })
    return due


def collect_radar_due(picks, now):
    due = []
    race_date = picks.get("date") or date.today().isoformat()
    seen = set()
    for list_name in ("topRated", "topRatedFlat", "topRatedJumps"):
        for horse in picks.get(list_name, []) or []:
            name = horse.get("name") or horse.get("horse")
            course = horse.get("venue") or horse.get("course")
            time_text = horse.get("time")
            key = f"{name}|{course}|{time_text}"
            if not name or key in seen:
                continue
            seen.add(key)
            if result_is_settled(horse.get("result")) or horse.get("radarSettled") is True:
                continue
            race_time = parse_race_datetime(race_date, time_text)
            if not race_time:
                continue
            check_time = race_time + timedelta(minutes=MINUTES_AFTER_RACE)
            if now >= check_time:
                due.append({
                    "type": "radar",
                    "horse": name,
                    "course": course,
                    "time": time_text,
                    "check_time": check_time.isoformat(timespec="minutes"),
                })
    return due


def run_updater():
    env = os.environ.copy()
    env["SIGNAL75_EARLY_REFRESH"] = "1"
    result = subprocess.run(
        ["/usr/bin/python3", os.path.join(REPO_PATH, "scripts", "update-results-mac.py")],
        cwd=REPO_PATH,
        env=env,
        text=True,
    )
    return result.returncode


def main():
    now = datetime.now(UK_TZ)
    if now.hour < ACTIVE_START_HOUR or now.hour >= ACTIVE_END_HOUR:
        log("Outside racing refresh window — no check needed")
        return 0

    try:
        picks = load_picks()
    except Exception as exc:
        log(f"Could not load picks.json: {exc}")
        return 1

    picks_date = picks.get("date")
    today = now.date().isoformat()
    if picks_date != today:
        log(f"picks.json is dated {picks_date}; today is {today}. Skipping early refresh.")
        return 0

    due = collect_official_due(picks, now) + collect_radar_due(picks, now)
    if not due:
        log("No due unsettled races yet")
        return 0

    preview = ", ".join([f"{item['horse']} {item['time']} {item['course']}" for item in due[:6]])
    more = "" if len(due) <= 6 else f" +{len(due)-6} more"
    log(f"{len(due)} due unsettled race(s): {preview}{more}")
    status = run_updater()
    if status:
        log(f"update-results-mac.py failed with status {status}")
        return status
    log("Early results refresh completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
