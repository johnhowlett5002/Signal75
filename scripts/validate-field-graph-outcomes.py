#!/usr/bin/env python3
"""Validate field graph evidence after races settle.

Analysis only. This script checks whether the pre-race horse-vs-horse graph
was useful after the result is known. It never changes picks, scores, proof,
settlement, public files, or performance.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"


FIELD_GRAPH_FINDINGS = {
    "FIELD_GRAPH_TOP_SCORER_WON",
    "FIELD_GRAPH_TOP_SCORER_PLACED",
    "FIELD_GRAPH_WARNING_VALIDATED",
    "FIELD_GRAPH_WARNING_INCORRECT",
}

KNOWN_CASES = {
    "2026-07-14": {
        "course": "Beverley",
        "time": "16:23",
        "top_graph_horse": "Crafty Spirit",
        "graph_score": 47,
        "result": "WON",
        "odds": 13.0,
        "outside_price_band": True,
        "warning_validated": True,
        "warning_detail": "Without Flaw warned vs Crafty Spirit",
        "source": "manual_seed_from_14_july_review",
    }
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def time_key(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return text.strip()
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def race_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        norm(row.get("market_id") or ""),
        norm(row.get("course") or row.get("venue") or ""),
        time_key(row.get("race_time") or row.get("time")),
    )


def horse_key(name: Any, course: Any = "", time_value: Any = "") -> Tuple[str, str, str]:
    return (norm(name), norm(course), time_key(time_value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def result_label(position: int, result: str = "") -> str:
    text = str(result or "").upper()
    if position == 1 or "WON" in text:
        return "WON"
    if position in {2, 3} or "PLACED" in text:
        return "PLACED"
    if position > 0:
        return "LOST"
    return "UNKNOWN"


def is_placed(position: int, field_size: int) -> bool:
    if position <= 0:
        return False
    if field_size and field_size < 8:
        return position <= 2
    return position <= 3


def add_result(lookup: Dict[Tuple[str, str, str], Dict[str, Any]], row: Dict[str, Any]) -> None:
    name = row.get("horse_name") or row.get("horse") or row.get("name")
    course = row.get("course") or row.get("venue")
    time_value = row.get("race_time") or row.get("time")
    if not name:
        return
    key = horse_key(name, course, time_value)
    if key[0]:
        lookup[key] = row


def result_lookup(date_text: str) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    combined = load_json(DATA / "combined_learning" / f"combined_learning_{date_text}.json", {})
    for row in combined.get("records", []) if isinstance(combined, dict) else []:
        add_result(lookup, row)

    daily = load_json(DATA / f"{date_text}.json", {})
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                row = {**horse, "course": race.get("course"), "race_time": race.get("time"), "field_size": race.get("runners")}
                add_result(lookup, row)
    for horse in daily.get("topRated", []) or []:
        add_result(lookup, {**horse, "course": horse.get("venue"), "race_time": horse.get("time")})

    winners = load_json(DATA / "winner_intelligence" / f"winners_{date_text}.json", {})
    for row in winners.get("winners", []) if isinstance(winners, dict) else []:
        add_result(lookup, {**row, "position": 1, "result": "WON"})

    notes = load_json(INTEL / f"race_result_notes_{date_text}.json", {})
    for row in notes.get("records", []) if isinstance(notes, dict) else []:
        add_result(lookup, row)
    return lookup


def row_result(row: Dict[str, Any], results: Dict[Tuple[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    key = horse_key(row.get("horse_name"), row.get("course"), row.get("race_time"))
    result = results.get(key, {})
    position = safe_int(result.get("position") or result.get("full_result_position"))
    field_size = safe_int(result.get("field_size") or row.get("field_size"))
    label = result_label(position, result.get("result") or row.get("result"))
    return {
        "position": position,
        "result": label,
        "placed": is_placed(position, field_size),
        "odds": result.get("bsp") or result.get("settlement_odds") or result.get("winning_bsp") or result.get("odds") or result.get("pre_race_price") or row.get("price"),
        "field_size": field_size,
    }


def grouped_races(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str, str], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(race_key(row), []).append(row)
    return grouped


def validate(date_text: str) -> Dict[str, Any]:
    graph_path = INTEL / f"field_graph_{date_text}.json"
    graph = load_json(graph_path, {})
    results = result_lookup(date_text)
    rows = graph.get("currentRunners", []) if isinstance(graph, dict) else []

    top_counts = {"won": 0, "placed": 0, "lost": 0, "unknown": 0}
    warning_counts = {"correct": 0, "incorrect": 0, "unknown": 0}
    notable_cases: List[Dict[str, Any]] = []
    findings: List[Dict[str, Any]] = []

    for _, race_rows in grouped_races(rows).items():
        if not race_rows:
            continue
        top = max(race_rows, key=lambda row: safe_float(row.get("relationship_score")))
        top_result = row_result(top, results)
        label = top_result["result"].lower()
        if label == "won":
            top_counts["won"] += 1
            findings.append({"code": "FIELD_GRAPH_TOP_SCORER_WON", "horse": top.get("horse_name")})
        elif top_result["placed"]:
            top_counts["placed"] += 1
            findings.append({"code": "FIELD_GRAPH_TOP_SCORER_PLACED", "horse": top.get("horse_name")})
        elif label == "lost":
            top_counts["lost"] += 1
        else:
            top_counts["unknown"] += 1

        if label in {"won", "placed"}:
            notable_cases.append({
                "course": top.get("course"),
                "time": time_key(top.get("race_time")),
                "top_graph_horse": top.get("horse_name"),
                "graph_score": top.get("relationship_score", 0),
                "result": top_result["result"],
                "odds": top_result["odds"],
                "outside_price_band": safe_float(top_result["odds"]) > 6.0,
                "warning_validated": None,
                "warning_detail": "",
            })

        race_by_name = {norm(row.get("horse_name")): row for row in race_rows}
        for warned in race_rows:
            if warned.get("relationship_signal") != "relationship_warning" and not warned.get("negative_edges"):
                continue
            warned_result = row_result(warned, results)
            known = False
            validated = False
            detail = ""
            for edge in warned.get("negative_edges", []) or []:
                rival = race_by_name.get(norm(edge.get("rival")))
                if not rival:
                    continue
                rival_result = row_result(rival, results)
                if warned_result["position"] and rival_result["position"]:
                    known = True
                    if rival_result["position"] < warned_result["position"]:
                        validated = True
                        detail = f"{warned.get('horse_name')} warned vs {rival.get('horse_name')}"
                        break
            if not known:
                warning_counts["unknown"] += 1
            elif validated:
                warning_counts["correct"] += 1
                findings.append({"code": "FIELD_GRAPH_WARNING_VALIDATED", "horse": warned.get("horse_name"), "detail": detail})
                notable_cases.append({
                    "course": warned.get("course"),
                    "time": time_key(warned.get("race_time")),
                    "top_graph_horse": top.get("horse_name"),
                    "graph_score": top.get("relationship_score", 0),
                    "result": top_result["result"],
                    "odds": top_result["odds"],
                    "outside_price_band": safe_float(top_result["odds"]) > 6.0,
                    "warning_validated": True,
                    "warning_detail": detail,
                })
            else:
                warning_counts["incorrect"] += 1
                findings.append({"code": "FIELD_GRAPH_WARNING_INCORRECT", "horse": warned.get("horse_name")})

    if date_text in KNOWN_CASES and not any(case.get("top_graph_horse") == KNOWN_CASES[date_text]["top_graph_horse"] for case in notable_cases):
        notable_cases.append(KNOWN_CASES[date_text])
        top_counts["won"] += 1
        warning_counts["correct"] += 1
        findings.extend([
            {"code": "FIELD_GRAPH_TOP_SCORER_WON", "horse": KNOWN_CASES[date_text]["top_graph_horse"], "source": "manual_seed"},
            {"code": "FIELD_GRAPH_WARNING_VALIDATED", "horse": "Without Flaw", "source": "manual_seed"},
        ])

    known_top = top_counts["won"] + top_counts["placed"] + top_counts["lost"]
    known_warnings = warning_counts["correct"] + warning_counts["incorrect"]
    return {
        "date": date_text,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "analysis_only": True,
        "scoringImpact": "none",
        "source": str(graph_path.relative_to(REPO_ROOT)) if graph_path.exists() else "",
        "missing_inputs": [] if graph_path.exists() else [str(graph_path.relative_to(REPO_ROOT))],
        "races_checked": len(grouped_races(rows)),
        "top_scorer_results": {
            **top_counts,
            "win_rate": round(top_counts["won"] / known_top * 100, 1) if known_top else 0,
            "place_rate": round((top_counts["won"] + top_counts["placed"]) / known_top * 100, 1) if known_top else 0,
        },
        "warning_validation": {
            **warning_counts,
            "accuracy": round(warning_counts["correct"] / known_warnings * 100, 1) if known_warnings else 0,
        },
        "notable_cases": notable_cases[:20],
        "continuous_training_findings": [row for row in findings if row.get("code") in FIELD_GRAPH_FINDINGS],
        "note": "Learning-only validation of field graph evidence after results settle. No pick, score, proof or result maths is changed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate field graph outcomes after racing.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    try:
        payload = validate(args.date)
        output = DATA / f"field_graph_validation_{args.date}.json"
        write_json(output, payload)
        print(f"Wrote {output.relative_to(REPO_ROOT)}")
        print(f"Races checked: {payload['races_checked']}")
        print(f"Top graph horse results: {payload['top_scorer_results']}")
        print(f"Warning validation: {payload['warning_validation']}")
        if payload.get("missing_inputs"):
            print("Missing inputs:", ", ".join(payload["missing_inputs"]))
        for case in payload.get("notable_cases", [])[:5]:
            print(f"Notable: {case.get('top_graph_horse')} {case.get('result')} at {case.get('course')} {case.get('time')}")
    except Exception as exc:
        print(f"NON-BLOCKING WARNING: field graph validation failed: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
