#!/usr/bin/env python3
"""Build field relationship intelligence for Signal 75.

This is the richer "Grandad's book" layer. It combines head-to-head records,
historic rival meetings, and result-note context into horse-level evidence:
who this horse has beaten, whether it was decisive, whether the conditions were
similar, and whether the pattern is strong enough to support future selection.

It is deliberately conservative. It writes analysis files and a controlled
profile used by the existing rival-memory overlay. It does not touch proof,
settlement, public results, unlock logic, or historical picks.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INTEL_DIR = DATA_DIR / "horse_intelligence"
DB_PATH = INTEL_DIR / "signal75_history.sqlite"
HEAD_TO_HEAD_PROFILES = INTEL_DIR / "head_to_head_profiles.json"
HISTORIC_RIVAL_PROFILES = INTEL_DIR / "historic_rival_profiles.json"
RESULT_NOTE_PROFILES = INTEL_DIR / "race_result_note_profiles.json"
OUTPUT_TEMPLATE = INTEL_DIR / "field_relationships_{}.json"
PROFILE_FILE = INTEL_DIR / "field_relationship_profiles.json"


def norm_name(value: Any) -> str:
    text = re.sub(r"^\s*\d+\.\s*", "", str(value or ""))
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def clean_name(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip())


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def parse_date(value: Any) -> Optional[datetime]:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None


def days_since(value: Any, as_of: str) -> Optional[int]:
    left = parse_date(value)
    right = parse_date(as_of)
    if not left or not right:
        return None
    return max(0, (right - left).days)


def distance_bucket(furlongs: Any) -> str:
    d = safe_float(furlongs, -1)
    if d < 0:
        return "unknown"
    if d <= 6:
        return "sprint"
    if d <= 9:
        return "mile"
    if d <= 14:
        return "middle"
    if d <= 19:
        return "staying"
    return "extended"


def race_family(value: Any) -> str:
    text = str(value or "").lower()
    if "chase" in text:
        return "chase"
    if "hurdle" in text or "hrd" in text:
        return "hurdle"
    if "bumper" in text or "nh flat" in text:
        return "bumper"
    return "flat"


def read_sql_rows(table: str) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(f"SELECT * FROM {table}").fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def decode_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return json.loads(row.get("payload_json") or "{}")
    except json.JSONDecodeError:
        return {}


def add_signal(scores: Dict[str, Any], points: int, label: str, note: str) -> None:
    scores["relationship_score"] += points
    scores["signals"].append(label)
    scores["notes"].append(note)


def condition_score(record: Dict[str, Any]) -> int:
    score = 0
    if record.get("historic_race_type"):
        score += 1
    if distance_bucket(record.get("historic_distance_furlongs")) != "unknown":
        score += 1
    if record.get("historic_course") and record.get("target_course") and record.get("historic_course") == record.get("target_course"):
        score += 2
    # Going is only available where result-note seeds have captured it. Missing
    # going should not count against a horse yet.
    if record.get("going") and record.get("target_going") and str(record.get("going")).lower() == str(record.get("target_going")).lower():
        score += 2
    return min(6, score)


def build_horse_profiles(as_of: str) -> Dict[str, Dict[str, Any]]:
    horses: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "horse_name": "",
            "horse_key": "",
            "relationship_score": 0,
            "overlay_points": 0,
            "selection_signal": "none",
            "signals": [],
            "notes": [],
            "rivals_beaten": Counter(),
            "rivals_lost_to": Counter(),
            "decisive_wins": 0,
            "clear_margins": [],
            "same_or_known_condition_edges": 0,
            "beat_high_signal_horses": 0,
            "recent_edges_180d": 0,
            "recent_edges_365d": 0,
            "meetings_logged": 0,
            "last_seen": "",
            "last_evidence": "",
            "evidence_examples": [],
        }
    )

    # 1. Direct race-memory head-to-head evidence.
    for row in read_sql_rows("head_to_head"):
        payload = decode_payload(row)
        winner = clean_name(row.get("winner"))
        loser = clean_name(row.get("loser"))
        winner_key = norm_name(winner)
        loser_key = norm_name(loser)
        if not winner_key or not loser_key:
            continue
        margin = safe_float(payload.get("margin"), 0)
        d = days_since(row.get("date"), as_of)
        profile = horses[winner_key]
        profile["horse_name"] = winner
        profile["horse_key"] = winner_key
        profile["meetings_logged"] += 1
        profile["rivals_beaten"][loser] += 1
        profile["last_seen"] = max(profile["last_seen"], str(row.get("date") or ""))
        profile["last_evidence"] = row.get("evidence_note") or ""
        profile["evidence_examples"].append(row.get("evidence_note") or f"{winner} beat {loser}.")
        add_signal(profile, 2, "BEAT_RIVAL", row.get("evidence_note") or f"{winner} beat {loser}.")
        if margin >= 3:
            profile["decisive_wins"] += 1
            profile["clear_margins"].append(margin)
            add_signal(profile, 3, "CLEAR_MARGIN", f"Won the match-up by {margin:g} lengths.")
        if margin >= 8:
            add_signal(profile, 2, "DOMINANT_MARGIN", f"Dominant winning margin: {margin:g} lengths.")
        if d is not None and d <= 180:
            profile["recent_edges_180d"] += 1
            add_signal(profile, 2, "RECENT_EDGE", "Head-to-head edge was recorded in the last 180 days.")
        elif d is not None and d <= 365:
            profile["recent_edges_365d"] += 1
            add_signal(profile, 1, "YEAR_EDGE", "Head-to-head edge was recorded in the last year.")
        if payload.get("winner_signal_score") and safe_float(payload.get("winner_signal_score")) >= 90:
            add_signal(profile, 1, "HIGH_SIGNAL_PERFORMANCE", "Performed strongly while carrying a high Signal 75 score.")

        loser_profile = horses[loser_key]
        loser_profile["horse_name"] = loser
        loser_profile["horse_key"] = loser_key
        loser_profile["rivals_lost_to"][winner] += 1

    # 2. Historic same-field rival evidence from the large Betfair history.
    for row in read_sql_rows("historic_rivals"):
        payload = decode_payload(row)
        winner = clean_name(row.get("winner"))
        loser = clean_name(row.get("loser"))
        winner_key = norm_name(winner)
        loser_key = norm_name(loser)
        if not winner_key or not loser_key:
            continue
        d = days_since(row.get("historic_date"), as_of)
        profile = horses[winner_key]
        profile["horse_name"] = winner
        profile["horse_key"] = winner_key
        profile["rivals_beaten"][loser] += 1
        profile["meetings_logged"] += 1
        profile["last_seen"] = max(profile["last_seen"], str(row.get("target_date") or row.get("historic_date") or ""))
        profile["last_evidence"] = row.get("evidence_note") or ""
        profile["evidence_examples"].append(row.get("evidence_note") or f"{winner} previously beat {loser}.")
        add_signal(profile, 2, "HISTORIC_RIVAL_EDGE", row.get("evidence_note") or f"{winner} previously beat {loser}.")
        cond = condition_score({**payload, **row})
        if cond:
            profile["same_or_known_condition_edges"] += 1
            add_signal(profile, cond, "CONDITION_MATCH", f"Historic evidence has {cond}/6 condition support.")
        if d is not None and d <= 365:
            profile["recent_edges_365d"] += 1
            add_signal(profile, 1, "RECENT_HISTORIC_EDGE", "Historic rival edge is within the last year.")
        elif d is not None and d > 730:
            add_signal(profile, -1, "OLD_EVIDENCE", "Historic rival edge is over two years old.")

        loser_profile = horses[loser_key]
        loser_profile["horse_name"] = loser
        loser_profile["horse_key"] = loser_key
        loser_profile["rivals_lost_to"][winner] += 1

    # 3. Rich result notes: decisive wins and beating high-signal horses.
    result_profiles = load_json(RESULT_NOTE_PROFILES, {}).get("profiles", {})
    for horse_key, result_profile in result_profiles.items():
        key = norm_name(horse_key)
        profile = horses[key]
        profile["horse_name"] = profile["horse_name"] or clean_name(result_profile.get("horse_name"))
        profile["horse_key"] = key
        decisive = safe_int(result_profile.get("times_won_decisively")) + safe_int(result_profile.get("times_won_clear"))
        high_signal = safe_int(result_profile.get("times_beat_high_signal_horse"))
        if decisive:
            profile["decisive_wins"] += decisive
            add_signal(profile, min(6, decisive * 3), "DECISIVE_WIN_PROFILE", f"Has {decisive} decisive/clear win note(s).")
        if high_signal:
            profile["beat_high_signal_horses"] += high_signal
            add_signal(profile, min(8, high_signal * 4), "BEAT_HIGH_SIGNAL_HORSE", f"Beat high Signal 75 opposition {high_signal} time(s).")
        if safe_float(result_profile.get("best_winning_margin_lengths")) >= 3:
            margin = safe_float(result_profile.get("best_winning_margin_lengths"))
            profile["clear_margins"].append(margin)
            add_signal(profile, 2, "BEST_MARGIN_CLEAR", f"Best recorded winning margin: {margin:g} lengths.")
        if safe_int(result_profile.get("times_heavily_beaten")) >= 2:
            add_signal(profile, -5, "REPEATED_HEAVY_DEFEATS", "Repeated heavy defeat notes reduce confidence.")

    # 4. Profile-level repeated dominance from existing pair summaries.
    for source_path in (HEAD_TO_HEAD_PROFILES, HISTORIC_RIVAL_PROFILES):
        pairs = load_json(source_path, {}).get("pairs", {})
        for pair in pairs.values():
            dominant = pair.get("dominant_horse")
            dominant_key = norm_name(dominant)
            if not dominant_key:
                continue
            meetings = safe_int(pair.get("meetings_logged") or pair.get("historic_meetings_found"))
            dominance = safe_float(pair.get("dominance_rate"), 0)
            tier = pair.get("evidence_tier")
            profile = horses[dominant_key]
            profile["horse_name"] = profile["horse_name"] or clean_name(dominant)
            profile["horse_key"] = dominant_key
            if meetings >= 2 and dominance >= 0.67:
                add_signal(profile, 5, "REPEATED_DOMINANCE", f"Dominant in {meetings} recorded meeting(s), {dominance:.0%} edge.")
            if tier == "strong_pattern":
                add_signal(profile, 6, "STRONG_PATTERN", "Existing profile rates this as a strong repeat pattern.")
            elif tier == "useful_pattern":
                add_signal(profile, 3, "USEFUL_PATTERN", "Existing profile rates this as useful repeat evidence.")

    final_profiles: Dict[str, Dict[str, Any]] = {}
    for key, profile in horses.items():
        score = int(profile["relationship_score"])
        beaten = dict(profile["rivals_beaten"])
        lost_to = dict(profile["rivals_lost_to"])
        if not profile.get("horse_name"):
            continue
        if score >= 24 and (profile["decisive_wins"] or profile["beat_high_signal_horses"] or profile["same_or_known_condition_edges"]):
            signal = "strong_positive"
            overlay = 8
        elif score >= 16:
            signal = "positive"
            overlay = 5
        elif score <= -5:
            signal = "warning"
            overlay = 0
        else:
            signal = "watch_only"
            overlay = 0
        examples = []
        seen = set()
        for note in profile["evidence_examples"]:
            if not note or note in seen:
                continue
            seen.add(note)
            examples.append(note)
            if len(examples) >= 5:
                break
        final_profiles[key] = {
            "horse_name": profile["horse_name"],
            "horse_key": key,
            "relationship_score": score,
            "selection_signal": signal,
            "overlay_points": overlay,
            "rivals_beaten": beaten,
            "rivals_lost_to": lost_to,
            "rivals_beaten_count": sum(beaten.values()),
            "rivals_lost_to_count": sum(lost_to.values()),
            "decisive_wins": profile["decisive_wins"],
            "clear_margins": sorted(set(round(float(m), 2) for m in profile["clear_margins"]), reverse=True)[:8],
            "same_or_known_condition_edges": profile["same_or_known_condition_edges"],
            "beat_high_signal_horses": profile["beat_high_signal_horses"],
            "recent_edges_180d": profile["recent_edges_180d"],
            "recent_edges_365d": profile["recent_edges_365d"],
            "last_seen": profile["last_seen"],
            "last_evidence": profile["last_evidence"],
            "top_signals": Counter(profile["signals"]).most_common(10),
            "evidence_examples": examples,
            "public_label": public_label(signal, profile, beaten),
            "recommended_use": recommended_use(signal),
        }
    return dict(sorted(final_profiles.items(), key=lambda item: (-item[1]["relationship_score"], item[1]["horse_name"])))


def public_label(signal: str, profile: Dict[str, Any], beaten: Dict[str, int]) -> str:
    if signal in {"strong_positive", "positive"}:
        rivals = sorted(beaten, key=lambda name: beaten[name], reverse=True)[:2]
        rival_text = ", ".join(rivals) if rivals else "previous rivals"
        if profile["decisive_wins"]:
            return f"Horse memory: proven against {rival_text}, including decisive win evidence."
        if profile["same_or_known_condition_edges"]:
            return f"Horse memory: previous rival edge with similar/known race conditions."
        return f"Horse memory: has beaten {rival_text} before."
    if signal == "warning":
        return "Horse memory warning: repeated negative relationship evidence."
    return "Horse memory note: relationship evidence recorded for review."


def recommended_use(signal: str) -> str:
    if signal == "strong_positive":
        return "Eligible for controlled memory support if current price, field size and form gates also pass."
    if signal == "positive":
        return "Useful support note; small controlled overlay only when normal gates are sound."
    if signal == "warning":
        return "Show as warning/review evidence; do not promote without separate support."
    return "Store for future pattern-building only."


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Signal 75 field relationship memory.")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    profiles = build_horse_profiles(args.date)
    output = {
        "date": args.date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "controlled_overlay_ready",
        "scoringImpact": "small_positive_overlay_only_when_existing_gates_pass",
        "horseCount": len(profiles),
        "strongPositiveCount": sum(1 for p in profiles.values() if p.get("selection_signal") == "strong_positive"),
        "positiveCount": sum(1 for p in profiles.values() if p.get("selection_signal") == "positive"),
        "warningCount": sum(1 for p in profiles.values() if p.get("selection_signal") == "warning"),
        "notes": [
            "This is the richer Grandad's book layer: field relationship evidence, not a standalone tip.",
            "It combines repeated head-to-head records, historic rival evidence, margins, decisive wins, high-signal victims and condition support where available.",
            "A horse can only receive live memory support through the existing guarded overlay; bad form, weak price, low score or small-field gates still block official promotion.",
        ],
        "profiles": profiles,
    }

    daily_summary = {
        key: value
        for key, value in output.items()
        if key != "profiles"
    }
    daily_summary["top_profiles"] = list(profiles.values())[:100]

    write_json(OUTPUT_TEMPLATE.with_name(f"field_relationships_{args.date}.json"), daily_summary)
    write_json(PROFILE_FILE, output)
    print("Field relationship memory built")
    print(f"  Horses profiled: {output['horseCount']}")
    print(f"  Strong positive: {output['strongPositiveCount']}")
    print(f"  Positive: {output['positiveCount']}")
    print(f"  Warnings: {output['warningCount']}")
    print(f"  Output: {OUTPUT_TEMPLATE.with_name(f'field_relationships_{args.date}.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
