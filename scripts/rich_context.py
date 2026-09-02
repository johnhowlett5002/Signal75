#!/usr/bin/env python3
"""Read-only rich-form context for a runner, with safe horse-name matching."""

from __future__ import annotations

import re
import sqlite3
import atexit
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


COUNTRY_SUFFIX_RE = re.compile(r"\s*\(([A-Z]{2,3})\)\s*$", re.IGNORECASE)
FRACTIONS = {"\u00bc": 0.25, "\u00bd": 0.5, "\u00be": 0.75}
_CONNECTIONS: Dict[str, sqlite3.Connection] = {}


def horse_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def canonical_horse_key(value: Any) -> str:
    """Normalise a horse name while removing only a trailing country marker."""
    return horse_key(COUNTRY_SUFFIX_RE.sub("", str(value or "").strip()))


def normalise_course(value: Any) -> str:
    text = re.sub(r"\s*\([^)]*\)\s*$", "", str(value or "").strip())
    text = re.sub(
        r"\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _fraction_value(text: str) -> float:
    return sum(value for marker, value in FRACTIONS.items() if marker in text)


def distance_furlongs(value: Any) -> Optional[float]:
    text = str(value or "").strip().lower().replace(" ", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    miles_match = re.search(r"(\d+(?:\.\d+)?)m", text)
    furlong_match = re.search(r"(\d+(?:\.\d+)?)([\u00bc\u00bd\u00be]?)f", text)
    yards_match = re.search(r"(\d+)y", text)
    if not any((miles_match, furlong_match, yards_match)):
        return None
    total = float(miles_match.group(1)) * 8 if miles_match else 0.0
    if furlong_match:
        total += float(furlong_match.group(1)) + _fraction_value(furlong_match.group(2))
    if yards_match:
        total += float(yards_match.group(1)) / 220.0
    return round(total, 2)


def normalise_going(value: Any) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def _position(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status(known_dimension: bool, history_count: int, matching_runs: int, wins: int) -> str:
    if not known_dimension or history_count <= 0:
        return "unknown"
    if wins > 0:
        return "proven"
    return "unproven"


def _open_readonly(path: Path) -> sqlite3.Connection:
    key = str(path.resolve())
    existing = _CONNECTIONS.get(key)
    if existing is not None:
        return existing
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    _CONNECTIONS[key] = connection
    return connection


def close_connections() -> None:
    for connection in _CONNECTIONS.values():
        connection.close()
    _CONNECTIONS.clear()


atexit.register(close_connections)


@lru_cache(maxsize=4096)
def _historical_rows_cached(path_text: str, base_key: str, before_date: str, limit: int) -> tuple:
    connection = _open_readonly(Path(path_text))
    rows = connection.execute(
        """
        SELECT date, course, race_id, off_time, race_name, race_type,
               race_class, distance, going, runners, position, draw,
               horse_name, horse_key, weight_lbs, jockey, trainer,
               official_rating, rpr, topspeed
        FROM form_results
        WHERE horse_key GLOB ? AND date < ?
        ORDER BY date DESC
        LIMIT 1000
        """,
        (base_key + "*", before_date),
    ).fetchall()
    matched = [dict(row) for row in rows if canonical_horse_key(row["horse_name"]) == base_key]
    deduped: Dict[tuple, Dict[str, Any]] = {}
    for row in matched:
        key = (row.get("date"), row.get("race_id") or row.get("off_time"), normalise_course(row.get("course")))
        existing = deduped.get(key)
        richness = sum(row.get(field) not in (None, "") for field in ("race_class", "going", "rpr", "distance"))
        old_richness = sum(existing.get(field) not in (None, "") for field in ("race_class", "going", "rpr", "distance")) if existing else -1
        if richness > old_richness:
            deduped[key] = row
    selected = sorted(deduped.values(), key=lambda row: str(row.get("date") or ""), reverse=True)[:limit]
    return tuple(tuple(row.items()) for row in selected)


def historical_rows(
    database: Path | str,
    name: Any,
    before_date: str,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Return the named horse's prior rows without prefix-name collisions."""
    path = Path(database)
    base_key = canonical_horse_key(name)
    if not path.exists() or not base_key or not before_date:
        return []
    cached = _historical_rows_cached(str(path.resolve()), base_key, before_date, limit)
    return [dict(row) for row in cached]


def current_racecard(
    database: Path | str,
    name: Any,
    race_date: str,
    course: Any = "",
) -> Dict[str, Any]:
    path = Path(database)
    base_key = canonical_horse_key(name)
    if not path.exists() or not base_key or not race_date:
        return {}
    connection = _open_readonly(path)
    rows = connection.execute(
        "SELECT * FROM racecards WHERE date = ? AND horse_key GLOB ?",
        (race_date, base_key + "*"),
    ).fetchall()
    candidates = [dict(row) for row in rows if canonical_horse_key(row["horse_name"]) == base_key]
    wanted_course = normalise_course(course)
    if wanted_course:
        course_matches = [row for row in candidates if normalise_course(row.get("course")) == wanted_course]
        if course_matches:
            candidates = course_matches
    if not candidates:
        return {}
    return max(
        candidates,
        key=lambda row: sum(
            row.get(field) not in (None, "")
            for field in ("going", "race_class", "rpr", "trainer_rtf", "distance", "draw", "weight_lbs")
        ),
    )


def build_runner_context(
    database: Path | str,
    runner: Dict[str, Any],
    race_date: str,
) -> Dict[str, Any]:
    history = historical_rows(database, runner.get("name") or runner.get("horse_name"), race_date)
    card = current_racecard(
        database,
        runner.get("name") or runner.get("horse_name"),
        race_date,
        runner.get("venue") or runner.get("course"),
    )

    current_course = normalise_course(runner.get("venue") or runner.get("course") or card.get("course"))
    current_distance = distance_furlongs(
        runner.get("distance") or card.get("distance") or runner.get("race_name")
    )
    current_going_raw = runner.get("going") or card.get("going")
    current_going = normalise_going(current_going_raw)

    course_rows = [row for row in history if current_course and normalise_course(row.get("course")) == current_course]
    distance_rows = [
        row for row in history
        if current_distance is not None
        and distance_furlongs(row.get("distance")) is not None
        and abs(distance_furlongs(row.get("distance")) - current_distance) <= 0.25
    ]
    going_rows = [row for row in history if current_going and normalise_going(row.get("going")) == current_going]

    def wins(rows: Iterable[Dict[str, Any]]) -> int:
        return sum(_position(row.get("position")) == 1 for row in rows)

    course_wins = wins(course_rows)
    distance_wins = wins(distance_rows)
    going_wins = wins(going_rows)
    current_jockey = str(runner.get("jockey") or card.get("jockey") or "").strip().lower()
    current_trainer = str(runner.get("trainer") or card.get("trainer") or "").strip().lower()
    jockey_rows = [row for row in history if current_jockey and str(row.get("jockey") or "").strip().lower() == current_jockey]
    trainer_rows = [row for row in history if current_trainer and str(row.get("trainer") or "").strip().lower() == current_trainer]

    statuses = {
        "course": _status(bool(current_course), len(history), len(course_rows), course_wins),
        "distance": _status(current_distance is not None, len(history), len(distance_rows), distance_wins),
        "going": _status(bool(current_going), len(history), len(going_rows), going_wins),
        "draw": "known" if (runner.get("stall_draw") or card.get("draw")) not in (None, "") else "unknown",
        "weight": "known" if (runner.get("weight") or card.get("weight_lbs")) not in (None, "") else "unknown",
        "jockey": "known" if current_jockey else "unknown",
        "trainer": "known" if current_trainer else "unknown",
        "rpr": "known" if card.get("rpr") not in (None, "") else "unknown",
    }
    latest_run_date = history[0].get("date") if history else None
    try:
        days_since_last_run = (date.fromisoformat(race_date) - date.fromisoformat(str(latest_run_date))).days
    except (TypeError, ValueError):
        days_since_last_run = None
    return {
        "source": "form_history.sqlite",
        "asOfDateExclusive": race_date,
        "matchedHorseKey": canonical_horse_key(runner.get("name") or runner.get("horse_name")),
        "historyRuns": len(history),
        "latestRunDate": latest_run_date,
        "daysSinceLastRun": days_since_last_run,
        "courseRuns": len(course_rows) if current_course else None,
        "courseWins": course_wins if current_course and history else None,
        "distanceRuns": len(distance_rows) if current_distance is not None else None,
        "distanceWins": distance_wins if current_distance is not None and history else None,
        "goingRuns": len(going_rows) if current_going else None,
        "goingWins": going_wins if current_going and history else None,
        "distanceFurlongs": current_distance,
        "going": current_going_raw or None,
        "draw": runner.get("stall_draw") if runner.get("stall_draw") not in (None, "") else card.get("draw"),
        "weightLbs": runner.get("weight") if runner.get("weight") not in (None, "") else card.get("weight_lbs"),
        "rpr": card.get("rpr"),
        "raceClass": card.get("race_class") or None,
        "trainerRtf": card.get("trainer_rtf"),
        "jockeyHorseRuns": len(jockey_rows) if current_jockey and history else None,
        "jockeyHorseWins": wins(jockey_rows) if current_jockey and history else None,
        "trainerHorseRuns": len(trainer_rows) if current_trainer and history else None,
        "trainerHorseWins": wins(trainer_rows) if current_trainer and history else None,
        "statuses": statuses,
    }
