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
from typing import Any, Dict, Iterable, Optional


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


def iter_result_rows(day: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
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


def find_result(day: Dict[str, Any], horse: str) -> Optional[Dict[str, Any]]:
    target = norm(horse)
    if not target:
        return None
    for row in iter_result_rows(day):
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
    archive = load_json(archive_path, {})
    day = load_json(day_path, {})

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
        row = find_result(day, pick_name(pick))
        updated = dict(pick)
        updated["settled"] = bool(row)
        updated["live_result"] = row.get("result") if row else None
        updated["position"] = row.get("position") if row else None
        updated["bsp"] = row.get("settlementOdds") or row.get("odds") if row else None
        updated["placed"] = placed_from_result(row)
        updated["returned"] = row.get("totalReturn") if row else None
        updated["profit_loss"] = None
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
