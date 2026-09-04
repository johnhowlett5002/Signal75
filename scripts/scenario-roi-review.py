#!/usr/bin/env python3
"""Signal 75 scenario ROI review.

Analysis only. This reads the proof/performance files and shadow intelligence
already collected, then writes a report of scenarios that appear to improve ROI.
It does not change picks, scoring, settlement, proof maths, unlock logic, or
public JSON structures.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
REVIEWS = DATA / "intelligence_reviews"
TODAY = datetime.now(ZoneInfo("Europe/London")).date().isoformat()
OUT_JSON = REVIEWS / f"scenario_roi_review_{TODAY}.json"
OUT_TXT = REVIEWS / f"scenario_roi_review_{TODAY}.txt"
UK_TZ = ZoneInfo("Europe/London")
EW_STAKE_PER_SELECTION = 2.0


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


def result_bucket(row: dict) -> str:
    result = str(row.get("result") or row.get("radarResult") or "").upper()
    pos = int(row.get("position") or 0)
    if result == "WON" or pos == 1:
        return "won"
    if result == "PLACED" or pos in (2, 3, 4) and str(row.get("result", "")).upper() == "PLACED":
        return "placed"
    if result in {"LOST", "UNPLACED"} or pos > 0:
        return "lost"
    return "pending"


def odds_band(odds) -> str:
    value = money(odds)
    if value <= 0:
        return "unknown"
    if value <= 4.0:
        return "2.75-4.0"
    if value <= 6.0:
        return "4.1-6.0"
    if value <= 8.0:
        return "6.1-8.0"
    return "8.1+"


def score_band(score) -> str:
    value = money(score)
    if value >= 95:
        return "95+"
    if value >= 85:
        return "85-94"
    if value >= 75:
        return "75-84"
    return "below 75"


def add_leg(rows: list[dict], row: dict, context: dict):
    if result_bucket(row) == "pending":
        return
    return_available = "totalReturn" in row
    total_return = money(row.get("totalReturn")) if return_available else None
    rows.append({
        **context,
        "name": str(row.get("name") or "").title(),
        "course": row.get("course"),
        "time": row.get("time"),
        "type": str(row.get("type") or row.get("tab") or "").lower(),
        "odds": money(row.get("odds") or row.get("bsp") or row.get("late_bsp") or row.get("morning_bsp")),
        "score": money(row.get("signal_score") or row.get("score") or row.get("late_score") or row.get("morning_score")),
        "result": result_bucket(row),
        "return": total_return,
        "return_available": return_available,
        "profit": round(total_return - EW_STAKE_PER_SELECTION, 2) if return_available else None,
    })


def summarize_legs(rows: list[dict]) -> dict:
    returns_available = all(r.get("return_available") for r in rows) if rows else False
    stake = len(rows) * EW_STAKE_PER_SELECTION if returns_available else None
    total_return = sum(r["return"] for r in rows) if returns_available else None
    winners = sum(1 for r in rows if r["result"] == "won")
    placed = sum(1 for r in rows if r["result"] == "placed")
    profit = total_return - stake if returns_available else None
    return {
        "selections": len(rows),
        "returns_available": returns_available,
        "stake": money(stake) if returns_available else None,
        "return": money(total_return) if returns_available else None,
        "profit": money(profit) if returns_available else None,
        "roi": pct(profit, stake) if returns_available else None,
        "winners": winners,
        "placed": placed,
        "win_rate": pct(winners, len(rows)),
        "win_place_rate": pct(winners + placed, len(rows)),
    }


def official_selection_legs() -> list[dict]:
    perf = load_json(REPO / "performance.json", {})
    rows = []
    for day in perf.get("selectionLog", []) or []:
        for selection in day.get("selections", []) or []:
            add_leg(rows, selection, {"date": day.get("date"), "source": "official"})
    return rows


def watchlist_legs() -> list[dict]:
    perf = load_json(REPO / "performance.json", {})
    rows = []
    for day in perf.get("radarLog", []) or []:
        for selection in day.get("selections", []) or []:
            add_leg(rows, selection, {"date": day.get("date"), "source": "watchlist"})
    return rows


def grouped_leg_scenarios(rows: list[dict]) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[f"odds {odds_band(row['odds'])}"].append(row)
        groups[f"score {score_band(row['score'])}"].append(row)
        groups[f"type {row['type'] or 'unknown'}"].append(row)
    return {name: summarize_legs(group) for name, group in sorted(groups.items())}


def shadow_summary(pattern: str) -> dict:
    variants: dict[str, dict] = defaultdict(lambda: {
        "days": 0,
        "complete_days": 0,
        "full_patent_days": 0,
        "no_bet_days": 0,
        "profit": 0.0,
        "return": 0.0,
        "stake": 0.0,
        "winners": 0,
        "placed": 0,
        "selections": 0,
        "sample_days": [],
    })
    for path in sorted(DATA.glob(pattern)):
        payload = load_json(path, {})
        results = payload.get("results") or {}
        date = str(payload.get("date") or path.stem.rsplit("_", 1)[-1])
        for name, result in results.items():
            item = variants[name]
            item["days"] += 1
            if not result.get("complete"):
                continue
            picks = result.get("results") or []
            item["complete_days"] += 1
            item["selections"] += len(picks)
            item["winners"] += sum(1 for r in picks if result_bucket(r) == "won")
            item["placed"] += sum(1 for r in picks if result_bucket(r) == "placed")
            if result.get("noBet"):
                item["no_bet_days"] += 1
            else:
                item["full_patent_days"] += 1
                item["stake"] += 14.0
                item["return"] += money(result.get("patentReturn"))
                item["profit"] += money(result.get("patentProfit"))
            item["sample_days"].append({
                "date": date,
                "profit": money(result.get("patentProfit")),
                "return": money(result.get("patentReturn")),
                "no_bet": bool(result.get("noBet")),
                "selections": [str(r.get("name") or "").title() for r in picks],
            })
    output = {}
    for name, item in variants.items():
        stake = item["stake"]
        output[name] = {
            "days_seen": item["days"],
            "complete_days": item["complete_days"],
            "full_patent_days": item["full_patent_days"],
            "no_bet_days": item["no_bet_days"],
            "stake": money(stake),
            "return": money(item["return"]),
            "profit": money(item["profit"]),
            "roi": pct(item["profit"], stake),
            "selections": item["selections"],
            "winners": item["winners"],
            "placed": item["placed"],
            "win_place_rate": pct(item["winners"] + item["placed"], item["selections"]),
            "sample_days": item["sample_days"],
        }
    return dict(sorted(output.items(), key=lambda pair: pair[1]["profit"], reverse=True))


def weekly_pattern_scenarios() -> dict:
    weekly = load_json(REVIEWS / "weekly_summary.json", {})
    patterns = weekly.get("pattern_totals") or {}
    return {
        "tipster_count": patterns.get("by_tipster_count", {}),
        "odds_band": patterns.get("by_odds_band", {}),
        "late_market": patterns.get("by_late_market", {}),
        "race_type": patterns.get("by_code", {}),
    }


def cluster_notes(official_rows: list[dict]) -> dict:
    by_date = defaultdict(list)
    for row in official_rows:
        by_date[row["date"]].append(row)
    same_course_days = []
    for date, rows in sorted(by_date.items()):
        courses = Counter(r["course"] for r in rows if r.get("course"))
        clusters = {course: count for course, count in courses.items() if count >= 2}
        if clusters:
            same_course_days.append({
                "date": date,
                "clusters": clusters,
                "profit": money(sum(r["profit"] for r in rows if r.get("profit") is not None)),
                "results": [f"{r['name']} {r['result']}" for r in rows],
            })
    return {
        "same_course_days": same_course_days,
        "note": "This is an individual-leg warning only. Patent correlation risk needs more days before it becomes a rule.",
    }


def build_payload() -> dict:
    perf = load_json(REPO / "performance.json", {})
    official_rows = official_selection_legs()
    watchlist_rows = watchlist_legs()
    consensus = shadow_summary("consensus_shadow_2026-06-*.json")
    late_value = shadow_summary("late_value_shadow_2026-06-*.json")
    official_perf = {
        "betting_days": perf.get("bettingDays", 0),
        "stake": money(perf.get("totalStaked")),
        "return": money(perf.get("totalReturn")),
        "profit": money(perf.get("totalProfit")),
        "roi": money(perf.get("roi")),
    }
    return {
        "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
        "analysis_only": True,
        "important_caveat": "Small sample only. Use this for shadow testing and the 14 June review, not immediate live rule changes.",
        "official_proof_after_roi_fix": official_perf,
        "proof_level_shadow_scenarios": {
            "consensus_variants": consensus,
            "late_value_variants": late_value,
        },
        "horse_level_scenarios": {
            "official_each_way_legs": summarize_legs(official_rows),
            "official_grouped": grouped_leg_scenarios(official_rows),
            "watchlist_each_way_legs": summarize_legs(watchlist_rows),
            "watchlist_grouped": grouped_leg_scenarios(watchlist_rows),
            "weekly_tipster_odds_late_patterns": weekly_pattern_scenarios(),
            "cluster_notes": cluster_notes(official_rows),
        },
        "ideas_to_shadow_next": [
            "Prefer consensus_prefer_tipped_v1 over strict tipster-first: it kept Signal 75 value picks available and had the best shadow profit so far.",
            "Keep no-forced-third: days with fewer than three strong qualifiers should remain no-bet or partial information, not forced Patent legs.",
            "Treat 1-tipster picks as risk unless backed by stronger Signal 75, value-band odds, no major weather warning, and no negative rival evidence.",
            "Test 4.1-6.0 odds as a protection band; early data is better there than 2.75-4.0.",
            "Keep late drift as a warning, not an automatic removal, until the sample is larger.",
            "Use Grandad's book/rival memory as a negative warning when a selected horse has repeatedly been beaten by a rival in similar conditions.",
            "Monitor same-course and same-trainer Patent clusters because one course/race-condition bias can damage several legs at once.",
            "Use watchlist winners/placers as learning candidates, not proof ROI, especially where high score plus no tipsters keeps finding winners.",
        ],
    }


def fmt_money(value: float) -> str:
    if value is None:
        return "n/a"
    value = money(value)
    return f"{'+' if value >= 0 else ''}£{value:.2f}"


def fmt_roi(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def format_shadow(title: str, rows: dict) -> list[str]:
    lines = [title]
    if not rows:
        return lines + ["- No settled data found."]
    for name, item in rows.items():
        lines.append(
            f"- {name}: {fmt_money(item['profit'])}, ROI {item['roi']:.1f}%, "
            f"{item['full_patent_days']} full Patent day(s), {item['no_bet_days']} no-bet day(s), "
            f"win/place {item['win_place_rate']:.1f}%"
        )
    return lines


def format_grouped(title: str, rows: dict) -> list[str]:
    lines = [title]
    for name, item in rows.items():
        if item["selections"] < 2:
            continue
        lines.append(
            f"- {name}: {item['selections']} runners, {fmt_money(item['profit'])}, "
            f"ROI {fmt_roi(item['roi'])}, win/place {item['win_place_rate']:.1f}%"
        )
    return lines


def text_report(payload: dict) -> str:
    proof = payload["official_proof_after_roi_fix"]
    horse = payload["horse_level_scenarios"]
    patterns = horse["weekly_tipster_odds_late_patterns"]
    lines = [
        "SIGNAL 75 SCENARIO ROI REVIEW",
        f"Generated: {payload['generated_at']}",
        "",
        "STATUS",
        "- Analysis only. No selection, proof, scoring, unlock, or result maths changed.",
        f"- Official proof after ROI fix: {fmt_money(proof['profit'])}, ROI {proof['roi']:.1f}%, {proof['betting_days']} betting days.",
        f"- Caveat: {payload['important_caveat']}",
        "",
    ]
    lines += format_shadow("PROOF-LEVEL SHADOW SCENARIOS", payload["proof_level_shadow_scenarios"]["consensus_variants"])
    lines += [""]
    lines += format_shadow("LATE-VALUE SHADOW SCENARIOS", payload["proof_level_shadow_scenarios"]["late_value_variants"])
    lines += [
        "",
        "HORSE-LEVEL CHECKS",
        "- These are individual each-way legs, not Patent proof. They show where selection quality looks stronger or weaker.",
        f"- Official legs: {fmt_money(horse['official_each_way_legs']['profit'])}, ROI {fmt_roi(horse['official_each_way_legs']['roi'])}, win/place {horse['official_each_way_legs']['win_place_rate']:.1f}%.",
        f"- Watchlist legs: money n/a because watchlist logs do not store returns; win/place {horse['watchlist_each_way_legs']['win_place_rate']:.1f}%.",
        "",
    ]
    lines += format_grouped("OFFICIAL LEG GROUPS", horse["official_grouped"])
    lines += [""]
    lines += format_grouped("WATCHLIST LEG GROUPS", horse["watchlist_grouped"])
    lines += ["", "WEEKLY PATTERNS ALREADY COLLECTED"]
    for title, rows in (
        ("Tipsters", patterns.get("tipster_count", {})),
        ("Odds", patterns.get("odds_band", {})),
        ("Late market", patterns.get("late_market", {})),
        ("Race type", patterns.get("race_type", {})),
    ):
        lines.append(title + ":")
        for name, item in rows.items():
            lines.append(
                f"- {name}: {item.get('selections', 0)} runners, "
                f"{item.get('winners', 0)} won, {item.get('placed', 0)} placed, "
                f"win/place {item.get('place_rate', 0)}%"
            )
    lines += ["", "IDEAS TO SHADOW NEXT"]
    for idea in payload["ideas_to_shadow_next"]:
        lines.append(f"- {idea}")
    return "\n".join(lines)


def main():
    REVIEWS.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    OUT_TXT.write_text(text_report(payload) + "\n")
    print(f"Wrote {OUT_JSON.relative_to(REPO)}")
    print(f"Wrote {OUT_TXT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
