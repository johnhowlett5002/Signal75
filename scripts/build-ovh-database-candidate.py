#!/usr/bin/env python3
"""Assemble verified OVH snapshots into an unpromoted database candidate."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


DATABASES = {
    "combined_learning": ("signal75_learning.sqlite", "data/combined_learning/signal75_learning.sqlite"),
    "form_history": ("form_history.sqlite", "data/horse_intelligence/form_history.sqlite"),
    "signal75_history": ("signal75_history.sqlite", "data/horse_intelligence/signal75_history.sqlite"),
}
RUNTIME_ARTIFACTS = {
    "head_to_head_master": ("head_to_head_master.jsonl", "data/horse_intelligence/head_to_head_master.jsonl"),
    "head_to_head_profiles": ("head_to_head_profiles.json", "data/horse_intelligence/head_to_head_profiles.json"),
    "historic_rival_profiles": ("historic_rival_profiles.json", "data/horse_intelligence/historic_rival_profiles.json"),
    "field_relationship_profiles": ("field_relationship_profiles.json", "data/horse_intelligence/field_relationship_profiles.json"),
    "historic_rival_master": ("historic_rival_master.jsonl", "data/horse_intelligence/historic_rival_master.jsonl"),
    "race_result_notes_master": ("race_result_notes_master.jsonl", "data/horse_intelligence/race_result_notes_master.jsonl"),
    "race_result_note_profiles": ("race_result_note_profiles.json", "data/horse_intelligence/race_result_note_profiles.json"),
    "result_notes_seed": ("result_notes_seed.json", "data/horse_intelligence/result_notes_seed.json"),
    "betfair_engine_csv": ("betfair_uk_races_full_v2.csv", "engine/betfair_uk_races_full_v2.csv"),
}


def run(command: list[str], capture: bool = False) -> str:
    result = subprocess.run(command, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def remote_output(host: str, command: str) -> str:
    return run(["ssh", host, command], capture=True)


def load_remote_manifest(host: str, snapshot_root: str, snapshot_id: str) -> Dict:
    path = f"{snapshot_root}/{snapshot_id}/manifest.json"
    return json.loads(remote_output(host, f"cat {shlex.quote(path)}"))


def build_candidate(
    host: str,
    candidate_id: str,
    snapshots: Dict[str, str],
    snapshot_root: str = "/srv/signal75/snapshots",
    candidate_root: str = "/srv/signal75/candidates",
    runtime_snapshot_id: str | None = None,
    runtime_root: str = "/srv/signal75/runtime-snapshots",
) -> str:
    databases: Dict[str, Dict] = {}
    for name, snapshot_id in snapshots.items():
        manifest = load_remote_manifest(host, snapshot_root, snapshot_id)
        details = manifest.get("databases", {}).get(name)
        if not details or details.get("quick_check") != "ok":
            raise RuntimeError(f"Snapshot {snapshot_id} does not contain verified {name}")
        filename, candidate_path = DATABASES[name]
        if details.get("filename") != filename:
            raise RuntimeError(f"Unexpected filename for {name}: {details.get('filename')}")
        databases[name] = {
            "snapshot_id": snapshot_id,
            "snapshot_path": f"{snapshot_root}/{snapshot_id}/{filename}",
            "candidate_path": candidate_path,
            "sha256": details["sha256"],
            "size_bytes": details["size_bytes"],
            "table_counts": details["table_counts"],
        }

    if not runtime_snapshot_id:
        raise RuntimeError("A verified runtime snapshot is required")
    runtime_manifest = load_remote_manifest(host, runtime_root, runtime_snapshot_id)
    runtime_artifacts: Dict[str, Dict] = {}
    for name, (filename, candidate_path) in RUNTIME_ARTIFACTS.items():
        details = runtime_manifest.get("artifacts", {}).get(name)
        if not details or details.get("filename") != filename or not details.get("sha256"):
            raise RuntimeError(f"Runtime snapshot {runtime_snapshot_id} is missing verified {name}")
        runtime_artifacts[name] = {
            "snapshot_id": runtime_snapshot_id,
            "snapshot_path": f"{runtime_root}/{runtime_snapshot_id}/{filename}",
            "candidate_path": candidate_path,
            "sha256": details["sha256"],
            "size_bytes": details["size_bytes"],
        }

    payload = {
        "candidate_id": candidate_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": "ovh-read-only-unpromoted-database-candidate",
        "promoted": False,
        "databases": databases,
        "runtime_artifacts": runtime_artifacts,
    }
    stage = f"{candidate_root}/.{candidate_id}.stage"
    release = f"{candidate_root}/{candidate_id}"
    setup = (
        f"set -eu; test ! -e {shlex.quote(release)}; "
        f"install -d -m 0750 {shlex.quote(stage + '/data/horse_intelligence')} "
        f"{shlex.quote(stage + '/data/combined_learning')} {shlex.quote(stage + '/engine')}"
    )
    run(["ssh", host, setup])

    for details in databases.values():
        source = str(details["snapshot_path"])
        target = f"{stage}/{details['candidate_path']}"
        verify_and_link = (
            f"set -eu; test -r {shlex.quote(source)}; "
            f"test \"$(sha256sum {shlex.quote(source)} | cut -d' ' -f1)\" = {shlex.quote(str(details['sha256']))}; "
            f"test \"$(sqlite3 {shlex.quote(f'file:{source}?immutable=1')} 'PRAGMA quick_check;')\" = ok; "
            f"ln -s {shlex.quote(source)} {shlex.quote(target)}"
        )
        run(["ssh", host, verify_and_link])

    for details in runtime_artifacts.values():
        source = str(details["snapshot_path"])
        target = f"{stage}/{details['candidate_path']}"
        verify_and_link = (
            f"set -eu; test -s {shlex.quote(source)}; "
            f"test \"$(sha256sum {shlex.quote(source)} | cut -d' ' -f1)\" = {shlex.quote(str(details['sha256']))}; "
            f"ln -s {shlex.quote(source)} {shlex.quote(target)}"
        )
        run(["ssh", host, verify_and_link])

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        local_manifest = Path(handle.name)
    try:
        run(["scp", "-q", str(local_manifest), f"{host}:{stage}/candidate-manifest.json"])
    finally:
        local_manifest.unlink(missing_ok=True)

    finalise = (
        f"set -eu; chmod 0440 {shlex.quote(stage + '/candidate-manifest.json')}; "
        f"find {shlex.quote(stage)} -type d -exec chmod 0550 {{}} +; "
        f"mv {shlex.quote(stage)} {shlex.quote(release)}"
    )
    run(["ssh", host, finalise])
    return release


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an unpromoted OVH database candidate.")
    parser.add_argument("--combined-learning", required=True, metavar="SNAPSHOT_ID")
    parser.add_argument("--form-history", required=True, metavar="SNAPSHOT_ID")
    parser.add_argument("--signal75-history", required=True, metavar="SNAPSHOT_ID")
    parser.add_argument("--runtime-snapshot", required=True, metavar="SNAPSHOT_ID")
    parser.add_argument("--candidate-id", default=datetime.now(timezone.utc).strftime("candidate-%Y%m%d-%H%M%S"))
    parser.add_argument("--remote-host", default="signal75-vps")
    args = parser.parse_args()
    release = build_candidate(
        args.remote_host,
        args.candidate_id,
        {
            "combined_learning": args.combined_learning,
            "form_history": args.form_history,
            "signal75_history": args.signal75_history,
        },
        runtime_snapshot_id=args.runtime_snapshot,
    )
    print(f"OVH read-only database candidate built without promotion: {release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
