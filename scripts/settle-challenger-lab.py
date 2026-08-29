#!/usr/bin/env python3
"""
Signal 75 Challenger Lab - settlement and post-race learning.

This updates only data/challenger_lab and dashboard/data/challenger_lab files.
It never writes official picks, proof or performance.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

from signal75_intelligence_store import FORM_ARCHIVE_DB


REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA_DIR = REPO_ROOT / "data"
CHALLENGER_DIR = DATA_DIR / "challenger_lab"
DASHBOARD_CHALLENGER_DIR = REPO_ROOT / "dashboard" / "data" / "challenger_lab"
STAKE_EW = 1.0
TOTAL_PATENT_STAKE = 14.0
TOTAL_LUCKY15_STAKE = 30.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_name(value: Any) -> str:
    text = str(value or "").lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalise_time(value: Any) -> str:
    match = re.search(r"(\d{1,2}):(\d{2})", str(value or ""))
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else str(value or "").strip()


def uk_local_time(date_value: str, value: Any) -> str:
    """Convert archived UTC off-times to the UK racecard time used pre-race."""
    try:
        utc_value = datetime.fromisoformat(f"{date_value}T{normalise_time(value)}:00+00:00")
        return utc_value.astimezone(ZoneInfo("Europe/London")).strftime("%H:%M")
    except (TypeError, ValueError):
        return normalise_time(value)


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


def default_place_fraction(runners: Any) -> float:
    try:
        value = int(runners)
    except (TypeError, ValueError):
        value = 8
    return 0.20 if value >= 16 else 0.25


def calculate_ew_return(odds: Any, result: str, runners: Any) -> Tuple[float, float, float]:
    decimal_odds = money(odds, 0.0)
    if decimal_odds <= 1:
        return 0.0, 0.0, 0.0
    place_frac = default_place_fraction(runners)
    place_multiplier = 1 + (decimal_odds - 1) * place_frac
    result = str(result or "").upper()
    if result == "WON":
        win_return = decimal_odds * STAKE_EW
        place_return = place_multiplier * STAKE_EW
    elif result == "PLACED":
        win_return = 0.0
        place_return = place_multiplier * STAKE_EW
    elif result == "VOID":
        win_return = STAKE_EW
        place_return = STAKE_EW
    else:
        win_return = 0.0
        place_return = 0.0
    return round(win_return, 2), round(place_return, 2), round(win_return + place_return, 2)


def calculate_patent_from_returns(results: List[Dict[str, Any]]) -> Tuple[float, float]:
    if len(results) < 3:
        return 0.0, 0.0
    picks = [{"win": money(r.get("winReturn")), "place": money(r.get("placeReturn"))} for r in results[:3]]
    h1, h2, h3 = picks
    singles = sum(h["win"] + h["place"] for h in picks)
    d1w = (h1["win"] * h2["win"]) / STAKE_EW if h1["win"] and h2["win"] else 0
    d1p = (h1["place"] * h2["place"]) / STAKE_EW if h1["place"] and h2["place"] else 0
    d2w = (h1["win"] * h3["win"]) / STAKE_EW if h1["win"] and h3["win"] else 0
    d2p = (h1["place"] * h3["place"]) / STAKE_EW if h1["place"] and h3["place"] else 0
    d3w = (h2["win"] * h3["win"]) / STAKE_EW if h2["win"] and h3["win"] else 0
    d3p = (h2["place"] * h3["place"]) / STAKE_EW if h2["place"] and h3["place"] else 0
    tw = (h1["win"] * h2["win"] * h3["win"]) / STAKE_EW**2 if all(h["win"] for h in picks) else 0
    tp = (h1["place"] * h2["place"] * h3["place"]) / STAKE_EW**2 if all(h["place"] for h in picks) else 0
    total = round(singles + d1w + d1p + d2w + d2p + d3w + d3p + tw + tp, 2)
    return total, round(total - TOTAL_PATENT_STAKE, 2)


def calculate_standard_proof_bet(results: List[Dict[str, Any]]) -> Tuple[float, float, str]:
    """Price the same £14 Single/Double/Patent structure used by live proof."""
    picks = [{"win": money(row.get("winReturn")), "place": money(row.get("placeReturn"))} for row in results]
    if len(picks) == 1:
        total = round(7.0 * (picks[0]["win"] + picks[0]["place"]), 2)
        return total, round(total - TOTAL_PATENT_STAKE, 2), "each_way_single"
    if len(picks) == 2:
        total = round(7.0 * ((picks[0]["win"] * picks[1]["win"]) + (picks[0]["place"] * picks[1]["place"])), 2)
        return total, round(total - TOTAL_PATENT_STAKE, 2), "each_way_double"
    if len(picks) == 3:
        total, profit = calculate_patent_from_returns(results)
        return total, profit, "each_way_patent"
    return 0.0, 0.0, "no_bet"


def calculate_lucky15_from_returns(results: List[Dict[str, Any]]) -> Tuple[float, float]:
    if len(results) != 4:
        return 0.0, 0.0
    picks = [{"win": money(row.get("winReturn")), "place": money(row.get("placeReturn"))} for row in results]
    total = 0.0
    for side in ("win", "place"):
        for size in range(1, 5):
            for combo in combinations(picks, size):
                value = 1.0
                for pick in combo:
                    value *= pick[side]
                total += value
    total = round(total, 2)
    return total, round(total - TOTAL_LUCKY15_STAKE, 2)


def calculate_scaled_ew_return(odds: Any, result: str, runners: Any, win_stake: Any, place_stake: Any) -> Tuple[float, float, float]:
    decimal_odds = money(odds, 0.0)
    win_unit = money(win_stake, 0.0)
    place_unit = money(place_stake, 0.0)
    if decimal_odds <= 1 or (win_unit <= 0 and place_unit <= 0):
        return 0.0, 0.0, 0.0
    place_frac = default_place_fraction(runners)
    place_multiplier = 1 + decimal_odds * place_frac
    result = str(result or "").upper()
    if result == "WON":
        win_return = decimal_odds * win_unit
        place_return = place_multiplier * place_unit
    elif result == "PLACED":
        win_return = 0.0
        place_return = place_multiplier * place_unit
    elif result == "VOID":
        win_return = win_unit
        place_return = place_unit
    else:
        win_return = 0.0
        place_return = 0.0
    return round(win_return, 2), round(place_return, 2), round(win_return + place_return, 2)


def result_from_position(position: Any) -> Optional[str]:
    try:
        pos = int(position)
    except (TypeError, ValueError):
        return None
    if pos <= 0:
        return None
    if pos == 1:
        return "WON"
    if pos <= 4:
        return "PLACED"
    return "LOST"


def result_lookup(day_payload: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def add(horse: Dict[str, Any], course: str, race_time: str, race: Dict[str, Any]) -> None:
        name = horse.get("name") or horse.get("horse")
        if not name:
            return
        result = horse.get("result") or horse.get("radarResult") or result_from_position(horse.get("position"))
        key = (normalise_name(name), normalise_name(course), normalise_time(race_time))
        lookup[key] = {
            "result": str(result or "").upper() if result else None,
            "position": horse.get("position"),
            "bsp": horse.get("bsp") or horse.get("odds"),
            "odds": horse.get("odds"),
            "runners": race.get("runners") or horse.get("field_size"),
            "race_comment": horse.get("race_comment") or horse.get("comment") or "",
        }

    for section in ("flat", "jumps", "topRated", "topRatedFlat", "topRatedJumps"):
        for race in day_payload.get(section, []) or []:
            if "horses" in race:
                for horse in race.get("horses") or []:
                    add(horse, race.get("course") or race.get("venue") or "", race.get("time") or "", race)
            else:
                add(race, race.get("course") or race.get("venue") or "", race.get("time") or "", race)

    for section in ("flat", "jumps"):
        for row in (day_payload.get("results") or {}).get(section, []) or []:
            add(row, row.get("course") or row.get("venue") or "", row.get("time") or "", row)
    return lookup


def archive_result_lookup(date_value: str) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Load non-official runner outcomes for paper-test settlement only."""
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    if not FORM_ARCHIVE_DB.exists():
        return lookup
    conn = sqlite3.connect(str(FORM_ARCHIVE_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT horse_name, course, off_time, position, runners, sp_decimal
            FROM form_results
            WHERE date = ?
            """,
            (date_value,),
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        try:
            position = int(row["position"])
        except (TypeError, ValueError):
            continue
        runners = int(row["runners"] or 0)
        place_cutoff = 4 if runners >= 16 else (3 if runners >= 8 else (2 if runners >= 5 else 1))
        result = "WON" if position == 1 else ("PLACED" if position <= place_cutoff else "LOST")
        result_row = {
            "result": result,
            "position": position,
            "bsp": None,
            "odds": row["sp_decimal"],
            "runners": runners,
            "race_comment": "",
            "settlement_source": "form_history_archive",
        }
        base_key = (normalise_name(row["horse_name"]), normalise_name(row["course"]), normalise_time(row["off_time"]))
        local_key = (normalise_name(row["horse_name"]), normalise_name(row["course"]), uk_local_time(date_value, row["off_time"]))
        lookup[base_key] = result_row
        lookup[local_key] = result_row
    return lookup


def pick_key(pick: Dict[str, Any]) -> Tuple[str, str, str]:
    return (normalise_name(pick.get("horse")), normalise_name(pick.get("course")), normalise_time(pick.get("time")))


def classify_excuses(comment: str, result: str) -> List[str]:
    text = str(comment or "").lower()
    flags: List[str] = []
    checks = [
        ("HAMPERED", ("hampered", "bumped", "checked")),
        ("BLOCKED_RUN", ("blocked", "short of room")),
        ("NO_CLEAR_RUN", ("no clear run", "not clear run")),
        ("SLOW_START", ("slowly away", "dwelt", "missed break")),
        ("PULLED_HARD", ("pulled hard", "keen", "over-raced", "over raced")),
        ("EASED", ("eased", "not pushed")),
        ("FELL", ("fell",)),
        ("UNSEATED", ("unseated",)),
        ("REFUSED", ("refused",)),
        ("PULLED_UP", ("pulled up",)),
        ("TRAVELLED_WELL_NO_FINISH", ("travelled well", "no response", "weakened")),
    ]
    for label, needles in checks:
        if any(needle in text for needle in needles):
            flags.append(label)
    if not flags:
        flags.append("NO_OBVIOUS_EXCUSE" if result in {"LOST", "PLACED"} else "UNKNOWN")
    return flags


def settle_challenger(challenger: Dict[str, Any], lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> None:
    settled_rows: List[Dict[str, Any]] = []
    all_settled = True
    variable_bankroll = challenger.get("id") == "skin_in_game_v1"
    variable_return = 0.0
    variable_stake = 0.0
    for pick in challenger.get("picks", []) or []:
        found = lookup.get(pick_key(pick))
        post = pick.setdefault("post_race_result", {})
        if not found or not found.get("result"):
            if challenger.get("id") == "rival_evidence_v1" and post.get("settled"):
                pick.update(
                    {
                        "settled": True,
                        "position": post.get("position"),
                        "result": post.get("result"),
                        "bsp": post.get("bsp"),
                        "return": post.get("return"),
                        "profit": post.get("profit"),
                    }
                )
                settled_rows.append(
                    {
                        "winReturn": post.get("winReturn", 0.0),
                        "placeReturn": post.get("placeReturn", post.get("return", 0.0)),
                    }
                )
                continue
            all_settled = False
            post.update({"settled": False})
            pick.update(
                {
                    "settled": False,
                    "position": None,
                    "result": None,
                    "return": None,
                }
            )
            continue
        result = found.get("result")
        if variable_bankroll:
            stake_total = money(pick.get("stake_total"), money(pick.get("win_stake")) + money(pick.get("place_stake")))
            win_return, place_return, total_return = calculate_scaled_ew_return(
                pick.get("odds") or found.get("bsp"),
                result,
                found.get("runners") or pick.get("field_size"),
                pick.get("win_stake"),
                pick.get("place_stake"),
            )
            profit = round(total_return - stake_total, 2)
            variable_stake = round(variable_stake + stake_total, 2)
            variable_return = round(variable_return + total_return, 2)
        else:
            win_return, place_return, total_return = calculate_ew_return(pick.get("odds") or found.get("bsp"), result, found.get("runners") or pick.get("field_size"))
            profit = round(total_return - 2.0, 2)
        post.update(
            {
                "settled": True,
                "position": found.get("position"),
                "result": result,
                "bsp": found.get("bsp"),
                "return": total_return,
                "profit": profit,
                "winReturn": win_return,
                "placeReturn": place_return,
                "excuse_flags": classify_excuses(found.get("race_comment"), result),
            }
        )
        pick.update(
            {
                "settled": True,
                "position": found.get("position"),
                "result": result,
                "bsp": found.get("bsp"),
                "return": total_return,
                "profit": profit,
            }
        )
        settled_rows.append(post)

    proof_return, proof_profit, proof_bet_type = calculate_standard_proof_bet(settled_rows)
    lucky15 = challenger.get("id") == "lucky15_v1"
    lucky15_return, lucky15_profit = calculate_lucky15_from_returns(settled_rows) if lucky15 else (0.0, 0.0)
    comparison = challenger.setdefault("comparison", {})
    comparison["settled"] = all_settled and (bool(challenger.get("picks")) or variable_bankroll)
    if variable_bankroll:
        variable_profit = round(variable_return - variable_stake, 2)
        comparison["challenger_stake"] = variable_stake
        comparison["challenger_profit"] = variable_profit if comparison["settled"] else None
        comparison["challenger_return"] = variable_return if comparison["settled"] else None
        bankroll = challenger.setdefault("bankroll", {})
        if comparison["settled"]:
            bankroll["settled_return"] = variable_return
            bankroll["profit_loss"] = variable_profit
            bankroll["ending_bankroll_if_bet"] = round(100.0 - variable_stake + variable_return, 2)
    elif lucky15:
        comparison["challenger_stake"] = TOTAL_LUCKY15_STAKE
        comparison["challenger_profit"] = lucky15_profit if comparison["settled"] else None
        comparison["challenger_return"] = lucky15_return if comparison["settled"] else None
    elif comparison["settled"] and comparison.get("same_as_live") is True and comparison.get("live_profit") is not None:
        live_profit = money(comparison.get("live_profit"))
        live_return = round(TOTAL_PATENT_STAKE + live_profit, 2)
        comparison["challenger_profit"] = live_profit
        comparison["challenger_return"] = live_return
        comparison["delta_vs_live"] = 0.0
    else:
        comparison["challenger_stake"] = TOTAL_PATENT_STAKE
        comparison["bet_type"] = proof_bet_type
        comparison["challenger_profit"] = proof_profit if comparison["settled"] else None
        comparison["challenger_return"] = proof_return if comparison["settled"] else None
    if comparison.get("live_profit") is not None and comparison["settled"]:
        comparison["delta_vs_live"] = round(money(comparison.get("challenger_profit")) - money(comparison.get("live_profit")), 2)
    challenger["settled_days"] = 1 if comparison["settled"] else 0
    settle_rival_evidence_comparison(challenger, lookup)


def settle_rival_evidence_comparison(challenger: Dict[str, Any], lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> None:
    if challenger.get("id") != "rival_evidence_v1":
        return
    old_comparison = challenger.get("old_overlay_comparison") or {}
    pick_context = {
        normalise_name(pick.get("horse")): pick
        for pick in challenger.get("picks", []) or []
        if pick.get("horse")
    }
    for row in old_comparison.get("notable_changes", []) or []:
        horse = row.get("horse")
        context = pick_context.get(normalise_name(horse), {})
        found = None
        if context:
            found = lookup.get(pick_key(context))
        if not found:
            matches = [
                value
                for key, value in lookup.items()
                if key[0] == normalise_name(horse)
            ]
            found = matches[0] if matches else None
        if found and found.get("result"):
            row["actual_result"] = found.get("result")
            row["actual_position"] = found.get("position")
            row["actual_bsp"] = found.get("bsp")
        elif row.get("actual_result"):
            continue
        else:
            row["actual_result"] = None
            row["actual_position"] = None
            row["actual_bsp"] = None


def settle_live_system(payload: Dict[str, Any], day_payload: Dict[str, Any]) -> None:
    results = day_payload.get("results") or {}
    complete = bool(results.get("complete"))
    payload["live_system"]["settled"] = complete
    payload["live_system"]["return"] = money(results.get("patentReturn")) if complete else None
    payload["live_system"]["profit"] = money(results.get("patentProfit")) if complete else None
    for challenger in payload.get("pre_race_challengers", []) or []:
        comparison = challenger.setdefault("comparison", {})
        comparison["live_profit"] = payload["live_system"]["profit"] if complete else None
        if comparison.get("challenger_profit") is not None and payload["live_system"]["profit"] is not None:
            comparison["delta_vs_live"] = round(money(comparison.get("challenger_profit")) - money(payload["live_system"]["profit"]), 2)


def settle_skin_in_game_file(date_value: str, lookup: Dict[Tuple[str, str, str], Dict[str, Any]]) -> Dict[str, Any]:
    path = CHALLENGER_DIR / f"skin_in_game_{date_value}.json"
    decision = read_json(path, {})
    if not decision:
        return {}
    total_return = 0.0
    total_stake = 0.0
    all_settled = True
    for selection in decision.get("selections") or []:
        key = (
            normalise_name(selection.get("horse")),
            normalise_name(selection.get("course")),
            str(selection.get("time") or "").strip(),
        )
        found = lookup.get(key)
        stake = money(selection.get("stake"))
        total_stake = round(total_stake + stake, 2)
        if not found or not found.get("result"):
            selection.update({"settled": False, "result": None, "return": 0.0, "profit": 0.0})
            all_settled = False
            continue
        result = found.get("result")
        win_return, place_return, total = calculate_scaled_ew_return(
            selection.get("odds") or found.get("bsp"),
            result,
            found.get("runners"),
            round(stake / 2, 2),
            round(stake / 2, 2),
        )
        profit = round(total - stake, 2)
        total_return = round(total_return + total, 2)
        selection.update(
            {
                "settled": True,
                "position": found.get("position"),
                "result": result,
                "bsp": found.get("bsp"),
                "return": total,
                "profit": profit,
                "winReturn": win_return,
                "placeReturn": place_return,
            }
        )
    if not decision.get("selections"):
        all_settled = True
    profit = round(total_return - total_stake, 2)
    decision["settled"] = all_settled
    decision["return"] = total_return
    decision["profit"] = profit
    decision["result"] = "PASSED" if not decision.get("selections") else ("SETTLED" if all_settled else "UNSETTLED")
    decision["bankroll_after"] = round(money(decision.get("bankroll_before"), 100.0) - total_stake + total_return, 2)
    decision["settled_at"] = now_iso() if all_settled else None
    write_json(path, decision)
    return decision


def build_post_race_tools(payload: Dict[str, Any]) -> None:
    excuse_results = []
    miss_results = []
    for challenger in payload.get("pre_race_challengers", []) or []:
        for pick in challenger.get("picks", []) or []:
            post = pick.get("post_race_result") or {}
            if post.get("settled"):
                excuse_results.append(
                    {
                        "challenger": challenger.get("id"),
                        "horse": pick.get("horse"),
                        "result": post.get("result"),
                        "excuse_flags": post.get("excuse_flags") or [],
                    }
                )
                if money(pick.get("base_score")) >= 90 and post.get("result") not in {"WON", "PLACED", "VOID"}:
                    miss_results.append(
                        {
                            "challenger": challenger.get("id"),
                            "horse": pick.get("horse"),
                            "base_score": pick.get("base_score"),
                            "result": post.get("result"),
                            "caution_flags": pick.get("live_rejection_reasons") or [],
                            "excuse_flags": post.get("excuse_flags") or [],
                        }
                    )

    live_count = len(payload.get("live_system", {}).get("official_picks") or [])
    fallback_results = []
    if live_count < 3:
        fallback_results.append(
            {
                "live_pick_count": live_count,
                "message": "Live system produced fewer than three official picks; fallback remains analysis-only.",
            }
        )

    payload["post_race_tools"] = [
        {
            "id": "excuse_interpreter_v1",
            "name": "Excuse Flag Interpreter",
            "analysis_only": True,
            "settled": True,
            "results": excuse_results,
        },
        {
            "id": "high_confidence_miss_v1",
            "name": "High-Confidence Miss Analyser",
            "analysis_only": True,
            "settled": True,
            "results": miss_results,
        },
        {
            "id": "balanced_fallback_v1",
            "name": "Balanced Fallback Tracker",
            "analysis_only": True,
            "settled": True,
            "results": fallback_results,
        },
    ]
    payload["summary"]["post_race_tools_run"] = len(payload["post_race_tools"])


def settle_payload(date_value: str) -> Dict[str, Any]:
    challenger_path = CHALLENGER_DIR / f"challenger_{date_value}.json"
    payload = read_json(challenger_path, {})
    if not payload:
        raise FileNotFoundError(f"Missing Challenger Lab daily file: {challenger_path}")
    day_payload = read_json(DATA_DIR / f"{date_value}.json", {})
    lookup = result_lookup(day_payload)
    for key, value in archive_result_lookup(date_value).items():
        lookup.setdefault(key, value)
    for challenger in payload.get("pre_race_challengers", []) or []:
        settle_challenger(challenger, lookup)
    settle_live_system(payload, day_payload)
    skin_decision = settle_skin_in_game_file(date_value, lookup)
    if skin_decision:
        for challenger in payload.get("pre_race_challengers", []) or []:
            if challenger.get("id") == "skin_in_game_v1":
                challenger["skin_in_game_file"] = f"data/challenger_lab/skin_in_game_{date_value}.json"
                challenger["bankroll"] = {**(challenger.get("bankroll") or {}), "bankroll_after": skin_decision.get("bankroll_after")}
                break
    build_post_race_tools(payload)
    payload["settled_at"] = now_iso()
    return payload


def write_outputs(date_value: str, payload: Dict[str, Any]) -> None:
    write_json(CHALLENGER_DIR / f"challenger_{date_value}.json", payload)
    write_json(DASHBOARD_CHALLENGER_DIR / f"challenger_{date_value}.json", payload)
    write_json(DASHBOARD_CHALLENGER_DIR / "challenger_latest.json", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Settle Signal 75 Challenger Lab shadow records.")
    parser.add_argument("--date", default=default_date())
    args = parser.parse_args()

    payload = settle_payload(args.date)
    write_outputs(args.date, payload)
    print(f"Challenger Lab settled for {args.date}")
    for challenger in payload.get("pre_race_challengers", []) or []:
        comparison = challenger.get("comparison") or {}
        print(f"  {challenger.get('id')}: settled={comparison.get('settled')} profit={comparison.get('challenger_profit')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
