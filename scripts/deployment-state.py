#!/usr/bin/env python3
"""Capture and compare Signal 75 Mac/OVH deployment state.

The manifest deliberately contains hashes and operational metadata only. It
never reads or stores API keys, passwords, environment values, or credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
CODE_DIRS = ("scripts", "tests", "dashboard", "docs", "assets", "deploy", ".github")
CODE_FILES = (
    "app.js",
    "index.html",
    "about.html",
    "contact.html",
    "faq.html",
    "how-it-works.html",
    "CNAME",
    "mailerlite.py",
)
CODE_EXCLUDED_PARTS = {
    ".DS_Store",
    ".pytest_cache",
    "__pycache__",
    "data",
    "test-output",
}
ARTIFACT_FILES = (
    "picks.json",
    "performance.json",
    "dashboard/data/dashboard_ready.json",
    "dashboard/data/officialPicks.json",
    "dashboard/data/performance.json",
    "dashboard/data/dashboardIntel.json",
)
DATABASES = {
    "signal75_history": {
        "path": "data/horse_intelligence/signal75_history.sqlite",
        "tables": ("historical_runners", "race_memory", "head_to_head", "historic_rivals", "horse_history"),
        "dated_tables": {"race_memory": "date", "head_to_head": "date"},
    },
    "form_history": {
        "path": "data/horse_intelligence/form_history.sqlite",
        "tables": ("form_results", "racecards", "betfair_prices", "performance_figures"),
        "dated_tables": {"form_results": "date", "racecards": "date", "betfair_prices": "date"},
    },
    "combined_learning": {
        "path": "data/combined_learning/signal75_learning.sqlite",
        "tables": (
            "combined_learning",
            "horse_profile_summary",
            "h2h_field_summary",
            "form_pattern_summary",
            "challenger_performance_summary",
            "dashboard_race_review_summary",
        ),
        "dated_tables": {},
    },
}
PACKAGE_NAMES = ("anthropic", "betfairlightweight", "pytest")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(command: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=False,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def deployable_code_files(root: Path) -> Iterable[Path]:
    for directory in CODE_DIRS:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(root)
            if any(part in CODE_EXCLUDED_PARTS for part in relative.parts):
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            yield path
    for name in CODE_FILES:
        path = root / name
        if path.is_file() and not path.is_symlink():
            yield path


def code_state(root: Path) -> Dict[str, Any]:
    files: Dict[str, str] = {}
    total_bytes = 0
    for path in sorted(set(deployable_code_files(root))):
        relative = path.relative_to(root).as_posix()
        files[relative] = sha256_file(path)
        total_bytes += path.stat().st_size

    aggregate = hashlib.sha256()
    for relative, digest in sorted(files.items()):
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")

    git = {"available": False, "commit": None, "branch": None, "dirty": None, "changed_files": []}
    if (root / ".git").exists() and shutil.which("git"):
        commit = run(["git", "rev-parse", "HEAD"], root)
        branch = run(["git", "branch", "--show-current"], root)
        status = run(["git", "status", "--porcelain"], root)
        changed = [line[3:] for line in status.stdout.splitlines() if len(line) > 3]
        git = {
            "available": commit.returncode == 0,
            "commit": commit.stdout.strip() or None,
            "branch": branch.stdout.strip() or None,
            "dirty": bool(changed),
            "changed_files": changed,
        }

    return {
        "aggregate_sha256": aggregate.hexdigest(),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
        "git": git,
    }


def sqlite_schema_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT type, name, COALESCE(sql, '') FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
    ).fetchall()
    encoded = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sqlite_state(root: Path, spec: Dict[str, Any]) -> Dict[str, Any]:
    link_path = root / str(spec["path"])
    if not link_path.exists():
        return {"path": str(spec["path"]), "present": False}

    resolved = link_path.resolve()
    result: Dict[str, Any] = {
        "path": str(spec["path"]),
        "resolved_path": str(resolved),
        "present": True,
        "size_bytes": resolved.stat().st_size,
        "mode": oct(resolved.stat().st_mode & 0o777),
        "sha256": sha256_file(resolved),
        "snapshot_id": None,
        "schema_sha256": None,
        "table_counts": {},
        "latest_dates": {},
        "latest_date": None,
        "error": None,
    }
    parts = resolved.parts
    if "snapshots" in parts:
        index = parts.index("snapshots")
        if index + 1 < len(parts):
            result["snapshot_id"] = parts[index + 1]

    try:
        query = "mode=ro&immutable=1" if not os.access(resolved, os.W_OK) else "mode=ro"
        conn = sqlite3.connect(f"{resolved.as_uri()}?{query}", uri=True)
        conn.execute("PRAGMA query_only = ON")
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        result["schema_sha256"] = sqlite_schema_hash(conn)
        for table in spec.get("tables", ()):
            result["table_counts"][table] = (
                int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                if table in tables
                else None
            )
        dates: List[str] = []
        for table, column in spec.get("dated_tables", {}).items():
            if table not in tables:
                result["latest_dates"][table] = None
                continue
            value = conn.execute(f'SELECT MAX("{column}") FROM "{table}"').fetchone()[0]
            text = str(value) if value else None
            result["latest_dates"][table] = text
            if text:
                dates.append(text)
        result["latest_date"] = max(dates) if dates else None
        conn.close()
    except sqlite3.Error as exc:
        result["error"] = str(exc)
    return result


def artifact_state(root: Path) -> Dict[str, Any]:
    artifacts: Dict[str, Any] = {}
    for relative in ARTIFACT_FILES:
        path = root / relative
        if not path.is_file():
            artifacts[relative] = {"present": False}
            continue
        artifacts[relative] = {
            "present": True,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
        }
    return artifacts


def schedule_state() -> Dict[str, Any]:
    cron = run(["crontab", "-l"]) if shutil.which("crontab") else None
    cron_lines = []
    if cron and cron.returncode == 0:
        cron_lines = [line for line in cron.stdout.splitlines() if line.strip() and not line.lstrip().startswith("#")]

    launch_agents: List[str] = []
    launch_agent_hashes: Dict[str, str] = {}
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    if launch_dir.exists():
        launch_paths = sorted(launch_dir.glob("*signal75*.plist"))
        launch_agents = [path.name for path in launch_paths]
        launch_agent_hashes = {path.name: sha256_file(path) for path in launch_paths if path.is_file()}

    wrapper_hashes = {
        path.name: sha256_file(path)
        for path in sorted(Path.home().glob("signal75*.sh"))
        if path.is_file()
    }

    systemd_lines: List[str] = []
    if shutil.which("systemctl"):
        timers = run(["systemctl", "list-timers", "--all", "--no-legend"])
        if timers.returncode == 0:
            systemd_lines = [line.strip() for line in timers.stdout.splitlines() if "signal75" in line.lower()]

    return {
        "cron_entry_hashes": [hashlib.sha256(line.encode("utf-8")).hexdigest() for line in cron_lines],
        "launch_agents": launch_agents,
        "launch_agent_hashes": launch_agent_hashes,
        "wrapper_hashes": wrapper_hashes,
        "systemd_timers": systemd_lines,
        "active_signal75_schedule_count": len(cron_lines) + len(launch_agents) + len(systemd_lines),
    }


def environment_state() -> Dict[str, Any]:
    packages = {}
    for name in PACKAGE_NAMES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "executable": sys.executable,
        "packages": packages,
    }


def capture(root: Path, role: str) -> Dict[str, Any]:
    root = root.resolve()
    return {
        "schema_version": SCHEMA_VERSION,
        "deployment_id": datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "generated_at": now_iso(),
        "role": role,
        "root": str(root),
        "environment": environment_state(),
        "code": code_state(root),
        "databases": {name: sqlite_state(root, spec) for name, spec in DATABASES.items()},
        "artifacts": artifact_state(root),
        "schedules": schedule_state(),
    }


def load_manifest(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported deployment manifest: {path}")
    return payload


def file_differences(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, List[str]]:
    left_files = left.get("code", {}).get("files", {})
    right_files = right.get("code", {}).get("files", {})
    left_names = set(left_files)
    right_names = set(right_files)
    return {
        "changed": sorted(name for name in left_names & right_names if left_files[name] != right_files[name]),
        "mac_only": sorted(left_names - right_names),
        "ovh_only": sorted(right_names - left_names),
    }


def compare(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    file_diff = file_differences(left, right)
    code_match = left.get("code", {}).get("aggregate_sha256") == right.get("code", {}).get("aggregate_sha256")
    databases: Dict[str, Any] = {}
    for name in sorted(set(left.get("databases", {})) | set(right.get("databases", {}))):
        mac = left.get("databases", {}).get(name, {})
        ovh = right.get("databases", {}).get(name, {})
        if not mac.get("present") or not ovh.get("present"):
            status = "MISSING"
        elif mac.get("sha256") == ovh.get("sha256"):
            status = "MATCH"
        elif (
            mac.get("schema_sha256") == ovh.get("schema_sha256")
            and mac.get("table_counts") == ovh.get("table_counts")
            and mac.get("latest_dates") == ovh.get("latest_dates")
        ):
            status = "SUMMARY_MATCH_BINARY_DIFFERENT"
        elif mac.get("latest_date") and ovh.get("latest_date"):
            if mac["latest_date"] > ovh["latest_date"]:
                status = "MAC_NEWER"
            elif ovh["latest_date"] > mac["latest_date"]:
                status = "OVH_NEWER"
            else:
                status = "DIFFERENT_SAME_DATE"
        else:
            status = "DIFFERENT"
        databases[name] = {
            "status": status,
            "mac_latest_date": mac.get("latest_date"),
            "ovh_latest_date": ovh.get("latest_date"),
            "mac_snapshot": mac.get("snapshot_id"),
            "ovh_snapshot": ovh.get("snapshot_id"),
            "row_counts_match": mac.get("table_counts") == ovh.get("table_counts"),
        }

    artifacts = {}
    for name in sorted(set(left.get("artifacts", {})) | set(right.get("artifacts", {}))):
        mac = left.get("artifacts", {}).get(name, {})
        ovh = right.get("artifacts", {}).get(name, {})
        if not mac.get("present") and not ovh.get("present"):
            artifacts[name] = "BOTH_MISSING"
        elif not mac.get("present"):
            artifacts[name] = "MAC_MISSING"
        elif not ovh.get("present"):
            artifacts[name] = "OVH_MISSING"
        elif mac.get("sha256") == ovh.get("sha256"):
            artifacts[name] = "MATCH"
        else:
            artifacts[name] = "DIFFERENT"

    return {
        "compared_at": now_iso(),
        "mac_role": left.get("role"),
        "ovh_role": right.get("role"),
        "code": {
            "status": "MATCH" if code_match else "DIFFERENT",
            **file_diff,
        },
        "databases": databases,
        "artifacts": artifacts,
        "schedules": {
            "mac_active": left.get("schedules", {}).get("active_signal75_schedule_count", 0),
            "ovh_active": right.get("schedules", {}).get("active_signal75_schedule_count", 0),
        },
    }


def print_comparison(payload: Dict[str, Any]) -> None:
    print("SIGNAL 75 MAC / OVH DEPLOYMENT STATE")
    print(f"Compared: {payload['compared_at']}")
    print(f"Roles: Mac={payload.get('mac_role')} | OVH={payload.get('ovh_role')}")
    print(f"CODE: {payload['code']['status']}")
    for label in ("changed", "mac_only", "ovh_only"):
        values = payload["code"].get(label, [])
        if values:
            print(f"  {label.replace('_', ' ').title()} ({len(values)}): {', '.join(values[:12])}")
            if len(values) > 12:
                print(f"  ... and {len(values) - 12} more")
    print("DATABASES:")
    for name, state in payload["databases"].items():
        dates = f"Mac {state.get('mac_latest_date') or '-'} | OVH {state.get('ovh_latest_date') or '-'}"
        print(f"  {name}: {state['status']} ({dates}; row counts match={state['row_counts_match']})")
    artifact_values = list(payload["artifacts"].values())
    matched = sum(value == "MATCH" for value in artifact_values)
    comparable = sum(value != "BOTH_MISSING" for value in artifact_values)
    both_missing = sum(value == "BOTH_MISSING" for value in artifact_values)
    suffix = f", {both_missing} absent on both" if both_missing else ""
    print(f"DASHBOARD ARTIFACTS: {matched}/{comparable} MATCH{suffix}")
    for name, status in payload["artifacts"].items():
        if status not in {"MATCH", "BOTH_MISSING"}:
            print(f"  {name}: {status}")
    schedules = payload["schedules"]
    print(f"SCHEDULES: Mac {schedules['mac_active']} active | OVH {schedules['ovh_active']} active")


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or compare Signal 75 deployment state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture", help="Create a deployment manifest.")
    capture_parser.add_argument("--root", type=Path, default=REPO_ROOT)
    capture_parser.add_argument("--role", required=True)
    capture_parser.add_argument("--output", type=Path, required=True)
    capture_parser.add_argument("--history-dir", type=Path)

    compare_parser = subparsers.add_parser("compare", help="Compare Mac and OVH manifests.")
    compare_parser.add_argument("mac_manifest", type=Path)
    compare_parser.add_argument("ovh_manifest", type=Path)
    compare_parser.add_argument("--output", type=Path)
    compare_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    if args.command == "capture":
        payload = capture(args.root, args.role)
        atomic_write_json(args.output, payload)
        if args.history_dir:
            history_path = args.history_dir / f"{payload['deployment_id']}-{args.role}.json"
            atomic_write_json(history_path, payload)
        print(f"Deployment state captured: {args.output}")
        return 0

    left = load_manifest(args.mac_manifest)
    right = load_manifest(args.ovh_manifest)
    payload = compare(left, right)
    if args.output:
        atomic_write_json(args.output, payload)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_comparison(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
