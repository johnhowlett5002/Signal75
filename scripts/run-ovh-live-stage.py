#!/usr/bin/env python3
"""Run one OVH live pipeline stage after explicit cutover activation."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ENABLE_FILE = Path("/etc/signal75/live-pipeline-enabled")
ENABLE_TOKEN = "SIGNAL75_OVH_LIVE_PIPELINE_ENABLED=YES"
REPO_ROOT = Path(__file__).resolve().parents[1]
FAILURE_ROOT = Path("/srv/signal75/state/scheduler-failures")


def assert_activated(enable_file: Path = ENABLE_FILE) -> None:
    if not enable_file.is_file() or enable_file.read_text().strip() != ENABLE_TOKEN:
        raise RuntimeError("OVH live pipeline is not explicitly enabled")
    if os.environ.get("SIGNAL75_OVH_ROLE") != "primary":
        raise RuntimeError("SIGNAL75_OVH_ROLE is not primary")


def commands(stage: str, date_text: str) -> list[list[str]]:
    python = sys.executable
    scripts = REPO_ROOT / "scripts"
    if stage == "morning":
        return [[python, str(scripts / "run_morning_pipeline.py"), "--date", date_text, "--publish-live"]]
    if stage == "results":
        return [
            [python, str(scripts / "update-results-mac.py")],
            [python, str(scripts / "generate-performance.py")],
            [
                python,
                str(scripts / "master-preflight.py"),
                "--phase",
                "pre-publish",
                "--kind",
                "results",
                "--date",
                date_text,
                "--repair-safe",
            ],
            [
                python,
                str(scripts / "publish-live-files.py"),
                "--kind",
                "results",
                "--date",
                date_text,
                "--message",
                f"Results and performance update {date_text}",
            ],
        ]
    if stage == "learning":
        return [[python, str(scripts / "run_nightly_pipeline.py"), "--date", date_text]]
    raise ValueError(f"unknown live stage: {stage}")


def clear_resolved_failure(stage: str, failure_root: Path = FAILURE_ROOT) -> None:
    (failure_root / f"{stage}.json").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["morning", "results", "learning"])
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--enable-file", type=Path, default=ENABLE_FILE)
    args = parser.parse_args()

    date_text = args.date or datetime.now(ZoneInfo("Europe/London")).date().isoformat()
    if not args.dry_run:
        assert_activated(args.enable_file)
    for command in commands(args.stage, date_text):
        if args.dry_run:
            print(" ".join(command))
            continue
        result = subprocess.run(command, cwd=REPO_ROOT, check=False)
        if result.returncode:
            return result.returncode
    if not args.dry_run:
        clear_resolved_failure(args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
