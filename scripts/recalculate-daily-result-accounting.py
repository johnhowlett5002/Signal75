#!/usr/bin/env python3
"""
Recalculate stored daily result money from settled pick legs.

This is for accountancy repairs only: it uses existing stored positions/results
plus verified bookmaker settlement overrides. It does not fetch new results and
does not change selections.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
UPDATE_SCRIPT = REPO / "scripts" / "update-results-mac.py"


def load_results_module():
    spec = importlib.util.spec_from_file_location("signal75_update_results", UPDATE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {UPDATE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result_lookup(results: Dict[str, Any], section: str) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for row in results.get(section, []) or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip().upper()
        if name:
            lookup[name] = row
    return lookup


def recalc_section(day: Dict[str, Any], section: str, helpers: Any) -> List[Dict[str, Any]]:
    results = day.get("results", {}) if isinstance(day.get("results"), dict) else {}
    existing = result_lookup(results, section)
    overrides = helpers.load_bookmaker_price_overrides(day.get("date"))
    recalculated: List[Dict[str, Any]] = []

    for race in day.get(section, []) or []:
        if not isinstance(race, dict):
            continue
        horses = [h for h in race.get("horses", []) or [] if isinstance(h, dict)]
        if not horses:
            continue
        horse = horses[0]
        name = str(horse.get("name") or "").strip()
        old = existing.get(name.upper())
        if not old:
            continue

        position = old.get("position", horse.get("position", 0))
        stored_result = str(old.get("result") or horse.get("result") or "").upper()
        runners = int(old.get("ran") or old.get("runners") or race.get("runners") or 8)
        locked_odds = float(horse.get("odds", old.get("lockedSignalPrice", old.get("odds", 0))) or 0)
        odds = float(old.get("settlementOdds", old.get("odds", locked_odds)) or locked_odds)
        place_fraction = old.get("placeFraction")
        places_paid = old.get("placesPaid")

        override = helpers.find_bookmaker_override(
            overrides,
            horse.get("name"),
            race.get("course"),
            race.get("time"),
        )
        rule4 = 0.0
        odds_before_rule4 = None
        bookmaker_odds_text = old.get("bookmakerOddsText")
        bookmaker = old.get("bookmaker", "")
        settlement_source = old.get("settlementOddsSource", horse.get("oddsSource", ""))
        each_way_terms = old.get("eachWayTerms")

        if override:
            override_odds = helpers.parse_fractional_odds(override.get("odds") or override.get("price"))
            rule4 = helpers.parse_rule4_deduction(
                override.get("rule4Deduction")
                if override.get("rule4Deduction") is not None
                else override.get("rule4")
                if override.get("rule4") is not None
                else override.get("rule4Percent")
            )
            if override_odds:
                odds_before_rule4 = override_odds
                odds = helpers.apply_rule4_to_profit_odds(override_odds, rule4)
                bookmaker_odds_text = str(override.get("odds") or override.get("price") or "")
                bookmaker = override.get("bookmaker", "")
                settlement_source = override.get("source", "bookmaker_override")
            if override.get("placeFraction") is not None:
                place_fraction = float(override.get("placeFraction"))
            places = helpers.parse_each_way_places(
                override.get("placesPaid"),
                override.get("placePlaces"),
                override.get("eachWayPlaces"),
                override.get("ewPlaces"),
                override.get("eachWayTerms"),
            )
            if places:
                places_paid = places
            each_way_terms = override.get("eachWayTerms", each_way_terms)

        result = helpers.determine_result(position, old.get("status", ""), runners, places_paid)
        if result == "PENDING" and stored_result and stored_result != "PENDING":
            result = stored_result

        locked_w, locked_p, locked_t = helpers.calculate_ew_return(locked_odds, result, runners)
        win_exact, place_exact, total_exact = helpers.calculate_ew_return_exact(
            odds,
            result,
            runners,
            place_fraction,
        )
        win_return = round(win_exact, 2)
        place_return = round(place_exact, 2)
        total_return = round(total_exact, 2)

        row = {
            **old,
            "name": name,
            "tipsters": old.get("tipsters", horse.get("tipsters")),
            "race_type": section,
            "position": position,
            "result": result,
            "winReturn": win_return,
            "placeReturn": place_return,
            "totalReturn": total_return,
            "winReturnExact": win_exact,
            "placeReturnExact": place_exact,
            "totalReturnExact": total_exact,
            "odds": odds,
            "settlementOdds": odds,
            "settlementOddsSource": settlement_source,
            "lockedSignalPrice": locked_odds,
            "lockedWinReturn": locked_w,
            "lockedPlaceReturn": locked_p,
            "lockedTotalReturn": locked_t,
        }
        if bookmaker_odds_text:
            row["bookmakerOddsText"] = bookmaker_odds_text
            row["bookmaker"] = bookmaker
        if odds_before_rule4 is not None:
            row["settlementOddsBeforeRule4"] = odds_before_rule4
            row["rule4Deduction"] = rule4
        if place_fraction is not None:
            row["placeFraction"] = place_fraction
        if places_paid:
            row["placesPaid"] = int(places_paid)
        if each_way_terms:
            row["eachWayTerms"] = each_way_terms

        recalculated.append(row)

    return recalculated


def repair_date(day_date: str, write: bool = True) -> Dict[str, Any]:
    helpers = load_results_module()
    path = DATA / f"{day_date}.json"
    day = json.loads(path.read_text(encoding="utf-8"))
    results = day.get("results", {}) if isinstance(day.get("results"), dict) else {}
    if results.get("complete") is not True:
        raise RuntimeError(f"{path} is not a completed result file")

    flat = recalc_section(day, "flat", helpers)
    jumps = recalc_section(day, "jumps", helpers)
    bet_meta = helpers.sectioned_bet_summary(flat, jumps)
    locked_meta = helpers.sectioned_bet_summary(
        [
            {
                "position": row.get("position"),
                "result": row.get("result"),
                "winReturn": row.get("lockedWinReturn", 0),
                "placeReturn": row.get("lockedPlaceReturn", 0),
                "totalReturn": row.get("lockedTotalReturn", 0),
            }
            for row in flat
        ],
        [
            {
                "position": row.get("position"),
                "result": row.get("result"),
                "winReturn": row.get("lockedWinReturn", 0),
                "placeReturn": row.get("lockedPlaceReturn", 0),
                "totalReturn": row.get("lockedTotalReturn", 0),
            }
            for row in jumps
        ],
    )

    updated_results = {
        **results,
        "flat": flat,
        "jumps": jumps,
        "patentReturn": bet_meta["totalReturn"],
        "patentProfit": bet_meta["totalProfit"],
        "totalReturn": bet_meta["totalReturn"],
        "totalStake": bet_meta["totalStake"],
        "totalProfit": bet_meta["totalProfit"],
        "profit": bet_meta["totalProfit"],
        "betType": bet_meta["betType"],
        "betLabel": bet_meta["betLabel"],
        "betLines": bet_meta["betLines"],
        "betSummary": bet_meta,
        "lockedReturn": locked_meta["totalReturn"],
        "lockedProfit": locked_meta["totalProfit"],
        "accountancyRecalculatedAt": helpers.datetime.now(helpers.timezone.utc).isoformat(),
    }
    day["results"] = updated_results
    if write:
        path.write_text(json.dumps(day, indent=2) + "\n", encoding="utf-8")
    return updated_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = repair_date(args.date, write=not args.dry_run)
    print(
        f"{args.date}: stake=£{result['totalStake']:.2f} "
        f"return=£{result['totalReturn']:.2f} "
        f"profit=£{result['profit']:.2f} "
        f"betType={result['betType']}"
    )
    for section in ("flat", "jumps"):
        for pick in result.get(section, []) or []:
            print(
                f"  {section}: {pick.get('name')} "
                f"{pick.get('result')} pos={pick.get('position')} "
                f"odds={pick.get('settlementOdds')} "
                f"return=£{pick.get('totalReturn'):.2f}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
