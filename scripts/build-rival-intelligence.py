#!/usr/bin/env python3
"""Build historic rival intelligence for Signal 75.

Analysis only. Reads the large Betfair engine CSV and finds previous meetings
between horses entered in the same Signal 75 race. This is the deeper
"Grandad's book" layer: has this horse already beaten today's rival before?

It does not change scoring, pick generation, settlement, proof maths, app data,
unlock logic, or public JSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
RACE_MEMORY_TEMPLATE = INTEL_DIR / "race_memory_{}.json"
RUNNERS_CACHE = DATA_DIR / "today_runners.json"
ENGINE_CSV_CANDIDATES = [
    Path("/Users/johnhowlett/Signal75-Work/Signal75-Engine/betfair_uk_races_master.csv"),
    Path("/Users/johnhowlett/Desktop/Signal75-Engine/betfair_uk_races_master.csv"),
    REPO_ROOT / "engine" / "betfair_uk_races_full_v2.csv",
]
MASTER_FILE = INTEL_DIR / "historic_rival_master.jsonl"
PROFILE_FILE = INTEL_DIR / "historic_rival_profiles.json"


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def display_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


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


def parse_date(value: Any) -> Optional[str]:
    text = str(value or "")
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else None


def choose_engine_csv() -> Path:
    for path in ENGINE_CSV_CANDIDATES:
        if path.exists():
            return path
    raise SystemExit("No Betfair engine CSV found for historic rival intelligence.")


def load_target_races(target_date: str) -> List[Dict[str, Any]]:
    race_memory = load_json(RACE_MEMORY_TEMPLATE.with_name(f"race_memory_{target_date}.json"), {})
    if race_memory.get("records"):
        grouped: Dict[str, Dict[str, Any]] = {}
        for record in race_memory.get("records", []):
            market_id = record.get("market_id")
            if not market_id:
                continue
            race = grouped.setdefault(
                market_id,
                {
                    "date": target_date,
                    "market_id": market_id,
                    "course": record.get("course"),
                    "race_time": record.get("race_time"),
                    "race_name": record.get("race_name"),
                    "runners": [],
                },
            )
            race["runners"].append(
                {
                    "name": record.get("horse_name"),
                    "normalised_name": norm_name(record.get("horse_name")),
                    "pre_race_price": record.get("pre_race_price"),
                    "signal_score": record.get("signal_score"),
                    "official_pick": record.get("official_pick"),
                    "watchlist": record.get("watchlist"),
                }
            )
        return list(grouped.values())

    cache = load_json(RUNNERS_CACHE, {})
    if cache.get("date") != target_date:
        raise SystemExit(f"No race memory for {target_date}, and today_runners.json is {cache.get('date')}.")
    races = []
    for race in cache.get("races", []):
        races.append(
            {
                "date": target_date,
                "market_id": race.get("market_id"),
                "course": re.sub(r"\s+\d+(st|nd|rd|th)?\s+\w+$", "", display_name(race.get("venue")), flags=re.I),
                "race_time": str(race.get("race_time") or "")[11:16] if race.get("race_time") else None,
                "race_name": race.get("race_name"),
                "runners": [
                    {
                        "name": runner.get("name"),
                        "normalised_name": norm_name(runner.get("name")),
                        "pre_race_price": runner.get("best_back"),
                    }
                    for runner in race.get("runners", [])
                ],
            }
        )
    return races


def scan_historic_rows(engine_csv: Path, target_names: Set[str], target_date: str) -> Dict[str, List[Dict[str, Any]]]:
    by_market: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    with engine_csv.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("market_type") != "WIN":
                continue
            horse_key = norm_name(row.get("horse_name"))
            if horse_key not in target_names:
                continue
            race_date = parse_date(row.get("race_time"))
            if not race_date or race_date >= target_date:
                continue
            market_id = row.get("market_id")
            if not market_id:
                continue
            by_market[market_id].append(
                {
                    "horse_name": display_name(row.get("horse_name")),
                    "normalised_name": horse_key,
                    "date": race_date,
                    "market_id": market_id,
                    "course": row.get("venue"),
                    "race_time": row.get("race_time"),
                    "race_name": row.get("race_name"),
                    "race_type": row.get("race_type"),
                    "race_subtype": row.get("race_subtype"),
                    "distance_furlongs": safe_float(row.get("distance_furlongs")),
                    "bsp": safe_float(row.get("bsp")),
                    "status": row.get("status"),
                    "sort_priority": safe_int(row.get("sort_priority")),
                    "runner_count": safe_int(row.get("runner_count")),
                }
            )
    return {market: rows for market, rows in by_market.items() if len({r["normalised_name"] for r in rows}) >= 2}


def compare_rows(left: Dict[str, Any], right: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    # In historic Betfair market files, WINNER/LOSER status is reliable.
    # Loser sort_priority is not safe enough to treat as full finishing order.
    left_status = str(left.get("status") or "").upper()
    right_status = str(right.get("status") or "").upper()
    if left_status == "WINNER" and right_status != "WINNER":
        return left, right
    if right_status == "WINNER" and left_status != "WINNER":
        return right, left
    return None


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted([norm_name(a), norm_name(b)]))


def parse_iso_date(value: Any) -> Optional[datetime]:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def evidence_tier(meetings: int, leader_wins: int, recent_12m: int) -> str:
    if meetings >= 4 and leader_wins / meetings >= 0.75 and recent_12m >= 2:
        return "strong_pattern"
    if meetings >= 2 and leader_wins / meetings >= 0.67:
        return "useful_pattern"
    if recent_12m >= 1:
        return "minor_note"
    return "archive_only"


def recommended_use(tier: str) -> str:
    if tier == "strong_pattern":
        return "Real warning/confidence candidate for post-trial overlay review."
    if tier == "useful_pattern":
        return "Useful context; review with Signal score, odds, race type, and tipster evidence."
    if tier == "minor_note":
        return "One recent historic meeting only; show as a note, not a scoring change."
    return "Old or thin evidence; keep for history only."


def build_rival_records(target_date: str, races: List[Dict[str, Any]], historic_markets: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    target_pair_context: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for race in races:
        runners = [r for r in race.get("runners", []) if r.get("normalised_name")]
        for i, left in enumerate(runners):
            for right in runners[i + 1 :]:
                target_pair_context[pair_key(left["name"], right["name"])].append(
                    {
                        "target_date": target_date,
                        "target_market_id": race.get("market_id"),
                        "target_course": race.get("course"),
                        "target_race_time": race.get("race_time"),
                        "target_race_name": race.get("race_name"),
                        "horse_a": left.get("name"),
                        "horse_b": right.get("name"),
                        "horse_a_signal_score": left.get("signal_score"),
                        "horse_b_signal_score": right.get("signal_score"),
                        "horse_a_official_pick": left.get("official_pick"),
                        "horse_b_official_pick": right.get("official_pick"),
                    }
                )

    records: List[Dict[str, Any]] = []
    seen = set()
    for market_id, rows in historic_markets.items():
        unique_rows = {row["normalised_name"]: row for row in rows}.values()
        unique_rows = list(unique_rows)
        for i, left in enumerate(unique_rows):
            for right in unique_rows[i + 1 :]:
                key = pair_key(left["horse_name"], right["horse_name"])
                contexts = target_pair_context.get(key)
                if not contexts:
                    continue
                comparison = compare_rows(left, right)
                if not comparison:
                    continue
                winner, loser = comparison
                for context in contexts:
                    record_id = "|".join(
                        [
                            target_date,
                            context.get("target_market_id") or "",
                            market_id,
                            norm_name(winner.get("horse_name")),
                            norm_name(loser.get("horse_name")),
                        ]
                    )
                    if record_id in seen:
                        continue
                    seen.add(record_id)
                    records.append(
                        {
                            "id": record_id,
                            "target_date": target_date,
                            "phase": "logging_only",
                            "scoringImpact": "none",
                            "source": "historic_betfair_engine_csv",
                            "target_market_id": context.get("target_market_id"),
                            "target_course": context.get("target_course"),
                            "target_race_time": context.get("target_race_time"),
                            "target_race_name": context.get("target_race_name"),
                            "horse_a": context.get("horse_a"),
                            "horse_b": context.get("horse_b"),
                            "historic_date": winner.get("date"),
                            "historic_market_id": market_id,
                            "historic_course": winner.get("course") or loser.get("course"),
                            "historic_race_time": winner.get("race_time") or loser.get("race_time"),
                            "historic_race_name": winner.get("race_name") or loser.get("race_name"),
                            "historic_race_type": winner.get("race_type") or loser.get("race_type"),
                            "historic_race_subtype": winner.get("race_subtype") or loser.get("race_subtype"),
                            "historic_distance_furlongs": winner.get("distance_furlongs") or loser.get("distance_furlongs"),
                            "winner": winner.get("horse_name"),
                            "winner_key": norm_name(winner.get("horse_name")),
                            "winner_position": 1,
                            "winner_status": winner.get("status"),
                            "winner_bsp": winner.get("bsp"),
                            "loser": loser.get("horse_name"),
                            "loser_key": norm_name(loser.get("horse_name")),
                            "loser_position": None,
                            "loser_status": loser.get("status"),
                            "loser_bsp": loser.get("bsp"),
                            "evidence_note": (
                                f"{winner.get('horse_name')} previously beat {loser.get('horse_name')} "
                                f"at {winner.get('course') or loser.get('course')} on {winner.get('date')}."
                            ),
                        }
                    )
    return records


def read_master() -> Dict[str, Dict[str, Any]]:
    records = {}
    if not MASTER_FILE.exists():
        return records
    with MASTER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("id"):
                records[record["id"]] = record
    return records


def write_master(records: Iterable[Dict[str, Any]]) -> int:
    existing = read_master()
    for record in records:
        existing[record["id"]] = record
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MASTER_FILE.open("w", encoding="utf-8") as f:
        for key in sorted(existing):
            f.write(json.dumps(existing[key], ensure_ascii=False, sort_keys=True) + "\n")
    return len(existing)


def build_profiles(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    pairs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        pairs[pair_key(record.get("winner"), record.get("loser"))].append(record)

    profiles = {}
    for key, items in pairs.items():
        items = sorted(items, key=lambda r: (r.get("historic_date") or "", r.get("target_date") or ""))
        wins = Counter(item.get("winner") for item in items)
        latest = items[-1]
        latest_target_date = parse_iso_date(latest.get("target_date"))
        recent_cutoff = latest_target_date - timedelta(days=365) if latest_target_date else None
        recent_12m = sum(
            1
            for item in items
            if recent_cutoff and (item_date := parse_iso_date(item.get("historic_date"))) and item_date >= recent_cutoff
        )
        leader, leader_wins = wins.most_common(1)[0]
        tier = evidence_tier(len(items), leader_wins, recent_12m)
        profiles[key] = {
            "horses": sorted({latest.get("winner"), latest.get("loser")}),
            "historic_meetings_found": len(items),
            "wins_by_horse": dict(wins),
            "dominant_horse": leader,
            "dominant_horse_wins": leader_wins,
            "dominance_rate": round(leader_wins / len(items), 3),
            "recent_12m_historic_meetings": recent_12m,
            "evidence_tier": tier,
            "recommended_use": recommended_use(tier),
            "historic_courses_seen": sorted({item.get("historic_course") for item in items if item.get("historic_course")}),
            "historic_race_types_seen": sorted({item.get("historic_race_type") for item in items if item.get("historic_race_type")}),
            "historic_race_subtypes_seen": sorted({item.get("historic_race_subtype") for item in items if item.get("historic_race_subtype")}),
            "historic_distances_furlongs_seen": sorted(
                {item.get("historic_distance_furlongs") for item in items if item.get("historic_distance_furlongs") is not None}
            ),
            "latest_target_date": latest.get("target_date"),
            "latest_target_race": latest.get("target_race_name"),
            "latest_historic_date": latest.get("historic_date"),
            "latest_historic_course": latest.get("historic_course"),
            "latest_historic_race_type": latest.get("historic_race_type"),
            "latest_historic_distance_furlongs": latest.get("historic_distance_furlongs"),
            "latest_historic_race": latest.get("historic_race_name"),
            "latest_note": latest.get("evidence_note"),
            "records": [
                {
                    "target_date": item.get("target_date"),
                    "target_race": item.get("target_race_name"),
                    "historic_date": item.get("historic_date"),
                    "historic_course": item.get("historic_course"),
                    "historic_race": item.get("historic_race_name"),
                    "historic_race_type": item.get("historic_race_type"),
                    "historic_race_subtype": item.get("historic_race_subtype"),
                    "historic_distance_furlongs": item.get("historic_distance_furlongs"),
                    "winner": item.get("winner"),
                    "loser": item.get("loser"),
                    "winner_position": item.get("winner_position"),
                    "loser_position": item.get("loser_position"),
                }
                for item in items[-10:]
            ],
        }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "pairCount": len(profiles),
        "pairs": dict(sorted(profiles.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historic rival intelligence.")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD.")
    parser.add_argument("--engine-csv", help="Optional Betfair engine CSV path.")
    args = parser.parse_args()

    engine_csv = Path(args.engine_csv) if args.engine_csv else choose_engine_csv()
    races = load_target_races(args.date)
    target_names = {runner["normalised_name"] for race in races for runner in race.get("runners", []) if runner.get("normalised_name")}
    historic_markets = scan_historic_rows(engine_csv, target_names, args.date)
    records = build_rival_records(args.date, races, historic_markets)

    output = {
        "date": args.date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "engineCsv": str(engine_csv),
        "targetRaceCount": len(races),
        "targetHorseCount": len(target_names),
        "historicMarketMatches": len(historic_markets),
        "recordCount": len(records),
        "notes": [
            "Historic rival intelligence is analysis only.",
            "It looks for previous meetings between horses entered in the same target race.",
            "It does not alter scoring, picks, proof, settlement, public display, or JSON contracts.",
        ],
        "records": records,
    }

    out_path = INTEL_DIR / f"historic_rivals_{args.date}.json"
    write_json(out_path, output)
    master_count = write_master(records)
    profiles = build_profiles(read_master().values())
    write_json(PROFILE_FILE, profiles)

    print("Historic rival intelligence built")
    print(f"  Target races: {len(races)}")
    print(f"  Target horses: {len(target_names)}")
    print(f"  Historic market matches: {len(historic_markets)}")
    print(f"  Daily records: {len(records)}")
    print(f"  Master records: {master_count}")
    print(f"  Pair profiles: {profiles['pairCount']}")
    print(f"  Output: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
