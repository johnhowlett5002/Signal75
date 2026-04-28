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
STAKE_PER_DAY = 7.0  # 50p EW patent = 7 bets
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")

def load_all_days():
    """Only load files matching YYYY-MM-DD.json — never performance.json"""
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
    """
    Get actual Signal 75 selections — top horse from each race group.
    Uses horses[0] from each race entry (the selected horse, not full racecard).
    Returns max 3 names.
    """
    names = []
    for race in day.get("flat", []) + day.get("jumps", []):
        horses = race.get("horses", [])
        if horses and horses[0].get("name"):
            names.append(horses[0]["name"])
        if len(names) >= 3:
            break
    return names

def get_selection_results(day):
    """Get results for actual selections only — max 3"""
    results = []
    for r in day.get("results", {}).get("flat", []) + day.get("results", {}).get("jumps", []):
        results.append(r.get("result", "PENDING"))
    return results[:3]

def is_complete(day):
    """Day must have results.complete == true to count in totals"""
    return day.get("results", {}).get("complete", False) is True

def calc_win_rate(completed_days):
    if not completed_days:
        return 0
    winners = sum(1 for d in completed_days if d["profit"] > 0)
    return round((winners / len(completed_days)) * 100)

def get_streak(completed_days):
    """Consecutive profitable days from most recent completed days only"""
    streak = 0
    for d in reversed(completed_days):
        if d["profit"] > 0:
            streak += 1
        else:
            break
    return streak

def period_stats(completed_subset):
    if not completed_subset:
        return {"profit": 0, "days": 0, "winRate": 0}
    profit = round(sum(d["profit"] for d in completed_subset), 2)
    win_r = calc_win_rate(completed_subset)
    return {"profit": profit, "days": len(completed_subset), "winRate": win_r}

def main():
    days = load_all_days()
    today = date.today().isoformat()

    total_days = len(days)
    no_bet_days = sum(1 for d in days if d.get("noBetDay", False))

    completed_days = []   # complete==true, used for all totals
    recent_display = []   # last 10 betting days including pending (display only)

    best_day = None

    for d in days:
        # Skip no bet days entirely
        if d.get("noBetDay", False):
            continue

        results = d.get("results", {})
        profit = round(results.get("patentProfit", 0) or 0, 2)
        patent_return = round(results.get("patentReturn", 0) or 0, 2)
        horses = get_selections(d)
        horse_results = get_selection_results(d)
        complete = is_complete(d)

        entry = {
            "date": d.get("date", ""),
            "profit": profit,
            "patentReturn": patent_return,
            "horses": horses,
            "results": horse_results,
            "complete": complete
        }

        # Only completed days affect performance totals
        if complete:
            completed_days.append(entry)
            if best_day is None or profit > best_day["profit"]:
                best_day = entry

        # All betting days (including pending) go to recent display
        recent_display.append(entry)

    # ── TOTALS — completed days only ──
    total_betting_days = len(completed_days)
    profitable_days = sum(1 for d in completed_days if d["profit"] > 0)
    total_staked = round(total_betting_days * STAKE_PER_DAY, 2)
    total_profit = round(sum(d["profit"] for d in completed_days), 2)
    total_return = round(total_staked + total_profit, 2)
    roi = round((total_profit / total_staked) * 100, 1) if total_staked > 0 else 0
    win_rate = calc_win_rate(completed_days)
    streak = get_streak(completed_days)

    # ── PERIOD STATS — completed days only ──
    last7  = period_stats(completed_days[-7:]  if len(completed_days) >= 7  else completed_days)
    last30 = period_stats(completed_days[-30:] if len(completed_days) >= 30 else completed_days)
    last90 = period_stats(completed_days[-90:] if len(completed_days) >= 90 else completed_days)

    # ── RECENT RESULTS — last 10 betting days, newest first, display only ──
    recent = list(reversed(recent_display[-10:]))

    # ── SAFETY CONFIRMATION ──
    print(f"📊 Safety check:")
    print(f"   Total files loaded:     {total_days}")
    print(f"   No bet days excluded:   {no_bet_days}")
    print(f"   Pending days excluded:  {len(recent_display) - len(completed_days)}")
    print(f"   Completed days counted: {total_betting_days}")
    print(f"   Total staked:           £{total_staked}")
    print(f"   Total profit:           £{total_profit}")
    print(f"   ROI:                    {roi}%")
    print(f"   Win rate:               {win_rate}%")
    print(f"   Streak:                 {streak}")

    performance = {
        "updatedAt": today,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
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
        "recentResults": recent
    }

    with open(PERF_FILE, "w") as f:
        json.dump(performance, f, indent=2)

    print(f"✅ performance.json written to repo root")

if __name__ == "__main__":
    main()
