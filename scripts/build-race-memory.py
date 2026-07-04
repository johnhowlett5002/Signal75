#!/usr/bin/env python3
"""Build Signal 75 race memory.

Analysis only. This is the "little book" layer: it records every runner
available in the daily runner cache, then adds Signal 75 labels and known
results where we have them. It does not change scoring, pick generation,
settlement, proof, app data, or public results.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
RUNNER_CACHE = DATA_DIR / "today_runners.json"
MASTER_FILE = INTEL_DIR / "race_memory_master.jsonl"
PROFILE_FILE = INTEL_DIR / "horse_memory_profiles.json"
HISTORY_DB = INTEL_DIR / "signal75_history.sqlite"

VALUE_MIN = 2.0
VALUE_MAX = 12.0
BETFAIR_CHUNK_SIZE = 25

RACE_CLASS_LEVELS = {
    "Group 1": 1,
    "Group 2": 2,
    "Group 3": 3,
    "Listed": 4,
    "Class 1": 4,
    "Class 2": 5,
    "Class 3": 6,
    "Class 4": 7,
    "Class 5": 8,
    "Class 6": 9,
    "Class 7": 10,
    "Handicap": 7,
}


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def display_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def clean_course(value: Any) -> str:
    course = display_name(value)
    course = re.sub(r"\s+\d+(st|nd|rd|th)?\s+\w+$", "", course, flags=re.I)
    return course


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


def race_time_hhmm(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(\d{1,2}:\d{2})\b", text)
    return match.group(1) if match else None


def race_class_info(*parts: Any) -> Dict[str, Any]:
    """Best-effort race standard from available race labels.

    Lower level means a stronger race. This is memory/context only, not scoring.
    """
    text = " ".join(display_name(part) for part in parts if part).lower()
    tags: List[str] = []

    group_match = re.search(r"\b(?:group|grp|g)\s*([123])\b", text)
    if group_match:
        label = f"Group {group_match.group(1)}"
        return {
            "label": label,
            "level": RACE_CLASS_LEVELS[label],
            "source": "race_name",
            "tags": [f"GROUP_{group_match.group(1)}", "GROUP_RACE"],
        }

    if re.search(r"\b(?:listed|lst)\b", text):
        return {
            "label": "Listed",
            "level": RACE_CLASS_LEVELS["Listed"],
            "source": "race_name",
            "tags": ["LISTED_RACE"],
        }

    class_match = re.search(r"\b(?:class|cls)\s*([1-7])\b", text)
    if class_match:
        label = f"Class {class_match.group(1)}"
        return {
            "label": label,
            "level": RACE_CLASS_LEVELS[label],
            "source": "race_name",
            "tags": [f"CLASS_{class_match.group(1)}"],
        }

    if "hcap" in text or "handicap" in text:
        return {
            "label": "Handicap",
            "level": RACE_CLASS_LEVELS["Handicap"],
            "source": "race_name",
            "tags": ["HANDICAP"],
        }

    if "maiden" in text:
        tags.append("MAIDEN")
    if "novice" in text or "novices" in text:
        tags.append("NOVICE")

    return {"label": "Unknown", "level": None, "source": "", "tags": tags}


def class_movement(current_level: Optional[int], previous_level: Optional[int]) -> Tuple[str, Optional[int], List[str]]:
    if current_level is None or previous_level is None:
        return "unknown", None, []
    steps = current_level - previous_level
    if steps > 0:
        return "class_drop", steps, ["CLASS_DROP"]
    if steps < 0:
        return "class_rise", steps, ["CLASS_RISE"]
    return "same_class", 0, ["SAME_CLASS"]


def recent_poor_form(form: Any, limit: int = 6) -> bool:
    markers = re.findall(r"[0-9PFURB]", str(form or "").upper())
    recent = markers[-limit:]
    if not recent:
        return False
    poor = sum(1 for marker in recent if marker in {"0", "P", "F", "U", "R", "B"} or marker.isdigit() and int(marker) >= 7)
    return poor >= 2


def historical_class_context_map(horse_keys: Iterable[str], target_date: str) -> Dict[str, Dict[str, Any]]:
    context: Dict[str, Dict[str, Any]] = {}
    keys = sorted({key for key in horse_keys if key})
    if not keys or not HISTORY_DB.exists():
        return context

    try:
        conn = sqlite3.connect(f"file:{HISTORY_DB}?mode=ro", uri=True)
    except sqlite3.Error:
        return context

    try:
        for key in keys:
            try:
                rows = conn.execute(
                    """
                    SELECT race_date, race_name, race_type, race_subtype, venue, distance_furlongs
                    FROM historical_runners
                    WHERE horse_key = ?
                      AND race_date IS NOT NULL
                      AND race_date < ?
                      AND COALESCE(market_type, '') = 'WIN'
                    ORDER BY race_date DESC
                    LIMIT 8
                    """,
                    (key, target_date),
                ).fetchall()
            except sqlite3.Error:
                rows = []

            class_path: List[Dict[str, Any]] = []
            for race_date, race_name, race_type, race_subtype, venue, distance in rows:
                info = race_class_info(race_name, race_type, race_subtype)
                class_path.append(
                    {
                        "date": race_date,
                        "course": display_name(venue),
                        "race_name": display_name(race_name),
                        "race_type": display_name(race_type),
                        "race_subtype": display_name(race_subtype),
                        "distance_furlongs": safe_float(distance),
                        "race_class_label": info["label"],
                        "race_class_level": info["level"],
                    }
                )

            previous = next((item for item in class_path if item.get("race_class_level") is not None), None)
            context[key] = {
                "recent_class_path": class_path,
                "previous_race_date": previous.get("date") if previous else None,
                "previous_race_name": previous.get("race_name") if previous else None,
                "previous_race_course": previous.get("course") if previous else None,
                "previous_race_class_label": previous.get("race_class_label") if previous else None,
                "previous_race_class_level": previous.get("race_class_level") if previous else None,
            }
    finally:
        conn.close()

    return context


def result_bucket(result: Any, position: Any = None, field_size: Any = None) -> str:
    text = str(result or "").upper()
    pos = safe_int(position)
    runners = safe_int(field_size) or 8

    if any(x in text for x in ("VOID", "NON-RUNNER", "NR", "REMOVED", "WITHDRAWN")):
        return "VOID"
    if "WON" in text or pos == 1:
        return "WON"
    if "PLACED" in text:
        return "PLACED"
    if pos is not None and pos > 1:
        if runners < 8 and pos == 2:
            return "PLACED"
        if 8 <= runners <= 11 and pos <= 3:
            return "PLACED"
        if runners >= 12 and pos <= 4:
            return "PLACED"
        return "LOST"
    if any(x in text for x in ("LOST", "LOSER", "UNPLACED")):
        return "LOST"
    return "UNKNOWN"


def fetch_betfair_results(market_ids: Iterable[str]) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Fetch settled Betfair WIN-market evidence for memory only.

    This marks winners and captures BSP. It deliberately avoids treating
    Betfair LOSER status as an each-way place result.
    """
    ids = [market_id for market_id in dict.fromkeys(market_ids) if market_id]
    if not ids:
        return {}

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        from betfair_client import get_client

        trading = get_client()
    except Exception as exc:
        print(f"Betfair memory lookup skipped: {exc}")
        return {}

    results: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for start in range(0, len(ids), BETFAIR_CHUNK_SIZE):
        chunk = ids[start : start + BETFAIR_CHUNK_SIZE]
        try:
            books = trading.betting.list_market_book(
                market_ids=chunk,
                price_projection={"priceData": ["SP_TRADED"]},
            )
        except Exception as exc:
            print(f"Betfair memory lookup skipped for {len(chunk)} markets: {exc}")
            continue

        for book in books:
            market_results: Dict[int, Dict[str, Any]] = {}
            for runner in book.runners:
                sp = runner.sp.actual_sp if runner.sp and runner.sp.actual_sp else None
                market_results[int(runner.selection_id)] = {
                    "status": str(runner.status or "").upper(),
                    "bsp": safe_float(sp),
                }
            results[book.market_id] = market_results
    return results


