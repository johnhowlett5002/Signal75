import importlib.util
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name: str, filename: str):
    path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    scripts_dir = str(path.parent)
    added_to_path = scripts_dir not in sys.path
    if added_to_path:
        sys.path.insert(0, scripts_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        if added_to_path:
            sys.path.remove(scripts_dir)
    return module


def create_readonly_wal_snapshot(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("CREATE TABLE evidence (value INTEGER)")
        conn.execute("INSERT INTO evidence VALUES (1)")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    path.with_name(path.name + "-wal").unlink(missing_ok=True)
    path.with_name(path.name + "-shm").unlink(missing_ok=True)
    path.chmod(0o440)


def test_dashboard_export_reads_immutable_wal_snapshot(tmp_path):
    module = load_script("readonly_dashboard_export", "export-dashboard-intelligence.py")
    path = tmp_path / "summary.sqlite"
    create_readonly_wal_snapshot(path)

    with module.open_readonly_database(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def test_integrity_guard_reads_immutable_wal_snapshot(tmp_path):
    module = load_script("readonly_integrity_guard", "validate_system_integrity.py")
    path = tmp_path / "summary.sqlite"
    create_readonly_wal_snapshot(path)

    with module.open_readonly_database(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()


def test_intelligence_lookup_reads_immutable_wal_snapshot(tmp_path):
    module = load_script("readonly_intelligence_lookup", "intelligence-lookup.py")
    path = tmp_path / "summary.sqlite"
    create_readonly_wal_snapshot(path)

    with module.open_readonly_database(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    assert not path.with_name(path.name + "-wal").exists()
    assert not path.with_name(path.name + "-shm").exists()
