import importlib.util
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "atomic_summary_rebuild",
        ROOT / "scripts" / "build-sqlite-summary-tables.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_databases(module, tmp_path: Path) -> None:
    module.COMBINED_DB = tmp_path / "learning.sqlite"
    module.LIVE_DB = tmp_path / "history.sqlite"
    module.FORM_DB = tmp_path / "form.sqlite"
    module.CHALLENGER_SUMMARY = tmp_path / "challenger_summary.json"

    with sqlite3.connect(module.COMBINED_DB) as connection:
        connection.execute(
            """
            CREATE TABLE combined_learning (
                date TEXT, market_id TEXT, horse_key TEXT, horse_name TEXT,
                selection_type TEXT, result TEXT, won INTEGER, placed INTEGER,
                signal_score REAL, pre_race_price REAL,
                head_to_head_wins_today INTEGER, head_to_head_losses_today INTEGER,
                class_movement TEXT, race_class_level INTEGER,
                course TEXT, distance_band TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO combined_learning VALUES
            ('2026-09-01', '1.1', 'EXAMPLE', 'Example', 'official', 'WON', 1, 1,
             80, 5, 1, 0, 'same_class', 3, 'Ripon', 'mile')
            """
        )
        connection.execute("CREATE TABLE old_marker (value TEXT)")
        connection.execute("INSERT INTO old_marker VALUES ('preserved')")

    with sqlite3.connect(module.LIVE_DB) as connection:
        connection.execute(
            """
            CREATE TABLE head_to_head (
                winner_key TEXT, winner TEXT, loser_key TEXT, loser TEXT,
                date TEXT, course TEXT, race_time TEXT, market_id TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO head_to_head VALUES ('EXAMPLE','Example','RIVAL','Rival','2026-08-01','Ripon','14:00','1.0')"
        )

    with sqlite3.connect(module.FORM_DB) as connection:
        connection.execute(
            """
            CREATE TABLE form_pattern_stats (
                pattern_length INTEGER, pattern TEXT, starts INTEGER,
                wins INTEGER, places INTEGER, win_rate REAL, place_rate REAL
            )
            """
        )
        connection.execute(
            "INSERT INTO form_pattern_stats VALUES (3, '123', 10, 2, 5, 0.2, 0.5)"
        )

    module.CHALLENGER_SUMMARY.write_text(
        json.dumps({"pre_race_challengers": []}), encoding="utf-8"
    )


def test_summary_rebuild_swaps_only_after_validation(tmp_path):
    module = load_module()
    seed_databases(module, tmp_path)

    counts = module.atomic_rebuild_combined_summaries("2026-09-01")

    assert counts["h2h_field_summary"] == 1
    with sqlite3.connect(module.COMBINED_DB) as connection:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT meetings_won FROM h2h_field_summary").fetchone()[0] == 1
    with sqlite3.connect(tmp_path / "learning.sqlite.previous") as connection:
        assert connection.execute("SELECT value FROM old_marker").fetchone()[0] == "preserved"
    assert not list(tmp_path.glob(".*.building"))
    assert not list(tmp_path.glob(".*.building-wal"))
    assert not list(tmp_path.glob(".*.building-shm"))

    spec = importlib.util.spec_from_file_location(
        "combined_learning_identity_audit",
        ROOT / "scripts" / "build-combined-learning.py",
    )
    combined = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(combined)
    identity_database = tmp_path / "identity.sqlite"
    with sqlite3.connect(identity_database) as connection:
        combined.create_schema(connection)
        connection.execute("DROP INDEX idx_combined_unique_date_horse_role")
        for race_time, horse_name, tips, h2h, payload in (
            ("17:15", "HARB", 0, 0, "{}"),
            ("18:15", "Harb", 7, 2, '{"complete": true}'),
        ):
            connection.execute(
                """
                INSERT INTO combined_learning (
                    date, course, race_time, market_id, horse_name, horse_key,
                    selection_type, tipster_count_live, head_to_head_wins_today,
                    payload_json
                ) VALUES ('2026-09-03', 'Newcastle', ?, '1.1', ?, 'HARB',
                          'OFFICIAL', ?, ?, ?)
                """,
                (race_time, horse_name, tips, h2h, payload),
            )
        assert combined.deduplicate_combined_learning(connection) == 1
        combined.create_schema(connection)
        assert connection.execute(
            """
            SELECT race_time, horse_name, tipster_count_live, head_to_head_wins_today
            FROM combined_learning
            """
        ).fetchone() == ("18:15", "Harb", 7, 2)
        try:
            connection.execute(
                """
                INSERT INTO combined_learning (
                    date, horse_name, horse_key, selection_type, payload_json
                ) VALUES ('2026-09-03', 'HARB', 'HARB', 'official', '{}')
                """
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate horse/date/selection identity must be rejected")


def test_failed_summary_rebuild_leaves_live_database_untouched(tmp_path):
    module = load_module()
    seed_databases(module, tmp_path)
    module.LIVE_DB = tmp_path / "missing-history.sqlite"

    try:
        module.atomic_rebuild_combined_summaries("2026-09-01")
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("missing source tables should fail the staged rebuild")

    with sqlite3.connect(module.COMBINED_DB) as connection:
        assert connection.execute("SELECT value FROM old_marker").fetchone()[0] == "preserved"
    assert not list(tmp_path.glob(".*.building"))
