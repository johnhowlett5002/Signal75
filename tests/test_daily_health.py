import os
import sqlite3
from datetime import date, datetime, timedelta

import pytest

from conftest_helpers import REPO_ROOT, load_json, today_str

DAILY = os.environ.get("SIGNAL75_DAILY_HEALTH") == "1"
skip_if_not_daily = pytest.mark.skipif(
    not DAILY,
    reason="Daily health check - set SIGNAL75_DAILY_HEALTH=1",
)


@skip_if_not_daily
def test_picks_json_is_from_today():
    picks = load_json("picks.json")
    assert picks.get("date") == today_str(), (
        f"picks.json date is {picks.get('date')}, expected {today_str()}"
    )


@skip_if_not_daily
def test_todays_race_data_file_exists():
    path = REPO_ROOT / "data" / f"{today_str()}.json"
    assert path.exists(), f"Today's race data file missing: data/{today_str()}.json"


@skip_if_not_daily
def test_morning_pipeline_outputs_all_exist():
    today = today_str()
    required = [
        f"data/{today}.json",
        "data/today_runners.json",
        f"data/script_tipster_overlay_{today}.json",
        f"data/consensus_overlay_{today}.json",
        f"data/race_comparison_{today}.json",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    assert not missing, f"Morning pipeline outputs missing: {missing}"


@skip_if_not_daily
def test_todays_files_were_created_today():
    today_file = REPO_ROOT / "data" / f"{today_str()}.json"
    if not today_file.exists():
        pytest.skip("Today's file not yet generated")

    mtime = datetime.fromtimestamp(today_file.stat().st_mtime)
    assert mtime.date() == date.today(), (
        f"data/{today_str()}.json was not created today"
    )


@skip_if_not_daily
def test_field_graph_is_from_today():
    path = REPO_ROOT / f"data/horse_intelligence/field_graph_{today_str()}.json"
    assert path.exists(), "Today's field graph not generated"

    data = load_json(f"data/horse_intelligence/field_graph_{today_str()}.json")
    assert data.get("date") == today_str()
    edge_count = data.get("edgeCount", 0)
    assert edge_count > 15000, (
        f"Field graph has only {edge_count} edges - "
        f"SQLite query may not be working correctly. "
        f"Expected 25,000+ on a normal racing day."
    )


@skip_if_not_daily
def test_field_graph_generated_before_challenger_lab():
    today = today_str()
    field_graph = REPO_ROOT / f"data/horse_intelligence/field_graph_{today}.json"
    challenger = REPO_ROOT / f"data/challenger_lab/challenger_{today}.json"

    if not field_graph.exists() or not challenger.exists():
        pytest.skip("One or both files not yet generated today")

    assert field_graph.stat().st_mtime < challenger.stat().st_mtime, (
        "Pipeline ordering bug: challenger lab generated BEFORE field graph on " + today
    )


@skip_if_not_daily
def test_sqlite_has_expected_records():
    db_path = REPO_ROOT / "data/horse_intelligence/signal75_history.sqlite"
    assert db_path.exists(), "SQLite database not found"

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    count = conn.execute("SELECT COUNT(*) FROM head_to_head").fetchone()[0]
    conn.close()

    assert count > 200000, (
        f"head_to_head has only {count:,} rows - SQLite memory may be incomplete"
    )


@skip_if_not_daily
def test_sqlite_row_count_has_not_dropped_significantly():
    """
    INCIDENT GUARD: The SQLite head-to-head store is rebuilt
    from the current historical JSONL source. This catches
    bad rebuilds that lose the expected 200k+ deduplicated relationships
    or stop including recent settled racing.
    """
    db_path = REPO_ROOT / "data/horse_intelligence/signal75_history.sqlite"
    assert db_path.exists(), "SQLite database not found"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA query_only = ON")
    count, latest_date = conn.execute(
        "SELECT COUNT(*), MAX(date) FROM head_to_head"
    ).fetchone()
    conn.close()
    assert count > 200000, (
        f"CRITICAL: head_to_head has only {count:,} rows. "
        f"Expected 200k+ after duplicate removal. The nightly rebuild may have "
        f"damaged the SQLite memory source. "
        f"Check build-intelligence-db.py and "
        f"self-learning-update.py immediately. "
        f"Restore from backups/ if needed."
    )
    recent_cutoff = (date.today() - timedelta(days=7)).isoformat()
    assert latest_date and latest_date >= recent_cutoff, (
        f"CRITICAL: latest head_to_head date is {latest_date}. "
        f"Expected data from {recent_cutoff} or later."
    )


@skip_if_not_daily
def test_sqlite_indexes_present():
    db_path = REPO_ROOT / "data/horse_intelligence/signal75_history.sqlite"
    conn = sqlite3.connect(str(db_path))
    indexes = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type='index' AND tbl_name='head_to_head'
        """
    ).fetchall()
    conn.close()

    names = [row[0] for row in indexes]
    assert "idx_h2h_winner" in names
    assert "idx_h2h_loser" in names
    assert "idx_h2h_date" in names


@skip_if_not_daily
def test_dashboard_field_graph_is_current():
    path = REPO_ROOT / "dashboard/data/fieldGraph.json"
    assert path.exists(), "Dashboard fieldGraph.json missing"

    data = load_json("dashboard/data/fieldGraph.json")
    assert data.get("date") == today_str(), (
        f"Dashboard field graph is from {data.get('date')}, not today"
    )


@skip_if_not_daily
def test_nightly_learning_outputs_exist():
    required = [
        "data/continuous_training/cumulative_findings.json",
        "data/continuous_training/pattern_alerts.json",
        "data/challenger_lab/challenger_summary.json",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    assert not missing, f"Nightly learning outputs missing: {missing}"
