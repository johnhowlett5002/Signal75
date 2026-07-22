#!/usr/bin/env python3
"""Import external race-form archive data into a separate research database.

This is analysis/storage only. It does not change live scoring, picks,
proof, settlement, public results, app data, or the existing Signal 75
head-to-head database.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = REPO_ROOT / "data" / "horse_intelligence"
DEFAULT_ARCHIVE = Path.home() / "Downloads" / "archive (1)"
DEFAULT_DB = INTEL_DIR / "form_history.sqlite"
DEFAULT_STATUS = INTEL_DIR / "form_history_status.json"
DEFAULT_SINCE = "2014-07-21"
BATCH_SIZE = 20000


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


def parse_date(value: Any) -> Optional[str]:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else None


def parse_fractional_odds(value: Any) -> Optional[float]:
    text = str(value or "").strip().upper()
    if not text or text in {"-", "–"}:
        return None
    text = re.sub(r"[A-Z]+$", "", text).strip()
    if "/" in text:
        left, right = text.split("/", 1)
        try:
            return round(float(left) / float(right) + 1, 4)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return safe_float(text)


def weight_to_lbs(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    match = re.match(r"^(\d+)-(\d+)$", text)
    if match:
        return int(match.group(1)) * 14 + int(match.group(2))
    return safe_int(text)


def output_sidecars(db_path: Path) -> Iterable[Path]:
    yield Path(str(db_path) + "-wal")
    yield Path(str(db_path) + "-shm")


def remove_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    for sidecar in output_sidecars(path):
        if sidecar.exists():
            sidecar.unlink()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=NORMAL;
        PRAGMA temp_store=MEMORY;

        CREATE TABLE meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE form_results (
            date TEXT NOT NULL,
            course TEXT,
            race_id INTEGER NOT NULL,
            off_time TEXT,
            race_name TEXT,
            race_type TEXT,
            race_class TEXT,
            pattern TEXT,
            rating_band TEXT,
            age_band TEXT,
            sex_restriction TEXT,
            distance TEXT,
            going TEXT,
            runners INTEGER,
            runner_number INTEGER,
            position INTEGER,
            draw INTEGER,
            distance_from_winner REAL,
            beaten_by REAL,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            age INTEGER,
            sex TEXT,
            weight TEXT,
            weight_lbs INTEGER,
            headgear TEXT,
            winning_time TEXT,
            sp TEXT,
            sp_decimal REAL,
            jockey TEXT,
            trainer TEXT,
            prize REAL,
            official_rating INTEGER,
            rpr INTEGER,
            topspeed INTEGER,
            sire TEXT,
            dam TEXT,
            damsire TEXT,
            owner TEXT,
            race_comment TEXT,
            source_archive TEXT NOT NULL,
            PRIMARY KEY (date, race_id, horse_key)
        );

        CREATE TABLE racecards (
            date TEXT NOT NULL,
            region TEXT,
            course TEXT,
            going TEXT,
            off_time TEXT,
            distance TEXT,
            race_name TEXT,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            field_size INTEGER,
            draw INTEGER,
            age INTEGER,
            weight_lbs INTEGER,
            form TEXT,
            jockey TEXT,
            owner TEXT,
            race_class TEXT,
            rpr INTEGER,
            sex TEXT,
            sire TEXT,
            dam TEXT,
            spotlight TEXT,
            comment TEXT,
            trainer TEXT,
            trainer_14_days_json TEXT,
            trainer_rtf INTEGER,
            topspeed INTEGER,
            stable_tour TEXT,
            stats_json TEXT,
            medical_json TEXT,
            PRIMARY KEY (date, course, off_time, horse_key)
        );

        CREATE TABLE betfair_prices (
            date TEXT NOT NULL,
            course TEXT,
            race_id INTEGER NOT NULL,
            off_time TEXT,
            horse_id TEXT,
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            sp TEXT,
            bsp REAL,
            wap REAL,
            morning_wap REAL,
            pre_min REAL,
            pre_max REAL,
            ip_min REAL,
            ip_max REAL,
            morning_vol REAL,
            pre_vol REAL,
            ip_vol REAL,
            PRIMARY KEY (date, race_id, horse_key)
        );

        CREATE TABLE bha_ratings (
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            year INTEGER,
            sex TEXT,
            sire TEXT,
            dam TEXT,
            trainer TEXT,
            flat_rating INTEGER,
            awt_rating INTEGER,
            chase_rating INTEGER,
            hurdle_rating INTEGER,
            PRIMARY KEY (horse_key, year)
        );

        CREATE TABLE performance_figures (
            horse_name TEXT NOT NULL,
            horse_key TEXT NOT NULL,
            year INTEGER,
            sex TEXT,
            trainer TEXT,
            latest TEXT,
            two_runs_ago TEXT,
            three_runs_ago TEXT,
            four_runs_ago TEXT,
            five_runs_ago TEXT,
            six_runs_ago TEXT,
            PRIMARY KEY (horse_key, year)
        );

        CREATE TABLE form_pattern_stats (
            pattern_length INTEGER NOT NULL,
            pattern TEXT NOT NULL,
            starts INTEGER NOT NULL,
            wins INTEGER NOT NULL,
            places INTEGER NOT NULL,
            win_rate REAL NOT NULL,
            place_rate REAL NOT NULL,
            PRIMARY KEY (pattern_length, pattern)
        );
        """
    )