def extract_horse_from_pick(entry: Dict[str, Any]) -> Dict[str, Any]:
    horses = entry.get("horses")
    if isinstance(horses, list) and horses:
        horse = dict(horses[0])
        for key in ("course", "time", "type", "distance", "going", "runners"):
            horse.setdefault(key, entry.get(key))
        return horse
    return dict(entry)


def consensus_details(horse: Dict[str, Any]) -> Tuple[int, List[str]]:
    consensus = horse.get("consensus") if isinstance(horse.get("consensus"), dict) else {}
    sources = consensus.get("sources") or consensus.get("tipsters") or horse.get("sources") or []
    if not isinstance(sources, list):
        sources = [sources]
    count = (
        safe_int(consensus.get("source_count"))
        or safe_int(consensus.get("tip_count"))
        or safe_int(horse.get("tipsters"))
        or len([s for s in sources if s])
        or 0
    )
    return count, [str(s) for s in sources if s]


def add_signal_lookup(
    lookup: Dict[str, Dict[str, Any]],
    horse: Dict[str, Any],
    label: str,
    rank: Optional[int] = None,
) -> None:
    name = horse.get("name") or horse.get("horse")
    key = norm_name(name)
    if not key:
        return

    existing = lookup.setdefault(key, {"labels": [], "records": []})
    if label not in existing["labels"]:
        existing["labels"].append(label)
    record = dict(horse)
    record["_label"] = label
    record["_rank"] = rank
    existing["records"].append(record)


