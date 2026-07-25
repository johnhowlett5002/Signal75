#!/usr/bin/env python3
"""Build the local-only, read-only Signal 75 intelligence dashboard feed.

This script only reads existing Signal 75 outputs and writes sanitized copies
to ``dashboard/data``. That folder is ignored by Git on purpose: it must never
be deployed to public GitHub Pages. It does not generate picks, alter scores,
settle results, or change proof.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
import re
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
OUT = REPO_ROOT / "dashboard" / "data"
DB_PATH = DATA / "horse_intelligence" / "signal75_history.sqlite"
FORM_HISTORY_DB = DATA / "horse_intelligence" / "form_history.sqlite"

LEARNING_LABELS = {
    "EVIDENCE_RICHNESS": "Evidence richness",
    "SURFACE_DATA_MISSING": "Surface evidence missing",
    "UNPROVEN_COURSE": "Course evidence missing",
    "UNPROVEN_GOING": "Ground/going evidence missing",
    "UNPROVEN_TRIP": "Distance evidence missing",
    "SAME_COURSE_CLUSTER": "Same-course cluster",
    "POOR_RECENT_FORM": "Poor recent form",
    "SHADOW_BEAT_LIVE_RULE": "Shadow rule beat live",
    "FULL_CRITERIA_MET_AND_PLACED": "Watchlist evidence working",
    "FALSE_CONSENSUS": "Weak/false consensus",
    "THIN_FORM_RECORD": "Thin form record",
    "LARGE_FIELD_CHAOS_RISK": "Large-field chaos risk",
}

LEARNING_EXPLANATIONS = {
    "EVIDENCE_RICHNESS": "Several related evidence gaps are being grouped together: course, going, distance, surface and thin recent form. This prevents one thin-data horse from creating four separate warnings.",
    "SURFACE_DATA_MISSING": "The stored files could not prove the horse on today's racing surface. This is mainly a data-quality caution, not an automatic failure.",
    "UNPROVEN_COURSE": "The database did not show a previous win at today's course. Useful as a caution, but horses can still win at a course for the first time.",
    "UNPROVEN_GOING": "The database did not prove the horse on today's going. This matters most when the ground is unusual, very soft, heavy, or very firm.",
    "UNPROVEN_TRIP": "The database did not show a previous win at today's distance or distance band. It becomes more important when the horse is changing trip.",
    "SAME_COURSE_CLUSTER": "Several selections relied on the same track. If that course has unusual weather, pace, draw, or going, more than one pick can be affected.",
    "POOR_RECENT_FORM": "The recent form string contained enough poor runs to deserve a warning before trusting a high score.",
    "SHADOW_BEAT_LIVE_RULE": "A test version of the rules would have made a better paper call than the live rule for that day.",
    "FULL_CRITERIA_MET_AND_PLACED": "A high-scoring horse outside the official picks won or placed. This is positive evidence that the watchlist is finding useful clues.",
    "FALSE_CONSENSUS": "The headline tipster number was stronger than the trusted independent-source number.",
    "THIN_FORM_RECORD": "There was not enough recent form evidence to fully trust the score.",
    "LARGE_FIELD_CHAOS_RISK": "The race had enough runners to create more traffic, draw, pace, and bad-luck risk.",
}

LEARNING_ACTIONS = {
    "EVIDENCE_RICHNESS": "Review as one confidence factor. Do not treat each missing field as a separate penalty unless the data proves it.",
    "SURFACE_DATA_MISSING": "Collect more evidence. Do not block a horse on this alone.",
    "UNPROVEN_COURSE": "Treat as a caution, not a hard rule.",
    "UNPROVEN_GOING": "Show as a weather/ground warning when conditions matter.",
    "UNPROVEN_TRIP": "Check whether the horse is moving up or down materially in trip.",
    "SAME_COURSE_CLUSTER": "Watch whether same-course groups underperform before making this a live rule.",
    "POOR_RECENT_FORM": "Review before allowing the horse to become official.",
    "SHADOW_BEAT_LIVE_RULE": "Keep testing. Do not promote without approval.",
    "FULL_CRITERIA_MET_AND_PLACED": "Review watchlist winners/placers to see what the official rules missed.",
    "FALSE_CONSENSUS": "Prefer trusted, named, independent sources over copied tip lists.",
    "THIN_FORM_RECORD": "Lower confidence until more recent evidence exists.",
    "LARGE_FIELD_CHAOS_RISK": "Use as a risk note, especially for short prices or crowded handicaps.",
}

LEARNING_TONES = {
    "EVIDENCE_RICHNESS": "warn",
    "FULL_CRITERIA_MET_AND_PLACED": "good",
    "SURFACE_DATA_MISSING": "warn",
    "UNPROVEN_COURSE": "warn",
    "UNPROVEN_GOING": "warn",
    "UNPROVEN_TRIP": "warn",
    "THIN_FORM_RECORD": "warn",
    "POOR_RECENT_FORM": "bad",
    "FALSE_CONSENSUS": "bad",
    "LARGE_FIELD_CHAOS_RISK": "warn",
    "SAME_COURSE_CLUSTER": "warn",
    "SHADOW_BEAT_LIVE_RULE": "info",
}

EVIDENCE_RICHNESS_COMPONENTS = {
    "SURFACE_DATA_MISSING",
    "UNPROVEN_COURSE",
    "UNPROVEN_GOING",
    "UNPROVEN_TRIP",
    "THIN_FORM_RECORD",
}


def read_json(path: Path, default):
    try:
        with path.open() as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def pct_number(value) -> float:
    try:
        return float(str(value or "0").rstrip("%"))
    except (TypeError, ValueError):
        return 0.0


def dated_json_files(folder: Path, prefix: str) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(folder.glob(f"{prefix}_*.json"), reverse=True)


def write_json(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / name
    fd, temp_name = tempfile.mkstemp(dir=OUT, prefix=".dashboard-")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, target)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def copy_dashboard_file(source: Path, destination_name: str) -> bool:
    """Copy a local dashboard source file into dashboard/data when it exists."""
    if not source.exists():
        return False
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, OUT / destination_name)
    return True


def short_result(value) -> str:
    value = str(value or "").upper()
    if value in {"WON", "WIN", "1ST"}:
        return "WON"
    if value in {"PLACED", "PLACE", "2ND", "3RD", "4TH"}:
        return "PLACED"
    if value in {"VOID", "NON_RUNNER", "NR"}:
        return "VOID"
    return "LOST" if value else "PENDING"


def all_selected(picks: dict) -> list[tuple[dict, dict]]:
    pairs = []
    for tab in ("flat", "jumps"):
        for race in picks.get(tab, []) or []:
            for horse in race.get("horses", []) or []:
                pairs.append((race, horse))
    return pairs


def official_rows(picks: dict, comparison: dict, quality_audit: dict | None = None) -> list[dict]:
    comparison_parts = {
        str(runner.get("name", "")).casefold(): runner.get("parts", {})
        for race in comparison.get("races", []) for runner in race.get("runners", [])
    }
    quality_lookup = {}
    if isinstance(quality_audit, dict):
        for row in quality_audit.get("picks", []) or []:
            if not isinstance(row, dict):
                continue
            quality_lookup[
                (
                    normalise_name(row.get("name")),
                    normalise_name(row.get("course")),
                    str(row.get("time") or ""),
                )
            ] = row
    rows = []
    for number, (race, horse) in enumerate(all_selected(picks), 1):
        consensus = horse.get("consensus") or {}
        # The public card uses a compact display structure. The comparison
        # export is the source of truth for the actual four visible parts.
        parts = comparison_parts.get(str(horse.get("name", "")).casefold(), {})
        quality = quality_lookup.get(
            (
                normalise_name(horse.get("name")),
                normalise_name(race.get("course")),
                str(race.get("time") or ""),
            ),
            {},
        )
        rows.append({
            "name": horse.get("name", "Unknown"),
            "course": race.get("course", ""),
            "time": race.get("time", ""),
            "race": f"{race.get('distance', '')} {race.get('race_name', '')}".strip(),
            "odds": horse.get("odds", 0),
            "score": horse.get("signal_score", 0),
            "badge": horse.get("badge", "Signal"),
            "jockey": horse.get("jockey", ""),
            "trainer": horse.get("trainer", ""),
            "tipsters": consensus.get("tip_count", horse.get("tipsters", 0)),
            "consensusLevel": consensus.get("consensus_level", "none"),
            "parts": [
                {"label": "PRICE", "value": parts.get("price", 0), "color": "var(--blue)"},
                {"label": "TIPS", "value": parts.get("tips", 0), "color": "var(--gold)"},
                {"label": "RACE", "value": parts.get("race", 0), "color": "var(--green)"},
                {"label": "FORM", "value": parts.get("form", 0), "color": "var(--green)"},
            ],
            "warnings": [horse.get("formWarning")] if horse.get("formWarning") else [],
            "pickNumber": number,
            "why": horse.get("reason", "Signal 75 selection."),
            "result": short_result(horse.get("result")),
            "qualityAudit": quality,
        })
    return rows


def normalise_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def memory_profiles() -> dict:
    """Read the compact horse-memory profile map without exporting the DB."""
    if not DB_PATH.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT payload_json FROM profiles WHERE profile_type = ? AND profile_key = ?",
                ("horse_memory", "profiles"),
            ).fetchone()
        return json.loads(row[0]) if row else {}
    except (sqlite3.Error, json.JSONDecodeError):
        return {}


def update_match_history(matched: int, total: int, date_text: str) -> list:
    path = OUT / "_match_rate_history.json"
    history = read_json(path, [])
    history = [row for row in history if row.get("date") != date_text]
    history.append({"date": date_text, "matched": matched, "total": total})
    history.sort(key=lambda row: row.get("date", ""))
    history = history[-14:]
    write_json("_match_rate_history.json", history)
    return history


def db_status(match_history: list, profile_count: int) -> dict:
    tables = []
    row_count = 0
    latest_date = None
    if DB_PATH.exists():
        try:
            with sqlite3.connect(str(DB_PATH)) as connection:
                connection.execute("PRAGMA query_only = ON")
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                if "head_to_head" in tables:
                    row_count = connection.execute(
                        "SELECT COUNT(*) FROM head_to_head"
                    ).fetchone()[0]
                    latest_date = connection.execute(
                        "SELECT MAX(date) FROM head_to_head"
                    ).fetchone()[0]
        except Exception:
            pass
    return {
        "profileCount": profile_count,
        "headToHeadRows": row_count,
        "latestHeadToHeadDate": latest_date,
        "dbSizeMb": round(DB_PATH.stat().st_size / 1024 / 1024, 1) if DB_PATH.exists() else 0,
        "tables": sorted(tables),
        "matchHistory": match_history,
        "note": "Local SQLite intelligence database. It is never copied into the dashboard.",
    }


def result_margin_intelligence(date_text: str, limit: int = 8) -> dict:
    """Small dashboard feed showing what the result notes learned from margins."""
    files = [DATA / "combined_learning" / f"combined_learning_{date_text}.json"]
    files.extend(dated_json_files(DATA / "combined_learning", "combined_learning"))
    seen_files: set[Path] = set()
    rows = []
    summary = {
        "with_margin_notes": 0,
        "decisive_winners": 0,
        "well_beaten": 0,
        "heavily_beaten": 0,
    }

    for path in files:
        if path in seen_files or not path.exists():
            continue
        seen_files.add(path)
        payload = read_json(path, {})
        daily_summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        summary["with_margin_notes"] += int(daily_summary.get("with_margin_notes", 0) or 0)
        summary["decisive_winners"] += int(daily_summary.get("won_decisively_count", 0) or 0) + int(daily_summary.get("won_clear_count", 0) or 0)
        summary["well_beaten"] += int(daily_summary.get("well_beaten_count", 0) or 0)
        summary["heavily_beaten"] += int(daily_summary.get("heavily_beaten_count", 0) or 0)

        for record in payload.get("records", []) if isinstance(payload, dict) else []:
            flags = record.get("result_note_flags") if isinstance(record.get("result_note_flags"), list) else []
            distance_summary = record.get("distance_summary") or ""
            finish = record.get("finish_impression") or ""
            if not distance_summary and not finish:
                continue
            if not (
                record.get("won")
                or "WON_DECISIVELY" in flags
                or "WON_CLEAR" in flags
                or "WELL_BEATEN" in flags
                or "HEAVILY_BEATEN" in flags
                or record.get("beat_high_signal_horses")
            ):
                continue
            rows.append({
                "date": record.get("date"),
                "horse": record.get("horse_name"),
                "course": record.get("course"),
                "time": record.get("race_time"),
                "position": record.get("position"),
                "signal_score": record.get("signal_score"),
                "selection_type": record.get("selection_type"),
                "distance_summary": distance_summary,
                "finish_impression": finish,
                "winning_margin_lengths": record.get("winning_margin_lengths"),
                "distance_from_winner_lengths": record.get("distance_from_winner_lengths"),
                "race_comment": record.get("race_comment"),
                "flags": flags,
                "beat_high_signal_horses": record.get("beat_high_signal_horses") or [],
            })
        if len(rows) >= limit:
            break

    rows.sort(key=lambda row: (row.get("date") or "", row.get("time") or "", row.get("horse") or ""), reverse=True)
    return {
        "summary": summary,
        "records": rows[:limit],
        "note": "Learning-only view of winning margins and beaten distances. This does not alter picks or proof.",
    }


def field_graph_intelligence(date_text: str, limit: int = 12) -> dict:
    """Small dashboard feed for the horse-vs-horse relationship graph."""
    preferred = DATA / "horse_intelligence" / f"field_graph_{date_text}.json"
    files = [preferred]
    files.extend(
        path
        for path in dated_json_files(DATA / "horse_intelligence", "field_graph")
        if re.search(r"field_graph_\d{4}-\d{2}-\d{2}\.json$", path.name)
    )
    seen_files: set[Path] = set()
    payload = {}
    source_path = None
    for path in files:
        if path in seen_files or not path.exists():
            continue
        seen_files.add(path)
        payload = read_json(path, {})
        if payload:
            source_path = path
            break

    runners = payload.get("currentRunners") or []
    strong = [row for row in runners if row.get("relationship_signal") == "strong_relationship_edge"]
    positive = [row for row in runners if row.get("relationship_signal") == "positive_relationship_edge"]
    warnings = [row for row in runners if row.get("relationship_signal") == "relationship_warning"]
    watched = [row for row in runners if row.get("relationship_signal") == "watch_relationship"]

    def compact(row: dict) -> dict:
        return {
            "horse": row.get("horse_name"),
            "course": row.get("course"),
            "time": row.get("race_time"),
            "race": row.get("race_name"),
            "score": row.get("relationship_score", 0),
            "signal": row.get("relationship_signal"),
            "directScore": row.get("direct_edge_score", 0),
            "indirectScore": row.get("indirect_edge_score", 0),
            "negativeScore": row.get("negative_edge_score", 0),
            "directRivals": [item.get("rival") for item in (row.get("direct_edges") or [])[:3]],
            "warningRivals": [item.get("rival") for item in (row.get("negative_edges") or [])[:3]],
            "chainCount": len(row.get("indirect_edges") or []),
            "label": row.get("public_label") or "No stored horse-vs-horse edge against today's field yet.",
            "use": row.get("recommended_use") or "Learning evidence only.",
        }

    top_rows = sorted(strong + positive + watched, key=lambda row: (-(row.get("relationship_score") or 0), row.get("horse_name") or ""))[:limit]
    warning_rows = sorted(warnings, key=lambda row: (row.get("relationship_score") or 0, row.get("horse_name") or ""))[:limit]
    return {
        "date": payload.get("date") or date_text,
        "source": str(source_path.relative_to(REPO_ROOT)) if source_path else "",
        "raceCount": payload.get("raceCount", 0),
        "runnerCount": payload.get("runnerCount", 0),
        "edgeCount": payload.get("edgeCount", 0),
        "signalCounts": payload.get("signalCounts", {}),
        "topEdges": [compact(row) for row in top_rows],
        "warnings": [compact(row) for row in warning_rows],
        "note": "Horse relationship graph: who has beaten today's rivals before, who has lost to them, and where an indirect chain exists. Learning/support evidence only.",
    }


def form_pattern_from_string(value) -> str:
    markers = []
    for char in str(value or ""):
        if char.isdigit():
            markers.append(char if char in "123456789" else "0")
    return "".join(markers[-4:]) if len(markers) >= 4 else ""


def rich_form_feed(date_text: str, comparison: dict) -> dict:
    """Compact dashboard feed from form_history.sqlite.

    The browser never reads the large SQLite database directly. This export
    gives the dashboard only the current runners' form-pattern evidence.
    Display only: no scoring, proof, settlement or pick-generation impact.
    """
    runners = []
    for race in comparison.get("races", []) or []:
        if not isinstance(race, dict):
            continue
        for runner in race.get("runners", []) or []:
            if not isinstance(runner, dict):
                continue
            runners.append({
                "name": runner.get("name") or runner.get("horse_name"),
                "course": race.get("course"),
                "time": race.get("time"),
                "status": runner.get("status"),
                "score": runner.get("score"),
                "form": runner.get("form"),
                "horseKey": normalise_name(runner.get("name") or runner.get("horse_name")),
            })

    if not FORM_HISTORY_DB.exists():
        return {
            "date": date_text,
            "available": False,
            "runnerCount": len(runners),
            "matchedCount": 0,
            "rows": [],
            "note": "Rich form database is not available on this Mac yet.",
        }

    rows = []
    matched = 0
    try:
        with sqlite3.connect(str(FORM_HISTORY_DB)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            for runner in runners:
                horse_key = runner.get("horseKey")
                pattern = form_pattern_from_string(runner.get("form"))
                stat = None
                latest = None
                if pattern:
                    stat = connection.execute(
                        """
                        SELECT starts, wins, places, win_rate, place_rate
                        FROM form_pattern_stats
                        WHERE pattern_length = 4 AND pattern = ?
                        """,
                        (pattern,),
                    ).fetchone()
                if horse_key:
                    latest = connection.execute(
                        """
                        SELECT date, course, distance, going, position, runners,
                               sp, rpr, topspeed, official_rating
                        FROM form_results
                        WHERE horse_key = ?
                        ORDER BY date DESC, race_id DESC
                        LIMIT 1
                        """,
                        (horse_key,),
                    ).fetchone()
                if stat or latest:
                    matched += 1
                row = {
                    "name": runner.get("name"),
                    "course": runner.get("course"),
                    "time": runner.get("time"),
                    "status": runner.get("status"),
                    "score": runner.get("score"),
                    "form": runner.get("form"),
                    "pattern": pattern,
                    "matched": bool(stat or latest),
                    "scoringImpact": "none",
                }
                if stat:
                    starts = int(stat["starts"] or 0)
                    wins = int(stat["wins"] or 0)
                    places = int(stat["places"] or 0)
                    win_rate = round(float(stat["win_rate"] or 0) * 100, 1)
                    place_rate = round(float(stat["place_rate"] or 0) * 100, 1)
                    if starts >= 50 and win_rate < 8:
                        tone = "poor"
                        label = "Poor similar-form record"
                    elif starts >= 50 and win_rate >= 16:
                        tone = "good"
                        label = "Strong similar-form record"
                    else:
                        tone = "neutral"
                        label = "Similar-form record"
                    row["patternStats"] = {
                        "starts": starts,
                        "wins": wins,
                        "places": places,
                        "winRate": win_rate,
                        "placeRate": place_rate,
                        "tone": tone,
                        "label": label,
                        "plainEnglish": (
                            f"Horses with recent form pattern {pattern} have won "
                            f"{win_rate}% and placed {place_rate}% next time "
                            f"from {starts:,} archive examples."
                        ),
                    }
                if latest:
                    row["latestArchiveRun"] = {
                        "date": latest["date"],
                        "course": latest["course"],
                        "distance": latest["distance"],
                        "going": latest["going"],
                        "position": latest["position"],
                        "runners": latest["runners"],
                        "sp": latest["sp"],
                        "rpr": latest["rpr"],
                        "topspeed": latest["topspeed"],
                        "officialRating": latest["official_rating"],
                    }
                rows.append(row)
    except sqlite3.Error as exc:
        return {
            "date": date_text,
            "available": False,
            "runnerCount": len(runners),
            "matchedCount": 0,
            "rows": [],
            "error": str(exc),
            "note": "Rich form database could not be queried. Dashboard display only.",
        }

    return {
        "date": date_text,
        "available": True,
        "runnerCount": len(runners),
        "matchedCount": matched,
        "matchRate": round((matched / len(runners)) * 100, 1) if runners else 0,
        "database": "data/horse_intelligence/form_history.sqlite",
        "rows": rows,
        "note": "Rich form evidence from 12-year form archive. Dashboard display only; no live scoring impact.",
    }


def post_race_review_feed(date_text: str, picks: dict) -> dict:
    """Join settled picks with race-memory evidence for dashboard review only."""
    daily = read_json(DATA / f"{date_text}.json", {})
    results = daily.get("results", {}) if isinstance(daily.get("results"), dict) else {}
    notes = read_json(DATA / "horse_intelligence" / f"race_result_notes_{date_text}.json", {})
    field_graph = read_json(DATA / "horse_intelligence" / f"field_graph_{date_text}.json", {})

    graph_by_horse_market = {}
    graph_by_market = {}
    for row in field_graph.get("currentRunners", []) or []:
        if not isinstance(row, dict):
            continue
        market_id = str(row.get("market_id") or "")
        horse_key = normalise_name(row.get("horse_name") or row.get("horse"))
        if market_id and horse_key:
            graph_by_horse_market[(market_id, horse_key)] = row
            graph_by_market.setdefault(market_id, {})[horse_key] = row

    winner_by_market = {}
    for row in notes.get("records", []) or []:
        if not isinstance(row, dict):
            continue
        market_id = str(row.get("market_id") or "")
        try:
            position = int(row.get("position") or 0)
        except (TypeError, ValueError):
            position = 0
        if market_id and position == 1:
            winner_by_market[market_id] = row

    race_by_pick = {}
    for section in ("flat", "jumps"):
        for race in daily.get(section, []) or picks.get(section, []) or []:
            if not isinstance(race, dict):
                continue
            market_id = str(race.get("market_id") or "")
            for horse in race.get("horses", []) or []:
                if not isinstance(horse, dict):
                    continue
                key = (
                    normalise_name(horse.get("name")),
                    normalise_name(race.get("course")),
                    str(race.get("time") or ""),
                )
                race_by_pick[key] = {
                    "section": section,
                    "market_id": market_id,
                    "course": race.get("course", ""),
                    "time": race.get("time", ""),
                    "race": race.get("distance") or race.get("race_name") or "",
                }

    def result_rows(section: str) -> list[dict]:
        rows = results.get(section, [])
        return rows if isinstance(rows, list) else []

    def relationship_against_winner(pick_graph: dict | None, winner_name: str) -> tuple[str, list[dict]]:
        if not pick_graph or not winner_name:
            return "No direct head-to-head link to the winner was found in the dashboard feed.", []
        winner_key = normalise_name(winner_name)
        evidence = []
        for edge in pick_graph.get("direct_edges", []) or []:
            if normalise_name(edge.get("rival")) == winner_key:
                meetings = int(edge.get("meetings") or 1)
                evidence.append({
                    "tone": "good",
                    "text": f"Our pick had beaten {winner_name} {meetings} time{'s' if meetings != 1 else ''} before.",
                    "notes": edge.get("notes", [])[:3],
                })
        for edge in pick_graph.get("negative_edges", []) or []:
            if normalise_name(edge.get("rival")) == winner_key:
                meetings = int(edge.get("meetings") or 1)
                evidence.append({
                    "tone": "warn",
                    "text": f"The winner had beaten our pick {meetings} time{'s' if meetings != 1 else ''} before.",
                    "notes": edge.get("notes", [])[:3],
                })
        if evidence:
            return evidence[0]["text"], evidence
        return "No direct head-to-head link to the winner was found in the dashboard feed.", []

    def warning_edges(pick_graph: dict | None) -> list[dict]:
        if not pick_graph:
            return []
        rows = []
        for edge in (pick_graph.get("negative_edges", []) or [])[:4]:
            rival = edge.get("rival")
            if not rival:
                continue
            meetings = int(edge.get("meetings") or 1)
            rows.append({
                "rival": rival,
                "meetings": meetings,
                "text": f"{rival} had beaten this horse {meetings} time{'s' if meetings != 1 else ''} before.",
                "notes": edge.get("notes", [])[:3],
            })
        return rows

    rows = []
    for section in ("flat", "jumps"):
        for result in result_rows(section):
            if not isinstance(result, dict):
                continue
            name = result.get("name", "")
            result_key = normalise_name(name)
            race = race_by_pick.get((result_key, "", ""), {})
            if not race:
                for key, value in race_by_pick.items():
                    if key[0] == result_key:
                        race = value
                        break
            market_id = str(race.get("market_id") or "")
            pick_graph = graph_by_horse_market.get((market_id, result_key))
            winner_record = winner_by_market.get(market_id)
            winner_name = winner_record.get("horse_name") if winner_record else None
            result_text = str(result.get("result") or "").upper()
            if result_text == "WON":
                winner_name = name
            relationship_summary, winner_evidence = relationship_against_winner(pick_graph, winner_name or "")
            rows.append({
                "name": name,
                "section": section,
                "course": race.get("course", ""),
                "time": race.get("time", ""),
                "marketId": market_id,
                "result": result_text or "PENDING",
                "position": result.get("position"),
                "odds": result.get("odds"),
                "return": result.get("totalReturn"),
                "winner": winner_name,
                "winnerKnown": bool(winner_name),
                "relationshipSummary": (
                    "Our pick won, so the race-memory winner check passed."
                    if result_text == "WON"
                    else relationship_summary
                ),
                "winnerEvidence": winner_evidence,
                "warningEdges": warning_edges(pick_graph),
                "scoringImpact": "none",
            })

    return {
        "date": date_text,
        "source": "data/{date}.json results + race_result_notes + field_graph",
        "picks": rows,
        "note": "Post-race dashboard review only. It explains what happened after the race and does not change picks, proof, scoring or settlement.",
    }


def latest_training_logs(limit: int = 14) -> list[dict]:
    logs: list[tuple[str, dict]] = []
    folder = DATA / "continuous_training"
    for path in sorted(folder.glob("training_log_*.json")):
        payload = read_json(path, {})
        if not isinstance(payload, dict):
            continue
        date = str(payload.get("date") or path.stem.replace("training_log_", ""))
        logs.append((date, payload))
    return [payload for _, payload in logs[-limit:]]


def learning_result_group(value) -> str:
    value = str(value or "").upper()
    if value in {"WON", "PLACED"}:
        return "placed"
    if value == "LOST":
        return "lost"
    return "unknown"


def learning_example_text(row: dict) -> str:
    details = []
    if row.get("score") not in (None, ""):
        details.append(f"score {row.get('score')}")
    if row.get("bsp") not in (None, ""):
        details.append(f"BSP {row.get('bsp')}")
    if row.get("trusted_tipsters") not in (None, "") and row.get("tipsters") not in (None, ""):
        details.append(f"{row.get('trusted_tipsters')}/{row.get('tipsters')} trusted tipsters")
    return ", ".join(details)


def learning_evidence_feed(learning: dict, alerts: dict) -> dict:
    logs = latest_training_logs()
    examples: dict[str, list[dict]] = {}
    for log in logs:
        date = str(log.get("date") or "")
        for horse in log.get("horses") or []:
            if not isinstance(horse, dict):
                continue
            for finding in (horse.get("findings") or []) + (horse.get("positive_findings") or []):
                if not isinstance(finding, dict):
                    continue
                key = str(finding.get("finding") or finding.get("check") or "")
                if not key:
                    continue
                examples.setdefault(key, []).append({
                    "date": date,
                    "horse": horse.get("horse"),
                    "type": horse.get("type"),
                    "result": horse.get("result"),
                    "resultGroup": learning_result_group(horse.get("result")),
                    "position": horse.get("position"),
                    "course": horse.get("course"),
                    "time": horse.get("time"),
                    "score": horse.get("signal_score"),
                    "bsp": horse.get("bsp"),
                    "tipsters": horse.get("tipster_count"),
                    "trusted_tipsters": horse.get("trusted_tipster_count"),
                    "evidence": finding.get("evidence") or finding.get("note") or "Evidence stored, but no plain note was available.",
                    "details": learning_example_text({
                        "score": horse.get("signal_score"),
                        "bsp": horse.get("bsp"),
                        "trusted_tipsters": horse.get("trusted_tipster_count"),
                        "tipsters": horse.get("tipster_count"),
                    }),
                })

    finding_totals = learning.get("finding_counts") or learning.get("finding_totals") or {}
    if finding_totals.get("EVIDENCE_RICHNESS"):
        richness_examples = []
        for component in EVIDENCE_RICHNESS_COMPONENTS:
            richness_examples.extend(examples.get(component) or [])
        richness_examples.sort(key=lambda row: (row.get("date") or "", row.get("horse") or ""))
        examples["EVIDENCE_RICHNESS"] = richness_examples[-12:]
    alert_map = {item.get("finding"): item for item in alerts.get("items", []) if isinstance(item, dict)}
    items = []
    for code, count in sorted(finding_totals.items(), key=lambda row: (-int(row[1] or 0), str(row[0])))[:12]:
        if finding_totals.get("EVIDENCE_RICHNESS") and code in EVIDENCE_RICHNESS_COMPONENTS:
            continue
        rows = examples.get(code) or []
        known = [row for row in rows if row.get("resultGroup") != "unknown"]
        placed = [row for row in known if row.get("resultGroup") == "placed"]
        lost = [row for row in known if row.get("resultGroup") == "lost"]
        tone = LEARNING_TONES.get(code)
        if not tone:
            tone = "bad" if lost and len(lost) >= max(2, len(placed) * 3) else "warn"
        items.append({
            "code": code,
            "label": LEARNING_LABELS.get(code, code.replace("_", " ").title()),
            "count": int(count or 0),
            "threshold": alert_map.get(code, {}).get("threshold", 0),
            "tone": tone,
            "plainMeaning": LEARNING_EXPLANATIONS.get(code, "Signal 75 has seen this pattern and is storing it for review."),
            "currentAction": LEARNING_ACTIONS.get(code, "Keep collecting evidence before making changes."),
            "evidenceSplit": {
                "placed": len(placed),
                "lost": len(lost),
                "unknown": max(0, len(rows) - len(known)),
                "sample": len(rows),
            },
            "examples": rows[-3:],
        })

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "daysAnalysed": learning.get("days_analysed", 0),
        "newFormatDays": len([d for d in learning.get("analysed_dates", []) if str(d) >= "2026-06-14"]),
        "officialPlaceRate": pct_number(learning.get("official_place_rate")),
        "watchlistPlaceRate": pct_number(learning.get("watchlist_place_rate")),
        "items": items,
        "evidenceRichness": learning.get("evidence_richness", {}),
        "summary": [
            "Counts alone are not enough. Each item below shows the horses behind the warning.",
            "Green means useful positive evidence. Amber means watch. Red means repeated concern.",
            "This dashboard is learning-only. It does not alter picks, proof, settlement, or scoring.",
        ],
    }


def truthy_context(value) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str) and value.lower() in {"unknown", "none", "null"}:
        return False
    return True


def latest_combined_records(date_text: str) -> tuple[list[dict], dict]:
    """Return the current day's combined learning records, falling back to latest."""
    files = [DATA / "combined_learning" / f"combined_learning_{date_text}.json"]
    files.extend(dated_json_files(DATA / "combined_learning", "combined_learning"))
    seen: set[Path] = set()
    for path in files:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        payload = read_json(path, {})
        if isinstance(payload, dict) and payload.get("records"):
            return payload.get("records", []), payload.get("summary", {})
    return [], {}


