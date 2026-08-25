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
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path


DEFAULT_REPO = Path("/Users/johnhowlett/Signal75")
PUBLIC_SITE = "https://signal75.co.uk"


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

    if kind == "picks":
        race_comparison_path = source_repo / f"data/race_comparison_{race_date}.json"
        if not race_comparison_path.exists():
            raise RuntimeError(
                f"data/race_comparison_{race_date}.json is missing; "
                "refusing to publish picks without the View All Runners feed"
            )
        race_comparison = read_json(race_comparison_path)
        if race_comparison.get("date") != race_date:
            raise RuntimeError(
                f"race comparison date is {race_comparison.get('date')!r}, expected {race_date!r}"
            )
        if not race_comparison.get("races"):
            raise RuntimeError(f"data/race_comparison_{race_date}.json has no races")

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


def verify_public_race_comparison(race_date, attempts=18, delay_seconds=10):
    rel = f"data/race_comparison_{race_date}.json"
    url = f"{PUBLIC_SITE}/{rel}?verify={datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=12) as response:
                status = getattr(response, "status", None)
                body = response.read()
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            payload = json.loads(body.decode("utf-8"))
            if payload.get("date") != race_date:
                raise RuntimeError(f"date {payload.get('date')!r} does not match {race_date!r}")
            race_count = len(payload.get("races") or [])
            if race_count <= 0:
                raise RuntimeError("0 races in public race comparison")
            print(f"Public race comparison verified: {rel} ({race_count} races)")
            return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts:
                print(
                    f"Public race comparison not ready yet "
                    f"({attempt}/{attempts}): {exc}. Retrying..."
                )
                time.sleep(delay_seconds)

    raise RuntimeError(
        f"Public race comparison failed verification after {attempts} attempts: {last_error}"
    )


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
            if args.kind == "picks" and f"data/race_comparison_{race_date}.json" not in copied:
                raise RuntimeError(
                    f"data/race_comparison_{race_date}.json was not copied; "
                    "refusing to publish incomplete runner data"
                )

            run(["git", "add", "--"] + copied, cwd=worktree)
            staged = run(["git", "diff", "--cached", "--name-only"], cwd=worktree).stdout.splitlines()
            if not staged:
                print("No live publish changes to commit")
                if args.kind == "picks":
                    verify_public_race_comparison(race_date)
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
            if args.kind == "picks":
                verify_public_race_comparison(race_date)
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
