import csv
import importlib.util
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "atomic_intelligence_rebuild",
        ROOT / "scripts" / "build-intelligence-db.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_inputs(module, tmp_path: Path) -> Path:
    module.JSONL_FILES = {
        name: tmp_path / f"{name}.jsonl"
        for name in ("race_memory", "head_to_head", "historic_rivals", "horse_history")
    }
    module.PROFILE_FILES = {}
    csv_path = tmp_path / "engine.csv"
    fields = [
        "market_id", "market_type", "betfair_runner_id", "horse_name", "cloth_number",
        "bsp", "status", "sort_priority", "venue", "race_time", "race_name",
        "race_type", "race_subtype", "distance_furlongs", "runner_count",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "market_id": "1.1", "market_type": "WIN", "betfair_runner_id": "1",
                "horse_name": "Example Horse", "bsp": "5.0", "status": "WINNER",
                "venue": "Ripon", "race_time": "2026-08-01T14:00:00Z",
                "race_name": "Test", "race_type": "Flat", "race_subtype": "Handicap",
                "distance_furlongs": "8", "runner_count": "10",
            }
        )
    return csv_path


def test_rebuild_swaps_only_after_staged_database_is_valid(tmp_path):
    module = load_module()
    csv_path = seed_inputs(module, tmp_path)
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE old_marker (value TEXT)")
        connection.execute("INSERT INTO old_marker VALUES ('preserved')")

    counts = module.build_database(database, csv_path)

    assert counts["historical_runners"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM historical_runners").fetchone()[0] == 1
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with sqlite3.connect(tmp_path / "history.sqlite.previous") as connection:
        assert connection.execute("SELECT value FROM old_marker").fetchone()[0] == "preserved"
    assert not list(tmp_path.glob(".*.building*"))


def test_failed_rebuild_does_not_replace_live_database(tmp_path):
    module = load_module()
    seed_inputs(module, tmp_path)
    database = tmp_path / "history.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('still-live')")

    try:
        module.build_database(database, tmp_path / "missing.csv")
    except SystemExit:
        pass
    else:
        raise AssertionError("missing source CSV should fail the staged rebuild")

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "still-live"
    assert not list(tmp_path.glob(".*.building*"))


def test_learning_only_sync_preserves_historical_runner_table(tmp_path):
    module = load_module()
    csv_path = seed_inputs(module, tmp_path)
    database = tmp_path / "history.sqlite"
    module.build_database(database, csv_path)
    module.JSONL_FILES["race_memory"].write_text(
        json.dumps(
            {
                "id": "2026-09-01|1.1|EXAMPLEHORSE",
                "date": "2026-09-01",
                "market_id": "1.1",
                "horse_name": "Example Horse",
                "normalised_name": "EXAMPLEHORSE",
                "finishing_position": 2,
                "known_result": "PLACED",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    counts = module.sync_learning_tables(database)

    assert counts["race_memory"] == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM historical_runners").fetchone()[0] == 1
        assert connection.execute(
            "SELECT finishing_position FROM race_memory WHERE date = '2026-09-01'"
        ).fetchone()[0] == 2
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
