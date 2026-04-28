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
ARCHIVE_FILE = os.path.join(REPO_PATH, "data", f"{TODAY}.json")
LOG_FILE = os.path.expanduser("~/signal75-results.log")
STAKE_EW = 0.50
TOTAL_PATENT_STAKE = 7.0

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

def determine_result(position, runners):
    if position == 0: return "PENDING"
    if position == 1: return "WON"
    if runners < 8 and position == 2: return "PLACED"
    if 8 <= runners <= 11 and position <= 3: return "PLACED"
    if runners >= 12 and position <= 4: return "PLACED"
    return "LOST"

def get_positions(horses_needed):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    prompt = f"Today is {TODAY_DISPLAY}. Find finishing positions of these horses: {json.dumps(horses_needed)}. Search attheraces.com, racingpost.com, sportinglife.com. Return ONLY JSON: {{\"positions\":[{{\"name\":\"HORSE\",\"position\":1,\"ran\":9}}]}}. position=0 if not yet available."
    log("Searching for results...")
    message = client.messages.create(
        model="claude-haiku-4-5", max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()
    if not response_text: raise ValueError("No response")
    if "```" in response_text:
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if m: response_text = m.group(1)
    start = response_text.find('{')
    if start == -1: raise ValueError("No JSON")
    depth, end = 0, -1
    for i, c in enumerate(response_text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: end = i + 1; break
    return json.loads(response_text[start:end])

def push_to_github():
    for cmd in [
        ["git", "-C", REPO_PATH, "pull", "--rebase", "--quiet"],
        ["git", "-C", REPO_PATH, "add", "picks.json", f"data/{TODAY}.json", "performance.json"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"Results {TODAY_DISPLAY}"],
        ["git", "-C", REPO_PATH, "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            log(f"Warning: {r.stderr.strip()}")
    log("Pushed to GitHub!")

def main():
    log(f"\n{'='*50}\nSignal 75 Results - {TODAY_DISPLAY}\n{'='*50}")
    if not ANTHROPIC_KEY: log("ERROR: No API key"); return
    try:
        with open(PICKS_FILE) as f:
            picks = json.load(f)
        if picks.get("noBetDay"): log("No bet day"); return
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
        if not horses_needed: log("No horses to check"); return
        raw = get_positions(horses_needed)
        positions = {p["name"].upper(): p for p in raw.get("positions", [])}
        flat_r, jumps_r, flat_races, jumps_races = [], [], [], []
        for entry in all_entries:
            race = entry["race"]
            h = race["horses"][0]
            name = h["name"].upper()
            pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            pos = pd.get("position", 0)
            ran = pd.get("ran", race.get("runners", 8))
            odds = h.get("odds", 2.0)
            result_str = determine_result(pos, ran)
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
        picks["results"] = {"flat": flat_r, "jumps": jumps_r, "patentReturn": patent_return,
                           "patentProfit": patent_profit, "complete": complete,
                           "updatedAt": datetime.now(timezone.utc).isoformat()}
        with open(PICKS_FILE, "w") as f:
            json.dump(picks, f, indent=2)
        if os.path.exists(ARCHIVE_FILE):
            with open(ARCHIVE_FILE, "w") as f:
                json.dump(picks, f, indent=2)
        log(f"Patent: {patent_return} | Profit: {patent_profit} | Complete: {complete}")
        # Generate performance.json from all historical data
        try:
            spec = importlib.util.spec_from_file_location("gp", os.path.join(REPO_PATH, "scripts/generate-performance.py"))
            gp = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gp)
            gp.main()
            log("✅ performance.json updated")
        except Exception as pe:
            log(f"⚠️ performance.json failed: {pe}")
        push_to_github()
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
