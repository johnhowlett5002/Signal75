#!/usr/bin/env python3
"""Export compact SQLite intelligence summaries for the private dashboard.

Dashboard-only. This reads the combined learning SQLite summary tables and
writes a small JSON feed for browser display. It never changes picks, scoring,
settlement, proof, or performance.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
SUMMARY_DB = DATA / "combined_learning" / "signal75_learning.sqlite"
OUT = REPO / "dashboard" / "data" / "sqliteIntelligence.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def open_readonly_database(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    query = "mode=ro&immutable=1" if not os.access(resolved, os.W_OK) else "mode=ro"
    conn = sqlite3.connect(f"{resolved.as_uri()}?{query}", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".sqlite-intel-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        Path(temp_name).replace(path)
    finally:
        Path(temp_name).unlink(missing_ok=True)


def status_map(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM summary_build_status").fetchall()
    status = {row["key"]: row["value"] for row in rows}
    table_counts = status.get("table_counts")
    if isinstance(table_counts, str):
        try:
            status["table_counts"] = json.loads(table_counts)
        except json.JSONDecodeError:
            status["table_counts"] = {}
    return status


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def build_payload(date_text: str) -> dict[str, Any]:
    if not SUMMARY_DB.exists():
        raise FileNotFoundError(f"Missing SQLite summary database: {SUMMARY_DB}")

    with open_readonly_database(SUMMARY_DB) as conn:
        conn.row_factory = sqlite3.Row
        status = status_map(conn)
        table_counts = status.get("table_counts") or {
            name: count_rows(conn, name)
            for name in (
                "horse_profile_summary",
                "h2h_field_summary",
                "form_pattern_summary",
                "class_movement_summary",
                "course_distance_summary",
                "dashboard_race_review_summary",
                "challenger_performance_summary",
            )
        }

        latest_review = rows(
            conn,
            """
            SELECT *
            FROM dashboard_race_review_summary
            ORDER BY date DESC
            LIMIT 1
            """,
        )
        recent_reviews = rows(
            conn,
            """
            SELECT *
            FROM dashboard_race_review_summary
            ORDER BY date DESC
            LIMIT 14
            """,
        )
        challengers = rows(
            conn,
            """
            SELECT id, name, status, days_tested, settled_days, picks_tested,
                   trial_return, paper_profit, delta_vs_live_profit,
                   plain_summary, updated_at
            FROM challenger_performance_summary
            ORDER BY
              CASE status
                WHEN 'READY' THEN 1
                WHEN 'PROMISING' THEN 2
                WHEN 'COLLECTING' THEN 3
                WHEN 'RISKY' THEN 4
                ELSE 5
              END,
              settled_days DESC,
              id
            """,
        )
        top_h2h = rows(
            conn,
            """
            SELECT winner, loser, meetings_won, latest_date
            FROM h2h_field_summary
            ORDER BY meetings_won DESC, latest_date DESC
            LIMIT 10
            """,
        )
        form_patterns = rows(
            conn,
            """
            SELECT pattern_length, pattern, starts, wins, places,
                   ROUND(win_rate, 3) AS win_rate,
                   ROUND(place_rate, 3) AS place_rate,
                   form_strength
            FROM form_pattern_summary
            WHERE starts >= 100
            ORDER BY place_rate DESC, starts DESC
            LIMIT 12
            """,
        )
        class_movement = rows(
            conn,
            """
            SELECT class_movement, race_class_level, runs, wins, places,
                   ROUND(win_pct, 1) AS win_pct,
                   ROUND(place_pct, 1) AS place_pct
            FROM class_movement_summary
            ORDER BY runs DESC, class_movement, race_class_level
            LIMIT 20
            """,
        )
        course_distance = rows(
            conn,
            """
            SELECT course, distance_band, runs, wins, places,
                   ROUND(win_pct, 1) AS win_pct,
                   ROUND(place_pct, 1) AS place_pct,
                   latest_date
            FROM course_distance_summary
            ORDER BY runs DESC, latest_date DESC
            LIMIT 12
            """,
        )

    return {
        "date": date_text,
        "generatedAt": iso_now(),
        "analysis_only": True,
        "dashboard_only": True,
        "scoring_impact": "none",
        "source": "data/combined_learning/signal75_learning.sqlite",
        "summaryStatus": {
            "asOfDate": status.get("as_of_date"),
            "builtAt": status.get("built_at"),
            "source": status.get("source"),
            "tableCounts": table_counts,
        },
        "learningCoverage": {
            "horsesProfiled": table_counts.get("horse_profile_summary", 0),
            "h2hPairs": table_counts.get("h2h_field_summary", 0),
            "formPatterns": table_counts.get("form_pattern_summary", 0),
            "classBuckets": table_counts.get("class_movement_summary", 0),
            "courseDistanceBuckets": table_counts.get("course_distance_summary", 0),
            "raceReviewDays": table_counts.get("dashboard_race_review_summary", 0),
            "challengersTracked": table_counts.get("challenger_performance_summary", 0),
        },
        "latestRaceReview": latest_review[0] if latest_review else {},
        "recentRaceReviews": recent_reviews,
        "challengerSummary": challengers,
        "topHeadToHead": top_h2h,
        "strongFormPatterns": form_patterns,
        "classMovement": class_movement,
        "courseDistance": course_distance,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dashboard SQLite intelligence feed.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    payload = build_payload(args.date)
    write_json(Path(args.output), payload)
    coverage = payload["learningCoverage"]
    print(
        "SQLite dashboard intelligence exported: "
        f"{coverage['horsesProfiled']:,} horses, "
        f"{coverage['h2hPairs']:,} H2H pairs, "
        f"{coverage['formPatterns']:,} form patterns"
    )
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