def build_signal_lookup(daily: Dict[str, Any], performance: Dict[str, Any], target_date: str) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}

    for tab in ("flat", "jumps"):
        for race_rank, race in enumerate(daily.get(tab, []) or [], start=1):
            horse = extract_horse_from_pick(race)
            horse["_tab"] = tab
            add_signal_lookup(lookup, horse, "OFFICIAL_PICK", race_rank)

    for key, label in (
        ("topRatedFlat", "WATCHLIST_FLAT"),
        ("topRatedJumps", "WATCHLIST_JUMPS"),
        ("topRated", "WATCHLIST_ALL"),
    ):
        for rank, horse in enumerate(daily.get(key, []) or [], start=1):
            add_signal_lookup(lookup, horse, label, rank)

    for log_key, label in (("selectionLog", "OFFICIAL_RESULT_LOG"), ("radarLog", "WATCHLIST_RESULT_LOG")):
        for day in performance.get(log_key, []) or []:
            if day.get("date") != target_date:
                continue
            for rank, horse in enumerate(day.get("selections", []) or [], start=1):
                add_signal_lookup(lookup, horse, label, rank)

    return lookup


def best_signal_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    def rank(record: Dict[str, Any]) -> Tuple[int, float]:
        label_score = {
            "OFFICIAL_RESULT_LOG": 5,
            "OFFICIAL_PICK": 4,
            "WATCHLIST_RESULT_LOG": 3,
            "WATCHLIST_FLAT": 2,
            "WATCHLIST_JUMPS": 2,
            "WATCHLIST_ALL": 1,
        }.get(record.get("_label"), 0)
        return label_score, safe_float(record.get("signal_score") or record.get("score")) or 0.0

    return sorted(records, key=rank, reverse=True)[0] if records else {}


def add_tag(tags: List[str], tag: str) -> None:
    if tag not in tags:
        tags.append(tag)


