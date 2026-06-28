#!/usr/bin/env python3
"""Build Signal 75 collateral-form learning notes.

Collateral form is the "Grandad's book" idea in racing-analysis language:
which horses beat which other horses, by how far, and under what conditions.

This is learning/storage only. It does not change picks, scoring, proof,
settlement, unlock logic, public JSON, or result maths.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"
OUT_DIR = INTEL / "collateral_form"
H2H_MASTER = INTEL / "head_to_head_master.jsonl"
RESULT_NOTES_MASTER = INTEL / "race_result_notes_master.jsonl"
H2H_PROFILES = INTEL / "head_to_head_profiles.json"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def classify_margin(margin: Optional[float]) -> str:
    if margin is None:
        return "unknown margin"
    if margin <= 1:
        return "narrow"
    if margin < 5:
        return "clear"
    if margin < 12:
        return "strong"
    return "decisive"


def conditions_key(row: Dict[str, Any]) -> str:
    parts = [
        clean(row.get("course")),
        clean(row.get("race_name")),
        clean(row.get("distance")),
        clean(row.get("going")),
    ]
    return " | ".join(part for part in parts if part)


def result_note_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = "|".join([str(row.get("date") or ""), str(row.get("market_id") or ""), norm(row.get("horse_name"))])
        idx[key] = row
    return idx


def note_for(idx: Dict[str, Dict[str, Any]], row: Dict[str, Any], horse_key: str) -> Dict[str, Any]:
    key = "|".join([str(row.get("date") or ""), str(row.get("market_id") or ""), horse_key])
    return idx.get(key, {})


def build(date: Optional[str] = None) -> Dict[str, Any]:
    h2h_rows = read_jsonl(H2H_MASTER)
    result_rows = read_jsonl(RESULT_NOTES_MASTER)
    result_idx = result_note_index(result_rows)
    profiles = read_json(H2H_PROFILES, {})

    if date:
        h2h_rows = [row for row in h2h_rows if row.get("date") == date]
        result_rows = [row for row in result_rows if row.get("date") == date]

    winner_scores: Dict[str, float] = defaultdict(float)
    warning_scores: Dict[str, float] = defaultdict(float)
    by_horse_positive: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_horse_warning: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    strong_lines: List[Dict[str, Any]] = []

    for row in h2h_rows:
        winner = clean(row.get("winner"))
        loser = clean(row.get("loser"))
        winner_key = norm(row.get("winner_key") or winner)
        loser_key = norm(row.get("loser_key") or loser)
        if not winner_key or not loser_key:
            continue

        winner_note = note_for(result_idx, row, winner_key)
        loser_note = note_for(result_idx, row, loser_key)
        margin = safe_float(row.get("margin")) or safe_float(loser_note.get("distance_from_winner_lengths"))
        loser_signal = safe_float(row.get("loser_signal_score"))
        winner_margin = safe_float(winner_note.get("winning_margin_lengths"))
        same_conditions = conditions_key(winner_note or loser_note or row)

        base = 1.0
        if loser_signal is not None and loser_signal >= 90:
            base += 3.0
        elif loser_signal is not None and loser_signal >= 75:
            base += 1.5
        if margin is not None:
            if margin >= 10:
                base += 2.5
            elif margin >= 5:
                base += 1.5
            elif margin <= 1:
                base += 0.25
        if "WON_DECISIVELY" in (winner_note.get("result_note_flags") or []):
            base += 1.5

        evidence = {
            "date": row.get("date"),
            "course": row.get("course") or winner_note.get("course"),
            "race_time": row.get("race_time") or winner_note.get("race_time"),
            "race_name": row.get("race_name") or winner_note.get("race_name"),
            "winner": winner,
            "loser": loser,
            "margin_lengths": margin,
            "margin_class": classify_margin(margin),
            "loser_signal_score": loser_signal,
            "winner_pre_race_price": safe_float(row.get("winner_price")),
            "loser_pre_race_price": safe_float(row.get("loser_price")),
            "conditions": same_conditions,
            "note": row.get("evidence_note") or f"{winner} beat {loser}.",
        }

        winner_scores[winner_key] += base
        by_horse_positive[winner_key].append(evidence)
        if loser_signal is not None and loser_signal >= 90:
            strong_lines.append(evidence)

    for row in result_rows:
        horse = clean(row.get("horse_name"))
        horse_key = norm(horse)
        if not horse_key:
            continue
        flags = row.get("result_note_flags") if isinstance(row.get("result_note_flags"), list) else []
        score = safe_float(row.get("signal_score"))
        beaten = safe_float(row.get("distance_from_winner_lengths"))
        warning = 0.0
        if "HEAVILY_BEATEN" in flags:
            warning += 4.0
        elif "WELL_BEATEN" in flags:
            warning += 2.0
        if "WEAKENED_OR_NO_RESPONSE" in flags:
            warning += 2.0
        if score is not None and score >= 90 and beaten is not None and beaten >= 10:
            warning += 3.0
        if warning <= 0:
            continue
        evidence = {
            "date": row.get("date"),
            "course": row.get("course"),
            "race_time": row.get("race_time"),
            "race_name": row.get("race_name"),
            "horse": horse,
            "signal_score": score,
            "distance_from_winner_lengths": beaten,
            "finish_impression": row.get("finish_impression"),
            "distance_summary": row.get("distance_summary"),
            "beaten_by": row.get("beaten_by") or [],
            "conditions": conditions_key(row),
            "note": row.get("race_comment"),
        }
        warning_scores[horse_key] += warning
        by_horse_warning[horse_key].append(evidence)

    pair_profiles = profiles.get("pairs", {}) if isinstance(profiles, dict) else {}
    repeat_patterns = [
        {
            "pair": key,
            "dominant_horse": value.get("dominant_horse"),
            "meetings_logged": value.get("meetings_logged"),
            "dominance_rate": value.get("dominance_rate"),
            "evidence_tier": value.get("evidence_tier"),
            "recommended_use": value.get("recommended_use"),
            "last_note": value.get("last_note"),
        }
        for key, value in pair_profiles.items()
        if value.get("evidence_tier") in {"useful_pattern", "strong_pattern"}
    ]

    horses_to_follow = []
    for horse_key, score in winner_scores.items():
        examples = sorted(by_horse_positive[horse_key], key=lambda item: (item.get("date") or "", item.get("margin_lengths") or 0), reverse=True)
        horses_to_follow.append(
            {
                "horse_key": horse_key,
                "horse_name": examples[0].get("winner"),
                "collateral_strength": round(score, 2),
                "evidence_count": len(examples),
                "best_margin_lengths": max((safe_float(item.get("margin_lengths")) or 0 for item in examples), default=0),
                "beat_high_signal_count": sum(1 for item in examples if (safe_float(item.get("loser_signal_score")) or 0) >= 90),
                "latest_evidence": examples[:5],
                "recommended_use": "Positive watchlist evidence; use only with today's price, race fit, recent form, going, distance and tipster context.",
            }
        )

    horses_to_be_careful_with = []
    for horse_key, score in warning_scores.items():
        examples = sorted(by_horse_warning[horse_key], key=lambda item: item.get("date") or "", reverse=True)
        horses_to_be_careful_with.append(
            {
                "horse_key": horse_key,
                "horse_name": examples[0].get("horse"),
                "warning_strength": round(score, 2),
                "evidence_count": len(examples),
                "worst_beaten_distance": max((safe_float(item.get("distance_from_winner_lengths")) or 0 for item in examples), default=0),
                "latest_evidence": examples[:5],
                "recommended_use": "Warning evidence; do not block automatically unless repeated or supported by today's conditions.",
            }
        )

    horses_to_follow.sort(key=lambda item: (item["collateral_strength"], item["beat_high_signal_count"], item["best_margin_lengths"]), reverse=True)
    horses_to_be_careful_with.sort(key=lambda item: (item["warning_strength"], item["worst_beaten_distance"]), reverse=True)
    strong_lines.sort(key=lambda item: ((safe_float(item.get("loser_signal_score")) or 0), (safe_float(item.get("margin_lengths")) or 0)), reverse=True)
    repeat_patterns.sort(key=lambda item: (item.get("meetings_logged") or 0, item.get("dominance_rate") or 0), reverse=True)

    return {
        "date": date or "all-history",
        "generatedAt": now_iso(),
        "mode": "collateral_form_learning_only",
        "analysis_only": True,
        "scoringImpact": "none",
        "summary": {
            "head_to_head_records_checked": len(h2h_rows),
            "result_note_records_checked": len(result_rows),
            "horses_to_follow": len(horses_to_follow),
            "horses_to_be_careful_with": len(horses_to_be_careful_with),
            "strong_lines_against_high_signal_horses": len(strong_lines),
            "repeat_rival_patterns": len(repeat_patterns),
        },
        "horses_to_follow": horses_to_follow[:50],
        "horses_to_be_careful_with": horses_to_be_careful_with[:50],
        "strong_lines_against_high_signal_horses": strong_lines[:100],
        "repeat_rival_patterns": repeat_patterns[:100],
        "plain_english": [
            "Horses to follow are horses that beat useful or high-score rivals, especially by a clear margin.",
            "Horses to be careful with are horses that were well beaten, heavily beaten, or gave no response.",
            "This is not an automatic pick rule. It is a future evidence layer used with price, race fit, going, distance, form and tipsters.",
        ],
    }


def render_text(payload: Dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "SIGNAL 75 - COLLATERAL FORM REVIEW",
        str(payload["date"]),
        "",
        "Learning only. No picks, proof, scoring or results maths changed.",
        "",
        "Summary:",
        f"- Head-to-head records checked: {summary['head_to_head_records_checked']}",
        f"- Result-note records checked: {summary['result_note_records_checked']}",
        f"- Horses to follow: {summary['horses_to_follow']}",
        f"- Horses to be careful with: {summary['horses_to_be_careful_with']}",
        f"- Strong lines against high-score horses: {summary['strong_lines_against_high_signal_horses']}",
        f"- Repeat rival patterns: {summary['repeat_rival_patterns']}",
        "",
        "Top horses to follow:",
    ]
    for idx, item in enumerate(payload.get("horses_to_follow", [])[:10], start=1):
        latest = (item.get("latest_evidence") or [{}])[0]
        lines.append(
            f"{idx}. {item['horse_name']} - strength {item['collateral_strength']} - "
            f"{latest.get('note', 'stored evidence')}"
        )
    lines.append("")
    lines.append("Top caution horses:")
    for idx, item in enumerate(payload.get("horses_to_be_careful_with", [])[:10], start=1):
        latest = (item.get("latest_evidence") or [{}])[0]
        lines.append(
            f"{idx}. {item['horse_name']} - warning {item['warning_strength']} - "
            f"{latest.get('distance_summary', latest.get('note', 'stored warning'))}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build collateral-form learning review.")
    parser.add_argument("--date", help="Limit the review to one date. Omit for all stored history.")
    args = parser.parse_args()

    payload = build(args.date)
    suffix = args.date or "all_history"
    json_path = OUT_DIR / f"collateral_form_{suffix}.json"
    txt_path = OUT_DIR / f"collateral_form_{suffix}.txt"
    latest_json = OUT_DIR / "collateral_form_latest.json"
    latest_txt = OUT_DIR / "collateral_form_latest.txt"
    write_json(json_path, payload)
    write_text(txt_path, render_text(payload))
    write_json(latest_json, payload)
    write_text(latest_txt, render_text(payload))
    print(f"Collateral form review saved: {json_path.relative_to(REPO_ROOT)}")
    print(f"Horses to follow: {payload['summary']['horses_to_follow']} | caution: {payload['summary']['horses_to_be_careful_with']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
