#!/usr/bin/env python3
"""
field_relative_v1 — Field-Relative Scoring Challenger

Scores each horse relative to its specific field today rather than
in isolation. Combines the base Signal 75 score with:
  - Head-to-head evidence against today's actual rivals (SQLite)
  - Course affinity (wins/places at today's course)
  - Trainer course strike rate
  - Jockey course strike rate
  - Tipster convergence signals
  - Class movement (dropping/rising)
  - Freshness (days since last run)

ANALYSIS ONLY — never changes live picks, scores, proof or results.
Runs nightly after picks generate. Outputs challenger_field_relative_{date}.json.

Author: Signal 75 Intelligence Layer
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Repository paths ────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parents[1]
DATA       = REPO_ROOT / "data"
INTEL      = DATA / "horse_intelligence"
CHAL_DIR   = DATA / "challenger_lab"
CHAL_DIR.mkdir(parents=True, exist_ok=True)

# ── Databases (read-only always) ────────────────────────────────────────
SQLITE_H2H  = INTEL / "signal75_history.sqlite"
SQLITE_FORM = INTEL / "form_history.sqlite"

# ── Signal weights (tuned from 821k-run analysis) ──────────────────────
# These are starting weights. After 30+ settled days the Bayesian
# update loop will adjust them based on actual Signal 75 outcomes.
WEIGHTS: Dict[str, float] = {
    "h2h_beaten_rival":    3.0,   # per rival beaten in today's field
    "h2h_lost_to_rival":  -3.0,   # per rival that beat us in today's field
    "course_win":          4.0,   # previous win at today's course
    "course_place":        2.0,   # previous place (2nd/3rd) at today's course
    "cd_win":              2.0,   # additional bonus for course AND distance win
    "trainer_course_win":  1.5,   # per trainer win here (capped at 5)
    "jockey_course_win":   1.0,   # per jockey win here (capped at 5)
    "tipster_signal":      1.5,   # per tipster backing this horse (capped at 8)
    "class_drop":          3.0,   # dropping in class today
    "class_rise":         -3.0,   # rising in class today
    "freshness_penalty":  -2.0,   # 36-90 days off (from 821k-run analysis)
}

# ── Minimum score to be considered by this challenger ──────────────────
FIELD_SCORE_GATE = 70.0   # slightly lower than live gate (75) to catch
                           # horses the live system misses but field edge lifts


# ════════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ════════════════════════════════════════════════════════════════════════

def open_db(path: Path) -> Optional[sqlite3.Connection]:
    """Open SQLite in strict read-only mode. Returns None if missing."""
    if not path.exists():
        return None
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA query_only = ON")
    conn.row_factory = sqlite3.Row
    return conn


def h2h_edge(
    conn: sqlite3.Connection,
    horse_key: str,
    rival_keys: List[str],
) -> Tuple[int, int]:
    """
    Return (beaten_count, lost_to_count) for this horse against
    the specific rivals running in today's race.
    Uses the main Signal 75 SQLite head-to-head database.
    """
    if not rival_keys:
        return 0, 0

    placeholders = ",".join("?" * len(rival_keys))

    beaten = conn.execute(f"""
        SELECT COUNT(DISTINCT loser_key) FROM head_to_head
        WHERE winner_key = ?
        AND loser_key IN ({placeholders})
    """, [horse_key] + rival_keys).fetchone()[0]

    lost_to = conn.execute(f"""
        SELECT COUNT(DISTINCT winner_key) FROM head_to_head
        WHERE loser_key = ?
        AND winner_key IN ({placeholders})
    """, [horse_key] + rival_keys).fetchone()[0]

    return int(beaten or 0), int(lost_to or 0)


def course_record(
    conn: sqlite3.Connection,
    horse_key: str,
    course: str,
    distance: Optional[str] = None,
    lookback_days: int = 730,
) -> Dict[str, int]:
    """
    Return course win/place record for this horse.
    Uses form_history.sqlite form_results table.
    """
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()

    row = conn.execute("""
        SELECT
            COUNT(*) as runs,
            SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN CAST(position as INTEGER) BETWEEN 1 AND 3
                THEN 1 ELSE 0 END) as places
        FROM form_results
        WHERE horse_key = ?
        AND course = ?
        AND date >= ?
        AND CAST(position as INTEGER) > 0
    """, [horse_key, course, cutoff]).fetchone()

    result = {
        "runs":   int(row["runs"]   or 0),
        "wins":   int(row["wins"]   or 0),
        "places": int(row["places"] or 0),
    }

    # Course AND distance check
    if distance:
        cd = conn.execute("""
            SELECT SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END)
            FROM form_results
            WHERE horse_key = ? AND course = ? AND distance = ?
            AND date >= ? AND CAST(position as INTEGER) > 0
        """, [horse_key, course, distance, cutoff]).fetchone()[0]
        result["cd_wins"] = int(cd or 0)
    else:
        result["cd_wins"] = 0

    return result


def trainer_course_wins(
    conn: sqlite3.Connection,
    trainer: str,
    course: str,
    lookback_days: int = 365,
) -> int:
    """How many wins has this trainer had at this course in the last year?"""
    if not trainer:
        return 0
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    row = conn.execute("""
        SELECT COUNT(*) FROM form_results
        WHERE trainer = ? AND course = ? AND position = 1
        AND date >= ?
    """, [trainer, course, cutoff]).fetchone()
    return int(row[0] or 0)


def jockey_course_wins(
    conn: sqlite3.Connection,
    jockey: str,
    course: str,
    lookback_days: int = 365,
) -> int:
    """How many wins has this jockey had at this course in the last year?"""
    if not jockey:
        return 0
    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    row = conn.execute("""
        SELECT COUNT(*) FROM form_results
        WHERE jockey = ? AND course = ? AND position = 1
        AND date >= ?
    """, [jockey, course, cutoff]).fetchone()
    return int(row[0] or 0)


def last_run_date(
    conn: sqlite3.Connection,
    horse_key: str,
) -> Optional[str]:
    """Date of horse's most recent run in form_results."""
    row = conn.execute("""
        SELECT MAX(date) FROM form_results WHERE horse_key = ?
    """, [horse_key]).fetchone()
    return row[0] if row else None


