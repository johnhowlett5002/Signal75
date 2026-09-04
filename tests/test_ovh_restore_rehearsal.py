import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ovh-restore-rehearsal.py"
SPEC = importlib.util.spec_from_file_location("ovh_restore_rehearsal", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_restore_rehearsal_checks_copy_and_preserves_source(tmp_path):
    source = tmp_path / "source.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE results (id INTEGER PRIMARY KEY, value TEXT)")
    connection.executemany("INSERT INTO results(value) VALUES (?)", [("one",), ("two",)])
    connection.commit()
    connection.close()
    source_hash = digest(source)

    candidate = tmp_path / "candidates" / "candidate-shadow-20260901-120000"
    candidate.mkdir(parents=True)
    (candidate / "candidate-manifest.json").write_text(json.dumps({
        "candidate_id": candidate.name,
        "promoted": False,
        "databases": {
            "test": {
                "snapshot_path": str(source),
                "sha256": source_hash,
                "table_counts": {"results": 2},
            }
        },
    }))

    report_path = MODULE.rehearse(candidate, tmp_path / "restore-tests")
    report = json.loads(report_path.read_text())

    assert report["status"] == "ok"
    assert report["source_modified"] is False
    assert report["databases"]["test"]["source_unchanged"] is True
    assert report["databases"]["test"]["write_probe"] == "ok"
    assert digest(source) == source_hash
    with sqlite3.connect(source) as check:
        assert check.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 2
        assert check.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='__signal75_restore_probe'"
        ).fetchone()[0] == 0


def test_restore_rehearsal_rejects_unsafe_candidate_name(tmp_path):
    candidate = tmp_path / "candidate-live"
    candidate.mkdir()
    with pytest.raises(ValueError, match="unsafe candidate"):
        MODULE.rehearse(candidate, tmp_path / "restore-tests")


def test_restore_rehearsal_rejects_promoted_candidate(tmp_path):
    candidate = tmp_path / "candidate-shadow-20260901-120000"
    candidate.mkdir()
    (candidate / "candidate-manifest.json").write_text(json.dumps({
        "candidate_id": candidate.name,
        "promoted": True,
        "databases": {"test": {}},
    }))
    with pytest.raises(RuntimeError, match="unpromoted"):
        MODULE.rehearse(candidate, tmp_path / "restore-tests")
