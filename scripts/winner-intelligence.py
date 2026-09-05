#!/usr/bin/env python3
"""Learn from the horses that actually won.

Analysis only. Writes to data/winner_intelligence and never changes live picks,
scoring, proof, settlement, unlock logic, or public JSON contracts.
"""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Any, Dict, List, Tuple

from learning_utils import DATA_DIR, available_combined_dates, combined_rows, norm, now_iso, safe_float, safe_int, won, write_json, write_text


OUT_DIR = DATA_DIR / "winner_intelligence"


def race_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (str(row.get("market_id") or ""), str(row.get("course") or "").upper(), str(row.get("race_time") or ""))


def missed_reason(row: Dict[str, Any]) -> str:
    selection = row.get("selection_type")
    score = safe_float(row.get("signal_score")) or 0
    price = safe_float(row.get("pre_race_price")) or safe_float(row.get("bsp")) or 0
    field = safe_int(row.get("field_size")) or 0
    tips = safe_int(row.get("tipster_count_live")) or safe_int(row.get("explicit_tip_count")) or 0
    if selection == "OFFICIAL":
        return "SIGNAL75_PICKED_AND_WON"
    if selection == "WATCHLIST":
        return "SIGNAL75_WATCHLIST_AND_WON"
    if score >= 75 and tips == 0:
        return "TIPSTER_GATE_EXCLUDED"
    if score >= 75 and price and not (2.75 <= price <= 6.0):
        return "ODDS_GATE_EXCLUDED"
    if score >= 75 and field and field < 8:
        return "FIELD_SIZE_EXCLUDED"
    if score >= 75:
        return "HIGH_SCORE_MISSED"
    if score >= 70:
        return "NEAR_SIGNAL75_VIEW"
    return "OUTSIDE_SIGNAL75_VIEW"


def winners_for_date(date: str) -> List[Dict[str, Any]]:
    rows = combined_rows(date)
    races: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for row in rows:
        key = race_key(row)
        if key != ("", "", ""):
            races.setdefault(key, []).append(row)

    winners = []
    seen = set()
    for key, race_rows in races.items():
        winner = next((row for row in race_rows if won(row)), None)
        if not winner:
            continue
        unique = (date, key, norm(winner.get("horse_name")))
        if unique in seen:
            continue
        seen.add(unique)
        category = missed_reason(winner)
        winners.append(
            {
                "date": date,
                "course": winner.get("course"),
                "race_time": winner.get("race_time"),
                "market_id": winner.get("market_id"),
                "horse_name": winner.get("horse_name"),
                "winning_bsp": winner.get("bsp") or winner.get("pre_race_price"),
                "was_signal75_pick": winner.get("selection_type") == "OFFICIAL",
                "was_signal75_watchlist": winner.get("selection_type") == "WATCHLIST",
                "signal75_score_if_known": winner.get("signal_score"),
                "tipster_count_if_known": winner.get("tipster_count_live") or winner.get("explicit_tip_count") or 0,
                "why_signal75_missed": category if category != "SIGNAL75_PICKED_AND_WON" else "",
                "winner_category": category,
                "finishing_comment_if_available": winner.get("race_comment") or "",
                "beat_high_signal_horses": winner.get("beat_high_signal_horses") or [],
            }
        )
    return winners


def build(date: str) -> Dict[str, Any]:
    daily_winners = winners_for_date(date)
    cumulative_winners = []
    for day in available_combined_dates():
        cumulative_winners.extend(winners_for_date(day))
    categories = Counter(w["winner_category"] for w in cumulative_winners)
    notable = [
        w for w in daily_winners
        if w["winner_category"] in {"TIPSTER_GATE_EXCLUDED", "ODDS_GATE_EXCLUDED", "HIGH_SCORE_MISSED", "SIGNAL75_WATCHLIST_AND_WON"}
    ][:12]
    return {
        "date": date,
        "generatedAt": now_iso(),
        "analysis_only": True,
        "scoringImpact": "none",
        "races_analysed": len({(w["course"], w["race_time"], w["market_id"]) for w in daily_winners}),
        "winners": daily_winners,
        "winner_categories": dict(sorted(Counter(w["winner_category"] for w in daily_winners).items())),
        "cumulative_winner_categories": dict(sorted(categories.items())),
        "notable_misses": notable,
        "recommendation": "Use winner categories after 14 June to see which gate excluded useful winners.",
    }


def render(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - WINNER INTELLIGENCE",
        payload["date"],
        "",
        "Analysis only. This does not change live scoring or picks.",
        "",
        "Winner categories:",
    ]
    for name, count in payload["winner_categories"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "Notable misses:"])
    for item in payload["notable_misses"] or []:
        lines.append(f"- {item['horse_name']} {item['course']} {item['race_time']}: {item['winner_category']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build winner intelligence.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    payload = build(args.date)
    write_json(OUT_DIR / f"winners_{args.date}.json", payload)
    write_json(OUT_DIR / "winners_cumulative.json", payload)
    write_text(OUT_DIR / f"winners_{args.date}.txt", render(payload))
    print(f"Winner intelligence complete for {args.date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
