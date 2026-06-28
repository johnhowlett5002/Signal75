#!/usr/bin/env python3
"""Build richer post-race result notes for Signal 75 learning.

This is analysis/storage only. It stores full finishing order, beaten distances,
race comments, jockey claims and "beat a high-score horse" flags when verified
result notes are available. It never changes picks, scoring, proof, settlement,
unlock logic, or public JSON contracts.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
SEED_FILE = INTEL_DIR / "result_notes_seed.json"
MASTER_FILE = INTEL_DIR / "race_result_notes_master.jsonl"
PROFILE_FILE = INTEL_DIR / "race_result_note_profiles.json"


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def normalise(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


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


def rounded(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 2)


def weight_to_lbs(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    match = re.match(r"^(\d+)-(\d+)$", text)
    if match:
        return int(match.group(1)) * 14 + int(match.group(2))
    return safe_int(value)


def finish_impression(record: Dict[str, Any]) -> str:
    position = safe_int(record.get("position"))
    result = str(record.get("result") or "").upper()
    comment = str(record.get("race_comment") or "").lower()
    winning_margin = safe_float(record.get("winning_margin_lengths"))
    beaten_distance = safe_float(record.get("distance_from_winner_lengths"))

    if result == "PU" or "pulled up" in comment:
        return "pulled up"
    if position == 1:
        if record.get("winner_won_decisively") or (winning_margin is not None and winning_margin >= 3):
            return "won decisively"
        if winning_margin is not None and winning_margin <= 0.5:
            return "narrow winner"
        return "winner"
    if beaten_distance is not None and beaten_distance <= 1:
        return "close finish"
    if beaten_distance is not None and beaten_distance >= 20:
        return "heavily beaten"
    if beaten_distance is not None and beaten_distance >= 10:
        return "well beaten"
    if "no response" in comment or "dropped away" in comment or "weakened" in comment:
        return "weakened/no response"
    return "finished"


def read_master() -> Dict[str, Dict[str, Any]]:
    if not MASTER_FILE.exists():
        return {}
    records: Dict[str, Dict[str, Any]] = {}
    with MASTER_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("id"):
                records[row["id"]] = row
    return records


def write_master(records: List[Dict[str, Any]]) -> int:
    existing = read_master()
    for record in records:
        existing[record["id"]] = record
    MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
    with MASTER_FILE.open("w", encoding="utf-8") as f:
        for record_id in sorted(existing):
            f.write(json.dumps(existing[record_id], ensure_ascii=False, sort_keys=True) + "\n")
    return len(existing)


def memory_index(date: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    payload = load_json(INTEL_DIR / f"race_memory_{date}.json", {})
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in payload.get("records", []) if isinstance(payload, dict) else []:
        idx[(str(row.get("market_id") or ""), normalise(row.get("horse_name")))] = row
    return idx


def note_flags(row: Dict[str, Any], race: Dict[str, Any], high_signal_behind: List[str]) -> List[str]:
    flags: List[str] = []
    comment = str(row.get("race_comment") or "").lower()
    winning_margin = safe_float(row.get("winning_margin_lengths"))
    beaten_distance = safe_float(row.get("distance_from_winner_lengths"))
    if row.get("position") == 1:
        flags.append("WINNER")
    if row.get("jockey_claim_lbs"):
        flags.append("JOCKEY_CLAIM")
    if race.get("winner_won_decisively") and row.get("position") == 1:
        flags.append("WON_DECISIVELY")
    if row.get("position") == 1 and winning_margin is not None and winning_margin >= 3:
        flags.append("WON_CLEAR")
    if row.get("position") == 1 and winning_margin is not None and winning_margin <= 0.5:
        flags.append("NARROW_WIN")
    if row.get("position") != 1 and beaten_distance is not None and beaten_distance <= 1:
        flags.append("CLOSE_UP")
    if row.get("position") != 1 and beaten_distance is not None and beaten_distance >= 10:
        flags.append("WELL_BEATEN")
    if row.get("position") != 1 and beaten_distance is not None and beaten_distance >= 20:
        flags.append("HEAVILY_BEATEN")
    if "no response" in comment or "dropped away" in comment or "weakened" in comment:
        flags.append("WEAKENED_OR_NO_RESPONSE")
    if "pulled up" in comment or str(row.get("result") or "").upper() == "PU":
        flags.append("PULLED_UP")
    if high_signal_behind:
        flags.append("BEAT_HIGH_SIGNAL_HORSE")
    return flags


def build_records(date: str) -> Dict[str, Any]:
    seed = load_json(SEED_FILE, {})
    memory = memory_index(date)
    records: List[Dict[str, Any]] = []

    for race in seed.get("races", []) if isinstance(seed, dict) else []:
        if race.get("date") != date:
            continue
        market_id = str(race.get("market_id") or "")
        runners = race.get("runners") or []
        high_signal = {}
        for runner in runners:
            mem = memory.get((market_id, normalise(runner.get("horse_name"))), {})
            score = safe_float(mem.get("signal_score"))
            if score is not None and score >= 90:
                high_signal[normalise(runner.get("horse_name"))] = runner.get("horse_name")

        positioned = [r for r in runners if safe_int(r.get("position")) is not None]
        positioned.sort(key=lambda r: safe_int(r.get("position")) or 999)
        winner_margin = None
        if len(positioned) > 1 and safe_int(positioned[0].get("position")) == 1:
            winner_margin = safe_float(positioned[1].get("cumulative_beaten_lengths"))
        winner_margin = safe_float(race.get("winning_margin_lengths")) or winner_margin

        for runner in runners:
            horse = clean_text(runner.get("horse_name"))
            horse_key = normalise(horse)
            position = safe_int(runner.get("position"))
            beaten_by = []
            high_signal_behind = []
            if position is not None:
                for other in positioned:
                    other_pos = safe_int(other.get("position"))
                    if other_pos is not None and other_pos < position:
                        beaten_by.append(clean_text(other.get("horse_name")))
                    if other_pos is not None and other_pos > position:
                        other_key = normalise(other.get("horse_name"))
                        if other_key in high_signal:
                            high_signal_behind.append(clean_text(other.get("horse_name")))

            mem = memory.get((market_id, horse_key), {})
            record = {
                "id": f"{date}|{market_id}|{horse_key}",
                "date": date,
                "phase": "learning_only",
                "scoringImpact": "none",
                "course": race.get("course"),
                "race_time": race.get("race_time"),
                "runner_cache_time": race.get("runner_cache_time"),
                "market_id": market_id,
                "race_name": race.get("race_name"),
                "race_type": race.get("race_type"),
                "distance": race.get("distance"),
                "going": race.get("going"),
                "source": race.get("source"),
                "horse_name": horse,
                "horse_key": horse_key,
                "position": position,
                "result": runner.get("result") or ("WON" if position == 1 else "PLACED" if position and position <= 3 else "LOST" if position else "UNKNOWN"),
                "distance_from_previous_lengths": rounded(safe_float(runner.get("distance_from_previous"))),
                "cumulative_beaten_lengths": rounded(safe_float(runner.get("cumulative_beaten_lengths"))),
                "distance_from_winner_lengths": rounded(safe_float(runner.get("cumulative_beaten_lengths")) if position != 1 else 0.0 if position == 1 else None),
                "beaten_margin_lengths": rounded(safe_float(runner.get("cumulative_beaten_lengths")) if position != 1 else None),
                "winning_margin_lengths": rounded(winner_margin if position == 1 else None),
                "sp": runner.get("sp"),
                "jockey": runner.get("jockey"),
                "jockey_claim_lbs": safe_int(runner.get("jockey_claim_lbs")) or 0,
                "trainer": runner.get("trainer"),
                "age": safe_int(runner.get("age")),
                "weight_text": runner.get("weight_text"),
                "carried_weight_lbs": weight_to_lbs(runner.get("weight_text")),
                "official_rating": safe_int(runner.get("official_rating")),
                "race_comment": clean_text(runner.get("race_comment")),
                "winner_impression": race.get("winner_impression") if position == 1 else "",
                "winner_won_decisively": bool(race.get("winner_won_decisively") and position == 1),
                "beaten_by": beaten_by,
                "beat_high_signal_horses": high_signal_behind,
                "signal_score": safe_float(mem.get("signal_score")),
                "watchlist": bool(mem.get("watchlist")),
                "official_pick": bool(mem.get("official_pick")),
                "pre_race_price": safe_float(mem.get("pre_race_price")),
            }
            record["result_note_flags"] = note_flags(record, race, high_signal_behind)
            record["finish_impression"] = finish_impression(record)
            if position == 1 and record.get("winning_margin_lengths") is not None:
                record["distance_summary"] = f"Won by {record['winning_margin_lengths']} lengths"
            elif record.get("distance_from_winner_lengths") is not None:
                record["distance_summary"] = f"Beaten {record['distance_from_winner_lengths']} lengths by winner"
            elif record.get("result") == "PU":
                record["distance_summary"] = "Pulled up"
            else:
                record["distance_summary"] = ""
            records.append(record)

    flags = Counter(flag for record in records for flag in record.get("result_note_flags", []))
    records_with_margin = sum(1 for record in records if record.get("winning_margin_lengths") is not None or record.get("distance_from_winner_lengths") is not None)
    return {
        "date": date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "learning_only",
        "scoringImpact": "none",
        "recordCount": len(records),
        "raceCount": len({r["market_id"] for r in records}),
        "marginCoverage": {
            "records_with_margin": records_with_margin,
            "winners_with_margin": sum(1 for record in records if record.get("winning_margin_lengths") is not None),
            "close_finishes": flags.get("CLOSE_UP", 0) + flags.get("NARROW_WIN", 0),
            "decisive_winners": sum(
                1
                for record in records
                if "WON_DECISIVELY" in record.get("result_note_flags", [])
                or "WON_CLEAR" in record.get("result_note_flags", [])
            ),
            "well_beaten": flags.get("WELL_BEATEN", 0),
            "heavily_beaten": flags.get("HEAVILY_BEATEN", 0),
        },
        "notes": [
            "Richer post-race notes are learning only.",
            "They store finishing order, beaten distances, comments, jockey claims, weights and high-score-horse context when verified notes are available.",
            "They do not change picks, scoring, proof, settlement, unlock logic, or public JSON contracts.",
        ],
        "records": records,
    }


def build_profiles(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["horse_key"]].append(row)

    profiles: Dict[str, Any] = {}
    for key, items in grouped.items():
        items = sorted(items, key=lambda r: (r.get("date") or "", r.get("race_time") or ""))
        latest = items[-1]
        flags = Counter(flag for item in items for flag in item.get("result_note_flags", []))
        profiles[key] = {
            "horse_name": latest.get("horse_name"),
            "runs_with_result_notes": len(items),
            "last_seen": latest.get("date"),
            "last_position": latest.get("position"),
            "last_result": latest.get("result"),
            "last_comment": latest.get("race_comment"),
            "last_cumulative_beaten_lengths": latest.get("cumulative_beaten_lengths"),
            "last_distance_from_winner_lengths": latest.get("distance_from_winner_lengths"),
            "last_winning_margin_lengths": latest.get("winning_margin_lengths"),
            "last_finish_impression": latest.get("finish_impression"),
            "best_winning_margin_lengths": max(
                (safe_float(item.get("winning_margin_lengths")) or 0 for item in items),
                default=0,
            ),
            "worst_distance_from_winner_lengths": max(
                (safe_float(item.get("distance_from_winner_lengths")) or 0 for item in items),
                default=0,
            ),
            "times_beat_high_signal_horse": sum(1 for item in items if item.get("beat_high_signal_horses")),
            "times_no_response_or_weakened": flags.get("WEAKENED_OR_NO_RESPONSE", 0),
            "times_won_decisively": flags.get("WON_DECISIVELY", 0),
            "times_won_clear": flags.get("WON_CLEAR", 0),
            "times_close_up": flags.get("CLOSE_UP", 0),
            "times_well_beaten": flags.get("WELL_BEATEN", 0),
            "times_heavily_beaten": flags.get("HEAVILY_BEATEN", 0),
            "common_flags": flags.most_common(8),
        }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "learning_only",
        "scoringImpact": "none",
        "horseCount": len(profiles),
        "profiles": dict(sorted(profiles.items(), key=lambda item: item[1]["horse_name"] or "")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build richer Signal 75 post-race result notes.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    payload = build_records(args.date)
    output = INTEL_DIR / f"race_result_notes_{args.date}.json"
    write_json(output, payload)
    master_count = write_master(payload["records"])
    profiles = build_profiles(read_master().values())
    write_json(PROFILE_FILE, profiles)

    print(f"Race result notes built for {args.date}")
    print(f"  Daily records: {payload['recordCount']}")
    print(f"  Master records: {master_count}")
    print(f"  Profiles: {profiles['horseCount']}")
    print(f"  Output: {output.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
