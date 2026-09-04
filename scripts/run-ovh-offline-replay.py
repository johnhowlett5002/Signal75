#!/usr/bin/env python3
"""Replay safe morning stages inside an OVH workspace with networking blocked.

This deployment check intentionally skips official pick generation and live
publishing. It reuses transferred pre-race inputs to verify that Debian can run
the local guards, learning, Challenger Lab and dashboard stages end to end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def network_is_blocked() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=1).close()
    except OSError:
        return True
    return False


def run_step(name: str, command: list[str], warning_codes: set[int] | None = None) -> dict[str, Any]:
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True, check=False)
    allowed = warning_codes or set()
    status = "ok" if result.returncode == 0 else ("warning" if result.returncode in allowed else "failed")
    print(f"{name}: {status} (exit {result.returncode})", flush=True)
    return {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "status": status,
        "stdoutTail": (result.stdout or "")[-3000:],
        "stderrTail": (result.stderr or "")[-3000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an offline OVH morning-pipeline replay.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    report_path = REPO / "data" / f"ovh_offline_replay_{args.date}.json"
    protected = [REPO / "picks.json", REPO / "performance.json"]
    before = {str(path.relative_to(REPO)): digest(path) for path in protected}
    blocked = network_is_blocked()
    if not blocked:
        raise SystemExit("Network is available; refusing to run an offline replay.")

    python = sys.executable
    steps: list[dict[str, Any]] = []
    if not args.skip_tests:
        steps.append(run_step("Regression tests", [python, "-m", "pytest", "tests/", "-q"]))
    steps.extend(
        [
            run_step(
                "Master preflight before picks",
                [python, "scripts/master-preflight.py", "--phase", "pre-pick", "--date", args.date, "--repair-safe"],
                {1},
            ),
            {
                "name": "Official pick generation",
                "status": "skipped_offline",
                "reason": "Requires the live Betfair feed; transferred race comparison and picks are replayed instead.",
            },
            run_step("Selection diagnostics", [python, "scripts/selection-diagnostics.py", "--date", args.date], {1}),
            run_step("Rich form daily racecard sync", [python, "scripts/sync-rich-form-history.py", "--date", args.date], {1}),
            run_step(
                "Pick quality audit",
                [python, "scripts/pick-quality-audit.py", "--date", args.date, "--fail-on-flagged"],
            ),
            run_step("Field graph intelligence", [python, "scripts/build-field-graph-intelligence.py", "--date", args.date], {1}),
            run_step("Challenger Lab rebuild", [python, "scripts/generate-challenger-lab.py", "--date", args.date], {1}),
            run_step("Challenger summary rebuild", [python, "scripts/build-challenger-summary.py"], {1}),
            run_step("Dashboard publish", [python, "scripts/publish_dashboard_data.py", "--date", args.date]),
            run_step(
                "Master preflight after picks",
                [python, "scripts/master-preflight.py", "--phase", "post-pick", "--date", args.date, "--repair-safe"],
                {1},
            ),
        ]
    )

    after = {str(path.relative_to(REPO)): digest(path) for path in protected}
    proof_unchanged = before == after
    failures = [step["name"] for step in steps if step.get("status") == "failed"]
    if not proof_unchanged:
        failures.append("Protected proof files changed")
    warnings = [step["name"] for step in steps if step.get("status") == "warning"]
    status = "failed" if failures else ("warning" if warnings else "ok")
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": args.date,
        "role": "ovh-network-disabled-shadow-replay",
        "status": status,
        "networkBlocked": blocked,
        "officialPickGeneration": "skipped_offline",
        "livePublishing": "disabled",
        "proofFilesUnchanged": proof_unchanged,
        "failedSteps": failures,
        "warningSteps": warnings,
        "steps": steps,
    }
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Offline replay: {status}; report={report_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
