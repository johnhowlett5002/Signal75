#!/usr/bin/env python3
"""
Restore a Signal 75 safety snapshot.

This is intentionally explicit: pass a snapshot id and --confirm. Before
restoring, it creates a pre-restore snapshot so the current state can be recovered.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = REPO / "data" / "safety_snapshots"


def list_snapshots():
    if not SNAPSHOT_ROOT.exists():
        print("No safety snapshots found.")
        return
    snapshots = sorted([p for p in SNAPSHOT_ROOT.iterdir() if p.is_dir()])
    if not snapshots:
        print("No safety snapshots found.")
        return
    for snap in snapshots:
        manifest = snap / "manifest.json"
        label = snap.name
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                label += f"  {data.get('created_at', '')}"
            except Exception:
                pass
        print(label)


def create_pre_restore_snapshot():
    script = REPO / "scripts" / "snapshot-safe-state.py"
    result = subprocess.run(["python3", str(script)], cwd=REPO, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Could not create pre-restore snapshot")
    print(result.stdout.strip())


def restore(snapshot_id):
    snapshot_dir = SNAPSHOT_ROOT / snapshot_id
    manifest_path = snapshot_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")

    manifest = json.loads(manifest_path.read_text())
    copied = manifest.get("copied", [])
    if not copied:
        raise RuntimeError("Snapshot manifest contains no copied files")

    create_pre_restore_snapshot()

    restored = []
    for rel in copied:
        src = snapshot_dir / rel
        dst = REPO / rel
        if not src.exists():
            print(f"Skipping missing snapshot file: {rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(rel)

    restore_log = {
        "restored_snapshot": snapshot_id,
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "restored_files": restored,
    }
    with (SNAPSHOT_ROOT / f"restore_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json").open("w") as f:
        json.dump(restore_log, f, indent=2)

    print(f"Restored {len(restored)} files from snapshot {snapshot_id}")
    print("Run scripts/safety-check.py before committing or pushing.")


def main():
    parser = argparse.ArgumentParser(description="List or restore Signal 75 safety snapshots.")
    parser.add_argument("snapshot_id", nargs="?", help="Snapshot id to restore, for example 20260526T170000Z")
    parser.add_argument("--list", action="store_true", help="List available snapshots")
    parser.add_argument("--confirm", action="store_true", help="Required when restoring")
    args = parser.parse_args()

    if args.list:
        list_snapshots()
        return 0

    if not args.snapshot_id:
        parser.error("provide a snapshot_id or use --list")

    if not args.confirm:
        parser.error("restore requires --confirm")

    restore(args.snapshot_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