def capture_intelligence_feed(date_text: str, limit: int = 18) -> dict:
    """Expose what the learning layer captured, in plain dashboard form."""
    records, summary = latest_combined_records(date_text)

    def has_rating(row: dict) -> bool:
        return truthy_context(row.get("field_top_official_rating")) or truthy_context(row.get("official_rating_memory")) or truthy_context(row.get("official_rating_result_note"))

    categories = [
        {
            "key": "race_class",
            "label": "Race class / standard",
            "count": int(summary.get("with_race_class_context", 0) or sum(1 for row in records if truthy_context(row.get("race_class_label")))),
            "plain": "Records whether this was a Group, Listed, Handicap, Novice or other race, plus whether the horse is up or down in class.",
            "why": "Stops us treating a strong run in a poor race the same as a strong run in a better race.",
        },
        {
            "key": "distance",
            "label": "Distance and trip",
            "count": int(summary.get("with_distance_context", 0) or sum(1 for row in records if truthy_context(row.get("distance_band")))),
            "plain": "Stores the distance in furlongs and the broad distance band such as sprint, mile, middle or staying.",
            "why": "Helps compare like with like instead of assuming a horse is equally suited at every trip.",
        },
        {
            "key": "draw",
            "label": "Draw position",
            "count": int(summary.get("with_draw_context", 0) or sum(1 for row in records if truthy_context(row.get("draw_bucket")))),
            "plain": "Stores low, middle or high draw where the runner data provides a stall.",
            "why": "Useful on courses where a draw bias can change the race shape.",
        },
        {
            "key": "market",
            "label": "Market confidence",
            "count": int(summary.get("with_market_share_context", 0) or sum(1 for row in records if truthy_context(row.get("market_confidence_label")))),
            "plain": "Stores price rank, implied chance and traded-market share where available.",
            "why": "Shows whether the market was quietly backing the horse or ignoring it.",
        },
        {
            "key": "field_rating",
            "label": "Field strength",
            "count": int(summary.get("with_field_rating_context", 0) or sum(1 for row in records if has_rating(row))),
            "plain": "Stores official-rating context for the field and where the horse sits against the field top and average.",
            "why": "Gives a stronger view of whether the horse is well treated or outclassed.",
        },
        {
            "key": "result_notes",
            "label": "Result notes and excuses",
            "count": int(summary.get("with_result_notes", 0) or sum(1 for row in records if truthy_context(row.get("race_comment")) or truthy_context(row.get("excuse_flags")))),
            "plain": "Stores pace, finishing comment, excuse flags, win style, price movement and closing-line value after the race.",
            "why": "Prevents the learning layer from blindly punishing a horse that had a genuine excuse.",
        },
    ]

    rows = []
    for row in records:
        chips = []
        if truthy_context(row.get("race_class_label")):
            move = row.get("class_movement")
            chips.append(f"Class: {row.get('race_class_label')}" + (f" / {move.replace('_', ' ')}" if move else ""))
        if truthy_context(row.get("distance_band")):
            dist = row.get("distance_furlongs")
            chips.append(f"Trip: {dist}f {row.get('distance_band')}" if dist else f"Trip: {row.get('distance_band')}")
        if truthy_context(row.get("draw_bucket")):
            chips.append(f"Draw: {row.get('draw_bucket')}")
        if truthy_context(row.get("market_confidence_label")):
            ratio = row.get("market_share_ratio")
            chips.append(f"Market: {row.get('market_confidence_label').replace('_', ' ')}" + (f" x{ratio}" if ratio not in (None, "") else ""))
        if has_rating(row):
            top = row.get("field_top_official_rating")
            avg = row.get("field_avg_official_rating")
            chips.append(f"Ratings: top {top}, avg {avg}" if top or avg else "Ratings captured")
        if truthy_context(row.get("excuse_flags")):
            chips.append("Excuses: " + ", ".join(row.get("excuse_flags", [])[:2]))
        if truthy_context(row.get("price_movement")):
            chips.append(f"Price move: {row.get('price_movement')}")
        if not chips:
            continue
        notes = []
        if truthy_context(row.get("recent_class_path")):
            notes.append(f"{len(row.get('recent_class_path') or [])} previous class records found")
        if int(row.get("recent_stronger_races_count") or 0) > 0:
            notes.append(f"{row.get('recent_stronger_races_count')} recent stronger-race example(s)")
        if truthy_context(row.get("distance_summary")):
            notes.append(row.get("distance_summary"))
        if truthy_context(row.get("finish_impression")):
            notes.append(row.get("finish_impression"))
        if truthy_context(row.get("race_comment")):
            notes.append(row.get("race_comment"))
        rows.append({
            "horse": row.get("horse_name") or row.get("horse") or "Unknown",
            "date": row.get("date") or date_text,
            "course": row.get("course") or row.get("venue") or "",
            "time": row.get("race_time") or row.get("time") or "",
            "score": row.get("signal_score") or row.get("score"),
            "selection_type": row.get("selection_type") or row.get("view") or "runner",
            "chips": chips[:7],
            "note": ". ".join(notes[:3]) or "Context captured for future comparison.",
        })
        if len(rows) >= limit:
            break

    return {
        "date": date_text,
        "recordCount": len(records),
        "categories": categories,
        "examples": rows,
        "plainSummary": "This is the transparent list of the learning fields Signal 75 is storing. These fields are learning/evidence only unless a separate approved rule uses them.",
    }


