#!/usr/bin/env python3
"""Open a small morning summary of Signal 75 continuous-learning findings."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = REPO_ROOT / "data" / "continuous_training"
DEFAULT_OUTPUT = Path.home() / "SIGNAL 75 MORNING FINDINGS.txt"


PLAIN_LABELS = {
    "SURFACE_DATA_MISSING": "Surface record missing",
    "UNPROVEN_COURSE": "Course record unproven",
    "UNPROVEN_GOING": "Going record unproven",
    "UNPROVEN_TRIP": "Trip or distance record unproven",
    "SAME_COURSE_CLUSTER": "Too many selections from the same course",
    "POOR_RECENT_FORM": "Poor recent form warning",
    "SHADOW_BEAT_LIVE_RULE": "Shadow rule beat live rule",
    "FULL_CRITERIA_MET_AND_PLACED": "Strong Watchlist evidence",
}


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def money(value: Any) -> str:
    try:
        return f"+£{float(value):.2f}"
    except (TypeError, ValueError):
        return "+£0.00"


def pct(value: Any) -> str:
    if isinstance(value, str) and value.endswith("%"):
        return value
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def render_summary() -> str:
    cumulative = load_json(TRAINING_DIR / "cumulative_findings.json", {})
    candidates = load_json(TRAINING_DIR / "roi_improvement_candidates.json", {})

    finding_counts: Dict[str, int] = cumulative.get("finding_counts") or cumulative.get("finding_totals") or {}
    candidate_items: List[Dict[str, Any]] = candidates.get("items") or []
    candidate_by_finding = {item.get("finding"): item for item in candidate_items}

    lines = [
        "SIGNAL 75 - MORNING FINDINGS",
        datetime.now().strftime("%A %d %B %Y"),
        "",
        "This is learning only. It does not change picks, proof, or results.",
        "",
        f"Days analysed: {len(cumulative.get('analysed_dates') or [])}",
        f"Official place rate: {pct(cumulative.get('official_place_rate_percent') or cumulative.get('official_place_rate'))}",
        f"Watchlist place rate: {pct(cumulative.get('watchlist_place_rate_percent') or cumulative.get('watchlist_place_rate'))}",
        "",
        "Numbered findings:",
    ]

    if not finding_counts:
        lines.append("1. No continuous-learning findings recorded yet.")
    else:
        ordered = sorted(finding_counts.items(), key=lambda row: (-row[1], row[0]))
        for idx, (finding, count) in enumerate(ordered[:10], start=1):
            item = candidate_by_finding.get(finding, {})
            evidence = item.get("evidence_so_far") or {}
            label = PLAIN_LABELS.get(finding, finding.replace("_", " ").title())
            status = item.get("status") or "watching"
            saving = evidence.get("theoretical_roi_impact") or money(item.get("estimated_saving_if_avoided", 0))
            lines.append(f"{idx}. {label} - {count} time(s) - {status} - possible saving {saving}")

    lines.extend(
        [
            "",
            "14 June review list:",
        ]
    )

    review_items = [item for item in candidate_items if item.get("status")]
    if not review_items:
        lines.append("1. No ROI improvement candidates yet.")
    else:
        for idx, item in enumerate(review_items[:8], start=1):
            label = PLAIN_LABELS.get(str(item.get("finding")), str(item.get("finding", "")).replace("_", " ").title())
            lines.append(f"{idx}. {label} - {item.get('status')} - manual approval required")

    lines.extend(
        [
            "",
            "Reminder:",
            "Only obvious credibility failures should be fixed before 14 June.",
            "Normal findings stay as evidence until the review.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Write and optionally open the Signal 75 morning findings note.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Text file to write.")
    parser.add_argument("--open", action="store_true", help="Open the note on screen after writing it.")
    args = parser.parse_args()

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_summary(), encoding="utf-8")

    if args.open:
        subprocess.run(["/usr/bin/open", "-a", "TextEdit", str(output)], check=False)

    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