# ════════════════════════════════════════════════════════════════════════
# FIELD EDGE CALCULATION
# ════════════════════════════════════════════════════════════════════════

def horse_key_from_name(name: str) -> str:
    """Normalise horse name to key format used in SQLite."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def days_since_last_run(last_date: Optional[str]) -> Optional[int]:
    """Days between last run and today."""
    if not last_date:
        return None
    try:
        d = datetime.strptime(last_date, "%Y-%m-%d").date()
        return (date.today() - d).days
    except ValueError:
        return None


def class_movement(
    current_class: Optional[str],
    prev_class: Optional[str],
) -> str:
    """
    Determine if horse is dropping, rising or same in class.
    UK classes: 1 (best) to 7 (weakest).
    Dropping = moving to higher class number = easier race.
    """
    def parse_class(c: Optional[str]) -> Optional[int]:
        if not c:
            return None
        m = re.search(r"\d", str(c))
        return int(m.group()) if m else None

    curr = parse_class(current_class)
    prev = parse_class(prev_class)

    if curr is None or prev is None:
        return "unknown"
    if curr > prev:
        return "drop"   # higher number = easier race
    if curr < prev:
        return "rise"   # lower number = harder race
    return "same"


def confidence_tier(
    field_score: float,
    tipsters: int,
    h2h_beaten: int,
    risk_count: int,
) -> str:
    """
    Derive a single confidence tier from combined signals.
    STRONG / SOLID / MODERATE / WEAK
    """
    if field_score >= 95 and tipsters >= 4 and h2h_beaten >= 1 and risk_count == 0:
        return "STRONG"
    if field_score >= 85 and (tipsters >= 2 or h2h_beaten >= 1) and risk_count <= 1:
        return "SOLID"
    if field_score >= 75:
        return "MODERATE"
    return "WEAK"


def build_reasons(edge: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Build plain-English top reasons and risks from edge signals.
    Returns (reasons, risks).
    """
    reasons = []
    risks   = []

    tips = edge.get("tipsters", 0)
    if tips >= 6:
        reasons.append(f"{tips} professional tipsters")
    elif tips >= 3:
        reasons.append(f"{tips} tipsters backing this horse")

    beaten = edge.get("h2h_beaten", 0)
    lost   = edge.get("h2h_lost_to", 0)
    if beaten >= 2:
        reasons.append(f"Beaten {beaten} rivals in today's field before")
    elif beaten == 1:
        reasons.append("Beaten a rival in today's field before")
    if lost >= 2:
        risks.append(f"{lost} rivals in this field have beaten it before")
    elif lost == 1:
        risks.append("A rival in this field has beaten it before")

    cw = edge.get("course_wins", 0)
    cp = edge.get("course_places", 0)
    cd = edge.get("cd_wins", 0)
    if cd >= 1:
        reasons.append("Course and distance winner")
    elif cw >= 2:
        reasons.append(f"Won at this course {cw} times before")
    elif cw == 1:
        reasons.append("Won at this course before")
    elif cp >= 2:
        reasons.append(f"Placed at this course {cp} times before")

    tw = edge.get("trainer_wins_here", 0)
    if tw >= 5:
        reasons.append(f"Trainer has {tw} wins here (12 months)")
    elif tw >= 3:
        reasons.append(f"Trainer strong at this course ({tw} wins)")

    jw = edge.get("jockey_wins_here", 0)
    if jw >= 5:
        reasons.append(f"Jockey has {jw} wins here (12 months)")
    elif jw >= 3:
        reasons.append(f"Jockey knows this course ({jw} wins)")

    mv = edge.get("class_movement", "unknown")
    if mv == "drop":
        reasons.append("Dropping in class today — easier race")
    elif mv == "rise":
        risks.append("Rising in class today — tougher race")

    days = edge.get("days_off")
    if days is not None and 36 <= days <= 90:
        risks.append(f"{days} days since last run — slightly below peak")
    elif days is not None and days > 90:
        reasons.append(f"Returning after break — trainer confident")

    return reasons[:4], risks[:3]


