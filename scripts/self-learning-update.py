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
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
COMBINED_DIR = DATA_DIR / "combined_learning"
RUNNER_CACHE = DATA_DIR / "today_runners.json"
PYTHON_BIN = sys.executable


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
        f"Status: {payload.get('status', 'UNKNOWN')}",
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
    full_field_file = INTEL_DIR / f"full_field_results_{date}.json"
    race_memory_file = INTEL_DIR / f"race_memory_{date}.json"
    result_notes_file = INTEL_DIR / f"race_result_notes_{date}.json"
    head_to_head_file = INTEL_DIR / f"head_to_head_{date}.json"
    rivals_file = INTEL_DIR / f"historic_rivals_{date}.json"
    field_relationships_file = INTEL_DIR / f"field_relationships_{date}.json"
    field_graph_file = INTEL_DIR / f"field_graph_{date}.json"
    field_relative_archive_file = DATA_DIR / f"field_relative_archive_{date}.json"
    combined_file = COMBINED_DIR / f"combined_learning_{date}.json"

    steps: List[Dict[str, Any]] = []

    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Full-field result collection",
            [PYTHON_BIN, "scripts/collect-full-field-results.py", "--date", date],
            [DATA_DIR / f"race_comparison_{date}.json"],
        )
    )

    if args.skip_race_memory:
        steps.append({"name": "Race memory", "status": "skipped", "message": "Skipped by request."})
    elif race_memory_file.exists() and load_json(RUNNER_CACHE, {}).get("date") != date:
        steps.append(
            (planned_step if args.dry_run else run_step)(
                "Race memory result enrichment",
                [
                    PYTHON_BIN,
                    "scripts/build-race-memory.py",
                    "--date",
                    date,
                    "--enrich-results-only",
                ],
                [race_memory_file, full_field_file],
            )
        )
    else:
        step_fn = planned_step if args.dry_run else run_step
        steps.append(
            step_fn(
                "Race memory",
                [PYTHON_BIN, "scripts/build-race-memory.py", "--date", date],
                [daily_file, RUNNER_CACHE],
            )
        )

    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Tipster memory",
            [PYTHON_BIN, "scripts/build-tipster-memory.py", "--date", date, "--csv"],
            [DATA_DIR / f"consensus_overlay_{date}.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Race result notes",
            [PYTHON_BIN, "scripts/build-race-result-notes.py", "--date", date],
            [INTEL_DIR / "result_notes_seed.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Head-to-head memory",
            [PYTHON_BIN, "scripts/build-head-to-head-memory.py", "--date", date],
            [race_memory_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Historic rival memory",
            [PYTHON_BIN, "scripts/build-rival-intelligence.py", "--date", date],
            [race_memory_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Field relationship memory",
            [PYTHON_BIN, "scripts/build-field-relationship-memory.py", "--date", date],
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
            [PYTHON_BIN, "scripts/build-field-graph-intelligence.py", "--date", date],
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
            [PYTHON_BIN, "scripts/build-intelligence-db.py", "--learning-only"],
            [INTEL_DIR / "race_memory_master.jsonl"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Data freshness status",
            [PYTHON_BIN, "scripts/data-freshness-status.py"],
            [INTEL_DIR / "race_memory_master.jsonl"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Rich form settled sync",
            [PYTHON_BIN, "scripts/sync-rich-form-history.py", "--date", date],
            [race_memory_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Post-race diagnosis",
            [PYTHON_BIN, "scripts/post-race-diagnosis.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Continuous training diagnostics",
            [PYTHON_BIN, "scripts/continuous-training.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Combined learning layer",
            [PYTHON_BIN, "scripts/build-combined-learning.py", "--date", date, "--csv"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "SQLite summary tables",
            [PYTHON_BIN, "scripts/build-sqlite-summary-tables.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Collateral form review",
            [PYTHON_BIN, "scripts/collateral-form-review.py"],
            [INTEL_DIR / "head_to_head_master.jsonl", INTEL_DIR / "race_result_notes_master.jsonl"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Score calibration check",
            [PYTHON_BIN, "scripts/score-calibration-check.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Feature importance tracker",
            [PYTHON_BIN, "scripts/feature-importance-tracker.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Winner intelligence",
            [PYTHON_BIN, "scripts/winner-intelligence.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Drift detector",
            [PYTHON_BIN, "scripts/drift-detector.py", "--date", date],
            [combined_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Shadow promotion tracker",
            [PYTHON_BIN, "scripts/shadow-promotion-tracker.py", "--date", date],
            [],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Rich form outcome validation",
            [PYTHON_BIN, "scripts/validate-rich-form-outcomes.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Challenger Lab settlement",
            [PYTHON_BIN, "scripts/settle-challenger-lab.py", "--date", date],
            [daily_file, DATA_DIR / "challenger_lab" / f"challenger_{date}.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Field graph outcome validation",
            [PYTHON_BIN, "scripts/validate-field-graph-outcomes.py", "--date", date],
            [daily_file],
        )
    )
    if not field_relative_archive_file.exists():
        steps.append(
            {
                "name": "Field-relative archive settlement",
                "status": "not_applicable",
                "message": "No field-relative paper archive was generated for this date.",
            }
        )
    else:
        steps.append(
            (planned_step if args.dry_run else run_step)(
                "Field-relative archive settlement",
                [PYTHON_BIN, "scripts/settle-field-relative-archive.py", "--date", date],
                [daily_file, field_relative_archive_file],
            )
        )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Challenger Lab summary",
            [PYTHON_BIN, "scripts/build-challenger-summary.py"],
            [DATA_DIR / "challenger_lab" / f"challenger_{date}.json"],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Master learning summary",
            [PYTHON_BIN, "scripts/master-learning-summary.py", "--date", date],
            [],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Public daily scorecard",
            [PYTHON_BIN, "scripts/generate-public-scorecard.py", "--date", date, "--latest"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Pick quality audit",
            [PYTHON_BIN, "scripts/pick-quality-audit.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Scenario ROI review",
            [PYTHON_BIN, "scripts/scenario-roi-review.py"],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Pipeline health report",
            [PYTHON_BIN, "scripts/pipeline-health-check.py", "--date", date],
            [daily_file],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Report archive housekeeping",
            [PYTHON_BIN, "scripts/archive-learning-reports.py", "--keep-days", "14"],
            [],
        )
    )
    steps.append(
        (planned_step if args.dry_run else run_step)(
            "Dashboard data publish",
            [PYTHON_BIN, "scripts/publish_dashboard_data.py", "--date", date],
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
            "status": "DRY_RUN",
            "steps": steps,
            "combined_summary": {},
            "outputs": {},
        }
        print(render_text(payload))
        return 0

    combined_payload = load_json(combined_file, {})
    critical_steps = {
        "Post-race diagnosis",
        "Challenger Lab settlement",
        "Field-relative archive settlement",
        "Challenger Lab summary",
        "Public daily scorecard",
        "Pipeline health report",
        "Dashboard data publish",
    }
    failed = [step for step in steps if step.get("status") == "failed"]
    critical_skips = [
        step for step in steps
        if step.get("status") == "skipped" and step.get("name") in critical_steps
    ]
    run_status = "DEGRADED" if failed or critical_skips else "OK"
    payload = {
        "date": date,
        "generatedAt": now_iso(),
        "mode": "self_learning_update_only",
        "analysis_only": True,
        "no_live_changes_made": True,
        "status": run_status,
        "failed_steps": [step.get("name") for step in failed],
        "critical_skipped_steps": [step.get("name") for step in critical_skips],
        "steps": steps,
        "combined_summary": combined_payload.get("summary") if isinstance(combined_payload, dict) else {},
        "outputs": {
            "full_field_results": str(full_field_file.relative_to(REPO_ROOT)) if full_field_file.exists() else "",
            "race_memory": str(race_memory_file.relative_to(REPO_ROOT)) if race_memory_file.exists() else "",
            "tipster_memory": str((DATA_DIR / "tipster_intelligence" / f"tipster_memory_{date}.json").relative_to(REPO_ROOT)),
            "race_result_notes": str(result_notes_file.relative_to(REPO_ROOT)) if result_notes_file.exists() else "",
            "post_race_diagnosis": str((DATA_DIR / "diagnosis" / f"diagnosis_{date}.json").relative_to(REPO_ROOT)),
            "head_to_head": str(head_to_head_file.relative_to(REPO_ROOT)) if head_to_head_file.exists() else "",
            "historic_rivals": str(rivals_file.relative_to(REPO_ROOT)) if rivals_file.exists() else "",
            "field_relationships": str(field_relationships_file.relative_to(REPO_ROOT)) if field_relationships_file.exists() else "",
            "field_graph": str(field_graph_file.relative_to(REPO_ROOT)) if field_graph_file.exists() else "",
            "combined_learning": str(combined_file.relative_to(REPO_ROOT)) if combined_file.exists() else "",
            "sqlite_summary_tables": str((DATA_DIR / "combined_learning" / "signal75_learning.sqlite").relative_to(REPO_ROOT)),
            "rich_form_daily_sync": str((INTEL_DIR / "form_history_status.json").relative_to(REPO_ROOT)),
            "collateral_form": str((INTEL_DIR / "collateral_form" / "collateral_form_latest.json").relative_to(REPO_ROOT)),
            "score_calibration": str((DATA_DIR / "calibration" / f"calibration_{date}.json").relative_to(REPO_ROOT)),
            "feature_importance": str((DATA_DIR / "feature_tracking" / f"feature_importance_{date}.json").relative_to(REPO_ROOT)),
            "winner_intelligence": str((DATA_DIR / "winner_intelligence" / f"winners_{date}.json").relative_to(REPO_ROOT)),
            "drift_detection": str((DATA_DIR / "drift_detection" / f"drift_{date}.json").relative_to(REPO_ROOT)),
            "shadow_promotion": str((DATA_DIR / "continuous_training" / "shadow_promotion_log.json").relative_to(REPO_ROOT)),
            "challenger_lab": str((DATA_DIR / "challenger_lab" / "challenger_summary.json").relative_to(REPO_ROOT)),
            "data_freshness": str((INTEL_DIR / "data_freshness_status.json").relative_to(REPO_ROOT)),
            "field_graph_validation": str((DATA_DIR / f"field_graph_validation_{date}.json").relative_to(REPO_ROOT)),
            "field_relative_archive_settled": str((DATA_DIR / f"field_relative_archive_{date}_settled.json").relative_to(REPO_ROOT)),
            "master_learning_summary": str((DATA_DIR / "continuous_training" / "master_learning_summary.json").relative_to(REPO_ROOT)),
            "public_scorecard": str((DATA_DIR / "public_scorecards" / f"scorecard_{date}.json").relative_to(REPO_ROOT)),
            "pick_quality_audit": str((DATA_DIR / f"pick_quality_audit_{date}.json").relative_to(REPO_ROOT)),
            "scenario_roi_review": str((DATA_DIR / "intelligence_reviews" / f"scenario_roi_review_{date}.json").relative_to(REPO_ROOT)),
            "pipeline_health": str((DATA_DIR / f"pipeline_health_{date}.json").relative_to(REPO_ROOT)),
            "report_archives": str((DATA_DIR / "report_archives" / "manifest.json").relative_to(REPO_ROOT)),
            "dashboard_data": str((REPO_ROOT / "dashboard" / "data").relative_to(REPO_ROOT)),
        },
    }

    report_json = COMBINED_DIR / f"self_learning_update_{date}.json"
    report_txt = COMBINED_DIR / f"self_learning_update_{date}.txt"
    write_json(report_json, payload)
    write_text(report_txt, render_text(payload))

    print(f"Self-learning update complete for {date}")
    print(f"Status: {run_status}")
    print(f"Wrote {report_txt.relative_to(REPO_ROOT)}")
    if failed or critical_skips:
        print(
            f"Warning: {len(failed)} failed and {len(critical_skips)} critical skipped "
            "step(s). See report for details."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
