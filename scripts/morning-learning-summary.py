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
    "SURFACE_DATA_MISSING": "We did not have enough surface evidence",
    "UNPROVEN_COURSE": "We did not have enough course evidence",
    "UNPROVEN_GOING": "We did not have enough ground/going evidence",
    "UNPROVEN_TRIP": "We did not have enough distance evidence",
    "SAME_COURSE_CLUSTER": "Too many horses came from the same racecourse",
    "POOR_RECENT_FORM": "A horse had poor recent form",
    "SHADOW_BEAT_LIVE_RULE": "A test rule would have done better than the live rule",
    "FULL_CRITERIA_MET_AND_PLACED": "Watchlist horses are still performing well",
    "FALSE_CONSENSUS": "Tipster support looked stronger than it really was",
    "THIN_FORM_RECORD": "A horse had very little recent evidence",
}

PLAIN_MEANINGS = {
    "SURFACE_DATA_MISSING": "We need to know whether the horse has proved itself on this type of racing surface.",
    "UNPROVEN_COURSE": "The horse has not clearly proved it likes this course yet.",
    "UNPROVEN_GOING": "The horse has not clearly proved it handles today's ground conditions.",
    "UNPROVEN_TRIP": "The horse has not clearly proved it stays or suits today's distance.",
    "SAME_COURSE_CLUSTER": "Several selections from one course can make the day too dependent on one track or weather pattern.",
    "POOR_RECENT_FORM": "Recent runs were weak enough that the horse should probably need stronger proof before becoming official.",
    "SHADOW_BEAT_LIVE_RULE": "One of our test versions would have made a better call on that day.",
    "FULL_CRITERIA_MET_AND_PLACED": "Some horses outside the official picks are doing well, so the watchlist may contain useful future clues.",
    "FALSE_CONSENSUS": "Some tipster counts may have been inflated or came from weaker sources.",
    "THIN_FORM_RECORD": "There was not enough recent form to be fully confident.",
}

PLAIN_ACTIONS = {
    "SURFACE_DATA_MISSING": "Keep collecting. Do not block a horse on this alone yet.",
    "UNPROVEN_COURSE": "Keep collecting. Treat as a caution, not a hard rule.",
    "UNPROVEN_GOING": "Keep collecting. Important in bad weather.",
    "UNPROVEN_TRIP": "Keep collecting. Could become useful with more evidence.",
    "SAME_COURSE_CLUSTER": "Watch carefully. It may help avoid several picks being exposed to the same course bias.",
    "POOR_RECENT_FORM": "This is a serious warning and should be checked before official selection.",
    "SHADOW_BEAT_LIVE_RULE": "Keep testing before changing the live system.",
    "FULL_CRITERIA_MET_AND_PLACED": "Review watchlist winners and placers to see what the official rules missed.",
    "FALSE_CONSENSUS": "Only count trusted sources and be careful with copied tipster lists.",
    "THIN_FORM_RECORD": "Do not over-trust a horse without enough recent evidence.",
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
    analysed_dates = cumulative.get("analysed_dates") or []
    new_format_dates = [d for d in analysed_dates if str(d) >= "2026-06-14"]

    lines = [
        "SIGNAL 75 - MORNING LEARNING NOTE",
        datetime.now().strftime("%A %d %B %Y"),
        "",
        "Plain English version",
        "",
        "This note is only telling us what Signal 75 has noticed.",
        "It has NOT changed today's picks, proof, results, or scoring rules.",
        "",
        f"New format days checked: {len(new_format_dates)} day(s) since 14 June",
        f"Older learning days also stored: {max(0, len(analysed_dates) - len(new_format_dates))}",
        f"Official picks placed across all stored learning days: {pct(cumulative.get('official_place_rate_percent') or cumulative.get('official_place_rate'))}",
        f"Watchlist horses placed across all stored learning days: {pct(cumulative.get('watchlist_place_rate_percent') or cumulative.get('watchlist_place_rate'))}",
        "",
        "What Signal 75 has noticed:",
    ]

    if not finding_counts:
        lines.append("1. No continuous-learning findings recorded yet.")
    else:
        ordered = sorted(finding_counts.items(), key=lambda row: (-row[1], row[0]))
        for idx, (finding, count) in enumerate(ordered[:10], start=1):
            item = candidate_by_finding.get(finding, {})
            evidence = item.get("evidence_so_far") or {}
            label = PLAIN_LABELS.get(finding, finding.replace("_", " ").title())
            meaning = PLAIN_MEANINGS.get(finding, "Signal 75 has seen this pattern and is storing it for review.")
            action = PLAIN_ACTIONS.get(finding, "Keep collecting more evidence before making changes.")
            saving = evidence.get("theoretical_roi_impact") or money(item.get("estimated_saving_if_avoided", 0))
            lines.extend(
                [
                    f"{idx}. {label}",
                    f"   Seen: {count} time(s)",
                    f"   Meaning: {meaning}",
                    f"   Current action: {action}",
                    f"   Money note: this is only a rough test figure, not guaranteed profit. Best case saving shown: {saving}.",
                    "",
                ]
            )

    lines.extend(["What to review next:"])

    review_items = [item for item in candidate_items if item.get("status")]
    if not review_items:
        lines.append("1. No ROI improvement candidates yet.")
    else:
        for idx, item in enumerate(review_items[:8], start=1):
            label = PLAIN_LABELS.get(str(item.get("finding")), str(item.get("finding", "")).replace("_", " ").title())
            lines.append(f"{idx}. {label}")

    lines.extend(
        [
            "",
            "Bottom line:",
            "The system is learning, but it is not allowed to change the live rules by itself.",
            "We only promote a finding into the live selection rules after John reviews it and approves it.",
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
