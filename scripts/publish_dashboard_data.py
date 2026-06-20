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
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
OUT = REPO_ROOT / "dashboard" / "data"
DB_PATH = DATA / "horse_intelligence" / "signal75_history.sqlite"


def read_json(path: Path, default):
    try:
        with path.open() as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


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


def official_rows(picks: dict, comparison: dict) -> list[dict]:
    comparison_parts = {
        str(runner.get("name", "")).casefold(): runner.get("parts", {})
        for race in comparison.get("races", []) for runner in race.get("runners", [])
    }
    rows = []
    for number, (race, horse) in enumerate(all_selected(picks), 1):
        consensus = horse.get("consensus") or {}
        # The public card uses a compact display structure. The comparison
        # export is the source of truth for the actual four visible parts.
        parts = comparison_parts.get(str(horse.get("name", "")).casefold(), {})
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
        })
    return rows


def db_status() -> dict:
    tables = []
    profile_count = None
    if DB_PATH.exists():
        try:
            with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as connection:
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                for candidate in ("horse_profiles", "profiles", "horse_memory", "runners"):
                    if candidate in tables:
                        profile_count = connection.execute(f"SELECT COUNT(*) FROM {candidate}").fetchone()[0]
                        break
        except sqlite3.Error:
            pass
    return {
        "profileCount": profile_count or 0,
        "dbSizeMb": round(DB_PATH.stat().st_size / 1024 / 1024, 1) if DB_PATH.exists() else 0,
        "tables": sorted(tables),
        "matchHistory": [],
        "note": "Local SQLite intelligence database. It is never copied into the dashboard.",
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
    cost_control = read_json(DATA / "api_cost_control.json", {})
    diagnostics = read_json(DATA / "selection_diagnostics" / f"selection_diagnostics_{date_text}.json", {})
    selected = official_rows(picks, comparison)

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
    write_json("watchlist.json", [
        {"name": horse.get("name", "Unknown"), "course": horse.get("venue", ""), "time": horse.get("time", ""),
         "odds": horse.get("odds", 0), "score": horse.get("signal_score", 0),
         "reason": "WATCHLIST", "reasonText": horse.get("reason", "Strong signal, not an official pick.")}
        for horse in picks.get("topRated", []) or []
    ])
    write_json("raceView.json", {"races": comparison.get("races", [])})
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
    write_json("dbStatus.json", db_status())
    write_json("horseMemory.json", {})
    write_json("winnerIntel.json", [])
    write_json("radarVsOfficial.json", [])
    write_json("continuousLearning.json", {
        "daysAnalysed": learning.get("days_analysed", 0), "officialAnalysed": learning.get("official_picks_analysed", 0),
        "officialPlaced": learning.get("official_picks_placed", 0), "watchlistAnalysed": learning.get("watchlist_horses_analysed", 0),
        "watchlistPlaced": learning.get("watchlist_placed", 0),
        "officialPlaceRate": float(str(learning.get("official_place_rate", "0")).rstrip("%") or 0),
        "watchlistPlaceRate": float(str(learning.get("watchlist_place_rate", "0")).rstrip("%") or 0),
        "findings": [{"code": item.get("finding", ""), "count": item.get("count", 0), "threshold": item.get("threshold", 0), "severity": "warn"} for item in alerts.get("items", [])],
    })
    write_json("shadowRules.json", {"live": {"name": "Current live rule", "picks": len(selected), "roi": performance.get("roi", 0), "profit": performance.get("totalProfit", 0)}, "variants": [], "promotionRule": "Shadow findings are evidence only; no automatic scoring change."})
    write_json("patentViability.json", {"stake": (performance.get("proofBasis") or {}).get("dailyStake", 14), "lines": (performance.get("proofBasis") or {}).get("betLines", 14), "legs": [{"name": row["name"], "odds": row["odds"]} for row in selected], "placeFraction": 0.2})
    write_json("apiCostControl.json", {**cost_control, "calls_today": (consensus.get("api_cost_control") or {}).get("anthropic_calls_used", 0), "calls_avoided": (consensus.get("api_cost_control") or {}).get("estimated_api_call_count_avoided", 0)})
    write_json("dataCoverage.json", {"runnersLoaded": sum(len(r.get("runners", [])) for r in comparison.get("races", [])), "runnersMatched": 0, "racesProcessed": len(comparison.get("races", [])), "tipsterMatched": consensus.get("total_matched", 0), "resultsSettled": 0, "resultsTotal": 0})
    write_json("journey.json", [{"ico": "✓", "label": "Picks generated", "num": len(selected), "pct": 1}, {"ico": "✦", "label": "Tipster matches", "num": consensus.get("total_matched", 0), "pct": 1}, {"ico": "◉", "label": "Races compared", "num": len(comparison.get("races", [])), "pct": 1}, {"ico": "↻", "label": "Learning days", "num": learning.get("days_analysed", 0), "pct": 1}])
    write_json("timeline.json", [{"time": "10:00", "label": "Morning picks pipeline", "status": "done" if picks.get("generatedAt") else "scheduled"}, {"time": "23:10", "label": "Nightly learning refresh", "status": "scheduled"}])
    write_json("ledger.json", {"horse": selected[0]["name"] if selected else "No official pick", "race": f"{selected[0]['course']} {selected[0]['time']}" if selected else "", "gathered": [], "used": [], "note": "Detailed per-runner evidence remains in the local comparison and intelligence data."})
    write_json("automation.json", read_json(OUT / "automation_status.json", {"jobs": [], "manualByDesign": []}))
    write_json("diagnostics.json", diagnostics)
    print(f"Dashboard feed refreshed for {date_text}: {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args()
    build(args.date)
