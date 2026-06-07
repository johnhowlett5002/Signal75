#!/usr/bin/env python3
"""Signal 75 ROI diagnostics.

Analysis only. Reads archived public data and intelligence reviews, then writes
a concise report about what is helping/hurting official ROI. It does not change
picks, scoring, settlement, proof maths, unlock logic, or public JSON.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO = Path(os.path.expanduser("~/Signal75"))
DATA = REPO / "data"
REVIEWS = DATA / "intelligence_reviews"
OUT_JSON = REVIEWS / "roi_diagnostics_2026-06-07.json"
OUT_TXT = REVIEWS / "roi_diagnostics_2026-06-07.txt"
UK_TZ = ZoneInfo("Europe/London")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def pct(part, total) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def is_watchlist_only(day: dict) -> bool:
    mode = day.get("mode")
    note = str((day.get("results") or {}).get("_note", "")).lower()
    return bool(day.get("noBetDay")) or mode in {"topRatedOnly", "noBetDay"} or "no official proof picks" in note


def result_bucket(row: dict) -> str:
    result = str(row.get("result") or row.get("radarResult") or "").upper()
    pos = int(row.get("position") or 0)
    if result == "WON" or pos == 1:
        return "WON"
    if result == "PLACED" or pos in (2, 3):
        return "PLACED"
    if result in {"LOST", "UNPLACED"} or pos > 0:
        return "LOST"
    return "PENDING"


def archive_snapshot():
    proof_days = []
    watchlist_only_days = []
    for path in sorted(DATA.glob("2026-*.json")):
        day = load_json(path, {})
        if day.get("date", "") < "2026-05-24":
            continue
        if is_watchlist_only(day):
            watchlist_only_days.append(day)
        else:
            proof_days.append(day)
    return proof_days, watchlist_only_days


def performance_snapshot():
    perf = load_json(REPO / "performance.json", {})
    return {
        "betting_days": perf.get("bettingDays", 0),
        "total_staked": money(perf.get("totalStaked")),
        "total_return": money(perf.get("totalReturn")),
        "total_profit": money(perf.get("totalProfit")),
        "roi": money(perf.get("roi")),
        "selection_stats": perf.get("selectionStats", {}),
    }


def watchlist_snapshot():
    perf = load_json(REPO / "performance.json", {})
    rows = []
    for day in perf.get("radarLog", []) or []:
        rows.extend(day.get("selections", []) or [])
    settled = [r for r in rows if result_bucket(r) != "PENDING"]
    winners = sum(1 for r in settled if result_bucket(r) == "WON")
    placed = sum(1 for r in settled if result_bucket(r) == "PLACED")
    return {
        "settled": len(settled),
        "winners": winners,
        "placed": placed,
        "win_rate": pct(winners, len(settled)),
        "place_rate": pct(winners + placed, len(settled)),
        "note": "Watchlist is tracked for learning only and excluded from official ROI.",
    }


def pattern_snapshot():
    weekly = load_json(REVIEWS / "weekly_summary.json", {})
    patterns = weekly.get("pattern_totals") or {}
    consensus = weekly.get("consensus_shadow") or {}
    radar = weekly.get("radar_review") or {}
    return {
        "tipster_count": patterns.get("by_tipster_count", {}),
        "odds_band": patterns.get("by_odds_band", {}),
        "late_market": patterns.get("by_late_market", {}),
        "best_consensus_variant": consensus.get("best_variant"),
        "consensus_variants": consensus.get("variant_profit", {}),
        "radar": radar,
        "key_patterns": weekly.get("key_patterns", {}),
    }


def review_findings():
    findings = []
    for path in sorted(REVIEWS.glob("review_2026-06-0*.json")):
        payload = load_json(path, {})
        if not payload:
            continue
        findings.append({
            "date": payload.get("date"),
            "official_patent": payload.get("official_patent", {}),
            "key_findings": payload.get("key_findings", []),
            "possible_improvements": payload.get("possible_improvements_to_monitor", []),
        })
    return findings


def build_report():
    proof_days, watchlist_only_days = archive_snapshot()
    perf = performance_snapshot()
    watchlist = watchlist_snapshot()
    patterns = pattern_snapshot()

    payload = {
        "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
        "analysis_only": True,
        "summary": {
            "official_roi_after_fix": perf,
            "proof_days_in_archive": len(proof_days),
            "watchlist_only_days_excluded_from_roi": len(watchlist_only_days),
            "watchlist_learning": watchlist,
        },
        "patterns": patterns,
        "daily_review_findings": review_findings(),
        "recommended_until_2026_06_14": [
            "Keep official picks fixed once published.",
            "Do not count watchlist/topRatedOnly days in official ROI.",
            "Keep no forced third pick.",
            "Use weather, late drift, same-course cluster, and rival evidence as warnings only.",
            "Treat 1-tipster official picks as a risk bucket until they prove otherwise.",
            "Prefer fewer official bets over forcing weak Patent legs.",
            "Do not promote watchlist or rival-memory rules into scoring until the 14 June review.",
        ],
        "candidate_rules_to_shadow": [
            "One-tipster picks need stronger protection: high Signal score, no major weather caution, no late drift, no negative rival evidence.",
            "Compare 4.1-6.0 value band against 2.75-8.0 consensus band.",
            "Track whether late drifters underperform before making it a live penalty.",
            "Track whether repeated head-to-head dominance predicts underperformance.",
        ],
    }
    return payload


def text_report(payload: dict) -> str:
    summary = payload["summary"]
    perf = summary["official_roi_after_fix"]
    watch = summary["watchlist_learning"]
    patterns = payload["patterns"]
    lines = [
        "SIGNAL 75 ROI DIAGNOSTICS",
        f"Generated: {payload['generated_at']}",
        "",
        "OFFICIAL ROI",
        f"Betting days: {perf['betting_days']}",
        f"Staked: £{perf['total_staked']:.2f}",
        f"Return: £{perf['total_return']:.2f}",
        f"Profit: {'+' if perf['total_profit'] >= 0 else ''}£{perf['total_profit']:.2f}",
        f"ROI: {'+' if perf['roi'] >= 0 else ''}{perf['roi']:.1f}%",
        f"Watchlist/topRatedOnly days excluded from ROI: {summary['watchlist_only_days_excluded_from_roi']}",
        "",
        "WATCHLIST LEARNING",
        f"Settled watchlist horses: {watch['settled']}",
        f"Winners: {watch['winners']} ({watch['win_rate']}%)",
        f"Placed: {watch['placed']} | Win/place: {watch['place_rate']}%",
        watch["note"],
        "",
        "PATTERNS TO PROTECT ROI",
    ]
    for label, rows in (
        ("Tipster count", patterns.get("tipster_count", {})),
        ("Odds band", patterns.get("odds_band", {})),
        ("Late market", patterns.get("late_market", {})),
    ):
        if not rows:
            continue
        lines.append(label + ":")
        for bucket, row in rows.items():
            lines.append(f"  - {bucket}: {row.get('winners', 0)}/{row.get('selections', 0)} won, {row.get('placed', 0)}/{row.get('selections', 0)} placed")

    lines.extend([
        "",
        "CONSENSUS SHADOW",
        f"Best variant so far: {patterns.get('best_consensus_variant') or 'unknown'}",
    ])
    for name, profit in (patterns.get("consensus_variants") or {}).items():
        lines.append(f"  - {name}: {'+' if money(profit) >= 0 else ''}£{money(profit):.2f}")

    lines.extend(["", "RECOMMENDED UNTIL 14 JUNE"])
    for item in payload["recommended_until_2026_06_14"]:
        lines.append(f"- {item}")

    lines.extend(["", "CANDIDATE RULES TO SHADOW"])
    for item in payload["candidate_rules_to_shadow"]:
        lines.append(f"- {item}")

    return "\n".join(lines)


def main():
    REVIEWS.mkdir(parents=True, exist_ok=True)
    payload = build_report()
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    OUT_TXT.write_text(text_report(payload) + "\n")
    print(f"Wrote {OUT_JSON.relative_to(REPO)}")
    print(f"Wrote {OUT_TXT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
