#!/usr/bin/env python3
"""Build one master summary across the Signal 75 learning scripts."""

from __future__ import annotations

import argparse
from typing import Any, Dict

from learning_utils import DATA_DIR, load_json, now_iso, write_json, write_text


OUT_DIR = DATA_DIR / "continuous_training"


def build(date: str) -> Dict[str, Any]:
    cumulative = load_json(OUT_DIR / "cumulative_findings.json", {})
    calibration = load_json(DATA_DIR / "calibration" / "calibration_cumulative.json", {})
    features = load_json(DATA_DIR / "feature_tracking" / "feature_importance_cumulative.json", {})
    winners = load_json(DATA_DIR / "winner_intelligence" / "winners_cumulative.json", {})
    drift = load_json(DATA_DIR / "drift_detection" / "drift_cumulative.json", {})
    shadow = load_json(OUT_DIR / "shadow_promotion_log.json", {})
    alerts = load_json(OUT_DIR / "pattern_alerts.json", {})

    strongest = features.get("strongest_predictors") or []
    winner_categories = winners.get("cumulative_winner_categories") or {}
    return {
        "last_updated": now_iso(),
        "date": date,
        "analysis_only": True,
        "scoringImpact": "none",
        "days_in_trial": cumulative.get("days_analysed", 0),
        "performance": {
            "official_place_rate_all_time": cumulative.get("official_place_rate", "0.0%"),
            "watchlist_place_rate_all_time": cumulative.get("watchlist_place_rate", "0.0%"),
            "drift_status": drift.get("drift_status", "UNKNOWN"),
        },
        "calibration": {
            "status": calibration.get("calibration_status", "UNKNOWN"),
            "finding": calibration.get("finding", ""),
            "settled_scored_runners": calibration.get("settled_scored_runners", 0),
        },
        "strongest_predictors": strongest,
        "weak_or_noise_factors": features.get("weak_or_noise_factors") or [],
        "winner_analysis": {
            "categories": winner_categories,
            "tipster_gate_cost": winner_categories.get("TIPSTER_GATE_EXCLUDED", 0),
            "watchlist_winners": winner_categories.get("SIGNAL75_WATCHLIST_AND_WON", 0),
            "high_score_missed": winner_categories.get("HIGH_SCORE_MISSED", 0),
        },
        "shadow_promotion": {
            "leading_candidate": shadow.get("leading_candidate", ""),
            "ready_for_review": bool(shadow.get("ready_for_review")),
            "days_completed": shadow.get("days_completed", 0),
        },
        "top_pattern_alerts": alerts.get("items", [])[:10] if isinstance(alerts.get("items"), list) else [],
        "14_june_readiness": {
            "evidence_collected": True,
            "manual_review_required": True,
            "recommendation": "Review this summary before making any live rule changes after 14 June.",
        },
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - MASTER LEARNING SUMMARY",
        payload["date"],
        "",
        "Analysis only. This does not change live scoring or picks.",
        "",
        f"Official place rate: {payload['performance']['official_place_rate_all_time']}",
        f"Watchlist place rate: {payload['performance']['watchlist_place_rate_all_time']}",
        f"Calibration: {payload['calibration']['status']}",
        f"Drift: {payload['performance']['drift_status']}",
        f"Leading shadow candidate: {payload['shadow_promotion']['leading_candidate'] or 'none'}",
        "",
        "Strongest predictors:",
    ]
    for item in payload["strongest_predictors"] or ["None yet"]:
        lines.append(f"- {item}")
    lines.extend(["", "Winner analysis:"])
    for key, value in payload["winner_analysis"]["categories"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Signal 75 master learning summary.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / "master_learning_summary.json", payload)
    write_text(OUT_DIR / "master_learning_summary.txt", render(payload))
    print(f"Master learning summary complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
