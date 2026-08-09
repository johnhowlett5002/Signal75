#!/usr/bin/env python3
"""
Signal 75 — System Integrity Validator
Runs before morning picks and after nightly pipeline.

Catches common errors before they run for weeks:
  - Price band breaches in picks
  - Large field selections
  - Challenger settlement gaps
  - H2H duplicate records
  - Score gate violations
  - Missing profit fields
  - Pipeline file gaps
  - Odds outside band in challengers

Usage:
  python3 scripts/validate_system_integrity.py
  python3 scripts/validate_system_integrity.py --post-race
  python3 scripts/validate_system_integrity.py --full

Exit code 0 = all checks passed
Exit code 1 = warnings found (non-critical)
Exit code 2 = errors found (critical — stop pipeline)
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO    = Path(__file__).resolve().parents[1]
DATA    = REPO / 'data'
SCRIPTS = REPO / 'scripts'
CHAL    = DATA / 'challenger_lab'
BOOKMAKER_AUDITS = DATA / 'bookmaker_settlement_audits.json'

# ── Price band ───────────────────────────────────────────
ODDS_MIN = 4.1
ODDS_MAX = 6.0
SCORE_GATE = 75
MAX_FIELD  = 14

# ── Colours for terminal output ──────────────────────────
GREEN  = '\033[92m'
YELLOW = '\033[93m'
RED    = '\033[91m'
RESET  = '\033[0m'
BOLD   = '\033[1m'

errors   = []
warnings = []
passes   = []


def ok(msg: str) -> None:
    passes.append(msg)
    print(f"  {GREEN}✅ {msg}{RESET}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  {YELLOW}⚠️  {msg}{RESET}")


def error(msg: str) -> None:
    errors.append(msg)
    print(f"  {RED}❌ {msg}{RESET}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: Any) -> float:
    return round(safe_float(value, 0.0), 2)


def ew_section_return(rows: List[Dict[str, Any]], line_stake: float = 1.0) -> Tuple[float, float, int]:
    """Recalculate Single/Double/Patent return from stored win/place legs."""
    line_stake = line_stake if line_stake > 0 else 1.0
    picks = [
        {
            "win": safe_float(row.get("winReturnExact", row.get("winReturn")), 0.0),
            "place": safe_float(row.get("placeReturnExact", row.get("placeReturn")), 0.0),
        }
        for row in rows[:3]
        if isinstance(row, dict)
    ]
    count = len(picks)
    if count == 0:
        return 0.0, 0.0, 0
    if count == 1:
        return round(picks[0]["win"] + picks[0]["place"], 2), 2.0, 2
    if count == 2:
        h1, h2 = picks
        total = sum(h["win"] + h["place"] for h in picks)
        total += (h1["win"] * h2["win"]) / line_stake if h1["win"] and h2["win"] else 0
        total += (h1["place"] * h2["place"]) / line_stake if h1["place"] and h2["place"] else 0
        return round(total, 2), 6.0, 6

    h1, h2, h3 = picks
    total = sum(h["win"] + h["place"] for h in picks)
    total += (h1["win"] * h2["win"]) / line_stake if h1["win"] and h2["win"] else 0
    total += (h1["place"] * h2["place"]) / line_stake if h1["place"] and h2["place"] else 0
    total += (h1["win"] * h3["win"]) / line_stake if h1["win"] and h3["win"] else 0
    total += (h1["place"] * h3["place"]) / line_stake if h1["place"] and h3["place"] else 0
    total += (h2["win"] * h3["win"]) / line_stake if h2["win"] and h3["win"] else 0
    total += (h2["place"] * h3["place"]) / line_stake if h2["place"] and h3["place"] else 0
    total += (h1["win"] * h2["win"] * h3["win"]) / (line_stake ** 2) if all(h["win"] for h in picks) else 0
    total += (h1["place"] * h2["place"] * h3["place"]) / (line_stake ** 2) if all(h["place"] for h in picks) else 0
    return round(total, 2), 14.0, 14


def ew_day_return(results: Dict[str, Any]) -> Tuple[float, float, int]:
    """Best-effort recalculation for legacy rows without betSummary metadata."""
    bet_summary = results.get("betSummary") if isinstance(results.get("betSummary"), dict) else {}
    section_meta = {
        row.get("section"): row
        for row in bet_summary.get("sectionBets", []) or []
        if isinstance(row, dict)
    }
    sections = []
    for section in ("flat", "jumps"):
        rows = [row for row in results.get(section, []) or [] if isinstance(row, dict)]
        if not rows:
            continue
        meta = section_meta.get(section) or {}
        default_return, default_stake, default_lines = ew_section_return(rows)
        sections.append(
            {
                "section": section,
                "raw_return": default_return,
                "raw_stake": default_stake,
                "lines": default_lines,
            }
        )
    if not sections:
        return 0.0, 0.0, 0
    raw_stake_total = round(sum(row["raw_stake"] for row in sections), 2)
    target_stake = safe_float(results.get("totalStake"), 0.0) or (14.0 if raw_stake_total > 0 else 0.0)
    scale = target_stake / raw_stake_total if raw_stake_total > 0 else 0.0
    total_return = round(sum(row["raw_return"] * scale for row in sections), 2)
    total_lines = sum(row["lines"] for row in sections)
    return total_return, target_stake, total_lines


def official_pick_rows(picks_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for section in ["flat", "jumps"]:
        for race in picks_data.get(section, []) or []:
            if not isinstance(race, dict):
                continue
            runners = int(race.get("runners", 0) or 0)
            for horse in race.get("horses", []) or []:
                if not isinstance(horse, dict):
                    continue
                rows.append(
                    {
                        "name": horse.get("name", "?"),
                        "course": race.get("course", ""),
                        "time": race.get("time", ""),
                        "odds": horse.get("odds", 0),
                        "score": horse.get("signal_score", horse.get("score", 0)),
                        "runners": runners,
                    }
                )
    return rows


def normalised_pick_key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        re.sub(r"[^A-Z0-9]+", "", str(row.get("name", "")).upper()),
        re.sub(r"[^A-Z0-9]+", "", str(row.get("course", "")).upper()),
        str(row.get("time") or ""),
        str(round(safe_float(row.get("odds"), 0), 2)),
        str(round(safe_float(row.get("score"), 0), 1)),
    )


# ════════════════════════════════════════════════════════
# CHECK 1 — picks.json integrity
# ════════════════════════════════════════════════════════

def check_picks() -> None:
    print(f"\n{BOLD}CHECK 1 — picks.json integrity{RESET}")
    path = REPO / 'picks.json'
    d = load_json(path)

    if d is None:
        error("picks.json missing or invalid JSON")
        return

    today = date.today().isoformat()
    pick_date = d.get('date', '')
    bet_type  = d.get('betType', '')

    if pick_date != today:
        warn(f"picks.json date is {pick_date} not {today}")
    else:
        ok(f"picks.json date is today ({today})")

    if bet_type == 'no_bet':
        warn("Today is a no-bet day — no official picks")
        return

    # Only flat/jumps are official picks. topRated/topRatedFlat/topRatedJumps
    # are public radar/watchlist cards and must not be treated as proof picks.
    official_picks = official_pick_rows(d)
    radar_sections = ('topRated', 'topRatedFlat', 'topRatedJumps')
    for section in radar_sections:
        for horse in d.get(section, []) or []:
            if not isinstance(horse, dict):
                continue
            name = horse.get('name') or '?'
            if horse.get('official') is not False:
                error(f"{section} horse {name}: radar card missing official=false")
            if horse.get('pickType') != 'radar':
                error(f"{section} horse {name}: radar card missing pickType=radar")

    if not official_picks:
        warn("No official picks found in picks.json")
        return

    ok(f"Found {len(official_picks)} official picks")

    for p in official_picks:
        name  = p.get('name', '?')
        odds  = safe_float(p.get('odds'), 0)
        score = safe_float(p.get('score'), 0)
        runners = int(p.get('runners', 0) or 0)

        # Price band check
        if odds > ODDS_MAX:
            error(f"{name}: odds {odds} exceeds "
                  f"ceiling {ODDS_MAX}")
        elif odds < ODDS_MIN:
            error(f"{name}: odds {odds} below "
                  f"floor {ODDS_MIN}")
        else:
            ok(f"{name}: odds {odds} within band")

        # Score gate check
        if score < SCORE_GATE:
            error(f"{name}: score {score} below "
                  f"gate {SCORE_GATE}")
        else:
            ok(f"{name}: score {score} above gate")

        # Field size check
        if runners > MAX_FIELD:
            error(f"{name}: field size {runners} "
                  f"exceeds max {MAX_FIELD}")
        elif runners > 0:
            ok(f"{name}: field size {runners} OK")


# ════════════════════════════════════════════════════════
# CHECK 2 — performance.json profit fields
# ════════════════════════════════════════════════════════

def check_profit_fields() -> None:
    print(f"\n{BOLD}CHECK 2 — Daily result profit fields{RESET}")

    import glob
    files = sorted(glob.glob(str(DATA / '2026-*.json')))
    missing = []
    undercounted = []
    checked = 0

    # This guard is for the current proof system. Older June seed files used
    # different settlement fields, so do not let legacy proof noise stop picks.
    cutoff = max(
        (date.today() - timedelta(days=21)).isoformat(),
        "2026-07-01",
    )

    for f in files:
        d = load_json(Path(f))
        if not d: continue
        file_date = str(d.get('date') or Path(f).stem)
        if file_date < cutoff:
            continue
        r = d.get('results', {})
        if not r.get('complete'): continue
        if r.get('betType') == 'no_bet':
            continue
        if not r.get('flat') and not r.get('jumps'):
            continue
        checked += 1

        profit = r.get('profit')
        stake  = float(r.get('totalStake', 0) or 0)
        ret    = float(r.get('totalReturn', 0) or 0)
        patent_ret = float(r.get('patentReturn', 0) or 0)

        if patent_ret > 0 and ret + 0.02 < patent_ret:
            undercounted.append({
                'date': d.get('date', f[-15:-5]),
                'totalReturn': ret,
                'patentReturn': patent_ret,
            })

        if profit is None:
            item = {
                'date':  d.get('date', f[-15:-5]),
                'stake': stake,
                'ret':   ret,
                'calc':  round(ret - stake, 2),
            }
            if stake == 0 and ret == 0:
                warn(f"profit=None in no-bet day {item['date']} "
                     f"(should be £{item['calc']})")
                continue
            missing.append({
                'date':  d.get('date', f[-15:-5]),
                'stake': stake,
                'ret':   ret,
                'calc':  round(ret - stake, 2),
            })

    if undercounted:
        for m in undercounted:
            error(
                f"{m['date']}: totalReturn £{m['totalReturn']:.2f} "
                f"undercounts patentReturn £{m['patentReturn']:.2f}"
            )

    if missing:
        for m in missing:
            error(f"profit=None in {m['date']} "
                  f"(should be £{m['calc']})")
        warn(f"Run: python3 scripts/"
             f"generate-performance.py to fix")
    else:
        ok(f"All {checked} daily result files "
           f"have profit field")


# ════════════════════════════════════════════════════════
# CHECK 3 — Challenger settlement gaps
# ════════════════════════════════════════════════════════

def check_challenger_settlement(strict: bool = False) -> None:
    print(f"\n{BOLD}CHECK 3 — Challenger settlement{RESET}")

    import glob
    files = sorted(glob.glob(
        str(CHAL / 'challenger_2026-*.json')))

    unsettled_days = {}
    total_picks = 0
    settled_picks = 0

    settlement_grace_days = 3
    cutoff_recent = (date.today() - timedelta(days=7)).isoformat()
    cutoff_old = (date.today() - timedelta(days=settlement_grace_days)).isoformat()

    for f in files:
        d = load_json(Path(f))
        if not d: continue
        day_date = d.get('date', '')
        if day_date < cutoff_recent:
            continue

        for c in d.get('pre_race_challengers', []):
            cid   = c.get('id', '')
            picks = c.get('picks', [])

            for p in picks:
                total_picks += 1
                result = p.get('result', '')
                settled = p.get('settled', False)

                if result in ('WON','PLACED','LOST') \
                        or settled:
                    settled_picks += 1
                else:
                    key = f"{day_date}:{cid}"
                    unsettled_days[key] = \
                        unsettled_days.get(key, 0) + 1

    if total_picks == 0:
        warn("No challenger pick files found")
        return

    settle_rate = settled_picks / total_picks * 100

    old_unsettled = {
        k: v for k, v in unsettled_days.items()
        if k.split(':')[0] < cutoff_old
    }

    if old_unsettled:
        for key, count in list(
                old_unsettled.items())[:5]:
            day, cid = key.split(':', 1)
            msg = (f"Unsettled challenger picks >{settlement_grace_days} days old: "
                   f"{day} {cid} ({count} picks)")
            warn(msg)
    else:
        ok(f"No old unsettled challenger picks "
           f"(settle rate {settle_rate:.0f}%)")


# ════════════════════════════════════════════════════════
# CHECK 4 — Challenger odds in price band
# ════════════════════════════════════════════════════════

def check_challenger_odds() -> None:
    print(f"\n{BOLD}CHECK 4 — Challenger odds in price band{RESET}")

    import glob
    files = sorted(glob.glob(
        str(CHAL / 'challenger_2026-*.json')))

    violations = []
    for f in files[-7:]:  # last 7 days
        d = load_json(Path(f))
        if not d: continue
        day_date = d.get('date', '')

        for c in d.get('pre_race_challengers', []):
            cid = c.get('id', '')
            # wider_price_band is allowed wider range
            if 'wider' in cid:
                continue
            for p in c.get('picks', []):
                odds = float(p.get('odds', 0) or 0)
                if odds > 0 and (
                        odds < ODDS_MIN or
                        odds > ODDS_MAX):
                    violations.append(
                        f"{day_date} {cid}: "
                        f"{p.get('horse','?')} "
                        f"odds={odds}")

    if violations:
        for v in violations[:5]:
            error(f"Odds outside band: {v}")
        if len(violations) > 5:
            error(f"...and {len(violations)-5} more")
    else:
        ok("All challenger picks within price band")


# ════════════════════════════════════════════════════════
# CHECK 5 — H2H duplicate records
# ════════════════════════════════════════════════════════

def check_h2h_duplicates() -> None:
    print(f"\n{BOLD}CHECK 5 — H2H duplicate records{RESET}")

    master_path = DATA / 'horse_intelligence' / 'head_to_head_master.jsonl'
    if not master_path.exists():
        warn("head_to_head_master.jsonl not found")
        return

    try:
        seen = set()
        total = 0
        duplicates = 0
        with master_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                total += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    warn("Could not parse a head_to_head_master.jsonl row")
                    continue
                key = (
                    row.get("winner_key") or row.get("winner"),
                    row.get("loser_key") or row.get("loser"),
                    row.get("date"),
                    row.get("course"),
                    row.get("race_time") or row.get("time"),
                )
                if key in seen:
                    duplicates += 1
                else:
                    seen.add(key)

        dup_pct = duplicates / total * 100 \
            if total > 0 else 0

        if duplicates:
            error(f"H2H has {duplicates:,} duplicates "
                  f"({dup_pct:.0f}% of {total:,} rows) "
                  f"— dashboard showing doubled counts")
        else:
            ok(f"H2H records: {total:,} total, "
               f"{duplicates:,} duplicates "
               f"({dup_pct:.0f}%)")

    except Exception as e:
        warn(f"Could not check H2H: {e}")


# ════════════════════════════════════════════════════════
# CHECK 6 — Challenger RISKY status
# ════════════════════════════════════════════════════════

def check_challenger_status() -> None:
    print(f"\n{BOLD}CHECK 6 — Challenger RISKY detection{RESET}")

    path = CHAL / 'challenger_summary.json'
    s = load_json(path)
    if not s:
        warn("challenger_summary.json not found")
        return

    for c in s.get('pre_race_challengers', []):
        cid     = c.get('id', '')
        settled = c.get('settled_days', 0)
        delta   = c.get('delta_vs_live_profit', 0)
        status  = c.get('promotion_status', '')

        # Should be RISKY if 14+ settled and -£5+ delta
        if settled >= 14 and delta < -5.0:
            if status != 'RISKY':
                error(f"{cid}: {settled} settled days, "
                      f"delta £{delta:.2f} — "
                      f"should be RISKY not {status}")
            else:
                ok(f"{cid}: correctly marked RISKY "
                   f"({settled}d, £{delta:.2f})")
        elif settled >= 14:
            ok(f"{cid}: {settled} settled days, "
               f"delta £{delta:+.2f} — status {status}")


# ════════════════════════════════════════════════════════
# CHECK 7 — Pipeline files exist for today
# ════════════════════════════════════════════════════════

def check_pipeline_files() -> None:
    print(f"\n{BOLD}CHECK 7 — Pipeline files for today{RESET}")

    today = date.today().isoformat()

    expected = {
        'picks.json':
            REPO / 'picks.json',
        f'race_comparison_{today}.json':
            DATA / f'race_comparison_{today}.json',
        f'field_relative_archive_{today}.json':
            DATA / f'field_relative_archive_{today}.json',
        f'field_relative_daily_{today}.json':
            DATA / f'field_relative_daily_{today}.json',
        f'challenger_{today}.json':
            CHAL / f'challenger_{today}.json',
    }

    for name, path in expected.items():
        if path.exists():
            size = path.stat().st_size
            if size < 10:
                warn(f"{name} exists but is empty "
                     f"({size} bytes)")
            else:
                ok(f"{name} exists ({size:,} bytes)")
        else:
            warn(f"{name} missing — pipeline may "
                 f"not have run yet")


# ════════════════════════════════════════════════════════
# CHECK 13 — Dashboard official picks match picks.json
# ════════════════════════════════════════════════════════

def check_dashboard_sync() -> None:
    print(f"\n{BOLD}CHECK 13 — Dashboard picks sync{RESET}")

    picks = load_json(REPO / 'picks.json')
    dashboard_rows = load_json(REPO / 'dashboard' / 'data' / 'officialPicks.json')
    dashboard_ready = load_json(REPO / 'dashboard' / 'data' / 'dashboard_ready.json') or {}

    if not isinstance(picks, dict):
        error("Cannot check dashboard sync because picks.json is invalid")
        return

    pick_date = str(picks.get('date') or '')
    today = date.today().isoformat()
    if pick_date != today:
        warn(f"Dashboard sync skipped because picks.json is from {pick_date}, not {today}")
        return

    if not isinstance(dashboard_rows, list):
        error("dashboard/data/officialPicks.json missing or invalid")
        return

    dashboard_date = str(dashboard_ready.get('date') or '')
    if dashboard_date and dashboard_date != pick_date:
        error(
            f"Dashboard export date {dashboard_date} does not match picks.json date {pick_date}"
        )

    expected = [
        {
            "name": row.get("name"),
            "course": row.get("course"),
            "time": row.get("time"),
            "odds": row.get("odds"),
            "score": row.get("score"),
        }
        for row in official_pick_rows(picks)
    ]
    actual = [
        {
            "name": row.get("name"),
            "course": row.get("course"),
            "time": row.get("time"),
            "odds": row.get("odds"),
            "score": row.get("score"),
        }
        for row in dashboard_rows
        if isinstance(row, dict)
    ]

    expected_keys = {normalised_pick_key(row) for row in expected}
    actual_keys = {normalised_pick_key(row) for row in actual}

    if expected_keys != actual_keys:
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        if missing:
            error(f"Dashboard missing official pick(s) from picks.json: {sorted(missing)}")
        if extra:
            error(f"Dashboard has stale/extra official pick(s): {sorted(extra)}")
        return

    ok(f"Dashboard official picks match picks.json ({len(expected)} pick(s))")


# ════════════════════════════════════════════════════════
# CHECK 11 — V1 settlement quality
# ════════════════════════════════════════════════════════

def check_v1_settlement_quality() -> None:
    print(f"\n{BOLD}CHECK 11 — V1 settlement quality{RESET}")

    import glob
    files = sorted(glob.glob(str(DATA / 'field_relative_archive_*_settled.json')))
    if not files:
        warn("No V1 settled archive files found yet")
        return

    settled_checked = 0
    pending_rows = 0
    for f in files[-7:]:
        d = load_json(Path(f))
        if not d:
            error(f"{Path(f).name}: invalid JSON")
            continue
        picks = d.get('picks', d.get('selections', []))
        for p in picks:
            if not isinstance(p, dict):
                continue
            name = p.get('horse') or p.get('name') or ''
            if not name or name == '?':
                error(f"{Path(f).name}: V1 row has no horse name")
            if not p.get('settled'):
                pending_rows += 1
                continue
            settled_checked += 1
            result = p.get('result')
            if result not in ('WON', 'PLACED', 'LOST'):
                error(f"{Path(f).name}: {name} settled without valid result")
            ret = safe_float(p.get('return'), 0.0)
            if result in ('WON', 'PLACED') and ret <= 0:
                error(f"{Path(f).name}: {name} {result} but return is £{ret:.2f}")

    if settled_checked:
        ok(f"V1 settled archive rows valid ({settled_checked} settled rows checked)")
    else:
        warn("No settled V1 archive rows with matched results found in last 7 files")
    if pending_rows:
        warn(f"{pending_rows} V1 archive rows still pending result match")

    daily_files = sorted(glob.glob(str(DATA / 'field_relative_daily_2026-*.json')))
    settled_daily = 0
    for f in daily_files[-14:]:
        d = load_json(Path(f))
        if not d or not d.get('settled'):
            continue
        settled_daily += 1
        picks = d.get('picks', [])
        for p in picks:
            if not isinstance(p, dict):
                continue
            name = p.get('horse') or p.get('name') or ''
            if not name or name == '?':
                error(f"{Path(f).name}: settled V1 daily pick has no horse name")
            result = p.get('result')
            if result not in ('WON', 'PLACED', 'LOST'):
                error(f"{Path(f).name}: {name} settled without valid result")
            ret = safe_float(p.get('return'), 0.0)
            if result in ('WON', 'PLACED') and ret <= 0:
                error(f"{Path(f).name}: {name} {result} but return is £{ret:.2f}")
            odds = safe_float(p.get('odds'), 0.0)
            if odds < ODDS_MIN or odds > ODDS_MAX:
                error(f"{Path(f).name}: {name} odds {odds} outside {ODDS_MIN}-{ODDS_MAX}")

    if settled_daily:
        ok(f"V1 settled daily comparison files valid ({settled_daily} settled days checked)")
    else:
        warn("No fully settled V1 daily comparison days found")


# ════════════════════════════════════════════════════════
# CHECK 12 — V1 price band compliance
# ════════════════════════════════════════════════════════

def check_v1_price_band() -> None:
    print(f"\n{BOLD}CHECK 12 — V1 daily price band{RESET}")

    today = date.today().isoformat()
    path = DATA / f'field_relative_daily_{today}.json'
    d = load_json(path)
    if not d:
        warn(f"field_relative_daily_{today}.json not found yet")
        return

    picks = d.get('picks', [])
    if not picks:
        ok("V1 daily selector has no picks today")
        return

    for p in picks:
        name = p.get('horse') or p.get('name') or '?'
        odds = safe_float(p.get('odds'), 0.0)
        if not name or name == '?':
            error("V1 daily pick has no horse name")
        if odds < ODDS_MIN or odds > ODDS_MAX:
            error(f"V1 daily pick {name}: odds {odds} outside {ODDS_MIN}-{ODDS_MAX}")
        else:
            ok(f"V1 daily pick {name}: odds {odds} within band")


# ════════════════════════════════════════════════════════
# CHECK 14 — Field graph pre-race evidence only
# ════════════════════════════════════════════════════════

def check_field_graph_pre_race_only() -> None:
    print(f"\n{BOLD}CHECK 14 — Field graph pre-race evidence only{RESET}")

    files = sorted((DATA / 'horse_intelligence').glob('field_graph_2026-*.json'))
    if not files:
        warn("No field_graph files found yet")
        return

    path = files[-1]
    d = load_json(path)
    if not isinstance(d, dict):
        error(f"{path.name}: invalid JSON")
        return

    graph_date = str(d.get('date') or '')
    if not graph_date:
        error(f"{path.name}: missing date")
        return

    leaks = []
    for runner in d.get('currentRunners', []) or []:
        if not isinstance(runner, dict):
            continue
        horse = runner.get('horse_name') or '?'
        for edge_type in ('direct_edges', 'negative_edges'):
            for edge in runner.get(edge_type, []) or []:
                edge_date = str(edge.get('latest_date') or '')[:10]
                if edge_date and edge_date >= graph_date:
                    leaks.append(
                        f"{horse}: {edge_type} against {edge.get('rival','?')} "
                        f"uses {edge_date} in {graph_date} graph"
                    )

    if leaks:
        for leak in leaks[:5]:
            error(f"Field graph hindsight risk: {leak}")
        if len(leaks) > 5:
            error(f"...and {len(leaks) - 5} more same-day field graph edge(s)")
    else:
        ok(f"{path.name}: all direct/warning edges pre-date {graph_date}")


# ════════════════════════════════════════════════════════
# CHECK 8 — Post-race: results settled correctly
# ════════════════════════════════════════════════════════

def check_post_race_settlement() -> None:
    print(f"\n{BOLD}CHECK 8 — Post-race settlement{RESET}")

    today = date.today().isoformat()
    yesterday = (date.today() -
                  timedelta(days=1)).isoformat()

    for check_date in [today, yesterday]:
        path = DATA / f'{check_date}.json'
        if not path.exists():
            continue

        d = load_json(path)
        if not d: continue
        r = d.get('results', {})

        if not r.get('complete'):
            warn(f"{check_date}: results not "
                 f"marked complete yet")
            continue

        picks_count = 0
        missing_result = []

        for section in ['flat', 'jumps']:
            for p in r.get(section, []):
                if not isinstance(p, dict): continue
                picks_count += 1
                result = p.get('result', '')
                if not result or result == '?':
                    missing_result.append(
                        p.get('name', '?'))

        if missing_result:
            error(f"{check_date}: {len(missing_result)}"
                  f" picks have no result: "
                  f"{missing_result}")
        elif picks_count > 0:
            ok(f"{check_date}: {picks_count} picks "
               f"all have results")


# ════════════════════════════════════════════════════════
# CHECK 9 — Score gate not changed
# ════════════════════════════════════════════════════════

def check_score_gate() -> None:
    print(f"\n{BOLD}CHECK 9 — Live gate integrity{RESET}")

    path = SCRIPTS / 'scoring_engine.py'
    if not path.exists():
        error("scoring_engine.py not found")
        return

    content = path.read_text(encoding='utf-8')

    # Check score gate is still 75
    if '75' in content:
        ok("Score gate 75 present in scoring_engine.py")
    else:
        error("Score gate 75 not found in "
              "scoring_engine.py — may have changed")

    generator = SCRIPTS / 'generate-picks-betfair.py'
    generator_content = generator.read_text(encoding='utf-8') if generator.exists() else ''
    if (
        'OFFICIAL_MIN_ODDS = 4.1' in generator_content
        and 'OFFICIAL_MAX_ODDS = 6.0' in generator_content
    ):
        ok("Official price band 4.1-6.0 present in generate-picks-betfair.py")
    else:
        error("Official price band 4.1-6.0 not found in generate-picks-betfair.py")

    if 'OFFICIAL_MAX_FIELD_SIZE = 14' in generator_content:
        ok("Official field-size ceiling 14 present in generate-picks-betfair.py")
    else:
        error("Official field-size ceiling 14 not found in generate-picks-betfair.py")


# ════════════════════════════════════════════════════════
# CHECK 10 — Each-way place terms are explicit for 4th+
# ════════════════════════════════════════════════════════

def check_each_way_place_terms() -> None:
    print(f"\n{BOLD}CHECK 10 — Each-way place terms{RESET}")

    issues = []
    for path in sorted(DATA.glob('2026-*.json')):
        d = load_json(path)
        if not d:
            continue
        r = d.get('results', {})
        if r.get('complete') is not True:
            continue
        for section in ('flat', 'jumps'):
            for pick in r.get(section, []) or []:
                if not isinstance(pick, dict):
                    continue
                position = int(pick.get('position') or 0)
                places_paid = int(
                    pick.get('placesPaid')
                    or pick.get('placePlaces')
                    or pick.get('eachWayPlaces')
                    or 0
                )
                if (
                    pick.get('result') == 'PLACED'
                    and position >= 4
                    and places_paid < position
                ):
                    issues.append(
                        f"{path.name}: {pick.get('name', '?')} is "
                        f"PLACED at {position}th but placesPaid={places_paid or 'missing'}"
                    )

    if issues:
        for issue in issues:
            error(issue)
    else:
        ok("No 4th-or-worse placed results without explicit places-paid proof")


# ════════════════════════════════════════════════════════
# CHECK 11 — Accountancy and dashboard totals agree
# ════════════════════════════════════════════════════════

def check_accountancy_totals() -> None:
    print(f"\n{BOLD}CHECK 11 — Accountancy totals and dashboard sync{RESET}")

    perf_path = REPO / 'performance.json'
    dash_perf_path = REPO / 'dashboard' / 'data' / 'performance.json'
    perf = load_json(perf_path)
    dash_perf = load_json(dash_perf_path)

    if not perf:
        error("performance.json missing or invalid")
        return

    daily_by_date = {}
    daily_count = 0

    for path in sorted(DATA.glob('2026-*.json')):
        day = load_json(path)
        if not day:
            continue
        results = day.get('results', {})
        if results.get('complete') is not True:
            continue
        day_stake = safe_float(results.get('totalStake'), 0)
        if day_stake <= 0:
            continue
        if not results.get('flat') and not results.get('jumps'):
            note = str(results.get('_note') or '').lower()
            if 'no official proof picks' in note or str(results.get('betType')).lower() == 'no_bet':
                continue
        day_return = safe_float(results.get('totalReturn', results.get('patentReturn')), 0)
        day_profit = safe_float(results.get('profit', results.get('totalProfit', results.get('patentProfit'))), 0)
        daily_count += 1

        bet_summary = results.get('betSummary') if isinstance(results.get('betSummary'), dict) else {}
        if bet_summary:
            summary_stake = money(bet_summary.get('totalStake'))
            summary_return = money(bet_summary.get('totalReturn'))
            summary_profit = money(bet_summary.get('totalProfit'))
            summary_lines = int(bet_summary.get('betLines') or 0)
            section_bets = [
                row for row in bet_summary.get('sectionBets', []) or []
                if isinstance(row, dict)
            ]
            section_stake = round(sum(money(row.get('totalStake')) for row in section_bets), 2)
            section_return = round(sum(money(row.get('return')) for row in section_bets), 2)
            section_profit = round(sum(money(row.get('profit')) for row in section_bets), 2)
            section_lines = sum(int(row.get('betLines') or 0) for row in section_bets)

            if abs(summary_stake - day_stake) > 0.02:
                error(
                    f"{path.name}: betSummary stake £{summary_stake:.2f} "
                    f"does not match daily stake £{day_stake:.2f}"
                )
            if abs(summary_return - day_return) > 0.02:
                error(
                    f"{path.name}: betSummary return £{summary_return:.2f} "
                    f"does not match daily return £{day_return:.2f}"
                )
            if abs(summary_profit - day_profit) > 0.02:
                error(
                    f"{path.name}: betSummary profit £{summary_profit:.2f} "
                    f"does not match daily profit £{day_profit:.2f}"
                )
            if section_bets:
                if abs(section_stake - summary_stake) > 0.02:
                    error(
                        f"{path.name}: section stakes total £{section_stake:.2f} "
                        f"but betSummary stake is £{summary_stake:.2f}"
                    )
                if abs(section_return - summary_return) > 0.02:
                    error(
                        f"{path.name}: section returns total £{section_return:.2f} "
                        f"but betSummary return is £{summary_return:.2f}"
                    )
                if abs(section_profit - summary_profit) > 0.02:
                    error(
                        f"{path.name}: section profits total £{section_profit:.2f} "
                        f"but betSummary profit is £{summary_profit:.2f}"
                    )
                if summary_lines and section_lines and section_lines != summary_lines:
                    error(
                        f"{path.name}: section bet lines total {section_lines} "
                        f"but betSummary lines are {summary_lines}"
                    )

            # Modern files can include rawReturn for each section. When present,
            # recalculate that section independently from the horse legs.
            for section_row in section_bets:
                if 'rawReturn' not in section_row:
                    continue
                section_name = section_row.get('section')
                rows = [
                    row for row in results.get(section_name, []) or []
                    if isinstance(row, dict)
                ]
                raw_return, raw_stake, raw_lines = ew_section_return(rows)
                raw_return_expected = money(section_row.get('rawReturn'))
                raw_stake_expected = money(section_row.get('rawStake'))
                raw_lines_expected = int(section_row.get('betLines') or 0)
                if abs(raw_return - raw_return_expected) > 0.02:
                    error(
                        f"{path.name}: {section_name} rawReturn £{raw_return_expected:.2f} "
                        f"but leg recalculation is £{raw_return:.2f}"
                    )
                if raw_stake_expected and abs(raw_stake - raw_stake_expected) > 0.02:
                    error(
                        f"{path.name}: {section_name} rawStake £{raw_stake_expected:.2f} "
                        f"but leg stake recalculation is £{raw_stake:.2f}"
                    )
                if raw_lines_expected and raw_lines != raw_lines_expected:
                    error(
                        f"{path.name}: {section_name} betLines {raw_lines_expected} "
                        f"but leg recalculation has {raw_lines}"
                    )
        else:
            # Legacy files did not always store enough bet metadata to prove the
            # doubles/trebles independently. They must still reconcile through
            # performance.json and dashboard totals, but this is not considered
            # full accountancy-grade evidence.
            if path.name >= '2026-07-15.json':
                warn(f"{path.name}: missing betSummary metadata for accountancy audit")

        if abs(day_profit - round(day_return - day_stake, 2)) > 0.02:
            error(
                f"{path.name}: profit £{day_profit:.2f} does not equal "
                f"return £{day_return:.2f} - stake £{day_stake:.2f}"
            )

        for section in ('flat', 'jumps'):
            for pick in results.get(section, []) or []:
                if not isinstance(pick, dict):
                    continue
                pick_name = pick.get('name') or '?'
                win_return = money(pick.get('winReturn'))
                place_return = money(pick.get('placeReturn'))
                total_return = money(pick.get('totalReturn'))
                if abs(total_return - round(win_return + place_return, 2)) > 0.02:
                    error(
                        f"{path.name}: {pick_name} totalReturn £{total_return:.2f} "
                        f"does not equal win £{win_return:.2f} + place £{place_return:.2f}"
                    )
                result = str(pick.get('result') or '').upper()
                if result == 'LOST' and (win_return > 0.02 or place_return > 0.02):
                    error(f"{path.name}: {pick_name} LOST but has return £{total_return:.2f}")
                if result == 'PLACED' and (win_return > 0.02 or place_return <= 0.0):
                    error(
                        f"{path.name}: {pick_name} PLACED should have £0 win and positive place return"
                    )
                if result == 'WON' and (win_return <= 0.0 or place_return <= 0.0):
                    error(
                        f"{path.name}: {pick_name} WON should have both win and place returns"
                    )

        daily_by_date[day.get('date') or path.stem] = {
            'stake': round(day_stake, 2),
            'return': round(day_return, 2),
            'profit': round(day_profit, 2),
        }

    ok(f"Recalculated and checked {daily_count} completed proof day(s)")

    scorecard_paths = sorted((DATA / 'public_scorecards').glob('scorecard_2026-*.json'))
    latest_scorecard = DATA / 'public_scorecards' / 'latest_scorecard.json'
    if latest_scorecard.exists():
        scorecard_paths.append(latest_scorecard)

    checked_scorecards = 0
    for scorecard_path in scorecard_paths:
        scorecard = load_json(scorecard_path)
        if not isinstance(scorecard, dict):
            error(f"{scorecard_path.name}: public scorecard is invalid JSON")
            continue
        scorecard_date = scorecard.get('date')
        if not scorecard_date:
            error(f"{scorecard_path.name}: public scorecard missing date")
            continue
        daily_row = daily_by_date.get(scorecard_date)
        if not daily_row:
            # Public scorecards can exist for older no-bet or legacy dates that
            # are not counted in proof. They should not block today's pipeline.
            continue
        checked_scorecards += 1
        scorecard_stake = money(scorecard.get('daily_stake'))
        scorecard_return = money(scorecard.get('return'))
        scorecard_profit = money(scorecard.get('profit'))
        if abs(scorecard_stake - daily_row['stake']) > 0.02:
            error(
                f"{scorecard_path.name}: public stake £{scorecard_stake:.2f} "
                f"does not match daily proof stake £{daily_row['stake']:.2f}"
            )
        if abs(scorecard_return - daily_row['return']) > 0.02:
            error(
                f"{scorecard_path.name}: public return £{scorecard_return:.2f} "
                f"does not match daily proof return £{daily_row['return']:.2f}"
            )
        if abs(scorecard_profit - daily_row['profit']) > 0.02:
            error(
                f"{scorecard_path.name}: public profit £{scorecard_profit:.2f} "
                f"does not match daily proof profit £{daily_row['profit']:.2f}"
            )

    if checked_scorecards:
        ok(f"Public scorecards match daily proof files ({checked_scorecards} checked)")
    else:
        warn("No public scorecards matched completed proof days")

    bookmaker_audits = load_json(BOOKMAKER_AUDITS) if BOOKMAKER_AUDITS.exists() else {}
    if isinstance(bookmaker_audits, dict) and bookmaker_audits:
        checked_audits = 0
        for audited_date, expected_row in sorted(bookmaker_audits.items()):
            if not isinstance(expected_row, dict):
                continue
            daily_row = daily_by_date.get(audited_date)
            if not daily_row:
                error(f"Bookmaker audit {audited_date}: no completed daily proof file found")
                continue
            expected_stake = money(expected_row.get('totalStake'))
            expected_return = money(expected_row.get('totalReturn'))
            expected_profit = money(expected_row.get('profit', expected_return - expected_stake))
            checked_audits += 1
            if abs(daily_row['stake'] - expected_stake) > 0.02:
                error(
                    f"Bookmaker audit {audited_date}: daily stake £{daily_row['stake']:.2f} "
                    f"does not match {expected_row.get('bookmaker', 'bookmaker')} stake £{expected_stake:.2f}"
                )
            if abs(daily_row['return'] - expected_return) > 0.02:
                error(
                    f"Bookmaker audit {audited_date}: daily return £{daily_row['return']:.2f} "
                    f"does not match {expected_row.get('bookmaker', 'bookmaker')} return £{expected_return:.2f}"
                )
            if abs(daily_row['profit'] - expected_profit) > 0.02:
                error(
                    f"Bookmaker audit {audited_date}: daily profit £{daily_row['profit']:.2f} "
                    f"does not match {expected_row.get('bookmaker', 'bookmaker')} profit £{expected_profit:.2f}"
                )
        if checked_audits:
            ok(f"Verified bookmaker settlement screenshots ({checked_audits} checked)")
    elif BOOKMAKER_AUDITS.exists():
        warn("bookmaker_settlement_audits.json exists but has no usable audits")

    log_stake = 0.0
    log_return = 0.0
    log_profit = 0.0
    log_days = 0
    missing_daily = []

    for entry in perf.get('selectionLog', []) or []:
        if not isinstance(entry, dict) or entry.get('complete') is not True:
            continue
        entry_stake = safe_float(entry.get('totalStake'), 0)
        entry_return = safe_float(entry.get('totalReturn', entry.get('patentReturn')), 0)
        entry_profit = safe_float(entry.get('totalProfit', entry.get('patentProfit')), 0)
        log_stake += entry_stake
        log_return += entry_return
        log_profit += entry_profit
        log_days += 1
        row = daily_by_date.get(entry.get('date'))
        if not row:
            missing_daily.append(entry.get('date'))
            continue
        if abs(entry_return - row['return']) > 0.02:
            error(
                f"selectionLog {entry.get('date')} return={entry_return} "
                f"but daily file return={row['return']}"
            )
        if abs(entry_profit - row['profit']) > 0.02:
            error(
                f"selectionLog {entry.get('date')} profit={entry_profit} "
                f"but daily file profit={row['profit']}"
            )

    if missing_daily:
        warn(f"selectionLog dates missing daily archive files: {missing_daily[:5]}")

    log_stake = round(log_stake, 2)
    log_return = round(log_return, 2)
    log_profit = round(log_profit, 2)
    log_roi = round((log_profit / log_stake) * 100, 1) if log_stake else 0.0

    expected = {
        'totalStaked': log_stake,
        'totalReturn': log_return,
        'totalProfit': log_profit,
        'roi': log_roi,
        'bettingDays': log_days,
    }
    for key, expected_value in expected.items():
        actual = safe_float(perf.get(key), 0)
        tolerance = 0.11 if key == 'roi' else 0.02
        if abs(actual - expected_value) > tolerance:
            error(f"performance.json {key}={actual} but selectionLog total {expected_value}")
        else:
            ok(f"performance.json {key} matches selectionLog ({expected_value})")

    if dash_perf:
        for key in ('totalStaked', 'totalReturn', 'totalProfit', 'roi', 'bettingDays'):
            actual = safe_float(dash_perf.get(key), 0)
            expected_value = safe_float(perf.get(key), 0)
            tolerance = 0.11 if key == 'roi' else 0.02
            if abs(actual - expected_value) > tolerance:
                error(
                    f"dashboard/data/performance.json {key}={actual} "
                    f"but performance.json has {expected_value}"
                )
            else:
                ok(f"dashboard performance {key} matches source")
    else:
        warn("dashboard/data/performance.json missing or invalid")



# ════════════════════════════════════════════════════════
# CHECK 12 — Protected files not modified
# ════════════════════════════════════════════════════════

def check_protected_files() -> None:
    print(f"\n{BOLD}CHECK 10 — Protected files status{RESET}")

    import subprocess

    protected = [
        'picks.json',
        'performance.json',
        'scripts/scoring_engine.py',
    ]

    for f in protected:
        result = subprocess.run(
            ['git', 'diff', '--stat', 'HEAD', f],
            capture_output=True,
            text=True,
            cwd=str(REPO)
        )
        if result.stdout.strip():
            warn(f"{f} has uncommitted changes — "
                 f"review before pushing")
        else:
            ok(f"{f} is clean")


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signal 75 system integrity validator"
    )
    parser.add_argument(
        '--post-race',
        action='store_true',
        help='Run post-race checks (settlement etc)'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Run all checks'
    )
    parser.add_argument(
        '--output',
        default='',
        help='Optional JSON report path'
    )
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*55}")
    print("SIGNAL 75 — SYSTEM INTEGRITY CHECK")
    print(f"{'='*55}{RESET}")
    print(f"Date: {date.today().isoformat()}")
    print(f"Time: {datetime.now().strftime('%H:%M')}")

    # Always run these
    check_picks()
    check_profit_fields()
    check_challenger_settlement(strict=args.post_race or args.full)
    check_challenger_odds()
    check_h2h_duplicates()
    check_challenger_status()
    check_pipeline_files()
    check_dashboard_sync()
    check_v1_settlement_quality()
    check_v1_price_band()
    check_field_graph_pre_race_only()
    check_score_gate()
    check_each_way_place_terms()
    check_accountancy_totals()

    # Post-race or full checks
    if args.post_race or args.full:
        check_post_race_settlement()
        check_protected_files()

    # Summary
    print(f"\n{BOLD}{'='*55}")
    print("SUMMARY")
    print(f"{'='*55}{RESET}")
    print(f"  {GREEN}✅ Passed:   {len(passes)}{RESET}")
    print(f"  {YELLOW}⚠️  Warnings: {len(warnings)}{RESET}")
    print(f"  {RED}❌ Errors:   {len(errors)}{RESET}")

    exit_code = 2 if errors else (1 if warnings else 0)
    check_type = "post_race" if args.post_race else ("full" if args.full else "pre_pick")
    report = {
        "date": date.today().isoformat(),
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "check_type": check_type,
        "mode": check_type,
        "status": "ERROR" if errors else "OK",
        "passed": len(passes),
        "warnings": len(warnings),
        "errors": len(errors),
        "passed_list": passes,
        "warning_list": warnings,
        "error_list": errors,
        "exit_code": exit_code,
    }
    output_path = Path(args.output) if args.output else DATA / f"integrity_check_{date.today().isoformat()}.json"
    if not output_path.is_absolute():
        output_path = REPO / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    latest_path = REPO / "dashboard" / "data" / "integrityStatus.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"  Report: {output_path.relative_to(REPO)}")
    print(f"  Dashboard copy: {latest_path.relative_to(REPO)}")

    if errors:
        print(f"\n{RED}{BOLD}ERRORS FOUND — "
              f"review before proceeding:{RESET}")
        for e in errors:
            print(f"  {RED}• {e}{RESET}")
        return 2

    if warnings:
        print(f"\n{YELLOW}Warnings — non-critical "
              f"but worth reviewing{RESET}")
        return 1

    print(f"\n{GREEN}{BOLD}All checks passed ✅{RESET}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
