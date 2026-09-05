#!/usr/bin/env python3
"""Central intelligence-store access for Signal 75.

This module is the contract for future selection and Challenger Lab work:

* signal75_history.sqlite is the live, growing daily learning store.
* form_history.sqlite is an imported historical archive and must be treated as
  stale/analysis-only unless its freshness status says otherwise.

It intentionally contains no scoring logic and never writes picks, proof,
results or performance data.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"

LIVE_DB = INTEL / "signal75_history.sqlite"
FORM_ARCHIVE_DB = INTEL / "form_history.sqlite"
FRESHNESS_STATUS = INTEL / "data_freshness_status.json"

LIVE_REQUIRED_TABLES = {"race_memory", "head_to_head"}
LIVE_REQUIRED_RACE_MEMORY_COLUMNS = {
    "date",
    "horse_name",
    "horse_key",
    "course",
    "race_time",
    "distance_furlongs",
    "distance_band",
    "known_result",
    "finishing_position",
    "pre_race_price",
    "signal_score",
    "official_pick",
    "watchlist",
    "tipster_count",
    "jockey",
    "trainer",
    "form",
    "days_since_run",
    "field_size",
    "draw_bucket",
    "carried_weight_lbs",
    "official_rating",
    "race_class_label",
    "race_class_level",
    "previous_race_class_label",
    "previous_race_class_level",
    "class_movement",
    "class_movement_steps",
}


class IntelligenceStoreError(RuntimeError):
    """Raised when the live intelligence store is unavailable or unsafe."""


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def days_old(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return (date.today() - date.fromisoformat(str(value)[:10])).days
    except ValueError:
        return None


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise IntelligenceStoreError(f"SQLite database not found: {path}")
    resolved = path.resolve()
    query = "mode=ro&immutable=1" if not os.access(resolved, os.W_OK) else "mode=ro"
    conn = sqlite3.connect(f"{resolved.as_uri()}?{query}", uri=True)
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def connect_live() -> sqlite3.Connection:
    """Open the central daily Signal 75 learning store in read-only mode."""
    return connect_readonly(LIVE_DB)


def connect_form_archive(*, allow_stale: bool = False) -> sqlite3.Connection:
    """Open the historical form archive.

    Callers must explicitly pass allow_stale=True when they are using the
    archive for analysis-only pattern context. This prevents new live selection
    work from accidentally treating stale archive data as current truth.
    """
    status = freshness_payload().get("historicalFormArchive") or {}
    if not allow_stale and status.get("status") != "OK":
        raise IntelligenceStoreError(
            "form_history.sqlite is not current. Use signal75_history.sqlite for "
            "live learning, or pass allow_stale=True for analysis-only context."
        )
    return connect_readonly(FORM_ARCHIVE_DB)


def freshness_payload() -> Dict[str, Any]:
    return read_json(FRESHNESS_STATUS, {})


def table_names(conn: sqlite3.Connection) -> Set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def table_columns(conn: sqlite3.Connection, table: str) -> Set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> Any:
    row = conn.execute(sql, tuple(params)).fetchone()
    return row[0] if row else None


def live_store_health(max_days_old: int = 3, min_h2h_rows: int = 200_000) -> Dict[str, Any]:
    """Return a compact health report for the central live store."""
    try:
        with connect_live() as conn:
            tables = table_names(conn)
            missing_tables = sorted(LIVE_REQUIRED_TABLES - tables)
            columns = table_columns(conn, "race_memory") if "race_memory" in tables else set()
            missing_columns = sorted(LIVE_REQUIRED_RACE_MEMORY_COLUMNS - columns)
            h2h_rows = int(scalar(conn, "SELECT COUNT(*) FROM head_to_head") or 0) if "head_to_head" in tables else 0
            race_memory_rows = int(scalar(conn, "SELECT COUNT(*) FROM race_memory") or 0) if "race_memory" in tables else 0
            latest_h2h = scalar(conn, "SELECT MAX(date) FROM head_to_head") if "head_to_head" in tables else None
            latest_memory = scalar(conn, "SELECT MAX(date) FROM race_memory") if "race_memory" in tables else None
            latest = max([d for d in (latest_h2h, latest_memory) if d] or [None])
    except (sqlite3.Error, IntelligenceStoreError) as exc:
        return {
            "status": "ERROR",
            "errors": [str(exc)],
            "warnings": [],
            "latestDate": None,
            "headToHeadRows": 0,
            "raceMemoryRows": 0,
        }

    age = days_old(latest)
    errors = []
    warnings = []
    if missing_tables:
        errors.append(f"Missing live intelligence tables: {', '.join(missing_tables)}")
    if missing_columns:
        errors.append(f"race_memory missing rich fields: {', '.join(missing_columns)}")
    if h2h_rows < min_h2h_rows:
        errors.append(f"head_to_head row count below safe deduplicated baseline: {h2h_rows:,}")
    if age is None or age > max_days_old:
        errors.append(f"live learning latest date is stale: {latest}")
    if race_memory_rows <= 0:
        errors.append("race_memory has no rows")

    return {
        "status": "ERROR" if errors else ("WARNING" if warnings else "OK"),
        "errors": errors,
        "warnings": warnings,
        "latestDate": latest,
        "latestHeadToHeadDate": latest_h2h,
        "latestRaceMemoryDate": latest_memory,
        "daysOld": age,
        "headToHeadRows": h2h_rows,
        "raceMemoryRows": race_memory_rows,
        "requiredRichFields": sorted(LIVE_REQUIRED_RACE_MEMORY_COLUMNS),
    }


def assert_live_store_ready() -> None:
    health = live_store_health()
    if health.get("status") == "ERROR":
        raise IntelligenceStoreError("; ".join(health.get("errors") or ["Live intelligence store failed health check"]))
