#!/usr/bin/env python3
"""Build the local Signal 75 intelligence SQLite database.

This is analysis/storage only. It does not change scoring, picks, proof,
settlement, results maths, app data, unlock logic, or public JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
DEFAULT_DB = INTEL_DIR / "signal75_history.sqlite"
ENGINE_CSV_CANDIDATES = [
    Path("/Users/johnhowlett/Signal75-Work/Signal75-Engine/betfair_uk_races_master.csv"),
    Path("/Users/johnhowlett/Desktop/Signal75-Engine/betfair_uk_races_master.csv"),
    REPO_ROOT / "engine" / "betfair_uk_races_full_v2.csv",
]
DEFAULT_ENGINE_CSV = next((path for path in ENGINE_CSV_CANDIDATES if path.exists()), ENGINE_CSV_CANDIDATES[-1])

JSONL_FILES = {
    "race_memory": INTEL_DIR / "race_memory_master.jsonl",
    "head_to_head": INTEL_DIR / "head_to_head_master.jsonl",
    "historic_rivals": INTEL_DIR / "historic_rival_master.jsonl",
    "horse_history": INTEL_DIR / "horse_history_master.jsonl",
}

PROFILE_FILES = {
    "horse_memory": INTEL_DIR / "horse_memory_profiles.json",
    "head_to_head": INTEL_DIR / "head_to_head_profiles.json",
    "historic_rival": INTEL_DIR / "historic_rival_profiles.json",
    "horse_profile": INTEL_DIR / "horse_profiles.json",
}


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def parse_date(value: Any) -> Optional[str]:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else None


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


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;

        DROP TABLE IF EXISTS meta;
        DROP TABLE IF EXISTS historical_runners;
        DROP TABLE IF EXISTS race_memory;
        DROP TABLE IF EXISTS head_to_head;
        DROP TABLE IF EXISTS historic_rivals;
        DROP TABLE IF EXISTS horse_history;
        DROP TABLE IF EXISTS profiles;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE historical_runners (
            market_id TEXT NOT NULL,
            market_type TEXT,
            betfair_runner_id TEXT,
            horse_name TEXT,
            horse_key TEXT NOT NULL,
            cloth_number TEXT,
            bsp REAL,
            status TEXT,
            sort_priority INTEGER,
            venue TEXT,
            race_time TEXT,
            race_date TEXT,
            race_name TEXT,
            race_type TEXT,
            race_subtype TEXT,
            distance_furlongs REAL,
            runner_count INTEGER
        );

        CREATE TABLE race_memory (
            id TEXT PRIMARY KEY,
            date TEXT,
            market_id TEXT,
            horse_name TEXT,
            horse_key TEXT,
            course TEXT,
            race_time TEXT,
            race_name TEXT,
            known_result TEXT,
            finishing_position INTEGER,
            betfair_status TEXT,
            pre_race_price REAL,
            signal_score REAL,
            official_pick INTEGER,
            watchlist INTEGER,
            tipster_count INTEGER,
            jockey TEXT,
            trainer TEXT,
            form TEXT,
            days_since_run INTEGER,
            field_size INTEGER,
            race_class_label TEXT,
            race_class_level INTEGER,
            previous_race_class_label TEXT,
            previous_race_class_level INTEGER,
            class_movement TEXT,
            class_movement_steps INTEGER,
            recent_stronger_races_count INTEGER,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE head_to_head (
            id TEXT PRIMARY KEY,
            date TEXT,
            market_id TEXT,
            winner TEXT,
            winner_key TEXT,
            loser TEXT,
            loser_key TEXT,
            course TEXT,
            race_time TEXT,
            race_name TEXT,
            source TEXT,
            confidence TEXT,
            evidence_note TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE historic_rivals (
            id TEXT PRIMARY KEY,
            target_date TEXT,
            target_market_id TEXT,
            target_course TEXT,
            target_race_time TEXT,
            target_race_name TEXT,
            historic_date TEXT,
            historic_market_id TEXT,
            historic_course TEXT,
            historic_race_type TEXT,
            historic_distance_furlongs REAL,
            winner TEXT,
            winner_key TEXT,
            loser TEXT,
            loser_key TEXT,
            evidence_note TEXT,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE horse_history (
            id TEXT PRIMARY KEY,
            date TEXT,
            market_id TEXT,
            horse_name TEXT,
            horse_key TEXT,
            course TEXT,
            race_time TEXT,
            race_name TEXT,
            result TEXT,
            finishing_position INTEGER,
            signal_score REAL,
            official_pick INTEGER,
            watchlist INTEGER,
            payload_json TEXT NOT NULL
        );

        CREATE TABLE profiles (
            profile_type TEXT NOT NULL,
            profile_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (profile_type, profile_key)
        );
        """
    )


