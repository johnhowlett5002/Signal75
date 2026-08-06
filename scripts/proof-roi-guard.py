#!/usr/bin/env python3
"""
Signal 75 proof ROI guard.

This is a read/record guard around performance.json. It does not score horses,
settle results, or change picks. It checks that the published ROI can be traced
back to the daily proof files and writes a dated snapshot for audit.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PERFORMANCE_FILE = REPO / "performance.json"
DATA_DIR = REPO / "data"
SNAPSHOT_DIR = DATA_DIR / "proof_snapshots"


def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def pct(value):
    try:
        return round(float(value or 0), 1)
    except Exception:
        return 0.0


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def current_proof_summary(performance):
    return {
        "bettingDays": int(performance.get("bettingDays") or 0),
        "totalStaked": money(performance.get("totalStaked")),
        "totalReturn": money(performance.get("totalReturn")),
        "totalProfit": money(performance.get("totalProfit")),
        "roi": pct(performance.get("roi")),
        "updatedAt": performance.get("updatedAt"),
        "generatedAt": performance.get("generatedAt"),
    }


def latest_snapshot_for(today):
    if not SNAPSHOT_DIR.exists():
        return None
    snapshots = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not snapshots:
        return None

    today_path = SNAPSHOT_DIR / f"{today}.json"
    if today_path.exists():
        return load_json(today_path)

    previous = [p for p in snapshots if p.stem < today]
    if not previous:
        return None
    return load_json(previous[-1])


def check_performance_math(current):
    expected_profit = round(current["totalReturn"] - current["totalStaked"], 2)
    expected_roi = round((expected_profit / current["totalStaked"]) * 100, 1) if current["totalStaked"] else 0.0
    errors = []

    if abs(expected_profit - current["totalProfit"]) > 0.02:
        errors.append(
            "performance.json profit mismatch: return - stake = "
            f"{expected_profit}, stored profit = {current['totalProfit']}"
        )

    if abs(expected_roi - current["roi"]) > 0.6:
        errors.append(
            f"performance.json ROI mismatch: calculated {expected_roi}%, "
            f"stored {current['roi']}%"
        )

    return {
        "status": "ERROR" if errors else "OK",
        "expectedProfit": expected_profit,
        "expectedRoi": expected_roi,
        "errors": errors,
    }


def check_daily_return_undercounts():
    undercounts = []
    for path in sorted(DATA_DIR.glob("2026-*.json")):
        try:
            day = load_json(path)
        except Exception as exc:
            undercounts.append({
                "file": path.name,
                "error": f"Could not read JSON: {exc}",
            })
            continue

        results = day.get("results") or {}
        if results.get("complete") is not True:
            continue

        total_return = money(results.get("totalReturn"))
        patent_return = money(results.get("patentReturn"))
        if patent_return > total_return + 0.02:
            undercounts.append({
                "file": path.name,
                "date": day.get("date") or path.stem,
                "totalReturn": total_return,
                "patentReturn": patent_return,
                "difference": round(patent_return - total_return, 2),
            })

    return undercounts


def build_report(args):
    if not PERFORMANCE_FILE.exists():
        return {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "status": "ERROR",
            "errors": ["performance.json is missing"],
            "warnings": [],
        }

    performance = load_json(PERFORMANCE_FILE)
    today = datetime.now(timezone.utc).date().isoformat()
    current = current_proof_summary(performance)
    previous = latest_snapshot_for(today)
    previous_current = (previous or {}).get("current") or {}
    previous_roi = previous_current.get("roi")
    roi_change = None
    warnings = []
    errors = []

    if previous_roi is not None:
        roi_change = round(current["roi"] - pct(previous_roi), 1)
        if abs(roi_change) > args.threshold and not args.allow_large_move:
            warnings.append(
                "ROI moved by more than the guard threshold: "
                f"{pct(previous_roi)}% -> {current['roi']}% "
                f"({roi_change:+.1f} pts)"
            )

    performance_math = check_performance_math(current)
    errors.extend(performance_math["errors"])

    daily_undercounts = check_daily_return_undercounts()
    if daily_undercounts:
        errors.append(
            f"{len(daily_undercounts)} settled daily result file(s) undercount patentReturn"
        )

    status = "ERROR" if errors else "WARNING" if warnings else "OK"
    return {
        "date": today,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reason": args.reason,
        "threshold_roi_points": args.threshold,
        "current": current,
        "previous_snapshot": {
            "date": (previous or {}).get("date"),
            "roi": previous_roi,
            "totalProfit": previous_current.get("totalProfit"),
            "bettingDays": previous_current.get("bettingDays"),
        } if previous else None,
        "roi_change_points": roi_change,
        "checks": {
            "performance_math": performance_math,
            "daily_return_undercounts": daily_undercounts,
        },
        "warnings": warnings,
        "errors": errors,
        "proof_guard": True,
    }


def write_snapshot(report):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{report['date']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return path


def print_report(report, wrote_path=None):
    current = report.get("current") or {}
    print("Signal 75 proof ROI guard")
    print(f"Status: {report.get('status')}")
    print(
        "Current proof: "
        f"{current.get('bettingDays')} betting days, "
        f"stake GBP {current.get('totalStaked')}, "
        f"return GBP {current.get('totalReturn')}, "
        f"profit GBP {current.get('totalProfit')}, "
        f"ROI {current.get('roi')}%"
    )
    previous = report.get("previous_snapshot")
    if previous:
        print(
            "Previous snapshot: "
            f"{previous.get('date')} ROI {previous.get('roi')}%"
        )
        print(f"ROI movement: {report.get('roi_change_points'):+.1f} pts")
    else:
        print("Previous snapshot: none")

    for warning in report.get("warnings") or []:
        print(f"WARNING: {warning}")
    for error in report.get("errors") or []:
        print(f"ERROR: {error}")
    if wrote_path:
        print(f"Snapshot written: {wrote_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reason", default="manual proof check")
    parser.add_argument("--threshold", type=float, default=2.0)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--allow-large-move", action="store_true")
    args = parser.parse_args()

    report = build_report(args)
    wrote_path = None
    if not args.check_only:
        wrote_path = write_snapshot(report)
    print_report(report, wrote_path)

    if report.get("status") == "ERROR":
        return 2
    if report.get("status") == "WARNING":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
