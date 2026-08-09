import importlib.util
import json
import sqlite3

import pytest

from conftest_helpers import REPO_ROOT


def load_store():
    module_path = REPO_ROOT / "scripts" / "signal75_intelligence_store.py"
    spec = importlib.util.spec_from_file_location("signal75_intelligence_store", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_live_database_is_declared_central_source():
    store = load_store()

    assert store.LIVE_DB.name == "signal75_history.sqlite"
    assert store.FORM_ARCHIVE_DB.name == "form_history.sqlite"
    assert store.LIVE_DB != store.FORM_ARCHIVE_DB


def test_race_memory_contract_contains_rich_selection_fields():
    store = load_store()

    required = store.LIVE_REQUIRED_RACE_MEMORY_COLUMNS
    for field in [
        "class_movement",
        "class_movement_steps",
        "carried_weight_lbs",
        "draw_bucket",
        "official_rating",
        "trainer",
        "jockey",
        "form",
        "field_size",
        "finishing_position",
    ]:
        assert field in required


def test_form_archive_requires_explicit_stale_opt_in(monkeypatch, tmp_path):
    store = load_store()

    form_db = tmp_path / "form_history.sqlite"
    conn = sqlite3.connect(str(form_db))
    conn.execute("CREATE TABLE form_results (date TEXT)")
    conn.close()

    status = {
        "historicalFormArchive": {
            "status": "STALE",
            "latestDate": "2026-06-03",
        }
    }
    status_file = tmp_path / "data_freshness_status.json"
    status_file.write_text(json.dumps(status), encoding="utf-8")

    monkeypatch.setattr(store, "FORM_ARCHIVE_DB", form_db)
    monkeypatch.setattr(store, "FRESHNESS_STATUS", status_file)

    with pytest.raises(store.IntelligenceStoreError):
        store.connect_form_archive()

    conn = store.connect_form_archive(allow_stale=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM form_results").fetchone()[0] == 0
    finally:
        conn.close()