def insert_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, str(value)))


def archive_result_sources(archive_root: Path, since: str) -> List[Tuple[str, Path]]:
    sources = []
    old = archive_root / "archive_2005-2014" / "archive_2005-2014" / "2005-2014.db"
    current = archive_root / "form_2015-present" / "form_2015-present" / "raceform.db"
    if old.exists() and since < "2015-01-01":
        sources.append(("archive_2005_2014", old))
    if current.exists():
        sources.append(("form_2015_present", current))
    return sources


def iter_source_rows(source_db: Path, since: str) -> Iterator[sqlite3.Row]:
    src = sqlite3.connect(str(source_db))
    src.row_factory = sqlite3.Row
    src.execute("PRAGMA query_only = ON")
    try:
        for row in src.execute(
            """
            SELECT date, course, race_id, off, race_name, type, class, pattern,
                   rating_band, age_band, sex_rest, dist, going, ran, num, pos,
                   draw, ovr_btn, btn, horse, age, sex, wgt, hg, time, sp,
                   jockey, trainer, prize, "or" AS official_rating, rpr, ts,
                   sire, dam, damsire, owner, comment
            FROM data
            WHERE date >= ?
              AND horse IS NOT NULL
              AND horse != ''
              AND horse != 'horse'
            ORDER BY date, race_id
            """,
            (since,),
        ):
            yield row
    finally:
        src.close()


