#!/usr/bin/env python3
"""
late-market-watch.py — Signal 75

Shadow-only market movement check. It refreshes Betfair prices after the
morning picks and records horses that move into the official value band.

This does not change public picks.
"""
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone, timedelta

SCRIPTS = "/Users/johnhowlett/Signal75/scripts"
REPO = "/Users/johnhowlett/Signal75"
RUNNERS_CACHE = f"{REPO}/data/today_runners.json"
PICKS_JSON = f"{REPO}/picks.json"
OUTPUT_TEMPLATE = f"{REPO}/data/late_value_shadow_{{}}.json"

sys.path.insert(0, SCRIPTS)

VALUE_MIN = 4.1
VALUE_MAX = 6.0
MIN_SCORE = 75
MIN_FIELD = 8


def today():
    return datetime.now().strftime("%Y-%m-%d")


def format_time_uk(race_time_str):
    try:
        dt = datetime.fromisoformat(str(race_time_str).replace("Z", "+00:00"))
        return (dt + timedelta(hours=1)).strftime("%H:%M")
    except Exception:
        return "00:00"


def normalise(name):
    n = (name or "").lower().replace("'", "").replace("\u2019", "")
    n = re.sub(r"[^a-z0-9 ]", "", n)
    return re.sub(r"\s+", " ", n).strip()


def official_pick_keys(picks):
    keys = set()
    market_ids = set()
    for tab in ("flat", "jumps"):
        for race in picks.get(tab, []):
            if not race.get("horses"):
                continue
            h = race["horses"][0]
            keys.add(normalise(h.get("name")))
            market_ids.add(h.get("market_id"))
    return keys, market_ids


def runner_meta(races):
    meta = {}
    for race in races:
        for runner in race.get("runners", []):
            meta[(race.get("market_id"), normalise(runner.get("name")))] = {
                "trainer": runner.get("trainer", ""),
                "jockey": runner.get("jockey", ""),
                "form": runner.get("form", ""),
                "days_since": runner.get("days_since", ""),
                "official_rating": runner.get("official_rating", ""),
                "age": runner.get("age", ""),
                "weight": runner.get("weight", ""),
                "morning_odds": runner.get("best_back"),
            }
    return meta


def current_price_maps(trading, market_ids):
    books = trading.betting.list_market_book(
        market_ids=list(market_ids),
        price_projection={
            "priceData": ["EX_BEST_OFFERS"],
            "exBestOffersOverrides": {"bestPricesDepth": 1},
        },
    )
    prices = {}
    traded = {}
    market_total = {}
    back_pool = {}
    for book in books:
        market_total[book.market_id] = float(getattr(book, "total_matched", 0) or 0)
        back_pool[book.market_id] = 0.0
        for runner in book.runners:
            if runner.ex and runner.ex.available_to_back:
                price = runner.ex.available_to_back[0].price
                size = float(runner.ex.available_to_back[0].size or 0)
                prices[(book.market_id, runner.selection_id)] = price
                traded[(book.market_id, runner.selection_id)] = size
                back_pool[book.market_id] += size
    return prices, traded, market_total, back_pool


def apply_current_prices(races, prices, traded, market_total, back_pool):
    updated = deepcopy(races)
    for race in updated:
        market_id = race.get("market_id")
        for runner in race.get("runners", []):
            key = (market_id, runner.get("selection_id"))
            if key in prices:
                runner["morning_best_back"] = runner.get("best_back")
                runner["best_back"] = prices[key]
                runner["total_matched"] = traded.get(key, 0.0)
                runner["market_matched"] = back_pool.get(market_id) or market_total.get(market_id) or 0.0
                runner["market_total_matched"] = market_total.get(market_id, 0.0)
                runner["market_back_pool"] = back_pool.get(market_id, 0.0)
    return updated


def official_candidate(runner):
    bsp = runner.get("bsp")
    return (
        runner.get("score", 0) >= MIN_SCORE
        and bsp is not None
        and VALUE_MIN <= float(bsp) <= VALUE_MAX
        and int(runner.get("field_size") or 0) >= MIN_FIELD
    )


def pick_three(candidates):
    picks = []
    used_markets = set()
    for runner in sorted(candidates, key=lambda r: r.get("score", 0), reverse=True):
        if runner.get("market_id") in used_markets:
            continue
        picks.append(runner)
        used_markets.add(runner.get("market_id"))
        if len(picks) == 3:
            break
    return picks