def calculate_field_edge(
    runner: Dict[str, Any],
    rival_keys: List[str],
    course: str,
    distance: Optional[str],
    h2h_conn: Optional[sqlite3.Connection],
    form_conn: Optional[sqlite3.Connection],
    weights: Dict[str, float],
) -> Dict[str, Any]:
    """
    Calculate the field-relative edge for a single runner.
    Returns a dict with each signal component and the total edge.
    """
    horse_name = runner.get("name", "")
    horse_key  = runner.get("horse_key") or horse_key_from_name(horse_name)
    trainer    = runner.get("trainer", "")
    jockey     = runner.get("jockey", "")
    tipsters   = int(runner.get("tipsters", 0) or 0)
    curr_class = runner.get("race_class") or runner.get("class")

    edge: Dict[str, Any] = {
        "horse":             horse_name,
        "horse_key":         horse_key,
        "h2h_beaten":        0,
        "h2h_lost_to":       0,
        "course_wins":       0,
        "course_places":     0,
        "cd_wins":           0,
        "trainer_wins_here": 0,
        "jockey_wins_here":  0,
        "tipsters":          tipsters,
        "class_movement":    "unknown",
        "days_off":          None,
        "signals":           [],
    }

    # ── H2H vs today's specific field ───────────────────────────────────
    if h2h_conn:
        beaten, lost_to = h2h_edge(h2h_conn, horse_key, rival_keys)
        edge["h2h_beaten"]  = beaten
        edge["h2h_lost_to"] = lost_to
        if beaten > 0:
            edge["signals"].append(
                f"Beaten {beaten} rival(s) in today's field")
        if lost_to > 0:
            edge["signals"].append(
                f"Previously beaten by {lost_to} rival(s) in today's field")

    # ── Course and distance record ───────────────────────────────────────
    if form_conn:
        cr = course_record(form_conn, horse_key, course, distance)
        edge["course_wins"]   = cr["wins"]
        edge["course_places"] = cr["places"]
        edge["cd_wins"]       = cr["cd_wins"]

        if cr["wins"] > 0:
            edge["signals"].append(
                f"Won at {course} before ({cr['wins']}x)")
        elif cr["places"] > 0:
            edge["signals"].append(
                f"Placed at {course} before ({cr['places']}x)")
        if cr["cd_wins"] > 0:
            edge["signals"].append(
                f"Course and distance winner at {course}")

        # Trainer and jockey course form
        tc = trainer_course_wins(form_conn, trainer, course)
        jc = jockey_course_wins(form_conn, jockey, course)
        edge["trainer_wins_here"] = tc
        edge["jockey_wins_here"]  = jc
        if tc >= 3:
            edge["signals"].append(
                f"Trainer has {tc} wins at {course} (12 months)")
        if jc >= 3:
            edge["signals"].append(
                f"Jockey has {jc} wins at {course} (12 months)")

        # Days since last run
        last  = last_run_date(form_conn, horse_key)
        edge["days_off"] = days_since_last_run(last)

        # Class movement
        if curr_class:
            prev_row = form_conn.execute("""
                SELECT race_class FROM form_results
                WHERE horse_key = ?
                AND CAST(position as INTEGER) > 0
                ORDER BY date DESC LIMIT 1
            """, [horse_key]).fetchone()
            prev_class = prev_row[0] if prev_row else None
            movement = class_movement(curr_class, prev_class)
            edge["class_movement"] = movement
            if movement == "drop":
                edge["signals"].append("Dropping in class today")
            elif movement == "rise":
                edge["signals"].append(
                    "Rising in class today — first time at level")

    # ── Tipsters ─────────────────────────────────────────────────────────
    if tipsters >= 3:
        edge["signals"].append(
            f"{tipsters} tipsters backing this horse")

    # ── Score components ─────────────────────────────────────────────────
    days = edge["days_off"]
    freshness_penalty = (
        weights["freshness_penalty"]
        if days is not None and 36 <= days <= 90
        else 0.0
    )

    field_size = max(len(rival_keys) + 1, 1)
    h2h_ratio = edge["h2h_beaten"] / field_size
    h2h_penalty = edge["h2h_lost_to"] / field_size
    h2h_score = (h2h_ratio * 24.0) - (h2h_penalty * 12.0)

    components = {
        "h2h": round(h2h_score, 1),
        "course": (
            edge["course_wins"]   * weights["course_win"] +
            edge["course_places"] * weights["course_place"] +
            edge["cd_wins"]       * weights["cd_win"]
        ),
        "trainer":  min(edge["trainer_wins_here"], 5) * weights["trainer_course_win"],
        "jockey":   min(edge["jockey_wins_here"],  5) * weights["jockey_course_win"],
        "tipsters": min(tipsters, 8) * weights["tipster_signal"],
        "class": (
            weights["class_drop"]  if edge["class_movement"] == "drop"
            else weights["class_rise"] if edge["class_movement"] == "rise"
            else 0.0
        ),
        "freshness": freshness_penalty,
    }

    total_edge = sum(components.values())
    edge["components"] = {k: round(v, 1) for k, v in components.items()}
    edge["total_edge"] = round(total_edge, 1)

    return edge


