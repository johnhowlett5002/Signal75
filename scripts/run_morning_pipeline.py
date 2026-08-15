#!/usr/bin/env python3
"""Signal 75 morning pipeline.

This is the single morning entry point. It keeps existing proven scripts in
place and runs them in the correct order:

1. automation/config/test pre-flight checks
2. pre-pick integrity guard
3. official pick generation
4. diagnostics, quality audit and learning feeds
5. dashboard publish/freshness export

`generate-picks-betfair.py` still owns scoring and official selections.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from pipeline_runner import (
    DATA,
    LOG_DIR,
    REPO_ROOT,
    acquire_lock,
    finish_report,
    log_line,
    now_iso,
    python_cmd,
    release_lock,
    run_command,
    today_text,
)


LOCK_DIR = Path("/tmp/signal75-morning-pipeline.lock")


def anthropic_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    result = subprocess.run(
        ["security", "find-generic-password", "-a", "signal75", "-s", "anthropic-api-key", "-w"],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def pick_generation_env() -> dict:
    env = os.environ.copy()
    key = anthropic_key()
    if key:
        env["ANTHROPIC_API_KEY"] = key
    env.update(
        {
            "SIGNAL75_DIRECT_CONSENSUS_LIMIT": "6",
            "SIGNAL75_DIRECT_CONSENSUS_MAX_WEB_USES": "1",
            "SIGNAL75_DIRECT_CONSENSUS_ONLY": "1",
            "SIGNAL75_RACE_CONSENSUS_LIMIT": "0",
            "SIGNAL75_DISABLE_RACE_CONSENSUS": "1",
            "SIGNAL75_DISABLE_AI_EXPLANATIONS": "1",
        }
    )
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Signal 75 morning pipeline.")
    parser.add_argument("--date", default=today_text())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument(
        "--publish-live",
        action="store_true",
        help="Commit/push public pick files after local dashboard output is verified.",
    )
    args = parser.parse_args()

    started_at = now_iso()
    log_path = LOG_DIR / f"morning_pipeline_{args.date}.log"
    report_path = DATA / f"morning_pipeline_{args.date}.json"

    if not acquire_lock(LOCK_DIR):
        log_line(log_path, "Morning pipeline already running. Exiting.")
        return 0

    steps = []
    try:
        log_line(log_path, f"Morning pipeline started for {args.date}")
        steps.append(
            run_command(
                "Dashboard automation reset",
                python_cmd("dashboard_automation_status.py", "reset"),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
            )
        )
        steps.append(
            run_command(
                "System configuration check",
                python_cmd("validate-system-config.py"),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
            )
        )
        if not args.skip_tests:
            steps.append(
                run_command(
                    "Regression tests",
                    [sys.executable, "-m", "pytest", "tests/", "-q"],
                    log_path=log_path,
                    dry_run=args.dry_run,
                    allow_warning_exit=[1],
                )
            )
        steps.append(
            run_command(
                "System integrity pre-check",
                python_cmd("validate_system_integrity.py"),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
            )
        )
        if steps[-1].get("status") == "failed":
            log_line(log_path, "Integrity errors found before picks. Stopping morning pipeline.")
            return finish_report(
                name="morning",
                date_text=args.date,
                started_at=started_at,
                steps=steps,
                report_path=report_path,
            )

        steps.append(
            run_command(
                "Official pick generation",
                python_cmd("generate-picks-betfair.py"),
                log_path=log_path,
                dry_run=args.dry_run,
                env=None if args.dry_run else pick_generation_env(),
            )
        )
        if steps[-1].get("status") == "failed":
            log_line(log_path, "Official pick generation failed. Stopping morning pipeline.")
            return finish_report(
                name="morning",
                date_text=args.date,
                started_at=started_at,
                steps=steps,
                report_path=report_path,
            )

        steps.append(
            run_command(
                "Selection diagnostics",
                python_cmd("selection-diagnostics.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[REPO_ROOT / "picks.json"],
            )
        )

        steps.append(
            run_command(
                "Rich form daily racecard sync",
                python_cmd("sync-rich-form-history.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[DATA / f"race_comparison_{args.date}.json"],
            )
        )

        steps.append(
            run_command(
                "Pick quality audit",
                python_cmd("pick-quality-audit.py", "--date", args.date, "--fail-on-flagged"),
                log_path=log_path,
                dry_run=args.dry_run,
                required_files=[REPO_ROOT / "picks.json"],
            )
        )
        if steps[-1].get("status") == "failed":
            log_line(log_path, "Pick quality audit blocked publication. Stopping morning pipeline.")
            return finish_report(
                name="morning",
                date_text=args.date,
                started_at=started_at,
                steps=steps,
                report_path=report_path,
            )

        steps.append(
            run_command(
                "Field graph intelligence",
                python_cmd("build-field-graph-intelligence.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[REPO_ROOT / "picks.json"],
            )
        )
        steps.append(
            run_command(
                "Challenger Lab rebuild",
                python_cmd("generate-challenger-lab.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[REPO_ROOT / "picks.json"],
            )
        )
        steps.append(
            run_command(
                "Skin In Game data fetch",
                python_cmd("fetch-skin-in-game-data.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[REPO_ROOT / "picks.json"],
            )
        )
        steps.append(
            run_command(
                "Skin In Game AI decision",
                python_cmd("generate-skin-in-game.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
                required_files=[REPO_ROOT / "picks.json"],
            )
        )
        steps.append(
            run_command(
                "Challenger summary rebuild",
                python_cmd("build-challenger-summary.py"),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
            )
        )

        steps.append(
            run_command(
                "Dashboard publish",
                python_cmd("publish_dashboard_data.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
                required_files=[REPO_ROOT / "picks.json"],
            )
        )

        if args.publish_live:
            steps.append(
                run_command(
                    "Publish live pick files",
                    python_cmd(
                        "publish-live-files.py",
                        "--kind",
                        "picks",
                        "--date",
                        args.date,
                        "--message",
                        f"Generate picks for {args.date}",
                    ),
                    log_path=log_path,
                    dry_run=args.dry_run,
                    required_files=[REPO_ROOT / "picks.json"],
                )
            )

        return finish_report(
            name="morning",
            date_text=args.date,
            started_at=started_at,
            steps=steps,
            report_path=report_path,
        )
    finally:
        release_lock(LOCK_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
