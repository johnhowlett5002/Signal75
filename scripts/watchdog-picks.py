#!/usr/bin/env python3
"""
Signal 75 morning picks watchdog.

Read-only unless today's picks are stale. If picks.json is not dated today
after the normal morning run window, this asks the existing morning runner to
generate and publish fresh picks.
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PICKS_JSON = REPO / "picks.json"
RUNNERS_JSON = REPO / "data" / "today_runners.json"
MORNING_RUNNER = Path.home() / "signal75-run-picks.sh"
LOCK_DIR = Path("/tmp/signal75-picks-watchdog.lock")


def log(message):
    print(f"[Signal75 watchdog {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def json_date(path):
    try:
        with path.open() as f:
            return json.load(f).get("date", "")
    except Exception:
        return ""


def process_running(pattern):
    result = subprocess.run(["/usr/bin/pgrep", "-f", pattern], capture_output=True, text=True)
    return result.returncode == 0


def acquire_lock():
    try:
        LOCK_DIR.mkdir()
        return True
    except FileExistsError:
        return False


def release_lock():
    try:
        LOCK_DIR.rmdir()
    except OSError:
        pass


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    picks_date = json_date(PICKS_JSON)
    runners_date = json_date(RUNNERS_JSON)

    log(f"Check started. picks={picks_date or 'missing'} runners={runners_date or 'missing'} expected={today}")

    if picks_date == today and runners_date == today:
        log("Fresh picks already exist. Nothing to do.")
        return 0

    if process_running("generate-picks-betfair.py|signal75-run-picks.sh"):
        log("Morning generator is already running. Leaving it alone.")
        return 0

    if not MORNING_RUNNER.exists():
        log(f"ERROR: missing runner {MORNING_RUNNER}")
        return 1

    if not acquire_lock():
        log("Another watchdog run is active. Exiting.")
        return 0

    try:
        log("Fresh picks are missing or stale. Running normal morning picks script now.")
        result = subprocess.run([str(MORNING_RUNNER)], cwd=str(REPO))
        if result.returncode != 0:
            log(f"ERROR: morning runner failed with status {result.returncode}")
            return result.returncode

        new_picks_date = json_date(PICKS_JSON)
        new_runners_date = json_date(RUNNERS_JSON)
        if new_picks_date != today or new_runners_date != today:
            log(f"ERROR: runner finished but files are still stale. picks={new_picks_date} runners={new_runners_date}")
            return 1

        log("Watchdog recovered fresh picks successfully.")
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())
