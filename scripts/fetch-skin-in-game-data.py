#!/usr/bin/env python3
"""
Collect the pre-race briefing for skin_in_game_v1.

Analysis-only. This script reads the local race field, fetches public web pages
best-effort, and writes data/skin_in_game_briefing_YYYY-MM-DD.json.
It never writes picks, proof, performance, scoring, or settlement files.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA = REPO_ROOT / "data"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)
MAX_HTML_CHARS = 120_000
MAX_TEXT_CHARS = 7_500
MAX_PROFILE_FETCHES = 12


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_date() -> str:
    return date.today().isoformat()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def clean_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT_CHARS]


def title_from_html(raw_html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw_html)
    return clean_text(match.group(1))[:160] if match else ""


def fetch_url(url: str, timeout: int = 12) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read(MAX_HTML_CHARS)
            raw = body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
            return {
                "url": url,
                "ok": True,
                "status": getattr(response, "status", 200),
                "title": title_from_html(raw),
                "text_excerpt": clean_text(raw),
                "chars_collected": len(raw),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"url": url, "ok": False, "status": exc.code, "title": "", "text_excerpt": "", "chars_collected": 0, "error": str(exc)}
    except Exception as exc:
        return {"url": url, "ok": False, "status": None, "title": "", "text_excerpt": "", "chars_collected": 0, "error": str(exc)}


def recent_result_files(date_value: str, limit: int = 7) -> List[Path]:
    files = sorted(DATA.glob("2026-*.json"))
    filtered = [path for path in files if path.stem < date_value]
    return filtered[-limit:]


def official_picks_for_comparison(picks_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for section in ("flat", "jumps"):
        for race in picks_payload.get(section, []) or []:
            for horse in race.get("horses") or []:
                rows.append(
                    {
                        "horse": horse.get("name", ""),
                        "course": race.get("course", ""),
                        "time": race.get("time", ""),
                        "distance": race.get("distance", ""),
                        "going": race.get("going", ""),
                        "race_type": race.get("race_type", section),
                        "runners": race.get("runners") or race.get("field_size"),
                        "odds": horse.get("odds"),
                    }
                )
    return rows


def race_field_summary(comparison_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    races: List[Dict[str, Any]] = []
    for race in comparison_payload.get("races", []) or []:
        runners = []
        for runner in race.get("runners", []) or []:
            runners.append(
                {
                    "horse": runner.get("name") or runner.get("horse"),
                    "odds": runner.get("odds"),
                    "form": runner.get("form"),
                    "jockey": runner.get("jockey"),
                    "trainer": runner.get("trainer"),
                    "draw": runner.get("draw"),
                    "weight": runner.get("weight"),
                    "age": runner.get("age"),
                    "official_rating": runner.get("official_rating") or runner.get("or"),
                }
            )
        races.append(
            {
                "course": race.get("course"),
                "time": race.get("time"),
                "race_name": race.get("race_name"),
                "race_type": race.get("race_type"),
                "distance": race.get("distance"),
                "going": race.get("going"),
                "race_class": race.get("race_class"),
                "field_size": race.get("field_size") or len(runners),
                "runners": runners,
            }
        )
    return races


def field_horse_names(races: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    for race in races:
        for runner in race.get("runners") or []:
            name = str(runner.get("horse") or "").strip()
            key = name.lower()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
    return names


def horse_profile_url(name: str) -> str:
    slug = urllib.parse.quote(re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-"))
    return f"https://www.racingpost.com/profile/horse/{slug}/form"


def racecard_url(course: str, date_value: str) -> str:
    slug = urllib.parse.quote(re.sub(r"[^a-z0-9]+", "-", str(course).lower()).strip("-"))
    return f"https://www.racingpost.com/racecards/{slug}/{date_value}"


def count_mentions(text: str, names: Iterable[str]) -> Dict[str, int]:
    lowered = text.lower()
    counts: Dict[str, int] = {}
    for name in names:
        key = str(name or "").strip()
        if not key:
            continue
        counts[key] = lowered.count(key.lower())
    return {key: value for key, value in counts.items() if value}


def build_briefing(date_value: str) -> Dict[str, Any]:
    picks_payload = read_json(REPO_ROOT / "picks.json", {})
    comparison_payload = read_json(DATA / f"race_comparison_{date_value}.json", {})
    official = official_picks_for_comparison(picks_payload)
    race_fields = race_field_summary(comparison_payload)
    names = field_horse_names(race_fields) or [row["horse"] for row in official]
    watched_courses = sorted(
        {str(row.get("course") or "") for row in race_fields if row.get("course")}
        or {str(row.get("course") or "") for row in official if row.get("course")}
    )

    web_targets = [
        ("racingpost_tips", "https://www.racingpost.com/tips/"),
        ("sportinglife_tips", "https://www.sportinglife.com/racing/tips"),
        ("attheraces_tips", "https://www.attheraces.com/tips"),
    ]
    for name in names[:MAX_PROFILE_FETCHES]:
        web_targets.append((f"racingpost_profile_{name}", horse_profile_url(name)))
    for course in watched_courses:
        web_targets.append((f"racingpost_racecard_{course}", racecard_url(course, date_value)))

    web: Dict[str, Any] = {}
    for label, url in web_targets:
        row = fetch_url(url)
        row["field_horse_mentions"] = count_mentions(row.get("text_excerpt", ""), names)
        web[label] = row

    recent_results = []
    for path in recent_result_files(date_value):
        payload = read_json(path, {})
        results = payload.get("results") or {}
        recent_results.append(
            {
                "date": payload.get("date") or path.stem,
                "betType": results.get("betType"),
                "stake": results.get("totalStake"),
                "return": results.get("totalReturn"),
                "profit": results.get("profit"),
                "complete": results.get("complete"),
            }
        )

    ok_sources = [key for key, row in web.items() if row.get("ok")]
    return {
        "date": date_value,
        "generated_at": now_iso(),
        "analysis_only": True,
        "source_files": [
            f"data/race_comparison_{date_value}.json",
            "picks.json (comparison only)",
        ],
        "local": {
            "signal75_official_picks_for_after_decision_comparison_only": official,
            "independent_race_fields": race_fields,
            "recent_skin_in_game_context": recent_results,
        },
        "web": web,
        "data_sources_used": ["local_race_field_without_signal75_scores"] + ok_sources,
        "collection_summary": {
            "web_targets": len(web_targets),
            "web_success": len(ok_sources),
            "web_failed": len(web_targets) - len(ok_sources),
            "official_picks": len(official),
            "races_loaded": len((comparison_payload.get("races") or [])),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch live data for skin_in_game_v1.")
    parser.add_argument("--date", default=default_date())
    args = parser.parse_args()
    briefing = build_briefing(args.date)
    out = DATA / f"skin_in_game_briefing_{args.date}.json"
    write_json(out, briefing)
    summary = briefing["collection_summary"]
    print(f"Skin In Game briefing written: {out.relative_to(REPO_ROOT)}")
    print(f"  official picks: {summary['official_picks']}")
    print(f"  races loaded: {summary['races_loaded']}")
    print(f"  web fetched: {summary['web_success']}/{summary['web_targets']}")
    for key, row in briefing["web"].items():
        status = "OK" if row.get("ok") else "FAIL"
        print(f"  {status} {key}: {row.get('status')} {row.get('url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
