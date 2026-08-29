#!/usr/bin/env python3
"""
Create a Signal 75 safety snapshot.

This copies important live files into data/safety_snapshots without changing the
public site, picks, proof, scoring, settlement, or automation.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = REPO / "data" / "safety_snapshots"

FILES_TO_COPY = [
    "index.html",
    "app.js",
    "sw.js",
    "picks.json",
    "performance.json",
    "scripts/generate-picks-betfair.py",
    "scripts/update-results-mac.py",
    "scripts/scoring_engine.py",
    "scripts/daily_consensus_overlay.py",
    "scripts/generate-performance.py",
    "scripts/master-preflight.py",
    "scripts/run_morning_pipeline.py",
    "scripts/run_nightly_pipeline.py",
    "scripts/publish-live-files.py",
    "data/today_runners.json",
]


def main():
    snapshot_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_dir = SNAPSHOT_ROOT / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    copied = []
    missing = []

    for rel in FILES_TO_COPY:
        src = REPO / rel
        if not src.exists():
            missing.append(rel)
            continue
        dst = snapshot_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    manifest = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo": str(REPO),
        "copied": copied,
        "missing": missing,
        "note": "Internal safety snapshot. Not public proof. Not used by live site.",
    }

    with (snapshot_dir / "manifest.json").open("w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Created safety snapshot: {snapshot_dir}")
    print(f"Copied {len(copied)} files")
    if missing:
        print("Missing optional files:")
        for rel in missing:
            print(f"  {rel}")


if __name__ == "__main__":
    main()