def challenger_lab_feed() -> dict:
    summary = read_json(DATA / "challenger_lab" / "challenger_summary.json", {})
    challengers = []
    for row in summary.get("pre_race_challengers", []) or []:
        if not isinstance(row, dict):
            continue
        challengers.append({
            "id": row.get("id", ""),
            "name": row.get("name") or str(row.get("id", "Challenger")).replace("_", " ").title(),
            "status": row.get("promotion_status", "COLLECTING"),
            "daysTested": row.get("days_tested", 0),
            "settledDays": row.get("settled_days", 0),
            "totalPicks": row.get("total_picks", 0),
            "stake": row.get("total_stake", 0),
            "return": row.get("total_return", 0),
            "profit": row.get("total_profit", 0),
            "roi": row.get("roi", 0),
            "deltaVsLiveProfit": row.get("delta_vs_live_profit", 0),
            "deltaVsLiveRoi": row.get("delta_vs_live_roi", 0),
            "sampleWarning": row.get("sample_warning", ""),
            "winningDays": row.get("winning_days", 0),
            "losingDays": row.get("losing_days", 0),
            "overlapWithLiveAvgPct": row.get("overlap_with_live_avg_pct", 0),
            "oneBigWinnerDistorting": bool(row.get("one_big_winner_distorting")),
            "criteria": row.get("promotion_criteria", {}),
            "warningCases": row.get("warning_cases", 0),
            "warningsValidated": row.get("warnings_validated", 0),
            "accuracy": row.get("accuracy", 0),
            "latestCases": row.get("latest_cases", []) or [],
            "plainSummary": row.get("plain_summary", ""),
        })

    live = summary.get("live", {}) if isinstance(summary.get("live"), dict) else {}
    return {
        "available": bool(summary),
        "generatedAt": summary.get("generated_at", ""),
        "dateRange": summary.get("date_range", {}),
        "live": {
            "days": live.get("days", 0),
            "bettingDays": live.get("betting_days", 0),
            "stake": live.get("total_stake", 0),
            "return": live.get("total_return", 0),
            "profit": live.get("total_profit", 0),
            "roi": live.get("roi", 0),
        },
        "challengers": challengers,
        "fieldAwareVsOldOverlay": summary.get("field_aware_vs_old_overlay", {}),
        "promotionCandidates": summary.get("promotion_candidates", []) or [],
        "futureChallengersPlanned": summary.get("future_challengers_planned", []) or [],
        "safety": summary.get("safety", {}),
        "plainSummary": "Challenger Lab tests possible future rules against real days without changing live picks, proof or public results. A rule can only be considered after enough settled days, enough picks, a positive result versus live, and John approval.",
    }