# ════════════════════════════════════════════════════════════════════════
# RACE PROCESSING
# ════════════════════════════════════════════════════════════════════════

def process_race(
    race: Dict[str, Any],
    h2h_conn: Optional[sqlite3.Connection],
    form_conn: Optional[sqlite3.Connection],
    weights: Dict[str, float],
) -> Optional[Dict[str, Any]]:
    """
    Process a single race and return field-relative scored runners.
    Returns None if race has insufficient data.
    """
    runners  = race.get("runners", [])
    course   = race.get("course", "")
    distance = race.get("distance") or race.get("race_name", "")
    time_str = race.get("time", "")

    if len(runners) < 4:
        return None

    # Build list of all horse keys in this race
    all_keys = [
        horse_key_from_name(r.get("name", ""))
        for r in runners
        if isinstance(r, dict) and r.get("name")
    ]

    scored_runners = []
    for runner in runners:
        if not isinstance(runner, dict) or not runner.get("name"):
            continue

        horse_name = runner["name"]
        base_score = float(runner.get("score", 0) or 0)
        odds       = float(runner.get("odds", 0) or 0)

        # Rivals = everyone except this horse
        horse_key_this = horse_key_from_name(horse_name)
        rival_keys = [k for k in all_keys if k != horse_key_this]

        # Calculate field edge
        edge = calculate_field_edge(
            runner, rival_keys, course, distance,
            h2h_conn, form_conn, weights,
        )

        # Compute field score
        field_score = round(base_score + edge["total_edge"], 1)

        # Build plain-English reasons and risks
        reasons, risks = build_reasons(edge)

        # Confidence tier
        tier = confidence_tier(
            field_score,
            edge["tipsters"],
            edge["h2h_beaten"],
            len(risks),
        )

        scored_runners.append({
            "name":           horse_name,
            "horse_key":      edge["horse_key"],
            "base_score":     base_score,
            "total_edge":     edge["total_edge"],
            "field_score":    field_score,
            "confidence":     tier,
            "odds":           odds,
            "status":         runner.get("status", "unknown"),
            "form":           runner.get("form", ""),
            "tipsters":       edge["tipsters"],
            "components":     edge["components"],
            "signals":        edge["signals"],
            "top_reasons":    reasons,
            "top_risks":      risks,
            "class_movement": edge["class_movement"],
            "days_off":       edge["days_off"],
            "h2h_beaten":     edge["h2h_beaten"],
            "h2h_lost_to":    edge["h2h_lost_to"],
            "course_wins":    edge["course_wins"],
            "course_places":  edge["course_places"],
            "cd_wins":        edge["cd_wins"],
        })

    if not scored_runners:
        return None

    # Sort by field score descending
    scored_runners.sort(key=lambda x: x["field_score"], reverse=True)

    # Challenger pick = highest field score above gate within odds range
    challenger_pick = next(
        (r for r in scored_runners
         if r["field_score"] >= FIELD_SCORE_GATE
         and 4.0 <= r["odds"] <= 7.5),
        None,
    )

    # Live official pick for comparison
    live_pick = next(
        (r for r in scored_runners if r["status"] == "official"),
        None,
    )

    same_as_live = (
        challenger_pick is not None
        and live_pick is not None
        and challenger_pick["name"] == live_pick["name"]
    )

    # Divergence case — most interesting to track
    divergence = (
        challenger_pick is not None
        and live_pick is not None
        and not same_as_live
    )

    return {
        "course":              course,
        "time":                time_str,
        "distance":            distance,
        "field_size":          len(runners),
        "runners":             scored_runners,
        "challenger_pick":     challenger_pick,
        "live_pick":           live_pick,
        "same_as_live":        same_as_live,
        "divergence":          divergence,
        "field_relative_top":  scored_runners[0]["name"] if scored_runners else None,
    }


