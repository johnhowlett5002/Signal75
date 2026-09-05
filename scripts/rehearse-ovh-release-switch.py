#!/usr/bin/env python3
"""Rehearse an atomic pre-live release switch and immediate rollback."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def replace_link(link: Path, relative_target: str) -> None:
    temporary = link.parent / f".{link.name}.new"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(relative_target)
    os.replace(temporary, link)


def rehearse(root: Path) -> dict:
    root = root.resolve()
    releases = root / "releases"
    current = root / "current"
    state = root / "state"
    if not current.is_symlink():
        raise RuntimeError("pre-live current link is missing")
    original = os.readlink(current)
    original_path = (root / original).resolve()
    if original_path.parent != releases.resolve() or not original_path.is_dir():
        raise RuntimeError("pre-live current target is outside the releases directory")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    probe = releases / f"rollback-probe-{stamp}"
    probe.mkdir(mode=0o750)
    (probe / "PROBE_ONLY").write_text("pre-live rollback rehearsal\n", encoding="utf-8")
    probe_target = str(probe.relative_to(root))
    switched = False
    restored = False
    try:
        replace_link(current, probe_target)
        switched = current.resolve() == probe.resolve()
        if not switched:
            raise RuntimeError("atomic pre-live switch did not select the probe")
        replace_link(current, original)
        restored = current.resolve() == original_path
        if not restored:
            raise RuntimeError("pre-live rollback did not restore the original release")
    finally:
        if current.resolve() != original_path:
            replace_link(current, original)
        shutil.rmtree(probe, ignore_errors=True)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "ok",
        "scope": "prelive-only",
        "original_target": original,
        "probe_switch": switched,
        "rollback": restored,
        "production_changed": False,
    }
    state.mkdir(parents=True, exist_ok=True)
    (state / "rollback-rehearsal-latest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/srv/signal75/prelive"))
    args = parser.parse_args()
    print(json.dumps(rehearse(args.root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

