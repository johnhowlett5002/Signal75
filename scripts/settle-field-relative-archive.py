#!/usr/bin/env python3
"""Settle the field-relative pre-race archive after results are known.

This is analysis-only. It reads the immutable pre-race archive and the settled
daily result file, then writes a separate ``_settled`` copy for learning.
It never changes picks, proof, performance, scoring, or public results.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def norm(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def pick_name(pick: Dict[str, Any]) -> str:
    return str(pick.get("horse") or pick.get("name") or pick.get("horse_name") or "")


def money(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_place_fraction(runners: Any) -> float:
    try:
        value = int(runners)
    except (TypeError, ValueError):
        value = 8
    return 0.20 if value >= 16 else 0.25


def calculate_ew_return(odds: Any, result: str, runners: Any) -> Tuple[float, float, float]:
    """Return the established Challenger Lab £1 each-way paper settlement."""
    decimal_odds = money(odds)
    if decimal_odds <= 1:
        return 0.0, 0.0, 0.0
    place_multiplier = 1 + (decimal_odds - 1) * default_place_fraction(runners)
    result = str(result or "").upper()
    if result == "WON":
        win_return = decimal_odds
        place_return = place_multiplier
    elif result == "PLACED":
        win_return = 0.0
        place_return = place_multiplier
    elif result == "VOID":
        win_return = 1.0
        place_return = 1.0
    else:
        win_return = 0.0
        place_return = 0.0
    return round(win_return, 2), round(place_return, 2), round(win_return + place_return, 2)


def iter_result_rows(day: Dict[str, Any], full_field: Optional[Dict[str, Any]] = None) -> Iterable[Dict[str, Any]]:
    results = day.get("results") if isinstance(day.get("results"), dict) else {}
    for section in ("flat", "jumps"):
        rows = results.get(section) if isinstance(results.get(section), list) else []
        for row in rows:
            if isinstance(row, dict):
                yield row

    # Some older files keep runner results on the visible pick lists.
    for section in ("flat", "jumps", "topRated", "topRatedFlat", "topRatedJumps"):
        rows = day.get(section) if isinstance(day.get(section), list) else []
        for row in rows:
            if isinstance(row, dict) and any(k in row for k in ("result", "position", "known_result", "radarResult")):
                yield row

    race_sizes = {
        str(race.get("market_id") or ""): race.get("expected_runner_count") or len(race.get("runners") or [])
        for race in (full_field or {}).get("races", []) or []
        if isinstance(race, dict)
    }
    for record in (full_field or {}).get("records", []) or []:
        if not isinstance(record, dict):
            continue
        row = dict(record)
        position = row.get("position")
        if row.get("status") == "NON_RUNNER":
            row["result"] = "VOID"
        elif position == 1:
            row["result"] = "WON"
        elif isinstance(position, int) and position <= 3:
            row["result"] = "PLACED"
        elif isinstance(position, int):
            row["result"] = "LOST"
        row.setdefault("odds", row.get("sp_decimal"))
        row.setdefault("runners", race_sizes.get(str(row.get("market_id") or ""), 8))
        yield row


def find_result(day: Dict[str, Any], horse: str, full_field: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    target = norm(horse)
    if not target:
        return None
    for row in iter_result_rows(day, full_field):
        if norm(row.get("name") or row.get("horse") or row.get("horse_name")) == target:
            return row
    return None


def placed_from_result(row: Optional[Dict[str, Any]]) -> Optional[bool]:
    if not row:
        return None
    result = str(row.get("result") or row.get("known_result") or row.get("radarResult") or "").upper()
    position = row.get("position") or row.get("finish_position") or row.get("pos")
    if result in {"WON", "PLACED"}:
        return True
    if result in {"LOST", "UNPLACED"}:
        return False
    try:
        return int(position) <= 3
    except (TypeError, ValueError):
        return None


def learning_note(pick: Dict[str, Any], row: Optional[Dict[str, Any]]) -> str:
    horse = pick_name(pick) or "This horse"
    if not row:
        return f"{horse} has not been matched to a settled result yet."

    result = str(row.get("result") or "").upper()
    position = row.get("position") or row.get("finish_position") or row.get("pos")
    reasons = pick.get("top_reasons") if isinstance(pick.get("top_reasons"), list) else []
    risks = pick.get("top_risks") if isinstance(pick.get("top_risks"), list) else []

    if result == "WON":
        outcome = "won"
    elif placed_from_result(row):
        outcome = f"placed ({position})" if position else "placed"
    elif result:
        outcome = "did not place"
    else:
        outcome = f"finished {position}" if position else "settled"

    reason_text = "; ".join(str(r) for r in reasons[:2]) if reasons else "No headline V1 reason was stored."
    risk_text = "; ".join(str(r) for r in risks[:2]) if risks else "No headline V1 risk was stored."
    return f"{horse} {outcome}. Reasons checked: {reason_text}. Risks noted: {risk_text}."


def settle(date_text: str) -> Dict[str, Any]:
    archive_path = DATA / f"field_relative_archive_{date_text}.json"
    day_path = DATA / f"{date_text}.json"
    full_field_path = DATA / "horse_intelligence" / f"full_field_results_{date_text}.json"
    archive = load_json(archive_path, {})
    day = load_json(day_path, {})
    full_field = load_json(full_field_path, {})

    if not archive:
        raise FileNotFoundError(f"Missing archive: {archive_path.relative_to(REPO_ROOT)}")
    if not day:
        raise FileNotFoundError(f"Missing daily result file: {day_path.relative_to(REPO_ROOT)}")

    settled_picks = []
    matched = 0
    placed = 0
    winners = 0

    for pick in archive.get("picks", []):
        if not isinstance(pick, dict):
            continue
        row = find_result(day, pick_name(pick), full_field)
        updated = dict(pick)
        updated["settled"] = bool(row)
        updated["live_result"] = row.get("result") if row else None
        updated["result"] = row.get("result") if row else None
        updated["position"] = row.get("position") if row else None
        updated["bsp"] = row.get("settlementOdds") or row.get("odds") if row else None
        updated["placed"] = placed_from_result(row)
        win_return, place_return, total_return = calculate_ew_return(
            updated.get("odds"), row.get("result") if row else "", row.get("runners") if row else 8
        )
        updated["win_return"] = win_return
        updated["place_return"] = place_return
        updated["return"] = total_return
        updated["returned"] = total_return
        updated["profit_loss"] = round(total_return - 2.0, 2) if row else None
        updated["return_basis"] = "analysis-only £1 each-way at archived pre-race odds"
        updated["learning_note"] = learning_note(updated, row)
        settled_picks.append(updated)

        if row:
            matched += 1
            if updated["placed"]:
                placed += 1
            if str(row.get("result") or "").upper() == "WON":
                winners += 1

    payload = dict(archive)
    payload.update(
        {
            "settled": True,
            "settled_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_type": "post_race_learning",
            "source_archive": str(archive_path.relative_to(REPO_ROOT)),
            "source_results": str(day_path.relative_to(REPO_ROOT)),
            "source_full_field_results": (
                str(full_field_path.relative_to(REPO_ROOT)) if full_field.get("complete") else ""
            ),
            "picks": settled_picks,
            "summary": {
                "picks": len(settled_picks),
                "matched_results": matched,
                "winners": winners,
                "placed_or_won": placed,
                "analysis_only": True,
                "scoringImpact": "none",
            },
        }
    )

    out = DATA / f"field_relative_archive_{date_text}_settled.json"
    write_json(out, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle V1 field-relative archive for learning only.")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    payload = settle(args.date)
    summary = payload.get("summary", {})
    print(
        f"Settled field-relative archive for {args.date}: "
        f"{summary.get('matched_results', 0)}/{summary.get('picks', 0)} matched, "
        f"{summary.get('winners', 0)} won, {summary.get('placed_or_won', 0)} placed/won"
    )
    print(f"Wrote data/field_relative_archive_{args.date}_settled.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
