#!/usr/bin/env python3
"""Generate a compact public Signal 75 daily scorecard.

Read-only for live proof and picks: this script reads daily archives and writes
public scorecard files for later site/social/email use.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from config_loader import REPO_ROOT, load_config


DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "public_scorecards"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")
LEGACY_ARCHIVE_STAKE_EW = 0.50


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def money(value: Any) -> str:
    value = safe_float(value)
    if value < 0:
        return f"-£{abs(value):.2f}"
    if value > 0:
        return f"+£{value:.2f}"
    return "£0.00"


def pct(value: Any) -> str:
    value = safe_float(value)
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def official_bet_meta(selection_count: int, results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    results = results or {}
    if selection_count >= 3:
        fallback = {"bet_type": "PATENT", "bet_label": "£1 each-way Patent", "bet_lines": 14, "daily_stake": 14.0}
    elif selection_count == 2:
        fallback = {"bet_type": "DOUBLE", "bet_label": "£1 each-way Double", "bet_lines": 6, "daily_stake": 6.0}
    elif selection_count == 1:
        fallback = {"bet_type": "SINGLE", "bet_label": "£1 each-way Single", "bet_lines": 2, "daily_stake": 2.0}
    else:
        fallback = {"bet_type": "NO_BET", "bet_label": "No official Signal 75 bet", "bet_lines": 0, "daily_stake": 0.0}

    return {
        "bet_type": results.get("betType") or fallback["bet_type"],
        "bet_label": fallback["bet_label"] if selection_count == 0 else (results.get("proofBasis") or results.get("betLabel") or fallback["bet_label"]),
        "bet_lines": safe_int(results.get("betLines"), fallback["bet_lines"]),
        "daily_stake": safe_float(results.get("totalStake"), fallback["daily_stake"]),
    }


def archive_files() -> Iterable[Path]:
    for path in sorted(DATA_DIR.iterdir()):
        if path.is_file() and DATE_RE.match(path.name):
            yield path


def latest_archive_date() -> str:
    files = list(archive_files())
    if not files:
        raise FileNotFoundError("No dated daily archive files found in data/")
    return files[-1].stem


def proof_scale(day: Dict[str, Any], stake_per_line: float) -> float:
    results = day.get("results") or {}
    source_stake = safe_float(
        results.get("stakeEW") or results.get("stakePerLine"),
        LEGACY_ARCHIVE_STAKE_EW,
    )
    if source_stake <= 0:
        source_stake = LEGACY_ARCHIVE_STAKE_EW
    return stake_per_line / source_stake


def scaled_amount(day: Dict[str, Any], value: Any, stake_per_line: float) -> float:
    return round(safe_float(value) * proof_scale(day, stake_per_line), 2)


def first_horse(race: Dict[str, Any]) -> Dict[str, Any]:
    horses = race.get("horses") or []
    return horses[0] if horses and isinstance(horses[0], dict) else {}


def official_races(day: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    if day.get("mode") != "qualified" or day.get("noBetDay") is True:
        return []
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for tab in ("flat", "jumps"):
        for race in day.get(tab, []) or []:
            horse = first_horse(race)
            if horse.get("name"):
                rows.append((tab, race))
    return rows


def result_rows(day: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    results = day.get("results") or {}
    return {
        "flat": list(results.get("flat") or []),
        "jumps": list(results.get("jumps") or []),
    }


def ordinal(position: Any) -> str:
    pos = safe_int(position)
    if pos <= 0:
        return ""
    if 10 <= pos % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(pos % 10, "th")
    return f"{pos}{suffix}"


def display_result(result: Any, position: Any = None) -> str:
    result_text = str(result or "").upper()
    pos = ordinal(position)
    if result_text == "WON":
        return f"WON - {pos.upper()}" if pos else "WON"
    if result_text == "PLACED":
        return f"PLACED - {pos.upper()}" if pos else "PLACED"
    if result_text == "LOST":
        return pos.upper() if pos else "UNPLACED"
    if result_text == "PENDING":
        return "RESULT PENDING"
    return result_text or "RESULT NOT RECORDED"


def consensus_sources(horse: Dict[str, Any]) -> List[str]:
    consensus = horse.get("consensus") or {}
    sources = consensus.get("sources") or []
    return [str(s) for s in sources if s]


def build_pick(tab: str, race: Dict[str, Any], result: Optional[Dict[str, Any]], idx: int, day: Dict[str, Any], stake_per_line: float) -> Dict[str, Any]:
    horse = first_horse(race)
    result = result or {}
    raw_result = str(result.get("result") or horse.get("result") or "").upper()
    position = result.get("position", horse.get("position", 0))
    return {
        "pick_number": idx,
        "horse": horse.get("name", ""),
        "course": race.get("course") or race.get("venue") or "",
        "time": race.get("time") or "",
        "code": tab,
        "race_type": race.get("type") or "",
        "score": safe_int(horse.get("signal_score")),
        "bsp": safe_float(horse.get("odds")),
        "tipsters": safe_int(horse.get("tipsters") or (horse.get("consensus") or {}).get("source_count")),
        "consensus_sources": consensus_sources(horse),
        "reason": horse.get("reason") or "",
        "result": raw_result or "PENDING",
        "position": safe_int(position),
        "position_text": ordinal(position),
        "display_result": display_result(raw_result, position),
        "win_return": scaled_amount(day, result.get("winReturn", 0), stake_per_line),
        "place_return": scaled_amount(day, result.get("placeReturn", 0), stake_per_line),
        "total_return": scaled_amount(day, result.get("totalReturn", 0), stake_per_line),
    }


def radar_source(day: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    rows: List[Tuple[str, Dict[str, Any]]] = []
    for key, tab in (("topRatedFlat", "flat"), ("topRatedJumps", "jumps")):
        for row in day.get(key, []) or []:
            if isinstance(row, dict) and row.get("name"):
                rows.append((tab, row))

    if day.get("mode") != "qualified":
        for tab in ("flat", "jumps"):
            for race in day.get(tab, []) or []:
                horse = first_horse(race)
                if horse.get("name"):
                    rows.append((tab, {
                        "name": horse.get("name"),
                        "venue": race.get("course"),
                        "course": race.get("course"),
                        "time": race.get("time"),
                        "race_type": race.get("type"),
                        "signal_score": horse.get("signal_score"),
                        "odds": horse.get("odds"),
                        "tipsters": horse.get("tipsters"),
                        "result": horse.get("result"),
                        "position": horse.get("position"),
                    }))
    return rows


def build_radar(day: Dict[str, Any], official_names: set[str]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str, str]] = set()
    rows: List[Dict[str, Any]] = []
    for tab, row in radar_source(day):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        key = (name.upper(), str(row.get("venue") or row.get("course") or ""), str(row.get("time") or ""))
        if key in seen:
            continue
        seen.add(key)
        if name.upper() in official_names:
            continue
        result = str(row.get("result") or row.get("radarResult") or "").upper()
        position = row.get("position") or 0
        rows.append({
            "horse": name,
            "course": row.get("venue") or row.get("course") or "",
            "time": row.get("time") or "",
            "code": tab,
            "race_type": row.get("race_type") or "",
            "score": safe_int(row.get("signal_score")),
            "bsp": safe_float(row.get("odds")),
            "tipsters": safe_int(row.get("tipsters")),
            "result": result or "PENDING",
            "position": safe_int(position),
            "position_text": ordinal(position),
            "display_result": display_result(result, position),
        })
    return rows[:6]


def load_shadow_summary(date_str: str) -> Optional[Dict[str, Any]]:
    path = DATA_DIR / f"consensus_shadow_{date_str}.json"
    if not path.exists():
        return None
    shadow = load_json(path)
    results = shadow.get("results") or {}
    complete_variants = []
    for name, row in results.items():
        if not isinstance(row, dict) or row.get("complete") is not True:
            continue
        complete_variants.append({
            "name": name,
            "profit": safe_float(row.get("patentProfit")),
            "return": safe_float(row.get("patentReturn")),
            "no_bet": row.get("noBet") is True,
        })
    if not complete_variants:
        return None
    complete_variants.sort(key=lambda x: x["profit"], reverse=True)
    return {
        "best_variant": complete_variants[0],
        "variant_count": len(complete_variants),
        "note": "Shadow results are for testing only and are not counted in public proof.",
    }


def build_scorecard(date_str: str) -> Dict[str, Any]:
    config = load_config()
    path = DATA_DIR / f"{date_str}.json"
    if not path.exists():
        raise FileNotFoundError(f"Daily archive not found: {path}")

    day = load_json(path)
    stake_per_line = safe_float(config.get("stake_per_line"), 1.0)
    results = day.get("results") or {}
    official = official_races(day)
    by_tab_results = result_rows(day)

    picks: List[Dict[str, Any]] = []
    tab_indexes = {"flat": 0, "jumps": 0}
    for idx, (tab, race) in enumerate(official, start=1):
        result = None
        if tab_indexes[tab] < len(by_tab_results[tab]):
            result = by_tab_results[tab][tab_indexes[tab]]
        tab_indexes[tab] += 1
        picks.append(build_pick(tab, race, result, idx, day, stake_per_line))

    complete = results.get("complete") is True
    no_bet = day.get("noBetDay") is True or (day.get("mode") in ("noBetDay", "topRatedOnly") and not picks)
    bet_meta = official_bet_meta(len(picks), results)
    patent_return = scaled_amount(day, results.get("totalReturn", results.get("patentReturn", 0)), stake_per_line) if picks else 0.0
    stake = bet_meta["daily_stake"] if picks else 0.0
    profit = safe_float(results.get("totalProfit"), round(patent_return - stake, 2)) if picks else 0.0
    roi = round((profit / stake) * 100, 1) if stake else 0.0
    winners = sum(1 for p in picks if p["result"] == "WON")
    placed = sum(1 for p in picks if p["result"] in ("WON", "PLACED"))
    win_rate = round((winners / len(picks)) * 100, 1) if picks else 0.0
    place_rate = round((placed / len(picks)) * 100, 1) if picks else 0.0
    official_names = {p["horse"].upper() for p in picks}
    radar = build_radar(day, official_names)
    radar_winners = sum(1 for r in radar if r["result"] == "WON")
    radar_placed = sum(1 for r in radar if r["result"] in ("WON", "PLACED"))

    return {
        "date": date_str,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source_archive": path.name,
        "mode": day.get("mode") or "",
        "complete": complete,
        "no_bet_day": no_bet,
        "proof_basis": bet_meta["bet_label"],
        "bet_type": bet_meta["bet_type"],
        "bet_label": bet_meta["bet_label"],
        "bet_lines": bet_meta["bet_lines"],
        "bet_summary": results.get("betSummary"),
        "stake_per_line": stake_per_line,
        "daily_stake": stake,
        "return": patent_return,
        "profit": profit,
        "roi_percent": roi,
        "official_pick_count": len(picks),
        "official_picks": picks,
        "winners": winners,
        "placed": placed,
        "win_rate": win_rate,
        "place_rate": place_rate,
        "radar": {
            "counts_in_proof": False,
            "pick_count": len(radar),
            "winners": radar_winners,
            "placed": radar_placed,
            "picks": radar,
        },
        "shadow": load_shadow_summary(date_str),
        "message": "Every result recorded. No deleted losers.",
        "responsible_gambling": "18+ only. Gamble responsibly. Results are not guaranteed. BeGambleAware.org",
    }


def compact_txt(card: Dict[str, Any]) -> str:
    lines = [
        "SIGNAL 75 DAILY RESULT",
        f"Date: {card['date']}",
        "",
    ]
    if card["no_bet_day"]:
        lines.extend([
            "No official Signal 75 bet today.",
            "No forced bets. No chasing.",
            "",
        ])
    else:
        status = "complete" if card["complete"] else "awaiting final results"
        lines.extend([
            f"Official {card['proof_basis']}",
            f"Status: {status}",
            f"Bet lines: {card.get('bet_lines', 0)}",
            f"Stake: £{card['daily_stake']:.2f}",
            f"Return: £{card['return']:.2f}",
            f"Profit/Loss: {money(card['profit'])}",
            f"ROI: {pct(card['roi_percent'])}",
            "",
            "Official picks:",
        ])
        for pick in card["official_picks"]:
            lines.append(
                f"{pick['pick_number']}. {pick['horse']} — {pick['course']} {pick['time']} — {pick['display_result']}"
            )
        lines.extend([
            "",
            f"Winners: {card['winners']} | Win rate: {card['win_rate']:.1f}% | Place rate: {card['place_rate']:.1f}%",
            "",
        ])

    radar = card.get("radar") or {}
    if radar.get("pick_count"):
        lines.extend([
            "Watchlist:",
            f"{radar['pick_count']} extra picks tracked separately — {radar['winners']} won, {radar['placed']} won or placed.",
            "Watchlist picks are not counted in official results.",
            "",
        ])

    shadow = card.get("shadow")
    if shadow and shadow.get("best_variant"):
        best = shadow["best_variant"]
        lines.extend([
            "Shadow test:",
            f"Best variant: {best['name']} ({money(best['profit'])})",
            "Shadow tests are not counted in official proof.",
            "",
        ])

    lines.extend([
        card["message"],
        card["responsible_gambling"],
        "https://signal75.co.uk",
    ])
    return "\n".join(lines) + "\n"


def save_scorecard(card: Dict[str, Any], update_latest: bool) -> Tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = card["date"]
    json_path = OUTPUT_DIR / f"scorecard_{date_str}.json"
    txt_path = OUTPUT_DIR / f"scorecard_{date_str}.txt"
    write_json(json_path, card)
    write_text(txt_path, compact_txt(card))

    if update_latest and card.get("complete"):
        latest_json = OUTPUT_DIR / "latest_scorecard.json"
        latest_txt = OUTPUT_DIR / "latest_scorecard.txt"
        write_json(latest_json, card)
        write_text(latest_txt, compact_txt(card))

    return json_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a public Signal 75 daily scorecard.")
    parser.add_argument("--date", help="Date to generate, YYYY-MM-DD. Defaults to latest daily archive.")
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Also update latest_scorecard files when the selected day is complete.",
    )
    args = parser.parse_args()

    date_str = args.date or latest_archive_date()
    card = build_scorecard(date_str)
    json_path, txt_path = save_scorecard(card, update_latest=args.latest)
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")
    if args.latest and not card.get("complete"):
        print("Latest scorecard was not updated because this day is not complete yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
