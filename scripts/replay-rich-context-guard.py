#!/usr/bin/env python3
"""Replay the analysis-only combined context guard using pre-race data only."""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from rich_context import build_runner_context


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FORM_DB = DATA / "horse_intelligence" / "form_history.sqlite"
OUTPUT_DIR = DATA / "intelligence_reviews"
DEFAULT_DATES = [
    "2026-08-26",
    "2026-08-28",
    "2026-08-29",
    "2026-08-30",
    "2026-08-31",
    "2026-09-01",
]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enrich_rows(rows: List[Dict[str, Any]], date_value: str, picks_module) -> None:
    picks_module._HORSE_CLASS_CONTEXT_CACHE.clear()
    for row in rows:
        row["date"] = date_value
        context = build_runner_context(FORM_DB, row, date_value)
        row["richContext"] = context
        row["contextEvidence"] = dict(context.get("statuses") or {})
        for key in ("courseWins", "courseRuns", "distanceWins", "distanceRuns", "goingWins", "goingRuns"):
            row[key] = context.get(key)
        if context.get("daysSinceLastRun") is not None:
            row["days_since_last_run"] = context["daysSinceLastRun"]
        if context.get("raceClass"):
            row["race_class"] = context["raceClass"]
        class_adjustment = picks_module._top_class_context_adjustment(row)
        if class_adjustment:
            row["classContextPenalty"] = class_adjustment
            row["contextEvidence"]["class"] = class_adjustment.get("evidence_status", "unknown")
        else:
            row["contextEvidence"]["class"] = "unknown"


def replay_day(date_value: str, challenger_module, settle_module, picks_module) -> Dict[str, Any]:
    comparison_path = DATA / f"race_comparison_{date_value}.json"
    day_path = DATA / f"{date_value}.json"
    day = read_json(day_path)
    if not comparison_path.exists():
        return {
            "date": date_value,
            "status": "not_replayable",
            "reason": "Stored full-field pre-race race comparison is missing; no reconstruction was attempted.",
            "live_picks": [pick.get("horse") for pick in challenger_module.extract_live_picks(day)],
            "live_profit": round(float((day.get("results") or {}).get("profit") or 0), 2),
            "context_guard_picks": [],
            "context_guard_settled": False,
            "context_guard_profit": None,
            "delta_vs_live": None,
        }
    comparison = read_json(comparison_path)
    rows = challenger_module.flatten_race_comparison(comparison)
    rows = [
        row for row in rows
        if 4.1 <= challenger_module.money(row.get("odds")) <= 6.0
        and 8 <= int(row.get("field_size") or 0) <= 14
    ]
    enrich_rows(rows, date_value, picks_module)
    live = challenger_module.extract_live_picks(day)
    challenger = challenger_module.select_context_guard(rows, live)
    lookup = settle_module.result_lookup(day)
    lookup.update(settle_module.archive_result_lookup(date_value))
    settle_module.settle_challenger(challenger, lookup)
    live_profit = round(float((day.get("results") or {}).get("profit") or 0), 2)
    challenger_profit = challenger.get("comparison", {}).get("challenger_profit")
    delta = None if challenger_profit is None else round(float(challenger_profit) - live_profit, 2)
    picks = []
    for pick in challenger.get("picks") or []:
        post = pick.get("post_race_result") or {}
        picks.append(
            {
                "horse": pick.get("horse"),
                "course": pick.get("course"),
                "time": pick.get("time"),
                "odds": pick.get("odds"),
                "score": pick.get("combined_score"),
                "live_selected": pick.get("live_selected"),
                "result": post.get("result"),
                "position": post.get("position"),
                "return": post.get("return"),
                "pre_race_evidence": pick.get("pre_race_evidence"),
            }
        )
    return {
        "date": date_value,
        "status": "replayed",
        "live_picks": [pick.get("horse") for pick in live],
        "live_profit": live_profit,
        "context_guard_picks": picks,
        "context_guard_settled": challenger.get("comparison", {}).get("settled"),
        "context_guard_profit": challenger_profit,
        "delta_vs_live": delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dates", nargs="*", default=DEFAULT_DATES)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    challenger = load_script("rich_context_replay_challenger", "generate-challenger-lab.py")
    settle = load_script("rich_context_replay_settle", "settle-challenger-lab.py")
    picks = load_script("rich_context_replay_picks", "generate-picks-betfair.py")
    daily = [replay_day(day, challenger, settle, picks) for day in args.dates]
    settled = [row for row in daily if row["context_guard_settled"]]
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "analysisOnly": True,
        "scoringImpact": "none",
        "proofImpact": "none",
        "method": "Stored pre-race race comparisons enriched only with archive rows dated before each race date.",
        "dates": args.dates,
        "summary": {
            "days": len(daily),
            "replayableDays": sum(row["status"] == "replayed" for row in daily),
            "unreplayableDays": sum(row["status"] != "replayed" for row in daily),
            "settledDays": len(settled),
            "liveProfit": round(sum(row["live_profit"] for row in settled), 2),
            "contextGuardProfit": round(sum(float(row["context_guard_profit"] or 0) for row in settled), 2),
            "deltaVsLive": round(sum(float(row["delta_vs_live"] or 0) for row in settled), 2),
            "contextGuardWinners": sum(
                pick.get("result") == "WON" for row in settled for pick in row["context_guard_picks"]
            ),
            "contextGuardPlacedIncludingWinners": sum(
                pick.get("result") in {"WON", "PLACED"} for row in settled for pick in row["context_guard_picks"]
            ),
        },
        "daily": daily,
    }
    output = Path(args.output) if args.output else OUTPUT_DIR / f"rich_context_replay_{args.dates[0]}_to_{args.dates[-1]}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
