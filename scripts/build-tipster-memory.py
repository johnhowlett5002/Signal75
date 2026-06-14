#!/usr/bin/env python3
"""Build automated tipster memory from the daily consensus overlay.

This is a storage/learning layer only. It does not change live scoring,
picks, proof, settlement, results maths, unlock logic, or public JSON shapes.
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


REPO = Path("/Users/johnhowlett/Signal75")
DATA = REPO / "data"
TIPSTER_DIR = DATA / "tipster_intelligence"
DEFAULT_DB = DATA / "combined_learning" / "signal75_learning.sqlite"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalise(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def source_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def result_flags(row: Dict[str, Any]) -> Tuple[str, Optional[int], int, int]:
    result = clean_text(row.get("result") or row.get("radarResult") or row.get("status"))
    position = safe_int(row.get("position") or row.get("finishing_position"), 0) or None
    upper = result.upper()
    won = 1 if position == 1 or "WON" in upper else 0
    placed = 1 if won or "PLACED" in upper else 0
    if position and not placed:
        field = safe_int(row.get("runners") or row.get("field_size"), 0)
        place_cutoff = 2 if field and field < 8 else 3
        placed = 1 if position <= place_cutoff else 0
    return result, position, won, placed


def iter_daily_horses(daily: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for bucket, selection_type in (
        ("flat", "OFFICIAL"),
        ("jumps", "OFFICIAL"),
        ("topRated", "WATCHLIST"),
        ("topRatedFlat", "WATCHLIST"),
        ("topRatedJumps", "WATCHLIST"),
    ):
        for item in daily.get(bucket, []) or []:
            if "horses" in item:
                for horse in item.get("horses") or []:
                    row = dict(horse)
                    row.setdefault("course", item.get("course") or item.get("venue"))
                    row.setdefault("venue", item.get("venue") or item.get("course"))
                    row.setdefault("time", item.get("time"))
                    row.setdefault("race", item.get("race") or item.get("name"))
                    row["_selection_type"] = selection_type
                    yield row
            else:
                row = dict(item)
                row["_selection_type"] = selection_type
                yield row


def daily_index(daily: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for row in iter_daily_horses(daily):
        horse = row.get("name") or row.get("horse_name") or row.get("horse")
        course = row.get("venue") or row.get("course")
        race_time = row.get("time") or row.get("race_time")
        index[(normalise(horse), clean_text(course).upper(), clean_text(race_time))] = row
        index[(normalise(horse), "", "")] = row
    return index


def consensus_label(count: int) -> str:
    if count >= 10:
        return "Elite Consensus"
    if count >= 7:
        return "Strong Consensus"
    if count >= 4:
        return "Moderate Consensus"
    if count >= 1:
        return "Weak Consensus"
    return "No Consensus"


def tip_key(record: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        record.get("date", ""),
        record.get("market_id", ""),
        clean_text(record.get("course")).upper(),
        clean_text(record.get("race_time")),
        normalise(record.get("horse_name")),
    )


def merge_existing_records(path: Path, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    existing = load_json(path, {})
    merged: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for row in existing.get("records", []) if isinstance(existing, dict) else []:
        merged[tip_key(row)] = row
    for row in records:
        merged[tip_key(row)] = row
    return sorted(
        merged.values(),
        key=lambda r: (r.get("race_time") or "", r.get("course") or "", -safe_int(r.get("mention_count"), 0), r.get("horse_name") or ""),
    )


def build_memory(date: str, overlay_file: Path, daily_file: Path, output_file: Path) -> Dict[str, Any]:
    overlay = load_json(overlay_file, {})
    daily = load_json(daily_file, {})
    daily_rows = daily_index(daily)
    records: List[Dict[str, Any]] = []
    source_records: List[Dict[str, Any]] = []

    for item in overlay.get("matched_to_betfair", []) or []:
        horse = item.get("betfair_name") or item.get("horse")
        course = item.get("course")
        race_time = item.get("time")
        daily_row = (
            daily_rows.get((normalise(horse), clean_text(course).upper(), clean_text(race_time)))
            or daily_rows.get((normalise(horse), "", ""))
            or {}
        )
        result, position, won, placed = result_flags(daily_row)
        sources = item.get("sources") if isinstance(item.get("sources"), list) else []
        tipsters = item.get("tipsters") if isinstance(item.get("tipsters"), list) else []
        explicit_count = max(
            safe_int(item.get("tip_count"), 0),
            safe_int(item.get("consensus_count"), 0),
            len(tipsters),
            len(sources),
        )
        record = {
            "date": date,
            "course": course or "",
            "race_time": race_time or "",
            "race_name": daily_row.get("race") or daily_row.get("race_name") or "",
            "market_id": daily_row.get("market_id") or item.get("market_id") or "",
            "horse_name": horse or "",
            "horse_key": normalise(horse),
            "mention_count": explicit_count,
            "explicit_tip_count": explicit_count,
            "positive_score": 0,
            "negative_score": 0,
            "confidence_score": safe_int(round((safe_float(item.get("weighted_consensus_score")) or 0) * 12), 0),
            "consensus_label": consensus_label(explicit_count),
            "consensus_level": item.get("consensus_level") or item.get("support_level") or "",
            "support_level": item.get("support_level") or "",
            "weighted_consensus_score": safe_float(item.get("weighted_consensus_score")) or 0,
            "overlay_points": safe_int(item.get("overlay_points"), 0),
            "value_flag": False,
            "danger_flag": bool(item.get("stronger_tipped_horse_than_this")),
            "market_confidence": "Neutral",
            "source_count": safe_int(item.get("source_count"), len(sources)),
            "sources": sources,
            "source_tiers": item.get("source_tiers") if isinstance(item.get("source_tiers"), dict) else {},
            "tipsters": tipsters,
            "tip_evidence": item.get("tip_evidence") if isinstance(item.get("tip_evidence"), list) else [],
            "signal_score": safe_float(daily_row.get("signal_score") or daily_row.get("score")),
            "odds": safe_float(daily_row.get("odds") or daily_row.get("bsp")),
            "selection_type": daily_row.get("_selection_type") or "TIPSTER_ONLY",
            "ai_view": "Consensus Leader" if explicit_count >= 4 else "Tipster Evidence",
            "best_tipped_horse_in_race": item.get("best_tipped_horse_in_race") or "",
            "stronger_tipped_horse_than_this": bool(item.get("stronger_tipped_horse_than_this")),
            "stronger_tipped_horse_name": item.get("stronger_tipped_horse_name") or "",
            "result": result,
            "position": position,
            "won": won,
            "placed": placed,
            "collection_method": "automated_consensus_overlay",
            "source_file": source_path(overlay_file),
        }
        records.append(record)

        evidence_rows = item.get("tip_evidence") if isinstance(item.get("tip_evidence"), list) else []
        if not evidence_rows:
            evidence_rows = [{"sources": sources, "tipsters": tipsters, "notes": []}]
        for evidence in evidence_rows:
            ev_sources = evidence.get("sources") if isinstance(evidence.get("sources"), list) else sources
            ev_tipsters = evidence.get("tipsters") if isinstance(evidence.get("tipsters"), list) else tipsters
            if not ev_tipsters:
                ev_tipsters = [""]
            for source in ev_sources or [""]:
                for tipster in ev_tipsters:
                    source_records.append({
                        "date": date,
                        "course": course or "",
                        "race_time": race_time or "",
                        "market_id": record["market_id"],
                        "horse_name": horse or "",
                        "horse_key": normalise(horse),
                        "source": source,
                        "tipster": tipster,
                        "tip_type": evidence.get("tip_type") or "",
                        "is_nap": bool(evidence.get("is_nap")),
                        "is_nb": bool(evidence.get("is_nb")),
                        "weighted_add": safe_float(evidence.get("weighted_add")) or 0,
                        "notes": evidence.get("notes") if isinstance(evidence.get("notes"), list) else [],
                        "selection_type": record["selection_type"],
                        "signal_score": record["signal_score"],
                        "odds": record["odds"],
                        "result": result,
                        "position": position,
                        "won": won,
                        "placed": placed,
                    })

    records = merge_existing_records(output_file, records)
    summary = {
        "horse_count": len(records),
        "source_record_count": len(source_records),
        "sources": dict(sorted(Counter(s for row in records for s in row.get("sources", [])).items())),
        "with_results": sum(1 for row in records if row.get("result") or row.get("position")),
        "won_count": sum(safe_int(row.get("won"), 0) for row in records),
        "placed_count": sum(safe_int(row.get("placed"), 0) for row in records),
    }
    return {
        "version": "1.0",
        "date": date,
        "generatedAt": now_iso(),
        "mode": "automated_tipster_memory",
        "message": "Tipster evidence memory only. No scoring, picks, proof, results, unlock or public JSON changes.",
        "summary": summary,
        "records": records,
        "source_records": source_records,
        "source_files": {
            "consensus_overlay": source_path(overlay_file),
            "daily_results": source_path(daily_file) if daily_file.exists() else "",
        },
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        CREATE TABLE IF NOT EXISTS tipster_memory (
            date TEXT NOT NULL,
            course TEXT,
            race_time TEXT,
            race_name TEXT,
            market_id TEXT,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            mention_count INTEGER,
            explicit_tip_count INTEGER,
            source_count INTEGER,
            consensus_label TEXT,
            consensus_level TEXT,
            weighted_consensus_score REAL,
            overlay_points INTEGER,
            signal_score REAL,
            odds REAL,
            selection_type TEXT,
            result TEXT,
            position INTEGER,
            won INTEGER,
            placed INTEGER,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (date, market_id, course, race_time, horse_key)
        );

        CREATE TABLE IF NOT EXISTS tipster_source_memory (
            date TEXT NOT NULL,
            course TEXT,
            race_time TEXT,
            market_id TEXT,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            source TEXT,
            tipster TEXT,
            tip_type TEXT,
            is_nap INTEGER,
            is_nb INTEGER,
            weighted_add REAL,
            signal_score REAL,
            odds REAL,
            selection_type TEXT,
            result TEXT,
            position INTEGER,
            won INTEGER,
            placed INTEGER,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (date, market_id, course, race_time, horse_key, source, tipster, tip_type)
        );

        CREATE TABLE IF NOT EXISTS tipster_source_summary (
            source TEXT NOT NULL,
            tipster TEXT NOT NULL,
            selections INTEGER,
            resulted INTEGER,
            wins INTEGER,
            places INTEGER,
            win_rate REAL,
            place_rate REAL,
            avg_weighted_add REAL,
            last_seen TEXT,
            PRIMARY KEY (source, tipster)
        );

        CREATE INDEX IF NOT EXISTS idx_tipster_memory_horse ON tipster_memory (horse_key);
        CREATE INDEX IF NOT EXISTS idx_tipster_memory_date ON tipster_memory (date);
        CREATE INDEX IF NOT EXISTS idx_tipster_source_source ON tipster_source_memory (source, tipster);
        CREATE INDEX IF NOT EXISTS idx_tipster_source_horse ON tipster_source_memory (horse_key);
        """
    )