# ════════════════════════════════════════════════════════════════════════
# PRE-RACE ARCHIVE
# ════════════════════════════════════════════════════════════════════════

def write_prerace_archive(
    date_str: str,
    picks: List[Dict[str, Any]],
    races: List[Dict[str, Any]],
) -> Path:
    """
    Write the pre-race snapshot archive.
    This file is NEVER modified after creation.
    Settlement writes a separate _settled.json file.
    """
    archive = {
        "date":           date_str,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "snapshot_type":  "pre_race",
        "settled":        False,
        "picks":          picks,
        "divergence_cases": [
            {
                "course":           r["course"],
                "time":             r["time"],
                "live_pick":        r["live_pick"]["name"] if r["live_pick"] else None,
                "challenger_pick":  r["challenger_pick"]["name"] if r["challenger_pick"] else None,
                "live_field_score": r["live_pick"]["field_score"] if r["live_pick"] else None,
                "chal_field_score": r["challenger_pick"]["field_score"] if r["challenger_pick"] else None,
            }
            for r in races if r.get("divergence")
        ],
    }

    out = DATA / f"field_relative_archive_{date_str}.json"
    out.write_text(json.dumps(archive, indent=2, default=str), encoding="utf-8")
    return out


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════

def run(date_str: str) -> Dict[str, Any]:
    """Run field_relative_v1 for a given date."""

    rc_path = DATA / f"race_comparison_{date_str}.json"
    if not rc_path.exists():
        return {"error": f"No race comparison found for {date_str}"}

    race_comparison = json.loads(rc_path.read_text(encoding="utf-8"))
    races           = race_comparison.get("races", [])

    if not races:
        return {"date": date_str, "races_processed": 0, "picks": []}

    h2h_conn  = open_db(SQLITE_H2H)
    form_conn = open_db(SQLITE_FORM)

    processed_races = []
    all_picks       = []
    same_count      = 0
    different_count = 0
    divergence_count = 0

    for race in races:
        result = process_race(race, h2h_conn, form_conn, WEIGHTS)
        if result is None:
            continue

        processed_races.append(result)

        if result["challenger_pick"]:
            pick = result["challenger_pick"].copy()
            pick["course"]        = result["course"]
            pick["time"]          = result["time"]
            pick["live_selected"] = result["same_as_live"]
            pick["divergence"]    = result["divergence"]
            all_picks.append(pick)

            if result["same_as_live"]:
                same_count += 1
            else:
                different_count += 1
                divergence_count += 1

    if h2h_conn:
        h2h_conn.close()
    if form_conn:
        form_conn.close()

    # Write pre-race archive
    write_prerace_archive(date_str, all_picks, processed_races)

    output = {
        "date":          date_str,
        "id":            "field_relative_v1",
        "name":          "Field-Relative Scorer",
        "analysis_only": True,
        "scoringImpact": "none",
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "weights_used":  WEIGHTS,
        "summary": {
            "races_processed":   len(processed_races),
            "challenger_picks":  len(all_picks),
            "same_as_live":      same_count,
            "different":         different_count,
            "divergence_cases":  divergence_count,
            "plain_english": (
                "Field-relative scoring compares each horse against its "
                "specific rivals today using head-to-head history, course "
                "affinity, trainer/jockey form and tipster signals. "
                "Divergence cases — where challenger differs from live — "
                "are tracked to measure whether field edge adds value."
            ),
        },
        "picks":  all_picks,
        "races":  processed_races,
    }

    out_path = CHAL_DIR / f"challenger_field_relative_{date_str}.json"
    out_path.write_text(
        json.dumps(output, indent=2, default=str),
        encoding="utf-8",
    )

    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="field_relative_v1 — Field-relative scoring challenger"
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Date to process (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed output including signal breakdown",
    )
    args = parser.parse_args()

    print(f"[field_relative_v1] Running for {args.date}")
    result = run(args.date)

    if "error" in result:
        print(f"[field_relative_v1] ERROR: {result['error']}")
        return

    summary = result.get("summary", {})
    picks   = result.get("picks", [])

    print(f"[field_relative_v1] Races processed:   {summary.get('races_processed')}")
    print(f"[field_relative_v1] Challenger picks:  {summary.get('challenger_picks')}")
    print(f"[field_relative_v1] Same as live:      {summary.get('same_as_live')}")
    print(f"[field_relative_v1] Different:         {summary.get('different')}")
    print(f"[field_relative_v1] Divergence cases:  {summary.get('divergence_cases')}")

    if args.verbose:
        print()
        for pick in picks:
            same = "SAME" if pick.get("live_selected") else "DIFFERENT"
            div  = " *** DIVERGENCE ***" if pick.get("divergence") else ""
            print(
                f"  [{same}]{div}"
                f"  {pick.get('course')} {pick.get('time')}:"
                f"  {pick['name']}"
                f"  base={pick['base_score']}"
                f"  edge={pick['total_edge']:+.1f}"
                f"  field={pick['field_score']}"
                f"  odds={pick['odds']}"
                f"  [{pick['confidence']}]"
            )
            for reason in pick.get("top_reasons", []):
                print(f"    ✓ {reason}")
            for risk in pick.get("top_risks", []):
                print(f"    ⚠ {risk}")
            comps = pick.get("components", {})
            if comps:
                parts = "  ".join(
                    f"{k}={v:+.1f}"
                    for k, v in comps.items()
                    if v != 0
                )
                print(f"    components: {parts}")
            print()

    archive = DATA / f"field_relative_archive_{args.date}.json"
    chal    = CHAL_DIR / f"challenger_field_relative_{args.date}.json"
    print(f"[field_relative_v1] Archive:  {archive}")
    print(f"[field_relative_v1] Challenger: {chal}")


if __name__ == "__main__":
    main()
