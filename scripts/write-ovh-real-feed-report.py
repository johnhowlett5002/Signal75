#!/usr/bin/env python3
"""Write a credential-free audit report for an OVH real-feed shadow run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def integer_from_log(log_text: str, pattern: str) -> int | None:
    match = re.search(pattern, log_text, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an OVH real-feed shadow run.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--generator-exit", type=int, required=True)
    parser.add_argument("--before-picks-sha", required=True)
    parser.add_argument("--before-performance-sha", required=True)
    args = parser.parse_args()

    log_path = REPO / "logs" / "real_feed_trial.log"
    test_output = REPO / "data" / "picks_test.json"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
    try:
        picks = json.loads(test_output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        picks = {}

    picks_unchanged = digest(REPO / "picks.json") == args.before_picks_sha
    performance_unchanged = digest(REPO / "performance.json") == args.before_performance_sha
    proof_unchanged = picks_unchanged and performance_unchanged
    no_markets = args.generator_exit == 1 and picks.get("source") == "market_data_guard"
    if not proof_unchanged or not test_output.exists():
        status = "failed"
    elif args.generator_exit == 0:
        status = "ok"
    elif no_markets:
        status = "no_markets"
    else:
        status = "failed"

    env_files = [str(path.relative_to(REPO)) for path in REPO.glob(".env*") if path.is_file()]
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": args.date,
        "role": "ovh-real-feed-shadow",
        "status": status,
        "generatorExit": args.generator_exit,
        "markets": integer_from_log(log_text, r"^\s*(\d+) UK WIN markets"),
        "runners": integer_from_log(log_text, r"^\s*(\d+) runners across"),
        "testOutput": "data/picks_test.json",
        "testOutputMode": picks.get("mode"),
        "testOutputSource": picks.get("source"),
        "testOfficialSelections": len(picks.get("flat", [])) + len(picks.get("jumps", [])),
        "officialPickGeneration": "test_mode_only",
        "livePublishing": "disabled",
        "anthropic": "disabled",
        "credentialsStoredOnOvh": False,
        "environmentCredentialFiles": env_files,
        "picksProofUnchanged": picks_unchanged,
        "performanceProofUnchanged": performance_unchanged,
        "proofFilesUnchanged": proof_unchanged,
        "log": "logs/real_feed_trial.log",
    }
    report_dir = REPO / "data" / "deployment_state" / "real_feed_trials"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"trial_{args.date}_{datetime.now().strftime('%H%M%S')}.json"
    report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"REPORT_PATH={report_path}")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
