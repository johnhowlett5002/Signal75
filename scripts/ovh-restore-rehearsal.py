#!/usr/bin/env python3
"""Rehearse restoring an unpromoted OVH database candidate in isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CANDIDATE_RE = re.compile(r"^candidate-shadow-\d{8}-\d{6}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_counts(connection: sqlite3.Connection, expected: dict[str, int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in expected:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError(f"unsafe table name in manifest: {table}")
        counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    return counts


def verify_restored_database(restored: Path, details: dict[str, Any]) -> dict[str, Any]:
    expected_hash = str(details["sha256"])
    restored_hash = sha256(restored)
    if restored_hash != expected_hash:
        raise RuntimeError(f"restored hash mismatch for {restored.name}")

    connection = sqlite3.connect(restored)
    try:
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"SQLite quick_check failed for {restored.name}: {quick_check}")
        expected_counts = {key: int(value) for key, value in details["table_counts"].items()}
        actual_counts = table_counts(connection, expected_counts)
        if actual_counts != expected_counts:
            raise RuntimeError(f"table count mismatch for {restored.name}")

        connection.execute("CREATE TABLE __signal75_restore_probe (value TEXT NOT NULL)")
        connection.execute("INSERT INTO __signal75_restore_probe VALUES ('writable')")
        probe = connection.execute("SELECT value FROM __signal75_restore_probe").fetchone()[0]
        connection.execute("DROP TABLE __signal75_restore_probe")
        connection.commit()
        if probe != "writable":
            raise RuntimeError(f"write probe failed for {restored.name}")
        final_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if final_check != "ok":
            raise RuntimeError(f"post-write quick_check failed for {restored.name}: {final_check}")
    finally:
        connection.close()

    return {
        "filename": restored.name,
        "source_sha256": expected_hash,
        "restored_sha256_before_write_probe": restored_hash,
        "quick_check": "ok",
        "write_probe": "ok",
        "table_counts": actual_counts,
    }


def rehearse(candidate_dir: Path, state_root: Path) -> Path:
    if not CANDIDATE_RE.fullmatch(candidate_dir.name):
        raise ValueError(f"unsafe candidate id: {candidate_dir.name}")
    manifest_path = candidate_dir / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("candidate_id") != candidate_dir.name or manifest.get("promoted") is not False:
        raise RuntimeError("restore rehearsal requires an unpromoted candidate")
    databases = manifest.get("databases")
    if not isinstance(databases, dict) or not databases:
        raise RuntimeError("candidate manifest contains no databases")

    state_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_path = state_root / f"restore-rehearsal-{stamp}.json"
    report: dict[str, Any] = {
        "candidate_id": candidate_dir.name,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": "isolated-disposable-restore-rehearsal",
        "source_modified": False,
        "databases": {},
    }

    with tempfile.TemporaryDirectory(prefix=f".{stamp}-", dir=state_root) as temporary:
        stage = Path(temporary)
        for name, details in databases.items():
            source = Path(details["snapshot_path"])
            source_hash_before = sha256(source)
            if source_hash_before != details["sha256"]:
                raise RuntimeError(f"source hash mismatch before restore for {name}")
            restored = stage / source.name
            shutil.copy2(source, restored)
            restored.chmod(0o600)
            result = verify_restored_database(restored, details)
            source_hash_after = sha256(source)
            if source_hash_after != source_hash_before:
                raise RuntimeError(f"source changed during restore rehearsal for {name}")
            result["source_unchanged"] = True
            report["databases"][name] = result

    report["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["status"] = "ok"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    report_path.chmod(0o440)
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-root", type=Path, default=Path("/srv/signal75/candidates"))
    parser.add_argument("--state-root", type=Path, default=Path("/srv/signal75/state/restore-tests"))
    args = parser.parse_args()
    report = rehearse(args.candidate_root / args.candidate_id, args.state_root)
    print(f"OVH isolated restore rehearsal passed: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