def shadow_entry(runner, morning_lookup, meta, official_market_ids):
    key = (runner.get("market_id"), normalise(runner.get("name")))
    morning = morning_lookup.get(key, {})
    morning_odds = morning.get("bsp")
    live_odds = runner.get("bsp")
    signals = []
    if morning_odds and live_odds:
        if not (VALUE_MIN <= float(morning_odds) <= VALUE_MAX) and VALUE_MIN <= float(live_odds) <= VALUE_MAX:
            signals.append("MOVED_INTO_VALUE_BAND")
        if float(live_odds) < float(morning_odds):
            signals.append("MARKET_SHORTENED")
        if float(live_odds) > float(morning_odds):
            signals.append("MARKET_DRIFTED")
    if runner.get("market_id") in official_market_ids:
        signals.append("SAME_RACE_AS_OFFICIAL_PICK")

    m = meta.get(key, {})
    return {
        "name": runner.get("name"),
        "course": runner.get("venue"),
        "time": format_time_uk(runner.get("race_time")),
        "race_type": runner.get("race_type"),
        "market_id": runner.get("market_id"),
        "morning_bsp": morning_odds,
        "late_bsp": live_odds,
        "morning_score": morning.get("score"),
        "late_score": runner.get("score"),
        "score_delta": round((runner.get("score") or 0) - (morning.get("score") or 0), 1),
        "trainer": runner.get("trainer") or m.get("trainer"),
        "jockey": runner.get("jockey") or m.get("jockey"),
        "form": runner.get("form") or m.get("form"),
        "days_since": m.get("days_since"),
        "official_rating": m.get("official_rating"),
        "age": m.get("age"),
        "weight": m.get("weight"),
        "signals": signals,
        "breakdown": runner.get("breakdown", {}),
    }


def main():
    print("Signal 75 — late market shadow watch")
    if not os.path.exists(RUNNERS_CACHE) or not os.path.exists(PICKS_JSON):
        raise SystemExit("Missing today_runners.json or picks.json")

    with open(RUNNERS_CACHE) as f:
        cache = json.load(f)
    with open(PICKS_JSON) as f:
        picks = json.load(f)

    date_str = cache.get("date") or today()
    if date_str != today() and "--allow-stale" not in sys.argv:
        raise SystemExit(f"today_runners.json is dated {date_str}, not {today()} — waiting for today's 10am picks first")
    races = cache.get("races", [])
    if not races:
        raise SystemExit("No cached races")

    from betfair_client import get_client
    from runner_matcher import load_profiles, enrich_runners
    from scoring_engine import load_roi_tables, score_all_runners

    profiles = load_profiles()
    tables = load_roi_tables()

    morning_races = enrich_runners(deepcopy(races), profiles)
    morning_scored = score_all_runners(morning_races, tables)
    morning_lookup = {
        (r.get("market_id"), normalise(r.get("name"))): r
        for r in morning_scored
    }

    market_ids = {r.get("market_id") for r in races if r.get("market_id")}
    trading = get_client()
    prices, traded, market_total, back_pool = current_price_maps(trading, market_ids)
    live_races = apply_current_prices(races, prices, traded, market_total, back_pool)
    live_races = enrich_runners(live_races, profiles)
    live_scored = score_all_runners(live_races, tables)

    official_names, official_market_ids = official_pick_keys(picks)
    meta = runner_meta(races)

    official_now = []
    moved_into_band = []
    same_race_alternatives = []
    for runner in live_scored:
        if normalise(runner.get("name")) in official_names:
            official_now.append(runner)
            continue
        if not official_candidate(runner):
            continue
        entry = shadow_entry(runner, morning_lookup, meta, official_market_ids)
        if "MOVED_INTO_VALUE_BAND" in entry["signals"]:
            moved_into_band.append(entry)
        if "SAME_RACE_AS_OFFICIAL_PICK" in entry["signals"]:
            same_race_alternatives.append(entry)

    live_candidate_entries = [
        shadow_entry(r, morning_lookup, meta, official_market_ids)
        for r in pick_three([r for r in live_scored if official_candidate(r)])
    ]

    payload = {
        "date": date_str,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "shadow_only_not_live",
        "message": "Late market watch only. Public picks are unchanged.",
        "rules": {
            "value_band": [VALUE_MIN, VALUE_MAX],
            "min_score": MIN_SCORE,
            "min_field_size": MIN_FIELD,
        },
        "counts": {
            "markets_checked": len(market_ids),
            "runners_scored": len(live_scored),
            "moved_into_value_band": len(moved_into_band),
            "same_race_alternatives": len(same_race_alternatives),
        },
        "official_now": [
            shadow_entry(r, morning_lookup, meta, official_market_ids)
            for r in sorted(official_now, key=lambda x: x.get("score", 0), reverse=True)
        ],
        "variants": {
            "late_value_band_v1": {
                "description": "Top current-score horses using refreshed Betfair prices; shadow only.",
                "picks": live_candidate_entries,
            }
        },
        "moved_into_value_band": sorted(moved_into_band, key=lambda r: r.get("late_score") or 0, reverse=True),
        "same_race_alternatives": sorted(same_race_alternatives, key=lambda r: r.get("late_score") or 0, reverse=True),
    }

    out_path = OUTPUT_TEMPLATE.format(date_str)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"Saved {out_path}")
    print(json.dumps(payload["counts"], indent=2))


if __name__ == "__main__":
    main()
