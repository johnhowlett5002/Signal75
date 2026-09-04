#!/usr/bin/env python3
"""Write a single freshness report for Signal 75 learning stores.

This does not change picks, scoring, settlement or proof. It records what the
two intelligence databases actually contain so stale data cannot go unnoticed:

* signal75_history.sqlite: the live daily learning/rival-memory store.
* form_history.sqlite: the imported historical rich-form archive.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from signal75_intelligence_store import (
    FORM_ARCHIVE_DB,
    LIVE_DB,
    connect_readonly,
    live_store_health,
)


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
INTEL = DATA / "horse_intelligence"
FORM_DB = FORM_ARCHIVE_DB
FORM_STATUS = INTEL / "form_history_status.json"
DEFAULT_ARCHIVE = Path.home() / "Downloads" / "archive (1)"
OUT = INTEL / "data_freshness_status.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


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


def sqlite_scalar(db_path: Path, sql: str, default: Any = None) -> Any:
    if not db_path.exists():
        return default
    try:
        with connect_readonly(db_path) as conn:
            return conn.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return default


def table_exists(db_path: Path, table: str) -> bool:
    if not db_path.exists():
        return False
    try:
        with connect_readonly(db_path) as conn:
            return bool(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
            )
    except sqlite3.Error:
        return False


def source_archive_latest(archive_root: Path) -> Dict[str, Any]:
    """Inspect the local archive source without importing it."""
    result_db = archive_root / "form_2015-present" / "form_2015-present" / "raceform.db"
    racecard_dir = archive_root / "daily_racecards" / "daily_racecards"
    result_latest = None
    result_rows = 0
    if result_db.exists():
        try:
            with connect_readonly(result_db) as conn:
                row = conn.execute(
                    """
                    SELECT MAX(date), COUNT(*)
                    FROM data
                    WHERE date GLOB '????-??-??'
                    """
                ).fetchone()
                result_latest, result_rows = row[0], int(row[1] or 0)
        except sqlite3.Error:
            pass

    racecard_latest = None
    racecard_files = 0
    if racecard_dir.exists():
        for path in racecard_dir.glob("*.json"):
            racecard_files += 1
            candidate = path.stem[:10]
            if candidate and (racecard_latest is None or candidate > racecard_latest):
                racecard_latest = candidate

    return {
        "archiveRoot": str(archive_root),
        "resultArchiveExists": result_db.exists(),
        "sourceLatestResultDate": result_latest,
        "sourceResultRows": result_rows,
        "sourceLatestRacecardDate": racecard_latest,
        "sourceRacecardFiles": racecard_files,
    }


def live_db_status() -> Dict[str, Any]:
    health = live_store_health()
    return {
        "database": "data/horse_intelligence/signal75_history.sqlite",
        "exists": LIVE_DB.exists(),
        "purpose": "Central daily Signal 75 learning store: race memory, head-to-head, class, weight, draw, trainer, jockey and result context.",
        "latestDate": health.get("latestDate"),
        "latestHeadToHeadDate": health.get("latestHeadToHeadDate"),
        "latestRaceMemoryDate": health.get("latestRaceMemoryDate"),
        "daysOld": health.get("daysOld"),
        "headToHeadRows": int(health.get("headToHeadRows") or 0),
        "raceMemoryRows": int(health.get("raceMemoryRows") or 0),
        "requiredRichFields": health.get("requiredRichFields") or [],
        "errors": health.get("errors") or [],
        "warnings": health.get("warnings") or [],
        "status": health.get("status", "ERROR"),
    }


def form_db_status(archive_root: Path) -> Dict[str, Any]:
    latest = sqlite_scalar(FORM_DB, "SELECT MAX(date) FROM form_results")
    rows = sqlite_scalar(FORM_DB, "SELECT COUNT(*) FROM form_results", 0)
    racecards_latest = sqlite_scalar(FORM_DB, "SELECT MAX(date) FROM racecards")
    pattern_rows = sqlite_scalar(FORM_DB, "SELECT COUNT(*) FROM form_pattern_stats", 0)
    status_json = read_json(FORM_STATUS, {})
    source = source_archive_latest(archive_root)
    age = days_old(latest)
    stale = age is None or age > 14
    return {
        "database": "data/horse_intelligence/form_history.sqlite",
        "exists": FORM_DB.exists(),
        "purpose": "Historical rich-form archive. Used for pattern research and dashboard context; not a complete daily source unless the archive source is current.",
        "latestDate": latest,
        "latestRacecardDate": racecards_latest,
        "daysOld": age,
        "formResultsRows": int(rows or 0),
        "formPatternRows": int(pattern_rows or 0),
        "status": "STALE" if stale else "OK",
        "statusFilePurposeWas": status_json.get("purpose"),
        "source": source,
    }


def maybe_refresh_live_db(refresh: bool) -> Dict[str, Any]:
    if not refresh:
        return {"ran": False}
    result = subprocess.run(
        [sys.executable, "scripts/build-intelligence-db.py"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ran": True,
        "returncode": result.returncode,
        "stdoutTail": (result.stdout or "")[-2000:],
        "stderrTail": (result.stderr or "")[-2000:],
    }


def build_payload(archive_root: Path, refresh_live: bool = False) -> Dict[str, Any]:
    refresh = maybe_refresh_live_db(refresh_live)
    live = live_db_status()
    form = form_db_status(archive_root)
    warnings = []
    errors = []

    if live["status"] != "OK":
        errors.append(
            f"Central live learning store is stale or missing: latest={live.get('latestDate')} rows={live.get('headToHeadRows')}"
        )
        errors.extend(live.get("errors") or [])
    warnings.extend(live.get("warnings") or [])
    daily_sync = read_json(FORM_STATUS, {}).get("dailySync") or {}
    daily_sync_active = bool(daily_sync.get("syncedAt"))
    if form["status"] == "STALE":
        warnings.append(
            f"Historical rich-form archive is stale: latest={form.get('latestDate')} source_latest={form.get('source', {}).get('sourceLatestResultDate')}"
        )
    source_latest = form.get("source", {}).get("sourceLatestResultDate")
    if source_latest and form.get("latestDate") and source_latest <= form.get("latestDate") and not daily_sync_active:
        warnings.append("Local rich-form source archive has no newer data to backfill.")

    status = "ERROR" if errors else ("WARNING" if warnings else "OK")
    return {
        "generatedAt": iso_now(),
        "date": date.today().isoformat(),
        "status": status,
        "centralSource": "data/horse_intelligence/signal75_history.sqlite",
        "refreshLiveDatabase": refresh,
        "liveLearningDatabase": live,
        "historicalFormArchive": form,
        "dailyRichFormSync": daily_sync,
        "warnings": warnings,
        "errors": errors,
        "nextActions": [
            "Use signal75_history.sqlite as the central daily intelligence store.",
            "Treat form_history.sqlite as historical archive/pattern context until a fresh external source is added.",
            "Do not run a form-history backfill unless the local archive or provider source has dates newer than the current database.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Signal 75 data freshness status.")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--refresh-live-db", action="store_true")
    args = parser.parse_args()

    payload = build_payload(Path(args.archive_root), refresh_live=args.refresh_live_db)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"Data freshness status: {payload['status']}")
    print(f"Live learning latest: {payload['liveLearningDatabase'].get('latestDate')}")
    print(f"Rich form archive latest: {payload['historicalFormArchive'].get('latestDate')}")
    for warning in payload.get("warnings", []):
        print(f"WARNING: {warning}")
    for error in payload.get("errors", []):
        print(f"ERROR: {error}")

    return 2 if payload["errors"] else (1 if payload["warnings"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
