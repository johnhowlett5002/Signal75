#!/usr/bin/env python3
"""Look up Signal 75 horse intelligence from the local SQLite database.

Read-only. This gives the pre-selection "Grandad's book" view without changing
scoring, picks, proof, settlement, results maths, app data, or public JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from signal75_intelligence_store import LIVE_DB


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
DEFAULT_DB = LIVE_DB
TODAY_RUNNERS = DATA_DIR / "today_runners.json"


def open_readonly_database(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    query = "mode=ro&immutable=1" if not os.access(resolved, os.W_OK) else "mode=ro"
    conn = sqlite3.connect(f"{resolved.as_uri()}?{query}", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_course(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\s+\d{1,2}(st|nd|rd|th)?\s+\w+$", "", text, flags=re.I)
    text = re.sub(r"\s+\d{4}$", "", text)
    return text.strip()


def parse_distance_furlongs(value: Any) -> Optional[float]:
    text = str(value or "").lower()
    match = re.search(r"(\d+)m\s*(\d+)?f?", text)
    if match:
        miles = int(match.group(1))
        furlongs = int(match.group(2) or 0)
        return float(miles * 8 + furlongs)
    match = re.search(r"(\d+(?:\.\d+)?)f", text)
    if match:
        return float(match.group(1))
    return None


def load_today_race(market_id: Optional[str], horse_key: str) -> Dict[str, Any]:
    if not TODAY_RUNNERS.exists():
        return {}
    try:
        payload = json.loads(TODAY_RUNNERS.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    for race in payload.get("races", []) or []:
        runners = race.get("runners", []) or []
        has_horse = any(norm_name(r.get("name")) == horse_key for r in runners)
        if market_id and race.get("market_id") != market_id:
            continue
        if not market_id and not has_horse:
            continue
        course = clean_course((race.get("weatherRisk") or {}).get("course") or race.get("venue"))
        distance_furlongs = safe_float(race.get("distance_furlongs")) or parse_distance_furlongs(race.get("race_name"))
        return {
            "date": payload.get("date"),
            "market_id": race.get("market_id"),
            "course": course,
            "race_time": race.get("race_time"),
            "race_name": race.get("race_name"),
            "race_type": race.get("race_type"),
            "distance_furlongs": distance_furlongs,
            "runners": [
                {
                    "name": r.get("name"),
                    "horse_key": norm_name(r.get("name")),
                    "price": safe_float(r.get("best_back")),
                    "form": r.get("form"),
                    "trainer": r.get("trainer"),
                    "jockey": r.get("jockey"),
                }
                for r in runners
            ],
        }
    return {}


def rows_to_dicts(cursor: sqlite3.Cursor) -> List[Dict[str, Any]]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def recent_runs(conn: sqlite3.Connection, horse_key: str, limit: int) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT DISTINCT market_id, race_date, venue, race_time, race_name, race_type, race_subtype,
               distance_furlongs, bsp, status, sort_priority, runner_count
        FROM historical_runners
        WHERE horse_key = ? AND market_type = 'WIN'
        ORDER BY race_date DESC, race_time DESC
        LIMIT ?
        """,
        (horse_key, limit),
    )
    return rows_to_dicts(cur)


def signal_memory(conn: sqlite3.Connection, horse_key: str, limit: int) -> List[Dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT date, course, race_time, race_name, known_result, finishing_position,
               betfair_status, pre_race_price, signal_score, official_pick,
               watchlist, tipster_count, form, jockey, trainer
        FROM race_memory
        WHERE horse_key = ?
        ORDER BY date DESC, race_time DESC
        LIMIT ?
        """,
        (horse_key, limit),
    )
    return rows_to_dicts(cur)


def course_record(conn: sqlite3.Connection, horse_key: str, course: Optional[str]) -> Dict[str, Any]:
    if not course:
        return {"course": None, "runs": 0, "wins": 0}
    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT market_id) AS runs,
               COUNT(DISTINCT CASE WHEN UPPER(status) = 'WINNER' THEN market_id END) AS wins,
               MIN(race_date) AS first_seen,
               MAX(race_date) AS last_seen
        FROM historical_runners
        WHERE horse_key = ? AND LOWER(venue) = LOWER(?) AND market_type = 'WIN'
        """,
        (horse_key, course),
    )
    row = rows_to_dicts(cur)[0]
    row["course"] = course
    return row


def distance_record(conn: sqlite3.Connection, horse_key: str, distance: Optional[float]) -> Dict[str, Any]:
    if distance is None:
        return {"distance_furlongs": None, "runs": 0, "wins": 0}
    low = distance - 0.75
    high = distance + 0.75
    cur = conn.execute(
        """
        SELECT COUNT(DISTINCT market_id) AS runs,
               COUNT(DISTINCT CASE WHEN UPPER(status) = 'WINNER' THEN market_id END) AS wins,
               MIN(race_date) AS first_seen,
               MAX(race_date) AS last_seen
        FROM historical_runners
        WHERE horse_key = ? AND distance_furlongs BETWEEN ? AND ? AND market_type = 'WIN'
        """,
        (horse_key, low, high),
    )
    row = rows_to_dicts(cur)[0]
    row["distance_furlongs"] = distance
    row["range_checked"] = [round(low, 2), round(high, 2)]
    return row


def head_to_head_warnings(conn: sqlite3.Connection, horse_key: str, rival_keys: List[str], limit: int) -> List[Dict[str, Any]]:
    if not rival_keys:
        return []
    placeholders = ",".join("?" for _ in rival_keys)
    params = [horse_key, *rival_keys, horse_key, *rival_keys, limit]
    cur = conn.execute(
        f"""
        SELECT date, course, race_time, race_name, winner, loser, confidence,
               evidence_note, source
        FROM head_to_head
        WHERE (loser_key = ? AND winner_key IN ({placeholders}))
           OR (winner_key = ? AND loser_key IN ({placeholders}))
        ORDER BY date DESC
        LIMIT ?
        """,
        params,
    )
    return rows_to_dicts(cur)