def insert_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, str(value)))


def import_engine_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    if not csv_path.exists():
        raise SystemExit(f"Historical CSV not found: {csv_path}")

    rows = 0
    batch = []
    with csv_path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            horse_name = clean_text(row.get("horse_name"))
            horse_key = norm_name(horse_name)
            if not horse_key:
                continue
            batch.append(
                (
                    row.get("market_id"),
                    row.get("market_type"),
                    row.get("betfair_runner_id"),
                    horse_name,
                    horse_key,
                    row.get("cloth_number"),
                    safe_float(row.get("bsp")),
                    row.get("status"),
                    safe_int(row.get("sort_priority")),
                    row.get("venue"),
                    row.get("race_time"),
                    parse_date(row.get("race_time")),
                    row.get("race_name"),
                    row.get("race_type"),
                    row.get("race_subtype"),
                    safe_float(row.get("distance_furlongs")),
                    safe_int(row.get("runner_count")),
                )
            )
            if len(batch) >= 10000:
                conn.executemany(
                    """
                    INSERT INTO historical_runners VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                rows += len(batch)
                batch.clear()
        if batch:
            conn.executemany(
                """
                INSERT INTO historical_runners VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
            rows += len(batch)
    insert_meta(conn, "engine_csv", csv_path)
    insert_meta(conn, "historical_runners", rows)
    return rows


def import_race_memory(conn: sqlite3.Connection, path: Path) -> int:
    count = 0
    for record in iter_jsonl(path):
        conn.execute(
            """
            INSERT OR REPLACE INTO race_memory VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id") or "|".join([str(record.get("date")), str(record.get("market_id")), norm_name(record.get("horse_name"))]),
                record.get("date"),
                record.get("market_id"),
                record.get("horse_name"),
                record.get("normalised_name") or norm_name(record.get("horse_name")),
                record.get("course"),
                record.get("race_time"),
                record.get("race_name"),
                record.get("known_result"),
                safe_int(record.get("finishing_position")),
                record.get("betfair_status"),
                safe_float(record.get("pre_race_price")),
                safe_float(record.get("signal_score")),
                1 if record.get("official_pick") else 0,
                1 if record.get("watchlist") else 0,
                safe_int(record.get("tipster_count")),
                record.get("jockey"),
                record.get("trainer"),
                record.get("form"),
                safe_int(record.get("days_since_run")),
                safe_int(record.get("field_size")),
                record.get("race_class_label"),
                safe_int(record.get("race_class_level")),
                record.get("previous_race_class_label"),
                safe_int(record.get("previous_race_class_level")),
                record.get("class_movement"),
                safe_int(record.get("class_movement_steps")),
                safe_int(record.get("recent_stronger_races_count")),
                json_text(record),
            ),
        )
        count += 1
    insert_meta(conn, "race_memory_records", count)
    return count


def import_head_to_head(conn: sqlite3.Connection, path: Path) -> int:
    count = 0
    for record in iter_jsonl(path):
        conn.execute(
            """
            INSERT OR REPLACE INTO head_to_head VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id"),
                record.get("date"),
                record.get("market_id"),
                record.get("winner"),
                record.get("winner_key") or norm_name(record.get("winner")),
                record.get("loser"),
                record.get("loser_key") or norm_name(record.get("loser")),
                record.get("course"),
                record.get("race_time"),
                record.get("race_name"),
                record.get("source"),
                record.get("confidence"),
                record.get("evidence_note"),
                json_text(record),
            ),
        )
        count += 1
    insert_meta(conn, "head_to_head_records", count)
    return count