def runner_tags(
    runner: Dict[str, Any],
    signal: Dict[str, Any],
    labels: Iterable[str],
    field_size: int,
    market_rank: int,
    result: str,
) -> List[str]:
    tags: List[str] = []
    label_set = set(labels)
    score = safe_float(signal.get("signal_score") or signal.get("score"))
    price = safe_float(runner.get("best_back") or signal.get("odds") or signal.get("bsp"))
    tipster_count, _ = consensus_details(signal)
    days_since = safe_int(runner.get("days_since"))
    official_rating = safe_int(runner.get("official_rating"))
    form = str(runner.get("form") or signal.get("form") or signal.get("formStr") or "")

    if "OFFICIAL_PICK" in label_set or "OFFICIAL_RESULT_LOG" in label_set:
        add_tag(tags, "OFFICIAL_PICK")
    if any(label.startswith("WATCHLIST") for label in label_set):
        add_tag(tags, "WATCHLIST")
    if score is not None and score >= 75:
        add_tag(tags, "HIGH_SIGNAL_SCORE")
    if score is not None and score >= 90:
        add_tag(tags, "ELITE_SIGNAL_SCORE")
    if tipster_count >= 2:
        add_tag(tags, "MULTIPLE_TIPSTERS")
    elif tipster_count == 1:
        add_tag(tags, "ONE_TIPSTER")
    if price is not None and VALUE_MIN <= price <= VALUE_MAX:
        add_tag(tags, "PRICE_IN_VALUE_BAND")
    if market_rank == 1:
        add_tag(tags, "MARKET_FAVOURITE")
    if market_rank <= 3:
        add_tag(tags, "MARKET_TOP_THREE")
    if price is not None and price >= 12:
        add_tag(tags, "BIG_PRICE")
    if days_since is not None and days_since <= 21:
        add_tag(tags, "RECENT_RUN")
    if days_since is not None and days_since >= 120:
        add_tag(tags, "LONG_LAYOFF")
    if official_rating and official_rating > 0:
        add_tag(tags, "HAS_OFFICIAL_RATING")
    if re.search(r"1[-/ ]?$", form):
        add_tag(tags, "WON_LAST_TIME")
    if "F" in form or "P" in form or "U" in form:
        add_tag(tags, "RECENT_COMPLETION_RISK")
    if result == "WON":
        add_tag(tags, "WINNER")
    elif result == "PLACED":
        add_tag(tags, "PLACED")
    elif result == "LOST":
        add_tag(tags, "UNPLACED")
    elif result == "VOID":
        add_tag(tags, "VOID")
    else:
        add_tag(tags, "RESULT_NOT_KNOWN")

    return tags


def insight_text(name: str, result: str, tags: List[str], signal: Dict[str, Any]) -> str:
    score = safe_float(signal.get("signal_score") or signal.get("score"))
    if "POOR_FORM_SOFTENED_BY_CLASS_DROP" in tags:
        return f"{name} has poor recent form, but recent stronger-race context may explain part of it."
    if result == "WON" and "WATCHLIST" in tags:
        return f"{name} is a book horse: watchlist runner won and should be noticed next time."
    if result == "PLACED" and "WATCHLIST" in tags:
        return f"{name} is a book horse: watchlist runner placed and may be worth tracking again."
    if result == "LOST" and score is not None and score >= 90:
        return f"{name} had a very high score but did not deliver; useful warning evidence for next time."
    if "WON_LAST_TIME" in tags:
        return f"{name} came in with recent winning form; keep that pattern visible."
    if "LONG_LAYOFF" in tags:
        return f"{name} returned from a break; future runs may be more informative than today alone."
    if "MULTIPLE_TIPSTERS" in tags:
        return f"{name} had more than one tipster source; useful consensus evidence."
    return f"{name} logged for future course, price, trainer, jockey and form comparison."


