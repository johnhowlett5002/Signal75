#!/usr/bin/env python3
"""
Signal 75 — Performance Tracker Generator
Reads all data/YYYY-MM-DD.json files and writes performance.json
SAFETY: Only completed days affect totals. Pending/incomplete excluded.
"""

import os, json, re
from datetime import date, datetime, timezone

REPO_PATH = os.path.expanduser("~/Signal75")
ARCHIVE_DIR = os.path.join(REPO_PATH, "data")
PERF_FILE = os.path.join(REPO_PATH, "performance.json")
PROOF_STAKE_EW = 1.00
LEGACY_ARCHIVE_STAKE_EW = 0.50
STAKE_PER_DAY = PROOF_STAKE_EW * 14
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

# ── FUTURE-PROOFING CONSTANTS ──────────────────────────────────────────────
PROOF_START    = "2026-05-24"  # Reset date — change this one line to start fresh
ENGINE_VERSION = "v1"          # Bump to "v2" when scoring_engine_v2 goes live
DATA_SOURCE    = "betfair_api" # Change if paid API added
ODDS_SOURCE    = "betfair_bsp" # Change if bookmaker odds used
# ──────────────────────────────────────────────────────────────────────────

def load_all_days():
    days = []
    for fname in sorted(os.listdir(ARCHIVE_DIR)):
        if not DATE_PATTERN.match(fname):
            continue
        fpath = os.path.join(ARCHIVE_DIR, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            days.append(data)
        except Exception as e:
            print(f"⚠️ Skipping {fname}: {e}")
    return days

def get_selections(day):
    names = []
    for race in day.get("flat", []) + day.get("jumps", []):
        horses = race.get("horses", [])
        if horses and horses[0].get("name"):
            names.append(horses[0]["name"])
        if len(names) >= 3:
            break
    return names

def get_selection_results(day):
    results = []
    for r in day.get("results", {}).get("flat", []) + day.get("results", {}).get("jumps", []):
        results.append(r.get("result", "PENDING"))
    return results[:3]

def proof_scale(day):
    results = day.get("results", {})
    source_stake = results.get("stakeEW") or results.get("stakePerLine") or LEGACY_ARCHIVE_STAKE_EW
    try:
        source_stake = float(source_stake)
    except Exception:
        source_stake = LEGACY_ARCHIVE_STAKE_EW
    if source_stake <= 0:
        source_stake = LEGACY_ARCHIVE_STAKE_EW
    return PROOF_STAKE_EW / source_stake

def proof_amount(day, value):
    try:
        return round(float(value or 0) * proof_scale(day), 2)
    except Exception:
        return 0.0

def proof_patent_return(day):
    return proof_amount(day, day.get("results", {}).get("patentReturn", 0))

def proof_patent_profit(day):
    return round(proof_patent_return(day) - STAKE_PER_DAY, 2)

def build_selection_log_entry(day):
    date_str = day.get("date", "")
    mode = day.get("mode", "")
    complete = day.get("results", {}).get("complete", False) is True
    patent_return = proof_patent_return(day)
    patent_profit = proof_patent_profit(day)
    flat_results = day.get("results", {}).get("flat", [])
    jumps_results = day.get("results", {}).get("jumps", [])
    selections = []
    for i, race in enumerate(day.get("flat", [])):
        horses = race.get("horses", [])
        if not horses: continue
        h = horses[0]
        res = flat_results[i] if i < len(flat_results) else {}
        selections.append({
            "tab": "flat",
            "name": h.get("name", ""),
            "course": race.get("course", ""),
            "time": race.get("time", ""),
            "type": race.get("type", "flat"),
            "distance": race.get("distance", ""),
            "runners": race.get("runners", 0),
            "odds": h.get("odds", 0),
            "badge": h.get("badge", ""),
            "signal_score": h.get("signal_score", 0),
            "jockey": h.get("jockey", ""),
            "form": h.get("formStr", ""),
            "result": res.get("result", h.get("result", "PENDING")),
            "position": res.get("position", h.get("position", 0)),
            "winReturn": proof_amount(day, res.get("winReturn", 0)),
            "placeReturn": proof_amount(day, res.get("placeReturn", 0)),
            "totalReturn": proof_amount(day, res.get("totalReturn", 0)),
            "engineVersion": h.get("engineVersion", ENGINE_VERSION),
            "dataSource": h.get("dataSource", DATA_SOURCE),
            "oddsSource": h.get("oddsSource", ODDS_SOURCE),
        })
    for i, race in enumerate(day.get("jumps", [])):
        horses = race.get("horses", [])
        if not horses: continue
        h = horses[0]
        res = jumps_results[i] if i < len(jumps_results) else {}
        selections.append({
            "tab": "jumps",
            "name": h.get("name", ""),
            "course": race.get("course", ""),
            "time": race.get("time", ""),
            "type": race.get("type", "jumps"),
            "distance": race.get("distance", ""),
            "runners": race.get("runners", 0),
            "odds": h.get("odds", 0),
            "badge": h.get("badge", ""),
            "signal_score": h.get("signal_score", 0),
            "jockey": h.get("jockey", ""),
            "form": h.get("formStr", ""),
            "result": res.get("result", h.get("result", "PENDING")),
            "position": res.get("position", h.get("position", 0)),
            "winReturn": proof_amount(day, res.get("winReturn", 0)),
            "placeReturn": proof_amount(day, res.get("placeReturn", 0)),
            "totalReturn": proof_amount(day, res.get("totalReturn", 0)),
            "engineVersion": h.get("engineVersion", ENGINE_VERSION),
            "dataSource": h.get("dataSource", DATA_SOURCE),
            "oddsSource": h.get("oddsSource", ODDS_SOURCE),
        })
    return {
        "date": date_str,
        "mode": mode,
        "complete": complete,
        "stakeEW": PROOF_STAKE_EW,
        "totalStake": STAKE_PER_DAY,
        "proofBasis": "£1 each-way Patent",
        "patentReturn": patent_return,
        "patentProfit": patent_profit,
        "selections": selections,
    }

def build_radar_log_entry(day):
    date_str = day.get("date", "")
    mode = day.get("mode", "")
    radar_rows = []
    seen = set()

    for tab, key in (("flat", "topRatedFlat"), ("jumps", "topRatedJumps")):
        for h in day.get(key, []) or []:
            name = h.get("name", "")
            ident = (tab, name.lower(), h.get("venue") or h.get("course") or "", h.get("time") or "")
            if not name or ident in seen:
                continue
            seen.add(ident)
            radar_rows.append({
                "tab": tab,
                "name": name,
                "course": h.get("venue") or h.get("course") or "",
                "time": h.get("time", ""),
                "race": h.get("race", ""),
                "type": h.get("race_type") or h.get("type") or tab,
                "odds": h.get("odds", 0),
                "signal_score": h.get("signal_score") or h.get("qualificationScore") or 0,
                "tipsters": h.get("tipsters", 0),
                "consensus": h.get("consensus", {}),
                "result": h.get("result", "PENDING"),
                "position": h.get("position", 0),
                "radarResult": h.get("radarResult", ""),
                "settled": h.get("radarSettled", False) is True,
            })

    if not radar_rows:
        return None

    settled = [r for r in radar_rows if r["settled"] or r["result"] in ("WON", "PLACED", "LOST", "VOID")]
    winners = sum(1 for r in settled if r["result"] == "WON")
    placed = sum(1 for r in settled if r["result"] == "PLACED")
    unplaced = sum(1 for r in settled if r["result"] == "LOST")
    pending = len(radar_rows) - len(settled)

    return {
        "date": date_str,
        "mode": mode,
        "complete": pending == 0,
        "note": "Radar watchlist only — not official proof and not included in ROI",
        "winners": winners,
        "placed": placed,
        "unplaced": unplaced,
        "pending": pending,
        "selections": radar_rows,
    }

def is_complete(day):
    return day.get("results", {}).get("complete", False) is True

def calc_win_rate(completed_days):
    if not completed_days: return 0
    winners = sum(1 for d in completed_days if d["profit"] > 0)
    return round((winners / len(completed_days)) * 100)

def get_streak(completed_days):
    streak = 0
    for d in reversed(completed_days):
        if d["profit"] > 0: streak += 1
        else: break
    return streak

def period_stats(completed_subset):
    if not completed_subset:
        return {"profit": 0, "days": 0, "winRate": 0}
    profit = round(sum(d["profit"] for d in completed_subset), 2)
    return {"profit": profit, "days": len(completed_subset), "winRate": calc_win_rate(completed_subset)}

def main():
    all_days = load_all_days()
    days = [d for d in all_days if d.get("date", "") >= PROOF_START]
    today = date.today().isoformat()
    total_days = len(days)
    no_bet_days = sum(1 for d in days if d.get("noBetDay", False))
    completed_days = []
    recent_display = []
    selection_log = []
    radar_log = []
    best_day = None

    for d in days:
        radar_entry = build_radar_log_entry(d)
        if radar_entry:
            radar_log.append(radar_entry)

        if d.get("noBetDay", False): continue
        if d.get("date", "") < PROOF_START: continue
        results = d.get("results", {})
        patent_return = proof_patent_return(d)
        profit = proof_patent_profit(d)
        horses = get_selections(d)
        horse_results = get_selection_results(d)
        complete = is_complete(d)
        entry = {"date": d.get("date",""), "profit": profit, "patentReturn": patent_return,
                 "horses": horses, "results": horse_results, "complete": complete}
        log_entry = build_selection_log_entry(d)
        selection_log.append(log_entry)
        if complete:
            completed_days.append(entry)
            if best_day is None or profit > best_day["profit"]:
                best_day = entry
        recent_display.append(entry)

    selection_log = list(reversed(selection_log))
    radar_log = list(reversed(radar_log))
    total_betting_days = len(completed_days)
    profitable_days = sum(1 for d in completed_days if d["profit"] > 0)
    total_staked = round(total_betting_days * STAKE_PER_DAY, 2)
    total_profit = round(sum(d["profit"] for d in completed_days), 2)
    total_return = round(total_staked + total_profit, 2)
    roi = round((total_profit / total_staked) * 100, 1) if total_staked > 0 else 0
    win_rate = calc_win_rate(completed_days)
    streak = get_streak(completed_days)

    all_selections = []
    for log_e in selection_log:
        if log_e["complete"]:
            all_selections.extend(log_e["selections"])
    total_selections = len(all_selections)
    total_winners = sum(1 for s in all_selections if s["result"] == "WON")
    total_placed = sum(1 for s in all_selections if s["result"] == "PLACED")
    flat_selections = [s for s in all_selections if s["tab"] == "flat"]
    jumps_selections = [s for s in all_selections if s["tab"] == "jumps"]
    flat_winners = sum(1 for s in flat_selections if s["result"] == "WON")
    jumps_winners = sum(1 for s in jumps_selections if s["result"] == "WON")

    last7  = period_stats(completed_days[-7:]  if len(completed_days) >= 7  else completed_days)
    last30 = period_stats(completed_days[-30:] if len(completed_days) >= 30 else completed_days)
    last90 = period_stats(completed_days[-90:] if len(completed_days) >= 90 else completed_days)
    recent = list(reversed(recent_display[-10:]))

    print(f"📊 Safety check:")
    print(f"   Completed days: {total_betting_days} | Profit: £{total_profit} | ROI: {roi}%")
    print(f"   Selections: {total_selections} | Winners: {total_winners} | Placed: {total_placed}")
    print(f"   Selection log entries: {len(selection_log)}")

    performance = {
        "updatedAt": today,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "proofBasis": {
            "stakeEW": PROOF_STAKE_EW,
            "betLines": 14,
            "dailyStake": STAKE_PER_DAY,
            "label": "£1 each-way Patent"
        },
        "totalDays": total_days,
        "noBetDays": no_bet_days,
        "bettingDays": total_betting_days,
        "profitableDays": profitable_days,
        "totalStaked": total_staked,
        "totalReturn": total_return,
        "totalProfit": total_profit,
        "roi": roi,
        "winRate": win_rate,
        "streak": streak,
        "bestDay": best_day,
        "last7": last7,
        "last30": last30,
        "last90": last90,
        "recentResults": recent,
        "selectionLog": selection_log,
        "radarLog": radar_log,
        "selectionStats": {
            "total": total_selections,
            "winners": total_winners,
            "placed": total_placed,
            "flatWinners": flat_winners,
            "jumpsWinners": jumps_winners,
            "flatTotal": len(flat_selections),
            "jumpsTotal": len(jumps_selections),
        }
    }

    with open(PERF_FILE, "w") as f:
        json.dump(performance, f, indent=2)
    print(f"✅ performance.json written")

if __name__ == "__main__":
    main()
