#!/usr/bin/env python3
"""Run Signal 75 self-learning updates.

This is analysis/storage only. It refreshes the learning files that help Signal
75 improve over time, but it never changes live selections, proof, results
maths, settlement, unlock logic, app data, or public JSON contracts.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
COMBINED_DIR = DATA_DIR / "combined_learning"
RUNNER_CACHE = DATA_DIR / "today_runners.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def default_date() -> str:
    runner_cache = load_json(RUNNER_CACHE, {})
    cache_date = runner_cache.get("date")
    if cache_date and (DATA_DIR / f"{cache_date}.json").exists():
        return str(cache_date)
    today = datetime.now().strftime("%Y-%m-%d")
    if (DATA_DIR / f"{today}.json").exists():
        return today
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def run_step(name: str, command: List[str], required_files: List[Path] | None = None) -> Dict[str, Any]:
    missing = [str(path.relative_to(REPO_ROOT)) for path in required_files or [] if not path.exists()]
    if missing:
        return {
            "name": name,
            "status": "skipped",
            "missing": missing,
            "message": "Required input was not available yet.",
        }

    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "name": name,
        "status": "ok" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "command": command,
        "stdout": result.stdout.strip()[-4000:],
        "stderr": result.stderr.strip()[-4000:],
    }


def planned_step(name: str, command: List[str], required_files: List[Path] | None = None) -> Dict[str, Any]:
    missing = [str(path.relative_to(REPO_ROOT)) for path in required_files or [] if not path.exists()]
    return {
        "name": name,
        "status": "would_run" if not missing else "would_skip",
        "missing": missing,
        "command": command,
    }


def render_text(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - SELF LEARNING UPDATE",
        payload["date"],
        "",
        "This is learning only. It does not change picks, proof, results, unlock, or scoring.",
        "",
        "Steps:",
    ]
    for idx, step in enumerate(payload.get("steps", []), start=1):
        status = step.get("status", "").upper()
        line = f"{idx}. {step.get('name')} - {status}"
        if step.get("missing"):
            line += f" - missing {', '.join(step['missing'])}"
        lines.append(line)

    summary = payload.get("combined_summary") or {}
    if summary:
        lines.extend(
            [
                "",
                "Combined learning:",
                f"- Runners joined: {summary.get('runner_count', 0)}",
                f"- Official: {summary.get('official_count', 0)}",
                f"- Watchlist: {summary.get('watchlist_count', 0)}",
                f"- Tipster-only: {summary.get('tipster_only_count', 0)}",
                f"- Grandad memory: {summary.get('with_grandad_memory', 0)}",
                f"- Historic rivals: {summary.get('with_historic_rivals', 0)}",
                f"- Tipster intelligence: {summary.get('with_tipster_intelligence', 0)}",
                f"- Rich result notes: {summary.get('with_result_notes', 0)}",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Signal 75 self-learning updates.")
    parser.add_argument("--date", default=default_date())
    parser.add_argument("--skip-race-memory", action="store_true", help="Use existing race-memory files only.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without changing files.")
    args = parser.parse_args()

    date = args.date
    daily_file = DATA_DIR / f"{date}.json"
    race_memory_file = INTEL_DIR / f"race_memory_{date}.json"
    result_notes_file = INTEL_DIR / f"race_result_notes_{date}.json"
    head_to_head_file = INTEL_DIR / f"head_to_head_{date}.json"
    rivals_file = INTEL_DIR / f"historic_rivals_{date}.json"
    field_relationships_file = INTEL_DIR / f"field_relationships_{date}.json"
    field_graph_file = INTEL_DIR / f"field_graph_{date}.json"
    combined_file = COMBINED_DIR / f"combined_learning_{date}.json"

    steps: List[Dict[str, Any]] = []

    if args.skip_race_memory:
        steps.append({"name": "Race memory", "status": "skipped", "message": "Skipped by request."})
    else:
        step_fn = planned_step if args.dry_run else run_step
        steps.append(
            step_fn(
                "Race memory",
                ["/usr/bin/python3", "scripts/build-race-memory.py", "--date", date],
                [daily_file, RUNNER_CACHE],
            )
        )

    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Tipster memory",
            ["/usr/bin/python3", "scripts/build-tipster-memory.py", "--date", date, "--csv"],
            [DATA_DIR / f"consensus_overlay_{date}.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Race result notes",
            ["/usr/bin/python3", "scripts/build-race-result-notes.py", "--date", date],
            [INTEL_DIR / "result_notes_seed.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Head-to-head memory",
            ["/usr/bin/python3", "scripts/build-head-to-head-memory.py", "--date", date],
            [race_memory_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Historic rival memory",
            ["/usr/bin/python3", "scripts/build-rival-intelligence.py", "--date", date],
            [race_memory_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Field relationship memory",
            ["/usr/bin/python3", "scripts/build-field-relationship-memory.py", "--date", date],
            [
                INTEL_DIR / "head_to_head_profiles.json",
                INTEL_DIR / "historic_rival_profiles.json",
                INTEL_DIR / "race_result_note_profiles.json",
            ],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Field graph intelligence",
            ["/usr/bin/python3", "scripts/build-field-graph-intelligence.py", "--date", date],
            [
                INTEL_DIR / "race_memory_master.jsonl",
                INTEL_DIR / "head_to_head_master.jsonl",
                INTEL_DIR / "historic_rival_master.jsonl",
            ],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Local intelligence database",
            ["/usr/bin/python3", "scripts/build-intelligence-db.py"],
            [INTEL_DIR / "race_memory_master.jsonl"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Post-race diagnosis",
            ["/usr/bin/python3", "scripts/post-race-diagnosis.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Continuous training diagnostics",
            ["/usr/bin/python3", "scripts/continuous-training.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Combined learning layer",
            ["/usr/bin/python3", "scripts/build-combined-learning.py", "--date", date, "--csv"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Collateral form review",
            ["/usr/bin/python3", "scripts/collateral-form-review.py"],
            [INTEL_DIR / "head_to_head_master.jsonl", INTEL_DIR / "race_result_notes_master.jsonl"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Score calibration check",
            ["/usr/bin/python3", "scripts/score-calibration-check.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Feature importance tracker",
            ["/usr/bin/python3", "scripts/feature-importance-tracker.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Winner intelligence",
            ["/usr/bin/python3", "scripts/winner-intelligence.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Drift detector",
            ["/usr/bin/python3", "scripts/drift-detector.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Shadow promotion tracker",
            ["/usr/bin/python3", "scripts/shadow-promotion-tracker.py", "--date", date],
            [],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Rich form outcome validation",
            ["/usr/bin/python3", "scripts/validate-rich-form-outcomes.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Challenger Lab summary",
            ["/usr/bin/python3", "scripts/build-challenger-summary.py"],
            [DATA_DIR / "challenger_lab" / f"challenger_{date}.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Field graph outcome validation",
            ["/usr/bin/python3", "scripts/validate-field-graph-outcomes.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Master learning summary",
            ["/usr/bin/python3", "scripts/master-learning-summary.py", "--date", date],
            [],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Public daily scorecard",
            ["/usr/bin/python3", "scripts/generate-public-scorecard.py", "--date", date, "--latest"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Pick quality audit",
            ["/usr/bin/python3", "scripts/pick-quality-audit.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Scenario ROI review",
            ["/usr/bin/python3", "scripts/scenario-roi-review.py"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Pipeline health report",
            ["/usr/bin/python3", "scripts/pipeline-health-check.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Report archive housekeeping",
            ["/usr/bin/python3", "scripts/archive-learning-reports.py", "--keep-days", "14"],
            [],
        )
    )

    if args.dry_run:
        payload = {
            "date": date,
            "generatedAt": now_iso(),
            "mode": "self_learning_update_dry_run",
            "analysis_only": True,
            "no_live_changes_made": True,
            "steps": steps,
            "combined_summary": {},
            "outputs": {},
        }
        print(render_text(payload))
        return 0

    combined_payload = load_json(combined_file, {})
    payload = {
        "date": date,
        "generatedAt": now_iso(),
        "mode": "self_learning_update_only",
        "analysis_only": True,
        "no_live_changes_made": True,
        "steps": steps,
        "combined_summary": combined_payload.get("summary") if isinstance(combined_payload, dict) else {},
        "outputs": {
            "race_memory": str(race_memory_file.relative_to(REPO_ROOT)) if race_memory_file.exists() else "",
            "tipster_memory": str((DATA_DIR / "tipster_intelligence" / f"tipster_memory_{date}.json").relative_to(REPO_ROOT)),
            "race_result_notes": str(result_notes_file.relative_to(REPO_ROOT)) if result_notes_file.exists() else "",
            "post_race_diagnosis": str((DATA_DIR / "diagnosis" / f"diagnosis_{date}.json").relative_to(REPO_ROOT)),
            "head_to_head": str(head_to_head_file.relative_to(REPO_ROOT)) if head_to_head_file.exists() else "",
            "historic_rivals": str(rivals_file.relative_to(REPO_ROOT)) if rivals_file.exists() else "",
            "field_relationships": str(field_relationships_file.relative_to(REPO_ROOT)) if field_relationships_file.exists() else "",
            "field_graph": str(field_graph_file.relative_to(REPO_ROOT)) if field_graph_file.exists() else "",
            "combined_learning": str(combined_file.relative_to(REPO_ROOT)) if combined_file.exists() else "",
            "collateral_form": str((INTEL_DIR / "collateral_form" / "collateral_form_latest.json").relative_to(REPO_ROOT)),
            "score_calibration": str((DATA_DIR / "calibration" / f"calibration_{date}.json").relative_to(REPO_ROOT)),
            "feature_importance": str((DATA_DIR / "feature_tracking" / f"feature_importance_{date}.json").relative_to(REPO_ROOT)),
            "winner_intelligence": str((DATA_DIR / "winner_intelligence" / f"winners_{date}.json").relative_to(REPO_ROOT)),
            "drift_detection": str((DATA_DIR / "drift_detection" / f"drift_{date}.json").relative_to(REPO_ROOT)),
            "shadow_promotion": str((DATA_DIR / "continuous_training" / "shadow_promotion_log.json").relative_to(REPO_ROOT)),
            "challenger_lab": str((DATA_DIR / "challenger_lab" / "challenger_summary.json").relative_to(REPO_ROOT)),
            "field_graph_validation": str((DATA_DIR / f"field_graph_validation_{date}.json").relative_to(REPO_ROOT)),
            "master_learning_summary": str((DATA_DIR / "continuous_training" / "master_learning_summary.json").relative_to(REPO_ROOT)),
            "public_scorecard": str((DATA_DIR / "public_scorecards" / f"scorecard_{date}.json").relative_to(REPO_ROOT)),
            "pick_quality_audit": str((DATA_DIR / f"pick_quality_audit_{date}.json").relative_to(REPO_ROOT)),
            "scenario_roi_review": str((DATA_DIR / "intelligence_reviews" / f"scenario_roi_review_{date}.json").relative_to(REPO_ROOT)),
            "pipeline_health": str((DATA_DIR / f"pipeline_health_{date}.json").relative_to(REPO_ROOT)),
            "report_archives": str((DATA_DIR / "report_archives" / "manifest.json").relative_to(REPO_ROOT)),
        },
    }

    report_json = COMBINED_DIR / f"self_learning_update_{date}.json"
    report_txt = COMBINED_DIR / f"self_learning_update_{date}.txt"
    write_json(report_json, payload)
    write_text(report_txt, render_text(payload))

    failed = [step for step in steps if step.get("status") == "failed"]
    print(f"Self-learning update complete for {date}")
    print(f"Wrote {report_txt.relative_to(REPO_ROOT)}")
    if failed:
        print(f"Warning: {len(failed)} step(s) failed. See report for details.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
