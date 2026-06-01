#!/usr/bin/env python3
"""
Signal 75 results consistency checker.

Read-only: compares performance.json against completed daily archives and writes
a report. It does not change picks, scoring, settlement, or performance files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from config_loader import REPO_ROOT, load_config


DATA_DIR = REPO_ROOT / "data"
PERFORMANCE_FILE = REPO_ROOT / "performance.json"
CHECK_DIR = DATA_DIR / "proof_checks"
ARCHIVE_DIR = CHECK_DIR / "archive"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
LEGACY_ARCHIVE_STAKE_EW = 0.50
MONEY_TOLERANCE = 0.02
ROI_TOLERANCE = 0.1


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def archive_existing(path: Path) -> None:
    if not path.exists():
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.move(str(path), str(ARCHIVE_DIR / f"{path.stem}_{stamp}{path.suffix}"))


def archive_files() -> Iterable[Path]:
    for path in sorted(DATA_DIR.iterdir()):
        if path.is_file() and DATE_RE.match(path.name):
            yield path


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def proof_scale(day: Dict[str, Any], stake_per_line: float) -> float:
    results = day.get("results") or {}
    source_stake = safe_float(
        results.get("stakeEW") or results.get("stakePerLine"),
        LEGACY_ARCHIVE_STAKE_EW,
    )
    if source_stake <= 0:
        source_stake = LEGACY_ARCHIVE_STAKE_EW
    return stake_per_line / source_stake


def proof_amount(day: Dict[str, Any], value: Any, stake_per_line: float) -> float:
    return round(safe_float(value) * proof_scale(day, stake_per_line), 2)


def official_races(day: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for tab in ("flat", "jumps"):
        for race in day.get(tab, []) or []:
            horses = race.get("horses") or []
            if horses and horses[0].get("name"):
                rows.append((tab, race))
    return rows


def result_rows(day: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = day.get("results") or {}
    rows: List[Dict[str, Any]] = []
    for tab in ("flat", "jumps"):
        rows.extend(results.get(tab, []) or [])
    return rows


def day_complete(day: Dict[str, Any]) -> bool:
    return (day.get("results") or {}).get("complete") is True


def has_unsettled_official_picks(day: Dict[str, Any]) -> bool:
    rows = result_rows(day)
    official_count = len(official_races(day))
    if len(rows) < official_count:
        return True
    for row in rows[:official_count]:
        if not row.get("result") or str(row.get("result")).upper() == "PENDING":
            return True
    return False


def summarise_archives(config: Dict[str, Any]) -> Dict[str, Any]:
    start_date = str(config.get("results_start_date", "2026-05-24"))
    stake_per_line = safe_float(config.get("stake_per_line"), 1.0)
    daily_stake = safe_float(config.get("daily_stake"), 14.0)
    expected_pick_count = int(config.get("official_pick_count", 3))

    completed: List[Dict[str, Any]] = []
    all_days: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for path in archive_files():
        day = load_json(path)
        day_date = str(day.get("date") or path.stem)
        if day_date < start_date:
            continue

        official_count = len(official_races(day))
        complete = day_complete(day)
        no_bet = day.get("noBetDay") is True
        mode = day.get("mode", "")

        all_days.append({
            "date": day_date,
            "mode": mode,
            "noBetDay": no_bet,
            "complete": complete,
            "officialPickCount": official_count,
            "archive": path.name,
        })

        if no_bet:
            continue

        if official_count == 0:
            warnings.append({
                "date": day_date,
                "level": "WARNING",
                "message": "No official picks found in archive, but day is not marked noBetDay.",
            })
            continue

        if official_count != expected_pick_count:
            warnings.append({
                "date": day_date,
                "level": "WARNING",
                "message": f"Official pick count is {official_count}; expected {expected_pick_count}.",
            })

        if has_unsettled_official_picks(day):
            warnings.append({
                "date": day_date,
                "level": "ERROR" if complete else "WARNING",
                "message": "One or more official picks are missing a settled result.",
            })

        if not complete:
            warnings.append({
                "date": day_date,
                "level": "WARNING",
                "message": "Archive is not marked complete, so it is excluded from totals.",
            })
            continue

        patent_return = proof_amount(day, (day.get("results") or {}).get("patentReturn", 0), stake_per_line)
        profit = round(patent_return - daily_stake, 2)
        rows = result_rows(day)
        winners = sum(1 for r in rows[:official_count] if str(r.get("result", "")).upper() == "WON")
        placed = sum(1 for r in rows[:official_count] if str(r.get("result", "")).upper() in ("WON", "PLACED"))

        completed.append({
            "date": day_date,
            "mode": mode,
            "officialPickCount": official_count,
            "stake": daily_stake,
            "return": patent_return,
            "profit": profit,
            "winners": winners,
            "placed": placed,
        })

    betting_days = len(completed)
    total_staked = round(betting_days * daily_stake, 2)
    total_return = round(sum(d["return"] for d in completed), 2)
    total_profit = round(sum(d["profit"] for d in completed), 2)
    roi = round((total_profit / total_staked) * 100, 1) if total_staked else 0.0
    profitable_days = sum(1 for d in completed if d["profit"] > 0)
    no_bet_days = sum(1 for d in all_days if d["noBetDay"])

    return {
        "startDate": start_date,
        "daysSeen": len(all_days),
        "bettingDays": betting_days,
        "noBetDays": no_bet_days,
        "profitableDays": profitable_days,
        "totalStaked": total_staked,
        "totalReturn": total_return,
        "totalProfit": total_profit,
        "roi": roi,
        "completedDays": completed,
        "dayIndex": all_days,
        "archiveWarnings": warnings,
    }


def compare_value(name: str, expected: Any, actual: Any, tolerance: float = 0.0) -> Dict[str, Any] | None:
    if isinstance(expected, float) or isinstance(actual, float):
        if abs(safe_float(expected) - safe_float(actual)) <= tolerance:
            return None
    elif expected == actual:
        return None
    return {
        "field": name,
        "expectedFromArchives": expected,
        "actualInPerformanceJson": actual,
    }


def build_report() -> Dict[str, Any]:
    config = load_config()
    performance = load_json(PERFORMANCE_FILE)
    archive_summary = summarise_archives(config)
    mismatches: List[Dict[str, Any]] = []

    checks = [
        ("bettingDays", archive_summary["bettingDays"], performance.get("bettingDays"), 0),
        ("noBetDays", archive_summary["noBetDays"], performance.get("noBetDays"), 0),
        ("profitableDays", archive_summary["profitableDays"], performance.get("profitableDays"), 0),
        ("totalStaked", archive_summary["totalStaked"], performance.get("totalStaked"), MONEY_TOLERANCE),
        ("totalReturn", archive_summary["totalReturn"], performance.get("totalReturn"), MONEY_TOLERANCE),
        ("totalProfit", archive_summary["totalProfit"], performance.get("totalProfit"), MONEY_TOLERANCE),
        ("roi", archive_summary["roi"], performance.get("roi"), ROI_TOLERANCE),
    ]
    for name, expected, actual, tolerance in checks:
        mismatch = compare_value(name, expected, actual, tolerance)
        if mismatch:
            mismatches.append(mismatch)

    errors = [w for w in archive_summary["archiveWarnings"] if w["level"] == "ERROR"]
    warnings = [w for w in archive_summary["archiveWarnings"] if w["level"] != "ERROR"]
    status = "OK"
    if warnings:
        status = "WARNING"
    if mismatches or errors:
        status = "ERROR"

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "config": {
            "proof_basis": config.get("proof_basis"),
            "stake_per_line": config.get("stake_per_line"),
            "daily_stake": config.get("daily_stake"),
            "official_pick_count": config.get("official_pick_count"),
            "results_start_date": config.get("results_start_date"),
            "live_odds_gate": [
                config.get("live_odds_gate_low"),
                config.get("live_odds_gate_high"),
            ],
            "strict_value_band_status": config.get("strict_value_band_status"),
        },
        "archiveTotals": {k: archive_summary[k] for k in (
            "startDate",
            "daysSeen",
            "bettingDays",
            "noBetDays",
            "profitableDays",
            "totalStaked",
            "totalReturn",
            "totalProfit",
            "roi",
        )},
        "performanceTotals": {
            "bettingDays": performance.get("bettingDays"),
            "noBetDays": performance.get("noBetDays"),
            "profitableDays": performance.get("profitableDays"),
            "totalStaked": performance.get("totalStaked"),
            "totalReturn": performance.get("totalReturn"),
            "totalProfit": performance.get("totalProfit"),
            "roi": performance.get("roi"),
        },
        "mismatches": mismatches,
        "warnings": warnings,
        "errors": errors,
        "completedDays": archive_summary["completedDays"],
    }


def text_report(report: Dict[str, Any]) -> str:
    totals = report["archiveTotals"]
    lines = [
        "SIGNAL 75 RESULTS CHECK",
        f"Status: {report['status']}",
        f"Generated: {report['generatedAt']}",
        "",
        "Basis:",
        f"- {report['config']['proof_basis']}",
        f"- £{report['config']['daily_stake']:.2f} total daily stake",
        f"- Results from {report['config']['results_start_date']}",
        f"- Live odds gate: {report['config']['live_odds_gate'][0]} to {report['config']['live_odds_gate'][1]}",
        "",
        "Archive totals:",
        f"- Betting days: {totals['bettingDays']}",
        f"- No-bet days: {totals['noBetDays']}",
        f"- Profitable days: {totals['profitableDays']}",
        f"- Staked: £{totals['totalStaked']:.2f}",
        f"- Returned: £{totals['totalReturn']:.2f}",
        f"- Profit/Loss: £{totals['totalProfit']:.2f}",
        f"- ROI: {totals['roi']}%",
        "",
    ]

    if report["mismatches"]:
        lines.append("Mismatches:")
        for m in report["mismatches"]:
            lines.append(f"- {m['field']}: archives={m['expectedFromArchives']} performance.json={m['actualInPerformanceJson']}")
        lines.append("")

    if report["errors"]:
        lines.append("Errors:")
        for item in report["errors"]:
            lines.append(f"- {item['date']}: {item['message']}")
        lines.append("")

    if report["warnings"]:
        lines.append("Warnings:")
        for item in report["warnings"]:
            lines.append(f"- {item['date']}: {item['message']}")
        lines.append("")

    if not report["mismatches"] and not report["errors"] and not report["warnings"]:
        lines.append("No issues found.")
        lines.append("")

    lines.append("This checker is read-only. It does not change picks, results, or performance totals.")
    return "\n".join(lines) + "\n"


def write_report(report: Dict[str, Any], report_date: str) -> Tuple[Path, Path]:
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    json_path = CHECK_DIR / f"check_{report_date}.json"
    txt_path = CHECK_DIR / f"check_{report_date}.txt"
    archive_existing(json_path)
    archive_existing(txt_path)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    txt_path.write_text(text_report(report), encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Signal 75 results consistency.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Report date, default today.")
    args = parser.parse_args()

    report = build_report()
    json_path, txt_path = write_report(report, args.date)
    print(f"Status: {report['status']}")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {txt_path}")
    return 0 if report["status"] in ("OK", "WARNING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
