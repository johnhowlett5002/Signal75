#!/usr/bin/env python3
"""Signal 75 continuous training diagnostics.

Analysis only. Reads settled race data, writes separate learning logs under
data/continuous_training, and never changes live picks, proof, scoring, results,
unlock, frontend, or existing master memory files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
OUT_DIR = DATA_DIR / "continuous_training"
ARCHIVE_DIR = OUT_DIR / "archive"

PROTECTED_FILES = [
    "performance.json",
    "picks.json",
    "scripts/scoring_engine.py",
    "scripts/generate-picks-betfair.py",
    "scripts/update-results-mac.py",
    "app.js",
    "sw.js",
    "data/horse_intelligence/horse_history_master.jsonl",
    "data/diagnosis/pattern_accumulator.json",
]

TRUSTED_SOURCES = {
    "timeform",
    "racingpost",
    "racing post",
    "sportinglife",
    "sporting life",
    "attheraces",
    "at the races",
    "racingtv",
    "racing tv",
    "betfredinsights",
    "betfred insights",
    "olbg",
    "dailymail",
    "daily mail",
    "dailymirror",
    "daily mirror",
    "thesun",
    "the sun",
    "telegraph",
    "thetimes",
    "the times",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_uk() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def default_analysis_date() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def file_sha(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checksums() -> Dict[str, Optional[str]]:
    return {rel: file_sha(REPO_ROOT / rel) for rel in PROTECTED_FILES}


def protected_changes(before: Dict[str, Optional[str]]) -> List[str]:
    after = checksums()
    return [rel for rel, old in before.items() if after.get(rel) != old]


def horse_from_race(race: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    horses = race.get("horses")
    if isinstance(horses, list) and horses:
        h = dict(horses[0])
        h.setdefault("course", race.get("course"))
        h.setdefault("time", race.get("time"))
        h.setdefault("race_type", race.get("type") or race.get("race_type"))
        h.setdefault("distance", race.get("distance"))
        h.setdefault("going", race.get("going"))
        h.setdefault("runners", race.get("runners"))
        return h
    return None


def normalized_result(horse: Dict[str, Any]) -> str:
    text = str(horse.get("result") or horse.get("radarResult") or horse.get("status") or "").upper()
    pos = safe_int(horse.get("position"), 0)
    if "WON" in text or pos == 1:
        return "WON"
    if "PLACED" in text:
        return "PLACED"
    if "LOST" in text or "LOSER" in text or "UNPLACED" in text:
        return "LOST"
    if pos > 0:
        return "PLACED" if pos <= 3 else "LOST"
    return "UNKNOWN"


def placed_for_field(position: int, field_size: int) -> bool:
    if position <= 0:
        return False
    if field_size < 8:
        return position <= 2
    return position <= 3


def is_failure(horse: Dict[str, Any], selection_type: str) -> bool:
    position = safe_int(horse.get("position"), 0)
    field_size = safe_int(horse.get("runners") or horse.get("field_size"), 0)
    score = safe_float(horse.get("signal_score") or horse.get("score"), 0)
    if selection_type == "WATCHLIST" and score < 80:
        return False
    return position > 0 and not placed_for_field(position, field_size)


def is_positive(horse: Dict[str, Any]) -> bool:
    position = safe_int(horse.get("position"), 0)
    field_size = safe_int(horse.get("runners") or horse.get("field_size"), 0)
    return position > 0 and placed_for_field(position, field_size)


def sources(horse: Dict[str, Any]) -> List[str]:
    consensus = horse.get("consensus") if isinstance(horse.get("consensus"), dict) else {}
    raw = consensus.get("sources") or consensus.get("tipsters") or horse.get("sources") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(x) for x in raw if x]


def source_count(horse: Dict[str, Any]) -> int:
    consensus = horse.get("consensus") if isinstance(horse.get("consensus"), dict) else {}
    return (
        safe_int(consensus.get("source_count"), 0)
        or safe_int(consensus.get("tip_count"), 0)
        or safe_int(consensus.get("consensus_count"), 0)
        or safe_int(horse.get("tipsters"), 0)
        or len(sources(horse))
    )


def trusted_source_count(horse: Dict[str, Any]) -> int:
    total = 0
    for src in sources(horse):
        cleaned = re.sub(r"[^a-z0-9]+", "", src.lower())
        spaced = re.sub(r"\s+", " ", src.lower()).strip()
        if cleaned in TRUSTED_SOURCES or spaced in TRUSTED_SOURCES:
            total += 1
    return total


def recent_meaningful_form(form: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(form or "").upper())[-5:]


def poor_recent_form(form: Any) -> bool:
    recent = recent_meaningful_form(form)[-3:]
    if len(recent) < 3:
        return False
    bad = 0
    for c in recent:
        if c == "0" or c in "PUFRB":
            bad += 1
        elif c.isdigit() and int(c) >= 8:
            bad += 1
    return bad == 3


def volatile_win_form(form: Any) -> bool:
    cleaned = recent_meaningful_form(form)
    if len(cleaned) < 5 or cleaned[-1] != "1":
        return False
    previous = cleaned[:-1]
    poor = 0
    for c in previous:
        if c == "0" or c in "PUFRB":
            poor += 1
        elif c.isdigit() and int(c) >= 7:
            poor += 1
    return poor >= 3


def add_finding(findings: List[Dict[str, Any]], check: str, severity: str, evidence: str, note: str) -> None:
    findings.append(
        {
            "check": check,
            "finding": check,
            "severity": severity,
            "evidence": evidence,
            "note": note,
        }
    )


def collect_horses(daily: Dict[str, Any]) -> List[Dict[str, Any]]:
    horses: List[Dict[str, Any]] = []
    for tab in ("flat", "jumps"):
        for race in daily.get(tab, []) or []:
            horse = horse_from_race(race)
            if horse:
                horse["_selection_type"] = "OFFICIAL_PICK"
                horse["_tab"] = tab
                horses.append(horse)

    for tab, key in (("flat", "topRatedFlat"), ("jumps", "topRatedJumps")):
        for horse in daily.get(key, []) or []:
            item = dict(horse)
            item["_selection_type"] = "WATCHLIST"
            item["_tab"] = tab
            item.setdefault("course", item.get("venue"))
            item.setdefault("runners", item.get("field_size") or item.get("runners"))
            horses.append(item)

    return horses


def result_lookup(shadow_results: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for variant, payload in (shadow_results or {}).items():
        for row in payload.get("results", []) or []:
            lookup[(variant, norm(row.get("name")))] = row
    return lookup


def diagnose_horse(horse: Dict[str, Any], all_official: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    findings: List[Dict[str, Any]] = []
    positives: List[Dict[str, Any]] = []
    selection_type = horse.get("_selection_type", "WATCHLIST")
    position = safe_int(horse.get("position"), 0)
    result = normalized_result(horse)
    score = safe_float(horse.get("signal_score") or horse.get("score"), 0)
    field_size = safe_int(horse.get("runners") or horse.get("field_size"), 0)
    form = horse.get("formStr") or horse.get("form")

    if is_failure(horse, selection_type):
        going_runs = safe_int(horse.get("goingRuns"), 0)
        going_wins = safe_int(horse.get("goingWins"), 0)
        if going_runs == 0:
            add_finding(findings, "UNPROVEN_GOING", "MEDIUM", "No stored wins/runs on today's going.", "Going may be unknown rather than proven.")
        elif going_runs >= 3 and going_wins == 0:
            add_finding(findings, "POOR_GOING_FIT", "HIGH", f"{going_runs} going runs and 0 wins.", "Repeated poor performance on this going.")
        elif going_runs and going_wins / max(going_runs, 1) >= 0.25:
            add_finding(findings, "GOING_FIT_CONFIRMED_BUT_LOST", "LOW", "Going record looked acceptable.", "Going was probably not the main cause.")

        if safe_int(horse.get("courseWins"), 0) == 0:
            add_finding(findings, "UNPROVEN_COURSE", "LOW", f"No stored course win at {horse.get('course') or horse.get('venue')}.", "Course evidence was weak.")
        if safe_int(horse.get("distanceWins"), 0) == 0:
            add_finding(findings, "UNPROVEN_TRIP", "MEDIUM", f"No stored distance win for {horse.get('distance') or horse.get('race') or 'this trip'}.", "Trip evidence was weak.")

        add_finding(findings, "SURFACE_DATA_MISSING", "LOW", "No reliable surface profile available in stored daily data.", "Cannot verify turf/all-weather suitability.")

        if field_size >= 16:
            add_finding(findings, "LARGE_FIELD_CHAOS_RISK", "MEDIUM", f"{field_size} runners.", "Large fields create more traffic and variance.")

        if poor_recent_form(form):
            add_finding(findings, "POOR_RECENT_FORM", "HIGH", f"Recent form: {form}.", "Last three meaningful form markers were poor/non-completion.")
        elif volatile_win_form(form):
            add_finding(findings, "VOLATILE_RECENT_WIN", "MEDIUM", f"Recent form: {form}.", "Won last time, but previous recent form was messy.")
        elif len(recent_meaningful_form(form)) < 4:
            add_finding(findings, "THIN_FORM_RECORD", "LOW", f"Recent form: {form or 'missing'}.", "Not enough recent form evidence.")

        sc = source_count(horse)
        trusted = trusted_source_count(horse)
        if sc >= 2 and trusted < sc:
            add_finding(findings, "FALSE_CONSENSUS", "HIGH", f"{trusted}/{sc} sources matched trusted list.", "Tipster count may be inflated by weaker sources.")
        elif sc >= 2 and trusted == sc:
            add_finding(findings, "GENUINE_CONSENSUS_FAILED", "LOW", f"{sc} trusted source(s), but result was {result}.", "Real agreement can still lose.")

    if is_positive(horse) and score >= 75:
        positives.append(
            {
                "check": "FULL_CRITERIA_MET_AND_PLACED",
                "finding": "FULL_CRITERIA_MET_AND_PLACED",
                "severity": "POSITIVE",
                "evidence": f"{horse.get('name')} scored {score:g} and finished position {position}.",
                "note": "High-score horse won or placed.",
            }
        )

    if selection_type == "OFFICIAL_PICK":
        course = horse.get("course") or horse.get("venue")
        trainer = horse.get("trainer")
        same_course = [h for h in all_official if (h.get("course") or h.get("venue")) == course]
        same_trainer = [h for h in all_official if trainer and h.get("trainer") == trainer]
        if len(same_course) >= 2 and is_failure(horse, selection_type):
            add_finding(findings, "SAME_COURSE_CLUSTER", "MEDIUM", f"{len(same_course)} official pick(s) at {course}.", "Selections may be over-clustered at one meeting.")
        if len(same_trainer) >= 2 and is_failure(horse, selection_type):
            add_finding(findings, "SAME_TRAINER_CLUSTER", "MEDIUM", f"{len(same_trainer)} official pick(s) for {trainer}.", "Selections may be over-clustered around one trainer.")

    return findings, positives


def shadow_comparison(shadow: Dict[str, Any]) -> Dict[str, Any]:
    results = shadow.get("results") or {}
    if not results:
        return {}
    live = results.get("tipster_first_live_rule") or results.get("baseline_live_rule") or {}
    live_profit = safe_float(live.get("patentProfit"), 0)
    best_name = None
    best_profit = None
    for name, payload in results.items():
        profit = safe_float(payload.get("patentProfit"), 0)
        if best_profit is None or profit > best_profit:
            best_name = name
            best_profit = profit
    beat = best_profit is not None and best_profit > live_profit
    return {
        "live_rule_profit": live_profit,
        "best_shadow_variant": best_name,
        "best_shadow_profit": best_profit if best_profit is not None else 0,
        "shadow_beat_live": beat,
        "shadow_beat_margin": round((best_profit or 0) - live_profit, 2),
    }


def estimate_roi_from_logs(logs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    by_finding: Dict[str, Dict[str, Any]] = {}
    for log in logs:
        for horse in log.get("horses", []):
            if horse.get("result") not in ("LOST", "UNKNOWN"):
                continue
            stake = 14.0 if horse.get("type") == "OFFICIAL_PICK" else 0.0
            for finding in horse.get("findings", []):
                key = finding.get("finding")
                item = by_finding.setdefault(
                    key,
                    {
                        "finding": key,
                        "occurrences": 0,
                        "days_fired": [],
                        "total_stake_on_flagged_picks": 0.0,
                        "actual_return_on_flagged_picks": 0.0,
                        "theoretical_saving_if_excluded": 0.0,
                        "confidence": "LOW",
                        "note": "Directional only. Small sample. Not public proof.",
                    },
                )
                item["occurrences"] += 1
                item["days_fired"].append(log["date"])
                item["total_stake_on_flagged_picks"] += stake
                item["theoretical_saving_if_excluded"] += stake

    for item in by_finding.values():
        occ = item["occurrences"]
        item["days_fired"] = sorted(set(item["days_fired"]))
        if occ >= 10:
            item["confidence"] = "HIGH"
        elif occ >= 5:
            item["confidence"] = "MEDIUM"
        impact = item["theoretical_saving_if_excluded"]
        item["theoretical_roi_impact"] = f"+£{impact:.2f}"
        item["total_stake_on_flagged_picks"] = round(item["total_stake_on_flagged_picks"], 2)
        item["actual_return_on_flagged_picks"] = round(item["actual_return_on_flagged_picks"], 2)
        item["theoretical_saving_if_excluded"] = round(item["theoretical_saving_if_excluded"], 2)
    return {"last_updated": now_iso(), "items": sorted(by_finding.values(), key=lambda x: (-x["occurrences"], x["finding"]))}


def logs_with_current(current_log: Dict[str, Any]) -> List[Dict[str, Any]]:
    logs: Dict[str, Dict[str, Any]] = {}
    for path in OUT_DIR.glob("training_log_*.json"):
        log = load_json(path, {})
        if log.get("date") and not log.get("critical_safety_violation"):
            logs[log["date"]] = log
    logs[current_log["date"]] = current_log
    return [logs[date] for date in sorted(logs)]


def update_cumulative(log: Dict[str, Any]) -> Dict[str, Any]:
    path = OUT_DIR / "cumulative_findings.json"
    cumulative = load_json(
        path,
        {
            "last_updated": None,
            "days_analysed": 0,
            "analysed_dates": [],
            "official_picks_analysed": 0,
            "official_picks_placed": 0,
            "watchlist_horses_analysed": 0,
            "watchlist_placed": 0,
            "finding_totals": {},
            "pattern_alerts": [],
        },
    )

    if log["date"] not in cumulative["analysed_dates"]:
        cumulative["days_analysed"] += 1
        cumulative["analysed_dates"].append(log["date"])
    else:
        # Rebuild light totals from stored logs to avoid double-counting reruns.
        cumulative = rebuild_cumulative_with(log)
        return cumulative

    summary = log.get("session_summary", {})
    cumulative["official_picks_analysed"] += safe_int(summary.get("official_picks_reviewed"), 0)
    cumulative["official_picks_placed"] += safe_int(summary.get("official_placed"), 0)
    cumulative["watchlist_horses_analysed"] += safe_int(summary.get("watchlist_reviewed"), 0)
    cumulative["watchlist_placed"] += safe_int(summary.get("watchlist_placed"), 0)
    for horse in log.get("horses", []):
        for finding in horse.get("findings", []) + horse.get("positive_findings", []):
            key = finding.get("finding")
            cumulative["finding_totals"][key] = cumulative["finding_totals"].get(key, 0) + 1

    cumulative["last_updated"] = now_iso()
    cumulative["official_place_rate"] = pct(cumulative["official_picks_placed"], cumulative["official_picks_analysed"])
    cumulative["watchlist_place_rate"] = pct(cumulative["watchlist_placed"], cumulative["watchlist_horses_analysed"])
    cumulative["pattern_alerts"] = build_pattern_alerts(cumulative["finding_totals"], cumulative["days_analysed"])
    return cumulative


def rebuild_cumulative_with(current_log: Dict[str, Any]) -> Dict[str, Any]:
    logs: Dict[str, Dict[str, Any]] = {}
    for path in OUT_DIR.glob("training_log_*.json"):
        log = load_json(path, {})
        if log.get("date"):
            logs[log["date"]] = log
    logs[current_log["date"]] = current_log

    cumulative = {
        "last_updated": now_iso(),
        "days_analysed": len(logs),
        "analysed_dates": sorted(logs),
        "official_picks_analysed": 0,
        "official_picks_placed": 0,
        "watchlist_horses_analysed": 0,
        "watchlist_placed": 0,
        "finding_totals": {},
        "pattern_alerts": [],
    }
    for log in logs.values():
        summary = log.get("session_summary", {})
        cumulative["official_picks_analysed"] += safe_int(summary.get("official_picks_reviewed"), 0)
        cumulative["official_picks_placed"] += safe_int(summary.get("official_placed"), 0)
        cumulative["watchlist_horses_analysed"] += safe_int(summary.get("watchlist_reviewed"), 0)
        cumulative["watchlist_placed"] += safe_int(summary.get("watchlist_placed"), 0)
        for horse in log.get("horses", []):
            for finding in horse.get("findings", []) + horse.get("positive_findings", []):
                key = finding.get("finding")
                cumulative["finding_totals"][key] = cumulative["finding_totals"].get(key, 0) + 1
    cumulative["official_place_rate"] = pct(cumulative["official_picks_placed"], cumulative["official_picks_analysed"])
    cumulative["watchlist_place_rate"] = pct(cumulative["watchlist_placed"], cumulative["watchlist_horses_analysed"])
    cumulative["pattern_alerts"] = build_pattern_alerts(cumulative["finding_totals"], cumulative["days_analysed"])
    return cumulative


def pct(part: int, total: int) -> str:
    if not total:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def build_pattern_alerts(totals: Dict[str, int], days: int) -> List[Dict[str, Any]]:
    alerts = []
    for finding, count in sorted(totals.items()):
        threshold = 5
        if finding == "SHADOW_BEAT_LIVE_RULE":
            threshold = max(2, int(days * 0.3))
        if count >= threshold:
            alerts.append(
                {
                    "finding": finding,
                    "count": count,
                    "threshold": threshold,
                    "message": f"{finding} has fired {count} time(s).",
                    "recommended_action": "Review after 14 June before changing live rules.",
                }
            )
    return alerts


def update_roi_candidates(roi: Dict[str, Any]) -> Dict[str, Any]:
    candidates = []
    for item in roi.get("items", []):
        status = "watching"
        if item.get("confidence") in ("MEDIUM", "HIGH") and item.get("theoretical_saving_if_excluded", 0) > 0:
            status = "shadow testing"
        candidates.append(
            {
                "finding": item["finding"],
                "proposed_change": proposed_change(item["finding"]),
                "evidence_so_far": item,
                "status": status,
                "manual_approval_required": True,
                "earliest_live_review": "2026-06-14",
            }
        )
    return {"last_updated": now_iso(), "items": candidates}


def proposed_change(finding: str) -> str:
    return {
        "POOR_RECENT_FORM": "Block from official picks or apply a heavy penalty.",
        "VOLATILE_RECENT_WIN": "Apply a soft form penalty and public caution.",
        "MARKET_DRIFT_CONFIRMED": "Use late market drift as a warning layer.",
        "FALSE_CONSENSUS": "Reduce or ignore untrusted sources in consensus counts.",
        "UNPROVEN_GOING": "Keep as warning until going data becomes reliable.",
        "UNPROVEN_TRIP": "Keep as warning until distance profile is reliable.",
        "SHADOW_BEAT_LIVE_RULE": "Compare shadow rule against live rule after trial.",
    }.get(finding, "Keep collecting evidence before any live rule change.")


def render_text(log: Dict[str, Any], roi: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - CONTINUOUS TRAINING LOG",
        f"Date: {log['date']}",
        "",
        "ANALYSIS ONLY - NO LIVE CHANGES MADE",
        "NO-CHEAT RULE OBSERVED",
        "",
        "SESSION SUMMARY",
    ]
    s = log["session_summary"]
    lines.extend(
        [
            f"Official picks reviewed: {s['official_picks_reviewed']}",
            f"Official placed: {s['official_placed']} | Unplaced: {s['official_unplaced']}",
            f"Watchlist reviewed: {s['watchlist_reviewed']} | Watchlist placed: {s['watchlist_placed']}",
            f"Findings raised: {s['findings_raised']}",
            "",
            "UNPLACED HORSE DIAGNOSES",
        ]
    )
    for horse in log.get("horses", []):
        if not horse.get("findings"):
            continue
        lines.extend(
            [
                "",
                f"Horse: {horse['horse']}",
                f"Type: {horse['type'].replace('_', ' ').title()}",
                f"Result: {horse['result']} - position {horse.get('position') or 'unknown'} of {horse.get('field_size') or 'unknown'}",
                f"BSP: {horse.get('bsp')}",
                f"Score: {horse.get('signal_score')}",
            ]
        )
        for idx, finding in enumerate(horse["findings"], start=1):
            lines.extend(
                [
                    f"{idx}. {finding['severity']} - {finding['finding']}",
                    f"   Evidence: {finding['evidence']}",
                    f"   What we missed: {finding['note']}",
                ]
            )
    sc = log.get("shadow_comparison") or {}
    if sc:
        lines.extend(
            [
                "",
                "SHADOW COMPARISON",
                f"Live rule: £{safe_float(sc.get('live_rule_profit'), 0):.2f}",
                f"Best shadow: {sc.get('best_shadow_variant')} (£{safe_float(sc.get('best_shadow_profit'), 0):.2f})",
                f"Shadow beat live by: £{safe_float(sc.get('shadow_beat_margin'), 0):.2f}",
            ]
        )
    lines.extend(["", "ROI IMPACT ESTIMATES", "THEORETICAL ONLY - NOT PUBLIC PROOF"])
    for item in roi.get("items", [])[:10]:
        lines.append(f"- {item['finding']}: {item['occurrences']} occurrence(s), saving {item['theoretical_roi_impact']}")
    lines.extend(["", "NO PROOF FILES CHANGED.", "NO PICKS FILES CHANGED.", "NO SCORING LOGIC CHANGED.", ""])
    return "\n".join(lines)


def analyse(target_date: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    daily = load_json(DATA_DIR / f"{target_date}.json", {})
    shadow = load_json(DATA_DIR / f"consensus_shadow_{target_date}.json", {})
    late = load_json(DATA_DIR / f"late_value_shadow_{target_date}.json", {})
    overlay = load_json(DATA_DIR / f"consensus_overlay_{target_date}.json", {})
    system_config = load_json(DATA_DIR / "system_config.json", {})
    diagnosis = load_json(DATA_DIR / "diagnosis" / f"diagnosis_{target_date}.json", {})
    rival = load_json(DATA_DIR / f"rival_intelligence_{target_date}.json", {})
    race_intel = load_json(DATA_DIR / "horse_intelligence" / f"race_intelligence_{target_date}.json", {})

    horses = collect_horses(daily)
    official = [h for h in horses if h.get("_selection_type") == "OFFICIAL_PICK"]
    rows = []
    findings_count = 0
    high = 0
    positive = 0

    for horse in horses:
        selection_type = horse.get("_selection_type", "WATCHLIST")
        if selection_type == "WATCHLIST" and safe_float(horse.get("signal_score") or horse.get("score"), 0) < 80:
            continue
        findings, positives = diagnose_horse(horse, official)
        findings_count += len(findings)
        high += sum(1 for f in findings if f.get("severity") == "HIGH")
        positive += len(positives)
        if findings or positives:
            rows.append(
                {
                    "horse": horse.get("name") or horse.get("horse_name"),
                    "type": selection_type,
                    "result": normalized_result(horse),
                    "position": safe_int(horse.get("position"), 0),
                    "field_size": safe_int(horse.get("runners") or horse.get("field_size"), 0),
                    "bsp": horse.get("odds") or horse.get("bsp"),
                    "signal_score": safe_float(horse.get("signal_score") or horse.get("score"), 0),
                    "tipster_count": source_count(horse),
                    "trusted_tipster_count": trusted_source_count(horse),
                    "course": horse.get("course") or horse.get("venue"),
                    "time": horse.get("time"),
                    "form": horse.get("formStr") or horse.get("form"),
                    "findings": findings,
                    "positive_findings": positives,
                }
            )

    official_reviewed = len(official)
    official_placed = sum(1 for h in official if is_positive(h))
    watchlist = [
        h for h in horses
        if h.get("_selection_type") == "WATCHLIST" and safe_float(h.get("signal_score") or h.get("score"), 0) >= 80
    ]
    watchlist_placed = sum(1 for h in watchlist if is_positive(h))

    shadow_summary = shadow_comparison(shadow)
    if shadow_summary.get("shadow_beat_live"):
        rows.append(
            {
                "horse": "DAILY_RULE_COMPARISON",
                "type": "SYSTEM_PATTERN",
                "result": "N/A",
                "position": 0,
                "field_size": 0,
                "bsp": None,
                "signal_score": 0,
                "tipster_count": 0,
                "trusted_tipster_count": 0,
                "findings": [
                    {
                        "check": "SHADOW_BEAT_LIVE_RULE",
                        "finding": "SHADOW_BEAT_LIVE_RULE",
                        "severity": "HIGH",
                        "evidence": f"{shadow_summary.get('best_shadow_variant')} beat live by £{shadow_summary.get('shadow_beat_margin')}.",
                        "note": "Shadow rule did better, but this is analysis-only.",
                    }
                ],
                "positive_findings": [],
            }
        )
        findings_count += 1
        high += 1

    log = {
        "date": target_date,
        "generated_at": now_iso(),
        "analysis_only": True,
        "no_live_changes_made": True,
        "no_cheat_rule_observed": True,
        "input_files": {
            "daily": bool(daily),
            "consensus_shadow": bool(shadow),
            "late_value_shadow": bool(late),
            "consensus_overlay": bool(overlay),
            "system_config": bool(system_config),
            "diagnosis": bool(diagnosis),
            "rival_intelligence": bool(rival),
            "race_intelligence": bool(race_intel),
        },
        "session_summary": {
            "official_picks_reviewed": official_reviewed,
            "official_placed": official_placed,
            "official_unplaced": official_reviewed - official_placed,
            "watchlist_reviewed": len(watchlist),
            "watchlist_placed": watchlist_placed,
            "findings_raised": findings_count,
            "findings_high_severity": high,
            "findings_positive": positive,
        },
        "horses": rows,
        "shadow_comparison": shadow_summary,
        "cumulative_findings_updated": True,
        "continuous_training_files_only_changed": True,
        "no_proof_files_changed": True,
        "no_picks_files_changed": True,
        "no_scoring_logic_changed": True,
    }

    all_logs = logs_with_current(log)
    roi = estimate_roi_from_logs(all_logs)
    cumulative = update_cumulative(log)
    alerts = {"last_updated": now_iso(), "items": cumulative.get("pattern_alerts", [])}
    candidates = update_roi_candidates(roi)
    return log, cumulative, roi, alerts | {"roi_improvement_candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Signal 75 analysis-only continuous training.")
    parser.add_argument("--date", default=default_analysis_date(), help="Race date to analyse, YYYY-MM-DD. Defaults to yesterday.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    before = checksums()

    log, cumulative, roi, alert_payload = analyse(args.date)
    changed = protected_changes(before)
    if changed:
        violation = {
            "date": args.date,
            "generated_at": now_iso(),
            "analysis_only": True,
            "critical_safety_violation": True,
            "protected_files_changed": changed,
            "message": "Protected file checksum changed during continuous training. Outputs were not written.",
        }
        write_json(OUT_DIR / f"training_log_{args.date}.json", violation)
        return 2

    write_json(OUT_DIR / f"training_log_{args.date}.json", log)
    (OUT_DIR / f"training_log_{args.date}.txt").write_text(render_text(log, roi), encoding="utf-8")
    write_json(OUT_DIR / "cumulative_findings.json", cumulative)
    write_json(OUT_DIR / "roi_impact_estimates.json", roi)
    write_json(OUT_DIR / "pattern_alerts.json", {k: v for k, v in alert_payload.items() if k != "roi_improvement_candidates"})
    write_json(OUT_DIR / "roi_improvement_candidates.json", alert_payload["roi_improvement_candidates"])

    candidate_text = ["SIGNAL 75 - ROI IMPROVEMENT CANDIDATES", f"Updated: {now_iso()}", ""]
    for item in alert_payload["roi_improvement_candidates"].get("items", []):
        evidence = item.get("evidence_so_far", {})
        candidate_text.extend(
            [
                f"- {item['finding']}",
                f"  Status: {item['status']}",
                f"  Proposed change: {item['proposed_change']}",
                f"  Occurrences: {evidence.get('occurrences', 0)}",
                f"  Estimated saving: {evidence.get('theoretical_roi_impact', '+£0.00')}",
                "  Live change: manual approval required, no earlier than 14 June.",
                "",
            ]
        )
    (OUT_DIR / "roi_improvement_candidates.txt").write_text("\n".join(candidate_text), encoding="utf-8")

    cumulative_text = [
        "SIGNAL 75 - CONTINUOUS LEARNING REGISTER",
        f"Updated: {cumulative.get('last_updated')}",
        f"Days analysed: {cumulative.get('days_analysed')}",
        f"Official place rate: {cumulative.get('official_place_rate')}",
        f"Watchlist place rate: {cumulative.get('watchlist_place_rate')}",
        "",
        "Findings:",
    ]
    for finding, count in sorted(cumulative.get("finding_totals", {}).items(), key=lambda x: (-x[1], x[0])):
        cumulative_text.append(f"- {finding}: {count}")
    (OUT_DIR / "cumulative_findings.txt").write_text("\n".join(cumulative_text) + "\n", encoding="utf-8")

    print(f"Continuous training complete for {args.date}")
    print(f"Wrote {OUT_DIR / f'training_log_{args.date}.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
