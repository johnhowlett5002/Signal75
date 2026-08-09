#!/usr/bin/env python3
"""Build Signal 75 field graph intelligence.

This is the next stage of the "Grandad's book" layer. It does not try to
predict winners on its own. It asks a more useful question:

    Which horses have already proved they can beat today's actual rivals,
    directly or through a short chain of shared opponents?

The output is analysis/memory only unless another guarded layer chooses to read
it. It does not change proof, settlement, results maths, unlock logic or public
JSON structures.
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
TODAY_RUNNERS = DATA_DIR / "today_runners.json"
RACE_MEMORY_MASTER = INTEL_DIR / "race_memory_master.jsonl"
HEAD_TO_HEAD_MASTER = INTEL_DIR / "head_to_head_master.jsonl"
HISTORIC_RIVAL_MASTER = INTEL_DIR / "historic_rival_master.jsonl"
FIELD_GRAPH_PROFILE = INTEL_DIR / "field_graph_profiles.json"


def norm_name(value: Any) -> str:
    text = re.sub(r"^\s*\d+\.\s*", "", str(value or ""))
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def clean_name(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip())


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        if isinstance(value, str):
            text = value.strip().lower().replace("lengths", "").replace("length", "")
            if text.endswith("l"):
                text = text[:-1]
            fractions = {"½": 0.5, "¼": 0.25, "¾": 0.75, "hd": 0.2, "nk": 0.3, "nse": 0.1}
            if text in fractions:
                return fractions[text]
            if "/" in text:
                left, right = text.split("/", 1)
                return float(left) / float(right)
            return float(text)
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_date(value: Any) -> Optional[datetime]:
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(0), "%Y-%m-%d")
    except ValueError:
        return None


def days_since(value: Any, as_of: str) -> Optional[int]:
    left = parse_date(value)
    right = parse_date(as_of)
    if not left or not right:
        return None
    return max(0, (right - left).days)


def is_before_target_date(value: Any, target_date: str) -> bool:
    """True only when an evidence row is safely before the race day."""
    left = parse_date(value)
    right = parse_date(target_date)
    if not left or not right:
        return False
    return left.date() < right.date()


def race_family(value: Any) -> str:
    text = str(value or "").lower()
    if "chase" in text or "chs" in text:
        return "chase"
    if "hurdle" in text or "hrd" in text:
        return "hurdle"
    if "bumper" in text or "nh flat" in text:
        return "bumper"
    return "flat"


def parse_distance_furlongs(record: Dict[str, Any]) -> Optional[float]:
    for key in ("distance_furlongs", "historic_distance_furlongs", "target_distance_furlongs"):
        value = record.get(key)
        if value not in ("", None):
            return safe_float(value)
    text = str(record.get("race_name") or record.get("historic_race_name") or record.get("target_race_name") or "")
    match = re.search(r"(?:(\d+)m)?\s*(\d+(?:\.\d+)?)f", text.lower())
    if match:
        miles = safe_float(match.group(1), 0.0)
        furlongs = safe_float(match.group(2), 0.0)
        return miles * 8 + furlongs
    match = re.search(r"(\d+)m", text.lower())
    if match:
        return safe_float(match.group(1)) * 8
    return None


def distance_bucket(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    if value <= 6:
        return "sprint"
    if value <= 9:
        return "mile"
    if value <= 14:
        return "middle"
    if value <= 19:
        return "staying"
    return "extended"


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


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def runner_identity(record: Dict[str, Any]) -> Tuple[str, str]:
    name = clean_name(record.get("horse_name") or record.get("name") or record.get("runnerName"))
    return name, norm_name(name)


def load_today_fields(date: str) -> Dict[str, Dict[str, Any]]:
    """Return current race fields keyed by market_id.

    The morning runner cache is preferred. If it is empty or unavailable, use
    the race memory file for the requested date so backfills still work.
    """
    fields: Dict[str, Dict[str, Any]] = {}
    payload = load_json(TODAY_RUNNERS, {})
    if payload.get("date") == date:
        for race in payload.get("races") or []:
            market_id = str(race.get("market_id") or race.get("marketId") or "")
            if not market_id:
                continue
            runners = []
            for raw in race.get("runners") or []:
                name, key = runner_identity(raw)
                if not key:
                    continue
                runners.append({**raw, "horse_name": name, "horse_key": key})
            if runners:
                fields[market_id] = {
                    "market_id": market_id,
                    "course": race.get("venue") or race.get("course"),
                    "race_time": race.get("race_time") or race.get("time"),
                    "race_name": race.get("race_name") or race.get("name"),
                    "runners": runners,
                    "source": "today_runners",
                }
    if fields:
        return fields

    memory = load_json(INTEL_DIR / f"race_memory_{date}.json", {})
    grouped: Dict[str, Dict[str, Any]] = {}
    for raw in memory.get("records") or []:
        market_id = str(raw.get("market_id") or "")
        name, key = runner_identity(raw)
        if not market_id or not key:
            continue
        race = grouped.setdefault(
            market_id,
            {
                "market_id": market_id,
                "course": raw.get("course"),
                "race_time": raw.get("race_time"),
                "race_name": raw.get("race_name"),
                "runners": [],
                "source": "race_memory",
            },
        )
        race["runners"].append({**raw, "horse_name": name, "horse_key": key})
    return grouped


def build_race_attribute_index() -> Dict[Tuple[str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in iter_jsonl(RACE_MEMORY_MASTER):
        key = norm_name(row.get("horse_name"))
        market_id = str(row.get("market_id") or "")
        if not key or not market_id:
            continue
        index[(market_id, key)] = row
    return index


def condition_matches(edge: Dict[str, Any], current: Dict[str, Any], race: Dict[str, Any]) -> List[str]:
    matches = []
    current_course = clean_name(race.get("course"))
    edge_course = clean_name(edge.get("course") or edge.get("historic_course"))
    if current_course and edge_course and current_course.lower() == edge_course.lower():
        matches.append("same course")

    current_family = race_family(race.get("race_name") or current.get("race_name"))
    edge_family = race_family(edge.get("race_name") or edge.get("historic_race_name") or edge.get("historic_race_type"))
    if current_family == edge_family:
        matches.append("same race type")

    current_dist = parse_distance_furlongs({**current, **race})
    edge_dist = parse_distance_furlongs(edge)
    if current_dist is not None and edge_dist is not None:
        if abs(current_dist - edge_dist) <= 1:
            matches.append("similar trip")
        elif distance_bucket(current_dist) == distance_bucket(edge_dist):
            matches.append("same trip band")

    current_jockey = clean_name(current.get("jockey"))
    edge_jockey = clean_name(edge.get("winner_jockey"))
    if current_jockey and edge_jockey and current_jockey.lower() == edge_jockey.lower():
        matches.append("same jockey")

    current_trainer = clean_name(current.get("trainer"))
    edge_trainer = clean_name(edge.get("winner_trainer"))
    if current_trainer and edge_trainer and current_trainer.lower() == edge_trainer.lower():
        matches.append("same trainer")

    current_weight = safe_float(current.get("weight"), 0.0)
    edge_weight = safe_float(edge.get("winner_weight"), 0.0)
    if current_weight and edge_weight and abs(current_weight - edge_weight) <= 4:
        matches.append("similar weight")

    return matches


def build_edges(as_of: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
    race_index = build_race_attribute_index()
    edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
    seen_direct_meetings = set()
    seen_historic_meetings = set()

    def meeting_key(winner: str, loser: str, row: Dict[str, Any], date_key: str, course_key: str) -> Tuple[str, str, str, str, str]:
        return (
            norm_name(winner),
            norm_name(loser),
            str(row.get(date_key) or "").strip(),
            norm_name(row.get(course_key) or ""),
            str(row.get("race_time") or row.get("time") or "").strip(),
        )

    def historic_meeting_key(winner: str, loser: str, row: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
        return (
            norm_name(winner),
            norm_name(loser),
            str(row.get("historic_date") or "").strip(),
            norm_name(row.get("historic_course") or ""),
            norm_name(row.get("historic_race") or ""),
        )

    def edge_for(winner: str, loser: str) -> Dict[str, Any]:
        winner_key = norm_name(winner)
        loser_key = norm_name(loser)
        edge = edges.setdefault(
            (winner_key, loser_key),
            {
                "winner": clean_name(winner),
                "winner_key": winner_key,
                "loser": clean_name(loser),
                "loser_key": loser_key,
                "meetings": 0,
                "direct_records": [],
                "historic_records": [],
                "max_margin": 0.0,
                "clear_margin_count": 0,
                "recent_180d": 0,
                "recent_365d": 0,
                "beat_high_signal_count": 0,
                "latest_date": "",
                "sources": Counter(),
            },
        )
        return edge

    for row in iter_jsonl(HEAD_TO_HEAD_MASTER):
        if not is_before_target_date(row.get("date"), as_of):
            continue
        winner = clean_name(row.get("winner"))
        loser = clean_name(row.get("loser"))
        if not norm_name(winner) or not norm_name(loser):
            continue
        key = meeting_key(winner, loser, row, "date", "course")
        if key in seen_direct_meetings:
            continue
        seen_direct_meetings.add(key)
        edge = edge_for(winner, loser)
        market_id = str(row.get("market_id") or "")
        winner_attrs = race_index.get((market_id, edge["winner_key"]), {})
        edge_row = {**row}
        if winner_attrs:
            edge_row.update(
                {
                    "winner_jockey": winner_attrs.get("jockey"),
                    "winner_trainer": winner_attrs.get("trainer"),
                    "winner_weight": winner_attrs.get("weight"),
                    "distance_furlongs": winner_attrs.get("distance_furlongs"),
                }
            )
        edge["meetings"] += 1
        edge["direct_records"].append(edge_row)
        edge["sources"]["head_to_head"] += 1
        margin = safe_float(row.get("margin"), 0.0)
        edge["max_margin"] = max(edge["max_margin"], margin)
        if margin >= 3:
            edge["clear_margin_count"] += 1
        if safe_float(row.get("loser_signal_score"), 0.0) >= 75:
            edge["beat_high_signal_count"] += 1
        d = days_since(row.get("date"), as_of)
        if d is not None and d <= 180:
            edge["recent_180d"] += 1
        if d is not None and d <= 365:
            edge["recent_365d"] += 1
        edge["latest_date"] = max(edge["latest_date"], str(row.get("date") or ""))

    for row in iter_jsonl(HISTORIC_RIVAL_MASTER):
        if not is_before_target_date(row.get("historic_date"), as_of):
            continue
        winner = clean_name(row.get("winner"))
        loser = clean_name(row.get("loser"))
        if not norm_name(winner) or not norm_name(loser):
            continue
        key = historic_meeting_key(winner, loser, row)
        if key in seen_historic_meetings:
            continue
        seen_historic_meetings.add(key)
        edge = edge_for(winner, loser)
        edge["meetings"] += 1
        edge["historic_records"].append(row)
        edge["sources"]["historic_rival"] += 1
        d = days_since(row.get("historic_date"), as_of)
        if d is not None and d <= 180:
            edge["recent_180d"] += 1
        if d is not None and d <= 365:
            edge["recent_365d"] += 1
        edge["latest_date"] = max(edge["latest_date"], str(row.get("historic_date") or ""))

    return edges


def score_direct_edge(edge: Dict[str, Any], current: Dict[str, Any], race: Dict[str, Any]) -> Tuple[int, List[str]]:
    points = 7
    notes = [f"Beat {edge['loser']} before"]
    if edge["meetings"] >= 2:
        points += min(5, edge["meetings"] - 1)
        notes.append(f"{edge['meetings']} recorded edge(s)")
    if edge["clear_margin_count"]:
        points += 3
        notes.append("clear-margin evidence")
    if edge["max_margin"] >= 8:
        points += 2
        notes.append(f"best margin {edge['max_margin']:g} lengths")
    if edge["recent_180d"]:
        points += 2
        notes.append("recent edge")
    elif edge["recent_365d"]:
        points += 1
        notes.append("edge within 12 months")
    if edge["beat_high_signal_count"]:
        points += 3
        notes.append("beat a high Signal 75 horse")

    records = edge["direct_records"][:2] + edge["historic_records"][:2]
    match_labels: List[str] = []
    for record in records:
        match_labels.extend(condition_matches(record, current, race))
    unique_matches = sorted(set(match_labels))
    if unique_matches:
        points += min(4, len(unique_matches))
        notes.append("condition match: " + ", ".join(unique_matches[:4]))
    return points, notes


def summarise_runner(
    runner: Dict[str, Any],
    race: Dict[str, Any],
    field_keys: List[str],
    edges: Dict[Tuple[str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    key = runner["horse_key"]
    direct_for = []
    direct_against = []
    indirect_for = []

    for rival_key in field_keys:
        if rival_key == key:
            continue
        positive = edges.get((key, rival_key))
        negative = edges.get((rival_key, key))
        if positive:
            points, notes = score_direct_edge(positive, runner, race)
            direct_for.append(
                {
                    "rival": positive["loser"],
                    "rival_key": rival_key,
                    "points": points,
                    "meetings": positive["meetings"],
                    "latest_date": positive["latest_date"],
                    "notes": notes[:4],
                }
            )
        if negative:
            points, notes = score_direct_edge(negative, runner, race)
            direct_against.append(
                {
                    "rival": negative["winner"],
                    "rival_key": rival_key,
                    "points": points,
                    "meetings": negative["meetings"],
                    "latest_date": negative["latest_date"],
                    "notes": notes[:4],
                }
            )

    # One-hop relationship chain: A beat B, and B beat today's rival C.
    # This is capped so it can support a view but cannot overpower direct data.
    outgoing = [loser for winner, loser in edges if winner == key]
    for middle_key in outgoing[:50]:
        for rival_key in field_keys:
            if rival_key in (key, middle_key):
                continue
            chain_edge = edges.get((middle_key, rival_key))
            first_edge = edges.get((key, middle_key))
            if not chain_edge or not first_edge:
                continue
            indirect_for.append(
                {
                    "via": first_edge["loser"],
                    "rival": chain_edge["loser"],
                    "points": 3,
                    "notes": [
                        f"{runner['horse_name']} beat {first_edge['loser']}",
                        f"{first_edge['loser']} beat {chain_edge['loser']}",
                    ],
                }
            )

    direct_score = sum(item["points"] for item in direct_for)
    negative_score = sum(min(10, item["points"]) for item in direct_against)
    indirect_score = min(9, sum(item["points"] for item in indirect_for))
    net_score = direct_score + indirect_score - negative_score

    if net_score >= 18 and direct_for:
        signal = "strong_relationship_edge"
    elif net_score >= 8 and (direct_for or indirect_for):
        signal = "positive_relationship_edge"
    elif net_score <= -8:
        signal = "relationship_warning"
    elif direct_for or direct_against or indirect_for:
        signal = "watch_relationship"
    else:
        signal = "no_relationship_evidence"

    display_notes = []
    if direct_for:
        rivals = ", ".join(item["rival"] for item in sorted(direct_for, key=lambda x: -x["points"])[:3])
        display_notes.append(f"Direct edge: has beaten today's rival(s) {rivals}.")
    if direct_against:
        rivals = ", ".join(item["rival"] for item in sorted(direct_against, key=lambda x: -x["points"])[:3])
        display_notes.append(f"Warning: previously beaten by today's rival(s) {rivals}.")
    if indirect_for:
        display_notes.append("Indirect chain: beat a horse that later beat one of today's rivals.")
    if not display_notes:
        display_notes.append("No stored horse-vs-horse edge against today's field yet.")

    return {
        "horse_name": runner["horse_name"],
        "horse_key": key,
        "course": race.get("course"),
        "race_time": race.get("race_time"),
        "race_name": race.get("race_name"),
        "market_id": race.get("market_id"),
        "signal_score": runner.get("signal_score") or runner.get("score"),
        "price": runner.get("pre_race_price") or runner.get("best_back") or runner.get("bsp"),
        "tipster_count": runner.get("tipster_count") or runner.get("tipsters") or 0,
        "relationship_score": net_score,
        "direct_edge_score": direct_score,
        "indirect_edge_score": indirect_score,
        "negative_edge_score": negative_score,
        "relationship_signal": signal,
        "direct_edges": sorted(direct_for, key=lambda x: -x["points"])[:8],
        "negative_edges": sorted(direct_against, key=lambda x: -x["points"])[:8],
        "indirect_edges": indirect_for[:8],
        "public_label": " ".join(display_notes[:3]),
        "recommended_use": recommended_use(signal),
    }


def recommended_use(signal: str) -> str:
    if signal == "strong_relationship_edge":
        return "Strong support evidence. Can support selection only if normal price, field, form and scoring gates are sound."
    if signal == "positive_relationship_edge":
        return "Useful support evidence. Treat as a positive note, not a standalone reason to pick."
    if signal == "relationship_warning":
        return "Warning evidence. Review before trusting the horse against this field."
    if signal == "watch_relationship":
        return "Relationship evidence exists but is not decisive yet."
    return "Store for future learning only."


def build_field_graph(date: str) -> Dict[str, Any]:
    fields = load_today_fields(date)
    edges = build_edges(date)
    races = []
    all_runners = []
    for market_id, race in sorted(fields.items(), key=lambda item: (str(item[1].get("race_time") or ""), str(item[1].get("course") or ""))):
        runners = race.get("runners") or []
        field_keys = [runner["horse_key"] for runner in runners if runner.get("horse_key")]
        summaries = [
            summarise_runner(runner, {**race, "market_id": market_id}, field_keys, edges)
            for runner in runners
        ]
        summaries.sort(key=lambda item: (-item["relationship_score"], item["horse_name"]))
        races.append(
            {
                "market_id": market_id,
                "course": race.get("course"),
                "race_time": race.get("race_time"),
                "race_name": race.get("race_name"),
                "runner_count": len(runners),
                "source": race.get("source"),
                "runners": summaries,
                "top_relationship_horses": summaries[:5],
                "relationship_warnings": [item for item in summaries if item["relationship_signal"] == "relationship_warning"][:5],
            }
        )
        all_runners.extend(summaries)

    signal_counts = Counter(item["relationship_signal"] for item in all_runners)
    return {
        "date": date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "field_graph_shadow_and_support",
        "scoringImpact": "none_directly",
        "notes": [
            "This is a horse relationship graph: direct rival edges, negative rival edges and short indirect chains.",
            "It is designed to show whether a horse has already proved it can beat today's actual opposition.",
            "It is not a standalone pick generator and does not change proof or settlement.",
        ],
        "raceCount": len(races),
        "runnerCount": len(all_runners),
        "edgeCount": len(edges),
        "signalCounts": dict(signal_counts),
        "currentRunners": sorted(all_runners, key=lambda item: (str(item.get("race_time") or ""), str(item.get("course") or ""), item["horse_name"])),
        "topCurrentRunners": sorted(all_runners, key=lambda item: (-item["relationship_score"], item["horse_name"]))[:50],
        "races": races,
    }


def update_profile_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = load_json(FIELD_GRAPH_PROFILE, {"profiles": {}, "dates": []})
    profiles = current.setdefault("profiles", {})
    for runner in payload.get("currentRunners") or []:
        key = runner.get("horse_key")
        if not key:
            continue
        if runner.get("relationship_signal") == "no_relationship_evidence":
            continue
        profile = profiles.setdefault(
            key,
            {
                "horse_name": runner.get("horse_name"),
                "horse_key": key,
                "times_seen_with_relationship_edge": 0,
                "times_seen_with_warning": 0,
                "best_relationship_score": 0,
                "last_seen": "",
                "latest_public_label": "",
                "examples": [],
            },
        )
        signal = runner.get("relationship_signal")
        if signal in ("strong_relationship_edge", "positive_relationship_edge"):
            profile["times_seen_with_relationship_edge"] += 1
        if signal == "relationship_warning":
            profile["times_seen_with_warning"] += 1
        profile["best_relationship_score"] = max(int(profile.get("best_relationship_score") or 0), int(runner.get("relationship_score") or 0))
        profile["last_seen"] = payload.get("date")
        profile["latest_public_label"] = runner.get("public_label") or ""
        profile["examples"] = ([runner] + list(profile.get("examples") or []))[:5]
    dates = current.setdefault("dates", [])
    if payload.get("date") not in dates:
        dates.append(payload.get("date"))
    current["dates"] = dates[-60:]
    current["generatedAt"] = datetime.now(timezone.utc).isoformat()
    current["profileCount"] = len(profiles)
    write_json(FIELD_GRAPH_PROFILE, current)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Signal 75 field graph intelligence.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    payload = build_field_graph(args.date)
    out_path = INTEL_DIR / f"field_graph_{args.date}.json"
    write_json(out_path, payload)
    profiles = update_profile_store(payload)

    print("Field graph intelligence built")
    print(f"  Races: {payload['raceCount']}")
    print(f"  Runners: {payload['runnerCount']}")
    print(f"  Relationship edges: {payload['edgeCount']}")
    print(f"  Profile count: {profiles.get('profileCount', 0)}")
    print(f"  Output: {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
