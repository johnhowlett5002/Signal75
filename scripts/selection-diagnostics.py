#!/usr/bin/env python3
"""
Signal 75 — Selection Diagnostics

Analysis-only helper. It explains why scored horses are official candidates,
Radar/watchlist horses, or rejected by the current gates. It also compares a
few fallback shadow rules without changing picks, proof, settlement, or the
website.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO, "data")
SCRIPTS_DIR = os.path.join(REPO, "scripts")
OUT_DIR = os.path.join(DATA_DIR, "selection_diagnostics")
UK_TZ = ZoneInfo("Europe/London")

sys.path.insert(0, SCRIPTS_DIR)

import scoring_engine as scoring_engine_module  # noqa: E402

scoring_engine_module.ROI_TABLES = os.path.join(DATA_DIR, "roi_tables.json")
from scoring_engine import load_roi_tables, score_all_runners  # noqa: E402

try:
    from daily_consensus_overlay import apply_overlay_to_runners  # noqa: E402
except Exception:
    apply_overlay_to_runners = None


def today_uk():
    return datetime.now(UK_TZ).strftime("%Y-%m-%d")


def safe_float(value, default=None):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text.rstrip() + "\n")


def consensus_count(runner):
    consensus = runner.get("consensus") or {}
    return int(
        consensus.get("consensus_count")
        or consensus.get("tip_count")
        or consensus.get("source_count")
        or 0
    )


def format_time_uk(value):
    text = str(value or "")
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(UK_TZ)
        return dt.strftime("%H:%M")
    except Exception:
        pass
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else ""


def runner_entry(runner):
    consensus = runner.get("consensus") or {}
    return {
        "horse": runner.get("name"),
        "course": runner.get("venue"),
        "time": format_time_uk(runner.get("race_time")),
        "race_type": runner.get("race_type"),
        "market_id": runner.get("market_id"),
        "score": runner.get("score"),
        "qualifies": runner.get("qualifies") is True,
        "odds": safe_float(runner.get("bsp"), 0.0),
        "field_size": safe_int(runner.get("field_size"), 0),
        "tipsters": consensus_count(runner),
        "consensus_level": consensus.get("consensus_level", "none"),
        "sources": consensus.get("sources", []),
        "tipster_names": consensus.get("tipsters", []),
    }


def rejection_reasons(runner, mode="current"):
    score = safe_float(runner.get("score"), 0.0) or 0.0
    odds = safe_float(runner.get("bsp"))
    field_size = safe_int(runner.get("field_size"), 0)
    tipsters = consensus_count(runner)
    reasons = []

    if mode == "current":
        if tipsters <= 0:
            reasons.append("NO_TIPSTER_CONSENSUS")
        if score < 70:
            reasons.append("SCORE_BELOW_TIPSTER_FLOOR_70")
        if odds is None:
            reasons.append("NO_PRICE")
        elif odds < 2.75:
            reasons.append("ODDS_TOO_SHORT_FOR_CURRENT_GATE")
        elif odds > 8.0:
            reasons.append("ODDS_TOO_BIG_FOR_CURRENT_GATE")
        if field_size < 8:
            reasons.append("FIELD_TOO_SMALL")
        return reasons

    if mode == "classic":
        if runner.get("qualifies") is not True:
            reasons.append("ENGINE_QUALIFIES_FALSE")
        if score < 75:
            reasons.append("SCORE_BELOW_75")
        if odds is None:
            reasons.append("NO_PRICE")
        elif odds < 2.75:
            reasons.append("OUTSIDE_VALUE_BAND_TOO_SHORT")
        elif odds > 6.0:
            reasons.append("OUTSIDE_VALUE_BAND_TOO_BIG")
        if field_size < 8:
            reasons.append("FIELD_TOO_SMALL")
        return reasons

    return reasons


def passes_current_tipster_first(runner):
    odds = safe_float(runner.get("bsp"))
    return (
        consensus_count(runner) > 0
        and (safe_float(runner.get("score"), 0.0) or 0.0) >= 70
        and odds is not None
        and 2.75 <= odds <= 8.0
        and safe_int(runner.get("field_size"), 0) >= 8
    )


def passes_classic_value(runner):
    odds = safe_float(runner.get("bsp"))
    return (
        runner.get("qualifies") is True
        and (safe_float(runner.get("score"), 0.0) or 0.0) >= 75
        and odds is not None
        and 2.75 <= odds <= 6.0
        and safe_int(runner.get("field_size"), 0) >= 8
    )


def passes_balanced_fallback(runner):
    """Careful fallback: still needs either tips or a very strong model signal."""
    score = safe_float(runner.get("score"), 0.0) or 0.0
    odds = safe_float(runner.get("bsp"))
    field_size = safe_int(runner.get("field_size"), 0)
    tips = consensus_count(runner)
    if odds is None or field_size < 8 or not (2.75 <= odds <= 10.0):
        return False
    if tips >= 2 and score >= 66:
        return True
    if tips >= 1 and score >= 68:
        return True
    if tips == 0 and score >= 82 and 4.1 <= odds <= 8.0:
        return True
    return False


def passes_signal75_fill(runner):
    """Stronger Signal 75-only fill, useful as a paper comparison."""
    score = safe_float(runner.get("score"), 0.0) or 0.0
    odds = safe_float(runner.get("bsp"))
    return (
        score >= 78
        and odds is not None
        and 4.1 <= odds <= 8.0
        and safe_int(runner.get("field_size"), 0) >= 8
    )


def select_three(scored, predicate, ranking):
    selected = []
    used_markets = set()
    used_names = set()
    for runner in sorted(scored, key=ranking, reverse=True):
        name_key = str(runner.get("name") or "").lower()
        market_id = runner.get("market_id")
        if market_id in used_markets or name_key in used_names:
            continue
        if not predicate(runner):
            continue
        selected.append(runner)
        used_markets.add(market_id)
        used_names.add(name_key)
        if len(selected) >= 3:
            break
    return selected


def load_runner_cache(target_date):
    dated = os.path.join(DATA_DIR, "runner_cache", f"today_runners_{target_date}.json")
    plain = os.path.join(DATA_DIR, "today_runners.json")
    path = dated if os.path.exists(dated) else plain
    data = load_json(path)
    return data, path


def load_public_picks(target_date):
    archived = os.path.join(DATA_DIR, f"{target_date}.json")
    live = os.path.join(REPO, "picks.json")
    path = archived if os.path.exists(archived) else live
    if not os.path.exists(path):
        return None, path
    data = load_json(path)
    if data.get("date") != target_date:
        return None, path
    return data, path


def public_pick_entries(picks_data, key):
    entries = []
    if not picks_data:
        return entries
    for race in picks_data.get(key, []) or []:
        horse = (race.get("horses") or [{}])[0]
        entries.append({
            "horse": horse.get("name"),
            "course": race.get("course"),
            "time": race.get("time"),
            "race_type": race.get("type"),
            "score": horse.get("signal_score") or horse.get("score"),
            "odds": safe_float(horse.get("odds"), 0.0),
            "tipsters": safe_int(horse.get("tipsters"), 0),
            "result": horse.get("result") or race.get("result") or "",
            "position": horse.get("position") or race.get("position") or 0,
        })
    return entries


def public_top_rated_entries(picks_data, key):
    entries = []
    if not picks_data:
        return entries
    for row in picks_data.get(key, []) or []:
        entries.append({
            "horse": row.get("name"),
            "course": row.get("venue") or row.get("course"),
            "time": row.get("time"),
            "race_type": row.get("race_type"),
            "score": row.get("signal_score"),
            "odds": safe_float(row.get("odds"), 0.0),
            "tipsters": safe_int(row.get("tipsters"), 0),
            "result": row.get("result", ""),
            "position": row.get("position", 0),
        })
    return entries


def apply_existing_overlay(scored, target_date):
    overlay_path = os.path.join(DATA_DIR, f"consensus_overlay_{target_date}.json")
    if not apply_overlay_to_runners or not os.path.exists(overlay_path):
        for runner in scored:
            runner.setdefault("consensus", {
                "source_count": 0,
                "tip_count": 0,
                "consensus_count": 0,
                "overlay_points": 0,
                "consensus_level": "none",
                "warning": None,
                "sources": [],
                "tipsters": [],
            })
        return scored, {"path": overlay_path, "applied": False}
    overlay = load_json(overlay_path)
    return apply_overlay_to_runners(scored, overlay), {
        "path": overlay_path,
        "applied": True,
        "sources_successful": overlay.get("sources_successful", []),
        "total_matched": overlay.get("total_matched", 0),
    }


def make_report(target_date):
    runner_cache, runner_cache_path = load_runner_cache(target_date)
    picks_data, picks_path = load_public_picks(target_date)
    tables = load_roi_tables()
    scored = score_all_runners(runner_cache.get("races", []), tables)
    scored, overlay_meta = apply_existing_overlay(scored, target_date)

    current = select_three(
        scored,
        passes_current_tipster_first,
        lambda r: (consensus_count(r), safe_float(r.get("score"), 0.0) or 0.0),
    )
    classic = select_three(
        scored,
        passes_classic_value,
        lambda r: (safe_float(r.get("score"), 0.0) or 0.0, consensus_count(r)),
    )
    balanced = select_three(
        scored,
        passes_balanced_fallback,
        lambda r: (consensus_count(r) > 0, consensus_count(r), safe_float(r.get("score"), 0.0) or 0.0),
    )
    signal_fill = select_three(
        scored,
        passes_signal75_fill,
        lambda r: (safe_float(r.get("score"), 0.0) or 0.0, consensus_count(r)),
    )

    candidates = []
    for runner in sorted(
        scored,
        key=lambda r: (consensus_count(r), safe_float(r.get("score"), 0.0) or 0.0),
        reverse=True,
    )[:60]:
        row = runner_entry(runner)
        row["current_gate"] = "PASS" if passes_current_tipster_first(runner) else "FAIL"
        row["classic_value_gate"] = "PASS" if passes_classic_value(runner) else "FAIL"
        row["balanced_fallback_gate"] = "PASS" if passes_balanced_fallback(runner) else "FAIL"
        row["signal75_fill_gate"] = "PASS" if passes_signal75_fill(runner) else "FAIL"
        row["current_rejection_reasons"] = rejection_reasons(runner, "current")
        row["classic_rejection_reasons"] = rejection_reasons(runner, "classic")
        candidates.append(row)

    reason_counts = Counter()
    for runner in scored:
        if not passes_current_tipster_first(runner):
            reason_counts.update(rejection_reasons(runner, "current"))

    payload = {
        "date": target_date,
        "generated_at": datetime.now(UK_TZ).isoformat(),
        "analysis_only": True,
        "runner_cache": {
            "path": runner_cache_path,
            "date": runner_cache.get("date"),
            "race_count": len(runner_cache.get("races", [])),
        },
        "public_selection_snapshot": {
            "path": picks_path,
            "loaded": picks_data is not None,
            "mode": picks_data.get("mode") if picks_data else None,
            "flat": public_pick_entries(picks_data, "flat"),
            "jumps": public_pick_entries(picks_data, "jumps"),
            "top_rated": public_top_rated_entries(picks_data, "topRated"),
            "top_rated_flat": public_top_rated_entries(picks_data, "topRatedFlat"),
            "top_rated_jumps": public_top_rated_entries(picks_data, "topRatedJumps"),
        },
        "overlay": overlay_meta,
        "summary": {
            "scored_runners": len(scored),
            "current_tipster_first_candidate_count": sum(1 for r in scored if passes_current_tipster_first(r)),
            "classic_value_candidate_count": sum(1 for r in scored if passes_classic_value(r)),
            "balanced_fallback_candidate_count": sum(1 for r in scored if passes_balanced_fallback(r)),
            "signal75_fill_candidate_count": sum(1 for r in scored if passes_signal75_fill(r)),
            "current_rejection_reason_counts": dict(reason_counts.most_common()),
        },
        "shadow_variants": {
            "current_tipster_first": [runner_entry(r) for r in current],
            "classic_value_band": [runner_entry(r) for r in classic],
            "balanced_fallback": [runner_entry(r) for r in balanced],
            "signal75_fill": [runner_entry(r) for r in signal_fill],
        },
        "top_candidates": candidates,
        "recommendation": (
            "Do not change live picks from this report alone. Compare balanced_fallback "
            "and signal75_fill against settled results for at least 7-14 live days."
        ),
    }
    return payload


def make_text(payload):
    lines = []
    lines.append("SIGNAL 75 SELECTION DIAGNOSTICS")
    lines.append(f"Date: {payload['date']}")
    lines.append("")
    s = payload["summary"]
    lines.append("SUMMARY")
    lines.append(f"- Scored runners: {s['scored_runners']}")
    lines.append(f"- Current tipster-first candidates: {s['current_tipster_first_candidate_count']}")
    lines.append(f"- Classic value-band candidates: {s['classic_value_candidate_count']}")
    lines.append(f"- Balanced fallback candidates: {s['balanced_fallback_candidate_count']}")
    lines.append(f"- Signal 75 fill candidates: {s['signal75_fill_candidate_count']}")
    lines.append("")
    public = payload.get("public_selection_snapshot", {})
    lines.append("PUBLIC SITE SNAPSHOT")
    lines.append(f"- Source: {public.get('path')}")
    lines.append(f"- Mode: {public.get('mode')}")
    lines.append(f"- Official flat: {len(public.get('flat') or [])}")
    lines.append(f"- Official jumps: {len(public.get('jumps') or [])}")
    if public.get("flat") or public.get("jumps"):
        for row in (public.get("flat") or []) + (public.get("jumps") or []):
            lines.append(
                f"  - {row['horse']} — {row['course']} {row['time']} "
                f"score {row['score']} tips {row['tipsters']} odds {row['odds']}"
            )
    lines.append("")
    lines.append("TOP REJECTION REASONS")
    for reason, count in s["current_rejection_reason_counts"].items():
        lines.append(f"- {reason}: {count}")
    lines.append("")
    lines.append("SHADOW VARIANTS")
    for name, picks in payload["shadow_variants"].items():
        lines.append(f"{name}: {len(picks)}")
        if not picks:
            lines.append("  - No horses")
        for i, pick in enumerate(picks, 1):
            lines.append(
                f"  {i}. {pick['horse']} — {pick['course']} {pick['time']} "
                f"score {pick['score']} tips {pick['tipsters']} odds {pick['odds']} field {pick['field_size']}"
            )
        lines.append("")
    lines.append("TOP CANDIDATES AND WHY THEY MISS")
    for row in payload["top_candidates"][:25]:
        reasons = ", ".join(row["current_rejection_reasons"]) or "passes current gate"
        lines.append(
            f"- {row['horse']} — {row['course']} {row['time']} "
            f"score {row['score']} tips {row['tipsters']} odds {row['odds']} "
            f"field {row['field_size']} :: {reasons}"
        )
    lines.append("")
    lines.append(payload["recommendation"])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=today_uk())
    args = parser.parse_args()

    payload = make_report(args.date)
    json_path = os.path.join(OUT_DIR, f"selection_diagnostics_{args.date}.json")
    txt_path = os.path.join(OUT_DIR, f"selection_diagnostics_{args.date}.txt")
    write_json(json_path, payload)
    write_text(txt_path, make_text(payload))

    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")
    print(
        "Candidates: current={current_tipster_first_candidate_count}, "
        "balanced={balanced_fallback_candidate_count}, signal75={signal75_fill_candidate_count}".format(
            **payload["summary"]
        )
    )


if __name__ == "__main__":
    main()
