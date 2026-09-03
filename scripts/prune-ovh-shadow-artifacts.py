#!/usr/bin/env python3
"""Prune only timestamped OVH shadow artifacts beyond a retention limit."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_UPLOADS = REPO_ROOT / "data" / "deployment_state" / "sqlite_uploads"
LOCAL_RUNTIME_UPLOADS = REPO_ROOT / "data" / "deployment_state" / "runtime_uploads"
CANDIDATE_RE = re.compile(r"^candidate-shadow-(\d{8}-\d{6})$")
SNAPSHOT_RE = re.compile(r"^shadow-input-(\d{8}-\d{6})$")
RUNTIME_SNAPSHOT_RE = re.compile(r"^runtime-input-(\d{8}-\d{6})$")
RUN_RE = re.compile(r"^shadow-\d{4}-\d{2}-\d{2}-real-feed-\d{6}$")


def retained_and_old(names: Iterable[str], pattern: re.Pattern[str], keep: int) -> tuple[list[str], list[str]]:
    valid = sorted(name for name in names if pattern.fullmatch(name))
    if keep < 1:
        raise ValueError("keep must be at least 1")
    return valid[-keep:], valid[:-keep]


def paired_deletions(
    candidates: Iterable[str],
    snapshots: Iterable[str],
    runtime_snapshots: Iterable[str],
    keep: int,
) -> tuple[list[str], list[str], list[str]]:
    _, old_candidates = retained_and_old(candidates, CANDIDATE_RE, keep)
    snapshot_set = set(snapshots)
    runtime_snapshot_set = set(runtime_snapshots)
    old_snapshots: list[str] = []
    old_runtime_snapshots: list[str] = []
    for candidate in old_candidates:
        match = CANDIDATE_RE.fullmatch(candidate)
        assert match
        snapshot = f"shadow-input-{match.group(1)}"
        if snapshot in snapshot_set:
            old_snapshots.append(snapshot)
        runtime_snapshot = f"runtime-input-{match.group(1)}"
        if runtime_snapshot in runtime_snapshot_set:
            old_runtime_snapshots.append(runtime_snapshot)
    return old_candidates, old_snapshots, old_runtime_snapshots


def remote_names(host: str, root: str) -> list[str]:
    command = f"find {root} -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' 2>/dev/null || true"
    result = subprocess.run(["ssh", host, command], check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def delete_remote(host: str, root: str, names: list[str], pattern: re.Pattern[str]) -> None:
    if not names:
        return
    for name in names:
        if not pattern.fullmatch(name):
            raise ValueError(f"refusing unsafe remote deletion: {name}")
    payload = json.dumps(names)
    script = (
        "import json,shutil,sys; from pathlib import Path; "
        "root=Path(sys.argv[1]).resolve(); names=json.loads(sys.argv[2]); "
        "targets=[(root/name).resolve() for name in names]; "
        "assert all(p.parent == root for p in targets); "
        "[shutil.rmtree(p) for p in targets if p.is_dir()]"
    )
    command = "python3 -c {} {} {}".format(
        shlex.quote(script),
        shlex.quote(root),
        shlex.quote(payload),
    )
    subprocess.run(["ssh", host, command], check=True)


def delete_local_uploads(names: list[str], root: Path, pattern: re.Pattern[str]) -> None:
    root = root.resolve()
    for name in names:
        if not pattern.fullmatch(name):
            raise ValueError(f"refusing unsafe local deletion: {name}")
        target = (root / name).resolve()
        if target.parent != root:
            raise ValueError(f"refusing path outside upload root: {target}")
        if target.is_dir():
            shutil.rmtree(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote-host", default="signal75-vps")
    parser.add_argument("--keep-candidates", type=int, default=5)
    parser.add_argument("--keep-runs", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    candidates = remote_names(args.remote_host, "/srv/signal75/candidates")
    snapshots = remote_names(args.remote_host, "/srv/signal75/snapshots")
    runtime_snapshots = remote_names(args.remote_host, "/srv/signal75/runtime-snapshots")
    runs = remote_names(args.remote_host, "/srv/signal75/shadow-runs")
    old_candidates, old_snapshots, old_runtime_snapshots = paired_deletions(
        candidates, snapshots, runtime_snapshots, args.keep_candidates
    )
    _, old_runs = retained_and_old(runs, RUN_RE, args.keep_runs)
    plan = {
        "candidates": old_candidates,
        "snapshots": old_snapshots,
        "runtime_snapshots": old_runtime_snapshots,
        "shadow_runs": old_runs,
        "dry_run": args.dry_run,
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if args.dry_run:
        return 0

    delete_remote(args.remote_host, "/srv/signal75/candidates", old_candidates, CANDIDATE_RE)
    delete_remote(args.remote_host, "/srv/signal75/snapshots", old_snapshots, SNAPSHOT_RE)
    delete_remote(
        args.remote_host,
        "/srv/signal75/runtime-snapshots",
        old_runtime_snapshots,
        RUNTIME_SNAPSHOT_RE,
    )
    delete_remote(args.remote_host, "/srv/signal75/shadow-runs", old_runs, RUN_RE)
    delete_local_uploads(old_snapshots, LOCAL_UPLOADS, SNAPSHOT_RE)
    delete_local_uploads(old_runtime_snapshots, LOCAL_RUNTIME_UPLOADS, RUNTIME_SNAPSHOT_RE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
