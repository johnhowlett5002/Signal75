#!/usr/bin/env python3
"""Audit a staged OVH release without activating the production pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path


DATABASES = (
    "data/horse_intelligence/form_history.sqlite",
    "data/horse_intelligence/signal75_history.sqlite",
    "data/combined_learning/signal75_learning.sqlite",
)
RUNTIME_FILES = (
    "data/horse_intelligence/head_to_head_master.jsonl",
    "data/horse_intelligence/head_to_head_profiles.json",
    "data/horse_intelligence/historic_rival_profiles.json",
    "data/horse_intelligence/field_relationship_profiles.json",
)
PRODUCTION_TIMERS = (
    "signal75-morning.timer",
    "signal75-results.timer",
    "signal75-learning.timer",
)


def systemctl(action: str, unit: str) -> str:
    result = subprocess.run(
        ["systemctl", action, unit], capture_output=True, text=True, check=False
    )
    return (result.stdout or result.stderr).strip()


def audit(root: Path) -> dict:
    root = root.resolve()
    checks: dict[str, object] = {}
    failures: list[str] = []

    checks["root"] = str(root)
    checks["live_path_absent"] = not Path("/srv/signal75/live").exists()
    checks["activation_marker_absent"] = not Path("/etc/signal75/live-pipeline-enabled").exists()
    if not checks["live_path_absent"]:
        failures.append("production live path already exists")
    if not checks["activation_marker_absent"]:
        failures.append("production activation marker already exists")

    database_checks = {}
    for relative in DATABASES:
        path = root / relative
        details = {
            "exists": path.is_file(),
            "is_symlink": path.is_symlink(),
            "writable": os.access(path, os.W_OK),
        }
        if path.is_file():
            with sqlite3.connect(path) as connection:
                details["quick_check"] = connection.execute("PRAGMA quick_check").fetchone()[0]
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.execute("CREATE TABLE __signal75_cutover_probe (value TEXT)")
                    connection.execute("DROP TABLE __signal75_cutover_probe")
                    connection.rollback()
                    details["write_probe"] = "ok"
                except sqlite3.Error as exc:
                    connection.rollback()
                    details["write_probe"] = str(exc)
        database_checks[relative] = details
        if not details["exists"] or details["is_symlink"] or not details["writable"]:
            failures.append(f"database is not a writable release copy: {relative}")
        if details.get("quick_check") != "ok":
            failures.append(f"database quick_check failed: {relative}")
        if details.get("write_probe") != "ok":
            failures.append(f"database write probe failed: {relative}")
    checks["databases"] = database_checks

    runtime_checks = {}
    for relative in RUNTIME_FILES:
        path = root / relative
        runtime_checks[relative] = {
            "exists": path.is_file(),
            "is_symlink": path.is_symlink(),
            "bytes": path.stat().st_size if path.is_file() else 0,
        }
        if not path.is_file() or path.is_symlink():
            failures.append(f"runtime input is not a release copy: {relative}")
    checks["runtime_files"] = runtime_checks

    timer_checks = {}
    for timer in PRODUCTION_TIMERS:
        enabled = systemctl("is-enabled", timer)
        active = systemctl("is-active", timer)
        timer_checks[timer] = {"enabled": enabled, "active": active}
        if enabled != "disabled" or active != "inactive":
            failures.append(f"production timer is not safely disabled: {timer}")
    checks["production_timers"] = timer_checks

    checks["required_entrypoints"] = all(
        (root / relative).is_file()
        for relative in (
            "scripts/run-ovh-live-stage.py",
            "scripts/generate-picks-betfair.py",
            "scripts/update-results-mac.py",
            "scripts/self-learning-update.py",
        )
    )
    if not checks["required_entrypoints"]:
        failures.append("one or more production entrypoints are missing")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "ready_for_controlled_cutover" if not failures else "blocked",
        "production_activated": False,
        "checks": checks,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.root)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "ready_for_controlled_cutover" else 2


if __name__ == "__main__":
    raise SystemExit(main())
