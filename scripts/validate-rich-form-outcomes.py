#!/usr/bin/env python3
"""Validate rich form evidence after results settle.

Analysis only. This looks back after racing and asks a simple question:
when an official Signal 75 pick was beaten, did the horse that beat it have
stronger rich-form evidence before the race?

It never changes picks, scores, proof, settlement or performance.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"
CHALLENGER_DIR = DATA / "challenger_lab"
FORM_DB = INTEL / "form_history.sqlite"


def read_json(path: Path, default: Any) -> Any:
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


def parse_recent_form(form_value: Any, n: int = 4) -> List[str]:
    if not form_value:
        return []
    text = str(form_value or "").upper()
    cleaned = re.sub(r"[-/\s]", "", text)
    chars = list(reversed(cleaned))
    return [c for c in chars if c.isdigit() or c.upper() in ("P", "F", "U", "R", "B", "S")][:n]


def placed_count_recent(form_value: Any, n: int = 4) -> Optional[int]:
    recent = [c for c in parse_recent_form(form_value, n) if c.isdigit()]
    if len(recent) < n:
        return None
    return sum(1 for c in recent[:n] if c in ("1", "2", "3"))


def form_pattern_from_string(form_value: Any, length: int = 4) -> str:
    text = str(form_value or "").upper()
    cleaned = re.sub(r"[^0-9PFURBS]", "", text)
    if not cleaned:
        return ""
    # Pattern table is stored oldest-to-newest for the latest runs.
    # Form strings are read right-to-left, so the rightmost slice preserves
    # that chronological order for the database lookup.
    return cleaned[-length:]


def race_key(course: Any, time_value: Any, market_id: Any = "") -> Tuple[str, str, str]:
    return (norm(market_id), norm(course), time_key(time_value))


def loose_race_key(course: Any, time_value: Any) -> Tuple[str, str]:
    return (norm(course), time_key(time_value))


def horse_key(name: Any, course: Any, time_value: Any) -> Tuple[str, str, str]:
    return (norm(name), norm(course), time_key(time_value))


def result_label(position: int, result: Any = "") -> str:
    text = str(result or "").upper()
    if position == 1 or "WON" in text:
        return "WON"
    if position in {2, 3} or "PLACED" in text:
        return "PLACED"
    if position > 0:
        return "LOST"
    return "UNKNOWN"


def add_result(lookup: Dict[Tuple[str, str, str], Dict[str, Any]], row: Dict[str, Any]) -> None:
    name = row.get("horse_name") or row.get("horse") or row.get("name")
    course = row.get("course") or row.get("venue")
    time_value = row.get("race_time") or row.get("time")
    if not name:
        return
    key = horse_key(name, course, time_value)
    current = lookup.get(key, {})
    merged = {**current, **row}
    lookup[key] = merged


def result_lookup(date_text: str) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    combined = read_json(DATA / "combined_learning" / f"combined_learning_{date_text}.json", {})
    for row in combined.get("records", []) if isinstance(combined, dict) else []:
        add_result(lookup, row)

    notes = read_json(INTEL / f"race_result_notes_{date_text}.json", {})
    for row in notes.get("records", []) if isinstance(notes, dict) else []:
        add_result(lookup, row)

    daily = read_json(DATA / f"{date_text}.json", {})
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                add_result(
                    lookup,
                    {
                        **horse,
                        "section": tab,
                        "course": race.get("course"),
                        "race_time": race.get("time"),
                        "market_id": race.get("market_id"),
                        "field_size": race.get("runners"),
                        "distance": race.get("distance"),
                        "going": race.get("going"),
                    },
                )
    return lookup


def result_rows(date_text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    combined = read_json(DATA / "combined_learning" / f"combined_learning_{date_text}.json", {})
    rows.extend(combined.get("records", []) if isinstance(combined, dict) else [])
    notes = read_json(INTEL / f"race_result_notes_{date_text}.json", {})
    rows.extend(notes.get("records", []) if isinstance(notes, dict) else [])
    daily = read_json(DATA / f"{date_text}.json", {})
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                rows.append(
                    {
                        **horse,
                        "section": tab,
                        "course": race.get("course"),
                        "race_time": race.get("time"),
                        "market_id": race.get("market_id"),
                        "field_size": race.get("runners"),
                        "distance": race.get("distance"),
                        "going": race.get("going"),
                    }
                )
    return [row for row in rows if isinstance(row, dict)]


def official_picks(date_text: str) -> List[Dict[str, Any]]:
    daily = read_json(DATA / f"{date_text}.json", {})
    rows: List[Dict[str, Any]] = []
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                rows.append(
                    {
                        **horse,
                        "section": tab,
                        "course": race.get("course"),
                        "time": race.get("time"),
                        "race_time": race.get("time"),
                        "market_id": race.get("market_id"),
                        "field_size": race.get("runners"),
                        "distance": race.get("distance"),
                        "going": race.get("going"),
                        "name": horse.get("name") or horse.get("horse_name"),
                    }
                )
    return rows


def comparison_races(date_text: str) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    comparison = read_json(DATA / f"race_comparison_{date_text}.json", {"races": []})
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for race in comparison.get("races", []) or []:
        key = loose_race_key(race.get("course"), race.get("time"))
        runners = []
        for runner in race.get("runners", []) or []:
            runners.append(
                {
                    **runner,
                    "horse_name": runner.get("name") or runner.get("horse_name"),
                    "course": race.get("course"),
                    "race_time": race.get("time"),
                    "market_id": race.get("market_id"),
                    "field_size": race.get("field_size") or len(race.get("runners", []) or []),
                    "race_name": race.get("race_name"),
                }
            )
        grouped[key] = runners
    return grouped


class FormStats:
    def __init__(self, db_path: Path):
        self.conn: Optional[sqlite3.Connection] = None
        if db_path.exists():
            self.conn = sqlite3.connect(str(db_path))
            self.conn.execute("PRAGMA query_only = ON")

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def lookup(self, pattern: str) -> Dict[str, Any]:
        if not self.conn or not pattern:
            return {}
        candidates = [pattern]
        if len(pattern) >= 4:
            candidates.append(pattern[-3:])
        for candidate in candidates:
            row = self.conn.execute(
                """
                SELECT pattern_length, pattern, starts, wins, places, win_rate, place_rate
                FROM form_pattern_stats
                WHERE pattern_length = ? AND pattern = ?
                """,
                (len(candidate), candidate),
            ).fetchone()
            if row:
                return {
                    "patternLength": row[0],
                    "pattern": row[1],
                    "starts": row[2],
                    "wins": row[3],
                    "places": row[4],
                    "winRate": round(float(row[5]) * 100, 2),
                    "placeRate": round(float(row[6]) * 100, 2),
                }
        return {}


def evidence_tone(stats: Dict[str, Any]) -> str:
    starts = safe_int(stats.get("starts"))
    win_rate = safe_float(stats.get("winRate"))
    place_rate = safe_float(stats.get("placeRate"))
    if starts < 25:
        return "thin"
    if win_rate >= 14 and place_rate >= 34:
        return "strong"
    if win_rate < 7 or place_rate < 20:
        return "weak"
    return "normal"


def evidence_score(stats: Dict[str, Any]) -> float:
    if not stats:
        return 0.0
    sample = min(safe_int(stats.get("starts")), 500) / 500.0
    return round(safe_float(stats.get("winRate")) * 1.5 + safe_float(stats.get("placeRate")) * 0.5 + sample, 2)


def stronger_than(rival: Dict[str, Any], pick: Dict[str, Any]) -> bool:
    rs = rival.get("formStats") or {}
    ps = pick.get("formStats") or {}
    if safe_int(rs.get("starts")) < 25:
        return False
    if not ps:
        return True
    win_gap = safe_float(rs.get("winRate")) - safe_float(ps.get("winRate"))
    place_gap = safe_float(rs.get("placeRate")) - safe_float(ps.get("placeRate"))
    tone_rank = {"weak": 0, "thin": 1, "normal": 2, "strong": 3}
    return win_gap >= 3.0 or place_gap >= 8.0 or tone_rank.get(evidence_tone(rs), 0) > tone_rank.get(evidence_tone(ps), 0)


def runner_with_context(row: Dict[str, Any], results: Dict[Tuple[str, str, str], Dict[str, Any]], stats_db: FormStats) -> Dict[str, Any]:
    name = row.get("horse_name") or row.get("name")
    course = row.get("course")
    time_value = row.get("race_time") or row.get("time")
    result = results.get(horse_key(name, course, time_value), {})
    merged = {**row, **result}
    form_value = first_present(merged, "form", "formStr", "recent_form")
    pattern = form_pattern_from_string(form_value, 4)
    recent = parse_recent_form(form_value, 4)
    placed_recent = placed_count_recent(form_value, 4)
    stats = stats_db.lookup(pattern)
    position = safe_int(first_present(merged, "position", "full_result_position"))
    return {
        "horse": name,
        "course": course,
        "time": time_key(time_value),
        "marketId": merged.get("market_id"),
        "position": position,
        "result": result_label(position, merged.get("result")),
        "odds": first_present(merged, "bsp", "settlement_odds", "odds", "pre_race_price"),
        "score": first_present(merged, "signal_score", "score", "officialAdjustedScore"),
        "form": form_value,
        "formPattern": pattern,
        "recentForm": recent,
        "placedInLast4": placed_recent,
        "formStats": stats,
        "formTone": evidence_tone(stats),
        "evidenceScore": evidence_score(stats),
        "weightLbs": first_present(merged, "carried_weight_lbs", "weight_lbs"),
        "distance": first_present(merged, "distance", "distance_furlongs"),
        "going": merged.get("going"),
        "draw": first_present(merged, "stall_draw", "draw", "draw_bucket"),
        "officialRating": first_present(merged, "official_rating", "rpr"),
        "jockey": merged.get("jockey"),
        "trainer": merged.get("trainer"),
        "fieldSize": first_present(merged, "field_size"),
    }


def first_present(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def missing_context(row: Dict[str, Any]) -> List[str]:
    labels = []
    checks = [
        ("weightLbs", "weight"),
        ("distance", "distance"),
        ("going", "ground"),
        ("draw", "draw"),
        ("officialRating", "official rating"),
        ("jockey", "jockey"),
        ("trainer", "trainer"),
    ]
    for key, label in checks:
        if row.get(key) in (None, ""):
            labels.append(label)
    return labels


def find_winner_for_pick(
    pick_ctx: Dict[str, Any],
    race_rows: List[Dict[str, Any]],
    result_source_rows: Iterable[Dict[str, Any]],
    stats_db: FormStats,
) -> Optional[Dict[str, Any]]:
    course = pick_ctx.get("course")
    time_value = pick_ctx.get("time")
    market_id = pick_ctx.get("marketId")
    pre_race_by_name = {norm(row.get("horse_name") or row.get("name") or row.get("horse")): row for row in race_rows}
    candidates: List[Dict[str, Any]] = []
    for row in result_source_rows:
        same_market = market_id and str(row.get("market_id") or "") == str(market_id)
        same_course_time = loose_race_key(row.get("course") or row.get("venue"), row.get("race_time") or row.get("time")) == loose_race_key(course, time_value)
        if not (same_market or same_course_time):
            continue
        position = safe_int(first_present(row, "position", "full_result_position"))
        if position == 1 or str(row.get("result") or "").upper() == "WON":
            candidates.append(row)
    if not candidates:
        return None
    winner = candidates[0]
    winner_name = winner.get("horse_name") or winner.get("horse") or winner.get("name")
    pre_row = pre_race_by_name.get(norm(winner_name), {})
    return runner_with_context({**pre_row, **winner}, {}, stats_db)


def recent_form_warning(winner: Optional[Dict[str, Any]], pick: Dict[str, Any]) -> bool:
    if not winner:
        return False
    winner_placed = winner.get("placedInLast4")
    pick_placed = pick.get("placedInLast4")
    if winner_placed is None or pick_placed is None:
        return False
    return int(winner_placed) >= int(pick_placed) + 2


def plain_case(case: Dict[str, Any]) -> str:
    pick = case.get("ourPick", {})
    rival = case.get("rival", {})
    if case.get("verdict") == "RICH_FORM_WARNING_VALIDATED":
        return (
            f"{rival.get('horse')} beat {pick.get('horse')}. "
            f"Before the race, the archive gave {rival.get('horse')} the stronger similar-form profile."
        )
    if case.get("verdict") == "PICK_WON":
        return f"{pick.get('horse')} won, so there was no richer-form rival warning to validate."
    if case.get("verdict") == "RICH_FORM_WATCH":
        return (
            f"{pick.get('horse')} had at least one rival with stronger rich-form evidence, "
            "but the settled result has not proved that warning yet."
        )
    return (
        f"{pick.get('horse')} was beaten, but the richer form archive did not clearly point "
        "to the horse that beat it."
    )


def validate(date_text: str) -> Dict[str, Any]:
    picks = official_picks(date_text)
    races = comparison_races(date_text)
    results = result_lookup(date_text)
    all_result_rows = result_rows(date_text)
    stats_db = FormStats(FORM_DB)
    cases: List[Dict[str, Any]] = []

    try:
        for pick in picks:
            race_rows = races.get(loose_race_key(pick.get("course"), pick.get("time")), [])
            if not race_rows:
                race_rows = [pick]
            pick_ctx = runner_with_context(pick, results, stats_db)
            rival_contexts = [
                runner_with_context(row, results, stats_db)
                for row in race_rows
                if norm(row.get("horse_name") or row.get("name")) != norm(pick_ctx.get("horse"))
            ]
            known_rivals = [r for r in rival_contexts if r.get("position")]
            stronger_rivals = [r for r in rival_contexts if stronger_than(r, pick_ctx)]
            winner_ctx = find_winner_for_pick(pick_ctx, race_rows, all_result_rows, stats_db)
            beaters = [
                r for r in known_rivals
                if pick_ctx.get("position") and r.get("position") and r["position"] < pick_ctx["position"]
            ]
            stronger_beaters = [r for r in beaters if any(norm(r.get("horse")) == norm(s.get("horse")) for s in stronger_rivals)]
            chosen_rival = None
            verdict = "NO_RESULT_YET"
            if pick_ctx.get("position") == 1:
                verdict = "PICK_WON"
            elif winner_ctx and recent_form_warning(winner_ctx, pick_ctx):
                verdict = "RICH_FORM_WARNING_VALIDATED"
                chosen_rival = winner_ctx
            elif stronger_beaters:
                verdict = "RICH_FORM_WARNING_VALIDATED"
                chosen_rival = sorted(stronger_beaters, key=lambda r: (r.get("position") or 99, -r.get("evidenceScore", 0)))[0]
            elif stronger_rivals:
                verdict = "RICH_FORM_WATCH"
                chosen_rival = sorted(stronger_rivals, key=lambda r: -r.get("evidenceScore", 0))[0]
            elif beaters:
                verdict = "BEATEN_BUT_NOT_RICH_FORM"
                chosen_rival = sorted(beaters, key=lambda r: r.get("position") or 99)[0]
            elif pick_ctx.get("position", 0) > 1:
                verdict = "BEATEN_BUT_NOT_RICH_FORM"

            case = {
                "date": date_text,
                "section": pick.get("section"),
                "course": pick_ctx.get("course"),
                "time": pick_ctx.get("time"),
                "verdict": verdict,
                "ourPick": pick_ctx,
                "winner": winner_ctx,
                "beatenBy": chosen_rival,
                "rival": chosen_rival,
                "strongerRivalCount": len(stronger_rivals),
                "rivalsChecked": len(rival_contexts),
                "plainEnglish": "",
                "missingFields": sorted(set(missing_context(pick_ctx) + missing_context(chosen_rival or {}))),
                "analysisOnly": True,
                "scoringImpact": "none",
            }
            case["plainEnglish"] = plain_case(case)
            cases.append(case)
    finally:
        stats_db.close()

    settled = [c for c in cases if c["ourPick"].get("position")]
    validated = [c for c in cases if c["verdict"] == "RICH_FORM_WARNING_VALIDATED"]
    watch = [c for c in cases if c["verdict"] == "RICH_FORM_WATCH"]
    beaten = [c for c in cases if c["ourPick"].get("position", 0) > 1]
    payload = {
        "date": date_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "id": "rich_form_confidence_v1",
        "name": "Rich Form Confidence",
        "analysis_only": True,
        "scoringImpact": "none",
        "summary": {
            "official_picks_checked": len(picks),
            "settled_picks_checked": len(settled),
            "official_picks_beaten": len(beaten),
            "warning_candidates": len(validated),
            "warnings_validated": len(validated),
            "warnings_waiting": len(watch),
            "plainEnglish": (
                "This checks whether a horse that beat our pick also had stronger similar-form evidence "
                "before the race. It is a warning tracker only."
            ),
        },
        "cases": cases,
        "safety": {
            "changes_live_picks": False,
            "changes_scores": False,
            "changes_results": False,
            "john_approval_required_before_live_use": True,
        },
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rich form evidence after settlement.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    payload = validate(args.date)
    out = CHALLENGER_DIR / f"rich_form_outcomes_{args.date}.json"
    write_json(out, payload)
    summary = payload["summary"]
    print("Rich form outcome validation complete")
    print(f"  date: {args.date}")
    print(f"  official picks checked: {summary['official_picks_checked']}")
    print(f"  warnings validated: {summary['warnings_validated']}")
    print(f"  output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
