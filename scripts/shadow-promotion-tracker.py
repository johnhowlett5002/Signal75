#!/usr/bin/env python3
"""Track whether any shadow variant has earned manual promotion review."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from learning_utils import DATA_DIR, load_json, now_iso, safe_float, write_json, write_text


OUT_DIR = DATA_DIR / "continuous_training"
SHADOW_PATTERNS = ("consensus_shadow_*.json", "late_value_shadow_*.json")
LIVE_RULE = "tipster_first_live_rule"


def shadow_files() -> List[Path]:
    files: List[Path] = []
    for pattern in SHADOW_PATTERNS:
        files.extend(DATA_DIR.glob(pattern))
    return sorted(files)


def date_from_shadow(path: Path) -> str:
    return path.stem.split("_")[-1]


def iter_results() -> Iterable[Tuple[str, str, float, bool, str]]:
    for path in shadow_files():
        payload = load_json(path, {})
        date = str(payload.get("date") or date_from_shadow(path))
        results = payload.get("results") if isinstance(payload, dict) else {}
        if not isinstance(results, dict):
            continue
        for variant, item in results.items():
            yield date, variant, safe_float(item.get("patentProfit")) or 0.0, bool(item.get("noBet")), path.name


def build(date: str) -> Dict[str, Any]:
    by_day: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    for day, variant, profit, no_bet, source in iter_results():
        by_day[day][variant] = {"profit": profit, "no_bet": no_bet, "source": source}

    variants: Dict[str, Dict[str, Any]] = {}
    for day, rows in sorted(by_day.items()):
        live = rows.get(LIVE_RULE) or rows.get("baseline_live_rule") or {"profit": 0.0}
        live_profit = safe_float(live.get("profit")) or 0.0
        for variant, item in rows.items():
            if variant == LIVE_RULE:
                continue
            v = variants.setdefault(
                variant,
                {
                    "days_seen": 0,
                    "days_beat_live": 0,
                    "days_underperformed_live": 0,
                    "total_theoretical_profit": 0.0,
                    "live_comparison_profit": 0.0,
                    "catastrophic_days": [],
                    "daily": [],
                },
            )
            profit = safe_float(item.get("profit")) or 0.0
            v["days_seen"] += 1
            v["total_theoretical_profit"] += profit
            v["live_comparison_profit"] += live_profit
            if profit > live_profit:
                v["days_beat_live"] += 1
            if profit < live_profit:
                v["days_underperformed_live"] += 1
            if profit < -20 and live_profit > -10:
                v["catastrophic_days"].append(day)
            v["daily"].append({"date": day, "profit": round(profit, 2), "live_profit": round(live_profit, 2), "source": item.get("source")})

    for item in variants.values():
        item["total_theoretical_profit"] = round(item["total_theoretical_profit"], 2)
        item["vs_live_total"] = round(item["total_theoretical_profit"] - item["live_comparison_profit"], 2)
        item["average_daily_vs_live"] = round(item["vs_live_total"] / item["days_seen"], 2) if item["days_seen"] else 0.0
        item["promotion_criteria_met"] = (
            item["days_beat_live"] >= 10
            and item["vs_live_total"] > 0
            and item["average_daily_vs_live"] >= 2
            and not item["catastrophic_days"]
        )
        item["demotion_criteria_met"] = item["days_underperformed_live"] >= 10
        if item["promotion_criteria_met"]:
            item["status"] = "PROMOTION_CANDIDATE - manual review required"
        elif item["demotion_criteria_met"]:
            item["status"] = "DEMOTION_CANDIDATE - redesign or remove"
        else:
            item["status"] = "WATCH - keep collecting evidence"

    leading = sorted(variants.items(), key=lambda pair: pair[1].get("vs_live_total", 0), reverse=True)
    return {
        "date": date,
        "generatedAt": now_iso(),
        "analysis_only": True,
        "scoringImpact": "none",
        "live_rule": LIVE_RULE,
        "days_completed": len(by_day),
        "variants": dict(sorted(variants.items())),
        "leading_candidate": leading[0][0] if leading else "",
        "ready_for_review": bool(leading and leading[0][1].get("promotion_criteria_met")),
        "recommendation": "Use this for the 14 June manual review only. It does not promote anything automatically.",
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - SHADOW PROMOTION TRACKER",
        payload["date"],
        "",
        "Analysis only. This does not change live rules.",
        "",
        f"Days completed: {payload['days_completed']}",
        f"Leading candidate: {payload['leading_candidate'] or 'none'}",
        "",
        "Variants:",
    ]
    for name, item in payload["variants"].items():
        lines.append(f"- {name}: vs live £{item['vs_live_total']:.2f}, beat live {item['days_beat_live']} day(s), {item['status']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Track shadow variant promotion evidence.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / "shadow_promotion_log.json", payload)
    write_text(OUT_DIR / "shadow_promotion_log.txt", render(payload))
    print(f"Shadow promotion tracker complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
