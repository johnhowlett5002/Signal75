#!/usr/bin/env python3
"""
Signal 75 — Zero Proof Tracker
Run this to reset all historical data and start fresh.
Usage: python3 ~/Signal75/scripts/zero-proof.py
"""
import os, json, glob, subprocess
from datetime import datetime, timezone

REPO_PATH = os.path.expanduser("~/Signal75")

def main():
    print("⚠️  This will delete all historical data and reset performance.json to zero.")
    confirm = input("Type YES to confirm: ").strip()
    if confirm != "YES":
        print("Aborted.")
        return

    # Delete all data files
    data_files = glob.glob(os.path.join(REPO_PATH, "data", "*.json"))
    for f in data_files:
        os.remove(f)
        print(f"🗑  Deleted {os.path.basename(f)}")

    # Reset performance.json
    perf = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "totalDays": 0,
        "completeDays": 0,
        "wins": 0,
        "places": 0,
        "losses": 0,
        "totalStaked": 0.0,
        "totalReturned": 0.0,
        "totalProfit": 0.0,
        "roi": 0.0,
        "winRate": 0.0,
        "currentStreak": 0,
        "bestStreak": 0,
        "days": []
    }
    with open(os.path.join(REPO_PATH, "performance.json"), "w") as f:
        json.dump(perf, f, indent=2)
    print("✅ performance.json reset to zero")

    # Commit and push
    cmds = [
        ["git", "-C", REPO_PATH, "add", "-A"],
        ["git", "-C", REPO_PATH, "commit", "-m", "Zero proof tracker — fresh start"],
        ["git", "-C", REPO_PATH, "push"],
    ]
    for cmd in cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            print(f"⚠️  {r.stderr.strip()}")
    print("🏇 Done — proof tracker zeroed and pushed.")

if __name__ == "__main__":
    main()
