#!/usr/bin/env python3
"""Signal 75 nightly pipeline.

This is the single nightly entry point. It settles official proof first, then
runs the learning/update stack and publishes dashboard data at the end.
"""

from __future__ import annotations

import argparse
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


LOCK_DIR = Path("/tmp/signal75-nightly-pipeline.lock")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Signal 75 nightly pipeline.")
    parser.add_argument("--date", default=today_text())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-self-learning",
        action="store_true",
        help="Settle proof/dashboard only. Useful for emergency result repair.",
    )
    args = parser.parse_args()

    started_at = now_iso()
    log_path = LOG_DIR / f"nightly_pipeline_{args.date}.log"
    report_path = DATA / f"nightly_pipeline_{args.date}.json"
    daily_file = DATA / f"{args.date}.json"

    if not acquire_lock(LOCK_DIR):
        log_line(log_path, "Nightly pipeline already running. Exiting.")
        return 0

    steps = []
    try:
        log_line(log_path, f"Nightly pipeline started for {args.date}")
        steps.append(
            run_command(
                "Official result settlement",
                python_cmd("update-results-mac.py"),
                log_path=log_path,
                dry_run=args.dry_run,
            )
        )

        steps.append(
            run_command(
                "Performance and ROI proof",
                python_cmd("generate-performance.py"),
                log_path=log_path,
                dry_run=args.dry_run,
            )
        )

        if not args.skip_self_learning:
            steps.append(
                run_command(
                    "Self-learning update",
                    python_cmd("self-learning-update.py", "--date", args.date),
                    log_path=log_path,
                    dry_run=args.dry_run,
                    required_files=[daily_file],
                    allow_warning_exit=[1],
                )
            )

        steps.append(
            run_command(
                "Master post-race preflight",
                python_cmd("master-preflight.py", "--phase", "post-race", "--date", args.date, "--repair-safe"),
                log_path=log_path,
                dry_run=args.dry_run,
                allow_warning_exit=[1],
            )
        )
        if steps[-1].get("status") == "failed":
            log_line(log_path, "Post-race master preflight blocked dashboard publication.")
            return finish_report(
                name="nightly",
                date_text=args.date,
                started_at=started_at,
                steps=steps,
                report_path=report_path,
            )

        steps.append(
            run_command(
                "Dashboard publish",
                python_cmd("publish_dashboard_data.py", "--date", args.date),
                log_path=log_path,
                dry_run=args.dry_run,
            )
        )

        return finish_report(
            name="nightly",
            date_text=args.date,
            started_at=started_at,
            steps=steps,
            report_path=report_path,
        )
    finally:
        release_lock(LOCK_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