def import_results(conn: sqlite3.Connection, archive_root: Path, since: str) -> Dict[str, int]:
    total = 0
    by_source: Dict[str, int] = {}
    sql = """
        INSERT OR IGNORE INTO form_results VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    for label, source_db in archive_result_sources(archive_root, since):
        batch = []
        count = 0
        for row in iter_source_rows(source_db, since):
            horse_name = clean_text(row["horse"])
            horse_key = norm_name(horse_name)
            race_date = parse_date(row["date"])
            race_id = safe_int(row["race_id"])
            if not race_date or not race_id or not horse_key:
                continue
            batch.append(
                (
                    race_date,
                    clean_text(row["course"]),
                    race_id,
                    clean_text(row["off"]),
                    clean_text(row["race_name"]),
                    clean_text(row["type"]),
                    clean_text(row["class"]),
                    clean_text(row["pattern"]),
                    clean_text(row["rating_band"]),
                    clean_text(row["age_band"]),
                    clean_text(row["sex_rest"]),
                    clean_text(row["dist"]),
                    clean_text(row["going"]),
                    safe_int(row["ran"]),
                    safe_int(row["num"]),
                    safe_int(row["pos"]),
                    safe_int(row["draw"]),
                    safe_float(row["ovr_btn"]),
                    safe_float(row["btn"]),
                    horse_name,
                    horse_key,
                    safe_int(row["age"]),
                    clean_text(row["sex"]),
                    clean_text(row["wgt"]),
                    weight_to_lbs(row["wgt"]),
                    clean_text(row["hg"]),
                    clean_text(row["time"]),
                    clean_text(row["sp"]),
                    parse_fractional_odds(row["sp"]),
                    clean_text(row["jockey"]),
                    clean_text(row["trainer"]),
                    safe_float(row["prize"]),
                    safe_int(row["official_rating"]),
                    safe_int(row["rpr"]),
                    safe_int(row["ts"]),
                    clean_text(row["sire"]),
                    clean_text(row["dam"]),
                    clean_text(row["damsire"]),
                    clean_text(row["owner"]),
                    clean_text(row["comment"]),
                    label,
                )
            )
            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                count += len(batch)
                batch.clear()
        if batch:
            conn.executemany(sql, batch)
            count += len(batch)
        by_source[label] = count
        total += count
        print(f"Imported {count:,} result rows from {label}")
    insert_meta(conn, "form_results_imported", total)
    return by_source


def import_result_csv(conn: sqlite3.Connection, path: Path, since: str, label: str) -> int:
    if not path.exists():
        return 0
    sql = """
        INSERT OR IGNORE INTO form_results VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
         ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    count = 0
    for row in iter_csv(path):
        race_date = parse_date(row.get("date"))
        race_id = safe_int(row.get("race_id"))
        horse_name = clean_text(row.get("horse"))
        horse_key = norm_name(horse_name)
        if not race_date or race_date < since or not race_id or not horse_key:
            continue
        batch.append(
            (
                race_date,
                clean_text(row.get("course")),
                race_id,
                clean_text(row.get("off")),
                clean_text(row.get("race_name")),
                clean_text(row.get("type")),
                clean_text(row.get("class")),
                clean_text(row.get("pattern")),
                clean_text(row.get("rating_band")),
                clean_text(row.get("age_band")),
                clean_text(row.get("sex_rest")),
                clean_text(row.get("dist")),
                clean_text(row.get("going")),
                safe_int(row.get("ran")),
                safe_int(row.get("num")),
                safe_int(row.get("pos")),
                safe_int(row.get("draw")),
                safe_float(row.get("ovr_btn")),
                safe_float(row.get("btn")),
                horse_name,
                horse_key,
                safe_int(row.get("age")),
                clean_text(row.get("sex")),
                clean_text(row.get("wgt")),
                weight_to_lbs(row.get("wgt")),
                clean_text(row.get("hg")),
                clean_text(row.get("time")),
                clean_text(row.get("sp")),
                parse_fractional_odds(row.get("sp")),
                clean_text(row.get("jockey")),
                clean_text(row.get("trainer")),
                safe_float(row.get("prize")),
                safe_int(row.get("or")),
                safe_int(row.get("rpr")),
                safe_int(row.get("ts")),
                clean_text(row.get("sire")),
                clean_text(row.get("dam")),
                clean_text(row.get("damsire")),
                clean_text(row.get("owner")),
                clean_text(row.get("comment")),
                label,
            )
        )
        if len(batch) >= BATCH_SIZE:
            conn.executemany(sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    print(f"Imported {count:,} result rows from {label}")
    return count


def iter_csv(path: Path) -> Iterator[Dict[str, str]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        yield from csv.DictReader(f)


def import_racecards(conn: sqlite3.Connection, archive_root: Path, since: str) -> int:
    folder = archive_root / "daily_racecards" / "daily_racecards"
    if not folder.exists():
        return 0
    sql = """
        INSERT OR IGNORE INTO racecards VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
         ?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    count = 0
    for path in sorted(folder.glob("*.csv")):
        race_date = parse_date(path.name)
        if not race_date or race_date < since:
            continue
        for row in iter_csv(path):
            horse_name = clean_text(row.get("horse_name"))
            horse_key = norm_name(horse_name)
            if not horse_key:
                continue
            batch.append(
                (
                    parse_date(row.get("date")) or race_date,
                    clean_text(row.get("region")),
                    clean_text(row.get("course")),
                    clean_text(row.get("going")),
                    clean_text(row.get("off_time")),
                    clean_text(row.get("distance")),
                    clean_text(row.get("race_name")),
                    horse_name,
                    horse_key,
                    safe_int(row.get("field_size")),
                    safe_int(row.get("draw")),
                    safe_int(row.get("age")),
                    safe_int(row.get("lbs")),
                    clean_text(row.get("form")),
                    clean_text(row.get("jockey")),
                    clean_text(row.get("owner")),
                    clean_text(row.get("race_class")),
                    safe_int(row.get("rpr")),
                    clean_text(row.get("sex")),
                    clean_text(row.get("sire")),
                    clean_text(row.get("dam")),
                    clean_text(row.get("spotlight")),
                    clean_text(row.get("comment")),
                    clean_text(row.get("trainer")),
                    clean_text(row.get("trainer_14_days")),
                    safe_int(row.get("trainer_rtf")),
                    safe_int(row.get("ts")),
                    clean_text(row.get("stable_tour")),
                    clean_text(row.get("stats")),
                    clean_text(row.get("medical")),
                )
            )
            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                count += len(batch)
                batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    insert_meta(conn, "racecards_imported", count)
    print(f"Imported {count:,} racecard rows")
    return count


def import_betfair(conn: sqlite3.Connection, archive_root: Path, since: str) -> int:
    folder = archive_root / "betfair" / "betfair"
    if not folder.exists():
        return 0
    sql = """
        INSERT OR IGNORE INTO betfair_prices VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    batch = []
    count = 0
    for path in sorted(folder.glob("betfair_mapping_*.csv")):
        for row in iter_csv(path):
            race_date = parse_date(row.get("date"))
            horse_name = clean_text(row.get("horse"))
            horse_key = norm_name(horse_name)
            race_id = safe_int(row.get("race_id"))
            if not race_date or race_date < since or not horse_key or not race_id:
                continue
            batch.append(
                (
                    race_date,
                    clean_text(row.get("course")),
                    race_id,
                    clean_text(row.get("off")),
                    clean_text(row.get("horse_id")),
                    horse_name,
                    horse_key,
                    clean_text(row.get("sp")),
                    safe_float(row.get("bsp")),
                    safe_float(row.get("wap")),
                    safe_float(row.get("morning_wap")),
                    safe_float(row.get("pre_min")),
                    safe_float(row.get("pre_max")),
                    safe_float(row.get("ip_min")),
                    safe_float(row.get("ip_max")),
                    safe_float(row.get("morning_vol")),
                    safe_float(row.get("pre_vol")),
                    safe_float(row.get("ip_vol")),
                )
            )
            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                count += len(batch)
                batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    insert_meta(conn, "betfair_prices_imported", count)
    print(f"Imported {count:,} Betfair price rows")
    return count


def import_bha(conn: sqlite3.Connection, archive_root: Path) -> Dict[str, int]:
    folder = archive_root / "BHA_ratings" / "BHA_ratings"
    counts = {"bha_ratings": 0, "performance_figures": 0}
    ratings = folder / "Full_ratings.csv"
    if ratings.exists():
        sql = "INSERT OR IGNORE INTO bha_ratings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        batch = []
        for row in iter_csv(ratings):
            name = clean_text(row.get("Name"))
            key = norm_name(name)
            if not key:
                continue
            batch.append(
                (
                    name,
                    key,
                    safe_int(row.get("Year")),
                    clean_text(row.get("Sex")),
                    clean_text(row.get("Sire")),
                    clean_text(row.get("Dam")),
                    clean_text(row.get("Trainer")),
                    safe_int(row.get("Flat rating")),
                    safe_int(row.get("AWT rating")),
                    safe_int(row.get("Chase rating")),
                    safe_int(row.get("Hurdle rating")),
                )
            )
            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                counts["bha_ratings"] += len(batch)
                batch.clear()
        if batch:
            conn.executemany(sql, batch)
            counts["bha_ratings"] += len(batch)

    figures = folder / "performance-figures.csv"
    if figures.exists():
        sql = "INSERT OR IGNORE INTO performance_figures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        batch = []
        for row in iter_csv(figures):
            name = clean_text(row.get("Racehorse"))
            key = norm_name(name)
            if not key:
                continue
            batch.append(
                (
                    name,
                    key,
                    safe_int(row.get("YOF")),
                    clean_text(row.get("Sex")),
                    clean_text(row.get("Trainer")),
                    clean_text(row.get("Latest")),
                    clean_text(row.get("2 runs ago")),
                    clean_text(row.get("3 runs ago")),
                    clean_text(row.get("4 runs ago")),
                    clean_text(row.get("5 runs ago")),
                    clean_text(row.get("6 runs ago")),
                )
            )
            if len(batch) >= BATCH_SIZE:
                conn.executemany(sql, batch)
                counts["performance_figures"] += len(batch)
                batch.clear()
        if batch:
            conn.executemany(sql, batch)
            counts["performance_figures"] += len(batch)
    for key, value in counts.items():
        insert_meta(conn, f"{key}_imported", value)
        print(f"Imported {value:,} {key.replace('_', ' ')} rows")
    return counts


def build_form_pattern_stats(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        SELECT horse_key, date, race_id, position
        FROM form_results
        WHERE position IS NOT NULL AND position > 0
        ORDER BY horse_key, date, race_id
        """
    ).fetchall()
    stats: Dict[Tuple[int, str], List[int]] = {}
    previous: Dict[str, List[int]] = {}

    def marker(pos: int) -> str:
        return str(pos) if pos < 10 else "0"

    for horse_key, _date, _race_id, position in rows:
        history = previous.setdefault(horse_key, [])
        for length in (3, 4, 5):
            if len(history) >= length:
                pattern = "".join(marker(pos) for pos in history[-length:])
                entry = stats.setdefault((length, pattern), [0, 0, 0])
                entry[0] += 1
                entry[1] += 1 if position == 1 else 0
                entry[2] += 1 if position <= 3 else 0
        history.append(int(position))

    batch = []
    for (length, pattern), (starts, wins, places) in stats.items():
        if starts < 5:
            continue
        batch.append(
            (
                length,
                pattern,
                starts,
                wins,
                places,
                round(wins / starts, 6),
                round(places / starts, 6),
            )
        )
    conn.executemany("INSERT OR REPLACE INTO form_pattern_stats VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
    insert_meta(conn, "form_pattern_stats", len(batch))
    print(f"Built {len(batch):,} form pattern rows")
    return len(batch)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX idx_form_results_horse_date ON form_results (horse_key, date);
        CREATE INDEX idx_form_results_date ON form_results (date);
        CREATE INDEX idx_form_results_race ON form_results (date, race_id);
        CREATE INDEX idx_form_results_course_date ON form_results (course, date);
        CREATE INDEX idx_form_results_conditions ON form_results (distance, going, race_type);
        CREATE INDEX idx_form_results_position ON form_results (position);
        CREATE INDEX idx_form_results_rating ON form_results (official_rating, rpr, topspeed);

        CREATE INDEX idx_racecards_horse_date ON racecards (horse_key, date);
        CREATE INDEX idx_racecards_date ON racecards (date);
        CREATE INDEX idx_betfair_horse_date ON betfair_prices (horse_key, date);
        CREATE INDEX idx_bha_horse ON bha_ratings (horse_key);
        CREATE INDEX idx_perf_figures_horse ON performance_figures (horse_key);
        CREATE INDEX idx_form_pattern_lookup ON form_pattern_stats (pattern_length, pattern);
        """
    )


def database_summary(conn: sqlite3.Connection) -> Dict[str, Any]:
    summary = {
        "formResultsRows": conn.execute("SELECT COUNT(*) FROM form_results").fetchone()[0],
        "racecardRows": conn.execute("SELECT COUNT(*) FROM racecards").fetchone()[0],
        "betfairPriceRows": conn.execute("SELECT COUNT(*) FROM betfair_prices").fetchone()[0],
        "bhaRatingRows": conn.execute("SELECT COUNT(*) FROM bha_ratings").fetchone()[0],
        "performanceFigureRows": conn.execute("SELECT COUNT(*) FROM performance_figures").fetchone()[0],
        "formPatternRows": conn.execute("SELECT COUNT(*) FROM form_pattern_stats").fetchone()[0],
        "uniqueHorses": conn.execute("SELECT COUNT(DISTINCT horse_key) FROM form_results").fetchone()[0],
        "uniqueRaces": conn.execute("SELECT COUNT(DISTINCT date || '|' || race_id) FROM form_results").fetchone()[0],
        "earliestDate": conn.execute("SELECT MIN(date) FROM form_results").fetchone()[0],
        "latestDate": conn.execute("SELECT MAX(date) FROM form_results").fetchone()[0],
    }
    return summary


def write_status(path: Path, db_path: Path, archive_root: Path, since: str, summary: Dict[str, Any]) -> None:
    payload = {
        "builtAt": datetime.now(timezone.utc).isoformat(),
        "database": str(db_path),
        "archiveRoot": str(archive_root),
        "sinceDate": since,
        "purpose": "Form-history research only. No live pick impact.",
        **summary,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_database(db_path: Path, archive_root: Path, since: str, status_path: Path) -> Dict[str, Any]:
    if not archive_root.exists():
        raise SystemExit(f"Archive folder not found: {archive_root}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = Path(str(db_path) + ".tmp")
    remove_db(temp_path)

    conn = sqlite3.connect(str(temp_path))
    try:
        create_schema(conn)
        insert_meta(conn, "built_at", datetime.now(timezone.utc).isoformat())
        insert_meta(conn, "archive_root", archive_root)
        insert_meta(conn, "since_date", since)
        source_counts = import_results(conn, archive_root, since)
        source_counts["mini_update"] = import_result_csv(conn, archive_root / "mini-update.csv", since, "mini_update")
        insert_meta(conn, "result_source_counts_json", json.dumps(source_counts, sort_keys=True))
        insert_meta(conn, "form_results_imported", sum(source_counts.values()))
        conn.commit()
        import_racecards(conn, archive_root, since)
        import_betfair(conn, archive_root, since)
        import_bha(conn, archive_root)
        conn.commit()
        build_form_pattern_stats(conn)
        conn.commit()
        create_indexes(conn)
        conn.commit()
        summary = database_summary(conn)
        insert_meta(conn, "summary_json", json.dumps(summary, sort_keys=True))
        conn.commit()
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()

    remove_db(db_path)
    shutil.move(str(temp_path), str(db_path))
    remove_db(temp_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    try:
        summary = database_summary(conn)
    finally:
        conn.close()

    write_status(status_path, db_path, archive_root, since, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Import form archive into a separate Signal 75 research database.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE), help="Downloaded archive folder")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Output form-history SQLite database")
    parser.add_argument("--status", default=str(DEFAULT_STATUS), help="Output status JSON")
    parser.add_argument("--since-date", default=DEFAULT_SINCE, help="Oldest result date to import")
    args = parser.parse_args()

    summary = build_database(
        db_path=Path(args.db),
        archive_root=Path(args.archive_root),
        since=args.since_date,
        status_path=Path(args.status),
    )
    print(f"Form history research database built: {args.db}")
    for key, value in summary.items():
        print(f"- {key}: {value:,}" if isinstance(value, int) else f"- {key}: {value}")


if __name__ == "__main__":
    main()
