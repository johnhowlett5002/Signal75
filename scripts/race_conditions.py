#!/usr/bin/env python3
"""Collect current race class and going from Sporting Life's daily racecard."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


HEADERS = {"User-Agent": "Mozilla/5.0 Signal75RaceConditions/1.0"}


def clean_course(value: Any) -> str:
    text = re.sub(r"\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+$", "", str(value or "").strip())
    return re.sub(r"\s+", " ", text).strip()


def normalise_course(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", clean_course(value).lower())


def utc_hhmm(value: Any) -> str:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("Europe/London"))
        return parsed.astimezone(timezone.utc).strftime("%H:%M")
    except ValueError:
        match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
        if not match:
            return ""
        local = datetime.now(ZoneInfo("Europe/London")).replace(
            hour=int(match.group(1)), minute=int(match.group(2)), second=0, microsecond=0
        )
        return local.astimezone(timezone.utc).strftime("%H:%M")


def daily_racecard_url(date_text: str) -> str:
    return f"https://www.sportinglife.com/racing/racecards/{date_text}"


def fetch_page(url: str, timeout: int = 10) -> str:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def extract_daily_races(raw: str) -> List[Dict[str, str]]:
    marker = '<script id="__NEXT_DATA__"'
    start = raw.find(marker)
    if start < 0:
        raise ValueError("Sporting Life racecard payload was not found")
    start = raw.find(">", start) + 1
    end = raw.find("</script>", start)
    if start <= 0 or end < 0:
        raise ValueError("Sporting Life racecard payload was incomplete")
    payload = json.loads(raw[start:end])
    meetings = payload.get("props", {}).get("pageProps", {}).get("meetings", [])
    records = []
    for meeting in meetings:
        for race in meeting.get("races") or []:
            race_class = str(race.get("race_class") or "").strip()
            race_id = str((race.get("race_summary_reference") or {}).get("id") or "")
            records.append({
                "date": str(race.get("date") or "")[:10],
                "course_key": normalise_course(race.get("course_name")),
                "time_utc": str(race.get("time") or "")[:5],
                "race_class": f"Class {race_class}" if race_class else "",
                "going": str(race.get("going") or "").strip(),
                "distance": str(race.get("distance") or "").strip(),
                "race_id": race_id,
            })
    return records


def _eligible_races(races: Iterable[Dict[str, Any]], minimum_odds: float, maximum_odds: float):
    for race in races:
        field_size = int(race.get("field_size") or len(race.get("runners") or []))
        has_value_runner = any(
            runner.get("best_back") is not None
            and minimum_odds <= float(runner["best_back"]) <= maximum_odds
            for runner in race.get("runners") or []
        )
        if 8 <= field_size <= 14 and has_value_runner:
            yield race


def enrich_race_conditions(
    races: Iterable[Dict[str, Any]],
    date_text: str,
    minimum_odds: float,
    maximum_odds: float,
    fetcher: Callable[[str], str] = fetch_page,
) -> Dict[str, int]:
    """Enrich plausible selection races; a feed failure leaves evidence unknown."""
    candidates = list(_eligible_races(races, minimum_odds, maximum_odds))
    if not candidates:
        return {"checked": 0, "enriched": 0, "failed": 0}

    source_url = daily_racecard_url(date_text)
    try:
        source_races = extract_daily_races(fetcher(source_url))
    except Exception as error:
        for race in candidates:
            race["raceConditionsError"] = str(error)
        return {"checked": len(candidates), "enriched": 0, "failed": len(candidates)}

    lookup = {
        (record["date"], record["course_key"], record["time_utc"]): record
        for record in source_races
        if record["date"] and record["course_key"] and record["time_utc"]
    }
    enriched = 0
    failed = 0
    for race in candidates:
        key = (
            date_text,
            normalise_course(race.get("venue") or race.get("course")),
            utc_hhmm(race.get("race_time") or race.get("time")),
        )
        conditions = lookup.get(key)
        if not conditions:
            race["raceConditionsError"] = "No matching Sporting Life race was found"
            failed += 1
            continue
        for field in ("race_class", "going", "distance"):
            if conditions.get(field) and not race.get(field):
                race[field] = conditions[field]
        race["raceConditionsSource"] = "SportingLife"
        race["raceConditionsUrl"] = source_url
        race["raceConditionsRaceId"] = conditions.get("race_id", "")
        enriched += 1
    return {"checked": len(candidates), "enriched": enriched, "failed": failed}