def rich_form_outcome_feed(date_text: str) -> dict:
    outcome = read_json(DATA / "challenger_lab" / f"rich_form_outcomes_{date_text}.json", {})
    summary = outcome.get("summary", {}) if isinstance(outcome, dict) else {}
    cases = []
    for case in (outcome.get("cases", []) if isinstance(outcome, dict) else [])[:8]:
        if not isinstance(case, dict):
            continue
        pick = case.get("ourPick") or {}
        rival = case.get("rival") or {}
        cases.append({
            "verdict": case.get("verdict"),
            "plainEnglish": case.get("plainEnglish", ""),
            "course": case.get("course", ""),
            "time": case.get("time", ""),
            "ourPick": {
                "horse": pick.get("horse"),
                "result": pick.get("result"),
                "position": pick.get("position"),
                "form": pick.get("form"),
                "pattern": pick.get("formPattern"),
                "winRate": (pick.get("formStats") or {}).get("winRate"),
                "placeRate": (pick.get("formStats") or {}).get("placeRate"),
                "starts": (pick.get("formStats") or {}).get("starts"),
            },
            "rival": {
                "horse": rival.get("horse") if rival else None,
                "result": rival.get("result") if rival else None,
                "position": rival.get("position") if rival else None,
                "form": rival.get("form") if rival else None,
                "pattern": rival.get("formPattern") if rival else None,
                "winRate": ((rival.get("formStats") or {}).get("winRate") if rival else None),
                "placeRate": ((rival.get("formStats") or {}).get("placeRate") if rival else None),
                "starts": ((rival.get("formStats") or {}).get("starts") if rival else None),
                "weightLbs": rival.get("weightLbs") if rival else None,
                "distance": rival.get("distance") if rival else None,
                "going": rival.get("going") if rival else None,
                "draw": rival.get("draw") if rival else None,
                "officialRating": rival.get("officialRating") if rival else None,
                "jockey": rival.get("jockey") if rival else None,
                "trainer": rival.get("trainer") if rival else None,
            },
            "missingFields": case.get("missingFields", []) or [],
        })
    return {
        "available": bool(outcome),
        "date": date_text,
        "generatedAt": outcome.get("generated_at", "") if isinstance(outcome, dict) else "",
        "summary": summary,
        "cases": cases,
        "plainSummary": summary.get(
            "plainEnglish",
            "Checks whether stronger rich-form evidence pointed to the horse that beat our pick.",
        ),
        "safety": outcome.get("safety", {}) if isinstance(outcome, dict) else {},
    }


