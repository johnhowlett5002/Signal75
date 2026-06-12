#!/usr/bin/env python3
"""Check whether Signal 75 scores are calibrated against results.

Analysis only. Writes to data/calibration and never changes picks, scoring,
proof, settlement, unlock logic, or public JSON contracts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable

from learning_utils import DATA_DIR, available_combined_dates, combined_rows, now_iso, pct, placed, safe_float, score_band, scored_known_rows, won, write_json, write_text


OUT_DIR = DATA_DIR / "calibration"
BANDS = ["65-69", "70-74", "75-79", "80-84", "85-89", "90-94", "95-100"]


def blank_band() -> Dict[str, Any]:
    return {"count": 0, "winners": 0, "placed": 0, "unplaced": 0, "average_bsp": 0.0, "win_rate": 0.0, "place_rate": 0.0}


def summarise(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {band: blank_band() for band in BANDS}
    bsp_totals = defaultdict(float)
    bsp_counts = defaultdict(int)

    for row in rows:
        band = score_band(row.get("signal_score"))
        if band not in totals:
            continue
        item = totals[band]
        item["count"] += 1
        if won(row):
            item["winners"] += 1
        if placed(row):
            item["placed"] += 1
        else:
            item["unplaced"] += 1
        bsp = safe_float(row.get("bsp") or row.get("pre_race_price"))
        if bsp is not None:
            bsp_totals[band] += bsp
            bsp_counts[band] += 1

    for band, item in totals.items():
        item["win_rate"] = pct(item["winners"], item["count"])
        item["place_rate"] = pct(item["placed"], item["count"])
        item["average_bsp"] = round(bsp_totals[band] / bsp_counts[band], 2) if bsp_counts[band] else 0.0
    return totals


def calibration_status(score_bands: Dict[str, Dict[str, Any]], min_sample: int = 10) -> Dict[str, str]:
    populated = [(band, score_bands[band]["place_rate"], score_bands[band]["count"]) for band in BANDS if score_bands[band]["count"]]
    total = sum(count for _, _, count in populated)
    if total < min_sample:
        return {
            "status": "INSUFFICIENT_SAMPLE",
            "finding": f"Only {total} scored settled runners available. Keep collecting evidence.",
            "recommendation": "Review again after at least 10 settled scored runners.",
        }

    previous_rate = -1.0
    drift_pairs = []
    for band, rate, count in populated:
        if count >= 2 and rate < previous_rate:
            drift_pairs.append(band)
        if count >= 2:
            previous_rate = max(previous_rate, rate)

    if drift_pairs:
        return {
            "status": "CALIBRATION_DRIFT_DETECTED",
            "finding": f"Higher score band(s) {', '.join(drift_pairs)} are not outperforming lower bands on place rate.",
            "recommendation": "Treat top scores with caution until the 14 June review confirms whether score inflation is present.",
        }
    return {
        "status": "CALIBRATION_OK",
        "finding": "Higher score bands are broadly outperforming lower bands in the current sample.",
        "recommendation": "Keep monitoring; do not change live scoring from this script alone.",
    }


def build(date: str) -> Dict[str, Any]:
    current_rows = scored_known_rows(combined_rows(date))
    all_dates = available_combined_dates()
    cumulative_rows = []
    for day in all_dates:
        cumulative_rows.extend(scored_known_rows(combined_rows(day)))

    current = summarise(current_rows)
    cumulative = summarise(cumulative_rows)
    status = calibration_status(cumulative)
    return {
        "date": date,
        "generatedAt": now_iso(),
        "analysis_only": True,
        "scoringImpact": "none",
        "daily_score_bands": current,
        "cumulative_score_bands": cumulative,
        "days_in_sample": len(all_dates),
        "settled_scored_runners": len(cumulative_rows),
        "calibration_status": status["status"],
        "finding": status["finding"],
        "recommendation": status["recommendation"],
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - SCORE CALIBRATION CHECK",
        payload["date"],
        "",
        "Analysis only. This does not change live scoring or picks.",
        "",
        f"Status: {payload['calibration_status']}",
        f"Settled scored runners: {payload['settled_scored_runners']}",
        f"Finding: {payload['finding']}",
        "",
        "Cumulative score bands:",
    ]
    for band in BANDS:
        item = payload["cumulative_score_bands"][band]
        lines.append(f"{band}: {item['count']} runners, {item['win_rate']}% win, {item['place_rate']}% place")
    lines.append("")
    lines.append(f"Recommendation: {payload['recommendation']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check score calibration for Signal 75 learning.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / f"calibration_{args.date}.json", payload)
    write_json(OUT_DIR / "calibration_cumulative.json", payload)
    write_text(OUT_DIR / f"calibration_{args.date}.txt", render(payload))
    print(f"Score calibration complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
