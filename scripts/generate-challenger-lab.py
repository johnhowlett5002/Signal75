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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = REPO_ROOT / "data"
CHALLENGER_DIR = DATA_DIR / "challenger_lab"
DASHBOARD_CHALLENGER_DIR = REPO_ROOT / "dashboard" / "data" / "challenger_lab"

STRICT_MIN_ODDS = 4.1
STRICT_MAX_ODDS = 6.0
WIDE_MIN_ODDS = 2.75
WIDE_MAX_ODDS = 8.0
MIN_FIELD_SIZE = 8
MIN_BASE_SCORE = 70.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_name(value: Any) -> str:
    text = str(value or "").lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
            if score < MIN_BASE_SCORE or not (WIDE_MIN_ODDS <= odds <= WIDE_MAX_ODDS) or field < MIN_FIELD_SIZE:
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


def build_daily_payload(date_value: str) -> Dict[str, Any]:
    picks_payload = read_json(REPO_ROOT / "picks.json", {})
    comparison_payload = read_json(DATA_DIR / f"race_comparison_{date_value}.json", {})
    script_overlay = read_json(DATA_DIR / f"script_tipster_overlay_{date_value}.json", {})
    live_picks = extract_live_picks(picks_payload)
    rows = flatten_race_comparison(comparison_payload)

    challengers = [
        select_consensus_quality(rows, script_overlay, live_picks),
        select_field_graph(date_value, rows, live_picks),
    ]

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
