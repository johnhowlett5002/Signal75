#!/usr/bin/env python3
"""Build the combined Signal 75 learning layer.

This joins Signal 75 selections, Grandad/race memory, head-to-head evidence,
historic rival evidence, pasted tipster intelligence, and known results.

It is analysis/storage only. It does not change live scoring, picks, proof,
settlement, results maths, unlock logic, public JSON structures, or automation.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
HORSE_INTEL_DIR = DATA_DIR / "horse_intelligence"
TIPSTER_DIR = DATA_DIR / "tipster_intelligence"
OUT_DIR = DATA_DIR / "combined_learning"
DEFAULT_DB = OUT_DIR / "signal75_learning.sqlite"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalise(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def source_path(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def record_key(date: str, market_id: Any, course: Any, race_time: Any, horse_name: Any) -> Tuple[str, str, str, str, str]:
    return (
        str(date or ""),
        str(market_id or ""),
        clean_text(course).upper(),
        clean_text(race_time),
        normalise(horse_name),
    )


def fallback_key(date: str, course: Any, race_time: Any, horse_name: Any) -> Tuple[str, str, str, str]:
    return (str(date or ""), clean_text(course).upper(), clean_text(race_time), normalise(horse_name))


def selection_type_from_record(record: Dict[str, Any]) -> str:
    if record.get("official_pick"):
        return "OFFICIAL"
    if record.get("watchlist"):
        return "WATCHLIST"
    return "RUNNER"


def result_flags(record: Dict[str, Any]) -> Tuple[str, Optional[int], int, int]:
    result = clean_text(record.get("result") or record.get("known_result") or record.get("radarResult") or record.get("status"))
    position = safe_int(record.get("position") or record.get("finishing_position"))
    result_upper = result.upper()
    won = 1 if "WON" in result_upper or position == 1 else 0
    placed = 0
    if won:
        placed = 1
    elif "PLACED" in result_upper:
        placed = 1
    elif position:
        field = safe_int(record.get("runners") or record.get("field_size")) or 0
        placed = 1 if position <= (2 if field and field < 8 else 3) else 0
    return result, position, won, placed


def iter_daily_horses(daily: Dict[str, Any], date: str) -> Iterable[Dict[str, Any]]:
    seen: set[Tuple[str, str, str, str, str]] = set()
    for bucket, selection_type in (
        ("flat", "OFFICIAL"),
        ("jumps", "OFFICIAL"),
        ("topRated", "WATCHLIST"),
        ("topRatedFlat", "WATCHLIST"),
        ("topRatedJumps", "WATCHLIST"),
    ):
        for item in daily.get(bucket, []) or []:
            if "horses" in item:
                race = item
                for horse in item.get("horses") or []:
                    row = dict(horse)
                    row.setdefault("course", race.get("course") or race.get("venue"))
                    row.setdefault("venue", race.get("venue") or race.get("course"))
                    row.setdefault("time", race.get("time"))
                    row.setdefault("race", race.get("race") or race.get("name"))
                    row.setdefault("race_type", race.get("type") or race.get("race_type"))
                    row.setdefault("runners", race.get("runners"))
                    row["_selection_type"] = selection_type
                    key = record_key(date, row.get("market_id"), row.get("venue") or row.get("course"), row.get("time"), row.get("name") or row.get("horse_name"))
                    if key not in seen:
                        seen.add(key)
                        yield row
            else:
                row = dict(item)
                row["_selection_type"] = selection_type
                key = record_key(date, row.get("market_id"), row.get("venue") or row.get("course"), row.get("time"), row.get("name") or row.get("horse_name"))
                if key not in seen:
                    seen.add(key)
                    yield row


def memory_indexes(records: Iterable[Dict[str, Any]], date: str) -> Tuple[Dict[Tuple[str, str, str, str, str], Dict[str, Any]], Dict[Tuple[str, str, str, str], Dict[str, Any]]]:
    exact: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    fallback: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for record in records:
        horse = record.get("horse_name") or record.get("name")
        course = record.get("course") or record.get("venue")
        race_time = record.get("race_time") or record.get("time")
        exact[record_key(date, record.get("market_id"), course, race_time, horse)] = record
        exact[record_key(date, record.get("market_id"), course, "", horse)] = record
        fallback[fallback_key(date, course, race_time, horse)] = record
    return exact, fallback


def tipster_indexes(records: Iterable[Dict[str, Any]], date: str) -> Tuple[Dict[Tuple[str, str, str, str, str], Dict[str, Any]], Dict[Tuple[str, str, str, str], Dict[str, Any]]]:
    exact: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    fallback: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for record in records:
        horse = record.get("horse_name") or record.get("name")
        course = record.get("course") or record.get("venue")
        race_time = record.get("race_time") or record.get("time")
        exact[record_key(date, record.get("market_id"), course, race_time, horse)] = record
        exact[record_key(date, record.get("market_id"), course, "", horse)] = record
        fallback[fallback_key(date, course, race_time, horse)] = record
    return exact, fallback


def result_note_indexes(records: Iterable[Dict[str, Any]], date: str) -> Tuple[Dict[Tuple[str, str, str, str, str], Dict[str, Any]], Dict[Tuple[str, str, str, str], Dict[str, Any]]]:
    exact: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    fallback: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for record in records:
        horse = record.get("horse_name") or record.get("name")
        course = record.get("course") or record.get("venue")
        times = [record.get("race_time") or record.get("time"), record.get("runner_cache_time"), ""]
        for race_time in times:
            exact[record_key(date, record.get("market_id"), course, race_time, horse)] = record
            if race_time:
                fallback[fallback_key(date, course, race_time, horse)] = record
    return exact, fallback


def find_match(
    date: str,
    market_id: Any,
    course: Any,
    race_time: Any,
    horse: Any,
    exact: Dict[Tuple[str, str, str, str, str], Dict[str, Any]],
    fallback: Dict[Tuple[str, str, str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    return (
        exact.get(record_key(date, market_id, course, race_time, horse))
        or exact.get(record_key(date, market_id, course, "", horse))
        or fallback.get(fallback_key(date, course, race_time, horse))
        or {}
    )


def build_h2h_maps(records: Iterable[Dict[str, Any]]) -> Tuple[Dict[Tuple[str, str], List[Dict[str, Any]]], Dict[Tuple[str, str], List[Dict[str, Any]]]]:
    wins: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    losses: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        market = str(record.get("market_id") or "")
        winner = normalise(record.get("winner"))
        loser = normalise(record.get("loser"))
        if winner:
            wins[(market, winner)].append(record)
        if loser:
            losses[(market, loser)].append(record)
    return wins, losses


def build_historic_maps(records: Iterable[Dict[str, Any]]) -> Tuple[Dict[Tuple[str, str], List[Dict[str, Any]]], Dict[Tuple[str, str], List[Dict[str, Any]]]]:
    positive: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    negative: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        market = str(record.get("target_market_id") or "")
        winner = normalise(record.get("winner"))
        loser = normalise(record.get("loser"))
        if winner:
            positive[(market, winner)].append(record)
        if loser:
            negative[(market, loser)].append(record)
    return positive, negative


def consensus_count(tipster: Dict[str, Any], signal: Dict[str, Any], memory: Dict[str, Any]) -> int:
    for value in (
        tipster.get("explicit_tip_count"),
        tipster.get("mention_count"),
        signal.get("tipsters"),
        memory.get("tipster_count"),
    ):
        number = safe_int(value)
        if number is not None and number > 0:
            return number
    consensus = signal.get("consensus") if isinstance(signal.get("consensus"), dict) else {}
    for key in ("consensus_count", "tip_count", "source_count"):
        number = safe_int(consensus.get(key))
        if number is not None and number > 0:
            return number
    return 0


def combined_view(signal_score: Optional[float], tip_count: int, tipster: Dict[str, Any], h2h_losses: int, historic_negative: int, historic_positive: int, memory_tags: List[str]) -> str:
    market = str(tipster.get("market_confidence") or "")
    danger = bool(tipster.get("danger_flag"))
    value = bool(tipster.get("value_flag"))
    negative_signal = h2h_losses > 0 or historic_negative > 0 or danger
    if signal_score is not None and signal_score >= 75 and tip_count >= 7 and not negative_signal:
        return "Validated by Signal + Consensus"
    if signal_score is not None and signal_score >= 75 and negative_signal:
        return "Grandad Warning"
    if tip_count >= 7 and signal_score is None:
        return "Consensus Leader"
    if tip_count >= 7 and signal_score < 70:
        return "Overhyped Watch"
    if signal_score is not None and signal_score >= 80 and tip_count == 0 and not negative_signal:
        return "Contrarian Signal"
    if signal_score is not None and signal_score >= 70 and value:
        return "Value Overlay"
    if historic_positive > 0 and not negative_signal:
        return "Grandad Positive"
    if signal_score is not None and signal_score >= 75 and market in {"Positive", "Strong Positive"}:
        return "Market Support"
    if memory_tags:
        return "Grandad Memory"
    return "Learning Only"


def learning_questions(view: str, tip_count: int, h2h_losses: int, historic_negative: int, historic_positive: int) -> List[str]:
    questions = ["Did this evidence improve or weaken the Signal 75 decision?"]
    if tip_count:
        questions.append("Did tipster consensus improve win/place performance?")
    if h2h_losses or historic_negative:
        questions.append("Did the Grandad warning predict underperformance?")
    if historic_positive:
        questions.append("Did previous rival strength carry forward today?")
    if view in {"Overhyped Watch", "Contrarian Signal"}:
        questions.append("Was public opinion helpful here or misleading?")
    return questions


def build_combined(date: str, daily_file: Path, memory_file: Path, h2h_file: Path, rivals_file: Path, tipster_file: Path, result_notes_file: Path) -> Dict[str, Any]:
    daily = load_json(daily_file, {})
    memory_payload = load_json(memory_file, {})
    h2h_payload = load_json(h2h_file, {})
    rivals_payload = load_json(rivals_file, {})
    tipster_payload = load_json(tipster_file, {})
    result_notes_payload = load_json(result_notes_file, {})

    memory_records = memory_payload.get("records") if isinstance(memory_payload, dict) else []
    h2h_records = h2h_payload.get("records") if isinstance(h2h_payload, dict) else []
    rival_records = rivals_payload.get("records") if isinstance(rivals_payload, dict) else []
    tipster_records = tipster_payload.get("records") if isinstance(tipster_payload, dict) else []
    result_note_records = result_notes_payload.get("records") if isinstance(result_notes_payload, dict) else []

    memory_exact, memory_fallback = memory_indexes(memory_records or [], date)
    tipster_exact, tipster_fallback = tipster_indexes(tipster_records or [], date)
    result_note_exact, result_note_fallback = result_note_indexes(result_note_records or [], date)
    h2h_wins, h2h_losses = build_h2h_maps(h2h_records or [])
    historic_positive, historic_negative = build_historic_maps(rival_records or [])

    base_rows: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}

    for row in iter_daily_horses(daily, date):
        horse = row.get("name") or row.get("horse_name") or row.get("horse")
        course = row.get("venue") or row.get("course")
        race_time = row.get("time") or row.get("race_time")
        note = find_match(date, row.get("market_id"), course, race_time, horse, result_note_exact, result_note_fallback)
        key_market = note.get("market_id") or row.get("market_id")
        key_time = note.get("runner_cache_time") or note.get("race_time") or race_time
        key_course = note.get("course") or course
        key = record_key(date, key_market, key_course, key_time, horse)
        base_rows[key] = row

    for row in memory_records or []:
        horse = row.get("horse_name") or row.get("name")
        course = row.get("course") or row.get("venue")
        race_time = row.get("race_time") or row.get("time")
        key = record_key(date, row.get("market_id"), course, race_time, horse)
        base_rows.setdefault(key, row)

    for row in tipster_records or []:
        horse = row.get("horse_name") or row.get("name")
        course = row.get("course") or row.get("venue")
        race_time = row.get("race_time") or row.get("time")
        key = record_key(date, row.get("market_id"), course, race_time, horse)
        tipster_row = dict(row)
        tipster_row["_selection_type"] = "TIPSTER_ONLY"
        base_rows.setdefault(key, tipster_row)

    for row in result_note_records or []:
        horse = row.get("horse_name") or row.get("name")
        course = row.get("course") or row.get("venue")
        race_time = row.get("runner_cache_time") or row.get("race_time") or row.get("time")
        key = record_key(date, row.get("market_id"), course, race_time, horse)
        note_row = dict(row)
        note_row["_selection_type"] = "RUNNER"
        base_rows.setdefault(key, note_row)

    combined_rows: List[Dict[str, Any]] = []
    for key, signal_row in sorted(base_rows.items(), key=lambda item: (item[0][2], item[0][3], item[0][4])):
        horse = signal_row.get("name") or signal_row.get("horse_name") or signal_row.get("horse")
        course = signal_row.get("venue") or signal_row.get("course")
        race_time = signal_row.get("time") or signal_row.get("race_time")
        market_id = signal_row.get("market_id")
        memory = find_match(date, market_id, course, race_time, horse, memory_exact, memory_fallback)
        tipster = find_match(date, market_id, course, race_time, horse, tipster_exact, tipster_fallback)
        result_note = find_match(date, market_id, course, race_time, horse, result_note_exact, result_note_fallback)

        if not memory and result_note:
            memory = find_match(
                date,
                result_note.get("market_id"),
                result_note.get("course"),
                result_note.get("runner_cache_time") or result_note.get("race_time"),
                horse,
                memory_exact,
                memory_fallback,
            )

        final_course = course or memory.get("course") or tipster.get("course") or result_note.get("course")
        final_time = result_note.get("race_time") or race_time or memory.get("race_time") or tipster.get("race_time")
        final_market = market_id or memory.get("market_id") or tipster.get("market_id") or result_note.get("market_id")
        horse_key = normalise(horse)
        h2h_win_items = h2h_wins.get((str(final_market or ""), horse_key), [])
        h2h_loss_items = h2h_losses.get((str(final_market or ""), horse_key), [])
        historic_positive_items = historic_positive.get((str(final_market or ""), horse_key), [])
        historic_negative_items = historic_negative.get((str(final_market or ""), horse_key), [])

        signal_score = safe_float(
            signal_row.get("signal_score")
            or signal_row.get("score")
            or memory.get("signal_score")
            or tipster.get("signal_score")
        )
        result, position, won, placed = result_flags({**memory, **signal_row, **result_note})
        memory_tags = memory.get("memory_tags") if isinstance(memory.get("memory_tags"), list) else []
        tip_count = consensus_count(tipster, signal_row, memory)
        view = combined_view(
            signal_score,
            tip_count,
            tipster,
            len(h2h_loss_items),
            len(historic_negative_items),
            len(historic_positive_items),
            memory_tags,
        )

        selection_type = signal_row.get("_selection_type") or selection_type_from_record(memory)
        if memory.get("official_pick"):
            selection_type = "OFFICIAL"
        elif memory.get("watchlist") and selection_type == "RUNNER":
            selection_type = "WATCHLIST"

        combined_rows.append(
            {
                "date": date,
                "course": final_course or "",
                "race_time": final_time or "",
                "race_name": signal_row.get("race") or memory.get("race_name") or tipster.get("race_name") or "",
                "market_id": final_market or "",
                "horse_name": clean_text(horse),
                "horse_key": horse_key,
                "selection_type": selection_type,
                "signal_score": signal_score,
                "pre_race_price": safe_float(memory.get("pre_race_price")) or safe_float(signal_row.get("odds")),
                "bsp": safe_float(memory.get("bsp")),
                "field_size": safe_int(memory.get("field_size") or signal_row.get("runners")),
                "jockey": clean_text(signal_row.get("jockey") or memory.get("jockey")),
                "trainer": clean_text(signal_row.get("trainer") or memory.get("trainer")),
                "form": clean_text(signal_row.get("form") or memory.get("form")),
                "result": result,
                "position": position,
                "won": won,
                "placed": placed,
                "full_result_position": safe_int(result_note.get("position")),
                "distance_from_previous_lengths": safe_float(result_note.get("distance_from_previous_lengths")),
                "cumulative_beaten_lengths": safe_float(result_note.get("cumulative_beaten_lengths")),
                "distance_from_winner_lengths": safe_float(result_note.get("distance_from_winner_lengths")),
                "beaten_margin_lengths": safe_float(result_note.get("beaten_margin_lengths")),
                "winning_margin_lengths": safe_float(result_note.get("winning_margin_lengths")),
                "distance_summary": clean_text(result_note.get("distance_summary")),
                "finish_impression": clean_text(result_note.get("finish_impression")),
                "race_comment": clean_text(result_note.get("race_comment")),
                "winner_impression": clean_text(result_note.get("winner_impression")),
                "winner_won_decisively": bool(result_note.get("winner_won_decisively")),
                "beaten_by": result_note.get("beaten_by") if isinstance(result_note.get("beaten_by"), list) else [],
                "beat_high_signal_horses": result_note.get("beat_high_signal_horses") if isinstance(result_note.get("beat_high_signal_horses"), list) else [],
                "result_note_flags": result_note.get("result_note_flags") if isinstance(result_note.get("result_note_flags"), list) else [],
                "jockey_claim_lbs": safe_int(result_note.get("jockey_claim_lbs")),
                "carried_weight_lbs": safe_int(result_note.get("carried_weight_lbs")),
                "official_rating_result_note": safe_int(result_note.get("official_rating")),
                "tipster_count_live": safe_int(memory.get("tipster_count") or signal_row.get("tipsters")) or 0,
                "tipster_mentions_paste": safe_int(tipster.get("mention_count")) or 0,
                "explicit_tip_count": safe_int(tipster.get("explicit_tip_count")) or 0,
                "consensus_label": tipster.get("consensus_label") or "",
                "tipster_confidence_score": safe_int(tipster.get("confidence_score")),
                "tipster_market_confidence": tipster.get("market_confidence") or "",
                "tipster_value_flag": bool(tipster.get("value_flag")),
                "tipster_danger_flag": bool(tipster.get("danger_flag")),
                "tipster_ai_view": tipster.get("ai_view") or "",
                "tipster_sources": tipster.get("sources") if isinstance(tipster.get("sources"), list) else [],
                "grandad_memory_tags": memory_tags,
                "grandad_book_insight": memory.get("book_insight") or "",
                "head_to_head_wins_today": len(h2h_win_items),
                "head_to_head_losses_today": len(h2h_loss_items),
                "historic_rival_positive_count": len(historic_positive_items),
                "historic_rival_negative_count": len(historic_negative_items),
                "historic_rival_notes": [
                    clean_text(x.get("evidence_note"))
                    for x in (historic_positive_items + historic_negative_items)[:8]
                    if x.get("evidence_note")
                ],
                "head_to_head_notes": [
                    clean_text(x.get("evidence_note"))
                    for x in (h2h_win_items + h2h_loss_items)[:8]
                    if x.get("evidence_note")
                ],
                "combined_view": view,
                "learning_questions": learning_questions(
                    view,
                    tip_count,
                    len(h2h_loss_items),
                    len(historic_negative_items),
                    len(historic_positive_items),
                ),
                "source_files": {
                    "daily": source_path(daily_file),
                    "race_memory": source_path(memory_file),
                    "head_to_head": source_path(h2h_file),
                    "historic_rivals": source_path(rivals_file),
                    "tipster_intelligence": source_path(tipster_file),
                    "race_result_notes": source_path(result_notes_file),
                },
            }
        )

    type_counts = Counter(row["selection_type"] for row in combined_rows)
    view_counts = Counter(row["combined_view"] for row in combined_rows)
    summary = {
        "runner_count": len(combined_rows),
        "official_count": type_counts.get("OFFICIAL", 0),
        "watchlist_count": type_counts.get("WATCHLIST", 0),
        "tipster_only_count": type_counts.get("TIPSTER_ONLY", 0),
        "runner_only_count": type_counts.get("RUNNER", 0),
        "with_tipster_intelligence": sum(1 for row in combined_rows if row["tipster_mentions_paste"] or row["explicit_tip_count"]),
        "with_grandad_memory": sum(1 for row in combined_rows if row["grandad_memory_tags"] or row["grandad_book_insight"]),
        "with_head_to_head_today": sum(1 for row in combined_rows if row["head_to_head_wins_today"] or row["head_to_head_losses_today"]),
        "with_historic_rivals": sum(1 for row in combined_rows if row["historic_rival_positive_count"] or row["historic_rival_negative_count"]),
        "with_result_notes": sum(1 for row in combined_rows if row["result_note_flags"] or row["race_comment"]),
        "with_margin_notes": sum(1 for row in combined_rows if row["winning_margin_lengths"] is not None or row["distance_from_winner_lengths"] is not None),
        "beat_high_signal_horse_count": sum(1 for row in combined_rows if row["beat_high_signal_horses"]),
        "no_response_or_weakened_count": sum(1 for row in combined_rows if "WEAKENED_OR_NO_RESPONSE" in row["result_note_flags"]),
        "won_decisively_count": sum(1 for row in combined_rows if "WON_DECISIVELY" in row["result_note_flags"]),
        "won_clear_count": sum(1 for row in combined_rows if "WON_CLEAR" in row["result_note_flags"]),
        "well_beaten_count": sum(1 for row in combined_rows if "WELL_BEATEN" in row["result_note_flags"]),
        "heavily_beaten_count": sum(1 for row in combined_rows if "HEAVILY_BEATEN" in row["result_note_flags"]),
        "won_count": sum(row["won"] for row in combined_rows),
        "placed_count": sum(row["placed"] for row in combined_rows),
        "views": dict(sorted(view_counts.items())),
    }

    return {
        "version": "1.0",
        "date": date,
        "generatedAt": now_iso(),
        "mode": "combined_learning_only",
        "message": "Joined evidence layer only. No live picks, scoring, proof, results, unlock or automation changes.",
        "summary": summary,
        "records": combined_rows,
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS combined_learning (
            date TEXT NOT NULL,
            course TEXT,
            race_time TEXT,
            race_name TEXT,
            market_id TEXT,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            selection_type TEXT,
            signal_score REAL,
            pre_race_price REAL,
            bsp REAL,
            field_size INTEGER,
            result TEXT,
            position INTEGER,
            won INTEGER,
            placed INTEGER,
            tipster_count_live INTEGER,
            tipster_mentions_paste INTEGER,
            explicit_tip_count INTEGER,
            consensus_label TEXT,
            tipster_confidence_score INTEGER,
            tipster_market_confidence TEXT,
            tipster_value_flag INTEGER,
            tipster_danger_flag INTEGER,
            grandad_memory_count INTEGER,
            head_to_head_wins_today INTEGER,
            head_to_head_losses_today INTEGER,
            historic_rival_positive_count INTEGER,
            historic_rival_negative_count INTEGER,
            combined_view TEXT,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (date, market_id, course, race_time, horse_key)
        );

        CREATE INDEX IF NOT EXISTS idx_combined_learning_horse ON combined_learning (horse_key);
        CREATE INDEX IF NOT EXISTS idx_combined_learning_view ON combined_learning (combined_view);
        CREATE INDEX IF NOT EXISTS idx_combined_learning_date ON combined_learning (date);
        """
    )


