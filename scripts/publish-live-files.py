#!/usr/bin/env python3
"""
Publish Signal 75 public files from a clean main worktree.

The daily Mac pipeline can run on a working branch with local dashboard or
analysis changes. This publisher avoids that state completely: it creates a
temporary worktree from origin/main, copies only approved public files from the
local repo, commits those files, and pushes HEAD to main.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path


DEFAULT_REPO = Path("/Users/johnhowlett/Signal75")


def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def read_json(path):
    with path.open() as f:
        return json.load(f)


def optional_paths(kind, race_date):
    common = [
        "data/public_scorecards/latest_scorecard.json",
        f"data/public_scorecards/scorecard_{race_date}.json",
        f"data/public_scorecards/scorecard_{race_date}.txt",
    ]
    if kind == "picks":
        return common + [
            "performance.json",
            "data/today_runners.json",
            f"data/race_comparison_{race_date}.json",
            f"data/consensus_overlay_{race_date}.json",
            f"data/consensus_shadow_{race_date}.json",
            f"data/script_tipster_overlay_{race_date}.json",
            f"data/memory_overlay_{race_date}.json",
            f"data/pick_quality_audit_{race_date}.json",
            f"data/selection_diagnostics/selection_diagnostics_{race_date}.json",
            f"data/selection_diagnostics/selection_diagnostics_{race_date}.txt",
            f"picks_backup_{race_date}.json",
        ]
    return common + [
        "performance.json",
        f"data/{race_date}.json",
        f"data/consensus_shadow_{race_date}.json",
        f"data/late_value_shadow_{race_date}.json",
    ]


def validate_source(source_repo, kind, race_date):
    picks_path = source_repo / "picks.json"
    if not picks_path.exists():
        raise RuntimeError("picks.json is missing")

    picks = read_json(picks_path)
    if picks.get("date") != race_date:
        raise RuntimeError(f"picks.json date is {picks.get('date')!r}, expected {race_date!r}")

    if kind == "results" and not (source_repo / "performance.json").exists():
        raise RuntimeError("performance.json is missing")


def copy_public_files(source_repo, target_repo, paths):
    copied = []
    for rel in paths:
        src = source_repo / rel
        if not src.exists():
            continue
        dst = target_repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    return copied


def publish(args):
    source_repo = Path(args.source_repo).resolve()
    race_date = args.date
    validate_source(source_repo, args.kind, race_date)

    paths = ["picks.json"] + optional_paths(args.kind, race_date)

    with tempfile.TemporaryDirectory(prefix="signal75-live-publish-") as tmp:
        worktree = Path(tmp) / "main"
        run(["git", "-C", str(source_repo), "fetch", "origin", "main", "--quiet"])
        run(["git", "-C", str(source_repo), "worktree", "add", "--detach", str(worktree), "origin/main", "--quiet"])
        try:
            copied = copy_public_files(source_repo, worktree, paths)
            if not copied:
                raise RuntimeError("No public files were copied")

            run(["git", "add", "--"] + copied, cwd=worktree)
            staged = run(["git", "diff", "--cached", "--name-only"], cwd=worktree).stdout.splitlines()
            if not staged:
                print("No live publish changes to commit")
                return 0

            blocked = [p for p in staged if p.startswith("data/horse_intelligence/") or p.startswith("dashboard/")]
            if blocked:
                raise RuntimeError("Blocked unsafe publish paths: " + ", ".join(blocked))

            print("Publishing live files:")
            for path in staged:
                print(f"  {path}")

            run(["git", "commit", "--no-verify", "-m", args.message], cwd=worktree)
            push = run(["git", "push", "origin", "HEAD:main"], cwd=worktree, check=False)
            if push.returncode != 0:
                print("First push failed; fetching main and retrying once")
                run(["git", "fetch", "origin", "main", "--quiet"], cwd=worktree)
                run(["git", "rebase", "origin/main"], cwd=worktree)
                run(["git", "push", "origin", "HEAD:main"], cwd=worktree)
            print("Live publish pushed to main")
            return 0
        finally:
            run(["git", "-C", str(source_repo), "worktree", "remove", "--force", str(worktree)], check=False)


def main():
    parser = argparse.ArgumentParser(description="Publish Signal 75 public files from a clean main worktree.")
    parser.add_argument("--kind", choices=["picks", "results"], required=True)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--source-repo", default=str(DEFAULT_REPO))
    parser.add_argument("--message", default=None)
    args = parser.parse_args()
    if args.message is None:
        label = "Generate picks" if args.kind == "picks" else "Results and performance update"
        args.message = f"{label} {args.date}"
    try:
        return publish(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