def upsert_sqlite(db_path: Path, payload: Dict[str, Any]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        for row in payload.get("records", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO tipster_memory (
                    date, course, race_time, race_name, market_id, horse_name, horse_key,
                    mention_count, explicit_tip_count, source_count, consensus_label,
                    consensus_level, weighted_consensus_score, overlay_points, signal_score,
                    odds, selection_type, result, position, won, placed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("date"), row.get("course"), row.get("race_time"), row.get("race_name"),
                    row.get("market_id"), row.get("horse_name"), row.get("horse_key"),
                    safe_int(row.get("mention_count"), 0), safe_int(row.get("explicit_tip_count"), 0),
                    safe_int(row.get("source_count"), 0), row.get("consensus_label"),
                    row.get("consensus_level"), safe_float(row.get("weighted_consensus_score")),
                    safe_int(row.get("overlay_points"), 0), safe_float(row.get("signal_score")),
                    safe_float(row.get("odds")), row.get("selection_type"), row.get("result"),
                    row.get("position"), safe_int(row.get("won"), 0), safe_int(row.get("placed"), 0),
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                ),
            )
        for row in payload.get("source_records", []):
            conn.execute(
                """
                INSERT OR REPLACE INTO tipster_source_memory (
                    date, course, race_time, market_id, horse_name, horse_key, source, tipster,
                    tip_type, is_nap, is_nb, weighted_add, signal_score, odds, selection_type,
                    result, position, won, placed, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("date"), row.get("course"), row.get("race_time"), row.get("market_id"),
                    row.get("horse_name"), row.get("horse_key"), row.get("source") or "",
                    row.get("tipster") or "", row.get("tip_type") or "", 1 if row.get("is_nap") else 0,
                    1 if row.get("is_nb") else 0, safe_float(row.get("weighted_add")),
                    safe_float(row.get("signal_score")), safe_float(row.get("odds")),
                    row.get("selection_type"), row.get("result"), row.get("position"),
                    safe_int(row.get("won"), 0), safe_int(row.get("placed"), 0),
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                ),
            )
        conn.execute("DELETE FROM tipster_source_summary")
        conn.execute(
            """
            INSERT INTO tipster_source_summary (
                source, tipster, selections, resulted, wins, places, win_rate, place_rate,
                avg_weighted_add, last_seen
            )
            SELECT
                source,
                tipster,
                COUNT(*) AS selections,
                SUM(CASE WHEN result IS NOT NULL AND result != '' OR position IS NOT NULL THEN 1 ELSE 0 END) AS resulted,
                SUM(COALESCE(won, 0)) AS wins,
                SUM(COALESCE(placed, 0)) AS places,
                CASE WHEN SUM(CASE WHEN result IS NOT NULL AND result != '' OR position IS NOT NULL THEN 1 ELSE 0 END) > 0
                    THEN ROUND(1.0 * SUM(COALESCE(won, 0)) / SUM(CASE WHEN result IS NOT NULL AND result != '' OR position IS NOT NULL THEN 1 ELSE 0 END), 4)
                    ELSE NULL END AS win_rate,
                CASE WHEN SUM(CASE WHEN result IS NOT NULL AND result != '' OR position IS NOT NULL THEN 1 ELSE 0 END) > 0
                    THEN ROUND(1.0 * SUM(COALESCE(placed, 0)) / SUM(CASE WHEN result IS NOT NULL AND result != '' OR position IS NOT NULL THEN 1 ELSE 0 END), 4)
                    ELSE NULL END AS place_rate,
                ROUND(AVG(COALESCE(weighted_add, 0)), 4) AS avg_weighted_add,
                MAX(date) AS last_seen
            FROM tipster_source_memory
            GROUP BY source, tipster
            """
        )
        conn.commit()
    finally:
        conn.close()


def write_csv_file(records: List[Dict[str, Any]], path: Path) -> None:
    fields = [
        "date", "course", "race_time", "horse_name", "mention_count",
        "explicit_tip_count", "source_count", "consensus_label", "consensus_level",
        "weighted_consensus_score", "overlay_points", "signal_score", "odds",
        "selection_type", "result", "position", "won", "placed", "sources", "tipsters",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description="Build automated tipster memory from consensus overlay.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--overlay-file", type=Path)
    parser.add_argument("--daily-file", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()

    overlay_file = args.overlay_file or DATA / f"consensus_overlay_{args.date}.json"
    daily_file = args.daily_file or DATA / f"{args.date}.json"
    if not daily_file.exists() and (REPO / "picks.json").exists():
        daily_file = REPO / "picks.json"
    output = args.output or TIPSTER_DIR / f"tipster_intelligence_{args.date}.json"

    payload = build_memory(args.date, overlay_file, daily_file, output)
    write_json(output, payload)
    if args.csv:
        write_csv_file(payload.get("records", []), output.with_suffix(".csv"))
    upsert_sqlite(args.db, payload)

    summary = payload["summary"]
    print(f"Saved: {output}")
    print(f"Tipster horses: {summary['horse_count']} | source rows: {summary['source_record_count']} | with results: {summary['with_results']}")
    print(f"Database: {args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