def build(date_text: str | None = None) -> None:
    date_text = date_text or datetime.now().strftime("%Y-%m-%d")
    picks = read_json(REPO_ROOT / "picks.json", {})
    performance = read_json(REPO_ROOT / "performance.json", {})
    comparison = read_json(DATA / f"race_comparison_{date_text}.json", {"races": []})
    consensus = read_json(DATA / f"consensus_overlay_{date_text}.json", {})
    script_overlay = read_json(DATA / f"script_tipster_overlay_{date_text}.json", {})
    learning = read_json(DATA / "continuous_training" / "cumulative_findings.json", {})
    alerts = read_json(DATA / "continuous_training" / "pattern_alerts.json", {"items": []})
    learning_evidence = learning_evidence_feed(learning, alerts)
    has_evidence_richness = any(
        item.get("finding") == "EVIDENCE_RICHNESS"
        for item in alerts.get("items", [])
        if isinstance(item, dict)
    )
    visible_alerts = []
    for item in alerts.get("items", []):
        if not isinstance(item, dict):
            continue
        if has_evidence_richness and item.get("finding") in EVIDENCE_RICHNESS_COMPONENTS:
            continue
        visible_alerts.append(item)
    cost_control = read_json(DATA / "api_cost_control.json", {})
    diagnostics = read_json(DATA / "selection_diagnostics" / f"selection_diagnostics_{date_text}.json", {})
    quality_audit = read_json(DATA / f"pick_quality_audit_{date_text}.json", {})
    high_confidence_misses = read_json(DATA / "diagnosis" / f"high_confidence_misses_{date_text}.json", {})
    high_confidence_master = read_json(DATA / "diagnosis" / "high_confidence_miss_master.json", {})
    margin_intel = result_margin_intelligence(date_text)
    field_graph = field_graph_intelligence(date_text)
    rich_form = rich_form_feed(date_text, comparison)
    rich_form_outcome = rich_form_outcome_feed(date_text)
    capture_intel = capture_intelligence_feed(date_text)
    challenger_lab = challenger_lab_feed()
    selected = official_rows(picks, comparison, quality_audit)
    diagnostics_by_horse = {
        normalise_name(item.get("horse")): item
        for item in diagnostics.get("top_candidates", [])
    }
    runners = [runner for race in comparison.get("races", []) for runner in race.get("runners", [])]
    profiles = memory_profiles()
    matched_profiles = [profiles[normalise_name(runner.get("name"))] for runner in runners if normalise_name(runner.get("name")) in profiles]
    matched_count = len(matched_profiles)
    match_history = update_match_history(matched_count, len(runners), date_text)
    visible_memory = {
        profile.get("normalised_name") or normalise_name(profile.get("horse_name")): {
            "name": profile.get("horse_name", "Unknown"),
            "runsLogged": profile.get("runs_logged", 0), "knownWins": profile.get("known_wins", 0),
            "knownPlaces": profile.get("known_places", 0), "knownLosses": profile.get("known_losses", 0),
            "lastSeen": profile.get("last_seen", "Unknown"), "lastCourse": profile.get("last_course", "Unknown"),
            "insight": profile.get("last_insight", "No stored insight yet."),
            "confidence": "High" if profile.get("runs_logged", 0) >= 5 else "Medium" if profile.get("runs_logged", 0) >= 2 else "Low",
        }
        for profile in matched_profiles[:8]
    }
    warnings_count = sum(1 for runner in runners if runner.get("warnings"))

    write_json("dashboard_ready.json", {
        "local_only": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": picks.get("date", date_text),
        "message": "Local read-only dashboard feed. Never publish this folder.",
    })
    write_json("status.json", {
        "date": picks.get("date", date_text), "picksGenerated": bool(picks.get("generatedAt")),
        "picksTime": str(picks.get("generatedAt", ""))[11:16] or "not available",
        "mode": picks.get("mode", "unknown"), "officialCount": len(selected),
        "watchlistCount": len(picks.get("topRated", []) or []),
        "resultsSettled": "complete" if performance.get("updatedAt") == picks.get("date") else "pending",
        "resultsNote": "from latest published results", "learningRefreshed": bool(learning.get("last_updated")),
        "learningTime": str(learning.get("last_updated", ""))[11:16] or "scheduled",
        "anthropicUsedToday": bool((consensus.get("api_cost_control") or {}).get("anthropic_used")),
        "apiCallsAvoided": (consensus.get("api_cost_control") or {}).get("estimated_api_call_count_avoided", 0),
        "proofUnchanged": True,
    })
    write_json("officialPicks.json", selected)
    if quality_audit:
        write_json("pickQualityAudit.json", quality_audit)
    copy_dashboard_file(DATA / f"pick_quality_audit_{date_text}.json", "pickQualityAudit.json")
    watchlist_rows = []
    for horse in picks.get("topRated", []) or []:
        diagnostic = diagnostics_by_horse.get(normalise_name(horse.get("name")), {})
        watchlist_rows.append({
            "name": horse.get("name", "Unknown"), "course": horse.get("venue", ""), "time": horse.get("time", ""),
            "odds": horse.get("odds", 0), "score": horse.get("signal_score", 0),
            "reason": "DAILY_EXTRA_WATCHLIST",
            "reasonText": horse.get("reason", "Strong signal, not an official pick."),
            "officialGate": diagnostic.get("current_gate", "NOT_CHECKED"),
            "officialRejectionReasons": diagnostic.get("current_rejection_reasons", []),
            "publishedList": "Daily extra watchlist",
        })
    write_json("watchlist.json", watchlist_rows)
    official_source_names = [horse.get("name", "Unknown") for _, horse in all_selected(picks)]
    watchlist_source_names = [horse.get("name", "Unknown") for horse in picks.get("topRated", []) or []]
    verified = (
        official_source_names == [row["name"] for row in selected]
        and watchlist_source_names == [row["name"] for row in watchlist_rows]
    )
    write_json("selectionAudit.json", {
        "date": picks.get("date", date_text),
        "mode": picks.get("mode", "unknown"),
        "verified": verified,
        "official": {"count": len(selected), "names": [row["name"] for row in selected], "source": "picks.json flat + jumps"},
        "daily_watchlist": {"count": len(watchlist_rows), "names": [row["name"] for row in watchlist_rows], "source": "picks.json topRated"},
        "flat_radar": {"count": len(picks.get("topRatedFlat", []) or []), "names": [row.get("name") for row in picks.get("topRatedFlat", []) or []], "source": "picks.json topRatedFlat"},
        "jumps_radar": {"count": len(picks.get("topRatedJumps", []) or []), "names": [row.get("name") for row in picks.get("topRatedJumps", []) or []], "source": "picks.json topRatedJumps"},
        "note": "The dashboard does not invent a selection list. Each group is shown separately from its published picks.json source.",
    })
    write_json("raceView.json", {"races": comparison.get("races", [])})
    write_json("postRaceReview.json", post_race_review_feed(date_text, picks))
    write_json("richFormOutcome.json", rich_form_outcome)
    write_json("performance.json", {
        "bettingDays": performance.get("bettingDays", 0), "profitableDays": performance.get("profitableDays", 0),
        "totalStaked": performance.get("totalStaked", 0), "totalReturn": performance.get("totalReturn", 0),
        "totalProfit": performance.get("totalProfit", 0), "roi": performance.get("roi", 0),
        "winRate": performance.get("winRate", 0), "selectionStats": performance.get("selectionStats", {}),
        "recentProfits": [row.get("profit", 0) for row in reversed((performance.get("recentResults") or [])[:7])],
    })
    write_json("tipsterIntel.json", {
        "sourcesAttempted": len(script_overlay.get("sources_attempted", [])),
        "sourcesSuccessful": len(script_overlay.get("sources_successful", [])),
        "totalRunnersChecked": consensus.get("total_runners_checked", 0),
        "totalMatched": consensus.get("total_matched", 0),
        "tier1SourceFound": bool((consensus.get("script_tipster_overlay") or {}).get("tier1_source_found")),
        "anthropicUsed": bool((consensus.get("api_cost_control") or {}).get("anthropic_used")),
        "estimatedCallsAvoided": (consensus.get("api_cost_control") or {}).get("estimated_api_call_count_avoided", 0),
        "tierMix": [{"tier": tier, "value": sum((row.get("source_tiers") or {}).get(str(tier), 0) for row in consensus.get("matched_to_betfair", [])), "color": color} for tier, color in ((1, "var(--gold)"), (2, "var(--blue)"), (3, "var(--green)"), (4, "var(--muted2)"))],
        "matched": [{"horse": row.get("horse"), "sources": row.get("sources", []), "weighted": row.get("weighted_consensus_score", 0), "level": row.get("support_level", "none")} for row in consensus.get("matched_to_betfair", [])],
    })
    write_json("dbStatus.json", db_status(match_history, len(profiles)))
    write_json("horseMemory.json", visible_memory)
    write_json("winnerIntel.json", [
        {
            "winner": row.get("horse"),
            "status": row.get("selection_type") or "learning",
            "score": row.get("signal_score") or 0,
            "learning": row.get("distance_summary") or row.get("finish_impression") or "Stored for future review.",
            "action": row.get("race_comment") or "Result margin stored for future learning.",
        }
        for row in margin_intel["records"]
        if row.get("position") == 1
    ][:5])
    write_json("resultMarginIntel.json", margin_intel)
    write_json("fieldGraph.json", field_graph)
    copy_dashboard_file(DATA / "horse_intelligence" / f"field_graph_{date_text}.json", "fieldGraph.json")
    copy_dashboard_file(DATA / f"field_relative_daily_{date_text}.json", "fieldRelativeDaily.json")
    write_json("richForm.json", rich_form)
    write_json("captureIntel.json", capture_intel)
    write_json("challengerLab.json", challenger_lab)
    write_json("radarVsOfficial.json", [])
    write_json("continuousLearning.json", {
        "daysAnalysed": learning.get("days_analysed", 0), "officialAnalysed": learning.get("official_picks_analysed", 0),
        "officialPlaced": learning.get("official_picks_placed", 0), "watchlistAnalysed": learning.get("watchlist_horses_analysed", 0),
        "watchlistPlaced": learning.get("watchlist_placed", 0),
        "officialPlaceRate": float(str(learning.get("official_place_rate", "0")).rstrip("%") or 0),
        "watchlistPlaceRate": float(str(learning.get("watchlist_place_rate", "0")).rstrip("%") or 0),
        "findings": [{"code": item.get("finding", ""), "count": item.get("count", 0), "threshold": item.get("threshold", 0), "severity": "warn"} for item in visible_alerts],
    })
    write_json("learningEvidence.json", learning_evidence)
    write_json("shadowRules.json", {"live": {"name": "Current live rule", "picks": len(selected), "roi": performance.get("roi", 0), "profit": performance.get("totalProfit", 0)}, "variants": [], "promotionRule": "Shadow findings are evidence only; no automatic scoring change."})
    write_json("patentViability.json", {"stake": (performance.get("proofBasis") or {}).get("dailyStake", 14), "lines": (performance.get("proofBasis") or {}).get("betLines", 14), "legs": [{"name": row["name"], "odds": row["odds"]} for row in selected], "placeFraction": 0.2})
    write_json("apiCostControl.json", {**cost_control, "calls_today": (consensus.get("api_cost_control") or {}).get("anthropic_calls_used", 0), "calls_avoided": (consensus.get("api_cost_control") or {}).get("estimated_api_call_count_avoided", 0)})
    write_json("dataCoverage.json", {"runnersLoaded": len(runners), "runnersMatched": matched_count, "racesProcessed": len(comparison.get("races", [])), "tipsterMatched": consensus.get("total_matched", 0), "resultsSettled": 0, "resultsTotal": 0})
    write_json("journey.json", [
        {"ico": "◉", "label": "Races loaded", "num": len(comparison.get("races", [])), "pct": 1},
        {"ico": "✓", "label": "Runners scored", "num": len(runners), "pct": 1},
        {"ico": "◈", "label": "Horse memory matches", "num": f"{matched_count}/{len(runners)}", "pct": matched_count / len(runners) if runners else 0},
        {"ico": "⇄", "label": "Rival graph edges", "num": field_graph.get("edgeCount", 0), "pct": 1},
        {"ico": "✦", "label": "Tipster matches", "num": consensus.get("total_matched", 0), "pct": 1},
        {"ico": "⚠", "label": "Warnings recorded", "num": warnings_count, "pct": 1},
        {"ico": "★", "label": "Official picks", "num": len(selected) if selected else "No pick today", "pct": 1},
        {"ico": "◌", "label": "Watchlist tracked", "num": len(picks.get("topRated", []) or []), "pct": 1},
        {"ico": "↻", "label": "Learning days", "num": learning.get("days_analysed", 0), "pct": 1},
    ])
    write_json("timeline.json", [
        {"time": "09:00", "label": "Market and runner data collected", "status": "done" if picks.get("generatedAt") else "scheduled", "detail": "The day\'s races, runners and early Betfair prices are loaded."},
        {"time": "10:00", "label": "Picks and watchlist published", "status": "done" if picks.get("generatedAt") else "scheduled", "detail": f"Mode: {picks.get('mode', 'unknown')}. Official and watchlist horses are written to picks.json."},
        {"time": "After each race", "label": "Results checked", "status": "pending", "detail": "Finishing positions are collected as results become available."},
        {"time": "23:10", "label": "Nightly learning refresh", "status": "scheduled", "detail": "Race memory, rival history and learning reports are refreshed. This does not change today\'s picks."},
    ])
    write_json("ledger.json", {"horse": selected[0]["name"] if selected else "No official pick", "race": f"{selected[0]['course']} {selected[0]['time']}" if selected else "", "gathered": [], "used": [], "note": "Detailed per-runner evidence remains in the local comparison and intelligence data."})
    write_json("automation.json", read_json(OUT / "automation_status.json", {"jobs": [], "manualByDesign": []}))
    write_json("diagnostics.json", diagnostics)
    write_json("highConfidenceMisses.json", {
        "today": high_confidence_misses,
        "history": high_confidence_master,
    })
    print(f"Dashboard feed refreshed for {date_text}: {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args()
    build(args.date)
