#!/usr/bin/env python3
"""Open a small morning summary of Signal 75 continuous-learning findings."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = REPO_ROOT / "data" / "continuous_training"
DEFAULT_OUTPUT = Path.home() / "SIGNAL 75 MORNING LEARNING ALERTS.txt"


PLAIN_LABELS = {
    "SURFACE_DATA_MISSING": "We did not have enough surface evidence",
    "UNPROVEN_COURSE": "We did not have enough course evidence",
    "UNPROVEN_GOING": "We did not have enough ground/going evidence",
    "UNPROVEN_TRIP": "We did not have enough distance evidence",
    "SAME_COURSE_CLUSTER": "Too many horses came from the same racecourse",
    "POOR_RECENT_FORM": "A horse had poor recent form",
    "SHADOW_BEAT_LIVE_RULE": "A test rule would have done better than the live rule",
    "FULL_CRITERIA_MET_AND_PLACED": "Worth Watching horses are still performing well",
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
    "FULL_CRITERIA_MET_AND_PLACED": "Some horses outside the official picks are doing well, so Worth Watching may contain useful future clues.",
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
    "FULL_CRITERIA_MET_AND_PLACED": "Review Worth Watching winners and placers to see what the official rules missed.",
    "FALSE_CONSENSUS": "Only count trusted sources and be careful with copied tipster lists.",
    "THIN_FORM_RECORD": "Do not over-trust a horse without enough recent evidence.",
}

PLAIN_COUNT_MEANINGS = {
    "SURFACE_DATA_MISSING": "This is a data-quality warning. It means the stored files could not prove the horse on today's surface; it does not automatically mean the horse was a bad pick.",
    "UNPROVEN_COURSE": "This means the stored files did not show a previous win at today's course. It is useful as a caution, but many good horses can still win at a course for the first time.",
    "UNPROVEN_GOING": "This means the stored files did not show proven form on today's going. It matters most when the going is unusual, heavy, very soft, or very firm.",
    "UNPROVEN_TRIP": "This means the stored files did not show a previous win at today's distance or distance band. It is more serious when the horse is moving up or down a long way in trip.",
    "SAME_COURSE_CLUSTER": "This means several selections relied on the same track. If the going, draw, pace, or weather was unusual, more than one pick can be exposed to the same problem.",
    "POOR_RECENT_FORM": "This means the recent form string contained enough poor markers to deserve a warning before trusting a high score.",
    "SHADOW_BEAT_LIVE_RULE": "This means a test version of the rules would have produced a better paper result than the live rule for that day.",
    "FULL_CRITERIA_MET_AND_PLACED": "This is a positive finding. It means a high-scoring horse outside the official picks still won or placed, so Worth Watching may be carrying useful signals.",
    "FALSE_CONSENSUS": "This means the raw tipster number looked stronger than the trusted-source number. Example: 19 headline tips, but only 2 clearly trusted independent sources.",
    "THIN_FORM_RECORD": "This means there was not much recent evidence in the stored form record, so the confidence should be lower.",
    "LARGE_FIELD_CHAOS_RISK": "This means the race had enough runners to create more traffic, draw, pace, and bad-luck risk than a smaller clean race.",
}


def latest_training_logs(limit: int = 14) -> List[Dict[str, Any]]:
    logs: List[Tuple[str, Dict[str, Any]]] = []
    for path in sorted(TRAINING_DIR.glob("training_log_*.json")):
        data = load_json(path, {})
        if not isinstance(data, dict):
            continue
        date = str(data.get("date") or path.stem.replace("training_log_", ""))
        logs.append((date, data))
    return [data for _, data in logs[-limit:]]


def collect_examples(logs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    examples: Dict[str, List[Dict[str, Any]]] = {}
    for log in logs:
        date = str(log.get("date") or "")
        for horse in log.get("horses") or []:
            if not isinstance(horse, dict):
                continue
            checks = []
            checks.extend(horse.get("findings") or [])
            checks.extend(horse.get("positive_findings") or [])
            for finding in checks:
                if not isinstance(finding, dict):
                    continue
                key = str(finding.get("finding") or finding.get("check") or "")
                if not key:
                    continue
                examples.setdefault(key, []).append(
                    {
                        "date": date,
                        "horse": horse.get("horse"),
                        "type": horse.get("type"),
                        "result": horse.get("result"),
                        "position": horse.get("position"),
                        "course": horse.get("course"),
                        "time": horse.get("time"),
                        "score": horse.get("signal_score"),
                        "bsp": horse.get("bsp"),
                        "tipsters": horse.get("tipster_count"),
                        "trusted_tipsters": horse.get("trusted_tipster_count"),
                        "evidence": finding.get("evidence"),
                        "note": finding.get("note"),
                    }
                )
    return examples


def result_text(example: Dict[str, Any]) -> str:
    result = str(example.get("result") or "unknown").lower()
    pos = example.get("position")
    if pos not in (None, ""):
        return f"{result}, position {pos}"
    return result


def score_text(example: Dict[str, Any]) -> str:
    bits: List[str] = []
    if example.get("score") not in (None, ""):
        bits.append(f"score {example.get('score')}")
    if example.get("bsp") not in (None, ""):
        bits.append(f"BSP {example.get('bsp')}")
    if example.get("tipsters") not in (None, ""):
        trusted = example.get("trusted_tipsters")
        if trusted not in (None, ""):
            bits.append(f"{trusted}/{example.get('tipsters')} trusted tipsters")
        else:
            bits.append(f"{example.get('tipsters')} tipsters")
    return ", ".join(bits)


def render_examples_for_finding(finding: str, examples: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    rows = examples.get(finding) or []
    if not rows:
        return [
            "   Recent examples: none available in the latest training logs.",
            "   Usefulness: count only. Needs horse examples before making a decision.",
        ]

    recent = rows[-3:]
    known = [r for r in rows if str(r.get("result") or "").upper() not in {"", "UNKNOWN"}]
    placed = [r for r in known if str(r.get("result") or "").upper() in {"WON", "PLACED"}]
    lost = [r for r in known if str(r.get("result") or "").upper() == "LOST"]

    lines = [
        f"   What the count really means: {PLAIN_COUNT_MEANINGS.get(finding, 'This is an internal learning label; use the examples below before trusting the count.')}",
    ]
    if known:
        lines.append(f"   Latest evidence split: {len(placed)} won/placed, {len(lost)} lost, from {len(known)} recent logged example(s).")
    lines.append("   Recent examples:")
    for row in recent:
        place = " ".join(str(x) for x in [row.get("course"), row.get("time")] if x not in (None, ""))
        details = score_text(row)
        suffix = f" ({details})" if details else ""
        evidence = row.get("evidence") or row.get("note") or "No detailed evidence stored."
        lines.append(
            f"   - {row.get('date')}: {row.get('horse')} at {place} - {result_text(row)}{suffix}. {evidence}"
        )
    return lines


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


def finding_count(findings: Dict[str, int], key: str) -> int:
    try:
        return int(findings.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def render_plain_summary(finding_counts: Dict[str, int], new_format_days: int) -> List[str]:
    watchlist_count = finding_count(finding_counts, "FULL_CRITERIA_MET_AND_PLACED")
    missing_evidence = max(
        finding_count(finding_counts, "SURFACE_DATA_MISSING"),
        finding_count(finding_counts, "UNPROVEN_COURSE"),
        finding_count(finding_counts, "UNPROVEN_GOING"),
        finding_count(finding_counts, "UNPROVEN_TRIP"),
    )
    false_consensus = finding_count(finding_counts, "FALSE_CONSENSUS")
    poor_form = finding_count(finding_counts, "POOR_RECENT_FORM")
    thin_form = finding_count(finding_counts, "THIN_FORM_RECORD")
    same_course = finding_count(finding_counts, "SAME_COURSE_CLUSTER")

    lines = [
        "Simple summary:",
        f"- We only have {new_format_days} day(s) of evidence for the new 14 June format, so this is still early.",
    ]
    if watchlist_count:
        lines.append("- Worth Watching horses are still worth watching because several have run well.")
    if missing_evidence:
        lines.append("- The biggest repeated warning is missing proof: course, ground, surface, or distance evidence was not strong enough.")
    if false_consensus:
        lines.append("- Tipster numbers need checking carefully because some support may not be as strong as it first looks.")
    if poor_form or thin_form:
        lines.append("- Recent form matters: weak or thin form should probably make a horse harder to trust.")
    if same_course:
        lines.append("- Too many picks from one course may be risky because one track/weather pattern can affect them all.")
    if len(lines) == 2:
        lines.append("- No strong pattern is ready for action yet.")
    return lines


def render_possible_recommendations(finding_counts: Dict[str, int]) -> List[str]:
    recommendations: List[str] = []
    if finding_count(finding_counts, "FALSE_CONSENSUS"):
        recommendations.append("Reduce the effect of tipster support unless it comes from trusted, clearly named sources.")
    if finding_count(finding_counts, "POOR_RECENT_FORM") or finding_count(finding_counts, "THIN_FORM_RECORD"):
        recommendations.append("Add a stronger warning before making horses official when recent form is poor or there is not enough current evidence.")
    if finding_count(finding_counts, "SAME_COURSE_CLUSTER"):
        recommendations.append("Warn when too many selections come from the same course on the same day.")
    if max(
        finding_count(finding_counts, "SURFACE_DATA_MISSING"),
        finding_count(finding_counts, "UNPROVEN_COURSE"),
        finding_count(finding_counts, "UNPROVEN_GOING"),
        finding_count(finding_counts, "UNPROVEN_TRIP"),
    ):
        recommendations.append("Show course, ground, surface, and distance evidence more clearly before trusting a high score.")
    if finding_count(finding_counts, "FULL_CRITERIA_MET_AND_PLACED"):
        recommendations.append("Review Worth Watching winners/placers to see if the official gate is too strict.")
    if not recommendations:
        recommendations.append("Keep collecting evidence. No future rule change is suggested yet.")

    lines = ["Possible future recommendations if this keeps being proven:"]
    for idx, item in enumerate(recommendations[:6], start=1):
        lines.append(f"{idx}. {item}")
    lines.extend(
        [
            "",
            "Important:",
            "These are not live changes today. They are possible changes for John to approve later if the evidence keeps repeating.",
        ]
    )
    return lines


def render_alert_summary() -> str:
    cumulative = load_json(TRAINING_DIR / "cumulative_findings.json", {})
    candidates = load_json(TRAINING_DIR / "roi_improvement_candidates.json", {})
    pattern_alerts = load_json(TRAINING_DIR / "pattern_alerts.json", {})
    promotion_candidates = load_json(REPO_ROOT / "data" / "challenger_lab" / "promotion_candidates.json", {})

    finding_counts: Dict[str, int] = cumulative.get("finding_counts") or cumulative.get("finding_totals") or {}
    candidate_items: List[Dict[str, Any]] = candidates.get("items") or []
    analysed_dates = cumulative.get("analysed_dates") or []
    new_format_dates = [d for d in analysed_dates if str(d) >= "2026-06-14"]
    promotion_items = promotion_candidates.get("promotion_candidates") or []
    alert_items = pattern_alerts.get("items") or pattern_alerts.get("alerts") or []

    ordered = sorted(finding_counts.items(), key=lambda row: (-row[1], row[0]))
    watch_count = finding_count(finding_counts, "FULL_CRITERIA_MET_AND_PLACED")
    false_consensus = finding_count(finding_counts, "FALSE_CONSENSUS")
    zero_validation = finding_count(finding_counts, "ZERO_EXTERNAL_VALIDATION_WITH_FORM_WARNING")
    field_aware = finding_count(finding_counts, "FIELD_AWARE_OVERLAY_IMPROVEMENT")
    graph_blocked = finding_count(finding_counts, "GRAPH_EVIDENCE_BLOCKED_BY_FORM_GATE")

    lines = [
        "SIGNAL 75 - MORNING LEARNING ALERTS",
        datetime.now().strftime("%A %d %B %Y"),
        "",
        "Short version",
        "",
        "No live rules changed. Picks, proof, scoring and results are untouched.",
        "Use the dashboard for the full evidence view. This note only flags what needs attention.",
        "",
        f"New-format days checked: {len(new_format_dates)}",
        f"Promotion candidates: {len(promotion_items)}",
    ]

    if promotion_items:
        lines.append("ACTION: A challenger may need John review before anything changes.")
    else:
        lines.append("Action today: none. Keep collecting evidence.")

    lines.extend(["", "Dashboard evidence to watch:"])
    evidence_lines: List[str] = []
    if field_aware:
        evidence_lines.append(f"- Field-aware overlay improvement logged {field_aware} time(s).")
    if graph_blocked:
        evidence_lines.append(f"- Strong graph evidence blocked by form gate logged {graph_blocked} time(s).")
    if zero_validation:
        evidence_lines.append(f"- Official picks with zero external validation plus form warning logged {zero_validation} time(s).")
    if false_consensus:
        evidence_lines.append(f"- Tipster support looked stronger than it really was {false_consensus} time(s).")
    if watch_count:
        evidence_lines.append(f"- Worth Watching horses are still carrying useful signal: {watch_count} positive finding(s).")
    if not evidence_lines:
        evidence_lines.append("- No new high-priority learning pattern needs attention today.")
    lines.extend(evidence_lines[:6])

    lines.extend(["", "Top stored learning counts:"])
    if ordered:
        for finding, count in ordered[:5]:
            label = PLAIN_LABELS.get(finding, finding.replace("_", " ").title())
            lines.append(f"- {label}: {count}")
    else:
        lines.append("- No cumulative learning counts found yet.")

    lines.extend(["", "Alerts:"])
    if alert_items:
        for item in alert_items[:5]:
            if isinstance(item, dict):
                code = str(item.get("code") or item.get("finding") or "")
                label = item.get("title") or PLAIN_LABELS.get(code) or code.replace("_", " ").title() or "Learning alert"
                detail = item.get("summary") or item.get("message") or item.get("note") or ""
                if detail.startswith(code):
                    detail = detail.replace(code, label, 1)
                lines.append(f"- {label}" + (f": {detail}" if detail else ""))
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- No separate pattern alerts stored.")

    lines.extend(["", "Bottom line:"])
    if promotion_items:
        lines.append("Something may be ready for manual review, but nothing can go live automatically.")
    elif field_aware or graph_blocked or zero_validation:
        lines.append("Good evidence is building, but it is still monitor-only. Review in the dashboard.")
    else:
        lines.append("The system is learning normally. No action needed this morning.")

    review_items = [item for item in candidate_items if item.get("status")]
    if review_items:
        lines.extend(["", "Review later:"])
        for idx, item in enumerate(review_items[:5], start=1):
            label = PLAIN_LABELS.get(str(item.get("finding")), str(item.get("finding", "")).replace("_", " ").title())
            lines.append(f"{idx}. {label}")

    return "\n".join(lines).rstrip() + "\n"


def render_full_summary() -> str:
    cumulative = load_json(TRAINING_DIR / "cumulative_findings.json", {})
    candidates = load_json(TRAINING_DIR / "roi_improvement_candidates.json", {})
    recent_examples = collect_examples(latest_training_logs())

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
        f"Worth Watching horses placed across all stored learning days: {pct(cumulative.get('watchlist_place_rate_percent') or cumulative.get('watchlist_place_rate'))}",
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
                    f"   Money note: {saving} is a rough ceiling only. It assumes every flagged loser was avoided and no replacement was worse.",
                ]
            )
            lines.extend(render_examples_for_finding(finding, recent_examples))
            lines.append("")

    lines.extend(render_plain_summary(finding_counts, len(new_format_dates)))
    lines.append("")
    lines.extend(render_possible_recommendations(finding_counts))
    lines.append("")

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
    parser.add_argument("--full", action="store_true", help="Write the old long-form learning note instead of the short alert note.")
    args = parser.parse_args()

    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_full_summary() if args.full else render_alert_summary(), encoding="utf-8")

    if args.open:
        subprocess.run(["/usr/bin/open", "-a", "TextEdit", str(output)], check=False)

    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
