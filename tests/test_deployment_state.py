import importlib.util
import json
import sqlite3
from pathlib import Path

from conftest_helpers import REPO_ROOT


def load_module():
    path = REPO_ROOT / "scripts" / "deployment-state.py"
    spec = importlib.util.spec_from_file_location("deployment_state", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def create_db(path: Path, table: str, date_value: str = "2026-08-30") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE {table} (date TEXT, value INTEGER)")
    conn.execute(f"INSERT INTO {table} VALUES (?, ?)", (date_value, 1))
    conn.commit()
    conn.close()


def test_code_state_excludes_generated_dashboard_data_and_cache(tmp_path):
    module = load_module()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "example.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "scripts" / "__pycache__").mkdir()
    (tmp_path / "scripts" / "__pycache__" / "example.pyc").write_bytes(b"cache")
    (tmp_path / "dashboard" / "data").mkdir(parents=True)
    (tmp_path / "dashboard" / "data" / "generated.json").write_text("{}", encoding="utf-8")

    state = module.code_state(tmp_path)

    assert list(state["files"]) == ["scripts/example.py"]
    assert state["file_count"] == 1


def test_sqlite_state_is_read_only_metadata(tmp_path):
    module = load_module()
    path = tmp_path / "data" / "sample.sqlite"
    create_db(path, "runs")
    spec = {"path": "data/sample.sqlite", "tables": ("runs",), "dated_tables": {"runs": "date"}}

    state = module.sqlite_state(tmp_path, spec)

    assert state["present"] is True
    assert state["table_counts"] == {"runs": 1}
    assert state["latest_date"] == "2026-08-30"
    assert len(state["sha256"]) == 64
    assert state["error"] is None


def test_sqlite_state_reads_read_only_wal_snapshot_without_sidecars(tmp_path):
    module = load_module()
    path = tmp_path / "data" / "wal-snapshot.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE runs (date TEXT, value INTEGER)")
        conn.execute("INSERT INTO runs VALUES ('2026-08-31', 1)")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    path.with_name(path.name + "-wal").unlink(missing_ok=True)
    path.with_name(path.name + "-shm").unlink(missing_ok=True)
    path.chmod(0o440)
    spec = {"path": "data/wal-snapshot.sqlite", "tables": ("runs",), "dated_tables": {"runs": "date"}}

    state = module.sqlite_state(tmp_path, spec)

    assert state["error"] is None
    assert state["table_counts"] == {"runs": 1}
    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def test_compare_reports_exact_code_and_database_differences():
    module = load_module()
    mac = {
        "schema_version": 1,
        "role": "mac-primary",
        "code": {"aggregate_sha256": "mac", "files": {"same.py": "1", "changed.py": "2", "mac.py": "3"}},
        "databases": {"history": {"present": True, "sha256": "new", "schema_sha256": "schema", "latest_date": "2026-08-31", "latest_dates": {"runs": "2026-08-31"}, "table_counts": {"runs": 2}}},
        "artifacts": {"picks.json": {"present": True, "sha256": "a"}},
        "schedules": {"active_signal75_schedule_count": 2},
    }
    ovh = {
        "schema_version": 1,
        "role": "ovh-read-only-test",
        "code": {"aggregate_sha256": "ovh", "files": {"same.py": "1", "changed.py": "9", "ovh.py": "4"}},
        "databases": {"history": {"present": True, "sha256": "old", "schema_sha256": "schema", "latest_date": "2026-08-30", "latest_dates": {"runs": "2026-08-30"}, "table_counts": {"runs": 1}}},
        "artifacts": {"picks.json": {"present": True, "sha256": "b"}},
        "schedules": {"active_signal75_schedule_count": 0},
    }

    result = module.compare(mac, ovh)

    assert result["code"]["status"] == "DIFFERENT"
    assert result["code"]["changed"] == ["changed.py"]
    assert result["code"]["mac_only"] == ["mac.py"]
    assert result["code"]["ovh_only"] == ["ovh.py"]
    assert result["databases"]["history"]["status"] == "MAC_NEWER"
    assert result["schedules"] == {"mac_active": 2, "ovh_active": 0}


def test_compare_distinguishes_sqlite_backup_layout_from_logical_drift():
    module = load_module()
    common = {
        "schema_version": 1,
        "code": {"aggregate_sha256": "same", "files": {}},
        "artifacts": {"optional.json": {"present": False}},
        "schedules": {"active_signal75_schedule_count": 0},
    }
    mac = {
        **common,
        "role": "mac-primary",
        "databases": {"history": {"present": True, "sha256": "source-layout", "schema_sha256": "schema", "latest_date": "2026-08-30", "latest_dates": {"runs": "2026-08-30"}, "table_counts": {"runs": 10}}},
    }
    ovh = {
        **common,
        "role": "ovh-read-only-test",
        "databases": {"history": {"present": True, "sha256": "backup-layout", "schema_sha256": "schema", "latest_date": "2026-08-30", "latest_dates": {"runs": "2026-08-30"}, "table_counts": {"runs": 10}}},
    }

    result = module.compare(mac, ovh)

    assert result["databases"]["history"]["status"] == "SUMMARY_MATCH_BINARY_DIFFERENT"
    assert result["artifacts"]["optional.json"] == "BOTH_MISSING"


def test_manifest_write_is_valid_json(tmp_path):
    module = load_module()
    output = tmp_path / "state" / "manifest.json"
    module.atomic_write_json(output, {"schema_version": 1, "value": "ok"})
    assert json.loads(output.read_text(encoding="utf-8"))["value"] == "ok"
