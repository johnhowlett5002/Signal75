#!/usr/bin/env python3
"""Archive old dated Signal 75 report files into monthly bundles.

This keeps the repo from filling with hundreds of daily receipt files while
preserving the content for future reviews. It does not touch picks, proof,
settlement, scoring, app files, or the master/profile learning files used by
the live system.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
ARCHIVE = DATA / "report_archives"
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


FAMILIES = [
    ("continuous_training", "training_log_"),
    ("intelligence_reviews", "review_"),
    ("intelligence_reviews", "june14_idea_lab_"),
    ("intelligence_reviews", "scenario_roi_review_"),
    ("intelligence_reviews", "roi_diagnostics_"),
    ("horse_intelligence", "race_intelligence_"),
    ("horse_intelligence", "race_memory_"),
    ("horse_intelligence", "head_to_head_"),
    ("horse_intelligence", "historic_rivals_"),
    ("horse_intelligence", "race_result_notes_"),
    ("combined_learning", "combined_learning_"),
    ("alerts", "alerts_"),
    ("winner_intelligence", "winner_intelligence_"),
    ("feature_tracking", "feature_importance_"),
    ("drift_detection", "drift_detection_"),
    ("calibration", "score_calibration_"),
    ("proof_checks", "check_"),
    ("diagnosis", "diagnosis_"),
    ("public_scorecards", "public_scorecard_"),
    ("selection_diagnostics", "selection_diagnostics_"),
    ("tipster_intelligence", "tipster_intelligence_"),
    ("", "consensus_overlay_"),
    ("", "consensus_shadow_"),
    ("", "late_value_shadow_"),
    ("", "race_comparison_"),
    ("", "script_tipster_overlay_"),
    ("", "confirmed_tips_"),
    ("", "pipeline_health_"),
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_date(path: Path) -> str | None:
    match = DATE_RE.search(path.name)
    return match.group(1) if match else None


def family_paths(folder: str, prefix: str) -> list[Path]:
    root = DATA / folder if folder else DATA
    if not root.exists():
        return []
    return sorted(
        path for path in root.glob(f"{prefix}*")
        if path.is_file() and path.suffix in {".json", ".txt", ".md"} and parse_date(path)
    )


def read_payload(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        try:
            return {"content_type": "json", "payload": json.loads(path.read_text(encoding="utf-8"))}
        except json.JSONDecodeError:
            return {"content_type": "text", "text": path.read_text(encoding="utf-8", errors="replace")}
    return {"content_type": "text", "text": path.read_text(encoding="utf-8", errors="replace")}


def archive_name(folder: str, prefix: str) -> str:
    label = folder or "data_root"
    return f"{label}__{prefix.rstrip('_')}.jsonl"


def line_exists(archive_path: Path, source_path: str) -> bool:
    if not archive_path.exists():
        return False
    with archive_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("source_path") == source_path:
                return True
    return False


def validate_jsonl(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            json.loads(line)
            count += 1
    return count


def build_manifest(summary: dict[str, Any]) -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generatedAt": now_iso(),
        "purpose": "Monthly archives of old dated report snapshots. Current/latest files stay in normal locations.",
        "safe_to_read": True,
        "live_scoring_impact": "none",
        "summary": summary,
    }
    (ARCHIVE / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive old dated Signal 75 report files.")
    parser.add_argument("--keep-days", type=int, default=14, help="Keep this many recent days in normal folders.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cutoff = (datetime.now() - timedelta(days=args.keep_days)).date()
    archived_at = now_iso()
    to_archive: dict[tuple[str, str, str], list[Path]] = defaultdict(list)
    kept = 0

    for folder, prefix in FAMILIES:
        for path in family_paths(folder, prefix):
            date_text = parse_date(path)
            if not date_text:
                continue
            try:
                file_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except ValueError:
                continue
            if file_date >= cutoff:
                kept += 1
                continue
            month = date_text[:7]
            to_archive[(month, folder, prefix)].append(path)

    summary = {
        "cutoffDate": cutoff.isoformat(),
        "keepDays": args.keep_days,
        "kept_recent_files": kept,
        "archived_files": 0,
        "archives": {},
        "dry_run": args.dry_run,
    }

    for (month, folder, prefix), paths in sorted(to_archive.items()):
        archive_dir = ARCHIVE / month
        archive_path = archive_dir / archive_name(folder, prefix)
        archive_key = str(archive_path.relative_to(REPO_ROOT))
        summary["archives"].setdefault(archive_key, {"added": 0, "already_present": 0})
        if args.dry_run:
            summary["archives"][archive_key]["added"] += len(paths)
            summary["archived_files"] += len(paths)
            continue

        archive_dir.mkdir(parents=True, exist_ok=True)
        with archive_path.open("a", encoding="utf-8") as handle:
            for path in paths:
                source_path = str(path.relative_to(REPO_ROOT))
                if line_exists(archive_path, source_path):
                    summary["archives"][archive_key]["already_present"] += 1
                else:
                    record = {
                        "source_path": source_path,
                        "file_date": parse_date(path),
                        "archived_at": archived_at,
                    }
                    record.update(read_payload(path))
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                    summary["archives"][archive_key]["added"] += 1
                path.unlink()
                summary["archived_files"] += 1
        validate_jsonl(archive_path)

    build_manifest(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
