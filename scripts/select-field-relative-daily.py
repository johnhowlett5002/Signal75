#!/usr/bin/env python3
"""Build a daily 1-3 pick list from field_relative_v1 output.

Analysis only. This script never writes picks.json, performance.json,
scoring_engine.py, settlement files, or public proof.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "data"
FIELD_RELATIVE_SCRIPT = REPO_ROOT / "scripts" / "select-field-relative-v1.py"
FORM_HISTORY_DB = DATA / "horse_intelligence" / "form_history.sqlite"
STRONG_FORM_PATTERNS = {
    "111",
    "112",
    "121",
    "211",
    "113",
    "1111",
    "1112",
    "1121",
    "2111",
    "1122",
}


def read_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def norm(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def form_pattern_from_string(form_value: object, length: int = 4) -> str:
    text = str(form_value or "").upper()
    cleaned = re.sub(r"[^0-9PFURBS]", "", text)
    if not cleaned:
        return ""
    return cleaned[-length:]


def form_place_rate_from_db(form_value: object) -> dict:
    pattern = form_pattern_from_string(form_value, 4)
    if not pattern:
        return {
            "pattern": "",
            "pattern_length": 0,
            "starts": 0,
            "place_rate": None,
            "source": "missing_form",
        }

    if FORM_HISTORY_DB.exists():
        try:
            conn = sqlite3.connect(str(FORM_HISTORY_DB))
            conn.execute("PRAGMA query_only = ON")
            candidates = [pattern]
            if len(pattern) >= 4:
                candidates.append(pattern[-3:])
            for candidate in candidates:
                row = conn.execute(
                    """
                    SELECT pattern_length, pattern, starts, wins, places, win_rate, place_rate
                    FROM form_pattern_stats
                    WHERE pattern_length = ? AND pattern = ?
                    """,
                    (len(candidate), candidate),
                ).fetchone()
                if not row:
                    continue
                rate = float(row[6] or 0)
                if rate > 1:
                    rate = rate / 100.0
                conn.close()
                return {
                    "pattern_length": int(row[0]),
                    "pattern": str(row[1]),
                    "starts": int(row[2] or 0),
                    "wins": int(row[3] or 0),
                    "places": int(row[4] or 0),
                    "win_rate": float(row[5] or 0),
                    "place_rate": rate,
                    "source": "form_pattern_stats",
                }
            conn.close()
        except Exception:
            pass

    fallback_pattern = pattern if len(pattern) >= 3 else pattern[-3:]
    if fallback_pattern in STRONG_FORM_PATTERNS or pattern[-3:] in STRONG_FORM_PATTERNS:
        return {
            "pattern": fallback_pattern,
            "pattern_length": len(fallback_pattern),
            "starts": 0,
            "place_rate": 0.45,
            "source": "strong_pattern_fallback",
        }
    if len(fallback_pattern) >= 3 and not any(ch in "123" for ch in fallback_pattern if ch.isdigit()):
        return {
            "pattern": fallback_pattern,
            "pattern_length": len(fallback_pattern),
            "starts": 0,
            "place_rate": 0.14,
            "source": "all_unplaced_fallback",
        }
    return {
        "pattern": fallback_pattern,
        "pattern_length": len(fallback_pattern),
        "starts": 0,
        "place_rate": None,
        "source": "no_pattern_stats",
    }


def form_strength_from_place_rate(place_rate: float | None) -> str:
    if place_rate is None:
        return "UNKNOWN"
    if place_rate >= 0.45:
        return "STRONG"
    if place_rate >= 0.35:
        return "GOOD"
    if place_rate >= 0.20:
        return "WEAK"
    return "AVOID"


def form_score_bonus(place_rate: float | None) -> int:
    if place_rate is None:
        return 0
    if place_rate >= 0.55:
        return 5
    if place_rate >= 0.45:
        return 3
    if place_rate >= 0.35:
        return 0
    if place_rate < 0.15:
        return -8
    if place_rate < 0.25:
        return -3
    return 0


def form_profile(row: dict) -> dict:
    stats = form_place_rate_from_db(row.get("form"))
    place_rate = stats.get("place_rate")
    bonus = form_score_bonus(place_rate)
    raw_score = field_score_value(row)
    return {
        **stats,
        "strength": form_strength_from_place_rate(place_rate),
        "bonus": bonus,
        "raw_field_score": round(raw_score, 1),
        "adjusted_field_score": round(raw_score + bonus, 1),
    }


def field_score_value(row: dict) -> float:
    try:
        return float(row.get("field_score") or row.get("field_relative_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def source_candidates(date_text: str) -> list[Path]:
    return [
        DATA / "challenger_lab" / f"challenger_field_relative_{date_text}.json",
        DATA / f"field_relative_{date_text}.json",
        DASHBOARD_DATA / "fieldRelative.json",
    ]


def load_field_relative_feed(date_text: str, run_if_missing: bool = True) -> tuple[dict | None, Path | None, str | None]:
    for path in source_candidates(date_text):
        if not path.exists():
            continue
        try:
            feed = read_json(path)
        except json.JSONDecodeError as exc:
            return None, path, f"invalid JSON in {path}: {exc}"
        if str(feed.get("date") or "") == date_text:
            return feed, path, None

    if run_if_missing and FIELD_RELATIVE_SCRIPT.exists():
        cmd = [sys.executable, str(FIELD_RELATIVE_SCRIPT), "--date", date_text]
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=False)
        if result.returncode != 0:
            return None, None, "field_relative_v1 run failed: " + (result.stderr or result.stdout).strip()
        for path in source_candidates(date_text):
            if path.exists():
                feed = read_json(path)
                if str(feed.get("date") or "") == date_text:
                    return feed, path, None

    return None, None, f"no field_relative_v1 feed found for {date_text}"


def evidence_ok(row: dict) -> bool:
    return (
        int(row.get("h2h_beaten") or 0) >= 1
        or int(row.get("course_wins") or 0) >= 1
        or int(row.get("tipsters") or 0) >= 4
        or trainer_wins_here(row) >= 3
    )


def trainer_wins_here(row: dict) -> int:
    for key in ("trainer_wins_here", "trainer_course_wins", "course_trainer_wins"):
        try:
            wins = int(row.get(key) or 0)
        except (TypeError, ValueError):
            wins = 0
        if wins:
            return wins

    for reason in list(row.get("top_reasons") or []) + list(row.get("signals") or []):
        match = re.search(r"Trainer has\s+(\d+)\s+wins?", str(reason), flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def qualifies(row: dict) -> bool:
    try:
        odds = float(row.get("odds") or row.get("odds_at_pick") or 0)
    except (TypeError, ValueError):
        return False
    profile = form_profile(row)
    if profile["strength"] == "AVOID":
        return False
    if profile["strength"] == "WEAK" and int(row.get("tipsters") or 0) < 3 and int(row.get("h2h_beaten") or 0) < 2:
        return False
    return profile["adjusted_field_score"] >= 80 and 4.0 <= odds <= 7.5 and evidence_ok(row)


def race_key(row: dict) -> tuple[str, str]:
    return (norm(row.get("course")), str(row.get("time") or ""))


def bet_model(count: int) -> tuple[str, float, int, str]:
    if count >= 3:
        return "each_way_patent", 14.0, 14, "Field-relative Patent"
    if count == 2:
        return "each_way_double", 12.0, 6, "Field-relative Double"
    if count == 1:
        return "each_way_single", 14.0, 2, "Field-relative Single"
    return "no_bet", 0.0, 0, "No field-relative bet"


def reason_list(row: dict) -> list[str]:
    reasons = []
    profile = form_profile(row)
    beaten = int(row.get("h2h_beaten") or 0)
    course_wins = int(row.get("course_wins") or 0)
    tipsters = int(row.get("tipsters") or 0)
    trainer_wins = trainer_wins_here(row)
    place_rate = profile.get("place_rate")
    if profile["strength"] == "STRONG" and place_rate is not None:
        reasons.append(f"Strong form pattern: {place_rate * 100:.1f}% place rate")
    if beaten:
        reasons.append(f"Beaten {beaten} rival{'s' if beaten != 1 else ''} in today's field")
    if course_wins:
        reasons.append(f"{course_wins} course win{'s' if course_wins != 1 else ''}")
    if tipsters >= 4:
        reasons.append(f"{tipsters} professional tipsters")
    if trainer_wins >= 3:
        reasons.append(f"Trainer has {trainer_wins} wins here recently")
    for reason in row.get("top_reasons") or row.get("signals") or []:
        if reason and reason not in reasons:
            reasons.append(str(reason))
    return reasons[:4]


def pick_payload(row: dict) -> dict:
    profile = form_profile(row)
    return {
        "horse": row.get("name") or row.get("horse"),
        "course": row.get("course"),
        "time": row.get("time"),
        "form": row.get("form"),
        "odds": row.get("odds") or row.get("odds_at_pick"),
        "base_score": row.get("base_score"),
        "field_score": profile["adjusted_field_score"],
        "field_score_raw": profile["raw_field_score"],
        "form_pattern": profile.get("pattern"),
        "form_pattern_length": profile.get("pattern_length"),
        "form_pattern_starts": profile.get("starts"),
        "form_place_rate": profile.get("place_rate"),
        "form_strength": profile.get("strength"),
        "form_score_bonus": profile.get("bonus"),
        "form_pattern_source": profile.get("source"),
        "h2h_beaten": int(row.get("h2h_beaten") or 0),
        "h2h_lost_to": int(row.get("h2h_lost_to") or 0),
        "course_wins": int(row.get("course_wins") or 0),
        "course_places": int(row.get("course_places") or 0),
        "tipsters": int(row.get("tipsters") or 0),
        "trainer_wins_here": trainer_wins_here(row),
        "top_reasons": reason_list(row),
        "top_risks": list(row.get("top_risks") or [])[:3],
        "analysis_only": True,
        "live_result": None,
        "position": None,
        "bsp": None,
        "profit": None,
    }


def select_daily(feed: dict) -> list[dict]:
    rows = [row for row in feed.get("picks", []) if isinstance(row, dict) and qualifies(row)]
    rows.sort(key=lambda row: form_profile(row)["adjusted_field_score"], reverse=True)

    selected = []
    seen_races = set()
    for row in rows:
        key = race_key(row)
        if key in seen_races:
            continue
        selected.append(pick_payload(row))
        seen_races.add(key)
        if len(selected) == 3:
            break
    return selected


def rebuild_performance() -> dict:
    rows = []
    for path in sorted(DATA.glob("field_relative_daily_*.json")):
        item = read_json(path)
        if not item.get("settled"):
            continue
        rows.append(item)
    stake = sum(float(row.get("total_stake") or 0) for row in rows)
    returned = sum(float(row.get("total_return") or 0) for row in rows)
    profit = sum(float(row.get("profit") or 0) for row in rows)
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_only": True,
        "days": len(rows),
        "total_stake": round(stake, 2),
        "total_return": round(returned, 2),
        "total_profit": round(profit, 2),
        "roi": round((profit / stake * 100), 1) if stake else 0.0,
        "recent_results": [
            {
                "date": row.get("date"),
                "bet_type": row.get("bet_type"),
                "stake": row.get("total_stake"),
                "return": row.get("total_return"),
                "profit": row.get("profit"),
            }
            for row in rows[-30:]
        ],
    }


def build(date_text: str, run_if_missing: bool = True, verbose: bool = False) -> dict:
    feed, source, error = load_field_relative_feed(date_text, run_if_missing=run_if_missing)
    if error:
        payload = {
            "date": date_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_only": True,
            "available": False,
            "reason": error,
            "bet_type": "no_bet",
            "total_stake": 0.0,
            "bet_lines": 0,
            "picks": [],
            "live_result": None,
            "position": None,
            "profit": None,
            "settled": False,
        }
    else:
        picks = select_daily(feed or {})
        bet_type, stake, lines, label = bet_model(len(picks))
        payload = {
            "date": date_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(source.relative_to(REPO_ROOT)) if source else None,
            "analysis_only": True,
            "available": True,
            "bet_type": bet_type,
            "bet_label": label,
            "total_stake": stake,
            "bet_lines": lines,
            "selection_rule": "field_score >= 80, odds 4.0-7.5, one pick per race, h2h_beaten >= 1 or course_wins >= 1 or tipsters >= 4 or trainer_wins_here >= 3",
            "picks": picks,
            "live_result": None,
            "position": None,
            "profit": None,
            "settled": False,
        }

    out = DATA / f"field_relative_daily_{date_text}.json"
    write_json(out, payload)
    write_json(DATA / "field_relative_performance.json", rebuild_performance())

    if verbose:
        print(f"date: {date_text}")
        print(f"available: {payload.get('available')}")
        if not payload.get("available"):
            print(f"reason: {payload.get('reason')}")
        else:
            print(f"source: {payload.get('source_file')}")
        print(f"bet_type: {payload.get('bet_type')}")
        print(f"stake: {payload.get('total_stake')}")
        print(f"picks: {len(payload.get('picks') or [])}")
        for idx, pick in enumerate(payload.get("picks") or [], 1):
            print(
                f"{idx}. {pick.get('horse')} | {pick.get('course')} {pick.get('time')} | "
                f"odds={pick.get('odds')} | field_score={pick.get('field_score')} "
                f"(raw={pick.get('field_score_raw')}, form_bonus={pick.get('form_score_bonus')}) | "
                f"form={pick.get('form')} | form_place_rate={pick.get('form_place_rate')} | "
                f"form_strength={pick.get('form_strength')} | "
                f"h2h_beaten={pick.get('h2h_beaten')} | course_wins={pick.get('course_wins')} | "
                f"tipsters={pick.get('tipsters')} | trainer_wins_here={pick.get('trainer_wins_here')}"
            )
            for reason in pick.get("top_reasons") or []:
                print(f"   - {reason}")
        print(f"wrote: {out.relative_to(REPO_ROOT)}")

    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-run-v1", action="store_true", help="Do not attempt to run select-field-relative-v1.py if feed is missing")
    args = parser.parse_args()
    build(args.date, run_if_missing=not args.no_run_v1, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
