#!/usr/bin/env python3
"""Signal 75 - Evening Results Updater (Mac version)"""
import os, json, re, subprocess, traceback, importlib.util
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
LOG_FILE = os.path.expanduser("~/signal75-results.log")
STAKE_EW = 0.50
TOTAL_PATENT_STAKE = 7.0


def normalise_name(name):
    """Lowercase, remove apostrophes and punctuation, collapse spaces."""
    n = name.lower()
    n = n.replace("'", "").replace("'", "")
    n = re.sub(r"[^a-z0-9 ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def calculate_ew_return(odds, result, runners):
    place_frac = 0.20 if runners >= 16 else 0.25
    win_profit = odds - 1
    if result == "WON":
        w = odds * STAKE_EW
        p = (1 + win_profit * place_frac) * STAKE_EW
    elif result == "PLACED":
        w, p = 0.0, (1 + win_profit * place_frac) * STAKE_EW
    elif result == "VOID":
        w, p = STAKE_EW, STAKE_EW  # stake returned
    else:
        w, p = 0.0, 0.0
    return round(w, 2), round(p, 2), round(w + p, 2)

def calculate_patent(flat_r, jumps_r, flat_races, jumps_races):
    all_r = flat_r + jumps_r
    all_races = flat_races + jumps_races
    if len(all_r) < 3:
        total = sum(r.get("totalReturn", 0) for r in all_r)
        return round(total, 2), round(total - len(all_r) * 2 * STAKE_EW, 2)
    picks_data = []
    for i, r in enumerate(all_r[:3]):
        odds = all_races[i]["horses"][0]["odds"] if i < len(all_races) and all_races[i].get("horses") else 2.0
        runners = all_races[i].get("runners", 8) if i < len(all_races) else 8
        w, p, _ = calculate_ew_return(odds, r.get("result", "LOST"), runners)
        picks_data.append({"win": w, "place": p})
    h1, h2, h3 = picks_data
    singles = sum(h["win"] + h["place"] for h in picks_data)
    d1w = (h1["win"] * h2["win"]) / STAKE_EW if h1["win"] and h2["win"] else 0
    d1p = (h1["place"] * h2["place"]) / STAKE_EW if h1["place"] and h2["place"] else 0
    d2w = (h1["win"] * h3["win"]) / STAKE_EW if h1["win"] and h3["win"] else 0
    d2p = (h1["place"] * h3["place"]) / STAKE_EW if h1["place"] and h3["place"] else 0
    d3w = (h2["win"] * h3["win"]) / STAKE_EW if h2["win"] and h3["win"] else 0
    d3p = (h2["place"] * h3["place"]) / STAKE_EW if h2["place"] and h3["place"] else 0
    doubles = d1w + d1p + d2w + d2p + d3w + d3p
    tw = (h1["win"] * h2["win"] * h3["win"]) / STAKE_EW**2 if all(h["win"] for h in picks_data) else 0
    tp = (h1["place"] * h2["place"] * h3["place"]) / STAKE_EW**2 if all(h["place"] for h in picks_data) else 0
    total = round(singles + doubles + tw + tp, 2)
    return total, round(total - TOTAL_PATENT_STAKE, 2)

def determine_result(position, status, runners):
    """Determine result from position, status code, and field size."""
    s = str(status).upper().strip() if status else ""
    # Non-runners
    if s in ("NR", "NON-RUNNER", "WITHDRAWN", "W", "VOID"):
        return "VOID"
    # Racing mishaps — all count as lost for patent
    if s in ("PU", "PULLED UP", "F", "FELL", "UR", "UNSEATED", "BD", "BROUGHT DOWN", "RO", "RAN OUT", "SU", "SLIPPED UP", "REF", "REFUSED"):
        return "LOST"
    # Numeric position
    pos = int(position) if position else 0
    if pos == 0:
        return "PENDING"
    if pos == 1:
        return "WON"
    if runners < 8 and pos == 2:
        return "PLACED"
    if 8 <= runners <= 11 and pos <= 3:
        return "PLACED"
    if runners >= 12 and pos <= 4:
        return "PLACED"
    return "LOST"


def get_positions(horses_needed, race_date):
    """Search for finishing positions. race_date = YYYY-MM-DD of the race."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    names = [h["name"] for h in horses_needed]
    race_date_display = datetime.strptime(race_date, "%Y-%m-%d").strftime("%A %d %B %Y")
    names_with_details = []
    for h in horses_needed:
        detail = h["name"]
        if h.get("course"): detail += " (" + h.get("time","") + " " + h.get("course","") + ")"
        names_with_details.append(detail)
    prompt = (
        "Find official race results for these UK racehorses from " + race_date_display + ": "
        + ", ".join(names_with_details)
        + ". Check racingpost.com and sportinglife.com official results. "
        + "For each horse return: finishing position (number), status (NR if non-runner, PU if pulled up, F if fell, UR if unseated, BD if brought down, OK if finished), and number of runners. "
        + 'Return ONLY JSON: {"positions":[{"name":"HORSE","position":3,"status":"OK","ran":12}]}. '
        + "Use position=0 and status=NR for non-runners. Use position=0 and status=PU for pulled up. "
        + "Only use position=0 and status=PENDING if result genuinely not yet available. Include ALL horses."
    )
    log("Searching for results...")
    message = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=800,
        system="You are a JSON API. Return only valid JSON, nothing else.",
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text += block.text
    response_text = response_text.strip()
    log(f"Results response: {len(response_text)} chars")
    log(f"Preview: {response_text[:300]}")
    if not response_text:
        raise ValueError("No response from API")
    response_text = re.sub(r"```(?:json)?\s*", "", response_text)
    response_text = re.sub(r"```", "", response_text).strip()
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON found in response")
    result = json.loads(response_text[start:end+1])
    log(f"Found positions for {len(result.get('positions', []))} horses")
    return result

def push_to_github(race_date):
    archive_path = f"data/{race_date}.json"
    for cmd in [
        ["git", "-C", REPO_PATH, "pull", "--rebase", "--quiet"],
        ["git", "-C", REPO_PATH, "add", "picks.json", archive_path, "performance.json"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"Results {race_date}"],
        ["git", "-C", REPO_PATH, "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            log(f"Warning: {r.stderr.strip()}")
    log("Pushed to GitHub!")

def main():
    log(f"\n{'='*50}\nSignal 75 Results - {TODAY_DISPLAY}\n{'='*50}")
    if not ANTHROPIC_KEY:
        log("ERROR: No API key"); return
    try:
        with open(PICKS_FILE) as f:
            picks = json.load(f)

        mode = picks.get("mode", "")
        if picks.get("noBetDay"):
            log(f"Mode=noBetDay — skipping results"); return

        # Radar Results: on topRatedOnly days, look up positions for topRated horses only
        if mode == "topRatedOnly":
            top_rated = picks.get("topRated", [])
            if not top_rated:
                log("topRatedOnly but no topRated horses — skipping"); return
            horses_needed = [{"name": h["name"], "course": h.get("course",""), "time": h.get("time","")} for h in top_rated]
            raw = get_positions(horses_needed, picks.get("date", TODAY))
            positions = {normalise_name(p["name"]): p for p in raw.get("positions", [])}
            for h in top_rated:
                pd = positions.get(normalise_name(h["name"]), {})
                pos = pd.get("position", 0)
                status = pd.get("status", "PENDING")
                if status == "PENDING" or pos == 0 and status not in ("NR","PU","F","UR","BD"):
                    h["radarResult"] = "PENDING"
                elif status == "NR":
                    h["radarResult"] = "Non-Runner"
                elif pos == 1:
                    h["radarResult"] = "1st 🏆"
                elif pos == 2:
                    h["radarResult"] = "2nd"
                elif pos == 3:
                    h["radarResult"] = "3rd"
                else:
                    h["radarResult"] = f"{pos}th"
                    h["radarResult"] = f"{pos}th"
            picks["topRated"] = top_rated
            # Also update topRatedFlat and topRatedJumps by name match
            result_map = {normalise_name(h["name"]): h.get("radarResult","PENDING") for h in top_rated}
            for arr_key in ["topRatedFlat", "topRatedJumps"]:
                for h in picks.get(arr_key, []):
                    key = normalise_name(h["name"])
                    if key in result_map:
                        h["radarResult"] = result_map[key]
            with open(PICKS_FILE, "w") as f:
                json.dump(picks, f, indent=2)
            push_to_github(picks.get("date", TODAY))
            log("Radar results saved and pushed")
            return

        horses_needed, all_entries = [], []
        for race in picks.get("flat", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_entries.append({"tab": "flat", "race": race})
        for race in picks.get("jumps", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_entries.append({"tab": "jumps", "race": race})

        if not horses_needed:
            log("No horses to check"); return

        raw = get_positions(horses_needed, race_date)
        positions = {normalise_name(p["name"]): p for p in raw.get("positions", [])}

        flat_r, jumps_r, flat_races, jumps_races = [], [], [], []
        for entry in all_entries:
            race = entry["race"]
            h = race["horses"][0]
            name = normalise_name(h["name"])
            pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            pos = pd.get("position", 0)
            ran = pd.get("ran", race.get("runners", 8))
            odds = h.get("odds", 2.0)
            result_str = determine_result(pos, pd.get("status", ""), ran)
            w, p, t = calculate_ew_return(odds, result_str, ran)
            ro = {"position": pos, "result": result_str, "winReturn": w, "placeReturn": p, "totalReturn": t}
            h["result"] = result_str
            h["position"] = pos
            if entry["tab"] == "flat":
                flat_r.append(ro); flat_races.append(race)
            else:
                jumps_r.append(ro); jumps_races.append(race)

        patent_return, patent_profit = calculate_patent(flat_r, jumps_r, flat_races, jumps_races)
        complete = all(r["result"] not in ["", "PENDING"] for r in flat_r + jumps_r)

        picks["results"] = {
            "flat": flat_r, "jumps": jumps_r,
            "patentReturn": patent_return, "patentProfit": patent_profit,
            "complete": complete,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }

        with open(PICKS_FILE, "w") as f:
            json.dump(picks, f, indent=2)
        if os.path.exists(archive_file):
            with open(archive_file, "w") as f:
                json.dump(picks, f, indent=2)

        log(f"Patent: {patent_return} | Profit: {patent_profit} | Complete: {complete}")

        try:
            spec = importlib.util.spec_from_file_location("gp", os.path.join(REPO_PATH, "scripts/generate-performance.py"))
            gp = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gp)
            gp.main()
            log("✅ performance.json updated")
        except Exception as pe:
            log(f"⚠️ performance.json failed: {pe}")

        push_to_github(race_date)

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
