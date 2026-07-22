import importlib.util
import sqlite3

from conftest_helpers import REPO_ROOT


def load_importer():
    module_path = REPO_ROOT / "scripts" / "import-form-history-archive.py"
    spec = importlib.util.spec_from_file_location("import_form_history_archive", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_fractional_odds_are_converted_to_decimal():
    importer = load_importer()

    assert importer.parse_fractional_odds("5/1") == 6.0
    assert importer.parse_fractional_odds("9/5F") == 2.8
    assert importer.parse_fractional_odds("100/30") == 4.3333


def test_form_history_schema_has_separate_research_tables(tmp_path):
    importer = load_importer()
    db_path = tmp_path / "form_history.sqlite"

    conn = sqlite3.connect(str(db_path))
    importer.create_schema(conn)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert "form_results" in tables
    assert "racecards" in tables
    assert "betfair_prices" in tables
    assert "form_pattern_stats" in tables
