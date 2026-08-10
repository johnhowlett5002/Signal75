#!/usr/bin/env python3
"""Signal 75 system integrity guard.

Exit codes:
  0 = OK
  1 = warnings only
  2 = errors; live pick generation should stop
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
INTEL = DATA / "horse_intelligence"
PICKS = REPO / "picks.json"
PERFORMANCE = REPO / "performance.json"
DASHBOARD_PERFORMANCE = REPO / "dashboard" / "data" / "performance.json"
LIVE_DB = INTEL / "signal75_history.sqlite"
FORM_DB = INTEL / "form_history.sqlite"
FRESHNESS = INTEL / "data_freshness_status.json"
MONEY_TOLERANCE = 0.02
ROI_TOLERANCE = 0.2


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def days_old(value: Any) -> int | None:
    if not value:
        return None
    try:
        return (date.today() - date.fromisoformat(str(value)[:10])).days
    except ValueError:
        return None


def sqlite_one(db_path: Path, sql: str, default: Any = None) -> Any:
    if not db_path.exists():
        return default
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("PRAGMA query_only = ON")
            return conn.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return default


def money(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def official_picks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    picks: List[Dict[str, Any]] = []
    seen_ids = set()
    for key in ("topRatedFlat", "topRatedJumps", "topRated"):
        for pick in payload.get(key, []) or []:
            if not isinstance(pick, dict):
                continue
            ident = (
                str(pick.get("name") or pick.get("horse") or "").casefold(),
                str(pick.get("course") or "").casefold(),
                str(pick.get("time") or pick.get("race_time") or ""),
            )
            if ident in seen_ids:
                continue
            seen_ids.add(ident)
            picks.append(pick)
    return picks


def check_picks(errors: List[str], warnings: List[str]) -> None:
    picks = read_json(PICKS, {})
    if not picks:
        errors.append("picks.json is missing or invalid JSON.")
        return

    pick_date = picks.get("date")
    if pick_date and pick_date != date.today().isoformat():
        warnings.append(f"picks.json date is {pick_date}, not today.")

    for pick in official_picks(picks):
        name = pick.get("name") or pick.get("horse") or "Unknown"
        try:
            odds = float(pick.get("odds") or 0)
        except (TypeError, ValueError):
            odds = 0.0
        try:
            score = float(pick.get("live_adjusted_score", pick.get("signal_score", pick.get("score") or 0)) or 0)
        except (TypeError, ValueError):
            score = 0.0
        try:
            runners = int(pick.get("runners") or pick.get("field_size") or 0)
        except (TypeError, ValueError):
            runners = 0
        if not (4.1 <= odds <= 6.0):
            errors.append(f"Official pick {name} odds {odds} outside 4.1-6.0 band.")
        if score < 75:
            errors.append(f"Official pick {name} score {score} below 75 gate.")
        if runners and runners > 14:
            errors.append(f"Official pick {name} field size {runners} above 14-runner gate.")


def check_performance(errors: List[str], warnings: List[str]) -> None:
    perf = read_json(PERFORMANCE, {})
    if not perf:
        warnings.append("performance.json is missing or invalid.")
        return
    stake = money(perf.get("totalStake", perf.get("totalStaked", 0)))
    staked_alias = money(perf.get("totalStaked", perf.get("totalStake", 0)))
    returned = money(perf.get("totalReturn", 0))
    profit = money(perf.get("totalProfit", perf.get("profit", 0)))
    roi = money(perf.get("roi", 0))
    if stake <= 0 and int(perf.get("bettingDays") or 0) > 0:
        errors.append("performance.json has betting days but total stake is zero.")
    if abs(stake - staked_alias) > MONEY_TOLERANCE:
        errors.append("performance.json totalStake and totalStaked do not match.")
    if abs(round(returned - stake, 2) - round(profit, 2)) > 0.05:
        errors.append("performance.json totalReturn - totalStake does not equal totalProfit.")
    if stake > 0:
        expected_roi = round((profit / stake) * 100, 1)
        if abs(expected_roi - roi) > ROI_TOLERANCE:
            errors.append(f"performance.json ROI {roi}% does not match stake/return maths {expected_roi}%.")


def check_dashboard_performance_export(errors: List[str], warnings: List[str]) -> None:
    source = read_json(PERFORMANCE, {})
    exported = read_json(DASHBOARD_PERFORMANCE, {})
    if not source:
        warnings.append("Cannot compare dashboard performance export because performance.json is missing.")
        return
    if not exported:
        errors.append("dashboard/data/performance.json is missing or invalid.")
        return

    numeric_fields = (
        "bettingDays",
        "profitableDays",
        "totalStake",
        "totalStaked",
        "totalReturn",
        "totalProfit",
        "roi",
        "winRate",
    )
    for field in numeric_fields:
        source_value = money(source.get(field, source.get("totalStaked") if field == "totalStake" else None))
        export_value = money(exported.get(field, exported.get("totalStaked") if field == "totalStake" else None))
        tolerance = ROI_TOLERANCE if field in ("roi", "winRate") else MONEY_TOLERANCE
        if abs(source_value - export_value) > tolerance:
            errors.append(
                f"Dashboard performance export mismatch for {field}: "
                f"source={source_value} dashboard={export_value}."
            )

    export_stake = money(exported.get("totalStake", exported.get("totalStaked", 0)))
    export_return = money(exported.get("totalReturn", 0))
    export_profit = money(exported.get("totalProfit", 0))
    export_roi = money(exported.get("roi", 0))
    if export_stake <= 0 and int(exported.get("bettingDays") or 0) > 0:
        errors.append("dashboard/data/performance.json has betting days but totalStake is zero.")
    if abs(round(export_return - export_stake, 2) - round(export_profit, 2)) > 0.05:
        errors.append("dashboard/data/performance.json return minus stake does not equal profit.")
    if export_stake > 0:
        expected_roi = round((export_profit / export_stake) * 100, 1)
        if abs(expected_roi - export_roi) > ROI_TOLERANCE:
            errors.append(
                f"dashboard/data/performance.json ROI {export_roi}% does not match "
                f"stake/return maths {expected_roi}%."
            )


def check_daily_profit_fields(errors: List[str], warnings: List[str]) -> None:
    for path in sorted(DATA.glob("2026-*.json")):
        if path.stem < "2026-05-24":
            continue
        day = read_json(path, {})
        results = day.get("results") if isinstance(day.get("results"), dict) else {}
        if not results.get("complete"):
            continue
        settled_rows = [
            row
            for section in ("flat", "jumps")
            for row in (results.get(section) or [])
            if isinstance(row, dict)
        ]
        if not settled_rows:
            stake = money(results.get("totalStake"))
            returned = money(results.get("totalReturn", results.get("patentReturn", 0)))
            profit = money(results.get("profit", results.get("totalProfit", 0)))
            if stake or returned or profit:
                errors.append(f"{path.name} complete no-selection day carries non-zero money.")
            continue
        if results.get("profit") is None:
            errors.append(f"{path.name} complete result has missing profit.")
            continue
        stake = money(results.get("totalStake"))
        returned = money(results.get("totalReturn", results.get("patentReturn", 0)))
        profit = money(results.get("profit"))
        if abs(round(returned - stake, 2) - round(profit, 2)) > 0.05:
            errors.append(f"{path.name} result profit does not equal return minus stake.")


def run_freshness_report() -> Dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "scripts/data-freshness-status.py"],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
    )
    payload = read_json(FRESHNESS, {})
    payload["_returncode"] = result.returncode
    payload["_stdout"] = (result.stdout or "")[-2000:]
    payload["_stderr"] = (result.stderr or "")[-2000:]
    return payload


def check_database_freshness(errors: List[str], warnings: List[str]) -> None:
    status = run_freshness_report()
    live = status.get("liveLearningDatabase") or {}
    form = status.get("historicalFormArchive") or {}

    if live.get("status") != "OK":
        errors.append(
            f"Central live learning DB stale/missing: latest={live.get('latestDate')} rows={live.get('headToHeadRows')}"
        )
    latest_live = live.get("latestDate")
    if days_old(latest_live) is not None and days_old(latest_live) > 3:
        errors.append(f"Central live learning DB latest date is {latest_live}.")

    if form.get("status") == "STALE":
        warnings.append(
            f"Historical rich-form archive is stale: latest={form.get('latestDate')}; source_latest={form.get('source', {}).get('sourceLatestResultDate')}."
        )
    if form.get("source", {}).get("sourceLatestResultDate") == form.get("latestDate"):
        warnings.append("No newer local rich-form archive source is available to backfill from.")


def check_v1_files(errors: List[str], warnings: List[str]) -> None:
    today = date.today().isoformat()
    daily = DATA / f"field_relative_daily_{today}.json"
    if daily.exists():
        payload = read_json(daily, {})
        for pick in payload.get("picks", []) or []:
            if not isinstance(pick, dict):
                continue
            name = pick.get("horse") or pick.get("name") or "?"
            try:
                odds = float(pick.get("odds") or 0)
            except (TypeError, ValueError):
                odds = 0.0
            if not name or name == "?":
                errors.append("V1 daily pick has no horse name.")
            if not (4.1 <= odds <= 6.0):
                errors.append(f"V1 daily pick {name} odds {odds} outside 4.1-6.0 band.")
    else:
        warnings.append("V1 daily pick file has not been generated yet.")

    cutoff = date.today() - timedelta(days=7)
    for path in sorted(DATA.glob("field_relative_archive_*_settled.json"))[-7:]:
        payload = read_json(path, {})
        for pick in payload.get("picks", payload.get("selections", [])) or []:
            if not isinstance(pick, dict):
                continue
            name = pick.get("horse") or pick.get("name") or "?"
            result = pick.get("result")
            returned = float(pick.get("return", 0) or 0)
            if not name or name == "?":
                errors.append(f"{path.name} has V1 settled pick without horse name.")
            if result not in ("WON", "PLACED", "LOST", "VOID"):
                errors.append(f"{path.name} has V1 pick {name} without settled result.")
            if result in ("WON", "PLACED") and returned <= 0:
                errors.append(f"{path.name} has V1 {result} pick {name} with zero return.")


def build_payload(check_type: str) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    if check_type != "pre_pick":
        check_picks(errors, warnings)
    check_performance(errors, warnings)
    check_dashboard_performance_export(errors, warnings)
    check_daily_profit_fields(errors, warnings)
    check_database_freshness(errors, warnings)
    if check_type != "pre_pick":
        check_v1_files(errors, warnings)

    passed = 6
    status = "ERROR" if errors else ("WARNING" if warnings else "OK")
    return {
        "date": date.today().isoformat(),
        "run_at": iso_now(),
        "check_type": check_type,
        "status": status,
        "passed": passed,
        "warnings": len(warnings),
        "errors": len(errors),
        "warning_list": warnings,
        "error_list": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Signal 75 system integrity.")
    parser.add_argument("--post-race", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    payload = build_payload("post_race" if args.post_race else "pre_pick")
    if args.output:
        write_json(Path(args.output), payload)
    else:
        write_json(DATA / f"integrity_check_{date.today().isoformat()}.json", payload)

    print(f"System integrity: {payload['status']}")
    print(f"Passed: {payload['passed']}  Warnings: {payload['warnings']}  Errors: {payload['errors']}")
    for item in payload["warning_list"]:
        print(f"WARNING: {item}")
    for item in payload["error_list"]:
        print(f"ERROR: {item}")

    return 2 if payload["errors"] else (1 if payload["warnings"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
