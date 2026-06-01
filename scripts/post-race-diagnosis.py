#!/usr/bin/env python3
"""Post-race diagnosis for Signal 75.

Analysis only: reads settled daily files and writes diagnosis reports.
It does not alter picks, scoring, settlement, proof, or the public site.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DIAGNOSIS_DIR = DATA_DIR / "diagnosis"
ARCHIVE_DIR = DIAGNOSIS_DIR / "archive"
PATTERN_FILE = DIAGNOSIS_DIR / "pattern_accumulator.json"

THRESHOLDS = {
    "CONSENSUS_TRAP": 3,
    "RADAR_OUTPERFORMED_OFFICIAL": 5,
    "MARKET_DRIFT_CONFIRMED": 4,
    "SAME_TRAINER_CLUSTER_RISK": 3,
    "MARKET_SUPPORT_FAILED": 4,
}


def load_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def money(value: Any) -> float:
    parsed = safe_float(value)
    return round(parsed or 0.0, 2)


def pretty_money(value: Any) -> str:
    amount = money(value)
    sign = "+" if amount > 0 else ""
    return f"GBP {sign}{amount:.2f}"


def extract_horse_from_pick(entry: Dict[str, Any]) -> Dict[str, Any]:
    horses = entry.get("horses")
    if isinstance(horses, list) and horses:
        horse = dict(horses[0])
        horse.setdefault("course", entry.get("course"))
        horse.setdefault("time", entry.get("time"))
        horse.setdefault("race_type", entry.get("type") or entry.get("race_type"))
        horse.setdefault("distance", entry.get("distance"))
        horse.setdefault("going", entry.get("going"))
        horse.setdefault("runners", entry.get("runners"))
        return horse
    return dict(entry)


def result_rank(result: Any, position: Any = None) -> int:
    text = str(result or "").upper()
    pos = safe_int(position)
    if "WON" in text:
        return 3
    if "PLACED" in text:
        return 2
    if "LOST" in text or "UNPLACED" in text or text == "LOSER":
        return 1
    if pos == 1:
        return 3
    if pos is not None and 2 <= pos <= 4:
        return 2
    if pos is not None and pos > 4:
        return 1
    return 0


def normalize_result(result: Any, position: Any = None) -> str:
    text = str(result or "").upper()
    pos = safe_int(position)
    if "WON" in text:
        return "WON"
    if "PLACED" in text:
        return "PLACED"
    if "LOST" in text or "UNPLACED" in text or text == "LOSER":
        return "LOST"
    if pos == 1:
        return "WON"
    if pos is not None and 2 <= pos <= 4:
        return "PLACED"
    if pos is not None and pos > 4:
        return "LOST"
    return "UNKNOWN"


def display_position(position: Any, result_text: Any = None) -> Optional[int]:
    pos = safe_int(position)
    if pos is not None and pos > 0:
        return pos
    text = str(result_text or "").upper()
    match = re.search(r"(\d+)(?:ST|ND|RD|TH)", text)
    if match:
        return safe_int(match.group(1))
    return None


def sources_from_horse(horse: Dict[str, Any]) -> Tuple[int, List[str]]:
    consensus = horse.get("consensus") if isinstance(horse.get("consensus"), dict) else {}
    sources = consensus.get("sources") or consensus.get("tipsters") or horse.get("sources") or []
    if not isinstance(sources, list):
        sources = [str(sources)]
    count = (
        safe_int(consensus.get("source_count"))
        or safe_int(consensus.get("tip_count"))
        or safe_int(horse.get("tipsters"))
        or len(sources)
        or 0
    )
    return count, [str(s) for s in sources if s]


def horse_key(name: Any, course: Any = None, time: Any = None) -> Tuple[str, str, str]:
    return (norm_name(name), str(course or "").strip().lower(), str(time or "").strip())


def build_result_lookup(daily: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    for tab in ("flat", "jumps"):
        for entry in daily.get(tab, []) or []:
            horse = extract_horse_from_pick(entry)
            key = norm_name(horse.get("name"))
            if key:
                lookup[key] = horse
    for tab in ("topRatedFlat", "topRatedJumps", "topRated"):
        for horse in daily.get(tab, []) or []:
            key = norm_name(horse.get("name"))
            if key and key not in lookup:
                lookup[key] = horse
    return lookup


def add_label(labels: List[str], evidence: Dict[str, str], label: str, note: str) -> None:
    if label not in labels:
        labels.append(label)
    evidence.setdefault(label, note)


def collect_inputs(target_date: str) -> Tuple[Dict[str, Any], Dict[str, bool], Dict[str, Any]]:
    paths = {
        "daily_archive": DATA_DIR / f"{target_date}.json",
        "consensus_shadow": DATA_DIR / f"consensus_shadow_{target_date}.json",
        "late_value_shadow": DATA_DIR / f"late_value_shadow_{target_date}.json",
        "consensus_overlay": DATA_DIR / f"consensus_overlay_{target_date}.json",
        "confirmed_tips": DATA_DIR / f"confirmed_tips_{target_date}.json",
        "horse_intelligence": DATA_DIR / "horse_intelligence" / f"race_intelligence_{target_date}.json",
        "intelligence_review": DATA_DIR / "intelligence_reviews" / f"review_{target_date}.json",
        "runner_cache": DATA_DIR / "runner_cache" / f"today_runners_{target_date}.json",
        "system_config": DATA_DIR / "system_config.json",
    }
    status = {f"{name}_found": path.exists() for name, path in paths.items()}
    inputs = {name: load_json(path, {} if name != "runner_cache" else []) for name, path in paths.items()}
    return inputs, status, {name: str(path) for name, path in paths.items()}


def official_entries(daily: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for tab in ("flat", "jumps"):
        for rank, entry in enumerate(daily.get(tab, []) or [], start=1):
            horse = extract_horse_from_pick(entry)
            horse["_tab"] = tab
            horse["_rank"] = rank
            horse["_selection_type"] = "OFFICIAL_PICK"
            entries.append(horse)
    return entries


def radar_entries(daily: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for tab, key in (("flat", "topRatedFlat"), ("jumps", "topRatedJumps")):
        for rank, horse in enumerate(daily.get(key, []) or [], start=1):
            item = dict(horse)
            item["_tab"] = tab
            item["_rank"] = rank
            item["_selection_type"] = "RADAR_PICK"
            entries.append(item)
    return entries


def late_lookup(late: Dict[str, Any]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for section in ("official_now", "moved_into_value_band"):
        for item in late.get(section, []) or []:
            lookup[horse_key(item.get("name"), item.get("course"), item.get("time"))] = item
            lookup[(norm_name(item.get("name")), "", "")] = item
    for variant in (late.get("variants") or {}).values():
        for item in variant.get("picks", []) if isinstance(variant, dict) else []:
            lookup.setdefault(horse_key(item.get("name"), item.get("course"), item.get("time")), item)
            lookup.setdefault((norm_name(item.get("name")), "", ""), item)
    return lookup


def find_late(late_map: Dict[Tuple[str, str, str], Dict[str, Any]], horse: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return late_map.get(horse_key(horse.get("name"), horse.get("course") or horse.get("venue"), horse.get("time"))) or late_map.get((norm_name(horse.get("name")), "", ""))


def diagnose_horse(
    horse: Dict[str, Any],
    selection_type: str,
    official_course_counts: Counter,
    official_trainer_counts: Counter,
    late_map: Dict[Tuple[str, str, str], Dict[str, Any]],
    result_lookup: Dict[str, Dict[str, Any]],
    shadow_variants: Optional[List[str]] = None,
) -> Dict[str, Any]:
    name = horse.get("name") or horse.get("horse") or "Unknown"
    course = horse.get("course") or horse.get("venue")
    time = horse.get("time")
    late = find_late(late_map, horse) or {}
    result_source = result_lookup.get(norm_name(name), {})

    result_text = horse.get("result") or horse.get("radarResult") or result_source.get("result") or result_source.get("radarResult")
    position = display_position(horse.get("position") or result_source.get("position"), result_text)
    result = normalize_result(result_text, position)
    score = safe_float(horse.get("signal_score") or horse.get("score") or late.get("morning_score") or late.get("late_score"))
    bsp = safe_float(horse.get("odds") or horse.get("bsp") or late.get("morning_bsp") or late.get("late_bsp"))
    tipster_count, tipster_sources = sources_from_horse(horse)
    trainer = horse.get("trainer") or late.get("trainer")

    labels: List[str] = []
    evidence: Dict[str, str] = {}
    warnings: List[str] = []
    positives: List[str] = []
    missing: List[str] = []

    going_runs = safe_int(horse.get("goingRuns"))
    going_wins = safe_int(horse.get("goingWins"))
    course_wins = safe_int(horse.get("courseWins"))
    distance_wins = safe_int(horse.get("distanceWins"))
    form = horse.get("formStr") or horse.get("form") or late.get("form")

    if score is not None and score >= 88:
        positives.append("High Signal 75 score.")
        if result in ("WON", "PLACED"):
            add_label(labels, evidence, "CONFIRMED_MODEL", "High Signal 75 score and horse won or placed.")
        elif result == "LOST":
            add_label(labels, evidence, "UNDERPERFORMED", "High Signal 75 score but horse lost.")
            warnings.append("High score did not convert into a result.")

    if tipster_count > 0:
        positives.append(f"Tipster support recorded from {tipster_count} source(s).")
        if result in ("WON", "PLACED"):
            add_label(labels, evidence, "TIPSTER_SUPPORT_HELPED", "Tipster-backed horse won or placed.")
            add_label(labels, evidence, "CONSENSUS_CONFIRMED", "Tipster-backed horse won or placed.")
        elif result == "LOST":
            add_label(labels, evidence, "TIPSTER_SUPPORT_FAILED", "Tipster-backed horse lost.")
            warnings.append("Tipster support did not lead to a result.")

    if going_runs is None:
        missing.append("goingRuns missing")
    elif going_runs == 0:
        add_label(labels, evidence, "UNPROVEN_GOING", "No going record in stored data.")
        warnings.append("No proven going record in the stored data.")
    elif going_wins is not None and going_wins == 0 and going_runs >= 3:
        add_label(labels, evidence, "POOR_GOING_FIT", "No going wins from at least 3 going runs.")
        warnings.append("Stored going record looks weak.")
    elif going_wins is not None and going_runs > 0 and going_wins / going_runs >= 0.25:
        add_label(labels, evidence, "STRONG_GOING_FIT", "Good win rate on the recorded going.")
        positives.append("Stored going record looks positive.")

    if course_wins is None:
        missing.append("courseWins missing")
    elif course_wins == 0:
        add_label(labels, evidence, "UNPROVEN_COURSE", "No course wins in stored data.")
    elif course_wins >= 2 and result in ("WON", "PLACED"):
        add_label(labels, evidence, "COURSE_SPECIALIST", "Multiple course wins and horse won or placed.")

    if distance_wins is None:
        missing.append("distanceWins missing")
    elif distance_wins == 0:
        add_label(labels, evidence, "UNPROVEN_TRIP", "No distance wins in stored data.")
        warnings.append("No proven distance win in the stored data.")
    elif distance_wins >= 2 and result in ("WON", "PLACED"):
        add_label(labels, evidence, "PROVEN_DISTANCE", "Multiple distance wins and horse won or placed.")

    if form:
        usable = len(re.findall(r"[1-9]", str(form)))
        if usable < 4:
            add_label(labels, evidence, "THIN_DATA_RISK", "Form string has fewer than 4 usable run figures.")
            warnings.append("Limited recent form evidence.")
        elif result in ("WON", "PLACED"):
            add_label(labels, evidence, "RECENT_FORM_CONFIRMED", "Stored recent form was followed by a good result.")
    else:
        add_label(labels, evidence, "INSUFFICIENT_EVIDENCE", "No form string available.")
        missing.append("form missing")

    signals = late.get("signals") or horse.get("signals") or []
    if not isinstance(signals, list):
        signals = [str(signals)]
    if "MARKET_DRIFTED" in signals:
        warnings.append("Market drifted before the race.")
        if result == "LOST":
            add_label(labels, evidence, "MARKET_DRIFT_CONFIRMED", "Horse drifted and lost.")
        elif result in ("WON", "PLACED"):
            add_label(labels, evidence, "MARKET_DRIFT_FALSE_ALARM", "Horse drifted but won or placed.")
    if "MARKET_SHORTENED" in signals or "MOVED_INTO_VALUE_BAND" in signals:
        positives.append("Market support or value-band move recorded.")
        if result in ("WON", "PLACED"):
            add_label(labels, evidence, "MARKET_SUPPORT_CONFIRMED", "Horse shortened or moved into value and won/placed.")
        elif result == "LOST":
            add_label(labels, evidence, "MARKET_SUPPORT_FAILED", "Horse shortened or moved into value but lost.")
            warnings.append("Market support did not lead to a result.")

    course_key = str(course or "").lower()
    trainer_key = str(trainer or "").lower()
    if selection_type == "OFFICIAL_PICK" and course_key and official_course_counts[course_key] >= 2:
        add_label(labels, evidence, "SAME_COURSE_CLUSTER_RISK", "Two or more official picks shared the same course.")
        warnings.append("Official Patent had a same-course cluster.")
    if selection_type == "OFFICIAL_PICK" and trainer_key and official_trainer_counts[trainer_key] >= 2:
        add_label(labels, evidence, "SAME_TRAINER_CLUSTER_RISK", "Two or more official picks shared the same trainer.")
        warnings.append("Official Patent had a same-trainer cluster.")

    if tipster_count >= 2 and result == "LOST" and any(label in labels for label in ("POOR_GOING_FIT", "UNPROVEN_TRIP", "MARKET_DRIFT_CONFIRMED", "SAME_COURSE_CLUSTER_RISK", "SAME_TRAINER_CLUSTER_RISK")):
        add_label(labels, evidence, "CONSENSUS_TRAP", "Multiple tipster sources plus a suitability warning, followed by a loss.")

    if not labels:
        add_label(labels, evidence, "UNKNOWN_CAUSE", "Stored data was not enough to prove a specific diagnosis label.")

    lesson = build_lesson(name, result, labels, warnings, positives)
    future_watch = build_future_watch(labels, missing)

    return {
        "horse": str(name),
        "selection_type": selection_type,
        "shadow_variants": shadow_variants or [],
        "course": course,
        "time": time,
        "race_type": horse.get("race_type") or horse.get("type") or late.get("race_type"),
        "surface": None,
        "going": horse.get("going"),
        "distance": horse.get("distance") or horse.get("race"),
        "signal_score": score,
        "bsp": bsp,
        "tipster_count": tipster_count,
        "tipster_sources": tipster_sources,
        "trainer": trainer,
        "jockey": horse.get("jockey") or late.get("jockey"),
        "form": form,
        "days_since_last_run": safe_int(late.get("days_since")),
        "going_wins": going_wins,
        "going_runs": going_runs,
        "course_wins": course_wins,
        "distance_wins": distance_wins,
        "result": result,
        "finishing_position": position,
        "field_size": safe_int(horse.get("runners")),
        "market_signals": signals,
        "morning_bsp": safe_float(late.get("morning_bsp")),
        "late_bsp": safe_float(late.get("late_bsp")),
        "bsp_movement": movement_label(signals),
        "diagnosis_labels": labels,
        "label_evidence": evidence,
        "warning_signs_before_race": sorted(set(warnings)),
        "positive_signs_before_race": sorted(set(positives)),
        "missing_or_limited_data": sorted(set(missing)),
        "lesson": lesson,
        "future_watch_note": future_watch,
    }


def movement_label(signals: Iterable[str]) -> Optional[str]:
    signals = set(signals or [])
    if "MOVED_INTO_VALUE_BAND" in signals:
        return "MOVED_INTO_VALUE_BAND"
    if "MARKET_SHORTENED" in signals:
        return "SHORTENED"
    if "MARKET_DRIFTED" in signals:
        return "DRIFTED"
    return None


def build_lesson(name: str, result: str, labels: List[str], warnings: List[str], positives: List[str]) -> str:
    if result == "WON":
        return f"{name} confirmed the model on the available data." if "CONFIRMED_MODEL" in labels else f"{name} won; keep tracking which pre-race positives mattered."
    if result == "PLACED":
        return f"{name} produced a place result; useful for each-way learning, but not a win."
    if "MARKET_SUPPORT_FAILED" in labels:
        return f"{name} had market support, but that support was not enough."
    if "MARKET_DRIFT_CONFIRMED" in labels:
        return f"{name} drifted before racing and then lost; keep monitoring late drift."
    if warnings:
        return f"{name} lost with visible caution flags in the stored data."
    if positives:
        return f"{name} lost despite positive pre-race signals; cause remains uncertain."
    return f"{name} needs more stored evidence before a confident diagnosis."


def build_future_watch(labels: List[str], missing: List[str]) -> str:
    if "SAME_TRAINER_CLUSTER_RISK" in labels or "SAME_COURSE_CLUSTER_RISK" in labels:
        return "Watch Patent diversification when course or trainer clustering appears."
    if "MARKET_DRIFT_CONFIRMED" in labels:
        return "Keep late market drift in the watchlist until enough days prove its value."
    if "MARKET_SUPPORT_FAILED" in labels:
        return "Do not treat market support alone as proof."
    if missing:
        return "Improve stored race context before drawing stronger conclusions."
    return "Continue logging; no live rule change from this single case."


def shadow_comparison(shadow: Dict[str, Any], live_profit: float) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[float], bool]:
    rows: List[Dict[str, Any]] = []
    labels: List[str] = []
    best_name = None
    best_profit = None
    shadow_beat_live = False
    variants = shadow.get("variants") or {}
    results = shadow.get("results") or {}
    for name, variant in variants.items():
        picks = variant.get("picks", []) if isinstance(variant, dict) else []
        result = results.get(name, {}) if isinstance(results, dict) else {}
        profit = money(result.get("patentProfit"))
        ret = money(result.get("patentReturn"))
        if best_profit is None or profit > best_profit:
            best_name = name
            best_profit = profit
        vs_live = "BASELINE" if name == "tipster_first_live_rule" else ("BETTER_THAN_LIVE" if profit > live_profit else "WORSE_THAN_LIVE" if profit < live_profit else "SAME_AS_LIVE")
        if profit > live_profit and name != "tipster_first_live_rule":
            shadow_beat_live = True
        rows.append({
            "variant": name,
            "description": variant.get("description") if isinstance(variant, dict) else None,
            "picks": [p.get("name") for p in picks if isinstance(p, dict)],
            "number_of_picks": len(picks),
            "full_patent_possible": len(picks) >= 3 and not result.get("noBet", False),
            "patent_return": ret,
            "patent_profit": profit,
            "vs_live": vs_live,
        })
    if shadow_beat_live:
        labels.append("SHADOW_BEAT_LIVE")
    return rows, labels, best_name, best_profit, shadow_beat_live


def shadow_result_lookup(shadow: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for variant, result_block in (shadow.get("results") or {}).items():
        for result in result_block.get("results", []) if isinstance(result_block, dict) else []:
            name = norm_name(result.get("name"))
            if name:
                lookup[(variant, name)] = result
    return lookup


def radar_vs_official(official: List[Dict[str, Any]], radar: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    labels: List[str] = []
    rows: List[Dict[str, Any]] = []
    radar_by_tab: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in radar:
        radar_by_tab[r.get("_tab", "")].append(r)

    for tab in ("flat", "jumps"):
        official_lost = []
        alternatives = []
        for item in official:
            if item.get("_tab") != tab:
                continue
            if normalize_result(item.get("result"), item.get("position")) == "LOST":
                official_lost.append(str(item.get("name")))
        if not official_lost:
            continue
        for r in radar_by_tab.get(tab, []):
            res = normalize_result(r.get("result") or r.get("radarResult"), r.get("position"))
            if result_rank(res, r.get("position")) >= 2:
                pos = display_position(r.get("position"), r.get("radarResult"))
                alternatives.append(f"{r.get('name')} - {res}" + (f" {pos}" if pos else ""))
        if alternatives:
            labels.append("RADAR_OUTPERFORMED_OFFICIAL")
            labels.append("RADAR_SHOULD_HAVE_QUALIFIED")
            rows.append({
                "tab": tab,
                "official_lost": official_lost,
                "radar_did_better": alternatives,
                "verdict": "RADAR_SHOULD_HAVE_QUALIFIED",
                "note": "Radar horse(s) won or placed while official pick(s) in the same tab lost.",
            })
    return rows, labels


def live_profit_from_daily(daily: Dict[str, Any], shadow: Dict[str, Any]) -> float:
    result = ((shadow.get("results") or {}).get("tipster_first_live_rule") or {})
    if "patentProfit" in result:
        return money(result.get("patentProfit"))
    results = daily.get("results") or {}
    return money(results.get("profit") or results.get("patentProfit") or 0.0)


def build_report(target_date: str) -> Dict[str, Any]:
    inputs, input_status, source_paths = collect_inputs(target_date)
    daily = inputs["daily_archive"] or {}
    shadow = inputs["consensus_shadow"] or {}
    late = inputs["late_value_shadow"] or {}
    confirmed_tips = inputs["confirmed_tips"] or {}

    official = official_entries(daily)
    radar = radar_entries(daily)
    result_lookup = build_result_lookup(daily)
    late_map = late_lookup(late)
    official_course_counts = Counter(str(h.get("course") or "").lower() for h in official if h.get("course"))
    official_trainer_counts = Counter(str(h.get("trainer") or "").lower() for h in official if h.get("trainer"))

    live_profit = live_profit_from_daily(daily, shadow)
    shadow_rows, shadow_labels, best_shadow, best_shadow_profit, shadow_beat_live = shadow_comparison(shadow, live_profit)
    shadow_results = shadow_result_lookup(shadow)
    radar_rows, radar_labels = radar_vs_official(official, radar)

    daily_flags = sorted(set(shadow_labels + radar_labels))
    for _, count in official_course_counts.items():
        if count >= 2:
            daily_flags.append("SAME_COURSE_CLUSTER_RISK")
            break
    for _, count in official_trainer_counts.items():
        if count >= 2:
            daily_flags.append("SAME_TRAINER_CLUSTER_RISK")
            break
    daily_flags = sorted(set(daily_flags))

    horses: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()

    for h in official:
        rec = diagnose_horse(h, "OFFICIAL_PICK", official_course_counts, official_trainer_counts, late_map, result_lookup)
        horses.append(rec)
        seen.add((norm_name(rec["horse"]), "OFFICIAL_PICK"))

    for h in radar:
        rec = diagnose_horse(h, "RADAR_PICK", official_course_counts, official_trainer_counts, late_map, result_lookup)
        horses.append(rec)
        seen.add((norm_name(rec["horse"]), "RADAR_PICK"))

    official_names = {norm_name(h.get("name")) for h in official}
    shadow_names: Dict[str, List[str]] = defaultdict(list)
    for variant_name, variant in (shadow.get("variants") or {}).items():
        for p in variant.get("picks", []) if isinstance(variant, dict) else []:
            name_key = norm_name(p.get("name"))
            if name_key and name_key not in official_names:
                shadow_names[name_key].append(variant_name)
                if (name_key, "SHADOW_PICK") not in seen:
                    item = dict(p)
                    result = shadow_results.get((variant_name, name_key))
                    if result:
                        item.setdefault("result", result.get("result"))
                        item.setdefault("position", result.get("position"))
                        item.setdefault("return", result.get("totalReturn"))
                    rec = diagnose_horse(item, "SHADOW_PICK", official_course_counts, official_trainer_counts, late_map, result_lookup, [variant_name])
                    horses.append(rec)
                    seen.add((name_key, "SHADOW_PICK"))
    for rec in horses:
        if rec["selection_type"] == "SHADOW_PICK":
            rec["shadow_variants"] = sorted(set(shadow_names.get(norm_name(rec["horse"]), rec["shadow_variants"])))

    for item in late.get("moved_into_value_band", []) or []:
        key = norm_name(item.get("name"))
        if key and (key, "LATE_VALUE_ALERT") not in seen:
            rec = diagnose_horse(item, "LATE_VALUE_ALERT", official_course_counts, official_trainer_counts, late_map, result_lookup)
            horses.append(rec)
            seen.add((key, "LATE_VALUE_ALERT"))

    for tip in confirmed_tips.get("tips", []) or []:
        key = norm_name(tip.get("horse"))
        if key and key not in official_names and (key, "TIPSTER_ONLY_ALERT") not in seen:
            item = {
                "name": tip.get("horse"),
                "sources": tip.get("sources") or [],
                "tipsters": len(tip.get("sources") or tip.get("tipsters") or []),
            }
            rec = diagnose_horse(item, "TIPSTER_ONLY_ALERT", official_course_counts, official_trainer_counts, late_map, result_lookup)
            rec["tipster_sources"] = tip.get("sources") or tip.get("tipsters") or []
            rec["tipster_count"] = len(rec["tipster_sources"])
            horses.append(rec)
            seen.add((key, "TIPSTER_ONLY_ALERT"))

    official_winners = sum(1 for h in horses if h["selection_type"] == "OFFICIAL_PICK" and h["result"] == "WON")
    official_placed = sum(1 for h in horses if h["selection_type"] == "OFFICIAL_PICK" and h["result"] in ("WON", "PLACED"))
    radar_winners = sum(1 for h in horses if h["selection_type"] == "RADAR_PICK" and h["result"] == "WON")
    radar_placed = sum(1 for h in horses if h["selection_type"] == "RADAR_PICK" and h["result"] in ("WON", "PLACED"))

    labels_today = sorted(set(daily_flags + [label for h in horses for label in h["diagnosis_labels"]]))
    main_lessons = build_main_lessons(official, radar_winners, radar_placed, daily_flags, shadow_beat_live)

    report = {
        "date": target_date,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "analysis_only": True,
        "status": "ok" if daily else "missing_daily_archive",
        "input_status": input_status,
        "source_paths": source_paths,
        "daily_flags": daily_flags,
        "summary": {
            "official_picks": len(official),
            "official_winners": official_winners,
            "official_placed": official_placed,
            "radar_horses": len(radar),
            "radar_winners": radar_winners,
            "radar_placed": radar_placed,
            "shadow_beat_live": shadow_beat_live,
            "best_shadow_variant": best_shadow,
            "best_shadow_profit": best_shadow_profit,
            "live_profit": live_profit,
            "main_lessons": main_lessons,
        },
        "horses": horses,
        "shadow_comparison": shadow_rows,
        "radar_vs_official": radar_rows,
        "pattern_update": {"labels_added_today": labels_today},
        "recommendation": {
            "action": "LOG_ONLY",
            "confidence": "LOW",
            "reason": "Observational diagnosis only. No live rule change until repeated patterns are proven.",
        },
    }
    return report


def build_main_lessons(official: List[Dict[str, Any]], radar_winners: int, radar_placed: int, daily_flags: List[str], shadow_beat_live: bool) -> List[str]:
    lessons: List[str] = []
    official_lost = sum(1 for h in official if normalize_result(h.get("result"), h.get("position")) == "LOST")
    if official and official_lost == len(official):
        lessons.append("All official picks lost.")
    elif official:
        lessons.append(f"{len(official) - official_lost} official pick(s) won or placed.")
    if "SAME_COURSE_CLUSTER_RISK" in daily_flags:
        lessons.append("Official picks included a same-course cluster.")
    if "SAME_TRAINER_CLUSTER_RISK" in daily_flags:
        lessons.append("Official picks included a same-trainer cluster.")
    if radar_winners or radar_placed:
        lessons.append(f"Radar produced {radar_winners} winner(s) and {radar_placed} won/placed result(s).")
    if shadow_beat_live:
        lessons.append("At least one shadow rule beat the live rule on paper.")
    if not lessons:
        lessons.append("No strong repeated warning pattern was proven from stored data.")
    return lessons


def archive_existing(path: Path) -> None:
    if not path.exists():
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, ARCHIVE_DIR / f"{path.stem}_{stamp}{path.suffix}")


def write_report(report: Dict[str, Any]) -> Tuple[Path, Path]:
    DIAGNOSIS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = DIAGNOSIS_DIR / f"diagnosis_{report['date']}.json"
    txt_path = DIAGNOSIS_DIR / f"diagnosis_{report['date']}.txt"
    archive_existing(json_path)
    archive_existing(txt_path)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    txt_path.write_text(text_report(report), encoding="utf-8")
    return json_path, txt_path


def text_report(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "SIGNAL 75 - POST-RACE DIAGNOSIS",
        f"Date: {report['date']}",
        f"Generated: {report['generated_at']}",
        "",
        "STATUS",
        "Analysis only - no scoring or proof changes made.",
        "",
        "INPUTS",
    ]
    for key, ok in sorted(report["input_status"].items()):
        lines.append(f"- {key}: {'found' if ok else 'missing'}")
    lines.extend(["", "DAILY FLAGS"])
    lines.extend([f"- {flag}" for flag in report["daily_flags"]] or ["- None proven"])
    lines.extend([
        "",
        "OFFICIAL PICKS",
        f"Picks: {summary['official_picks']}",
        f"Winners: {summary['official_winners']}",
        f"Won/placed: {summary['official_placed']}",
        "",
        "RADAR HORSES",
        f"Horses: {summary['radar_horses']}",
        f"Winners: {summary['radar_winners']}",
        f"Won/placed: {summary['radar_placed']}",
        "",
        "SHADOW VARIANT COMPARISON",
    ])
    if report["shadow_comparison"]:
        for row in report["shadow_comparison"]:
            lines.append(f"- {row['variant']}: return {pretty_money(row['patent_return'])}, profit {pretty_money(row['patent_profit'])}, {row['vs_live']}")
    else:
        lines.append("- No shadow file available.")
    lines.extend(["", "RADAR VS OFFICIAL"])
    if report["radar_vs_official"]:
        for row in report["radar_vs_official"]:
            lines.append(f"- {row['tab']}: {row['verdict']} - {row['note']}")
            for alt in row["radar_did_better"]:
                lines.append(f"  - {alt}")
    else:
        lines.append("- No radar horse clearly outperformed official losers from stored data.")
    lines.extend(["", "HORSE DIAGNOSES"])
    for horse in report["horses"]:
        lines.extend([
            "",
            f"Horse: {horse['horse']}",
            f"Type: {horse['selection_type']}",
            f"Result: {horse['result']}" + (f" - position {horse['finishing_position']}" if horse.get("finishing_position") else ""),
            f"Score: {horse.get('signal_score')}",
            f"BSP: {horse.get('bsp')}",
            f"Tipsters: {horse.get('tipster_count')} ({', '.join(horse.get('tipster_sources') or []) or 'none recorded'})",
            f"Labels: {', '.join(horse['diagnosis_labels'])}",
            "Warnings: " + ("; ".join(horse["warning_signs_before_race"]) if horse["warning_signs_before_race"] else "None proven"),
            "Positive signs: " + ("; ".join(horse["positive_signs_before_race"]) if horse["positive_signs_before_race"] else "None proven"),
            "Lesson: " + horse["lesson"],
            "Future watch: " + horse["future_watch_note"],
        ])
    lines.extend(["", "KEY LESSONS TODAY"])
    for idx, lesson in enumerate(summary["main_lessons"], start=1):
        lines.append(f"{idx}. {lesson}")
    lines.extend([
        "",
        "PATTERN ACCUMULATOR UPDATE",
        "Label counts updated from diagnosis files.",
        "",
        "RECOMMENDATION",
        "No live rule change. Continue collecting.",
        "",
    ])
    return "\n".join(lines)


def recompute_accumulator() -> Dict[str, Any]:
    DIAGNOSIS_DIR.mkdir(parents=True, exist_ok=True)
    label_counts: Counter = Counter()
    analysed_dates: List[str] = []
    for path in sorted(DIAGNOSIS_DIR.glob("diagnosis_*.json")):
        if path.name == PATTERN_FILE.name:
            continue
        report = load_json(path, {})
        if not isinstance(report, dict) or not report.get("date"):
            continue
        analysed_dates.append(report["date"])
        labels = set(report.get("daily_flags") or [])
        labels.update(report.get("pattern_update", {}).get("labels_added_today") or [])
        for horse in report.get("horses") or []:
            labels.update(horse.get("diagnosis_labels") or [])
        label_counts.update(labels)

    days = len(set(analysed_dates))
    emerging = []
    alerts = []
    for label, count in label_counts.most_common():
        if count >= 2:
            rate = (count / days * 100.0) if days else 0.0
            emerging.append({
                "pattern": label,
                "count": count,
                "days_analysed": days,
                "rate": f"{rate:.1f}%",
                "note": f"{label} has appeared on {count} of {days} analysed day(s).",
            })
        threshold = THRESHOLDS.get(label)
        if threshold and count >= threshold:
            alerts.append({
                "label": label,
                "count": count,
                "threshold": threshold,
                "message": f"{label} has fired {count} times. Review before changing any live rule.",
            })

    accumulator = {
        "last_updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "days_analysed": days,
        "analysed_dates": sorted(set(analysed_dates)),
        "label_counts": dict(sorted(label_counts.items())),
        "emerging_patterns": emerging,
        "threshold_alerts": alerts,
    }
    with PATTERN_FILE.open("w", encoding="utf-8") as f:
        json.dump(accumulator, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return accumulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create analysis-only Signal 75 post-race diagnosis.")
    parser.add_argument("--date", default=(date.today() - timedelta(days=1)).isoformat(), help="Race date to diagnose. Defaults to yesterday.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args.date)
    json_path, txt_path = write_report(report)
    accumulator = recompute_accumulator()
    print(f"Diagnosis status: {report['status']}")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {txt_path}")
    print(f"Pattern days analysed: {accumulator['days_analysed']}")
    print(f"Pattern labels tracked: {len(accumulator['label_counts'])}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