def build_records(target_date: str, use_betfair_results: bool = False) -> Dict[str, Any]:
    runner_cache = load_json(RUNNER_CACHE, {})
    cache_date = runner_cache.get("date")
    daily = load_json(DATA_DIR / f"{target_date}.json", {})
    performance = load_json(REPO_ROOT / "performance.json", {})
    signal_lookup = build_signal_lookup(daily, performance, target_date)
    races = runner_cache.get("races", []) or []
    betfair_results = (
        fetch_betfair_results(race.get("market_id") for race in races)
        if use_betfair_results
        else {}
    )
    horse_keys = [
        norm_name(runner.get("name"))
        for race in races
        for runner in (race.get("runners", []) or [])
        if norm_name(runner.get("name"))
    ]
    historical_class = historical_class_context_map(horse_keys, target_date)

    records: List[Dict[str, Any]] = []
    for race in races:
        market_id = race.get("market_id")
        course = clean_course(race.get("venue"))
        race_time = race_time_hhmm(race.get("race_time"))
        race_name = display_name(race.get("race_name"))
        class_info = race_class_info(race_name, race.get("race_type"), race.get("race_subtype"))
        field_size = safe_int(race.get("field_size")) or len(race.get("runners", []) or [])
        sorted_runners = sorted(
            race.get("runners", []) or [],
            key=lambda r: safe_float(r.get("best_back")) if safe_float(r.get("best_back")) is not None else 9999,
        )
        market_ranks = {norm_name(r.get("name")): idx for idx, r in enumerate(sorted_runners, start=1)}

        for runner in race.get("runners", []) or []:
            name = display_name(runner.get("name"))
            key = norm_name(name)
            signal_match = signal_lookup.get(key, {"labels": [], "records": []})
            labels = signal_match.get("labels", [])
            signal = best_signal_record(signal_match.get("records", []))
            result = result_bucket(
                signal.get("result") or signal.get("radarResult"),
                signal.get("position"),
                field_size,
            )
            market_results = betfair_results.get(str(market_id), {})
            betfair_runner = market_results.get(safe_int(runner.get("selection_id")) or -1, {})
            betfair_status = betfair_runner.get("status")
            betfair_bsp = betfair_runner.get("bsp")
            if result == "UNKNOWN" and betfair_status == "WINNER":
                result = "WON"

            market_rank = market_ranks.get(key, 0)
            tags = runner_tags(runner, signal, labels, field_size, market_rank, result)
            tipster_count, tipster_sources = consensus_details(signal)
            price = safe_float(runner.get("best_back") or signal.get("odds") or signal.get("bsp") or betfair_bsp)
            class_context = historical_class.get(key, {})
            movement, movement_steps, movement_tags = class_movement(
                class_info.get("level"),
                safe_int(class_context.get("previous_race_class_level")),
            )
            race_standard_tags = list(class_info.get("tags") or [])
            for tag in movement_tags:
                add_tag(race_standard_tags, tag)
                add_tag(tags, tag)

            recent_class_path = class_context.get("recent_class_path") if isinstance(class_context.get("recent_class_path"), list) else []
            current_level = safe_int(class_info.get("level"))
            stronger_recent_count = sum(
                1
                for item in recent_class_path
                if current_level is not None
                and safe_int(item.get("race_class_level")) is not None
                and safe_int(item.get("race_class_level")) < current_level
            )
            if stronger_recent_count:
                add_tag(race_standard_tags, "RECENT_STRONGER_RACES")
                add_tag(tags, "RECENT_STRONGER_RACES")
            if movement == "class_drop" and recent_poor_form(runner.get("form") or signal.get("form") or signal.get("formStr")):
                add_tag(race_standard_tags, "POOR_FORM_SOFTENED_BY_CLASS_DROP")
                add_tag(tags, "POOR_FORM_SOFTENED_BY_CLASS_DROP")

            record_id = f"{target_date}|{market_id}|{runner.get('selection_id') or key}"
            records.append(
                {
                    "id": record_id,
                    "date": target_date,
                    "phase": "logging_only",
                    "scoringImpact": "none",
                    "horse_name": name,
                    "normalised_name": key,
                    "course": course,
                    "race_time": race_time,
                    "race_name": race_name,
                    "race_class_label": class_info.get("label"),
                    "race_class_level": class_info.get("level"),
                    "race_class_source": class_info.get("source"),
                    "race_standard_tags": race_standard_tags,
                    "previous_race_date": class_context.get("previous_race_date"),
                    "previous_race_name": class_context.get("previous_race_name"),
                    "previous_race_course": class_context.get("previous_race_course"),
                    "previous_race_class_label": class_context.get("previous_race_class_label"),
                    "previous_race_class_level": class_context.get("previous_race_class_level"),
                    "class_movement": movement,
                    "class_movement_steps": movement_steps,
                    "recent_stronger_races_count": stronger_recent_count,
                    "recent_class_path": recent_class_path,
                    "market_id": market_id,
                    "selection_id": runner.get("selection_id"),
                    "field_size": field_size,
                    "market_rank_by_price": market_rank or None,
                    "pre_race_price": price,
                    "bsp": betfair_bsp,
                    "settlement_odds": safe_float(signal.get("settlementOdds")),
                    "settlement_odds_source": signal.get("settlementOddsSource") or "",
                    "bookmaker_odds_text": signal.get("bookmakerOddsText") or "",
                    "bookmaker": signal.get("bookmaker") or "",
                    "each_way_terms": signal.get("eachWayTerms") or "",
                    "betfair_status": betfair_status,
                    "market_total_matched": safe_float(runner.get("market_total_matched")),
                    "runner_traded": safe_float(runner.get("runner_traded")),
                    "jockey": runner.get("jockey") or signal.get("jockey"),
                    "trainer": runner.get("trainer") or signal.get("trainer"),
                    "form": runner.get("form") or signal.get("form") or signal.get("formStr"),
                    "days_since_run": safe_int(runner.get("days_since")),
                    "age": safe_int(runner.get("age")),
                    "weight": safe_float(runner.get("weight")),
                    "official_rating": safe_int(runner.get("official_rating")),
                    "stall_draw": runner.get("stall_draw"),
                    "signal_labels": labels,
                    "official_pick": "OFFICIAL_PICK" in labels or "OFFICIAL_RESULT_LOG" in labels,
                    "watchlist": any(label.startswith("WATCHLIST") for label in labels),
                    "signal_score": safe_float(signal.get("signal_score") or signal.get("score")),
                    "tipster_count": tipster_count,
                    "tipster_sources": tipster_sources,
                    "known_result": result,
                    "result_text": signal.get("radarResult") or signal.get("result"),
                    "finishing_position": safe_int(signal.get("position")),
                    "memory_tags": tags,
                    "book_insight": insight_text(name, result, tags, signal),
                    "source": {
                        "runner_cache": "data/today_runners.json",
                        "signal_daily_file": f"data/{target_date}.json",
                        "result_source": (
                            "signal75_known_results_plus_betfair_winners"
                            if use_betfair_results
                            else "signal75_known_results_only"
                        ),
                    },
                }
            )

    counts = Counter()
    for record in records:
        counts["all_runners"] += 1
        counts[f"result_{record['known_result'].lower()}"] += 1
        if record["official_pick"]:
            counts["official_picks"] += 1
        if record["watchlist"]:
            counts["watchlist"] += 1
        for tag in record["memory_tags"]:
            counts[f"tag_{tag.lower()}"] += 1

    return {
        "date": target_date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "runnerCacheDate": cache_date,
        "recordCount": len(records),
        "raceCount": len(races),
        "betfairResultLookup": bool(use_betfair_results),
        "counts": dict(sorted(counts.items())),
        "notes": [
            "Grandad's book memory: records every runner available in the daily runner cache.",
            "Known results are attached only where Signal 75 already has settled pick/watchlist evidence.",
            "Optional Betfair lookup marks WIN-market winners and BSP for memory only; it does not settle each-way places.",
            "This file does not alter scoring, pick generation, settlement, proof, unlock logic, or public JSON structure.",
        ],
        "records": records,
    }