def historic_rival_warnings(conn: sqlite3.Connection, horse_key: str, target_market_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    if target_market_id:
        cur = conn.execute(
            """
            SELECT target_date, target_course, target_race_time, historic_date,
                   historic_course, historic_race_type, historic_distance_furlongs,
                   winner, loser, evidence_note
            FROM historic_rivals
            WHERE target_market_id = ? AND (winner_key = ? OR loser_key = ?)
            ORDER BY historic_date DESC
            LIMIT ?
            """,
            (target_market_id, horse_key, horse_key, limit),
        )
    else:
        cur = conn.execute(
            """
            SELECT target_date, target_course, target_race_time, historic_date,
                   historic_course, historic_race_type, historic_distance_furlongs,
                   winner, loser, evidence_note
            FROM historic_rivals
            WHERE winner_key = ? OR loser_key = ?
            ORDER BY target_date DESC, historic_date DESC
            LIMIT ?
            """,
            (horse_key, horse_key, limit),
        )
    return rows_to_dicts(cur)


def poor_recent_form(form: Optional[str]) -> bool:
    if not form:
        return False
    recent = [char.upper() for char in str(form) if char.upper() in "0123456789PFUR"]
    recent = recent[-3:]
    if len(recent) < 3:
        return False
    bad = sum(1 for char in recent if char in {"0", "9", "P", "F", "U", "R"} or char.isdigit() and int(char) >= 8)
    return bad >= 2


def build_warnings(summary: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    today_runner = summary.get("today_runner") or {}
    course = summary.get("course_record") or {}
    distance = summary.get("distance_record") or {}

    if poor_recent_form(today_runner.get("form")):
        warnings.append("Poor recent form pattern")
    if course.get("runs", 0) == 0:
        warnings.append("No previous course evidence found")
    elif course.get("wins", 0) == 0:
        warnings.append("Course run found, but no course win")
    if distance.get("runs", 0) == 0:
        warnings.append("No close-distance evidence found")
    elif distance.get("wins", 0) == 0:
        warnings.append("Distance run found, but no distance win")
    for row in summary.get("head_to_head", []):
        if norm_name(row.get("loser")) == summary["horse_key"]:
            warnings.append(f"Previously beaten by today's rival: {row.get('winner')}")
    for row in summary.get("historic_rivals", []):
        if norm_name(row.get("loser")) == summary["horse_key"]:
            warnings.append(f"Historic rival warning: previously beaten by {row.get('winner')}")

    return list(dict.fromkeys(warnings))


def lookup(db_path: Path, horse: str, market_id: Optional[str], limit: int) -> Dict[str, Any]:
    horse_key = norm_name(horse)
    today_race = load_today_race(market_id, horse_key)
    today_runner = {}
    rival_keys: List[str] = []
    for runner in today_race.get("runners", []):
        if runner["horse_key"] == horse_key:
            today_runner = runner
        elif runner["horse_key"]:
            rival_keys.append(runner["horse_key"])

    conn = open_readonly_database(db_path)
    try:
        summary = {
            "horse": horse,
            "horse_key": horse_key,
            "database": str(db_path),
            "today_race": {k: v for k, v in today_race.items() if k != "runners"},
            "today_runner": today_runner,
            "recent_historical_runs": recent_runs(conn, horse_key, limit),
            "signal75_memory": signal_memory(conn, horse_key, limit),
            "course_record": course_record(conn, horse_key, today_race.get("course")),
            "distance_record": distance_record(conn, horse_key, today_race.get("distance_furlongs")),
            "head_to_head": head_to_head_warnings(conn, horse_key, rival_keys, limit),
            "historic_rivals": historic_rival_warnings(conn, horse_key, today_race.get("market_id") or market_id, limit),
        }
    finally:
        conn.close()

    summary["warnings"] = build_warnings(summary)
    return summary


def print_text(summary: Dict[str, Any]) -> None:
    race = summary.get("today_race") or {}
    runner = summary.get("today_runner") or {}
    print(f"Signal 75 intelligence lookup: {summary['horse']}")
    if race:
        print(f"Race: {race.get('race_time')} {race.get('course')} — {race.get('race_name')}")
    if runner:
        print(f"Today: price {runner.get('price')} · form {runner.get('form')} · jockey {runner.get('jockey')} · trainer {runner.get('trainer')}")

    warnings = summary.get("warnings") or []
    print("\nWarnings:")
    if warnings:
        for idx, warning in enumerate(warnings, start=1):
            print(f"{idx}. {warning}")
    else:
        print("None found")

    print("\nRecent historical runs:")
    for row in summary.get("recent_historical_runs", [])[:5]:
        print(f"- {row.get('race_date')} {row.get('venue')} {row.get('race_name')} · {row.get('status')} · BSP {row.get('bsp')}")

    print("\nRival evidence:")
    evidence = (summary.get("head_to_head") or []) + (summary.get("historic_rivals") or [])
    if evidence:
        for row in evidence[:8]:
            print(f"- {row.get('evidence_note')}")
    else:
        print("No same-race rival evidence found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Signal 75 horse intelligence lookup.")
    parser.add_argument("horse", help="Horse name")
    parser.add_argument("--market-id", help="Optional today's market id")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}. Run scripts/build-intelligence-db.py first.")

    summary = lookup(db_path, args.horse, args.market_id, args.limit)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print_text(summary)


if __name__ == "__main__":
    main()
