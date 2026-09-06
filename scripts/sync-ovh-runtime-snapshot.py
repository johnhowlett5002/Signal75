#!/usr/bin/env python3
"""Transfer immutable, hash-verified non-SQLite runtime inputs to OVH."""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = REPO_ROOT / "data" / "deployment_state" / "runtime_uploads"
ARTIFACTS = {
    "head_to_head_master": REPO_ROOT / "data" / "horse_intelligence" / "head_to_head_master.jsonl",
    "head_to_head_profiles": REPO_ROOT / "data" / "horse_intelligence" / "head_to_head_profiles.json",
    "historic_rival_profiles": REPO_ROOT / "data" / "horse_intelligence" / "historic_rival_profiles.json",
    "field_relationship_profiles": REPO_ROOT / "data" / "horse_intelligence" / "field_relationship_profiles.json",
    "historic_rival_master": REPO_ROOT / "data" / "horse_intelligence" / "historic_rival_master.jsonl",
    "race_result_notes_master": REPO_ROOT / "data" / "horse_intelligence" / "race_result_notes_master.jsonl",
    "race_result_note_profiles": REPO_ROOT / "data" / "horse_intelligence" / "race_result_note_profiles.json",
    "result_notes_seed": REPO_ROOT / "data" / "horse_intelligence" / "result_notes_seed.json",
    "betfair_engine_csv": REPO_ROOT / "engine" / "betfair_uk_races_full_v2.csv",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_details(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)
    return {
        "source": str(path.relative_to(REPO_ROOT)),
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def transfer(snapshot_id: str, remote_host: str, remote_root: str) -> Path:
    local_dir = STATE_ROOT / snapshot_id
    local_dir.mkdir(parents=True, exist_ok=False)
    manifest = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": "ovh-unpromoted-read-only-runtime-snapshot",
        "artifacts": {name: artifact_details(path) for name, path in ARTIFACTS.items()},
    }
    manifest_path = local_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    remote_stage = f"{remote_root}/.{snapshot_id}.upload"
    remote_release = f"{remote_root}/{snapshot_id}"
    run(["ssh", remote_host, f"install -d -m 0750 {shlex.quote(remote_stage)}"])
    run(
        [
            "rsync",
            "-a",
            "--partial",
            str(manifest_path),
            *(str(path) for path in ARTIFACTS.values()),
            f"{remote_host}:{remote_stage}/",
        ]
    )
    for details in manifest["artifacts"].values():
        remote_file = f"{remote_stage}/{details['filename']}"
        verify = (
            f"test -s {shlex.quote(remote_file)} && "
            f"test \"$(sha256sum {shlex.quote(remote_file)} | cut -d' ' -f1)\" = "
            f"{shlex.quote(str(details['sha256']))}"
        )
        run(["ssh", remote_host, verify])
    finalise = (
        f"test ! -e {shlex.quote(remote_release)} && "
        f"mv {shlex.quote(remote_stage)} {shlex.quote(remote_release)} && "
        f"find {shlex.quote(remote_release)} -type d -exec chmod 0550 {{}} + && "
        f"find {shlex.quote(remote_release)} -type f -exec chmod 0440 {{}} +"
    )
    run(["ssh", remote_host, finalise])
    print(f"Verified OVH runtime snapshot stored without promotion: {remote_release}")
    return local_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-id", default=datetime.now(timezone.utc).strftime("runtime-input-%Y%m%d-%H%M%S"))
    parser.add_argument("--remote-host", default="signal75-vps")
    parser.add_argument("--remote-root", default="/srv/signal75/runtime-snapshots")
    args = parser.parse_args()
    transfer(args.snapshot_id, args.remote_host, args.remote_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
