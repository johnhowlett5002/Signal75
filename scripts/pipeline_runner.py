#!/usr/bin/env python3
"""Shared runner for Signal 75 morning/nightly pipeline wrappers.

The wrappers are intentionally thin. They do not replace proven scripts; they
give the system one visible morning entry point and one visible nightly entry
point with consistent locking, logging and dry-run behaviour.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
LOG_DIR = REPO_ROOT / "logs"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def log_line(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    text = f"[{now_iso()}] {message}"
    print(text, flush=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def acquire_lock(lock_dir: Path) -> bool:
    try:
        lock_dir.mkdir()
        return True
    except FileExistsError:
        return False


def release_lock(lock_dir: Path) -> None:
    try:
        lock_dir.rmdir()
    except OSError:
        pass


def run_command(
    name: str,
    command: List[str],
    *,
    log_path: Path,
    dry_run: bool = False,
    required_files: Optional[Iterable[Path]] = None,
    allow_warning_exit: Iterable[int] = (),
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if dry_run:
        log_line(log_path, f"{name}: would run {' '.join(command)}")
        return {
            "name": name,
            "status": "would_run",
            "command": command,
        }

    missing = [str(path.relative_to(REPO_ROOT)) for path in required_files or [] if not path.exists()]
    if missing:
        log_line(log_path, f"{name}: failed, missing required file(s): {', '.join(missing)}")
        return {
            "name": name,
            "status": "failed",
            "missing": missing,
            "command": command,
        }

    log_line(log_path, f"{name}: running {' '.join(command)}")
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
        env=env or os.environ.copy(),
    )
    ok_codes = {0, *allow_warning_exit}
    status = "ok" if result.returncode == 0 else ("warning" if result.returncode in allow_warning_exit else "failed")
    if result.stdout.strip():
        log_line(log_path, f"{name}: stdout\n{result.stdout.strip()[-4000:]}")
    if result.stderr.strip():
        log_line(log_path, f"{name}: stderr\n{result.stderr.strip()[-4000:]}")
    log_line(log_path, f"{name}: {status} exit={result.returncode}")
    return {
        "name": name,
        "status": status,
        "returncode": result.returncode,
        "command": command,
        "stdoutTail": result.stdout.strip()[-4000:],
        "stderrTail": result.stderr.strip()[-4000:],
        "ok": result.returncode in ok_codes,
    }


def finish_report(
    *,
    name: str,
    date_text: str,
    started_at: str,
    steps: List[Dict[str, Any]],
    report_path: Path,
) -> int:
    failed = [step for step in steps if step.get("status") == "failed"]
    payload = {
        "name": name,
        "date": date_text,
        "startedAt": started_at,
        "finishedAt": now_iso(),
        "status": "failed" if failed else "ok",
        "failedSteps": [step.get("name") for step in failed],
        "steps": steps,
    }
    write_json(report_path, payload)
    return 1 if failed else 0


def python_cmd(script: str, *args: str) -> List[str]:
    return [sys.executable, f"scripts/{script}", *args]
