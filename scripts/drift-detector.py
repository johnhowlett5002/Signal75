#!/usr/bin/env python3
"""Detect simple rolling performance drift for Signal 75 learning."""

from __future__ import annotations

import argparse
from statistics import mean
from typing import Any, Dict, List

from learning_utils import DATA_DIR, available_combined_dates, combined_rows, known_result, now_iso, pct, placed, safe_float, write_json, write_text


OUT_DIR = DATA_DIR / "drift_detection"


def candidate_rows(date: str) -> List[Dict[str, Any]]:
    rows = []
    for row in combined_rows(date):
        if not known_result(row):
            continue
        if row.get("selection_type") in {"OFFICIAL", "WATCHLIST"} or (safe_float(row.get("signal_score")) or 0) >= 75:
            rows.append(row)
    return rows


def window_stats(dates: List[str]) -> Dict[str, Any]:
    rows = []
    for date in dates:
        rows.extend(candidate_rows(date))
    placed_count = sum(1 for row in rows if placed(row))
    scores_placed = [safe_float(row.get("signal_score")) for row in rows if placed(row) and safe_float(row.get("signal_score")) is not None]
    scores_unplaced = [safe_float(row.get("signal_score")) for row in rows if not placed(row) and safe_float(row.get("signal_score")) is not None]
    return {
        "days": len(dates),
        "runners": len(rows),
        "place_rate": pct(placed_count, len(rows)),
        "average_score_placed": round(mean(scores_placed), 1) if scores_placed else 0.0,
        "average_score_unplaced": round(mean(scores_unplaced), 1) if scores_unplaced else 0.0,
        "score_discrimination_gap": round((mean(scores_placed) if scores_placed else 0) - (mean(scores_unplaced) if scores_unplaced else 0), 1),
    }


def build(date: str) -> Dict[str, Any]:
    dates = [d for d in available_combined_dates() if d <= date]
    windows = {
        "last_7_days": window_stats(dates[-7:]),
        "last_14_days": window_stats(dates[-14:]),
        "last_30_days": window_stats(dates[-30:]),
        "all_time": window_stats(dates),
    }
    recent = windows["last_7_days"]["place_rate"]
    longer = windows["last_30_days"]["place_rate"]
    drift = recent + 15 < longer if windows["last_7_days"]["runners"] and windows["last_30_days"]["runners"] else False
    gap = windows["last_7_days"]["score_discrimination_gap"]
    score_degrading = gap < 0 and windows["last_7_days"]["runners"] >= 5
    status = "PERFORMANCE_DRIFT_DETECTED" if drift else "SCORE_DISCRIMINATION_DEGRADING" if score_degrading else "DRIFT_OK_OR_INSUFFICIENT_SAMPLE"
    return {
        "date": date,
        "generatedAt": now_iso(),
        "analysis_only": True,
        "scoringImpact": "none",
        "place_rates": windows,
        "drift_status": status,
        "finding": f"Last 7-day place rate is {recent}%; last 30-day place rate is {longer}%.",
        "possible_causes": [
            "Seasonal going or surface changes.",
            "Tipster-first gate may be excluding better watchlist horses.",
            "Small sample size can exaggerate swings.",
        ],
        "recommendation": "Use as an early warning only. Review with calibration and winner intelligence before changing rules.",
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - DRIFT DETECTOR",
        payload["date"],
        "",
        "Analysis only. This does not change live scoring or picks.",
        "",
        f"Status: {payload['drift_status']}",
        payload["finding"],
        "",
        "Windows:",
    ]
    for name, item in payload["place_rates"].items():
        lines.append(f"- {name}: {item['place_rate']}% place from {item['runners']} runners")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect Signal 75 performance drift.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / f"drift_{args.date}.json", payload)
    write_json(OUT_DIR / "drift_cumulative.json", payload)
    write_text(OUT_DIR / f"drift_{args.date}.txt", render(payload))
    print(f"Drift detection complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
