import importlib.util
import json
import sqlite3
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-ovh-readonly-health.py"
SPEC = importlib.util.spec_from_file_location("check_ovh_readonly_health", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_sqlite_check_accepts_valid_readonly_database(tmp_path):
    database = tmp_path / "test.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE sample (value INTEGER)")
        conn.execute("INSERT INTO sample VALUES (1)")

    ok, detail = MODULE.sqlite_check(database)

    assert ok is True
    assert detail == "ok"


def test_health_report_fails_closed_for_missing_resources(tmp_path, monkeypatch):
    monkeypatch.setattr(MODULE, "active_signal75_timers", lambda: [])
    report = MODULE.check_health(
        tmp_path / "missing-preview",
        tmp_path / "missing-candidate.json",
        "http://127.0.0.1:1/",
        tmp_path,
        0,
    )

    assert report["status"] == "failed"
    assert "preview_release" in report["failedChecks"]
    assert "preview_http" in report["failedChecks"]
    assert "candidate_manifest" in report["failedChecks"]


def test_candidate_must_remain_unpromoted(tmp_path, monkeypatch):
    database = tmp_path / "candidate.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE sample (value INTEGER)")
    manifest = tmp_path / "candidate-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "role": "ovh-read-only-unpromoted-database-candidate",
                "promoted": True,
                "databases": {"sample": {"snapshot_path": str(database)}},
            }
        )
    )
    monkeypatch.setattr(MODULE, "active_signal75_timers", lambda: [])

    report = MODULE.check_health(
        tmp_path / "missing-preview",
        manifest,
        "http://127.0.0.1:1/",
        tmp_path,
        0,
    )

    assert "candidate_role" in report["failedChecks"]
    sqlite_result = next(item for item in report["checks"] if item["name"] == "sqlite_sample")
    assert sqlite_result["ok"] is True
