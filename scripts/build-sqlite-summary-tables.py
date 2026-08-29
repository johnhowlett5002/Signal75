#!/usr/bin/env python3
"""Build fast SQLite summary tables for Signal 75 intelligence.

This is storage/query optimisation only. It does not change live scoring,
picks, proof, settlement, ROI, public files or dashboard rendering.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
INTEL = DATA / "horse_intelligence"
COMBINED_DB = DATA / "combined_learning" / "signal75_learning.sqlite"
LIVE_DB = INTEL / "signal75_history.sqlite"
FORM_DB = INTEL / "form_history.sqlite"
CHALLENGER_SUMMARY = DATA / "challenger_lab" / "challenger_summary.json"


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def execute_many(db_path: Path, statements: Iterable[str]) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Missing database: {db_path}")
    with sqlite3.connect(str(db_path), timeout=60) as conn:
        conn.execute("PRAGMA busy_timeout = 60000")
        for statement in statements:
            conn.execute(statement)
        conn.commit()


def add_indexes() -> None:
    execute_many(
        LIVE_DB,
        [
            "CREATE INDEX IF NOT EXISTS idx_race_memory_date_horse ON race_memory (date, horse_key)",
            "CREATE INDEX IF NOT EXISTS idx_race_memory_market ON race_memory (market_id)",
            "CREATE INDEX IF NOT EXISTS idx_race_memory_class ON race_memory (race_class_level, class_movement)",
            "CREATE INDEX IF NOT EXISTS idx_race_memory_distance ON race_memory (distance_band)",
            "CREATE INDEX IF NOT EXISTS idx_h2h_winner_loser_date ON head_to_head (winner_key, loser_key, date)",
            "CREATE INDEX IF NOT EXISTS idx_h2h_date ON head_to_head (date)",
            "CREATE INDEX IF NOT EXISTS idx_historic_rivals_target ON historic_rivals (target_date, target_market_id)",
            "CREATE INDEX IF NOT EXISTS idx_historic_rivals_pair ON historic_rivals (winner_key, loser_key)",
            "CREATE INDEX IF NOT EXISTS idx_horse_history_date_horse ON horse_history (date, horse_key)",
            "CREATE INDEX IF NOT EXISTS idx_historical_runners_date_horse ON historical_runners (race_date, horse_key)",
        ],
    )
    execute_many(
        FORM_DB,
        [
            "CREATE INDEX IF NOT EXISTS idx_form_results_horse_date ON form_results (horse_key, date)",
            "CREATE INDEX IF NOT EXISTS idx_form_results_pattern_date ON form_results (pattern, date)",
            "CREATE INDEX IF NOT EXISTS idx_form_results_class_date ON form_results (race_class, date)",
            "CREATE INDEX IF NOT EXISTS idx_form_results_course_distance ON form_results (course, distance)",
            "CREATE INDEX IF NOT EXISTS idx_racecards_date_horse ON racecards (date, horse_key)",
            "CREATE INDEX IF NOT EXISTS idx_racecards_class ON racecards (race_class)",
            "CREATE INDEX IF NOT EXISTS idx_form_pattern_stats_pattern ON form_pattern_stats (pattern_length, pattern)",
        ],
    )
    execute_many(
        COMBINED_DB,
        [
            "CREATE INDEX IF NOT EXISTS idx_combined_date_horse ON combined_learning (date, horse_key)",
            "CREATE INDEX IF NOT EXISTS idx_combined_market ON combined_learning (market_id)",
            "CREATE INDEX IF NOT EXISTS idx_combined_selection_result ON combined_learning (selection_type, result)",
            "CREATE INDEX IF NOT EXISTS idx_combined_class ON combined_learning (race_class_level, class_movement)",
            "CREATE INDEX IF NOT EXISTS idx_combined_distance ON combined_learning (course, distance_band)",
            "CREATE INDEX IF NOT EXISTS idx_combined_h2h ON combined_learning (head_to_head_wins_today, head_to_head_losses_today)",
        ],
    )


def rebuild_combined_summaries(as_of_date: str) -> dict[str, Any]:
    COMBINED_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(COMBINED_DB), timeout=60) as conn:
        conn.execute("PRAGMA busy_timeout = 60000")
        conn.execute("ATTACH DATABASE ? AS live", (str(LIVE_DB),))
        conn.execute("ATTACH DATABASE ? AS formdb", (str(FORM_DB),))

        conn.executescript(
            """
            DROP TABLE IF EXISTS horse_profile_summary;
            CREATE TABLE horse_profile_summary AS
            SELECT
                horse_key,
                MAX(horse_name) AS horse_name,
                COUNT(*) AS rows_seen,
                SUM(CASE WHEN selection_type = 'official' THEN 1 ELSE 0 END) AS official_picks,
                SUM(CASE WHEN selection_type = 'watchlist' THEN 1 ELSE 0 END) AS watchlist_count,
                SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN placed = 1 THEN 1 ELSE 0 END) AS places,
                ROUND(AVG(signal_score), 2) AS avg_signal_score,
                ROUND(AVG(pre_race_price), 2) AS avg_pre_race_price,
                SUM(COALESCE(head_to_head_wins_today, 0)) AS h2h_wins_today,
                SUM(COALESCE(head_to_head_losses_today, 0)) AS h2h_losses_today,
                SUM(CASE WHEN class_movement = 'class_rise' THEN 1 ELSE 0 END) AS class_rises,
                SUM(CASE WHEN class_movement = 'class_drop' THEN 1 ELSE 0 END) AS class_drops,
                MAX(date) AS latest_date
            FROM combined_learning
            WHERE horse_key IS NOT NULL AND horse_key != ''
            GROUP BY horse_key;

            DROP TABLE IF EXISTS h2h_field_summary;
            CREATE TABLE h2h_field_summary AS
            SELECT
                winner_key,
                MAX(winner) AS winner,
                loser_key,
                MAX(loser) AS loser,
                COUNT(DISTINCT date || '|' || COALESCE(course, '') || '|' || COALESCE(race_time, '') || '|' || COALESCE(market_id, '')) AS meetings_won,
                MAX(date) AS latest_date
            FROM live.head_to_head
            WHERE winner_key IS NOT NULL AND winner_key != ''
              AND loser_key IS NOT NULL AND loser_key != ''
            GROUP BY winner_key, loser_key;

            DROP TABLE IF EXISTS form_pattern_summary;
            CREATE TABLE form_pattern_summary AS
            SELECT
                pattern_length,
                pattern,
                starts,
                wins,
                places,
                win_rate,
                place_rate,
                CASE
                    WHEN place_rate >= 0.45 THEN 'STRONG'
                    WHEN place_rate >= 0.35 THEN 'GOOD'
                    WHEN place_rate >= 0.20 THEN 'WEAK'
                    ELSE 'AVOID'
                END AS form_strength
            FROM formdb.form_pattern_stats;

            DROP TABLE IF EXISTS class_movement_summary;
            CREATE TABLE class_movement_summary AS
            SELECT
                COALESCE(class_movement, 'unknown') AS class_movement,
                COALESCE(race_class_level, -1) AS race_class_level,
                COUNT(*) AS runs,
                SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN placed = 1 THEN 1 ELSE 0 END) AS places,
                ROUND(100.0 * SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS win_pct,
                ROUND(100.0 * SUM(CASE WHEN placed = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS place_pct
            FROM combined_learning
            GROUP BY COALESCE(class_movement, 'unknown'), COALESCE(race_class_level, -1);

            DROP TABLE IF EXISTS course_distance_summary;
            CREATE TABLE course_distance_summary AS
            SELECT
                COALESCE(course, '') AS course,
                COALESCE(distance_band, 'unknown') AS distance_band,
                COUNT(*) AS runs,
                SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN placed = 1 THEN 1 ELSE 0 END) AS places,
                ROUND(100.0 * SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS win_pct,
                ROUND(100.0 * SUM(CASE WHEN placed = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS place_pct,
                MAX(date) AS latest_date
            FROM combined_learning
            WHERE course IS NOT NULL AND course != ''
            GROUP BY COALESCE(course, ''), COALESCE(distance_band, 'unknown');

            DROP TABLE IF EXISTS dashboard_race_review_summary;
            CREATE TABLE dashboard_race_review_summary AS
            SELECT
                date,
                COUNT(*) AS reviewed_rows,
                SUM(CASE WHEN selection_type = 'official' THEN 1 ELSE 0 END) AS official_rows,
                SUM(CASE WHEN selection_type = 'official' AND won = 1 THEN 1 ELSE 0 END) AS official_wins,
                SUM(CASE WHEN selection_type = 'official' AND placed = 1 THEN 1 ELSE 0 END) AS official_places,
                SUM(CASE WHEN selection_type = 'official' AND result = 'LOST' THEN 1 ELSE 0 END) AS official_losses,
                SUM(CASE WHEN selection_type = 'official' THEN COALESCE(head_to_head_losses_today, 0) ELSE 0 END) AS official_h2h_threats,
                SUM(CASE WHEN selection_type != 'official' AND placed = 1 THEN 1 ELSE 0 END) AS non_official_places
            FROM combined_learning
            GROUP BY date;
            """
        )

        challenger_payload = read_json(CHALLENGER_SUMMARY, {})
        conn.execute("DROP TABLE IF EXISTS challenger_performance_summary")
        conn.execute(
            """
            CREATE TABLE challenger_performance_summary (
                id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                days_tested INTEGER,
                settled_days INTEGER,
                picks_tested INTEGER,
                trial_return REAL,
                paper_profit REAL,
                delta_vs_live_profit REAL,
                plain_summary TEXT,
                updated_at TEXT
            )
            """
        )
        challengers = challenger_payload.get("pre_race_challengers") or challenger_payload.get("challengers") or []
        for challenger in challengers:
            if not isinstance(challenger, dict):
                continue
            conn.execute(
                """
                INSERT OR REPLACE INTO challenger_performance_summary
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    challenger.get("id", ""),
                    challenger.get("name", ""),
                    challenger.get("promotion_status") or challenger.get("status") or "",
                    int(challenger.get("days_tested") or challenger.get("daysTested") or 0),
                    int(challenger.get("settled_days") or challenger.get("settledDays") or 0),
                    int(challenger.get("picks_tested") or challenger.get("picksTested") or 0),
                    float(challenger.get("total_return") or challenger.get("trial_return") or challenger.get("trialReturn") or 0),
                    float(challenger.get("total_profit") or challenger.get("paper_profit") or challenger.get("paperProfit") or 0),
                    float(challenger.get("delta_vs_live_profit") or challenger.get("deltaVsLiveProfit") or 0),
                    challenger.get("plain_summary") or challenger.get("plainSummary") or "",
                    iso_now(),
                ),
            )

        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_horse_profile_key ON horse_profile_summary (horse_key);
            CREATE INDEX IF NOT EXISTS idx_h2h_field_pair ON h2h_field_summary (winner_key, loser_key);
            CREATE INDEX IF NOT EXISTS idx_h2h_field_loser ON h2h_field_summary (loser_key);
            CREATE INDEX IF NOT EXISTS idx_form_pattern_summary_pattern ON form_pattern_summary (pattern_length, pattern);
            CREATE INDEX IF NOT EXISTS idx_class_summary_movement ON class_movement_summary (class_movement, race_class_level);
            CREATE INDEX IF NOT EXISTS idx_course_distance_summary_course ON course_distance_summary (course, distance_band);
            CREATE INDEX IF NOT EXISTS idx_dashboard_review_date ON dashboard_race_review_summary (date);
            """
        )

        table_counts = {}
        for table in (
            "horse_profile_summary",
            "h2h_field_summary",
            "form_pattern_summary",
            "class_movement_summary",
            "course_distance_summary",
            "dashboard_race_review_summary",
            "challenger_performance_summary",
        ):
            table_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        conn.execute("DROP TABLE IF EXISTS summary_build_status")
        conn.execute(
            """
            CREATE TABLE summary_build_status (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        status_rows = {
            "built_at": iso_now(),
            "as_of_date": as_of_date,
            "source": "combined_learning + signal75_history + form_history",
            "analysis_only": "true",
            "scoring_impact": "none",
            "table_counts": json.dumps(table_counts, sort_keys=True),
        }
        conn.executemany(
            "INSERT OR REPLACE INTO summary_build_status VALUES (?, ?)",
            list(status_rows.items()),
        )
        conn.commit()
        return table_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fast Signal 75 SQLite summary tables.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--skip-indexes", action="store_true")
    args = parser.parse_args()

    if not args.skip_indexes:
        print("Adding SQLite indexes where missing...")
        add_indexes()

    print("Building summary tables...")
    counts = rebuild_combined_summaries(args.date)
    for table, count in counts.items():
        print(f"{table}: {count:,}")
    print(f"Database: {COMBINED_DB.relative_to(REPO)}")
    print("Scoring impact: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
