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


def recent_form(form: Any, length: int = 6) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(form or "").upper())[-length:]


def external_validation(tipsters: int, rival_overlay: Any) -> str:
    if tipsters >= 3:
        return "STRONG"
    if tipsters >= 1 or rival_overlay:
        return "MODERATE"
    return "WEAK"


def fitness_signal(form: Any) -> str:
    recent = recent_form(form, 6)
    if not recent:
        return "UNKNOWN"
    if recent[-1:] == "P":
        return "CRITICAL"
    bad = set("PFURB")
    if any(c in bad for c in recent[-3:]):
        return "WEAK"
    if any(c in bad for c in recent[:-3]):
        return "MODERATE"
    return "STRONG"


def recent_form_trajectory(form: Any) -> str:
    recent = recent_form(form, 6)
    if not recent:
        return "UNKNOWN"
    zeros = recent.count("0")
    if zeros >= 3:
        return "CRITICAL"
    if zeros >= 2:
        return "WEAK"
    last3 = recent[-3:]
    if last3 and all(c in "123" for c in last3):
        return "STRONG"
    if any(c in "123" for c in last3):
        return "MODERATE"
    return "WEAK"


def market_confidence(horse: Dict[str, Any]) -> str:
    current = safe_float(horse.get("odds"), 0.0)
    previous = safe_float(horse.get("prevOdds"), 0.0)
    if current <= 0 or previous <= 0:
        return "UNKNOWN"
    if current < previous:
        return "STRONG"
    if current <= previous * 1.05:
        return "MODERATE"
    return "WEAK"


def going_suitability(horse: Dict[str, Any], race: Dict[str, Any]) -> str:
    going = str(race.get("going") or "").strip().lower()
    if not going or going in {"not confirmed", "unknown", "none"}:
        return "UNKNOWN"
    if safe_int(horse.get("goingWins")) > 0:
        return "STRONG"
    if safe_int(horse.get("goingRuns")) > 0:
        return "MODERATE"
    return "UNKNOWN"


def course_distance(horse: Dict[str, Any]) -> str:
    course_wins = safe_int(horse.get("courseWins"))
    distance_wins = safe_int(horse.get("distanceWins"))
    if course_wins > 0 and distance_wins > 0:
        return "STRONG"
    if course_wins > 0 or distance_wins > 0:
        return "MODERATE"
    return "WEAK"


def score_composition(tipsters: int, rival_overlay: Any, runner: Dict[str, Any]) -> str:
    parts = runner.get("parts") if isinstance(runner.get("parts"), dict) else {}
    if tipsters == 0 and not rival_overlay and safe_int(parts.get("tips")) > 0:
        return "WARNING"
    return "HEALTHY"


def rating_from_dimensions(dimensions: Dict[str, str], myal_pattern: bool) -> Tuple[str, str]:
    values = list(dimensions.values())
    if myal_pattern or "CRITICAL" in values:
        return "FLAGGED", "red"
    weak_count = sum(1 for value in values if value in {"WEAK", "WARNING"})
    strong_count = values.count("STRONG") + values.count("HEALTHY")
    if weak_count >= 2:
        return "WEAK", "red"
    if strong_count >= 3 and weak_count == 0:
        return "STRONG", "green"
    if strong_count >= 2 and "CRITICAL" not in values:
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
    warning = form_warning(horse, runner)
    form = horse.get("formStr") or horse.get("form") or runner.get("form")
    dimensions = {
        "external_validation": external_validation(tipsters, rival_overlay),
        "fitness": fitness_signal(form),
        "recent_form": recent_form_trajectory(form),
        "market_confidence": market_confidence(horse),
        "going_suitability": going_suitability(horse, race),
        "course_distance": course_distance(horse),
        "score_composition": score_composition(tipsters, rival_overlay, runner),
    }
    myal_pattern = bool(tipsters == 0 and not rival_overlay and warning)
    rating, colour = rating_from_dimensions(dimensions, myal_pattern)
    flags: List[str] = []
    if tipsters == 0:
        flags.append("Zero tipster support")
    if not rival_overlay:
        flags.append("Zero rival memory evidence")
    if warning:
        flags.append(warning)
    if dimensions["score_composition"] == "WARNING":
        flags.append(f"Tips display shows {(runner.get('parts') or {}).get('tips')} but zero actual tipsters")
    return {
        "name": horse.get("name", "Unknown"),
        "course": race.get("course", ""),
        "time": race.get("time", ""),
        "score": safe_float(horse.get("signal_score") or runner.get("score"), 0.0),
        "odds": horse.get("odds"),
        "quality_rating": rating,
        "quality_colour": colour,
        "dimensions": dimensions,
        "flags": flags,
        "plain_english": plain_english(horse.get("name", "Unknown"), rating, tipsters, rival_overlay, warning),
        "myal_pattern": myal_pattern,
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
    counts: Dict[str, int] = {"strong": 0, "solid": 0, "moderate": 0, "weak": 0, "flagged": 0}
    for pick in picks:
        counts[pick["quality_rating"].lower()] = counts.get(pick["quality_rating"].lower(), 0) + 1
    return {
        "date": date_text,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "analysis_only": True,
        "scoringImpact": "none",
        "picks": picks,
        "summary": {
            "total_picks": len(picks),
            **counts,
            "flagged_horses": [pick["name"] for pick in picks if pick["quality_rating"] == "FLAGGED"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create pre-race quality audit for official Signal 75 picks.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument(
        "--fail-on-flagged",
        action="store_true",
        help="Exit non-zero when an official pick is flagged, so the morning publish can pause.",
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
        print(f"BLOCKING PUBLIC PUSH: flagged official pick(s): {', '.join(flagged)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
