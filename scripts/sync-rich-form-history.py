#!/usr/bin/env python3
"""Sync daily Signal 75 race context into the rich form SQLite archive.

This is storage only. It does not change scoring, picks, settlement, proof,
public ROI, or dashboard logic. The historical provider archive currently ends
in June 2026, so this script keeps the local rich-form store growing from the
daily Signal 75 files we already create:

* racecards: pre-race runner context from today_runners/race_comparison
* form_results: post-race runner context from race_memory_YYYY-MM-DD when
  available
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"
FORM_DB = INTEL / "form_history.sqlite"
STATUS = INTEL / "form_history_status.json"
IMPORTER = REPO_ROOT / "scripts" / "import-form-history-archive.py"


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None, "-", "–"):
            return None
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None, "-", "–"):
            return None
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def weight_to_lbs(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    match = re.match(r"^(\d+)-(\d+)$", text)
    if match:
        return int(match.group(1)) * 14 + int(match.group(2))
    return safe_int(value)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def race_id(value: Any) -> int:
    text = clean_text(value) or "unknown"
    return zlib.crc32(text.encode("utf-8")) & 0x7FFFFFFF


def hhmm(value: Any) -> str:
    text = str(value or "")
    match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    return match.group(1) if match else clean_text(value)


def distance_from_race_name(value: Any) -> str:
    text = clean_text(value)
    match = re.search(r"\b\d+m\d*f?|\b\d+f\b", text, flags=re.I)
    return match.group(0) if match else ""


def connect() -> sqlite3.Connection:
    if not FORM_DB.exists():
        raise SystemExit(f"Rich form database not found: {FORM_DB}")
    conn = sqlite3.connect(str(FORM_DB))
    conn.row_factory = sqlite3.Row
    return conn


def iter_runner_cache(date_text: str) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    payload = read_json(DATA / "today_runners.json", {})
    if payload.get("date") != date_text:
        return []
    return [
        (race, runner)
        for race in payload.get("races", [])
        for runner in race.get("runners", [])
        if isinstance(race, dict) and isinstance(runner, dict)
    ]


def iter_race_comparison(date_text: str) -> Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]:
    payload = read_json(DATA / f"race_comparison_{date_text}.json", {})
    return [
        (race, runner)
        for race in payload.get("races", [])
        for runner in race.get("runners", [])
        if isinstance(race, dict) and isinstance(runner, dict)
    ]


def sync_racecards(conn: sqlite3.Connection, date_text: str) -> int:
    rows = list(iter_runner_cache(date_text))
    source = "today_runners"
    if not rows:
        rows = list(iter_race_comparison(date_text))
        source = "race_comparison"
    if not rows:
        return 0

    sql = """
        INSERT OR REPLACE INTO racecards (
            date, region, course, going, off_time, distance, race_name,
            horse_name, horse_key, field_size, draw, age, weight_lbs, form,
            jockey, owner, race_class, rpr, sex, sire, dam, spotlight, comment,
            trainer, trainer_14_days_json, trainer_rtf, topspeed, stable_tour,
            stats_json, medical_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    for race, runner in rows:
        horse = clean_text(runner.get("name") or runner.get("horse_name"))
        key = norm_name(horse)
        if not key:
            continue
        race_name = clean_text(race.get("race_name"))
        conn.execute(
            sql,
            (
                date_text,
                clean_text(race.get("region")),
                clean_text(race.get("course") or race.get("venue")),
                clean_text(race.get("going")),
                hhmm(race.get("time") or race.get("race_time")),
                clean_text(race.get("distance")) or distance_from_race_name(race_name),
                race_name,
                horse,
                key,
                safe_int(race.get("field_size")) or safe_int(race.get("runner_count")) or len(race.get("runners", [])),
                safe_int(runner.get("stall_draw") or runner.get("draw")),
                safe_int(runner.get("age")),
                weight_to_lbs(runner.get("weight") or runner.get("lbs")),
                clean_text(runner.get("form")),
                clean_text(runner.get("jockey")),
                clean_text(runner.get("owner")),
                clean_text(race.get("race_class") or runner.get("race_class")),
                safe_int(runner.get("rpr")),
                clean_text(runner.get("sex")),
                clean_text(runner.get("sire")),
                clean_text(runner.get("dam")),
                "",
                f"Signal75 daily sync from {source}",
                clean_text(runner.get("trainer")),
                "",
                None,
                safe_int(runner.get("topspeed") or runner.get("ts")),
                "",
                json.dumps({"source": source}, sort_keys=True),
                "",
            ),
        )
        count += 1
    return count


def result_position(record: Dict[str, Any]) -> Optional[int]:
    position = safe_int(record.get("finishing_position"))
    if position is not None and position > 0:
        return position
    result = str(record.get("known_result") or "").upper()
    return 1 if result == "WON" else None


def sync_results(conn: sqlite3.Connection, date_text: str) -> int:
    payload = read_json(INTEL / f"race_memory_{date_text}.json", {})
    records = payload.get("records", [])
    if not records:
        return 0
    full_payload = read_json(INTEL / f"full_field_results_{date_text}.json", {})
    full_lookup: Dict[tuple, Dict[str, Any]] = {}
    full_rows = full_payload.get("records", []) or []
    if not full_rows:
        full_rows = [
            row
            for race in full_payload.get("races", []) or []
            for row in race.get("runners", []) or []
        ]
    for row in full_rows:
        key = (str(row.get("market_id") or ""), norm_name(row.get("horse_name")))
        if all(key):
            full_lookup[key] = row

    sql = """
        INSERT OR REPLACE INTO form_results (
            date, course, race_id, off_time, race_name, race_type, race_class,
            pattern, rating_band, age_band, sex_restriction, distance, going,
            runners, runner_number, position, draw, distance_from_winner,
            beaten_by, horse_name, horse_key, age, sex, weight, weight_lbs,
            headgear, winning_time, sp, sp_decimal, jockey, trainer, prize,
            official_rating, rpr, topspeed, sire, dam, damsire, owner,
            race_comment, source_archive
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    count = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        horse = clean_text(record.get("horse_name"))
        key = norm_name(horse)
        if not key:
            continue
        market_id = record.get("market_id") or "|".join(
            [date_text, clean_text(record.get("course")), clean_text(record.get("race_time")), clean_text(record.get("race_name"))]
        )
        full_result = full_lookup.get((str(record.get("market_id") or ""), key), {})
        pos = safe_int(full_result.get("position")) or result_position(record)
        conn.execute(
            sql,
            (
                date_text,
                clean_text(record.get("course")),
                race_id(market_id),
                hhmm(record.get("race_time")),
                clean_text(record.get("race_name")),
                clean_text(record.get("race_type")),
                clean_text(record.get("race_class_label")),
                clean_text(record.get("form")),
                "",
                "",
                "",
                clean_text(record.get("distance_furlongs")) or clean_text(record.get("distance_band")),
                clean_text(record.get("going")),
                safe_int(record.get("field_size")),
                safe_int(record.get("selection_id")),
                pos,
                safe_int(record.get("stall_draw")),
                safe_float(full_result.get("distance_from_winner")) if full_result else safe_float(record.get("distance_from_winner")),
                safe_float(full_result.get("beaten_by")) if full_result else safe_float(record.get("beaten_by")),
                horse,
                key,
                safe_int(record.get("age")),
                clean_text(record.get("sex")),
                clean_text(record.get("weight")),
                safe_int(record.get("carried_weight_lbs")),
                "",
                "",
                clean_text(full_result.get("sp_decimal") or record.get("sp_decimal") or record.get("bookmaker_odds_text")),
                safe_float(full_result.get("sp_decimal") or record.get("sp_decimal") or record.get("settlement_odds") or record.get("bsp") or record.get("pre_race_price")),
                clean_text(record.get("jockey")),
                clean_text(record.get("trainer")),
                None,
                safe_int(record.get("official_rating")),
                safe_int(record.get("rpr")),
                safe_int(record.get("topspeed")),
                "",
                "",
                "",
                "",
                clean_text(record.get("book_insight")),
                "signal75_full_field_results" if full_result or record.get("full_result_source") else "signal75_daily_race_memory",
            ),
        )
        count += 1
    return count


def rebuild_pattern_stats(conn: sqlite3.Connection) -> int:
    spec = importlib.util.spec_from_file_location("import_form_history_archive", IMPORTER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    conn.execute("DELETE FROM form_pattern_stats")
    return int(module.build_form_pattern_stats(conn))


def summary(conn: sqlite3.Connection) -> Dict[str, Any]:
    return {
        "formResultsRows": conn.execute("SELECT COUNT(*) FROM form_results").fetchone()[0],
        "racecardRows": conn.execute("SELECT COUNT(*) FROM racecards").fetchone()[0],
        "formPatternRows": conn.execute("SELECT COUNT(*) FROM form_pattern_stats").fetchone()[0],
        "latestDate": conn.execute("SELECT MAX(date) FROM form_results").fetchone()[0],
        "latestRacecardDate": conn.execute("SELECT MAX(date) FROM racecards").fetchone()[0],
    }


def update_status(sync_payload: Dict[str, Any], db_summary: Dict[str, Any]) -> None:
    previous = read_json(STATUS, {})
    payload = {
        **previous,
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "database": str(FORM_DB),
        "purpose": (
            "Historical rich-form archive plus Signal 75 daily sync. Archive data "
            "comes from the downloaded source; newer racecards/results are synced "
            "from Signal 75 daily files where available."
        ),
        "dailySync": sync_payload,
        **db_summary,
    }
    write_json(STATUS, payload)


def date_range(start: str, end: str) -> List[str]:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return [(start_date + timedelta(days=i)).isoformat() for i in range((end_date - start_date).days + 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Signal 75 daily race context into form_history.sqlite.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--rebuild-pattern-stats", action="store_true")
    args = parser.parse_args()

    dates = date_range(args.start_date, args.end_date) if args.start_date and args.end_date else [args.date]
    FORM_DB.parent.mkdir(parents=True, exist_ok=True)

    totals = {"racecards": 0, "formResults": 0, "dates": dates}
    with connect() as conn:
        for date_text in dates:
            racecard_count = sync_racecards(conn, date_text)
            result_count = sync_results(conn, date_text)
            totals["racecards"] += racecard_count
            totals["formResults"] += result_count
            print(f"{date_text}: racecards={racecard_count} form_results={result_count}")
        if args.rebuild_pattern_stats:
            totals["formPatternRows"] = rebuild_pattern_stats(conn)
        conn.commit()
        db_summary = summary(conn)

    sync_payload = {
        "syncedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Signal75 daily files",
        "analysisOnly": True,
        "scoringImpact": "none",
        **totals,
    }
    update_status(sync_payload, db_summary)
    print("Rich form daily sync complete")
    for key, value in db_summary.items():
        print(f"- {key}: {value:,}" if isinstance(value, int) else f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
