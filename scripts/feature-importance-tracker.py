#!/usr/bin/env python3
"""Track which Signal 75 evidence features are predictive.

Analysis only. Writes to data/feature_tracking and never changes live picks,
scoring, proof, settlement, unlock logic, or public JSON contracts.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from typing import Any, Callable, Dict, Iterable

from learning_utils import DATA_DIR, available_combined_dates, combined_rows, known_result, now_iso, pct, placed, safe_float, safe_int, write_json, write_text


OUT_DIR = DATA_DIR / "feature_tracking"


def tags(row: Dict[str, Any]) -> set[str]:
    raw = row.get("grandad_memory_tags") if isinstance(row.get("grandad_memory_tags"), list) else []
    return {str(x).upper() for x in raw}


def clean_form(row: Dict[str, Any]) -> bool:
    form = str(row.get("form") or "").upper()
    if not form:
        return False
    recent = "".join(ch for ch in form if ch.isalnum())[-3:]
    return bool(recent) and not any(ch in "PUFRB0" or (ch.isdigit() and int(ch) >= 8) for ch in recent)


FEATURES: Dict[str, Callable[[Dict[str, Any]], bool]] = {
    "trusted_tipster_present": lambda r: safe_int(r.get("tipster_count_live")) and safe_int(r.get("tipster_count_live")) >= 1,
    "multi_tipster": lambda r: safe_int(r.get("tipster_count_live")) and safe_int(r.get("tipster_count_live")) >= 2,
    "in_odds_sweet_spot": lambda r: (safe_float(r.get("pre_race_price")) or 0) >= 2.75 and (safe_float(r.get("pre_race_price")) or 0) <= 6.0,
    "optimal_field_size": lambda r: (safe_int(r.get("field_size")) or 0) >= 8 and (safe_int(r.get("field_size")) or 0) <= 12,
    "rival_warning_absent": lambda r: not r.get("head_to_head_losses_today") and not r.get("historic_rival_negative_count"),
    "historic_positive_present": lambda r: bool(r.get("historic_rival_positive_count")),
    "head_to_head_positive_present": lambda r: bool(r.get("head_to_head_wins_today")),
    "clean_form": clean_form,
    "grandad_memory_present": lambda r: bool(r.get("grandad_memory_tags") or r.get("grandad_book_insight")),
    "result_comment_positive": lambda r: "WON_DECISIVELY" in (r.get("result_note_flags") or []),
    "bad_result_comment_absent": lambda r: "WEAKENED_OR_NO_RESPONSE" not in (r.get("result_note_flags") or []) and "PULLED_UP" not in (r.get("result_note_flags") or []),
    "jockey_claim_present": lambda r: (safe_int(r.get("jockey_claim_lbs")) or 0) > 0,
    "price_in_value_band_tag": lambda r: "PRICE_IN_VALUE_BAND" in tags(r),
    "market_top_three_tag": lambda r: "MARKET_TOP_THREE" in tags(r),
}


def summarise(rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    stats = {
        name: {"placed_present": 0, "placed_total": 0, "unplaced_present": 0, "unplaced_total": 0}
        for name in FEATURES
    }
    for row in rows:
        if not known_result(row):
            continue
        bucket = "placed" if placed(row) else "unplaced"
        for name, fn in FEATURES.items():
            stats[name][f"{bucket}_total"] += 1
            if fn(row):
                stats[name][f"{bucket}_present"] += 1

    output = {}
    for name, item in stats.items():
        placed_rate = pct(item["placed_present"], item["placed_total"])
        unplaced_rate = pct(item["unplaced_present"], item["unplaced_total"])
        output[name] = {
            **item,
            "present_on_placed_rate": placed_rate,
            "present_on_unplaced_rate": unplaced_rate,
            "signal_strength": round(placed_rate - unplaced_rate, 1),
        }
    return dict(sorted(output.items(), key=lambda pair: pair[1]["signal_strength"], reverse=True))


def build(date: str) -> Dict[str, Any]:
    dates = available_combined_dates()
    rows = []
    for day in dates:
        rows.extend(combined_rows(day))
    daily = summarise(combined_rows(date))
    cumulative = summarise(rows)
    strongest = [name for name, item in cumulative.items() if item["signal_strength"] >= 10][:5]
    weak = [name for name, item in cumulative.items() if abs(item["signal_strength"]) <= 3][:8]
    return {
        "date": date,
        "generatedAt": now_iso(),
        "analysis_only": True,
        "scoringImpact": "none",
        "days_in_sample": len(dates),
        "daily_feature_signal_strength": daily,
        "cumulative_feature_signal_strength": cumulative,
        "strongest_predictors": strongest,
        "weak_or_noise_factors": weak,
        "recommendation": "Use this as 14 June evidence only. Do not change live scoring without manual review.",
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - FEATURE IMPORTANCE TRACKER",
        payload["date"],
        "",
        "Analysis only. This does not change live scoring or picks.",
        "",
        "Strongest predictors:",
    ]
    for name in payload["strongest_predictors"] or ["None yet"]:
        lines.append(f"- {name}")
    lines.extend(["", "Top cumulative feature strengths:"])
    for name, item in list(payload["cumulative_feature_signal_strength"].items())[:10]:
        lines.append(f"- {name}: {item['signal_strength']} points")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Track Signal 75 feature importance.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / f"feature_importance_{args.date}.json", payload)
    write_json(OUT_DIR / "feature_importance_cumulative.json", payload)
    write_text(OUT_DIR / f"feature_importance_{args.date}.txt", render(payload))
    print(f"Feature importance complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