def upsert_sqlite(db_path: Path, payload: Dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        for row in payload["records"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO combined_learning (
                    date, course, race_time, race_name, market_id, horse_name, horse_key,
                    selection_type, signal_score, pre_race_price, bsp, field_size, result,
                    position, won, placed, tipster_count_live, tipster_mentions_paste,
                    explicit_tip_count, consensus_label, tipster_confidence_score,
                    tipster_market_confidence, tipster_value_flag, tipster_danger_flag,
                    grandad_memory_count, head_to_head_wins_today, head_to_head_losses_today,
                    historic_rival_positive_count, historic_rival_negative_count,
                    combined_view, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["date"],
                    row["course"],
                    row["race_time"],
                    row["race_name"],
                    row["market_id"],
                    row["horse_name"],
                    row["horse_key"],
                    row["selection_type"],
                    row["signal_score"],
                    row["pre_race_price"],
                    row["bsp"],
                    row["field_size"],
                    row["result"],
                    row["position"],
                    row["won"],
                    row["placed"],
                    row["tipster_count_live"],
                    row["tipster_mentions_paste"],
                    row["explicit_tip_count"],
                    row["consensus_label"],
                    row["tipster_confidence_score"],
                    row["tipster_market_confidence"],
                    bool_int(row["tipster_value_flag"]),
                    bool_int(row["tipster_danger_flag"]),
                    len(row["grandad_memory_tags"]),
                    row["head_to_head_wins_today"],
                    row["head_to_head_losses_today"],
                    row["historic_rival_positive_count"],
                    row["historic_rival_negative_count"],
                    row["combined_view"],
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def write_csv_file(records: List[Dict[str, Any]], path: Path) -> None:
    fields = [
        "date",
        "course",
        "race_time",
        "horse_name",
        "selection_type",
        "signal_score",
        "pre_race_price",
        "bsp",
        "field_size",
        "result",
        "position",
        "won",
        "placed",
        "tipster_count_live",
        "tipster_mentions_paste",
        "explicit_tip_count",
        "consensus_label",
        "tipster_confidence_score",
        "tipster_market_confidence",
        "head_to_head_losses_today",
        "historic_rival_positive_count",
        "historic_rival_negative_count",
        "full_result_position",
        "cumulative_beaten_lengths",
        "distance_from_winner_lengths",
        "winning_margin_lengths",
        "finish_impression",
        "jockey_claim_lbs",
        "result_note_flags",
        "combined_view",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the joined Signal 75 learning layer.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--daily-file", type=Path)
    parser.add_argument("--race-memory-file", type=Path)
    parser.add_argument("--head-to-head-file", type=Path)
    parser.add_argument("--historic-rivals-file", type=Path)
    parser.add_argument("--tipster-file", type=Path)
    parser.add_argument("--race-result-notes-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()

    date = args.date
    daily_file = args.daily_file or DATA_DIR / f"{date}.json"
    race_memory_file = args.race_memory_file or HORSE_INTEL_DIR / f"race_memory_{date}.json"
    head_to_head_file = args.head_to_head_file or HORSE_INTEL_DIR / f"head_to_head_{date}.json"
    historic_rivals_file = args.historic_rivals_file or HORSE_INTEL_DIR / f"historic_rivals_{date}.json"
    tipster_file = args.tipster_file or TIPSTER_DIR / f"tipster_intelligence_{date}.json"
    result_notes_file = args.race_result_notes_file or HORSE_INTEL_DIR / f"race_result_notes_{date}.json"

    payload = build_combined(date, daily_file, race_memory_file, head_to_head_file, historic_rivals_file, tipster_file, result_notes_file)

    output_dir = args.output_dir
    output_file = output_dir / f"combined_learning_{date}.json"
    write_json(output_file, payload)
    if args.csv:
        write_csv_file(payload["records"], output_file.with_suffix(".csv"))
    upsert_sqlite(args.db, payload)

    summary = payload["summary"]
    print(f"Saved: {output_file}")
    print(f"Rows: {summary['runner_count']} | official: {summary['official_count']} | watchlist: {summary['watchlist_count']} | tipster-only: {summary['tipster_only_count']} | runner-only: {summary['runner_only_count']}")
    print(f"Tipster evidence: {summary['with_tipster_intelligence']} | Grandad memory: {summary['with_grandad_memory']} | historic rivals: {summary['with_historic_rivals']} | result notes: {summary['with_result_notes']}")
    print(f"Database: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
