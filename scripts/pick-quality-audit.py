#!/usr/bin/env python3
"""Pre-race quality audit for official Signal 75 picks.

Analysis only. This script never changes picks, scores, results or proof. It
adds a dashboard-facing warning layer so weakly validated official picks are
visible before races run.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalise(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def official_picks(daily: Dict[str, Any]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    rows: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                rows.append((race, horse))
    return rows


def comparison_lookup(comparison: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for race in comparison.get("races", []) or []:
        course = normalise(race.get("course"))
        time = str(race.get("time") or "")
        for runner in race.get("runners", []) or []:
            key = (normalise(runner.get("name")), course, time)
            lookup[key] = runner
    return lookup


def consensus_count(horse: Dict[str, Any], runner: Dict[str, Any]) -> int:
    consensus = horse.get("consensus") if isinstance(horse.get("consensus"), dict) else {}
    runner_consensus = runner.get("consensus") if isinstance(runner.get("consensus"), dict) else {}
    return (
        safe_int(horse.get("tipsters"))
        or safe_int(runner.get("tipsters"))
        or safe_int(consensus.get("consensus_count"))
        or safe_int(consensus.get("tip_count"))
        or safe_int(consensus.get("source_count"))
        or safe_int(runner_consensus.get("consensus_count"))
        or safe_int(runner_consensus.get("tip_count"))
        or safe_int(runner_consensus.get("source_count"))
    )


def form_warning(horse: Dict[str, Any], runner: Dict[str, Any]) -> str:
    values = [
        horse.get("formWarning"),
        horse.get("form_warning"),
        runner.get("formWarning"),
        runner.get("form_warning"),
    ]
    warnings = runner.get("warnings")
    if isinstance(warnings, list):
        values.extend(w for w in warnings if "form" in str(w).lower())
    for value in values:
        if value:
            return str(value)
    return ""


def parse_recent_form(form_string: Any, n: int = 3) -> Tuple[List[str], List[str], bool]:
    if not form_string:
        return [], [], False
    raw = str(form_string or "").upper()
    cleaned = raw.replace("-", "").replace("/", "")
    recent = list(cleaned[-n:]) if len(cleaned) >= n else list(cleaned)
    placed = [char for char in recent if char in "123"]
    has_pulled_up = "P" in recent or "PU" in raw[-6:]
    return recent, placed, has_pulled_up


def recent_form(form: Any, length: int = 6) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(form or "").upper())[-length:]


def rival_overlay_points(value: Any) -> int:
    if isinstance(value, dict):
        return safe_int(value.get("points") or value.get("overlay_points") or value.get("score"))
    return safe_int(value)


def external_validation(tipsters: int, rival_points: int) -> str:
    if tipsters >= 3:
        return "STRONG"
    if tipsters >= 1 or rival_points >= 8:
        return "MODERATE"
    if tipsters == 0 and rival_points == 0:
        return "NONE"
    return "WEAK"


def fitness_signal(form: Any) -> str:
    recent, placed, has_pulled_up = parse_recent_form(form, 3)
    if not recent:
        return "UNKNOWN"
    if has_pulled_up:
        return "CRITICAL"
    if len(placed) >= 2:
        return "STRONG"
    if len(placed) == 1:
        return "MODERATE"
    return "WEAK"


def form_trajectory(form: Any) -> str:
    recent = recent_form(form, 6)
    if not recent:
        return "UNKNOWN"
    placed = [char for char in recent if char in "123"]
    if len(placed) >= 3:
        return "CONSISTENT_GOOD"
    numeric = [int(char) for char in recent if char.isdigit() and char != "0"]
    if len(numeric) >= 4:
        last_two = sum(numeric[-2:]) / 2
        before_two = sum(numeric[-4:-2]) / 2
        if last_two < before_two:
            return "IMPROVING"
    if len(placed) == 1:
        return "INCONSISTENT"
    return "CONSISTENT_POOR"


def score_composition(score: float, tipsters: int, rival_points: int, runner: Dict[str, Any]) -> str:
    parts = runner.get("parts") if isinstance(runner.get("parts"), dict) else {}
    if 75 <= score <= 77 and tipsters == 0 and safe_int(parts.get("tips")) > 0:
        return "WARNING"
    healthy_components = sum(1 for value in parts.values() if safe_int(value) >= 15)
    if score >= 80 and healthy_components >= 2:
        return "HEALTHY"
    if 75 <= score <= 79:
        return "ADEQUATE"
    if tipsters == 0 and rival_points == 0 and safe_int(parts.get("tips")) > 0:
        return "WARNING"
    return "STRONG"


def field_evidence(rival_points: int, rival_overlay: Any) -> str:
    if isinstance(rival_overlay, dict):
        notes = " ".join(str(note) for note in rival_overlay.get("notes", []) or [])
        if "beaten by" in notes.lower() or rival_points < 0:
            return "WARNING"
    if rival_points >= 8:
        return "POSITIVE"
    if rival_points >= 1:
        return "MODERATE"
    return "NEUTRAL"


def rating_from_dimensions(dimensions: Dict[str, str], myal_pattern: bool) -> Tuple[str, str]:
    values = list(dimensions.values())
    if myal_pattern:
        return "FLAGGED", "red"
    if "CRITICAL" in values:
        return "CRITICAL", "red"
    weak_count = sum(1 for value in values if value in {"WEAK", "WARNING"})
    strong_count = values.count("STRONG") + values.count("HEALTHY") + values.count("POSITIVE") + values.count("CONSISTENT_GOOD")
    if weak_count >= 2:
        return "WEAK", "red"
    if strong_count >= 2 and weak_count == 0:
        return "STRONG", "green"
    if strong_count >= 1 and weak_count <= 1:
        return "SOLID", "blue"
    return "MODERATE", "amber"


def plain_english(name: str, rating: str, tipsters: int, rival_overlay: Any, warning: str) -> str:
    if rating == "FLAGGED":
        bits = []
        if tipsters == 0:
            bits.append("No tipster support")
        if not rival_overlay:
            bits.append("no rival evidence")
        if warning:
            bits.append("form warning present")
        return f"{name} is qualified by the live rules, but flagged before the race: {', '.join(bits)}. Treat this leg as carrying extra risk."
    if rating in {"STRONG", "SOLID"}:
        return f"{name} has enough supporting evidence for a normal official-pick confidence note."
    return f"{name} passed the official rules, but has mixed evidence. Review the warning details before treating this as a clean leg."


def audit_pick(race: Dict[str, Any], horse: Dict[str, Any], runner: Dict[str, Any]) -> Dict[str, Any]:
    tipsters = consensus_count(horse, runner)
    rival_overlay = horse.get("rivalMemoryOverlay") or runner.get("rivalMemoryOverlay")
    rival_points = rival_overlay_points(rival_overlay)
    warning = form_warning(horse, runner)
    form = horse.get("formStr") or horse.get("form") or runner.get("form")
    recent, placed, has_pulled_up = parse_recent_form(form, 3)
    score = safe_float(horse.get("signal_score") or runner.get("score"), 0.0)
    dimensions = {
        "external_validation": external_validation(tipsters, rival_points),
        "fitness": fitness_signal(form),
        "form_trajectory": form_trajectory(form),
        "score_composition": score_composition(score, tipsters, rival_points, runner),
        "field_evidence": field_evidence(rival_points, rival_overlay),
    }
    myal_pattern = bool(tipsters == 0 and rival_points == 0 and warning)
    rating, colour = rating_from_dimensions(dimensions, myal_pattern)
    flags: List[str] = []
    if tipsters == 0:
        flags.append("Zero tipster support")
    if rival_points == 0:
        flags.append("Zero rival memory evidence")
    if warning:
        flags.append(warning)
    if dimensions["score_composition"] == "WARNING":
        flags.append(f"Tips display shows {(runner.get('parts') or {}).get('tips')} but zero actual tipsters")
    return {
        "name": horse.get("name", "Unknown"),
        "course": race.get("course", ""),
        "time": race.get("time", ""),
        "score": score,
        "odds": horse.get("odds"),
        "quality_rating": rating,
        "quality_colour": colour,
        "dimensions": dimensions,
        "flags": flags,
        "plain_english": plain_english(horse.get("name", "Unknown"), rating, tipsters, rival_overlay, warning),
        "myal_pattern": myal_pattern,
        "recent_form": recent,
        "has_pulled_up": has_pulled_up,
        "placed_in_last_3": len(placed),
        "tipsters": tipsters,
        "rival_overlay_points": rival_points,
        "scoringImpact": "none",
        "analysis_only": True,
    }


def build(date_text: str) -> Dict[str, Any]:
    daily = read_json(DATA / f"{date_text}.json", {})
    if not daily:
        current = read_json(REPO_ROOT / "picks.json", {})
        if current.get("date") == date_text:
            daily = current
    comparison = read_json(DATA / f"race_comparison_{date_text}.json", {"races": []})
    comp = comparison_lookup(comparison)
    picks = []
    for race, horse in official_picks(daily):
        key = (normalise(horse.get("name")), normalise(race.get("course")), str(race.get("time") or ""))
        picks.append(audit_pick(race, horse, comp.get(key, {})))
    counts: Dict[str, int] = {"strong": 0, "solid": 0, "moderate": 0, "weak": 0, "flagged": 0, "critical": 0}
    for pick in picks:
        counts[pick["quality_rating"].lower()] = counts.get(pick["quality_rating"].lower(), 0) + 1
    return {
        "date": date_text,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "analysis_only": True,
        "scoringImpact": "none",
        "total_official_picks": len(picks),
        "flags_raised": counts.get("flagged", 0) + counts.get("critical", 0),
        "picks": picks,
        "summary": {
            "total_picks": len(picks),
            **counts,
            "flagged_horses": [pick["name"] for pick in picks if pick["quality_rating"] == "FLAGGED"],
            "critical_horses": [pick["name"] for pick in picks if pick["quality_rating"] == "CRITICAL"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create pre-race quality audit for official Signal 75 picks.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--fail-on-flagged",
        action="store_true",
        help="Deprecated: kept for old callers, but this audit is now always non-blocking.",
    )
    args = parser.parse_args()
    payload = build(args.date)
    output = DATA / f"pick_quality_audit_{args.date}.json"
    write_json(output, payload)
    print(f"Wrote {output}")
    for pick in payload["picks"]:
        print(f"{pick['name']}: {pick['quality_rating']} - {pick['plain_english']}")
    flagged = payload.get("summary", {}).get("flagged_horses", [])
    if args.fail_on_flagged and flagged:
        print(f"NON-BLOCKING WARNING: flagged official pick(s): {', '.join(flagged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
