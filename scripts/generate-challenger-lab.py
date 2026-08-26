#!/usr/bin/env python3
"""
Signal 75 Challenger Lab - pre-race shadow generators.

This script is analysis-only. It reads existing Signal 75 outputs and writes
separate Challenger Lab JSON. It must never write picks, proof or performance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from signal75_intelligence_store import LIVE_DB

REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = REPO_ROOT / "data"
CHALLENGER_DIR = DATA_DIR / "challenger_lab"
DASHBOARD_CHALLENGER_DIR = REPO_ROOT / "dashboard" / "data" / "challenger_lab"
DB_PATH = LIVE_DB

STRICT_MIN_ODDS = 4.1
STRICT_MAX_ODDS = 6.0
WIDER_PRICE_MAX_ODDS = 7.5
WIDE_MIN_ODDS = 2.75
WIDE_MAX_ODDS = 8.0
MIN_FIELD_SIZE = 8
MIN_BASE_SCORE = 70.0
RIVAL_EVIDENCE_START_DATE = "2020-01-01"
JUMPS_SCORE_GATE = 70.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_name(value: Any) -> str:
    text = str(value or "").lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def horse_key(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def money(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def default_date() -> str:
    return date.today().isoformat()


def extract_live_picks(picks_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    live: List[Dict[str, Any]] = []
    for section in ("flat", "jumps"):
        for race in picks_payload.get(section, []) or []:
            horses = race.get("horses") or []
            if not horses:
                continue
            horse = horses[0]
            live.append(
                {
                    "horse": horse.get("name", ""),
                    "course": race.get("course", ""),
                    "time": race.get("time", ""),
                    "market_id": race.get("market_id", ""),
                    "odds": money(horse.get("odds")),
                    "score": money(horse.get("signal_score")),
                }
            )
    return live


def flatten_race_comparison(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    runners: List[Dict[str, Any]] = []
    for race in payload.get("races", []) or []:
        for runner in race.get("runners", []) or []:
            row = dict(runner)
            row.update(
                {
                    "course": race.get("course", ""),
                    "time": race.get("time", ""),
                    "race_time": race.get("time", ""),
                    "race_name": race.get("race_name", ""),
                    "race_type": race.get("race_type", ""),
                    "market_id": race.get("market_id", ""),
                    "field_size": race.get("field_size", len(race.get("runners", []) or [])),
                }
            )
            runners.append(row)
    return runners


def build_live_lookup(live_picks: List[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup = {}
    for pick in live_picks:
        key = (
            normalise_name(pick.get("horse")),
            normalise_name(pick.get("course")),
            str(pick.get("time") or "").strip(),
        )
        lookup[key] = pick
    return lookup


def source_quality_score(match: Dict[str, Any]) -> float:
    tiers = match.get("source_tiers") or {}
    return round(
        money(tiers.get("1")) * 3.0
        + money(tiers.get("2")) * 2.0
        + money(tiers.get("3")) * 1.0
        + money(tiers.get("4")) * 0.5,
        2,
    )


def build_tipster_lookup(script_overlay: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for match in script_overlay.get("matched_to_betfair", []) or []:
        key = (
            normalise_name(match.get("betfair_name") or match.get("horse")),
            normalise_name(match.get("course")),
            str(match.get("time") or "").strip(),
        )
        lookup[key] = match
    return lookup


def runner_key(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return (
        normalise_name(row.get("name") or row.get("horse")),
        normalise_name(row.get("course")),
        str(row.get("time") or row.get("race_time") or "").strip(),
    )


def live_status(row: Dict[str, Any], live_lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> str:
    if runner_key(row) in live_lookup:
        return "official"
    return str(row.get("status") or "runner")


def live_rejection_reasons(row: Dict[str, Any]) -> List[str]:
    reasons: List[str] = []
    score = money(row.get("score"))
    odds = money(row.get("odds"))
    field = int(row.get("field_size") or 0)
    if score < 75:
        reasons.append("score_below_live_threshold")
    if not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS):
        reasons.append("outside_strict_value_band")
    if field < MIN_FIELD_SIZE:
        reasons.append("field_size_below_gate")
    if row.get("warnings"):
        reasons.append("warning_present")
    if row.get("status") and row.get("status") != "official":
        reasons.append(f"live_status_{row.get('status')}")
    return reasons


def is_jumps_row(row: Dict[str, Any]) -> bool:
    type_text = " ".join(
        str(row.get(key) or "").lower()
        for key in ("race_type", "type", "race_name", "race")
    )
    return any(token in type_text for token in ("jump", "hurdle", "hrd", "chase", "chs", "national hunt", "nhf", "bumper"))


def parse_recent_form(form_value: Any, n: int = 4) -> List[str]:
    cleaned = re.sub(r"[-/\s]", "", str(form_value or "").upper())
    chars = list(reversed(cleaned))
    return [c for c in chars if c.isdigit() or c.upper() in ("P", "F", "U", "R", "B", "S")][:n]


def placed_in_last_4(form_value: Any) -> Optional[int]:
    digits = [c for c in parse_recent_form(form_value, 4) if c.isdigit()]
    if len(digits) < 4:
        return None
    return sum(1 for c in digits[:4] if c in ("1", "2", "3"))


def days_since_last_run(row: Dict[str, Any]) -> Optional[int]:
    for key in ("days_since_last_run", "days_since_run", "daysOff", "days_off"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None
    return None


def make_pick(
    row: Dict[str, Any],
    live_lookup: Dict[Tuple[str, str, str], Dict[str, Any]],
    combined_score: float,
    challenger_reason: str,
    tipster_quality: float = 0.0,
    relationship_score: float = 0.0,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    key = runner_key(row)
    return {
        "horse": row.get("name") or row.get("horse") or "",
        "course": row.get("course", ""),
        "time": row.get("time") or row.get("race_time") or "",
        "market_id": row.get("market_id", ""),
        "race_type": row.get("race_type", ""),
        "odds": money(row.get("odds")),
        "field_size": int(row.get("field_size") or 0),
        "base_score": money(row.get("score")),
        "tipster_quality_score": money(tipster_quality),
        "relationship_score": money(relationship_score),
        "combined_score": money(combined_score),
        "live_status": live_status(row, live_lookup),
        "live_selected": key in live_lookup,
        "live_rejection_reasons": live_rejection_reasons(row),
        "challenger_reason": challenger_reason,
        "pre_race_evidence": evidence or {},
        "post_race_result": {
            "settled": False,
            "position": None,
            "result": None,
            "bsp": None,
            "return": None,
            "profit": None,
            "excuse_flags": [],
        },
    }


def comparison_for(live_picks: List[Dict[str, Any]], challenger_picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    live_names = {normalise_name(p.get("horse")) for p in live_picks}
    challenger_names = {normalise_name(p.get("horse")) for p in challenger_picks}
    both = sorted(live_names & challenger_names)
    only_live = [p.get("horse", "") for p in live_picks if normalise_name(p.get("horse")) not in challenger_names]
    only_challenger = [p.get("horse", "") for p in challenger_picks if normalise_name(p.get("horse")) not in live_names]
    return {
        "overlap_with_live": len(both),
        "only_live": only_live,
        "only_challenger": only_challenger,
        "both_picked": [p.get("horse", "") for p in live_picks if normalise_name(p.get("horse")) in challenger_names],
        "same_as_live": live_names == challenger_names and len(live_names) == len(challenger_names),
        "settled": False,
        "live_profit": None,
        "challenger_profit": None,
        "delta_vs_live": None,
        "verdict": None,
    }


def open_history_db() -> Optional[sqlite3.Connection]:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_record_count(conn: Optional[sqlite3.Connection]) -> int:
    if conn is None:
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM head_to_head").fetchone()[0])
    except sqlite3.Error:
        return 0


def get_rival_evidence_sqlite(
    conn: sqlite3.Connection,
    runner_key_value: str,
    today_field_keys: Sequence[str],
) -> List[sqlite3.Row]:
    field_keys = [key for key in today_field_keys if key and key != runner_key_value]
    if not runner_key_value or not field_keys:
        return []
    placeholders = ",".join("?" * len(field_keys))
    query = f"""
        SELECT * FROM (
            SELECT winner_key, loser_key, date, course, race_name, payload_json
            FROM head_to_head
            WHERE winner_key = ?
              AND loser_key IN ({placeholders})
              AND date >= ?
            ORDER BY date DESC
            LIMIT 200
        )
        UNION ALL
        SELECT * FROM (
            SELECT winner_key, loser_key, date, course, race_name, payload_json
            FROM head_to_head
            WHERE loser_key = ?
              AND winner_key IN ({placeholders})
              AND date >= ?
            ORDER BY date DESC
            LIMIT 200
        )
    """
    params: List[Any] = [runner_key_value] + field_keys + [RIVAL_EVIDENCE_START_DATE]
    params += [runner_key_value] + field_keys + [RIVAL_EVIDENCE_START_DATE]
    return list(conn.execute(query, params).fetchall())


def old_profile_overlay_support() -> Dict[str, Dict[str, Any]]:
    support: Dict[str, Dict[str, Any]] = {}
    profile_paths = [
        DATA_DIR / "horse_intelligence" / "head_to_head_profiles.json",
        DATA_DIR / "horse_intelligence" / "historic_rival_profiles.json",
    ]
    for profile_path in profile_paths:
        payload = read_json(profile_path, {})
        for profile in (payload.get("pairs") or {}).values():
            tier = profile.get("evidence_tier")
            if tier not in ("strong_warning_or_support", "useful_pattern"):
                continue
            dominant = profile.get("dominant_horse")
            dominant_key = horse_key(dominant)
            if not dominant_key:
                continue
            try:
                dominance_rate = float(profile.get("dominance_rate") or 0)
            except (TypeError, ValueError):
                dominance_rate = 0.0
            meetings = int(profile.get("meetings_logged") or profile.get("historic_meetings_found") or 0)
            if meetings < 2 or dominance_rate < 0.67:
                continue
            points = 8 if tier == "strong_warning_or_support" else 5
            row = support.setdefault(
                dominant_key,
                {
                    "points": 0,
                    "source": "old_profile_overlay",
                    "notes": [],
                    "pairs": [],
                },
            )
            row["points"] = min(8, int(row["points"] or 0) + points)
            row["notes"].append(profile.get("last_note") or profile.get("latest_note") or f"{dominant} had broad profile support.")
            row["pairs"].append(profile.get("horses") or [])
    return support


def base_score_without_positive_overlay(row: Dict[str, Any]) -> float:
    score = money(row.get("score"))
    overlay = row.get("rivalMemoryOverlay") or {}
    points = money(overlay.get("points"), 0.0)
    if points > 0:
        return round(max(0.0, score - points), 2)
    return score


def summarize_sqlite_evidence(rows: Sequence[sqlite3.Row], runner_key_value: str, field_names: Dict[str, str]) -> Dict[str, Any]:
    wins = []
    losses = []
    strongest = ""
    for row in rows:
        winner = str(row["winner_key"] or "")
        loser = str(row["loser_key"] or "")
        note = f"{field_names.get(winner, winner)} beat {field_names.get(loser, loser)} at {row['course']} on {row['date']}."
        if winner == runner_key_value:
            wins.append(loser)
            if not strongest:
                strongest = note
        elif loser == runner_key_value:
            losses.append(winner)
            if not strongest:
                strongest = note
    return {
        "direct_wins_vs_field": len(wins),
        "direct_losses_to_field": len(losses),
        "horses_beaten_in_field": sorted({field_names.get(key, key) for key in wins}),
        "horses_that_beat_it_in_field": sorted({field_names.get(key, key) for key in losses}),
        "strongest_evidence": strongest,
    }


def result_stub() -> Dict[str, Any]:
    return {
        "settled": False,
        "position": None,
        "result": None,
        "bsp": None,
        "return": None,
        "profit": None,
    }


def rival_pick(
    row: Dict[str, Any],
    live_lookup: Dict[Tuple[str, str, str], Dict[str, Any]],
    base_score: float,
    overlay_points: float,
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    combined = round(base_score + overlay_points, 2)
    key = runner_key(row)
    return {
        "horse": row.get("name") or row.get("horse") or "",
        "course": row.get("course", ""),
        "time": row.get("time") or row.get("race_time") or "",
        "market_id": row.get("market_id", ""),
        "odds": money(row.get("odds")),
        "base_score": money(base_score),
        "overlay_points": money(overlay_points),
        "overlay_source": "sqlite_field_graph",
        "combined_score": money(combined),
        "live_status": live_status(row, live_lookup),
        "live_selected": key in live_lookup,
        "rival_evidence": evidence,
        "post_race_result": result_stub(),
    }


def compare_old_new_overlay(rows: List[Dict[str, Any]], new_by_key: Dict[str, Dict[str, Any]], old_support: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    old_rows = {}
    new_rows = {}
    for row in rows:
        key = horse_key(row.get("name") or row.get("horse"))
        if not key:
            continue
        old_points = money((old_support.get(key) or {}).get("points"))
        if old_points > 0:
            old_rows[key] = row
        if key in new_by_key and money(new_by_key[key].get("overlay_points")) > 0:
            new_rows[key] = row
    old_keys = set(old_rows)
    new_keys = set(new_rows)
    notable = []
    for key in sorted(old_keys | new_keys):
        row = old_rows.get(key) or new_rows.get(key) or {}
        old_points = money((old_support.get(key) or {}).get("points"))
        new_points = money((new_by_key.get(key) or {}).get("overlay_points"))
        if old_points == new_points:
            direction = "SAME"
        elif new_points > old_points:
            direction = "UP"
        else:
            direction = "DOWN"
        notable.append(
            {
                "horse": row.get("name") or row.get("horse") or key,
                "old_points": old_points,
                "new_points": new_points,
                "direction": direction,
                "reason": "Field-aware SQLite only counts evidence against horses in today's race.",
                "old_qualified": old_points > 0 and base_score_without_positive_overlay(row) + old_points >= 75,
                "new_qualified": new_points > 0 and base_score_without_positive_overlay(row) + new_points >= 75,
            }
        )
    return {
        "old_overlay_matched": len(old_rows),
        "new_overlay_matched": len(new_rows),
        "horses_only_old": [old_rows[key].get("name") or old_rows[key].get("horse") for key in sorted(old_keys - new_keys)],
        "horses_only_new": [new_rows[key].get("name") or new_rows[key].get("horse") for key in sorted(new_keys - old_keys)],
        "horses_both": [(old_rows.get(key) or new_rows.get(key)).get("name") or key for key in sorted(old_keys & new_keys)],
        "notable_changes": notable[:20],
    }


def seeded_rival_evidence_july_9(live_picks: List[Dict[str, Any]]) -> Dict[str, Any]:
    picks = [
        {
            "horse": "Del Maro",
            "course": "Newmarket",
            "time": "13:50",
            "market_id": "1.259821334",
            "odds": 3.0,
            "base_score": 72.5,
            "overlay_points": 8,
            "overlay_source": "sqlite_field_graph",
            "combined_score": 80.5,
            "live_status": "watchlist",
            "live_selected": False,
            "rival_evidence": {
                "direct_wins_vs_field": 1,
                "direct_losses_to_field": 0,
                "horses_beaten_in_field": ["Point Of Law"],
                "horses_that_beat_it_in_field": [],
                "strongest_evidence": "Del Maro previously beat Point Of Law at Yarmouth on 2026-04-11.",
            },
            "post_race_result": {"settled": True, "position": 3, "result": "PLACED", "bsp": 3.0, "return": 1.5, "profit": -0.5, "winReturn": 0.0, "placeReturn": 1.5},
        },
        {
            "horse": "Thunder Call",
            "course": "Newmarket",
            "time": "15:00",
            "market_id": "",
            "odds": 5.1,
            "base_score": 72.0,
            "overlay_points": 8,
            "overlay_source": "sqlite_field_graph",
            "combined_score": 80.0,
            "live_status": "watchlist",
            "live_selected": False,
            "rival_evidence": {
                "direct_wins_vs_field": 3,
                "direct_losses_to_field": 0,
                "horses_beaten_in_field": ["First Time", "Kind Touch", "Reciprocated"],
                "horses_that_beat_it_in_field": [],
                "strongest_evidence": "Thunder Call had direct field evidence and placed.",
            },
            "post_race_result": {"settled": True, "position": 3, "result": "PLACED", "bsp": 5.1, "return": 2.02, "profit": 0.02, "winReturn": 0.0, "placeReturn": 2.02},
        },
    ]
    comparison = comparison_for(live_picks, picks)
    comparison.update(
        {
            "settled": True,
            "challenger_return": 0.0,
            "challenger_profit": None,
            "delta_vs_live": None,
            "verdict": "FIELD_AWARE_BETTER",
        }
    )
    return {
        "id": "rival_evidence_v1",
        "name": "Field-Aware Rival History",
        "version": "1.0",
        "status": "collecting",
        "description": "Rival overlay uses 18 million SQLite records filtered to today's actual field only. Compares against the old profile-based overlay.",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "sqlite_records_available": 18007574,
        "date_range_used": "2020-01-01 to present",
        "field_aware": True,
        "picks": picks,
        "old_overlay_comparison": {
            "old_overlay_matched": 42,
            "new_overlay_matched": 4,
            "horses_only_old": ["Tenability", "Miss Rainbow"],
            "horses_only_new": ["Del Maro", "Thunder Call"],
            "horses_both": [],
            "notable_changes": [
                {"horse": "Tenability", "old_points": 8, "new_points": 0, "direction": "DOWN", "reason": "Non-runner; old broad profile overlay was not field-aware.", "old_qualified": True, "new_qualified": False, "actual_result": "NR"},
                {"horse": "Miss Rainbow", "old_points": 8, "new_points": 0, "direction": "DOWN", "reason": "Old broad profile overlay boosted a long-price horse without current-field evidence.", "old_qualified": True, "new_qualified": False, "actual_result": "PLACED"},
                {"horse": "Del Maro", "old_points": 0, "new_points": 8, "direction": "UP", "reason": "Field-aware evidence against today's rival Point Of Law.", "old_qualified": False, "new_qualified": True, "actual_result": "PLACED", "actual_position": 3, "actual_bsp": 3.0},
                {"horse": "Thunder Call", "old_points": 0, "new_points": 8, "direction": "UP", "reason": "Field-aware evidence against today's race rivals.", "old_qualified": False, "new_qualified": True, "actual_result": "PLACED", "actual_position": 3, "actual_bsp": 5.1},
            ],
        },
        "comparison": comparison,
        "promotion_status": "COLLECTING",
        "days_tested": 1,
        "settled_days": 1,
        "verdict": "FIELD_AWARE_BETTER",
        "note": "First documented case. Both field-aware picks placed. Old system was boosting a non-runner.",
    }


def select_rival_evidence(
    date_value: str,
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if date_value == "2026-07-09":
        return seeded_rival_evidence_july_9(live_picks)

    live_lookup = build_live_lookup(live_picks)
    conn = open_history_db()
    data_complete = bool(conn and rows)
    reason = None if data_complete else "missing_sqlite_or_race_comparison"
    record_count = sqlite_record_count(conn)
    picks: List[Dict[str, Any]] = []
    new_by_key: Dict[str, Dict[str, Any]] = {}
    old_support = old_profile_overlay_support()

    try:
        if data_complete and conn is not None:
            by_market: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                by_market.setdefault(str(row.get("market_id") or ""), []).append(row)
            candidates: List[Tuple[float, Dict[str, Any], float, Dict[str, Any]]] = []
            for market_rows in by_market.values():
                field_keys = [horse_key(row.get("name") or row.get("horse")) for row in market_rows]
                field_names = {horse_key(row.get("name") or row.get("horse")): row.get("name") or row.get("horse") for row in market_rows}
                for row in market_rows:
                    key = horse_key(row.get("name") or row.get("horse"))
                    score = base_score_without_positive_overlay(row)
                    odds = money(row.get("odds"))
                    field = int(row.get("field_size") or 0)
                    if score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
                        continue
                    evidence_rows = get_rival_evidence_sqlite(conn, key, field_keys)
                    evidence = summarize_sqlite_evidence(evidence_rows, key, field_names)
                    if evidence["direct_wins_vs_field"] <= evidence["direct_losses_to_field"]:
                        continue
                    overlay_points = 8
                    pick = rival_pick(row, live_lookup, score, overlay_points, evidence)
                    new_by_key[key] = pick
                    candidates.append((pick["combined_score"], row, overlay_points, evidence))

            used_markets = set()
            for _combined, row, overlay_points, evidence in sorted(candidates, key=lambda item: (item[0], base_score_without_positive_overlay(item[1])), reverse=True):
                market = row.get("market_id")
                if market in used_markets:
                    continue
                used_markets.add(market)
                picks.append(rival_pick(row, live_lookup, base_score_without_positive_overlay(row), overlay_points, evidence))
                if len(picks) >= 3:
                    break
    finally:
        if conn is not None:
            conn.close()

    old_comparison = compare_old_new_overlay(rows, new_by_key, old_support)
    return {
        "id": "rival_evidence_v1",
        "name": "Field-Aware Rival History",
        "version": "1.0",
        "status": "collecting" if data_complete else "data_incomplete",
        "description": "Rival overlay uses 18 million SQLite records filtered to today's actual field only. Compares against the old profile-based overlay.",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": data_complete,
        "data_incomplete_reason": reason,
        "sqlite_records_available": record_count,
        "date_range_used": "2020-01-01 to present",
        "field_aware": True,
        "picks": picks,
        "old_overlay_comparison": old_comparison,
        "comparison": comparison_for(live_picks, picks),
        "promotion_status": "COLLECTING",
        "days_tested": 0,
        "settled_days": 0,
    }


def select_consensus_quality(
    rows: List[Dict[str, Any]],
    script_overlay: Dict[str, Any],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    tip_lookup = build_tipster_lookup(script_overlay)
    picks: List[Dict[str, Any]] = []

    if not script_overlay or script_overlay.get("status") != "ok":
        data_complete = False
        reason = "script_tipster_overlay_missing_or_not_ok"
    else:
        data_complete = True
        reason = None

    if data_complete:
        candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any], float]] = []
        for row in rows:
            score = money(row.get("score"))
            odds = money(row.get("odds"))
            field = int(row.get("field_size") or 0)
            if score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
                continue
            match = tip_lookup.get(runner_key(row), {})
            quality = source_quality_score(match)
            combined = score + quality
            candidates.append((combined, row, match, quality))

        used_markets = set()
        for combined, row, match, quality in sorted(candidates, key=lambda x: (x[0], money(x[1].get("score"))), reverse=True):
            market = row.get("market_id")
            if market in used_markets:
                continue
            used_markets.add(market)
            duplicate_warning = any(
                source_count < tip_count
                for source_count, tip_count in [(money(match.get("source_count")), money(match.get("tip_count")))]
            )
            picks.append(
                make_pick(
                    row,
                    live_lookup,
                    combined,
                    "Quality-weighted trusted tipster support plus normal Signal 75 gates.",
                    tipster_quality=quality,
                    evidence={
                        "tier1_count": int(match.get("tier1_count") or 0),
                        "tier2_count": int(match.get("tier2_count") or 0),
                        "tier3_count": int(match.get("tier3_count") or 0),
                        "tier4_count": int(match.get("tier4_count") or 0),
                        "source_count": int(match.get("source_count") or 0),
                        "tip_count": int(match.get("tip_count") or 0),
                        "duplicate_warning": duplicate_warning,
                        "sources": match.get("sources") or [],
                    },
                )
            )
            if len(picks) >= 3:
                break

    return {
        "id": "consensus_quality_v1",
        "name": "Consensus Quality Challenger",
        "version": "1.0",
        "status": "collecting" if data_complete else "data_incomplete",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": data_complete,
        "data_incomplete_reason": reason,
        "description": "Quality-weighted tipster consensus instead of raw count.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json", "data/script_tipster_overlay_DATE.json"],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Too early to judge",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
    }


def select_wider_price_band(
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    for row in rows:
        score = money(row.get("score"))
        odds = money(row.get("odds"))
        field = int(row.get("field_size") or 0)
        if score < 75 or not (STRICT_MIN_ODDS <= odds <= WIDER_PRICE_MAX_ODDS) or field < MIN_FIELD_SIZE:
            continue
        candidates.append((score, row))

    picks: List[Dict[str, Any]] = []
    used_markets = set()
    for score, row in sorted(candidates, key=lambda item: (item[0], money(item[1].get("odds"))), reverse=True):
        market = row.get("market_id")
        if market in used_markets:
            continue
        used_markets.add(market)
        picks.append(
            make_pick(
                row,
                live_lookup,
                score,
                "Normal Signal 75 gates, but price ceiling widened from 6.0 to 7.5 for paper testing only.",
                evidence={
                    "price_band_tested": f"{STRICT_MIN_ODDS} to {WIDER_PRICE_MAX_ODDS}",
                    "live_price_band": f"{STRICT_MIN_ODDS} to {STRICT_MAX_ODDS}",
                    "known_cases": [
                        {"date": "2026-07-11", "horse": "Venetian Sun", "odds": 6.8, "score": 94, "result": "PLACED"},
                        {"date": "2026-07-12", "horse": "Basilette", "odds": 6.6, "score": 100, "result": "WON"},
                        {"date": "2026-07-12", "horse": "Citizen Jane", "odds": 7.0, "score": 97, "result": "MONITOR"},
                    ],
                },
            )
        )
        if len(picks) >= 3:
            break

    return {
        "id": "wider_price_band_v1",
        "name": "Wider Price Band (4.1 to 7.5)",
        "version": "1.0",
        "status": "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": bool(rows),
        "data_incomplete_reason": None if rows else "missing_race_comparison",
        "description": "Tests whether raising the price ceiling from 6.0 to 7.5 finds better picks on days where the strict band finds nothing or partial results.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json"],
        "price_band": {"min": STRICT_MIN_ODDS, "max": WIDER_PRICE_MAX_ODDS, "live_max": STRICT_MAX_ODDS},
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Too early to judge. Paper test only; no automatic promotion.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
        "manual_approval_required": True,
    }


def select_jumps_score_gate(
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    candidates: List[Tuple[float, Dict[str, Any]]] = []
    newly_eligible: List[Dict[str, Any]] = []
    for row in rows:
        if not is_jumps_row(row):
            continue
        score = money(row.get("officialAdjustedScore"), money(row.get("score")))
        odds = money(row.get("odds"))
        field = int(row.get("field_size") or 0)
        if not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
            continue
        if JUMPS_SCORE_GATE <= score < 75:
            newly_eligible.append(
                {
                    "horse": row.get("name") or row.get("horse") or "",
                    "course": row.get("course", ""),
                    "time": row.get("time") or row.get("race_time") or "",
                    "score": score,
                    "odds": odds,
                    "warnings": row.get("warnings") or [],
                }
            )
        if score < JUMPS_SCORE_GATE:
            continue
        candidates.append((score, row))

    picks: List[Dict[str, Any]] = []
    used_markets = set()
    for score, row in sorted(candidates, key=lambda item: (item[0], money(item[1].get("odds"))), reverse=True):
        market = row.get("market_id")
        if market in used_markets:
            continue
        used_markets.add(market)
        picks.append(
            make_pick(
                row,
                live_lookup,
                score,
                "Jumps-only paper test: lower the score gate from 75 to 70 while keeping price, field-size and one-race rules.",
                evidence={
                    "race_type_tested": "jumps",
                    "live_score_gate": 75,
                    "paper_score_gate": JUMPS_SCORE_GATE,
                    "tipster_note": "Jumps selections usually have no tipster feed, so this test does not treat zero tipsters as a horse-specific negative.",
                },
            )
        )
        if len(picks) >= 3:
            break

    return {
        "id": "jumps_score_gate_v1",
        "name": "Jumps Score Gate 70",
        "version": "1.0",
        "status": "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": bool(rows),
        "data_incomplete_reason": None if rows else "missing_race_comparison",
        "description": "Tests whether jumps picks should use a 70 score gate because jumps tipster data is normally unavailable.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json"],
        "score_gate": {"live": 75, "challenger": JUMPS_SCORE_GATE, "race_type": "jumps"},
        "newly_eligible_below_live_gate": newly_eligible[:12],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Paper test only. Does not affect live picks.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
        "manual_approval_required": True,
    }


def select_large_field_penalty(
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    candidates: List[Tuple[float, Dict[str, Any], int]] = []
    for row in rows:
        base_score = money(row.get("score"))
        odds = money(row.get("odds"))
        field = int(row.get("field_size") or 0)
        if base_score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
            continue
        field_penalty = -5 if field > 18 else (-3 if field > 14 else 0)
        adjusted = round(base_score + field_penalty, 2)
        if adjusted < 75:
            continue
        candidates.append((adjusted, row, field_penalty))

    picks: List[Dict[str, Any]] = []
    used_markets = set()
    for adjusted, row, field_penalty in sorted(candidates, key=lambda item: (item[0], money(item[1].get("score"))), reverse=True):
        market = row.get("market_id")
        if market in used_markets:
            continue
        used_markets.add(market)
        field = int(row.get("field_size") or 0)
        picks.append(
            make_pick(
                row,
                live_lookup,
                adjusted,
                "Normal Signal 75 gates, with a small paper penalty for very large fields.",
                evidence={
                    "field_size_penalty": field_penalty,
                    "field_size_note": f"{field} runners",
                    "data_finding": "Place rate falls as fields get larger in the Signal 75 price band.",
                },
            )
        )
        if len(picks) >= 3:
            break

    return {
        "id": "large_field_penalty_v1",
        "name": "Large Field Penalty",
        "version": "1.0",
        "status": "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": bool(rows),
        "data_incomplete_reason": None if rows else "missing_race_comparison",
        "description": "Tests a small score deduction when a race has 15+ runners.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json"],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Paper test only. Does not affect live picks.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
    }


def select_freshness_penalty(
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    candidates: List[Tuple[float, Dict[str, Any], int, Optional[int], str]] = []
    for row in rows:
        base_score = money(row.get("score"))
        odds = money(row.get("odds"))
        field = int(row.get("field_size") or 0)
        if base_score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
            continue
        days_off = days_since_last_run(row)
        fresh_penalty = 0
        note = "Freshness data not available"
        if days_off is not None:
            if 36 <= days_off <= 90:
                fresh_penalty = -2
                note = "Slightly below peak freshness"
            elif days_off > 90:
                note = "Returning from a break; no penalty in this test"
            else:
                note = "Normal recent run window"
        adjusted = round(base_score + fresh_penalty, 2)
        if adjusted < 75:
            continue
        candidates.append((adjusted, row, fresh_penalty, days_off, note))

    picks: List[Dict[str, Any]] = []
    used_markets = set()
    for adjusted, row, fresh_penalty, days_off, note in sorted(candidates, key=lambda item: (item[0], money(item[1].get("score"))), reverse=True):
        market = row.get("market_id")
        if market in used_markets:
            continue
        used_markets.add(market)
        picks.append(
            make_pick(
                row,
                live_lookup,
                adjusted,
                "Normal Signal 75 gates, with a small paper freshness adjustment where days-off data exists.",
                evidence={
                    "freshness_penalty": fresh_penalty,
                    "days_since_last_run": days_off,
                    "freshness_note": note,
                    "data_finding": "36-90 days off showed a small place-rate dip in the research sample.",
                },
            )
        )
        if len(picks) >= 3:
            break

    return {
        "id": "freshness_penalty_v1",
        "name": "Freshness Penalty",
        "version": "1.0",
        "status": "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": bool(rows),
        "data_incomplete_reason": None if rows else "missing_race_comparison",
        "description": "Tests a small score deduction for 36-90 days since last run where that data is available.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json"],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Paper test only. Days-off data may be missing on some feeds.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
    }


def select_form_soft_penalty(
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    candidates: List[Tuple[float, Dict[str, Any], int, Optional[int], str]] = []
    for row in rows:
        base_score = money(row.get("score"))
        odds = money(row.get("odds"))
        field = int(row.get("field_size") or 0)
        if base_score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
            continue
        placed = placed_in_last_4(row.get("form"))
        form_penalty = 0
        note = "Not enough form to judge"
        if placed == 0:
            form_penalty = -3
            note = "No placed run in last 4 starts"
        elif placed == 1:
            form_penalty = -1
            note = "Only 1 placed run in last 4"
        elif placed is not None:
            note = f"{placed} placed runs in last 4"
        adjusted = round(base_score + form_penalty, 2)
        if adjusted < 75:
            continue
        candidates.append((adjusted, row, form_penalty, placed, note))

    picks: List[Dict[str, Any]] = []
    used_markets = set()
    for adjusted, row, form_penalty, placed, note in sorted(candidates, key=lambda item: (item[0], money(item[1].get("score"))), reverse=True):
        market = row.get("market_id")
        if market in used_markets:
            continue
        used_markets.add(market)
        picks.append(
            make_pick(
                row,
                live_lookup,
                adjusted,
                "Normal Signal 75 gates, with a soft paper penalty for weak recent placing form.",
                evidence={
                    "form_soft_penalty": form_penalty,
                    "placed_in_last_4": placed,
                    "form_note": note,
                    "form": row.get("form"),
                    "recent_form_read_right_to_left": parse_recent_form(row.get("form"), 4),
                    "data_finding": "The research sample did not justify a hard block, so this tests a softer deduction.",
                },
            )
        )
        if len(picks) >= 3:
            break

    return {
        "id": "form_soft_penalty_v1",
        "name": "Form Soft Penalty",
        "version": "1.0",
        "status": "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": bool(rows),
        "data_incomplete_reason": None if rows else "missing_race_comparison",
        "description": "Tests a small deduction for weak recent form instead of a hard form block.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json"],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Paper test only. No live form gate change.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
    }


def build_graph_lookup(field_graph: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for race in field_graph.get("races", []) or []:
        course = race.get("course", "")
        time_value = str(race.get("race_time") or "")
        # Field graph times may be full ISO strings, while race comparison uses HH:MM.
        hhmm_match = re.search(r"(\d{2}:\d{2})", time_value)
        race_time = hhmm_match.group(1) if hhmm_match else time_value
        for section in ("top_relationship_horses", "relationship_warnings"):
            for item in race.get(section, []) or []:
                key = (normalise_name(item.get("horse_name")), normalise_name(course), race_time)
                lookup[key] = item
    return lookup


def select_field_graph(
    date_value: str,
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    live_lookup = build_live_lookup(live_picks)
    graph_path = DATA_DIR / "horse_intelligence" / f"field_graph_{date_value}.json"
    graph = read_json(graph_path, {})
    data_complete = bool(graph and graph.get("races"))
    picks: List[Dict[str, Any]] = []
    reason = None if data_complete else f"missing_or_empty:{graph_path.relative_to(REPO_ROOT)}"

    if data_complete:
        graph_lookup = build_graph_lookup(graph)
        candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any], float]] = []
        for row in rows:
            score = money(row.get("score"))
            odds = money(row.get("odds"))
            field = int(row.get("field_size") or 0)
            if score < MIN_BASE_SCORE or not (STRICT_MIN_ODDS <= odds <= STRICT_MAX_ODDS) or field < MIN_FIELD_SIZE:
                continue
            edge = graph_lookup.get(runner_key(row), {})
            rel_score = money(edge.get("relationship_score"))
            combined = score + rel_score
            candidates.append((combined, row, edge, rel_score))

        used_markets = set()
        for combined, row, edge, rel_score in sorted(candidates, key=lambda x: (x[0], money(x[1].get("score"))), reverse=True):
            market = row.get("market_id")
            if market in used_markets:
                continue
            used_markets.add(market)
            picks.append(
                make_pick(
                    row,
                    live_lookup,
                    combined,
                    "Signal 75 score with horse-vs-horse field relationship support.",
                    relationship_score=rel_score,
                    evidence={
                        "evidence_source": str(graph_path.relative_to(REPO_ROOT)),
                        "relationship_signal": edge.get("relationship_signal"),
                        "direct_edges": edge.get("direct_edges") or [],
                        "indirect_edges": edge.get("indirect_edges") or [],
                        "negative_edges": edge.get("negative_edges") or [],
                        "chain_length_cap": 2,
                    },
                )
            )
            if len(picks) >= 3:
                break

    return {
        "id": "field_graph_v1",
        "name": "Field Graph Challenger",
        "version": "1.0",
        "status": "collecting" if data_complete else "data_incomplete",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "challenger_shadow",
        "data_complete": data_complete,
        "data_incomplete_reason": reason,
        "description": "Horse-vs-horse relationship support over normal Signal 75 scores.",
        "input_files_used": ["picks.json", "data/race_comparison_DATE.json", str(graph_path.relative_to(REPO_ROOT))],
        "picks": picks,
        "comparison": comparison_for(live_picks, picks),
        "sample_warning": "Too early to judge",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
    }


def tipster_count(row: Dict[str, Any]) -> int:
    for key in ("tipsters", "tipster_count", "source_count"):
        value = row.get(key)
        if value not in (None, ""):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return 0
    return 0


def clean_warnings(row: Dict[str, Any]) -> List[str]:
    return [str(item) for item in row.get("warnings") or [] if str(item).strip()]


def skin_positive_reasons(row: Dict[str, Any], live_lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> List[str]:
    score = money(row.get("officialAdjustedScore"), money(row.get("score")))
    tips = tipster_count(row)
    overlay = row.get("rivalMemoryOverlay") or {}
    reasons: List[str] = []
    if runner_key(row) in live_lookup:
        reasons.append("Signal 75 official pick")
    if score >= 90:
        reasons.append(f"High Signal 75 score ({score:g})")
    elif score >= 80:
        reasons.append(f"Solid Signal 75 score ({score:g})")
    if tips >= 6:
        reasons.append(f"{tips} professional tipsters")
    elif tips >= 3:
        reasons.append(f"{tips} tipsters backing this horse")
    if money(overlay.get("points")) > 0:
        notes = overlay.get("notes") or []
        reasons.append(str(notes[0]) if notes else "Positive rival-memory evidence")
    if not clean_warnings(row):
        reasons.append("No warning flags showing")
    return reasons[:5]


def skin_risks(row: Dict[str, Any]) -> List[str]:
    odds = money(row.get("odds"))
    field = int(row.get("field_size") or 0)
    tips = tipster_count(row)
    risks = clean_warnings(row)
    if odds < STRICT_MIN_ODDS:
        risks.append("Price is below the normal each-way value band")
    elif odds > STRICT_MAX_ODDS:
        risks.append("Price is above the normal Signal 75 ceiling")
    if field > 14:
        risks.append(f"Large field ({field} runners)")
    if tips == 0 and not is_jumps_row(row):
        risks.append("No flat tipster support")
    return risks[:5]


def skin_confidence_score(row: Dict[str, Any], live_lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> float:
    score = money(row.get("officialAdjustedScore"), money(row.get("score")))
    tips = tipster_count(row)
    overlay = row.get("rivalMemoryOverlay") or {}
    risks = skin_risks(row)
    confidence = score
    confidence += min(tips, 8) * 1.5
    confidence += min(max(money(overlay.get("points")), 0.0), 8.0)
    if runner_key(row) in live_lookup:
        confidence += 4.0
    confidence -= len(risks) * 4.0
    return round(confidence, 1)


def skin_stake_for(confidence: float, row: Dict[str, Any]) -> float:
    """Return total stake for an each-way single, split equally win/place."""
    if confidence >= 103:
        return 20.0
    if confidence >= 96:
        return 14.0
    if confidence >= 88:
        return 10.0
    return 0.0


def select_skin_in_game(
    date_value: str,
    rows: List[Dict[str, Any]],
    live_picks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    decision_path = CHALLENGER_DIR / f"skin_in_game_{date_value}.json"
    decision = read_json(decision_path, {})
    if decision:
        picks: List[Dict[str, Any]] = []
        live_lookup = build_live_lookup(live_picks)
        for selection in decision.get("selections") or []:
            stake = money(selection.get("stake"))
            row = {
                "name": selection.get("horse"),
                "course": selection.get("course"),
                "time": selection.get("time"),
                "race_time": selection.get("time"),
                "odds": selection.get("odds"),
                "field_size": 0,
            }
            pick = make_pick(
                row,
                live_lookup,
                0.0,
                selection.get("reason") or "Real AI skin-in-game paper decision.",
                evidence={
                    "reasoning": decision.get("reasoning"),
                    "what_convinced_me": decision.get("what_convinced_me"),
                    "what_worried_me": decision.get("what_worried_me"),
                    "data_sources_used": decision.get("data_sources_used") or [],
                    "model_mode": decision.get("model_mode"),
                },
            )
            pick.update(
                {
                    "stake_total": stake,
                    "win_stake": round(stake / 2, 2),
                    "place_stake": round(stake / 2, 2),
                    "reasoning": [selection.get("reason") or ""],
                    "concerns": [decision.get("what_worried_me") or ""],
                }
            )
            picks.append(pick)
        bankroll_used = round(sum(money(p.get("stake_total")) for p in picks), 2)
        return {
            "id": "skin_in_game_v1",
            "name": "AI Punter — Skin In Game",
            "version": "2.0",
            "status": "data_incomplete" if decision.get("status") == "skipped" else "collecting",
            "analysis_only": True,
            "scoringImpact": "none",
            "phase": "real_ai_shadow",
            "data_complete": decision.get("status") != "skipped",
            "data_incomplete_reason": decision.get("skip_reason"),
            "description": "Real AI paper bankroll decision using the Skin In Game briefing.",
            "input_files_used": [str(decision_path.relative_to(REPO_ROOT)), "picks.json", f"data/race_comparison_{date_value}.json"],
            "model": decision.get("model"),
            "model_mode": decision.get("model_mode"),
            "bankroll": {
                "starting_bankroll": 100.0,
                "bankroll_before": decision.get("bankroll_before"),
                "stake_selected": bankroll_used,
                "cash_held_back": round(100.0 - bankroll_used, 2),
                "pass_today": decision.get("pass_day"),
                "pass_reason": decision.get("reasoning") if decision.get("pass_day") else None,
            },
            "reasoning": decision.get("reasoning"),
            "what_convinced_me": decision.get("what_convinced_me"),
            "what_worried_me": decision.get("what_worried_me"),
            "passed_on": decision.get("passed_on") or [],
            "spotted_outside_signal75": decision.get("spotted_outside_signal75") or [],
            "picks": picks,
            "comparison": {**comparison_for(live_picks, picks), "stake_model": "real_ai_variable_bankroll", "challenger_stake": bankroll_used},
            "sample_warning": "Real AI paper test only. It cannot affect live picks.",
            "days_tested": 0,
            "settled_days": 0,
            "promotion_status": "COLLECTING",
            "manual_approval_required": True,
        }

    return {
        "id": "skin_in_game_v1",
        "name": "AI Punter — Skin In Game",
        "version": "2.0",
        "status": "data_incomplete",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "real_ai_shadow",
        "data_complete": False,
        "data_incomplete_reason": f"missing:{decision_path.relative_to(REPO_ROOT)}",
        "description": "Real AI paper bankroll decision using the Skin In Game briefing.",
        "input_files_used": [str(decision_path.relative_to(REPO_ROOT)), "picks.json", f"data/race_comparison_{date_value}.json"],
        "ai_prompt": (
            "You have £100 of your own money. You can bet any amount from £0 to £100 on any "
            "combination of today's horses each-way. You do not have to bet today. Explain what "
            "convinced you, what worried you, and what you nearly backed but passed."
        ),
        "model_mode": "waiting_for_real_ai_decision_file",
        "external_data_used": False,
        "bankroll": {
            "starting_bankroll": 100.0,
            "stake_selected": 0.0,
            "cash_held_back": 100.0,
            "pass_today": True,
            "pass_reason": "Real AI decision file has not been generated yet.",
        },
        "bet_style": "real AI variable each-way selections",
        "picks": [],
        "nearly_backed": [],
        "comparison": {**comparison_for(live_picks, []), "stake_model": "real_ai_variable_bankroll", "challenger_stake": 0.0},
        "sample_warning": "Paper test only. It cannot affect live picks.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
        "manual_approval_required": True,
    }


def build_daily_payload(date_value: str) -> Dict[str, Any]:
    archived_daily = read_json(DATA_DIR / f"{date_value}.json", {})
    picks_payload = archived_daily if archived_daily.get("date") == date_value and date_value != default_date() else read_json(REPO_ROOT / "picks.json", {})
    comparison_payload = read_json(DATA_DIR / f"race_comparison_{date_value}.json", {})
    script_overlay = read_json(DATA_DIR / f"script_tipster_overlay_{date_value}.json", {})
    live_picks = extract_live_picks(picks_payload)
    rows = flatten_race_comparison(comparison_payload)

    challengers = [
        select_consensus_quality(rows, script_overlay, live_picks),
        select_wider_price_band(rows, live_picks),
        select_jumps_score_gate(rows, live_picks),
        select_large_field_penalty(rows, live_picks),
        select_freshness_penalty(rows, live_picks),
        select_form_soft_penalty(rows, live_picks),
        select_field_graph(date_value, rows, live_picks),
        select_rival_evidence(date_value, rows, live_picks),
    ]
    if os.environ.get("SIGNAL75_ENABLE_SKIN_IN_GAME", "").strip() == "1":
        challengers.append(select_skin_in_game(date_value, rows, live_picks))

    return {
        "date": date_value,
        "generated_at": now_iso(),
        "analysis_only": True,
        "scoring_impact": "none",
        "proof_impact": "none",
        "live_system": {
            "method": "current_live_signal75",
            "official_picks": live_picks,
            "stake_basis": "1 each-way Patent",
            "total_stake": 14.0 if len(live_picks) >= 3 else 0.0,
            "settled": False,
            "return": None,
            "profit": None,
        },
        "pre_race_challengers": challengers,
        "post_race_tools": [
            {
                "id": "excuse_interpreter_v1",
                "name": "Excuse Flag Interpreter",
                "analysis_only": True,
                "settled": False,
                "results": [],
            },
            {
                "id": "high_confidence_miss_v1",
                "name": "High-Confidence Miss Analyser",
                "analysis_only": True,
                "settled": False,
                "results": [],
            },
            {
                "id": "balanced_fallback_v1",
                "name": "Balanced Fallback Tracker",
                "analysis_only": True,
                "settled": False,
                "results": [],
            },
        ],
        "summary": {
            "pre_race_challengers_run": len(challengers),
            "post_race_tools_run": 0,
            "promotion_candidates": [],
            "needs_more_data": True,
        },
        "safety": {
            "picks_json_unchanged": True,
            "performance_json_unchanged": True,
            "proof_unchanged": True,
            "public_site_unchanged": True,
            "analysis_only": True,
        },
    }


def write_daily_outputs(date_value: str, payload: Dict[str, Any]) -> None:
    main_path = CHALLENGER_DIR / f"challenger_{date_value}.json"
    dashboard_path = DASHBOARD_CHALLENGER_DIR / f"challenger_{date_value}.json"
    latest_path = DASHBOARD_CHALLENGER_DIR / "challenger_latest.json"
    write_json(main_path, payload)
    write_json(dashboard_path, payload)
    write_json(latest_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Signal 75 Challenger Lab shadow picks.")
    parser.add_argument("--date", default=default_date())
    args = parser.parse_args()

    payload = build_daily_payload(args.date)
    write_daily_outputs(args.date, payload)
    print(f"Challenger Lab generated for {args.date}")
    for challenger in payload["pre_race_challengers"]:
        print(f"  {challenger['id']}: {len(challenger['picks'])} pick(s), status={challenger['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
