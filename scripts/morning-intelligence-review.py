#!/usr/bin/env python3
"""
Signal 75 — Morning Intelligence Review

Analysis-only script. It reads settled archives and shadow-test files, then
writes daily and weekly learning reports. It never changes picks, proof,
scoring, settlement, or website files.
"""

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


REPO_PATH = os.path.expanduser("~/Signal75")
DATA_DIR = os.path.join(REPO_PATH, "data")
INTEL_DIR = os.path.join(DATA_DIR, "horse_intelligence")
OUT_DIR = os.path.join(DATA_DIR, "intelligence_reviews")
UK_TZ = ZoneInfo("Europe/London")
VALUE_BAND = (2.75, 6.0)


def money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def pct(part, total):
    if not total:
        return 0.0
    return round((part / total) * 100, 1)


def normalise_name(name):
    text = str(name or "").lower().replace("'", "").replace("\u2019", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalise_course(course):
    text = str(course or "").lower()
    text = re.sub(r"\s+\d{1,2}(st|nd|rd|th)?\s+\w+$", "", text)
    text = re.sub(r"\s+\d{4}$", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def normalise_time(value):
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(UK_TZ)
        return parsed.strftime("%H:%M")
    except Exception:
        pass
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not match:
        return ""
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def race_key(course, time_value):
    return (normalise_course(course), normalise_time(time_value))


def odds_band(odds):
    try:
        value = float(odds)
    except Exception:
        return "unknown"
    if VALUE_BAND[0] <= value <= VALUE_BAND[1]:
        return "2.75-6.0"
    if VALUE_BAND[1] < value <= 8.0:
        return "6.1-8.0"
    if value > 8.0:
        return "8.1+"
    return "under-2.75"


def to_number(value):
    try:
        return float(value)
    except Exception:
        return None


def safe_load(path):
    if not os.path.exists(path):
        return None, {"path": path, "found": False, "missing_file": True}
    try:
        with open(path) as f:
            return json.load(f), {"path": path, "found": True, "missing_file": False}
    except Exception as exc:
        return None, {"path": path, "found": False, "missing_file": False, "error": str(exc)}


def load_runner_cache(target_date):
    data, meta = safe_load(os.path.join(DATA_DIR, "today_runners.json"))
    if not data:
        return None, meta
    meta["cache_date"] = data.get("date")
    meta["date_matches_target"] = data.get("date") == target_date
    if data.get("date") != target_date:
        meta["warning"] = "Runner cache date does not match target review date."
    return data, meta


def build_runner_maps(runner_cache):
    maps = {"runner": {}, "race": {}}
    if not runner_cache:
        return maps

    for race in runner_cache.get("races", []) or []:
        key = race_key(race.get("venue"), race.get("race_time"))
        runners = race.get("runners", []) or []
        race_row = {
            "market_id": race.get("market_id"),
            "course": race.get("venue"),
            "time": normalise_time(race.get("race_time")),
            "race_name": race.get("race_name"),
            "field_size": race.get("field_size") or len(runners),
            "runners": runners,
        }
        maps["race"][key] = race_row
        for runner in runners:
            maps["runner"][(key[0], key[1], normalise_name(runner.get("name")))] = runner
    return maps


def runner_snapshot(runner):
    if not runner:
        return None
    market_matched = to_number(runner.get("market_matched")) or 0
    total_matched = to_number(runner.get("total_matched")) or 0
    liquidity_share = round((total_matched / market_matched) * 100, 1) if market_matched else None
    return {
        "selection_id": runner.get("selection_id"),
        "best_back": runner.get("best_back"),
        "market_total_matched": runner.get("market_total_matched"),
        "market_matched": runner.get("market_matched"),
        "runner_available": runner.get("total_matched"),
        "runner_traded": runner.get("runner_traded"),
        "liquidity_share_percent": liquidity_share,
        "jockey": runner.get("jockey"),
        "trainer": runner.get("trainer"),
        "form": runner.get("form"),
        "days_since": runner.get("days_since"),
        "age": runner.get("age"),
        "weight": runner.get("weight"),
        "official_rating": runner.get("official_rating"),
        "stall_draw": runner.get("stall_draw"),
    }


def market_order(race_row, limit=8):
    runners = []
    for runner in race_row.get("runners", []) if race_row else []:
        price = to_number(runner.get("best_back"))
        if price is None:
            continue
        runners.append({
            "horse": runner.get("name"),
            "best_back": price,
            "trainer": runner.get("trainer"),
            "jockey": runner.get("jockey"),
            "form": runner.get("form"),
            "age": runner.get("age"),
            "weight": runner.get("weight"),
            "official_rating": runner.get("official_rating"),
            "stall_draw": runner.get("stall_draw"),
        })
    return sorted(runners, key=lambda row: row["best_back"])[:limit]


def enrich_with_runner_cache(rows, runner_maps):
    for row in rows:
        key = (*race_key(row.get("course"), row.get("time")), normalise_name(row.get("horse")))
        runner = runner_maps["runner"].get(key)
        if runner:
            row["runner_pre_race"] = runner_snapshot(runner)
            row["age"] = runner.get("age")
            row["weight"] = runner.get("weight")
            row["official_rating"] = runner.get("official_rating")
            row["stall_draw"] = runner.get("stall_draw")
            row["days_since"] = runner.get("days_since")
            row["market_liquidity_share_percent"] = row["runner_pre_race"].get("liquidity_share_percent")
        else:
            row["runner_pre_race"] = None


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text.rstrip() + "\n")


def result_bucket(result, position=0):
    result = str(result or "PENDING").upper()
    try:
        position = int(position or 0)
    except Exception:
        position = 0
    if result == "WON" or position == 1:
        return "WON"
    if result == "PLACED":
        return "PLACED"
    if result in ("LOST", "VOID", "NR"):
        return result
    return "PENDING"


def extract_official_picks(day):
    if not day:
        return []

    rows = []
    result_groups = {
        "flat": day.get("results", {}).get("flat", []) or [],
        "jumps": day.get("results", {}).get("jumps", []) or [],
    }
    for tab in ("flat", "jumps"):
        for idx, race in enumerate(day.get(tab, []) or []):
            horses = race.get("horses") or []
            if not horses:
                continue
            horse = horses[0]
            res = result_groups.get(tab, [])
            res = res[idx] if idx < len(res) else {}
            position = res.get("position", horse.get("position", 0))
            result = res.get("result", horse.get("result", "PENDING"))
            consensus = horse.get("consensus") or {}
            rows.append({
                "tab": tab,
                "horse": horse.get("name", ""),
                "course": race.get("course", ""),
                "time": race.get("time", ""),
                "race_type": race.get("type", tab),
                "distance": race.get("distance", ""),
                "going": race.get("going", ""),
                "runners": race.get("runners", 0),
                "signal_score": horse.get("signal_score", 0),
                "bsp": horse.get("odds", 0),
                "odds_band": odds_band(horse.get("odds", 0)),
                "tipster_count": horse.get("tipsters", consensus.get("source_count", 0) or 0),
                "tipster_sources": consensus.get("sources", []) or [],
                "tipsters": consensus.get("tipsters", []) or [],
                "trainer": horse.get("trainer", ""),
                "jockey": horse.get("jockey", ""),
                "form": horse.get("formStr", ""),
                "reason": horse.get("reason", ""),
                "confidence": horse.get("confidence", ""),
                "badge": horse.get("badge", ""),
                "result": result_bucket(result, position),
                "position": position,
                "win_return": money(res.get("winReturn", 0)),
                "place_return": money(res.get("placeReturn", 0)),
                "total_return": money(res.get("totalReturn", 0)),
                "notes": [],
                "labels": [],
            })
    return rows


def extract_radar(day):
    if not day:
        return []
    rows = []
    seen = set()
    for tab, key in (("flat", "topRatedFlat"), ("jumps", "topRatedJumps")):
        for horse in day.get(key, []) or []:
            ident = (tab, normalise_name(horse.get("name")), horse.get("venue") or horse.get("course"), horse.get("time"))
            if ident in seen:
                continue
            seen.add(ident)
            position = horse.get("position", 0)
            result = result_bucket(horse.get("result", "PENDING"), position)
            rows.append({
                "tab": tab,
                "horse": horse.get("name", ""),
                "course": horse.get("venue") or horse.get("course", ""),
                "time": horse.get("time", ""),
                "race_type": horse.get("race_type") or horse.get("type") or tab,
                "signal_score": horse.get("signal_score", 0),
                "bsp": horse.get("odds", 0),
                "odds_band": odds_band(horse.get("odds", 0)),
                "tipster_count": horse.get("tipsters", 0),
                "tipster_sources": (horse.get("consensus") or {}).get("sources", []) or [],
                "trainer": horse.get("trainer", ""),
                "jockey": horse.get("jockey", ""),
                "form": horse.get("form", ""),
                "reason": horse.get("reason", ""),
                "result": result,
                "position": position,
                "radar_result": horse.get("radarResult", ""),
                "labels": [],
                "notes": [],
            })
    return rows


def late_movement_lookup(late_data):
    lookup = {}
    if not late_data:
        return lookup
    for row in late_data.get("official_now", []) or []:
        key = (normalise_name(row.get("name")), row.get("course", ""), row.get("time", ""))
        lookup[key] = row
    return lookup


def shadow_pick_rows(consensus_data, late_data):
    rows = []
    if consensus_data:
        for variant_name, variant in (consensus_data.get("variants") or {}).items():
            results = ((consensus_data.get("results") or {}).get(variant_name) or {}).get("results", []) or []
            result_by_name = {normalise_name(r.get("name")): r for r in results}
            for pick in variant.get("picks", []) or []:
                res = result_by_name.get(normalise_name(pick.get("name")), {})
                rows.append({
                    "variant": variant_name,
                    "horse": pick.get("name"),
                    "course": pick.get("course"),
                    "time": pick.get("time"),
                    "race_type": pick.get("race_type"),
                    "signal_score": pick.get("score"),
                    "bsp": pick.get("bsp"),
                    "odds_band": odds_band(pick.get("bsp")),
                    "tipster_count": pick.get("source_count", 0),
                    "tipster_sources": pick.get("sources", []),
                    "result": result_bucket(res.get("result"), res.get("position")),
                    "position": res.get("position", 0),
                })
    if late_data:
        for variant_name, variant in (late_data.get("variants") or {}).items():
            results = ((late_data.get("results") or {}).get(variant_name) or {}).get("results", []) or []
            result_by_name = {normalise_name(r.get("name")): r for r in results}
            for pick in variant.get("picks", []) or []:
                res = result_by_name.get(normalise_name(pick.get("name")), {})
                rows.append({
                    "variant": variant_name,
                    "horse": pick.get("name"),
                    "course": pick.get("course"),
                    "time": pick.get("time"),
                    "race_type": pick.get("race_type"),
                    "signal_score": pick.get("late_score", pick.get("morning_score")),
                    "bsp": pick.get("late_bsp", pick.get("morning_bsp")),
                    "odds_band": odds_band(pick.get("late_bsp", pick.get("morning_bsp"))),
                    "tipster_count": pick.get("source_count", 0),
                    "tipster_sources": pick.get("sources", []),
                    "result": result_bucket(res.get("result"), res.get("position")),
                    "position": res.get("position", 0),
                    "late_market_signals": pick.get("signals", []),
                })
    return rows


def build_race_contexts(official_picks, radar_rows, shadow_rows, tipster_only_rows, runner_maps):
    contexts = []
    seen = set()
    for pick in official_picks:
        key = race_key(pick.get("course"), pick.get("time"))
        if key in seen:
            continue
        seen.add(key)
        race_row = runner_maps["race"].get(key)
        same_radar = [r for r in radar_rows if race_key(r.get("course"), r.get("time")) == key]
        same_shadow = [r for r in shadow_rows if race_key(r.get("course"), r.get("time")) == key]
        same_tipster_only = [r for r in tipster_only_rows if race_key(r.get("course"), r.get("time")) == key]
        same_official = [p for p in official_picks if race_key(p.get("course"), p.get("time")) == key]

        context = {
            "course": pick.get("course"),
            "time": pick.get("time"),
            "race_name": race_row.get("race_name") if race_row else None,
            "market_id": race_row.get("market_id") if race_row else None,
            "field_size": race_row.get("field_size") if race_row else pick.get("runners"),
            "official_picks": [
                {
                    "horse": p.get("horse"),
                    "result": p.get("result"),
                    "position": p.get("position"),
                    "signal_score": p.get("signal_score"),
                    "bsp": p.get("bsp"),
                    "tipster_count": p.get("tipster_count"),
                    "reason": p.get("reason"),
                    "late_market": p.get("late_market"),
                    "labels": p.get("labels", []),
                }
                for p in same_official
            ],
            "same_race_radar": [
                {
                    "horse": r.get("horse"),
                    "result": r.get("result"),
                    "position": r.get("position"),
                    "signal_score": r.get("signal_score"),
                    "bsp": r.get("bsp"),
                    "tipster_count": r.get("tipster_count"),
                    "reason": r.get("reason"),
                }
                for r in same_radar
            ],
            "same_race_shadow": [
                {
                    "variant": r.get("variant"),
                    "horse": r.get("horse"),
                    "result": r.get("result"),
                    "position": r.get("position"),
                    "signal_score": r.get("signal_score"),
                    "bsp": r.get("bsp"),
                    "tipster_count": r.get("tipster_count"),
                    "late_market_signals": r.get("late_market_signals", []),
                }
                for r in same_shadow
            ],
            "same_race_tipster_only": same_tipster_only,
            "morning_market_order": market_order(race_row),
            "learning_notes": [],
        }

        if same_radar and any(r.get("result") in ("WON", "PLACED") for r in same_radar):
            context["learning_notes"].append("A radar horse in this race placed or won; review why it stayed radar.")
        if same_shadow and any(r.get("result") in ("WON", "PLACED") for r in same_shadow):
            context["learning_notes"].append("A shadow-test horse in this race placed or won; compare the shadow rule.")
        if same_tipster_only:
            context["learning_notes"].append("Tipster-only alerts existed in this race; check whether Signal 75 was right to ignore them.")
        if not race_row:
            context["learning_notes"].append("Runner cache for this race was not available; context is incomplete.")

        contexts.append(context)
    return contexts


def outcome_summary(rows):
    rows = rows or []
    total = len(rows)
    winners = sum(1 for row in rows if row.get("result") == "WON")
    placed = sum(1 for row in rows if row.get("result") in ("WON", "PLACED"))
    profit = money(sum(money(row.get("total_return", 0)) for row in rows) - (total * 2.0))
    return {
        "selections": total,
        "winners": winners,
        "placed": placed,
        "win_rate": pct(winners, total),
        "place_rate": pct(placed, total),
        "estimated_singles_profit": profit,
    }


def grouped_outcomes(rows, key_func):
    groups = defaultdict(list)
    for row in rows:
        groups[str(key_func(row) or "unknown")].append(row)
    return {key: outcome_summary(value) for key, value in sorted(groups.items())}


def tipster_bucket(count):
    try:
        count = int(count or 0)
    except Exception:
        count = 0
    if count >= 5:
        return "5+ tipsters"
    if count >= 3:
        return "3-4 tipsters"
    if count == 2:
        return "2 tipsters"
    if count == 1:
        return "1 tipster"
    return "0 tipsters"


def late_market_bucket(row):
    signals = ((row.get("late_market") or {}).get("signals") or [])
    if "MARKET_DRIFTED" in signals:
        return "late drift"
    if "MARKET_SHORTENED" in signals:
        return "late support"
    if signals:
        return ", ".join(signals)
    return "no late signal"


def market_rank_for_pick(pick, context):
    target = normalise_name(pick.get("horse"))
    for index, runner in enumerate(context.get("morning_market_order", []), 1):
        if normalise_name(runner.get("horse")) == target:
            return index
    return None


def build_decision_audit(official_picks, race_contexts):
    audit = []
    context_lookup = {race_key(ctx.get("course"), ctx.get("time")): ctx for ctx in race_contexts}
    for pick in official_picks:
        ctx = context_lookup.get(race_key(pick.get("course"), pick.get("time")), {})
        market_rank = market_rank_for_pick(pick, ctx)
        better_same_race = []
        for source_name, rows in (
            ("radar", ctx.get("same_race_radar", [])),
            ("shadow", ctx.get("same_race_shadow", [])),
            ("tipster_only", ctx.get("same_race_tipster_only", [])),
        ):
            for row in rows:
                if normalise_name(row.get("horse")) == normalise_name(pick.get("horse")):
                    continue
                if row.get("result") in ("WON", "PLACED"):
                    better_same_race.append({
                        "source": source_name,
                        "horse": row.get("horse"),
                        "result": row.get("result"),
                        "position": row.get("position"),
                        "signal_score": row.get("signal_score"),
                        "bsp": row.get("bsp"),
                        "tipster_count": row.get("tipster_count"),
                    })

        audit.append({
            "horse": pick.get("horse"),
            "course": pick.get("course"),
            "time": pick.get("time"),
            "result": pick.get("result"),
            "position": pick.get("position"),
            "selected_because": {
                "signal_score": pick.get("signal_score"),
                "bsp": pick.get("bsp"),
                "odds_band": pick.get("odds_band"),
                "tipster_count": pick.get("tipster_count"),
                "tipster_sources": pick.get("tipster_sources", []),
                "reason": pick.get("reason"),
                "confidence": pick.get("confidence"),
                "late_market": pick.get("late_market"),
                "morning_market_rank": market_rank,
            },
            "same_race_context": {
                "race_name": ctx.get("race_name"),
                "field_size": ctx.get("field_size"),
                "morning_market_top": ctx.get("morning_market_order", [])[:5],
                "better_same_race_meaningful_horses": better_same_race,
            },
        })
    return audit


def build_pattern_review(official_picks):
    return {
        "by_tipster_count": grouped_outcomes(official_picks, lambda row: tipster_bucket(row.get("tipster_count"))),
        "by_odds_band": grouped_outcomes(official_picks, lambda row: row.get("odds_band")),
        "by_late_market": grouped_outcomes(official_picks, late_market_bucket),
        "by_code": grouped_outcomes(official_picks, lambda row: row.get("tab")),
        "by_course": grouped_outcomes(official_picks, lambda row: row.get("course")),
        "by_race_type": grouped_outcomes(official_picks, lambda row: row.get("race_type")),
    }


def build_evidence_gaps(official_picks, race_contexts):
    gaps = []
    if any(p.get("result") == "LOST" for p in official_picks):
        gaps.append("Need full 1st/2nd/3rd result and beaten-distance capture for losing official-pick races.")
        gaps.append("Need race comments such as short of room, weakened, outpaced, jumping errors, or made all.")
    if any(not p.get("runner_pre_race") for p in official_picks):
        gaps.append("Some official picks were missing pre-race runner-cache details.")
    if any(not ctx.get("morning_market_order") for ctx in race_contexts):
        gaps.append("Some race contexts were missing morning market order.")
    gaps.append("Do not infer beaten lengths, pace, or going suitability unless a confirmed results source provides it.")
    return gaps


def label_official_picks(picks, radar_rows, late_lookup):
    course_counts = Counter(p["course"] for p in picks if p.get("course"))
    trainer_counts = Counter(p["trainer"] for p in picks if p.get("trainer"))
    radar_success = [r for r in radar_rows if r["result"] in ("WON", "PLACED")]

    for pick in picks:
        result = pick["result"]
        if result == "WON":
            pick["labels"].extend(["GOOD_SELECTION", "OFFICIAL_PICK_WON"])
            pick["notes"].append("Official pick won.")
        elif result == "PLACED":
            pick["labels"].extend(["GOOD_SELECTION", "OFFICIAL_PICK_PLACED"])
            pick["notes"].append("Official pick placed.")
        elif result == "LOST":
            pick["labels"].extend(["POOR_SELECTION", "OFFICIAL_PICK_LOST"])
            pick["notes"].append("Official pick lost.")

        if pick["odds_band"] == "2.75-6.0":
            pick["labels"].append("VALUE_BAND_CONFIRMED" if result in ("WON", "PLACED") else "VALUE_BAND_FAILED")
        else:
            pick["labels"].append("OUTSIDE_VALUE_BAND_RISK")

        if pick["tipster_count"] > 0:
            pick["labels"].append("TIPSTER_SUPPORT_HELPED" if result in ("WON", "PLACED") else "TIPSTER_SUPPORT_FAILED")
        else:
            pick["labels"].append("NO_TIPSTER_SUPPORT_BUT_WON" if result in ("WON", "PLACED") else "NO_TIPSTER_SUPPORT_AND_LOST")

        if course_counts[pick.get("course")] > 1:
            pick["labels"].append("SAME_COURSE_CLUSTER_RISK")
            pick["notes"].append("More than one official pick was at the same course.")
        if trainer_counts[pick.get("trainer")] > 1:
            pick["labels"].append("SAME_TRAINER_CLUSTER_RISK")
            pick["notes"].append("More than one official pick had the same trainer.")

        movement = late_lookup.get((normalise_name(pick["horse"]), pick["course"], pick["time"]))
        if movement:
            pick["late_market"] = {
                "morning_bsp": movement.get("morning_bsp"),
                "late_bsp": movement.get("late_bsp"),
                "score_delta": movement.get("score_delta"),
                "signals": movement.get("signals", []),
            }
            signals = movement.get("signals", []) or []
            if "MARKET_DRIFTED" in signals:
                pick["labels"].append("MARKET_DRIFT_WARNING")
                pick["notes"].append("Late market drift was recorded.")
            if "MARKET_SHORTENED" in signals:
                pick["labels"].append("MARKET_SUPPORT_CONFIRMED")
                pick["notes"].append("Late market support was recorded.")

        if result == "LOST" and any(r["tab"] == pick["tab"] and r["result"] in ("WON", "PLACED") for r in radar_success):
            pick["labels"].append("RADAR_OUTPERFORMED_OFFICIAL")

        if not pick["labels"]:
            pick["labels"].append("UNKNOWN_CAUSE")


def build_official_patent(day, picks):
    results = day.get("results", {}) if day else {}
    winners = sum(1 for p in picks if p["result"] == "WON")
    placed = sum(1 for p in picks if p["result"] in ("WON", "PLACED"))
    selections = len(picks)
    stake = money(results.get("totalStake", selections * 2.0))
    returned = money(results.get("patentReturn", sum(p["total_return"] for p in picks)))
    profit = money(results.get("patentProfit", returned - stake))
    return {
        "stake": stake,
        "return": returned,
        "profit": profit,
        "roi_percent": pct(profit, stake),
        "selections": selections,
        "winners": winners,
        "placed": placed,
        "win_rate": pct(winners, selections),
        "place_rate": pct(placed, selections),
        "complete": bool(results.get("complete", False)),
        "proof_basis": results.get("proofBasis", ""),
    }


def build_radar_review(radar_rows, official_picks):
    official_lost = any(p["result"] == "LOST" for p in official_picks)
    winners = [r for r in radar_rows if r["result"] == "WON"]
    placed = [r for r in radar_rows if r["result"] == "PLACED"]
    notable = []
    for row in radar_rows:
        if row["result"] in ("WON", "PLACED"):
            row["labels"].append("RADAR_SHOULD_HAVE_QUALIFIED")
            row["notes"].append("Radar horse beat or matched several official-pick outcomes; monitor the gate that excluded it.")
            notable.append(row)
        elif row["result"] == "LOST":
            row["labels"].append("RADAR_CORRECTLY_REJECTED")
    return {
        "radar_horses_checked": len(radar_rows),
        "radar_winners": len(winners),
        "radar_placed": len(placed),
        "radar_outperformed_official": official_lost and bool(winners or placed),
        "notable_radar": notable[:6],
        "all_radar": radar_rows,
    }


def summarize_variant(name, variant, result):
    picks = variant.get("picks", []) if variant else []
    rows = result.get("results", []) if result else []
    winners = sum(1 for r in rows if result_bucket(r.get("result"), r.get("position")) == "WON")
    placed = sum(1 for r in rows if result_bucket(r.get("result"), r.get("position")) in ("WON", "PLACED"))
    stake = 14.0 if len(picks) >= 3 else len(picks) * 2.0
    profit = money(result.get("patentProfit", 0) if result else 0)
    returned = money(result.get("patentReturn", 0) if result else 0)
    return {
        "variant": name,
        "description": variant.get("description", "") if variant else "",
        "picks": picks,
        "pick_count": len(picks),
        "full_patent": len(picks) >= 3,
        "winners": winners,
        "placed": placed,
        "patent_return": returned,
        "profit": profit,
        "roi_percent": pct(profit, stake),
        "results": rows,
    }


def build_consensus_review(consensus_data):
    if not consensus_data:
        return {
            "variants": {},
            "best_variant_today": None,
            "recommendation": "Consensus file missing. Continue monitoring.",
        }
    variants = {}
    for name, variant in (consensus_data.get("variants") or {}).items():
        result = (consensus_data.get("results") or {}).get(name, {})
        variants[name] = summarize_variant(name, variant, result)

    best_name = None
    full_patent_variants = {name: row for name, row in variants.items() if row.get("full_patent")}
    comparable_variants = full_patent_variants or variants
    if comparable_variants:
        best_name = max(comparable_variants, key=lambda n: comparable_variants[n]["profit"])

    baseline = variants.get("baseline_live_rule")
    best = variants.get(best_name) if best_name else None
    recommendation = "No rule change. Continue shadow testing."
    if baseline and best and best_name != "baseline_live_rule" and best["profit"] > baseline["profit"]:
        recommendation = f"{best_name} beat baseline today. Continue monitoring before any live change."
    elif baseline and best_name == "baseline_live_rule":
        recommendation = "Baseline beat or matched consensus today. Do not tighten consensus from this single day."

    return {
        "variants": variants,
        "best_variant_today": best_name,
        "recommendation": recommendation,
    }


def extract_tipster_only(intel_data):
    if not intel_data:
        return []
    rows = []
    for rec in intel_data.get("records", []) or []:
        if rec.get("selection_type") != "TIPSTER_ONLY_ALERT":
            continue
        rows.append({
            "horse": rec.get("horse_name"),
            "course": rec.get("course"),
            "time": rec.get("time"),
            "signal_score": rec.get("signal_score"),
            "bsp": rec.get("bsp"),
            "tipster_count": rec.get("consensus_count", 0),
            "tipster_sources": rec.get("consensus_sources", []),
            "result": rec.get("result"),
            "position": rec.get("finishing_position"),
        })
    return rows


def build_findings(patent, official_picks, radar_review, consensus_review):
    findings = []
    if patent["selections"]:
        findings.append(
            f"Official Patent returned £{patent['return']:.2f} from £{patent['stake']:.2f}: "
            f"{patent['winners']} winners and {patent['placed']} placed from {patent['selections']} selections."
        )
    else:
        findings.append("No official selections were available to analyse.")

    lost_with_tipsters = [p for p in official_picks if p["tipster_count"] > 0 and p["result"] == "LOST"]
    if lost_with_tipsters:
        findings.append(f"{len(lost_with_tipsters)} tipster-backed official pick(s) lost; one-source support should remain under review.")

    drifters = [p for p in official_picks if "MARKET_DRIFT_WARNING" in p["labels"]]
    if drifters:
        findings.append(f"{len(drifters)} official pick(s) had a late market drift warning.")

    if radar_review["radar_winners"] or radar_review["radar_placed"]:
        findings.append(
            f"Radar produced {radar_review['radar_winners']} winner(s) and "
            f"{radar_review['radar_placed']} placed horse(s); monitor whether the gate is too strict."
        )

    best = consensus_review.get("best_variant_today")
    if best:
        findings.append(f"Best shadow variant today: {best}.")

    same_course = [p for p in official_picks if "SAME_COURSE_CLUSTER_RISK" in p["labels"]]
    same_trainer = [p for p in official_picks if "SAME_TRAINER_CLUSTER_RISK" in p["labels"]]
    if same_course:
        findings.append("Official picks had same-course clustering risk.")
    if same_trainer:
        findings.append("Official picks had same-trainer clustering risk.")

    return findings


def build_possible_improvements(official_picks, radar_review, consensus_review, race_contexts=None):
    race_contexts = race_contexts or []
    items = [
        "Continue collecting at least 7 days before changing live rules.",
        "Track whether 1-tipster picks underperform versus 2+ tipster picks.",
        "Track whether late market drifters repeatedly lose.",
        "Track whether Radar winners are coming from the same odds band or race type.",
        "Compare Signal 75 baseline against tipster-first and strict consensus variants.",
        "Review same-race alternatives that beat official picks before changing gates.",
        "Capture confirmed winner/placed horse reasons from full race results where available.",
    ]
    if any("SAME_COURSE_CLUSTER_RISK" in p["labels"] for p in official_picks):
        items.append("Monitor whether multiple picks from the same course increase Patent risk.")
    if any("SAME_TRAINER_CLUSTER_RISK" in p["labels"] for p in official_picks):
        items.append("Monitor whether same-trainer clustering increases Patent risk.")
    if radar_review.get("radar_outperformed_official"):
        items.append("Investigate whether high-scoring Radar horses need a clearer promotion path.")
    if consensus_review.get("best_variant_today") == "baseline_live_rule":
        items.append("Do not assume stricter consensus is better until shadow data proves it.")
    if any(ctx.get("same_race_shadow") for ctx in race_contexts):
        items.append("Check whether a shadow variant repeatedly finds better same-race alternatives.")
    if any(ctx.get("same_race_tipster_only") for ctx in race_contexts):
        items.append("Track whether tipster-only alerts are useful signals or public traps.")
    return items


def recommendation_for_day(valid_days):
    if valid_days < 7:
        return {
            "action": "NO_CHANGE",
            "confidence": "LOW",
            "reason": "Fewer than 7 completed review days. Continue collecting evidence.",
        }
    return {
        "action": "CONTINUE_MONITORING",
        "confidence": "MEDIUM",
        "reason": "At least 7 review days exist. Patterns may be investigated, but live changes still need testing.",
    }


def text_report(payload):
    patent = payload["official_patent"]
    lines = [
        "SIGNAL 75 DAILY INTELLIGENCE REVIEW",
        f"Date analysed: {payload['date']}",
        f"Generated: {payload['generated_at']}",
        "",
        "OFFICIAL PATENT",
        f"Stake: £{patent['stake']:.2f}",
        f"Return: £{patent['return']:.2f}",
        f"Profit: {'+' if patent['profit'] >= 0 else ''}£{patent['profit']:.2f}",
        f"ROI: {'+' if patent['roi_percent'] >= 0 else ''}{patent['roi_percent']:.1f}%",
        f"Winners: {patent['winners']}/{patent['selections']}",
        f"Placed: {patent['placed']}/{patent['selections']}",
        f"Win Rate: {patent['win_rate']:.1f}%",
        f"Place Rate: {patent['place_rate']:.1f}%",
        "",
        "OFFICIAL PICKS",
    ]
    for pick in payload["official_picks"]:
        tip = f"{pick['tipster_count']} tipster" + ("" if pick["tipster_count"] == 1 else "s")
        movement = ""
        if pick.get("late_market"):
            signals = ", ".join(pick["late_market"].get("signals", []))
            movement = f" | late: {signals or 'no signal'}"
        extras = []
        if pick.get("age"):
            extras.append(f"age {pick['age']}")
        if pick.get("weight"):
            extras.append(f"weight {pick['weight']}")
        if pick.get("official_rating"):
            extras.append(f"OR {pick['official_rating']}")
        if pick.get("days_since"):
            extras.append(f"{pick['days_since']} days")
        extra_text = f" | {'; '.join(extras)}" if extras else ""
        lines.append(
            f"- {pick['horse']} ({pick['course']} {pick['time']}): {pick['result']} "
            f"pos {pick['position']} | score {pick['signal_score']} | BSP {pick['bsp']} "
            f"| {tip}{movement}{extra_text}"
        )

    lines.extend(["", "RACE CONTEXT"])
    for ctx in payload.get("race_contexts", []):
        lines.append(f"- {ctx['course']} {ctx['time']} ({ctx.get('race_name') or 'race'}):")
        if ctx.get("morning_market_order"):
            market = ", ".join([f"{r['horse']} {r['best_back']}" for r in ctx["morning_market_order"][:5]])
            lines.append(f"  Morning market top: {market}")
        if ctx.get("same_race_radar"):
            radar = ", ".join([f"{r['horse']} {r['result']} pos {r['position']}" for r in ctx["same_race_radar"]])
            lines.append(f"  Same-race radar: {radar}")
        if ctx.get("same_race_shadow"):
            shadow = ", ".join([f"{r['variant']}:{r['horse']} {r['result']} pos {r['position']}" for r in ctx["same_race_shadow"][:6]])
            lines.append(f"  Same-race shadow: {shadow}")
        if ctx.get("learning_notes"):
            for note in ctx["learning_notes"]:
                lines.append(f"  Note: {note}")

    lines.extend(["", "SELECTION AUDIT"])
    for row in payload.get("decision_audit", []):
        selected = row.get("selected_because", {})
        context = row.get("same_race_context", {})
        lines.append(f"- {row['horse']} ({row['course']} {row['time']}): {row['result']} pos {row['position']}")
        why_parts = [
            f"score {selected.get('signal_score')}",
            f"BSP {selected.get('bsp')}",
            f"{selected.get('tipster_count', 0)} tipster(s)",
        ]
        if selected.get("morning_market_rank"):
            why_parts.append(f"morning market rank {selected['morning_market_rank']}")
        late_market = selected.get("late_market") or {}
        if late_market.get("signals"):
            why_parts.append("late " + ", ".join(late_market["signals"]))
        lines.append(f"  Pick facts: {', '.join(why_parts)}")
        if selected.get("reason"):
            lines.append(f"  Original reason: {selected['reason']}")
        better = context.get("better_same_race_meaningful_horses", [])
        if better:
            lines.append(
                "  Meaningful same-race horses that did better: "
                + ", ".join([
                    f"{item['horse']} ({item['source']}, {item['result']} pos {item['position']})"
                    for item in better[:5]
                ])
            )
        else:
            lines.append("  No logged radar/shadow/tipster-only horse in this same race clearly beat it.")

    lines.extend(["", "PATTERN SNAPSHOT"])
    patterns = payload.get("pattern_review", {})
    for title, key in (
        ("Tipster count", "by_tipster_count"),
        ("Odds band", "by_odds_band"),
        ("Late market", "by_late_market"),
        ("Code", "by_code"),
    ):
        if not patterns.get(key):
            continue
        lines.append(f"{title}:")
        for bucket, row in patterns[key].items():
            lines.append(
                f"  - {bucket}: {row['winners']}/{row['selections']} won, "
                f"{row['placed']}/{row['selections']} placed"
            )

    lines.extend(["", "KEY FINDINGS"])
    for i, finding in enumerate(payload["key_findings"], 1):
        lines.append(f"{i}. {finding}")

    lines.extend(["", "WHAT TO MONITOR"])
    for item in payload["possible_improvements_to_monitor"]:
        lines.append(f"- {item}")

    if payload.get("evidence_gaps"):
        lines.extend(["", "EVIDENCE GAPS"])
        for gap in payload["evidence_gaps"]:
            lines.append(f"- {gap}")

    rec = payload["recommendation"]
    lines.extend([
        "",
        "RECOMMENDATION",
        rec["action"],
        f"Confidence: {rec['confidence']}",
        f"Reason: {rec['reason']}",
    ])
    return "\n".join(lines)


def existing_review_days():
    if not os.path.isdir(OUT_DIR):
        return []
    days = []
    for name in os.listdir(OUT_DIR):
        match = re.match(r"review_(\d{4}-\d{2}-\d{2})\.json$", name)
        if match:
            days.append(match.group(1))
    return sorted(days)


def build_daily_review(target_date):
    official_path = os.path.join(DATA_DIR, f"{target_date}.json")
    overlay_path = os.path.join(DATA_DIR, f"consensus_overlay_{target_date}.json")
    shadow_path = os.path.join(DATA_DIR, f"consensus_shadow_{target_date}.json")
    intel_path = os.path.join(INTEL_DIR, f"race_intelligence_{target_date}.json")
    performance_path = os.path.join(REPO_PATH, "performance.json")
    late_path = os.path.join(DATA_DIR, f"late_value_shadow_{target_date}.json")

    official, official_meta = safe_load(official_path)
    overlay, overlay_meta = safe_load(overlay_path)
    shadow, shadow_meta = safe_load(shadow_path)
    intel, intel_meta = safe_load(intel_path)
    performance, performance_meta = safe_load(performance_path)
    late, late_meta = safe_load(late_path)
    runner_cache, runner_cache_meta = load_runner_cache(target_date)
    runner_maps = build_runner_maps(runner_cache if runner_cache_meta.get("date_matches_target") else None)

    picks = extract_official_picks(official)
    radar = extract_radar(official)
    tipster_only = extract_tipster_only(intel)
    shadow_rows = shadow_pick_rows(shadow, late)
    enrich_with_runner_cache(picks, runner_maps)
    enrich_with_runner_cache(radar, runner_maps)
    enrich_with_runner_cache(tipster_only, runner_maps)
    enrich_with_runner_cache(shadow_rows, runner_maps)
    label_official_picks(picks, radar, late_movement_lookup(late))
    patent = build_official_patent(official or {}, picks)
    radar_review = build_radar_review(radar, picks)
    consensus_review = build_consensus_review(shadow)
    race_contexts = build_race_contexts(picks, radar, shadow_rows, tipster_only, runner_maps)
    decision_audit = build_decision_audit(picks, race_contexts)
    pattern_review = build_pattern_review(picks)
    evidence_gaps = build_evidence_gaps(picks, race_contexts)

    review_days = set(existing_review_days())
    review_days.add(target_date)
    valid_days = len(review_days)

    payload = {
        "date": target_date,
        "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
        "status": "ok" if official else "warning",
        "analysis_only": True,
        "input_files": {
            "official_archive": official_meta,
            "consensus_overlay": overlay_meta,
            "consensus_shadow": shadow_meta,
            "horse_intelligence": intel_meta,
            "performance": performance_meta,
            "late_value_shadow": late_meta,
            "runner_cache": runner_cache_meta,
        },
        "official_patent": patent,
        "official_picks": picks,
        "radar_review": radar_review,
        "consensus_shadow_review": consensus_review,
        "shadow_pick_rows": shadow_rows,
        "tipster_only_alerts": tipster_only,
        "race_contexts": race_contexts,
        "decision_audit": decision_audit,
        "pattern_review": pattern_review,
        "evidence_gaps": evidence_gaps,
        "performance_context": {
            "total_days": (performance or {}).get("totalDays"),
            "betting_days": (performance or {}).get("bettingDays"),
            "total_profit": (performance or {}).get("totalProfit"),
            "roi": (performance or {}).get("roi"),
        },
        "key_findings": build_findings(patent, picks, radar_review, consensus_review),
        "possible_improvements_to_monitor": build_possible_improvements(picks, radar_review, consensus_review, race_contexts),
        "recommendation": recommendation_for_day(valid_days),
    }

    if not official:
        payload["key_findings"].append("Official archive missing; review is incomplete.")
        payload["recommendation"] = {
            "action": "CONTINUE_MONITORING",
            "confidence": "LOW",
            "reason": "Target day archive missing, so no live conclusion can be drawn.",
        }

    return payload


def load_reviews(limit=7):
    reviews = []
    for day in existing_review_days()[-limit:]:
        data, _ = safe_load(os.path.join(OUT_DIR, f"review_{day}.json"))
        if data:
            reviews.append(data)
    return reviews


def summarize_weekly():
    reviews = load_reviews(7)
    if not reviews:
        return {
            "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
            "status": "warning",
            "message": "No daily reviews available yet.",
            "analysis_only": True,
        }

    first, last = reviews[0]["date"], reviews[-1]["date"]
    completed = [r for r in reviews if r.get("official_patent", {}).get("complete")]
    profit = sum(money(r.get("official_patent", {}).get("profit", 0)) for r in completed)
    stake = sum(money(r.get("official_patent", {}).get("stake", 0)) for r in completed)
    selections = sum(int(r.get("official_patent", {}).get("selections", 0)) for r in completed)
    winners = sum(int(r.get("official_patent", {}).get("winners", 0)) for r in completed)
    placed = sum(int(r.get("official_patent", {}).get("placed", 0)) for r in completed)

    variant_profit = defaultdict(float)
    variant_days = Counter()
    labels = Counter()
    radar_winners = 0
    radar_placed = 0
    radar_outperformed_days = 0
    pattern_totals = {
        "by_tipster_count": defaultdict(lambda: Counter({"selections": 0, "winners": 0, "placed": 0})),
        "by_odds_band": defaultdict(lambda: Counter({"selections": 0, "winners": 0, "placed": 0})),
        "by_late_market": defaultdict(lambda: Counter({"selections": 0, "winners": 0, "placed": 0})),
        "by_code": defaultdict(lambda: Counter({"selections": 0, "winners": 0, "placed": 0})),
    }
    same_race_better = 0

    for review in reviews:
        for pick in review.get("official_picks", []):
            labels.update(pick.get("labels", []))
        for audit in review.get("decision_audit", []):
            better = ((audit.get("same_race_context") or {}).get("better_same_race_meaningful_horses") or [])
            if better:
                same_race_better += 1
        rr = review.get("radar_review", {})
        radar_winners += int(rr.get("radar_winners", 0))
        radar_placed += int(rr.get("radar_placed", 0))
        radar_outperformed_days += 1 if rr.get("radar_outperformed_official") else 0
        for pattern_name in pattern_totals:
            for bucket, row in (review.get("pattern_review", {}).get(pattern_name, {}) or {}).items():
                pattern_totals[pattern_name][bucket]["selections"] += int(row.get("selections", 0))
                pattern_totals[pattern_name][bucket]["winners"] += int(row.get("winners", 0))
                pattern_totals[pattern_name][bucket]["placed"] += int(row.get("placed", 0))
        variants = review.get("consensus_shadow_review", {}).get("variants", {})
        for name, row in variants.items():
            variant_profit[name] += money(row.get("profit", 0))
            variant_days[name] += 1

    variant_full_patent_days = Counter()
    for review in reviews:
        variants = review.get("consensus_shadow_review", {}).get("variants", {})
        for name, row in variants.items():
            if row.get("full_patent"):
                variant_full_patent_days[name] += 1

    comparable_profit = {
        name: profit
        for name, profit in variant_profit.items()
        if variant_full_patent_days.get(name, 0) > 0
    }
    best_variant = None
    if comparable_profit:
        best_variant = max(comparable_profit, key=lambda name: comparable_profit[name])

    confidence = "LOW_CONFIDENCE"
    if len(completed) >= 30:
        confidence = "HIGH_CONFIDENCE"
    elif len(completed) >= 7:
        confidence = "MEDIUM_CONFIDENCE"

    recommendation = "No live change yet."
    if len(completed) >= 7:
        recommendation = "Patterns may now be investigated, but rule changes still need shadow or backtest confirmation."

    payload = {
        "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
        "analysis_only": True,
        "period": {"start": first, "end": last},
        "valid_days": {"analysed_days": len(reviews), "completed_days": len(completed)},
        "official_baseline": {
            "profit": round(profit, 2),
            "stake": round(stake, 2),
            "roi_percent": pct(profit, stake),
            "winners": winners,
            "placed": placed,
            "selections": selections,
            "win_rate": pct(winners, selections),
            "place_rate": pct(placed, selections),
        },
        "consensus_shadow": {
            "best_variant": best_variant,
            "variant_profit": {k: round(v, 2) for k, v in sorted(variant_profit.items())},
            "variant_days": dict(variant_days),
            "variant_full_patent_days": dict(variant_full_patent_days),
        },
        "radar_review": {
            "radar_winners": radar_winners,
            "radar_placed": radar_placed,
            "radar_outperformed_days": radar_outperformed_days,
        },
        "decision_audit": {
            "official_picks_with_better_logged_same_race_alternative": same_race_better,
        },
        "pattern_totals": {
            pattern_name: {
                bucket: {
                    "selections": int(row["selections"]),
                    "winners": int(row["winners"]),
                    "placed": int(row["placed"]),
                    "win_rate": pct(row["winners"], row["selections"]),
                    "place_rate": pct(row["placed"], row["selections"]),
                }
                for bucket, row in sorted(buckets.items())
            }
            for pattern_name, buckets in pattern_totals.items()
        },
        "label_counts": dict(labels.most_common()),
        "recommendation": {
            "action": "CONTINUE_MONITORING",
            "confidence": confidence,
            "reason": recommendation,
        },
    }
    return payload


def weekly_text(payload):
    if payload.get("status") == "warning":
        return "SIGNAL 75 WEEKLY INTELLIGENCE SUMMARY\n\nNo daily reviews available yet."
    base = payload["official_baseline"]
    lines = [
        "SIGNAL 75 WEEKLY INTELLIGENCE SUMMARY",
        f"Period: {payload['period']['start']} to {payload['period']['end']}",
        "",
        "VALID DAYS",
        f"Analysed days: {payload['valid_days']['analysed_days']}",
        f"Completed days: {payload['valid_days']['completed_days']}",
        "",
        "OFFICIAL BASELINE",
        f"Profit: {'+' if base['profit'] >= 0 else ''}£{base['profit']:.2f}",
        f"ROI: {'+' if base['roi_percent'] >= 0 else ''}{base['roi_percent']:.1f}%",
        f"Winners: {base['winners']}/{base['selections']}",
        f"Placed: {base['placed']}/{base['selections']}",
        "",
        "CONSENSUS SHADOW",
        f"Best variant: {payload['consensus_shadow']['best_variant'] or 'None yet'}",
    ]
    for name, profit in payload["consensus_shadow"]["variant_profit"].items():
        lines.append(f"- {name}: {'+' if profit >= 0 else ''}£{profit:.2f}")
    lines.extend([
        "",
        "RADAR REVIEW",
        f"Radar winners: {payload['radar_review']['radar_winners']}",
        f"Radar placed: {payload['radar_review']['radar_placed']}",
        f"Radar outperformed official days: {payload['radar_review']['radar_outperformed_days']}",
        f"Official picks with a better logged same-race alternative: {payload.get('decision_audit', {}).get('official_picks_with_better_logged_same_race_alternative', 0)}",
        "",
        "PATTERN TOTALS",
    ])
    for title, key in (
        ("Tipster count", "by_tipster_count"),
        ("Odds band", "by_odds_band"),
        ("Late market", "by_late_market"),
        ("Code", "by_code"),
    ):
        rows = payload.get("pattern_totals", {}).get(key, {})
        if not rows:
            continue
        lines.append(f"{title}:")
        for bucket, row in rows.items():
            lines.append(
                f"- {bucket}: {row['winners']}/{row['selections']} won, "
                f"{row['placed']}/{row['selections']} placed"
            )
    lines.extend(["", "KEY PATTERNS"])
    for label, count in list(payload.get("label_counts", {}).items())[:10]:
        lines.append(f"- {label}: {count}")
    rec = payload["recommendation"]
    lines.extend([
        "",
        "RECOMMENDATION",
        rec["action"],
        f"Confidence: {rec['confidence']}",
        f"Reason: {rec['reason']}",
    ])
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Build Signal 75 morning intelligence review.")
    parser.add_argument("--date", help="Date to analyse, YYYY-MM-DD. Defaults to yesterday in UK time.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.date:
        target_date = args.date
    else:
        target_date = (datetime.now(UK_TZ).date() - timedelta(days=1)).isoformat()

    daily = build_daily_review(target_date)
    json_path = os.path.join(OUT_DIR, f"review_{target_date}.json")
    txt_path = os.path.join(OUT_DIR, f"review_{target_date}.txt")
    write_json(json_path, daily)
    write_text(txt_path, text_report(daily))

    weekly = summarize_weekly()
    write_json(os.path.join(OUT_DIR, "weekly_summary.json"), weekly)
    write_text(os.path.join(OUT_DIR, "weekly_summary.txt"), weekly_text(weekly))

    print(f"Morning intelligence review written for {target_date}")
    print(f"  {json_path}")
    print(f"  {txt_path}")
    print("Weekly summary updated.")


if __name__ == "__main__":
    main()
