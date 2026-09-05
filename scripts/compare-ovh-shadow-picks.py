#!/usr/bin/env python3
"""Compare Mac official picks with an OVH test-mode real-feed output."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


MAX_GENERATION_GAP_MINUTES = 20


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def horse_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def selections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for discipline in ("flat", "jumps"):
        for race in payload.get(discipline, []) or []:
            horse = (race.get("horses") or [{}])[0]
            rows.append(
                {
                    "horse": horse.get("name"),
                    "horseKey": horse_key(horse.get("name")),
                    "discipline": discipline,
                    "course": race.get("course"),
                    "time": race.get("time"),
                    "odds": horse.get("odds"),
                    "score": horse.get("signal_score", horse.get("score")),
                }
            )
    return rows


def parse_generated_at(payload: dict[str, Any]) -> datetime | None:
    value = payload.get("generatedAt")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def comparability_reasons(
    mac: dict[str, Any],
    ovh: dict[str, Any],
    report: dict[str, Any],
    *,
    require_time_proximity: bool = True,
) -> list[str]:
    reasons = []
    if mac.get("date") != ovh.get("date"):
        reasons.append("pick dates differ")
    if report.get("status") != "ok":
        reasons.append(f"OVH trial status is {report.get('status') or 'missing'}")
    if not report.get("markets"):
        reasons.append("OVH trial had no markets")
    if require_time_proximity:
        mac_time = parse_generated_at(mac)
        ovh_time = parse_generated_at(ovh)
        if not mac_time or not ovh_time:
            reasons.append("generation time is missing or invalid")
        else:
            gap_minutes = abs((ovh_time - mac_time).total_seconds()) / 60
            if gap_minutes > MAX_GENERATION_GAP_MINUTES:
                reasons.append(
                    f"generation times differ by {gap_minutes:.1f} minutes; maximum is {MAX_GENERATION_GAP_MINUTES}"
                )
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Mac and OVH shadow picks.")
    parser.add_argument("--mac-picks", type=Path, required=True)
    parser.add_argument("--ovh-picks", type=Path, required=True)
    parser.add_argument("--ovh-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--identical-input",
        action="store_true",
        help="Compare the exact Mac input without applying the live-feed time-gap guard.",
    )
    args = parser.parse_args()

    mac = read_json(args.mac_picks)
    ovh = read_json(args.ovh_picks)
    report = read_json(args.ovh_report)
    mac_rows = selections(mac)
    ovh_rows = selections(ovh)
    mac_keys = [row["horseKey"] for row in mac_rows]
    ovh_keys = [row["horseKey"] for row in ovh_rows]
    not_comparable_reasons = comparability_reasons(
        mac,
        ovh,
        report,
        require_time_proximity=not args.identical_input,
    )
    comparable = not not_comparable_reasons
    status = "match" if comparable and mac_keys == ovh_keys else ("different" if comparable else "not_comparable")
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "comparisonMode": "identical_frozen_input" if args.identical_input else "independent_live_feed",
        "status": status,
        "comparable": comparable,
        "notComparableReasons": not_comparable_reasons,
        "macDate": mac.get("date"),
        "ovhDate": ovh.get("date"),
        "ovhTrialStatus": report.get("status"),
        "proofFilesUnchanged": report.get("proofFilesUnchanged"),
        "macSelections": mac_rows,
        "ovhSelections": ovh_rows,
        "sameSelectionsInOrder": comparable and mac_keys == ovh_keys,
        "macOnly": [row for row in mac_rows if row["horseKey"] not in set(ovh_keys)],
        "ovhOnly": [row for row in ovh_rows if row["horseKey"] not in set(mac_keys)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
