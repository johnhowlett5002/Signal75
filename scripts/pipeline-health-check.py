#!/usr/bin/env python3
"""
Signal 75 pipeline health check.

Read-only checks for the daily automation files, then writes one small JSON
summary. It does not change picks, scoring, settlement, proof, or performance.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config_loader import REPO_ROOT


DATA_DIR = REPO_ROOT / "data"
PICKS_FILE = REPO_ROOT / "picks.json"
PERFORMANCE_FILE = REPO_ROOT / "performance.json"


def load_json(path: Path) -> Optional[Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def iso_mtime(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def is_fresh(path: Path, target_date: str, by_time: time, now: datetime) -> bool:
    """True when file exists and either is fresh today or the deadline has not passed."""
    if not path.exists():
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime)
    if modified.date().isoformat() != target_date:
        return False
    deadline = datetime.combine(modified.date(), by_time)
    return modified <= deadline or now < deadline or modified.date() == now.date()


def file_status(name: str, path: Path, target_date: str, by_time: time, now: datetime) -> Dict[str, Any]:
    exists = path.exists()
    fresh = is_fresh(path, target_date, by_time, now) if exists else False
    return {
        "name": name,
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": exists,
        "fresh_for_date": fresh,
        "modifiedAt": iso_mtime(path),
        "expectedBy": by_time.strftime("%H:%M"),
    }


def proof_status(target_date: str) -> Dict[str, Any]:
    path = DATA_DIR / "proof_checks" / f"check_{target_date}.json"
    data = load_json(path) or {}
    status = str(data.get("status") or "missing").upper() if path.exists() else "MISSING"
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": path.exists(),
        "status": status,
        "proof_consistent": status == "OK",
        "errors": data.get("errors", []) if isinstance(data, dict) else [],
        "warnings": data.get("warnings", []) if isinstance(data, dict) else [],
        "modifiedAt": iso_mtime(path),
    }


def picks_date_ok(target_date: str) -> bool:
    data = load_json(PICKS_FILE)
    return isinstance(data, dict) and str(data.get("date")) == target_date


def build_report(target_date: str, now: datetime) -> Dict[str, Any]:
    checks = {
        "picks": file_status("picks.json", PICKS_FILE, target_date, time(10, 30), now),
        "performance": file_status("performance.json", PERFORMANCE_FILE, target_date, time(21, 30), now),
        "consensus": file_status(
            "consensus overlay",
            DATA_DIR / f"consensus_overlay_{target_date}.json",
            target_date,
            time(10, 30),
            now,
        ),
        "results": file_status(
            "daily results archive",
            DATA_DIR / f"{target_date}.json",
            target_date,
            time(20, 0),
            now,
        ),
        "intelligence": file_status(
            "intelligence review",
            DATA_DIR / "intelligence_reviews" / f"review_{target_date}.json",
            target_date,
            time(9, 30),
            now,
        ),
    }
    proof = proof_status(target_date)

    issues: List[str] = []
    if not checks["picks"]["exists"]:
        issues.append("picks.json is missing")
    elif not picks_date_ok(target_date):
        issues.append("picks.json date does not match target date")

    for key, check in checks.items():
        if key == "picks":
            continue
        if not check["exists"]:
            issues.append(f"{check['name']} is missing")
        elif not check["fresh_for_date"]:
            issues.append(f"{check['name']} was not updated for {target_date}")

    if not proof["exists"]:
        issues.append("proof consistency check is missing")
    elif not proof["proof_consistent"]:
        issues.append(f"proof consistency status is {proof['status']}")

    return {
        "date": target_date,
        "generatedAt": now.isoformat(timespec="seconds"),
        "picks_ran": checks["picks"]["exists"] and picks_date_ok(target_date),
        "results_settled": checks["results"]["exists"] and checks["results"]["fresh_for_date"],
        "consensus_ran": checks["consensus"]["exists"] and checks["consensus"]["fresh_for_date"],
        "intelligence_ran": checks["intelligence"]["exists"] and checks["intelligence"]["fresh_for_date"],
        "performance_updated": checks["performance"]["exists"] and checks["performance"]["fresh_for_date"],
        "proof_consistent": proof["proof_consistent"],
        "checks": checks,
        "proof_check": proof,
        "issues": issues,
        "status": "ok" if not issues else "attention",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Signal 75 daily pipeline health JSON.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Target date, YYYY-MM-DD")
    args = parser.parse_args()

    now = datetime.now()
    report = build_report(args.date, now)
    output = DATA_DIR / f"pipeline_health_{args.date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Pipeline health: {report['status']} | issues: {len(report['issues'])}")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
