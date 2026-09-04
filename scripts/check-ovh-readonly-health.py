#!/usr/bin/env python3
"""Check the OVH read-only migration environment without running Signal 75."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_TIMER = "ovh-readonly-health.timer"


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: str) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def sqlite_check(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"missing: {path}"
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True, timeout=10) as conn:
            result = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        return result == "ok", result
    except (OSError, sqlite3.Error) as exc:
        return False, str(exc)


def active_signal75_timers() -> list[str]:
    try:
        result = subprocess.run(
            ["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    timers: list[str] = []
    for line in result.stdout.splitlines():
        for field in line.split():
            if field.endswith(".timer") and "signal75" in field.lower():
                timers.append(field)
                break
    return sorted(set(timers))


def check_health(
    preview: Path,
    candidate_manifest: Path,
    url: str,
    disk_path: Path,
    minimum_free_gb: float,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    resolved_preview = preview.resolve(strict=False)
    preview_ok = preview.is_symlink() and resolved_preview.is_dir() and (resolved_preview / "index.html").is_file()
    add_check(checks, "preview_release", preview_ok, str(resolved_preview))

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            status = int(response.status)
            body = response.read(256)
        add_check(checks, "preview_http", status == 200 and b"<html" in body.lower(), f"HTTP {status}")
    except Exception as exc:  # urllib exposes several transport exception types.
        add_check(checks, "preview_http", False, str(exc))

    try:
        manifest = json.loads(candidate_manifest.read_text(encoding="utf-8"))
        add_check(
            checks,
            "candidate_role",
            manifest.get("role") == "ovh-read-only-unpromoted-database-candidate"
            and manifest.get("promoted") is False,
            str(manifest.get("role")),
        )
        for name, details in sorted(manifest.get("databases", {}).items()):
            ok, detail = sqlite_check(Path(str(details.get("snapshot_path", ""))))
            add_check(checks, f"sqlite_{name}", ok, detail)
    except (OSError, ValueError, TypeError) as exc:
        add_check(checks, "candidate_manifest", False, str(exc))

    usage = shutil.disk_usage(disk_path)
    free_gb = usage.free / (1024**3)
    add_check(checks, "disk_space", free_gb >= minimum_free_gb, f"{free_gb:.1f} GiB free")

    unexpected_timers = [timer for timer in active_signal75_timers() if timer != ALLOWED_TIMER]
    add_check(
        checks,
        "no_live_signal75_timers",
        not unexpected_timers,
        ", ".join(unexpected_timers) if unexpected_timers else "none",
    )

    failed = [item["name"] for item in checks if not item["ok"]]
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "role": "ovh-read-only-health",
        "status": "healthy" if not failed else "failed",
        "failedChecks": failed,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, default=Path("/var/www/signal75-preview-current"))
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=Path("/srv/signal75/candidates/candidate-20260831-verified/candidate-manifest.json"),
    )
    parser.add_argument("--url", default="http://127.0.0.1:8750/")
    parser.add_argument("--disk-path", type=Path, default=Path("/"))
    parser.add_argument("--minimum-free-gb", type=float, default=10.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = check_health(
        args.preview,
        args.candidate_manifest,
        args.url,
        args.disk_path,
        args.minimum_free_gb,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0 if report["status"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
