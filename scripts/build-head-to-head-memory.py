#!/usr/bin/env python3
"""Build Signal 75 head-to-head race memory.

Analysis only. This is part of the "Grandad's book" layer: it records when
one horse has beaten another in the same race, using Signal 75 race memory and
manual verified seed facts. It does not change scoring, picks, settlement,
proof maths, app data, unlock logic, or public JSON.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
RACE_MEMORY_MASTER = INTEL_DIR / "race_memory_master.jsonl"
SEED_FILE = INTEL_DIR / "head_to_head_seed.json"
MASTER_FILE = INTEL_DIR / "head_to_head_master.jsonl"
PROFILE_FILE = INTEL_DIR / "head_to_head_profiles.json"


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def display_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


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


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def record_rank(record: Dict[str, Any]) -> Optional[int]:
    result = str(record.get("known_result") or "").upper()
    status = str(record.get("betfair_status") or "").upper()
    pos = safe_int(record.get("finishing_position"))

    if pos and pos > 0:
        return pos
    if result == "WON" or status == "WINNER":
        return 1
    if result == "PLACED" and pos:
        return pos
    return None


def can_compare(left: Dict[str, Any], right: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], str]]:
    left_rank = record_rank(left)
    right_rank = record_rank(right)
    left_status = str(left.get("betfair_status") or "").upper()
    right_status = str(right.get("betfair_status") or "").upper()
    left_result = str(left.get("known_result") or "").upper()
    right_result = str(right.get("known_result") or "").upper()

    if left_rank is not None and right_rank is not None and left_rank != right_rank:
        return (left, right, "known_positions") if left_rank < right_rank else (right, left, "known_positions")
    if left_rank == 1 and right_status in {"LOSER", "REMOVED"}:
        return left, right, "winner_beat_betfair_loser"
    if right_rank == 1 and left_status in {"LOSER", "REMOVED"}:
        return right, left, "winner_beat_betfair_loser"
    if left_result == "PLACED" and right_status == "LOSER":
        return left, right, "placed_beat_betfair_loser"
    if right_result == "PLACED" and left_status == "LOSER":
        return right, left, "placed_beat_betfair_loser"
    return None


def pair_id(date: str, market_id: str, winner_key: str, loser_key: str, source: str) -> str:
    return "|".join([date, market_id or "", winner_key, loser_key, source])


def build_auto_records(race_records: Iterable[Dict[str, Any]], target_date: Optional[str]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for record in race_records:
        date = record.get("date")
        if target_date and date != target_date:
            continue
        market_id = record.get("market_id")
        if not date or not market_id:
            continue
        grouped[(date, market_id)].append(record)

    output: List[Dict[str, Any]] = []
    for (date, market_id), runners in grouped.items():
        runners = [r for r in runners if r.get("horse_name")]
        for i, left in enumerate(runners):
            for right in runners[i + 1 :]:
                comparison = can_compare(left, right)
                if not comparison:
                    continue
                winner, loser, confidence = comparison
                winner_key = norm_name(winner.get("horse_name"))
                loser_key = norm_name(loser.get("horse_name"))
                if not winner_key or not loser_key or winner_key == loser_key:
                    continue
                output.append(
                    {
                        "id": pair_id(date, market_id, winner_key, loser_key, "race_memory"),
                        "date": date,
                        "phase": "logging_only",
                        "scoringImpact": "none",
                        "source": "race_memory",
                        "confidence": confidence,
                        "market_id": market_id,
                        "course": winner.get("course") or loser.get("course"),
                        "race_time": winner.get("race_time") or loser.get("race_time"),
                        "race_name": winner.get("race_name") or loser.get("race_name"),
                        "winner": winner.get("horse_name"),
                        "winner_key": winner_key,
                        "winner_position": record_rank(winner),
                        "winner_result": winner.get("known_result"),
                        "winner_betfair_status": winner.get("betfair_status"),
                        "winner_price": winner.get("pre_race_price"),
                        "winner_signal_score": winner.get("signal_score"),
                        "winner_labels": winner.get("signal_labels", []),
                        "loser": loser.get("horse_name"),
                        "loser_key": loser_key,
                        "loser_position": record_rank(loser),
                        "loser_result": loser.get("known_result"),
                        "loser_betfair_status": loser.get("betfair_status"),
                        "loser_price": loser.get("pre_race_price"),
                        "loser_signal_score": loser.get("signal_score"),
                        "loser_labels": loser.get("signal_labels", []),
                        "evidence_note": f"{winner.get('horse_name')} beat {loser.get('horse_name')} at {winner.get('course') or loser.get('course')}.",
                    }
                )
    return output


def build_seed_records(target_date: Optional[str]) -> List[Dict[str, Any]]:
    payload = load_json(SEED_FILE, {"records": []})
    records: List[Dict[str, Any]] = []
    for item in payload.get("records", []):
        if target_date and item.get("date") != target_date:
            continue
        winner = item.get("winner") or item.get("horse_a")
        loser = item.get("loser") or item.get("horse_b")
        winner_key = norm_name(winner)
        loser_key = norm_name(loser)
        source_name = item.get("source_name") or "manual_seed"
        market_id = item.get("market_id") or f"manual:{item.get('date')}:{norm_name(item.get('race_name'))}"
        records.append(
            {
                "id": pair_id(item.get("date", ""), market_id, winner_key, loser_key, "manual_seed"),
                "date": item.get("date"),
                "phase": "logging_only",
                "scoringImpact": "none",
                "source": "manual_seed",
                "confidence": "verified_historic_result",
                "market_id": market_id,
                "course": item.get("course"),
                "race_time": item.get("race_time"),
                "race_name": item.get("race_name"),
                "winner": winner,
                "winner_key": winner_key,
                "winner_position": safe_int(item.get("horse_a_position")) if norm_name(item.get("horse_a")) == winner_key else safe_int(item.get("horse_b_position")),
                "winner_result": "WON",
                "loser": loser,
                "loser_key": loser_key,
                "loser_position": safe_int(item.get("horse_b_position")) if norm_name(item.get("horse_b")) == loser_key else safe_int(item.get("horse_a_position")),
                "loser_result": "LOST_TO_RIVAL",
                "margin": item.get("margin"),
                "source_name": source_name,
                "source_url": item.get("source_url"),
                "evidence_note": item.get("evidence_note") or f"{winner} beat {loser}.",
            }
        )
    return records


def read_master() -> Dict[str, Dict[str, Any]]:
    return {record["id"]: record for record in read_jsonl(MASTER_FILE) if record.get("id")}


def write_master(records: Iterable[Dict[str, Any]]) -> int:
    existing = read_master()
    for record in records:
        if record.get("id"):
            existing[record["id"]] = record
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MASTER_FILE.open("w", encoding="utf-8") as f:
        for key in sorted(existing):
            f.write(json.dumps(existing[key], ensure_ascii=False, sort_keys=True) + "\n")
    return len(existing)


def profile_key(a: str, b: str) -> str:
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
        return "One recent meeting only; show as a note, not a scoring change."
    return "Old or thin evidence; keep for history only."


def build_profiles(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    pair_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    horse_counts: Dict[str, Counter] = defaultdict(Counter)

    for record in records:
        winner = record.get("winner")
        loser = record.get("loser")
        if not winner or not loser:
            continue
        pair_groups[profile_key(winner, loser)].append(record)
        horse_counts[norm_name(winner)]["rivals_beaten"] += 1
        horse_counts[norm_name(loser)]["beaten_by_rivals"] += 1

    pair_profiles = {}
    for key, items in pair_groups.items():
        items = sorted(items, key=lambda r: (r.get("date") or "", r.get("race_time") or ""))
        names = sorted({items[0].get("winner"), items[0].get("loser")})
        wins_by_horse = Counter(item.get("winner") for item in items)
        latest = items[-1]
        latest_date = parse_iso_date(latest.get("date"))
        recent_cutoff = latest_date - timedelta(days=365) if latest_date else None
        recent_12m = sum(
            1
            for item in items
            if recent_cutoff and (item_date := parse_iso_date(item.get("date"))) and item_date >= recent_cutoff
        )
        leader, leader_wins = wins_by_horse.most_common(1)[0]
        tier = evidence_tier(len(items), leader_wins, recent_12m)
        pair_profiles[key] = {
            "horses": names,
            "meetings_logged": len(items),
            "wins_by_horse": dict(wins_by_horse),
            "dominant_horse": leader,
            "dominant_horse_wins": leader_wins,
            "dominance_rate": round(leader_wins / len(items), 3),
            "recent_12m_meetings": recent_12m,
            "evidence_tier": tier,
            "recommended_use": recommended_use(tier),
            "courses_seen": sorted({item.get("course") for item in items if item.get("course")}),
            "race_names_seen": sorted({item.get("race_name") for item in items if item.get("race_name")}),
            "last_seen": latest.get("date"),
            "last_course": latest.get("course"),
            "last_race": latest.get("race_name"),
            "last_winner": latest.get("winner"),
            "last_loser": latest.get("loser"),
            "last_note": latest.get("evidence_note"),
            "records": [
                {
                    "date": item.get("date"),
                    "course": item.get("course"),
                    "race_name": item.get("race_name"),
                    "winner": item.get("winner"),
                    "loser": item.get("loser"),
                    "confidence": item.get("confidence"),
                    "source": item.get("source"),
                    "margin": item.get("margin"),
                }
                for item in items[-5:]
            ],
        }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "pairCount": len(pair_profiles),
        "horseCount": len(horse_counts),
        "horseSummary": {key: dict(value) for key, value in sorted(horse_counts.items())},
        "pairs": dict(sorted(pair_profiles.items(), key=lambda item: item[0])),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Signal 75 head-to-head memory.")
    parser.add_argument("--date", help="Build a daily output for YYYY-MM-DD. Master/profile still include all records.")
    args = parser.parse_args()

    race_records = read_jsonl(RACE_MEMORY_MASTER)
    auto_records = build_auto_records(race_records, args.date)
    seed_records = build_seed_records(args.date)
    daily_records = auto_records + seed_records

    if args.date:
        output_path = INTEL_DIR / f"head_to_head_{args.date}.json"
        write_json(
            output_path,
            {
                "date": args.date,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "phase": "logging_only",
                "scoringImpact": "none",
                "recordCount": len(daily_records),
                "records": daily_records,
                "notes": [
                    "Head-to-head memory is analysis only.",
                    "Records are built from known race-memory evidence and verified manual seed facts.",
                ],
            },
        )
    else:
        output_path = None

    all_auto = build_auto_records(race_records, None)
    all_seed = build_seed_records(None)
    master_count = write_master(all_auto + all_seed)
    profiles = build_profiles(read_master().values())
    write_json(PROFILE_FILE, profiles)

    print("Head-to-head memory built")
    if output_path:
        print(f"  Daily records: {len(daily_records)}")
        print(f"  Output: {output_path.relative_to(REPO_ROOT)}")
    print(f"  Master records: {master_count}")
    print(f"  Pair profiles: {profiles['pairCount']}")


if __name__ == "__main__":
    main()
