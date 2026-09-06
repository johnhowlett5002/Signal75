#!/usr/bin/env python3
"""Collect complete finishing orders for the daily racecard.

This is an analysis/storage feed. It does not alter official settlement,
proof, performance, picks, scoring, unlock logic, or public result maths.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
INTEL = DATA / "horse_intelligence"


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", clean_text(value).upper())


def course_slug(value: Any) -> str:
    slug = clean_text(value).lower().replace("royal ascot", "ascot")
    slug = re.sub(r"\s+\d+(?:st|nd|rd|th)?\s+\w+$", "", slug)
    slug = slug.replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_position(value: Any) -> Tuple[Optional[int], str]:
    text = clean_text(value).upper()
    match = re.search(r"\b(\d+)(?:ST|ND|RD|TH)\b", text)
    if match:
        return int(match.group(1)), "FINISHED"
    if text in {"-", "NR", "NON-RUNNER", "NON RUNNER", "REMOVED", "WITHDRAWN"}:
        return None, "NON_RUNNER"
    return None, text or "UNKNOWN"


def length_value(value: Any) -> Optional[float]:
    text = clean_text(value).lower()
    if not text:
        return 0.0
    aliases = {
        "nse": 0.05,
        "nose": 0.05,
        "sh": 0.05,
        "s hd": 0.05,
        "hd": 0.1,
        "head": 0.1,
        "nk": 0.25,
        "neck": 0.25,
        "dist": 30.0,
    }
    if text in aliases:
        return aliases[text]
    fractions = {"¼": 0.25, "½": 0.5, "¾": 0.75}
    total = 0.0
    found = False
    number = re.search(r"\d+(?:\.\d+)?", text)
    if number:
        total += float(number.group(0))
        found = True
    for token, amount in fractions.items():
        if token in text:
            total += amount
            found = True
    return total if found else None


def parse_result_page(page: str, course: str, source_url: str) -> List[Dict[str, Any]]:
    races: List[Dict[str, Any]] = []
    heading = re.compile(
        r'<h2\s+id="(?P<time>\d{1,2}:\d{2})"[^>]*>.*?\bResult</h2>(?P<body>.*?)(?=<h2\s+id="|\Z)',
        re.I | re.S,
    )
    for match in heading.finditer(page):
        race_time = match.group("time")
        body = match.group("body")
        status_match = re.search(r"Race Status:\s*([^<\r\n]+)", body, re.I)
        race_status = clean_text(status_match.group(1)) if status_match else ""
        runners: List[Dict[str, Any]] = []
        chunks = re.split(r'<li\s+class="(?:results-table-row|results-row)"', body, flags=re.I)[1:]
        cumulative = 0.0
        for chunk in chunks:
            name_match = re.search(r'class="runner-title"[^>]*>\s*([^<]+?)\s*</a>', chunk, re.I | re.S)
            if not name_match:
                name_match = re.search(
                    r'class="inner-result-content position-name"[^>]*>\s*([^<]+?)\s*</span>',
                    chunk,
                    re.I | re.S,
                )
            if not name_match:
                continue
            position_match = re.search(r'class="number position"[^>]*>(.*?)</span>', chunk, re.I | re.S)
            if not position_match:
                position_match = re.search(
                    r'class="inner-result-content place-content"[^>]*>\s*([^<]+?)\s*</span>',
                    chunk,
                    re.I | re.S,
                )
            position, runner_status = parse_position(position_match.group(1) if position_match else "")
            distance_match = re.search(r'class="dist-title"[^>]*>(.*?)</span>', chunk, re.I | re.S)
            beaten_by_text = clean_text(distance_match.group(1)) if distance_match else ""
            beaten_by = length_value(beaten_by_text) if position and position > 1 else 0.0 if position == 1 else None
            if position and position > 1 and beaten_by is not None:
                cumulative += beaten_by
            odds_match = re.search(r'data-oddsdecimal="([^"]+)"', chunk[:500], re.I)
            sp_decimal = safe_float(odds_match.group(1)) if odds_match else None
            if sp_decimal is not None and sp_decimal >= 99999:
                sp_decimal = None
            runners.append(
                {
                    "horse_name": clean_text(name_match.group(1)),
                    "horse_key": norm_name(name_match.group(1)),
                    "position": position,
                    "status": runner_status,
                    "sp_decimal": sp_decimal,
                    "beaten_by_text": beaten_by_text,
                    "beaten_by": beaten_by,
                    "distance_from_winner": round(cumulative, 3) if position else None,
                }
            )
        races.append(
            {
                "course": clean_text(course),
                "race_time": race_time,
                "race_status": race_status,
                "settled": bool(runners) and "AWAITING" not in race_status.upper(),
                "source_url": source_url,
                "runners": runners,
            }
        )
    return races


def load_expected_races(date_text: str) -> List[Dict[str, Any]]:
    comparison = read_json(DATA / f"race_comparison_{date_text}.json", {})
    races = comparison.get("races", []) if isinstance(comparison, dict) else []
    if races:
        return [race for race in races if isinstance(race, dict)]
    return []


def unsupported_race_reason(race: Dict[str, Any]) -> Optional[str]:
    race_name = clean_text(race.get("race_name"))
    if re.search(r"\bArab(?:ian)?\b", race_name, re.I):
        return "Arabian race - outside the Signal 75 evidence base"
    for runner in race.get("runners", []) or []:
        warnings = runner.get("warnings") or []
        if any("Arabian race" in clean_text(warning) for warning in warnings):
            return "Arabian race - outside the Signal 75 evidence base"
    return None


def fetch_page(url: str, timeout: int = 20) -> str:
    # horseracing.net rejects product tokens appended to a browser User-Agent
    # from some data-centre networks. Keep this deliberately generic.
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "ignore")


def expected_race_key(course: Any, race_time: Any) -> Tuple[str, str]:
    return norm_name(course), clean_text(race_time)


def collect(date_text: str, fetcher=fetch_page) -> Dict[str, Any]:
    expected_races = load_expected_races(date_text)
    supported_races = [race for race in expected_races if not unsupported_race_reason(race)]
    excluded_races = [race for race in expected_races if unsupported_race_reason(race)]
    parsed_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    errors: List[str] = []
    courses = sorted({clean_text(race.get("course")) for race in expected_races if race.get("course")})
    day = datetime.strptime(date_text, "%Y-%m-%d").strftime("%d-%m-%y")
    for course in courses:
        url = f"https://www.horseracing.net/results/{course_slug(course)}/{day}"
        try:
            page = fetcher(url)
            for race in parse_result_page(page, course, url):
                parsed_by_key[expected_race_key(course, race.get("race_time"))] = race
        except Exception as exc:
            errors.append(f"{course}: {exc}")

    output_races: List[Dict[str, Any]] = []
    output_rows: List[Dict[str, Any]] = []
    missing_races: List[str] = []
    unmatched_runners: List[str] = []
    for expected in expected_races:
        course = clean_text(expected.get("course"))
        race_time = clean_text(expected.get("time"))
        market_id = clean_text(expected.get("market_id"))
        exclusion_reason = unsupported_race_reason(expected)
        if exclusion_reason:
            output_races.append(
                {
                    "market_id": market_id,
                    "course": course,
                    "race_time": race_time,
                    "settled": False,
                    "excluded": True,
                    "exclusion_reason": exclusion_reason,
                    "expected_runner_count": len(expected.get("runners", []) or []),
                    "matched_runner_count": 0,
                    "runners": [],
                }
            )
            continue
        parsed = parsed_by_key.get(expected_race_key(course, race_time))
        if not parsed or not parsed.get("settled"):
            missing_races.append(f"{course} {race_time}")
            output_races.append(
                {
                    "market_id": market_id,
                    "course": course,
                    "race_time": race_time,
                    "settled": False,
                    "expected_runner_count": len(expected.get("runners", []) or []),
                    "matched_runner_count": 0,
                    "runners": [],
                }
            )
            continue
        parsed_index = {row.get("horse_key"): row for row in parsed.get("runners", []) if row.get("horse_key")}
        race_rows: List[Dict[str, Any]] = []
        for runner in expected.get("runners", []) or []:
            name = clean_text(runner.get("name") or runner.get("horse_name"))
            result = parsed_index.get(norm_name(name))
            if not result:
                unmatched_runners.append(f"{course} {race_time}: {name}")
                continue
            row = {
                **result,
                "date": date_text,
                "market_id": market_id,
                "course": course,
                "race_time": race_time,
                "race_name": clean_text(expected.get("race_name")),
                "runner_number": runner.get("number"),
                "source": "horseracing.net",
                "source_url": parsed.get("source_url"),
            }
            race_rows.append(row)
            output_rows.append(row)
        output_races.append(
            {
                "market_id": market_id,
                "course": course,
                "race_time": race_time,
                "race_status": parsed.get("race_status"),
                "settled": True,
                "expected_runner_count": len(expected.get("runners", []) or []),
                "matched_runner_count": len(race_rows),
                "source_runner_count": len(parsed.get("runners", []) or []),
                "source_url": parsed.get("source_url"),
                "runners": race_rows,
            }
        )

    expected_runner_count = sum(len(race.get("runners", []) or []) for race in supported_races)
    positioned = sum(1 for row in output_rows if row.get("position") is not None)
    non_runners = sum(1 for row in output_rows if row.get("status") == "NON_RUNNER")
    unresolved_statuses = {"", "UNKNOWN", "PENDING", "AWAITING"}
    resolved = sum(
        1
        for row in output_rows
        if row.get("position") is not None
        or clean_text(row.get("status")).upper() not in unresolved_statuses
    )
    non_finishers = resolved - positioned - non_runners
    settled_races = sum(1 for race in output_races if race.get("settled"))
    complete = (
        bool(supported_races)
        and settled_races == len(supported_races)
        and len(output_rows) == expected_runner_count
        and resolved == len(output_rows)
        and not errors
    )
    return {
        "date": date_text,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "analysisOnly": True,
        "scoringImpact": "none",
        "proofImpact": "none",
        "complete": complete,
        "summary": {
            "cardRaces": len(expected_races),
            "expectedRaces": len(supported_races),
            "settledRaces": settled_races,
            "expectedRunners": expected_runner_count,
            "matchedRunners": len(output_rows),
            "positionedRunners": positioned,
            "nonRunners": non_runners,
            "nonFinishers": non_finishers,
            "resolvedRunners": resolved,
            "missingRaces": missing_races,
            "excludedRaces": [
                {
                    "course": clean_text(race.get("course")),
                    "raceTime": clean_text(race.get("time")),
                    "reason": unsupported_race_reason(race),
                }
                for race in excluded_races
            ],
            "unmatchedRunners": unmatched_runners,
            "fetchErrors": errors,
        },
        "races": output_races,
        "records": output_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect complete daily race finishing orders.")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    payload = collect(args.date)
    output = INTEL / f"full_field_results_{args.date}.json"
    write_json(output, payload)
    summary = payload["summary"]
    print(
        f"Full-field results {args.date}: "
        f"{summary['settledRaces']}/{summary['expectedRaces']} races, "
        f"{summary['matchedRunners']}/{summary['expectedRunners']} runners matched, "
        f"{summary['positionedRunners']} finishers, {summary['nonRunners']} non-runners"
    )
    if summary["missingRaces"]:
        print("Missing races: " + ", ".join(summary["missingRaces"]))
    if summary["unmatchedRunners"]:
        print("Unmatched runners: " + ", ".join(summary["unmatchedRunners"][:20]))
    if summary["fetchErrors"]:
        print("Fetch errors: " + "; ".join(summary["fetchErrors"]))
    print(f"Output: {output.relative_to(REPO_ROOT)}")
    return 0 if payload.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
