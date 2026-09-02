import importlib.util
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = REPO_ROOT / "scripts" / "sync-ovh-sqlite-snapshots.py"
    spec = importlib.util.spec_from_file_location("sync_ovh_sqlite_snapshots", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_snapshot_is_consistent_read_only_copy(tmp_path):
    module = load_script()
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "snapshot.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE evidence (id INTEGER PRIMARY KEY, value TEXT)")
        conn.executemany("INSERT INTO evidence(value) VALUES (?)", [("one",), ("two",)])

    result = module.create_snapshot(source, destination)

    assert result["quick_check"] == "ok"
    assert result["table_counts"] == {"evidence": 2}
    assert result["sha256"] == module.sha256_file(destination)
    assert destination.stat().st_mode & 0o777 == 0o440
    assert not destination.with_name(destination.name + "-wal").exists()
    assert not destination.with_name(destination.name + "-shm").exists()


def test_snapshot_reuses_verified_local_copy(tmp_path):
    module = load_script()
    source = tmp_path / "source.sqlite"
    destination = tmp_path / "snapshot.sqlite"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE evidence (value TEXT)")
    module.create_snapshot(source, destination)

    result = module.create_snapshot(source, destination)

    assert result["reused_local_snapshot"] is True
