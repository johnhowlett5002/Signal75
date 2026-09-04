#!/usr/bin/env python3
"""Record a failed OVH scheduler stage without touching proof data."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


SAFE_UNIT = re.compile(r"^[A-Za-z0-9_.@-]+$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("/srv/signal75/state/scheduler-failures"))
    args = parser.parse_args()
    if not SAFE_UNIT.fullmatch(args.unit):
        raise SystemExit("unsafe unit name")
    args.output_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "unit": args.unit,
        "failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "failed",
    }
    path = args.output_root / f"{args.unit}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.chmod(0o640)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