def import_historic_rivals(conn: sqlite3.Connection, path: Path) -> int:
    count = 0
    for record in iter_jsonl(path):
        conn.execute(
            """
            INSERT OR REPLACE INTO historic_rivals VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id"),
                record.get("target_date"),
                record.get("target_market_id"),
                record.get("target_course"),
                record.get("target_race_time"),
                record.get("target_race_name"),
                record.get("historic_date"),
                record.get("historic_market_id"),
                record.get("historic_course"),
                record.get("historic_race_type"),
                safe_float(record.get("historic_distance_furlongs")),
                record.get("winner"),
                record.get("winner_key") or norm_name(record.get("winner")),
                record.get("loser"),
                record.get("loser_key") or norm_name(record.get("loser")),
                record.get("evidence_note"),
                json_text(record),
            ),
        )
        count += 1
    insert_meta(conn, "historic_rival_records", count)
    return count


def import_horse_history(conn: sqlite3.Connection, path: Path) -> int:
    count = 0
    for record in iter_jsonl(path):
        conn.execute(
            """
            INSERT OR REPLACE INTO horse_history VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("id") or "|".join([str(record.get("date")), str(record.get("market_id")), norm_name(record.get("horse_name"))]),
                record.get("date"),
                record.get("market_id"),
                record.get("horse_name"),
                record.get("normalised_name") or norm_name(record.get("horse_name")),
                record.get("course"),
                record.get("race_time"),
                record.get("race_name"),
                record.get("known_result") or record.get("result"),
                safe_int(record.get("finishing_position")),
                safe_float(record.get("signal_score")),
                1 if record.get("official_pick") else 0,
                1 if record.get("watchlist") else 0,
                json_text(record),
            ),
        )
        count += 1
    insert_meta(conn, "horse_history_records", count)
    return count


def import_profiles(conn: sqlite3.Connection, files: Dict[str, Path]) -> int:
    count = 0
    for profile_type, path in files.items():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items = payload.items()
        elif isinstance(payload, list):
            items = ((str(idx), value) for idx, value in enumerate(payload))
        else:
            continue
        for key, value in items:
            conn.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?, ?, ?)",
                (profile_type, str(key), json_text(value)),
            )
            count += 1
    insert_meta(conn, "profile_records", count)
    return count


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_hist_horse ON historical_runners (horse_key);
        CREATE INDEX idx_hist_market ON historical_runners (market_id);
        CREATE INDEX idx_hist_date ON historical_runners (race_date);
        CREATE INDEX idx_hist_course ON historical_runners (venue);
        CREATE INDEX idx_hist_horse_date ON historical_runners (horse_key, race_date);

        CREATE INDEX idx_race_memory_horse ON race_memory (horse_key);
        CREATE INDEX idx_race_memory_date ON race_memory (date);
        CREATE INDEX idx_race_memory_market ON race_memory (market_id);
        CREATE INDEX idx_race_memory_class ON race_memory (race_class_level, class_movement);

        CREATE INDEX idx_h2h_winner ON head_to_head (winner_key);
        CREATE INDEX idx_h2h_loser ON head_to_head (loser_key);
        CREATE INDEX idx_h2h_date ON head_to_head (date);

        CREATE INDEX idx_rivals_target ON historic_rivals (target_date, target_market_id);
        CREATE INDEX idx_rivals_winner ON historic_rivals (winner_key);
        CREATE INDEX idx_rivals_loser ON historic_rivals (loser_key);

        CREATE INDEX idx_horse_history_horse ON horse_history (horse_key);
        CREATE INDEX idx_horse_history_date ON horse_history (date);
        """
    )


def build_database(db_path: Path, engine_csv: Path) -> Dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    conn = sqlite3.connect(str(db_path))
    try:
        create_schema(conn)
        counts = {
            "historical_runners": import_engine_csv(conn, engine_csv),
            "race_memory": import_race_memory(conn, JSONL_FILES["race_memory"]),
            "head_to_head": import_head_to_head(conn, JSONL_FILES["head_to_head"]),
            "historic_rivals": import_historic_rivals(conn, JSONL_FILES["historic_rivals"]),
            "horse_history": import_horse_history(conn, JSONL_FILES["horse_history"]),
            "profiles": import_profiles(conn, PROFILE_FILES),
        }
        insert_meta(conn, "built_at", datetime.now(timezone.utc).isoformat())
        create_indexes(conn)
        conn.commit()
        conn.execute("VACUUM")
        return counts
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Signal 75 local intelligence SQLite database.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Output SQLite database path")
    parser.add_argument("--engine-csv", default=str(DEFAULT_ENGINE_CSV), help="Historical Betfair CSV path")
    args = parser.parse_args()

    db_path = Path(args.db)
    engine_csv = Path(args.engine_csv)
    counts = build_database(db_path, engine_csv)

    print(f"Signal 75 intelligence database built: {db_path}")
    for key, value in counts.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
