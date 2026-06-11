#!/usr/bin/env python3
"""Signal 75 June 14 idea lab.

Analysis only. Tests six extra intelligence layers against stored shadow picks
and race memory. It does not change picks, scoring, proof, settlement, results
maths, unlock logic, app data, or public JSON.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo


REPO = Path(os.path.expanduser("~/Signal75"))
DATA = REPO / "data"
INTEL = DATA / "horse_intelligence"
REVIEWS = DATA / "intelligence_reviews"
UK_TZ = ZoneInfo("Europe/London")
EW_STAKE = 2.0

IDEAS = {
    "trainer_jockey_combo": {
        "title": "Trainer and jockey partnership memory",
        "purpose": "Spot combinations that are already producing winners/places in our stored races, and combinations with no support yet.",
        "fourteenth_use": "Use as a small confidence nudge only. Do not let it override horse score, value, or hard warnings.",
    },
    "market_confidence": {
        "title": "Market confidence versus Signal 75 confidence",
        "purpose": "Check whether a high-score horse also has real market interest, or whether it looks high-score but cold in the market.",
        "fourteenth_use": "Warn when Signal 75 likes a horse but the market rank/liquidity says the public is not really with it.",
    },
    "race_competitiveness": {
        "title": "Race competitiveness pressure",
        "purpose": "Treat big, open, highly competitive races differently from cleaner races where the shortlist is clearer.",
        "fourteenth_use": "Raise the bar in bigger/open races, especially for weak-consensus horses.",
    },
    "freshness_profile": {
        "title": "Freshness and layoff profile",
        "purpose": "Catch horses returning too quickly, from long breaks, or from awkward prep patterns.",
        "fourteenth_use": "Use as a caution layer, especially when combined with poor form or no course/distance proof.",
    },
    "weight_rating_pressure": {
        "title": "Weight and rating pressure",
        "purpose": "Compare a horse's weight and official rating against the rest of the race rather than looking at the number alone.",
        "fourteenth_use": "Warn when a horse is carrying a lot more weight or is oddly rated for the field without other support.",
    },
    "race_messiness": {
        "title": "Race messiness / unknown-data risk",
        "purpose": "Avoid overtrusting races where too many runners have missing ratings, unknown results, long layoffs, or weak data.",
        "fourteenth_use": "Lower confidence in races where the data itself is thin or noisy.",
    },
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def pct(part: float, total: float) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def norm_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def result_bucket(row: Dict[str, Any]) -> str:
    result = str(row.get("result") or row.get("known_result") or "").upper()
    pos = int(float(row.get("position") or row.get("finishing_position") or 0))
    if result == "WON" or pos == 1:
        return "won"
    if result == "PLACED":
        return "placed"
    if result in {"LOST", "UNPLACED"} or pos > 0:
        return "lost"
    return "pending"


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def race_key(date: str, market_id: str) -> str:
    return f"{date}|{market_id}"


def records_for_dates(dates: Iterable[str]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    by_runner: Dict[str, Dict[str, Any]] = {}
    by_race: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for date in sorted(set(dates)):
        payload = load_json(INTEL / f"race_memory_{date}.json", {})
        for record in payload.get("records", []) or []:
            key = race_key(record.get("date"), record.get("market_id"))
            by_race[key].append(record)
            runner_key = f"{key}|{norm_name(record.get('horse_name'))}"
            by_runner[runner_key] = record
    return by_runner, by_race


def build_combo_profiles(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"runs": 0, "wins": 0, "places": 0})
    for record in records:
        trainer = str(record.get("trainer") or "").strip()
        jockey = str(record.get("jockey") or "").strip()
        if not trainer or not jockey:
            continue
        key = f"{trainer} / {jockey}"
        profiles[key]["runs"] += 1
        if str(record.get("known_result") or "").upper() == "WON":
            profiles[key]["wins"] += 1
        elif str(record.get("known_result") or "").upper() == "PLACED":
            profiles[key]["places"] += 1
    return profiles


def race_stats(runners: List[Dict[str, Any]]) -> Dict[str, Any]:
    prices = [safe_float(r.get("pre_race_price")) for r in runners]
    prices = [p for p in prices if p is not None and p > 0]
    weights = [safe_float(r.get("weight")) for r in runners]
    weights = [w for w in weights if w is not None and w > 0]
    ratings = [safe_float(r.get("official_rating")) for r in runners]
    ratings = [r for r in ratings if r is not None and r > 0]
    long_layoffs = sum(1 for r in runners if (safe_int(r.get("days_since_run")) or 0) >= 90)
    missing_ratings = sum(1 for r in runners if not (safe_float(r.get("official_rating")) or 0))
    unknown_results = sum(1 for r in runners if str(r.get("known_result") or "").upper() == "UNKNOWN")
    field_size = len(runners)
    top_prices = sorted(prices)[:3]
    return {
        "field_size": field_size,
        "average_price": round(sum(prices) / len(prices), 2) if prices else None,
        "top3_price_spread": round(max(top_prices) - min(top_prices), 2) if len(top_prices) == 3 else None,
        "average_weight": round(sum(weights) / len(weights), 2) if weights else None,
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "long_layoff_share": pct(long_layoffs, field_size),
        "missing_rating_share": pct(missing_ratings, field_size),
        "unknown_result_share": pct(unknown_results, field_size),
    }


def tip_count(pick: Dict[str, Any]) -> int:
    return int(pick.get("consensus_count") or pick.get("tip_count") or pick.get("source_count") or 0)


def idea_flags(pick: Dict[str, Any], record: Dict[str, Any], runners: List[Dict[str, Any]], combo_profiles: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    stats = race_stats(runners)
    market_rank = safe_int(record.get("market_rank_by_price"))
    price = safe_float(record.get("pre_race_price") or pick.get("bsp"))
    field_size = stats.get("field_size") or safe_int(record.get("field_size")) or 0
    score = money(pick.get("score") or record.get("signal_score"))
    tips = tip_count(pick)

    combo = f"{record.get('trainer') or ''} / {record.get('jockey') or ''}".strip(" /")
    combo_profile = combo_profiles.get(combo, {})
    if combo and combo_profile.get("runs", 0) >= 2 and combo_profile.get("wins", 0) == 0 and combo_profile.get("places", 0) == 0:
        flags.append({"idea": "trainer_jockey_combo", "signal": "caution", "detail": f"{combo} has {combo_profile['runs']} logged runs without a known win/place."})
    elif combo and combo_profile.get("wins", 0) >= 1:
        flags.append({"idea": "trainer_jockey_combo", "signal": "support", "detail": f"{combo} has a logged winner in Signal 75 memory."})

    if score >= 85 and market_rank and market_rank > 3 and tips == 0:
        flags.append({"idea": "market_confidence", "signal": "caution", "detail": f"High score {score}, but market rank {market_rank} and no tipster support."})
    elif market_rank and market_rank <= 3 and 4.0 <= (price or 0) <= 8.0:
        flags.append({"idea": "market_confidence", "signal": "support", "detail": f"Top-three in the market at a usable price."})

    if field_size >= 12 and tips == 0:
        flags.append({"idea": "race_competitiveness", "signal": "caution", "detail": f"{field_size}-runner race with no consensus support."})
    elif field_size and field_size <= 8 and score >= 85:
        flags.append({"idea": "race_competitiveness", "signal": "support", "detail": f"Smaller field and strong Signal 75 score."})

    days_since = safe_int(record.get("days_since_run"))
    if days_since is not None and days_since >= 120:
        flags.append({"idea": "freshness_profile", "signal": "caution", "detail": f"Long layoff: {days_since} days since run."})
    elif days_since is not None and days_since <= 7:
        flags.append({"idea": "freshness_profile", "signal": "caution", "detail": f"Quick return: {days_since} days since run."})
    elif days_since is not None and 14 <= days_since <= 60:
        flags.append({"idea": "freshness_profile", "signal": "support", "detail": f"Normal recent run window: {days_since} days."})

    weight = safe_float(record.get("weight"))
    rating = safe_float(record.get("official_rating"))
    avg_weight = stats.get("average_weight")
    avg_rating = stats.get("average_rating")
    if weight and avg_weight and weight >= avg_weight + 8 and tips == 0:
        flags.append({"idea": "weight_rating_pressure", "signal": "caution", "detail": f"Carrying {round(weight - avg_weight, 1)}lb above race average with no consensus support."})
    elif rating and avg_rating and rating >= avg_rating + 5 and 4.0 <= (price or 0) <= 8.0:
        flags.append({"idea": "weight_rating_pressure", "signal": "support", "detail": f"Official rating is {round(rating - avg_rating, 1)} above race average."})

    if stats["missing_rating_share"] >= 50 or stats["unknown_result_share"] >= 80 or stats["long_layoff_share"] >= 25:
        bits = []
        if stats["missing_rating_share"] >= 50:
            bits.append(f"{stats['missing_rating_share']}% missing ratings")
        if stats["unknown_result_share"] >= 80:
            bits.append(f"{stats['unknown_result_share']}% unknown stored results")
        if stats["long_layoff_share"] >= 25:
            bits.append(f"{stats['long_layoff_share']}% long layoffs")
        flags.append({"idea": "race_messiness", "signal": "caution", "detail": "; ".join(bits)})

    return flags


def shadow_rows() -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    dates: List[str] = []
    for path in sorted(glob.glob(str(DATA / "consensus_shadow_2026-06-*.json"))):
        payload = load_json(Path(path), {})
        date = payload.get("date")
        if not date:
            continue
        dates.append(date)
        results = payload.get("results") or {}
        for variant, variant_data in (payload.get("variants") or {}).items():
            result_by_name = {norm_name(r.get("name")): r for r in (results.get(variant, {}).get("results") or [])}
            for pick in variant_data.get("picks") or []:
                result = result_by_name.get(norm_name(pick.get("name")))
                if not result:
                    continue
                rows.append({**pick, **result, "date": date, "variant": variant})
    return rows, sorted(set(dates))


def summarise_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    settled = [r for r in rows if result_bucket(r) != "pending"]
    stake = len(settled) * EW_STAKE
    total_return = sum(money(r.get("totalReturn")) for r in settled)
    winners = sum(1 for r in settled if result_bucket(r) == "won")
    placed = sum(1 for r in settled if result_bucket(r) == "placed")
    return {
        "legs": len(settled),
        "stake": money(stake),
        "return": money(total_return),
        "profit": money(total_return - stake),
        "roi": pct(total_return - stake, stake),
        "winners": winners,
        "placed": placed,
        "win_place_rate": pct(winners + placed, len(settled)),
    }


def unique_examples(rows: List[Dict[str, Any]], idea: str, signal: str, limit: int = 8) -> List[Dict[str, Any]]:
    examples: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = (row.get("date"), norm_name(row.get("name")), idea, signal)
        if key in seen:
            continue
        seen.add(key)
        details = [f["detail"] for f in row["idea_flags"] if f["idea"] == idea and f["signal"] == signal]
        if not details:
            continue
        examples.append(
            {
                "date": row["date"],
                "variant": row["variant"],
                "horse": row["name"],
                "result": result_bucket(row),
                "return": money(row.get("totalReturn")),
                "details": details,
            }
        )
        if len(examples) >= limit:
            break
    return examples


def suggested_use(caution: Dict[str, Any], support: Dict[str, Any]) -> str:
    if caution["legs"] >= 3 and caution["roi"] < 0:
        return "Candidate warning layer. Keep shadow-testing; may reduce confidence when combined with other risks."
    if support["legs"] >= 3 and support["roi"] > 40:
        return "Candidate positive nudge. Useful as supporting evidence, not a standalone reason to pick."
    if caution["legs"] and caution["roi"] > 0:
        return "Information only for now. It flagged too many successful horses to be a blocker."
    return "Watch only until more evidence is collected."


def analyse() -> Dict[str, Any]:
    rows, dates = shadow_rows()
    by_runner, by_race = records_for_dates(dates)
    all_records = [record for records in by_race.values() for record in records]
    combo_profiles = build_combo_profiles(all_records)

    enriched: List[Dict[str, Any]] = []
    for row in rows:
        key = race_key(row.get("date"), row.get("market_id"))
        record = by_runner.get(f"{key}|{norm_name(row.get('name'))}", {})
        runners = by_race.get(key, [])
        flags = idea_flags(row, record, runners, combo_profiles) if record and runners else []
        enriched.append({**row, "idea_flags": flags})

    by_variant: Dict[str, Any] = {}
    for variant in sorted({r["variant"] for r in enriched}):
        variant_rows = [r for r in enriched if r["variant"] == variant]
        by_variant[variant] = {
            "all_legs": summarise_rows(variant_rows),
            "no_caution_legs": summarise_rows([r for r in variant_rows if not any(f["signal"] == "caution" for f in r["idea_flags"])]),
            "support_legs": summarise_rows([r for r in variant_rows if any(f["signal"] == "support" for f in r["idea_flags"])]),
            "caution_legs": summarise_rows([r for r in variant_rows if any(f["signal"] == "caution" for f in r["idea_flags"])]),
        }

    idea_summary: Dict[str, Any] = {}
    for idea in IDEAS:
        caution_rows = [r for r in enriched if any(f["idea"] == idea and f["signal"] == "caution" for f in r["idea_flags"])]
        support_rows = [r for r in enriched if any(f["idea"] == idea and f["signal"] == "support" for f in r["idea_flags"])]
        idea_summary[idea] = {
            **IDEAS[idea],
            "caution": summarise_rows(caution_rows),
            "support": summarise_rows(support_rows),
        }
        idea_summary[idea]["suggested_use_after_test"] = suggested_use(
            idea_summary[idea]["caution"],
            idea_summary[idea]["support"],
        )
        idea_summary[idea]["example_cautions"] = unique_examples(caution_rows, idea, "caution")
        idea_summary[idea]["example_supports"] = unique_examples(support_rows, idea, "support")

    return {
        "generated_at": datetime.now(UK_TZ).isoformat(timespec="seconds"),
        "analysis_only": True,
        "no_live_changes_made": True,
        "dates_tested": dates,
        "shadow_rows_tested": len(enriched),
        "six_new_ideas": idea_summary,
        "variant_summary": by_variant,
        "recommended_14_june_use": [
            "Use these as shadow confidence layers first, not automatic proof-changing rules.",
            "Promote only layers that show repeated improvement without removing too many winners.",
            "Combine with the already planned consensus_prefer_tipped_v1 and Grandad's book hard warnings.",
        ],
    }


def render_text(payload: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 - 14 JUNE SIX-IDEA LAB",
        f"Generated: {payload['generated_at']}",
        "Analysis only. No live picks, proof, scoring, settlement, or app files changed.",
        "",
        f"Dates tested: {', '.join(payload['dates_tested'])}",
        f"Shadow selections tested: {payload['shadow_rows_tested']}",
        "",
        "SIX NEW IDEAS",
    ]
    for idx, (key, item) in enumerate(payload["six_new_ideas"].items(), start=1):
        caution = item["caution"]
        support = item["support"]
        lines.extend(
            [
                "",
                f"{idx}. {item['title']}",
                f"Purpose: {item['purpose']}",
                f"14 June use: {item['fourteenth_use']}",
                f"Test verdict: {item['suggested_use_after_test']}",
                f"Caution legs: {caution['legs']} | profit £{caution['profit']:.2f} | ROI {caution['roi']}% | win/place {caution['win_place_rate']}%",
                f"Support legs: {support['legs']} | profit £{support['profit']:.2f} | ROI {support['roi']}% | win/place {support['win_place_rate']}%",
            ]
        )
        for example in item.get("example_cautions", [])[:3]:
            lines.append(f"Example: {example['date']} {example['horse']} {example['result']} - {'; '.join(example['details'])}")

    lines.extend(["", "SCENARIO VIEW"])
    for variant, item in payload["variant_summary"].items():
        all_legs = item["all_legs"]
        clean = item["no_caution_legs"]
        support = item["support_legs"]
        lines.append(
            f"- {variant}: all ROI {all_legs['roi']}% (£{all_legs['profit']:.2f}); "
            f"no-caution ROI {clean['roi']}% (£{clean['profit']:.2f}); "
            f"support ROI {support['roi']}% (£{support['profit']:.2f})"
        )

    lines.extend(["", "RECOMMENDED USE"])
    for item in payload["recommended_14_june_use"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Signal 75 six-idea lab for 14 June.")
    parser.add_argument("--date", default=datetime.now(UK_TZ).date().isoformat(), help="Output report date")
    args = parser.parse_args()

    REVIEWS.mkdir(parents=True, exist_ok=True)
    payload = analyse()
    out_json = REVIEWS / f"june14_idea_lab_{args.date}.json"
    out_txt = REVIEWS / f"june14_idea_lab_{args.date}.txt"
    write_json(out_json, payload)
    out_txt.write_text(render_text(payload), encoding="utf-8")
    print(f"Wrote {out_json.relative_to(REPO)}")
    print(f"Wrote {out_txt.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
