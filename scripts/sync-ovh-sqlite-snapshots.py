#!/usr/bin/env python3
"""Create and transfer verified, read-only SQLite snapshots to OVH.

This migration tool never edits the live Mac databases and never activates an
OVH database. Promotion is deliberately a separate future step.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_ROOT = REPO_ROOT / "data" / "deployment_state" / "sqlite_uploads"
DATABASES = {
    "signal75_history": REPO_ROOT / "data" / "horse_intelligence" / "signal75_history.sqlite",
    "form_history": REPO_ROOT / "data" / "horse_intelligence" / "form_history.sqlite",
    "combined_learning": REPO_ROOT / "data" / "combined_learning" / "signal75_learning.sqlite",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quick_check(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True) as conn:
        return str(conn.execute("PRAGMA quick_check").fetchone()[0])


def table_counts(path: Path) -> Dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True) as conn:
        tables = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]) for name in tables}


def create_snapshot(source: Path, destination: Path) -> Dict[str, Any]:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and quick_check(destination) == "ok":
        reused = True
    else:
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(destination) as snapshot_db:
                source_db.backup(snapshot_db, pages=8192)
        reused = False
    if quick_check(destination) != "ok":
        raise RuntimeError(f"SQLite quick_check failed for {destination}")
    destination.chmod(0o440)
    try:
        source_label = str(source.relative_to(REPO_ROOT))
    except ValueError:
        source_label = str(source)
    return {
        "source": source_label,
        "filename": destination.name,
        "size_bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
        "quick_check": "ok",
        "table_counts": table_counts(destination),
        "reused_local_snapshot": reused,
    }


def checked_run(command: Iterable[str]) -> None:
    subprocess.run(list(command), check=True)


def transfer(snapshot_id: str, names: Iterable[str], remote_host: str, remote_root: str) -> Path:
    local_dir = UPLOAD_ROOT / snapshot_id
    local_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": "ovh-unpromoted-read-only-snapshot",
        "databases": {},
    }
    for name in names:
        source = DATABASES[name]
        destination = local_dir / source.name
        print(f"Creating consistent snapshot: {name}", flush=True)
        manifest["databases"][name] = create_snapshot(source, destination)

    manifest_path = local_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    remote_stage = f"{remote_root}/.{snapshot_id}.upload"
    remote_release = f"{remote_root}/{snapshot_id}"
    checked_run(["ssh", remote_host, f"install -d -m 0750 {shlex.quote(remote_stage)}"])
    upload_files = [manifest_path] + [local_dir / str(item["filename"]) for item in manifest["databases"].values()]
    checked_run(
        ["rsync", "-a", "--partial", *(str(path) for path in upload_files), f"{remote_host}:{remote_stage}/"]
    )

    for details in manifest["databases"].values():
        filename = str(details["filename"])
        expected_hash = str(details["sha256"])
        remote_file = f"{remote_stage}/{filename}"
        verify = (
            f"test \"$(sha256sum {shlex.quote(remote_file)} | cut -d' ' -f1)\" = {shlex.quote(expected_hash)} "
            f"&& test \"$(sqlite3 {shlex.quote(f'file:{remote_file}?immutable=1')} 'PRAGMA quick_check;')\" = ok"
        )
        checked_run(["ssh", remote_host, verify])

    finalise = (
        f"test ! -e {shlex.quote(remote_release)} && "
        f"mv {shlex.quote(remote_stage)} {shlex.quote(remote_release)} && "
        f"find {shlex.quote(remote_release)} -type d -exec chmod 0550 {{}} + && "
        f"find {shlex.quote(remote_release)} -type f -exec chmod 0440 {{}} +"
    )
    checked_run(["ssh", remote_host, finalise])
    print(f"Verified OVH snapshot stored without promotion: {remote_release}")
    return local_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Transfer verified read-only SQLite snapshots to OVH.")
    parser.add_argument("--database", action="append", choices=sorted(DATABASES), required=True)
    parser.add_argument("--snapshot-id", default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--remote-host", default="signal75-vps")
    parser.add_argument("--remote-root", default="/srv/signal75/snapshots")
    args = parser.parse_args()
    transfer(args.snapshot_id, dict.fromkeys(args.database), args.remote_host, args.remote_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