def read_master() -> Dict[str, Dict[str, Any]]:
    existing: Dict[str, Dict[str, Any]] = {}
    if not MASTER_FILE.exists():
        return existing
    with MASTER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = record.get("id")
            if record_id:
                existing[record_id] = record
    return existing


def write_master(records: List[Dict[str, Any]]) -> int:
    existing = read_master()
    for record in records:
        existing[record["id"]] = record
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MASTER_FILE.open("w", encoding="utf-8") as f:
        for record_id in sorted(existing):
            f.write(json.dumps(existing[record_id], ensure_ascii=False, sort_keys=True) + "\n")
    return len(existing)


def build_profiles(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["normalised_name"]].append(record)

    profiles: Dict[str, Any] = {}
    for key, items in grouped.items():
        items = sorted(items, key=lambda r: (r.get("date") or "", r.get("race_time") or ""))
        result_counts = Counter(item.get("known_result") for item in items)
        tag_counts = Counter(tag for item in items for tag in item.get("memory_tags", []))
        courses = Counter(item.get("course") for item in items if item.get("course"))
        trainers = Counter(item.get("trainer") for item in items if item.get("trainer"))
        jockeys = Counter(item.get("jockey") for item in items if item.get("jockey"))
        class_labels = Counter(item.get("race_class_label") for item in items if item.get("race_class_label"))
        class_movements = Counter(item.get("class_movement") for item in items if item.get("class_movement"))
        class_levels = [
            safe_int(item.get("race_class_level"))
            for item in items
            if safe_int(item.get("race_class_level")) is not None
        ]
        prices = [item.get("pre_race_price") for item in items if item.get("pre_race_price") is not None]
        latest = items[-1]
        highest_class_level = min(class_levels) if class_levels else None
        highest_class_label = next(
            (
                item.get("race_class_label")
                for item in sorted(items, key=lambda r: safe_int(r.get("race_class_level")) or 999)
                if safe_int(item.get("race_class_level")) == highest_class_level
            ),
            None,
        )

        profiles[key] = {
            "horse_name": latest.get("horse_name"),
            "normalised_name": key,
            "runs_logged": len(items),
            "known_wins": result_counts.get("WON", 0),
            "known_places": result_counts.get("PLACED", 0),
            "known_losses": result_counts.get("LOST", 0),
            "unknown_results": result_counts.get("UNKNOWN", 0),
            "official_pick_count": sum(1 for item in items if item.get("official_pick")),
            "watchlist_count": sum(1 for item in items if item.get("watchlist")),
            "last_seen": latest.get("date"),
            "last_course": latest.get("course"),
            "last_result": latest.get("known_result"),
            "last_race_class_label": latest.get("race_class_label"),
            "last_race_class_level": latest.get("race_class_level"),
            "highest_race_class_label": highest_class_label,
            "highest_race_class_level": highest_class_level,
            "last_insight": latest.get("book_insight"),
            "common_courses": courses.most_common(5),
            "common_trainers": trainers.most_common(5),
            "common_jockeys": jockeys.most_common(5),
            "common_race_classes": class_labels.most_common(5),
            "class_movement_counts": class_movements.most_common(5),
            "average_recorded_price": round(sum(prices) / len(prices), 2) if prices else None,
            "strongest_tags": tag_counts.most_common(10),
        }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "horseCount": len(profiles),
        "profiles": dict(sorted(profiles.items(), key=lambda item: item[1]["horse_name"] or "")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Signal 75 race memory.")
    parser.add_argument("--date", help="Race date YYYY-MM-DD. Defaults to today_runners.json date.")
    parser.add_argument(
        "--fetch-betfair-results",
        action="store_true",
        help="Add Betfair winner/BSP evidence to the memory file only.",
    )
    args = parser.parse_args()

    runner_cache = load_json(RUNNER_CACHE, {})
    target_date = args.date or runner_cache.get("date") or datetime.now().strftime("%Y-%m-%d")
    cache_date = runner_cache.get("date")
    if cache_date != target_date:
        raise SystemExit(
            f"Runner cache date is {cache_date or 'missing'}, not {target_date}; race memory not built."
        )
    payload = build_records(target_date, use_betfair_results=args.fetch_betfair_results)

    output_path = INTEL_DIR / f"race_memory_{target_date}.json"
    write_json(output_path, payload)
    master_count = write_master(payload["records"])
    profiles = build_profiles(read_master().values())
    write_json(PROFILE_FILE, profiles)

    print(f"Race memory built for {target_date}")
    print(f"  Daily records: {payload['recordCount']}")
    print(f"  Master records: {master_count}")
    print(f"  Horse profiles: {profiles['horseCount']}")
    print(f"  Output: {output_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
