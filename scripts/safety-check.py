#!/usr/bin/env python3
"""
Signal 75 safety check.

Read-only checks for the live site files. This does not generate picks, settle
results, write public JSON, or push to GitHub.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PYTHON_FILES = [
    "scripts/generate-picks-betfair.py",
    "scripts/update-results-mac.py",
    "scripts/scoring_engine.py",
    "scripts/daily_consensus_overlay.py",
    "scripts/betfair_client.py",
    "scripts/runner_matcher.py",
    "scripts/generate-performance.py",
    "scripts/late-market-watch.py",
    "scripts/morning-resolve-mac.py",
]

JSON_FILES = [
    "picks.json",
    "performance.json",
    "data/today_runners.json",
]

REQUIRED_PICK_KEYS = {
    "date",
    "mode",
    "flat",
    "jumps",
    "topRatedFlat",
    "topRatedJumps",
    "results",
}

REQUIRED_PERFORMANCE_KEYS = {
    "updatedAt",
    "bettingDays",
    "totalStaked",
    "totalReturn",
    "totalProfit",
    "roi",
    "recentResults",
    "selectionLog",
}


def run(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)


def fail(errors, message):
    errors.append(message)
    print(f"FAIL: {message}")


def ok(message):
    print(f"OK: {message}")


def load_json(rel_path, errors):
    path = REPO / rel_path
    if not path.exists():
        fail(errors, f"{rel_path} is missing")
        return None
    try:
        with path.open() as f:
            return json.load(f)
    except Exception as exc:
        fail(errors, f"{rel_path} is not valid JSON: {exc}")
        return None


def race_type_text(race):
    parts = [
        str(race.get("type", "")),
        str(race.get("race_type", "")),
        str(race.get("race", "")),
        str(race.get("race_name", "")),
    ]
    for horse in race.get("horses", []) or []:
        parts.append(str(horse.get("race_type", "")))
        parts.append(str(horse.get("race", "")))
    return " ".join(parts).lower()


def is_jumps_race(race):
    text = race_type_text(race)
    return any(word in text for word in ("hurdle", "hrd", "chase", "chs", "bumper", "nhf", "jumps"))


def normalise_name(name):
    return " ".join(str(name or "").lower().split())


def check_python(errors):
    existing = [str(REPO / f) for f in PYTHON_FILES if (REPO / f).exists()]
    if not existing:
        fail(errors, "no Python files found for syntax check")
        return
    result = run(["python3", "-m", "py_compile", *existing])
    if result.returncode:
        fail(errors, "Python syntax check failed:\n" + (result.stderr or result.stdout).strip())
    else:
        ok("Python scripts compile")


def check_javascript(errors):
    app = REPO / "app.js"
    if not app.exists():
        fail(errors, "app.js is missing")
        return
    result = run(["node", "--check", "app.js"])
    if result.returncode:
        fail(errors, "app.js syntax check failed:\n" + (result.stderr or result.stdout).strip())
    else:
        ok("app.js syntax is valid")


def check_json(errors):
    for rel in JSON_FILES:
        if (REPO / rel).exists():
            data = load_json(rel, errors)
            if data is not None:
                ok(f"{rel} is valid JSON")


def check_picks_contract(errors):
    picks = load_json("picks.json", errors)
    if not picks:
        return

    missing = sorted(REQUIRED_PICK_KEYS - set(picks))
    if missing:
        fail(errors, "picks.json missing required keys: " + ", ".join(missing))
    else:
        ok("picks.json has required top-level keys")

    flat = picks.get("flat", []) or []
    jumps = picks.get("jumps", []) or []
    radar_flat = picks.get("topRatedFlat", []) or []
    radar_jumps = picks.get("topRatedJumps", []) or []
    results = picks.get("results", {}) or {}

    if not isinstance(flat, list) or not isinstance(jumps, list):
        fail(errors, "picks.json flat/jumps must be lists")
        return

    if len(flat) + len(jumps) > 3:
        fail(errors, "official public picks exceed three")
    else:
        ok("official public pick count is three or fewer")

    if picks.get("noBetDay") and (flat or jumps):
        fail(errors, "noBetDay is true but official flat/jumps picks are present")
    elif picks.get("noBetDay"):
        ok("noBetDay has no official picks")

    for race in flat:
        if is_jumps_race(race):
            fail(errors, f"Flat tab appears to contain a jumps race: {race.get('course','')} {race.get('time','')}")
    if flat:
        ok("Flat official picks do not look like jumps races")

    for race in jumps:
        if not is_jumps_race(race):
            fail(errors, f"Jumps tab appears to contain a flat race: {race.get('course','')} {race.get('time','')}")
    if jumps:
        ok("Jumps official picks look like jumps races")

    for horse in radar_flat:
        if is_jumps_race(horse):
            fail(errors, f"Flat radar appears to contain a jumps horse: {horse.get('name','unknown')}")
    if radar_flat:
        ok("Flat radar does not look like jumps")

    for horse in radar_jumps:
        if not is_jumps_race(horse):
            fail(errors, f"Jumps radar appears to contain a flat horse: {horse.get('name','unknown')}")
    if radar_jumps:
        ok("Jumps radar looks like jumps")

    if not isinstance(results, dict):
        fail(errors, "picks.json results must be an object")
    else:
        for key in ("flat", "jumps", "patentReturn", "patentProfit", "complete"):
            if key not in results:
                fail(errors, f"picks.json results missing {key}")
        ok("picks.json results object has expected fields")


def check_performance_contract(errors):
    perf = load_json("performance.json", errors)
    if not perf:
        return

    missing = sorted(REQUIRED_PERFORMANCE_KEYS - set(perf))
    if missing:
        fail(errors, "performance.json missing required keys: " + ", ".join(missing))
    else:
        ok("performance.json has required top-level keys")

    if perf.get("totalStaked", 0) < 0 or perf.get("totalReturn", 0) < 0:
        fail(errors, "performance totals cannot be negative")
    else:
        ok("performance totals are non-negative")

    if not isinstance(perf.get("selectionLog", []), list):
        fail(errors, "performance selectionLog must be a list")


def check_cache_safety(errors):
    app = (REPO / "app.js").read_text(errors="ignore")
    sw_path = REPO / "sw.js"
    if "picks.json?v=" in app and "performance.json?v=" in app:
        ok("app.js cache-busts picks.json and performance.json")
    else:
        fail(errors, "app.js must cache-bust picks.json and performance.json")

    if sw_path.exists():
        sw = sw_path.read_text(errors="ignore")
        if "picks.json" in sw and "performance.json" in sw and "fetch(e.request)" in sw:
            ok("sw.js treats live JSON as network-first")
        else:
            fail(errors, "sw.js may not be network-first for live JSON")


def check_git_noise():
    result = run(["git", "status", "--short"])
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        ok("git working tree is clean")
        return

    print("INFO: git working tree has local changes:")
    for line in lines:
        print(f"  {line}")
    print("INFO: review these before committing; this is not automatically a failure.")


def main():
    errors = []
    print("Signal 75 safety check")
    print(f"Repo: {REPO}")
    print("-" * 60)

    check_python(errors)
    check_javascript(errors)
    check_json(errors)
    check_picks_contract(errors)
    check_performance_contract(errors)
    check_cache_safety(errors)
    check_git_noise()

    print("-" * 60)
    if errors:
        print(f"Safety check FAILED with {len(errors)} issue(s).")
        return 1
    print("Safety check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
