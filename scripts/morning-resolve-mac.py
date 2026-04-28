#!/usr/bin/env python3
"""
Signal 75 — Morning Second Pass (Mac version)
Runs at 9am via launchd.
Checks yesterday's results for any remaining PENDING horses.
Tries to resolve them via AI web search.
If still unresolved, defaults to LOST (conservative).
Then marks day complete and regenerates performance.json.
"""

import os, json, re, subprocess, traceback, importlib.util
from datetime import date, datetime, timezone, timedelta

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
REPO_PATH = os.path.expanduser("~/Signal75")
ARCHIVE_FILE = os.path.join(REPO_PATH, "data", f"{YESTERDAY}.json")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
LOG_FILE = os.path.expanduser("~/signal75-resolve.log")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
STAKE_EW = 0.50

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

def get_positions(horses_needed):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    yesterday_display = (date.today() - timedelta(days=1)).strftime("%A %d %B %Y")
    prompt = (
        f"Racing date was {yesterday_display}. "
        f"Find finishing positions of these horses: {json.dumps(horses_needed)}. "
        f"Search attheraces.com, racingpost.com, sportinglife.com. "
        f"Return ONLY JSON: {{\"positions\":[{{\"name\":\"HORSE\",\"position\":1,\"ran\":9}}]}}. "
        f"position=0 if genuinely not found."
    )
    log(f"Searching for {len(horses_needed)} unresolved horse(s)...")
    message = client.messages.create(
        model="claude-haiku-4-5", max_tokens=800,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()
    if not response_text:
        raise ValueError("No response from AI")
    if "```" in response_text:
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if m: response_text = m.group(1)
    start = response_text.find('{')
    if start == -1: raise ValueError("No JSON in response")
    depth, end = 0, -1
    for i, c in enumerate(response_text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0: end = i + 1; break
    return json.loads(response_text[start:end])

def determine_result(position, runners):
    if position == 0: return "PENDING"
    if position == 1: return "WON"
    if runners < 8 and position == 2: return "PLACED"
    if 8 <= runners <= 11 and position <= 3: return "PLACED"
    if runners >= 12 and position <= 4: return "PLACED"
    return "LOST"

def run_performance():
    try:
        spec = importlib.util.spec_from_file_location(
            "gp", os.path.join(REPO_PATH, "scripts/generate-performance.py"))
        gp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gp)
        gp.main()
        log("✅ performance.json updated")
    except Exception as e:
        log(f"⚠️ performance.json failed: {e}")

def push_to_github():
    for cmd in [
        ["git", "-C", REPO_PATH, "pull", "--rebase", "--quiet"],
        ["git", "-C", REPO_PATH, "add",
         f"data/{YESTERDAY}.json", "picks.json", "performance.json"],
        ["git", "-C", REPO_PATH, "commit", "-m",
         f"Morning resolve — {YESTERDAY}"],
        ["git", "-C", REPO_PATH, "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            log(f"Warning: {r.stderr.strip()}")
    log("✅ Pushed to GitHub")

def main():
    log(f"\n{'='*50}\nSignal 75 Morning Resolve — {YESTERDAY}\n{'='*50}")

    if not os.path.exists(ARCHIVE_FILE):
        log(f"No archive file for {YESTERDAY} — nothing to resolve")
        return

    with open(ARCHIVE_FILE) as f:
        d = json.load(f)

    if d.get("noBetDay"):
        log("No bet day — nothing to resolve")
        return

    if d.get("results", {}).get("complete"):
        log("Day already complete — nothing to do")
        return

    # Find all PENDING horses
    horses_needed = []
    all_entries = []
    for race in d.get("flat", []):
        if race.get("horses"):
            h = race["horses"][0]
            if h.get("result") in ["PENDING", "", None]:
                horses_needed.append({
                    "name": h["name"],
                    "course": race["course"],
                    "time": race["time"]
                })
                all_entries.append({"tab": "flat", "race": race})

    for race in d.get("jumps", []):
        if race.get("horses"):
            h = race["horses"][0]
            if h.get("result") in ["PENDING", "", None]:
                horses_needed.append({
                    "name": h["name"],
                    "course": race["course"],
                    "time": race["time"]
                })
                all_entries.append({"tab": "jumps", "race": race})

    if not horses_needed:
        log("No PENDING horses found — marking complete")
    else:
        log(f"Found {len(horses_needed)} PENDING horse(s) to resolve")

        # Try to resolve via AI
        try:
            raw = get_positions(horses_needed)
            positions = {p["name"].upper(): p for p in raw.get("positions", [])}

            for entry in all_entries:
                race = entry["race"]
                h = race["horses"][0]
                name = h["name"].upper()
                pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
                pos = pd.get("position", 0)
                ran = pd.get("ran", race.get("runners", 8))
                odds = h.get("odds", 2.0)

                if pos == 0:
                    # Still unresolved — default to LOST conservatively
                    result_str = "LOST"
                    h["_note"] = "Unresolved after morning pass — defaulted to LOST (conservative)"
                    log(f"⚠️ {h['name']} still unresolved — defaulted to LOST")
                else:
                    result_str = determine_result(pos, ran)
                    log(f"✅ {h['name']} resolved: {result_str} (pos {pos}/{ran})")

                h["result"] = result_str
                h["position"] = pos

                # Update results array
                w, p, t = calculate_ew_return(odds, result_str, ran)
                results_list = d["results"].get(entry["tab"], [])
                # Find matching pending result entry
                for ro in results_list:
                    if ro.get("result") in ["PENDING", "", None]:
                        ro["result"] = result_str
                        ro["winReturn"] = w
                        ro["placeReturn"] = p
                        ro["totalReturn"] = t
                        if pos == 0:
                            ro["_note"] = "Defaulted to LOST — unresolved after morning pass"
                        break

        except Exception as e:
            log(f"⚠️ AI resolve failed: {e} — defaulting all remaining PENDING to LOST")
            # Default everything to LOST
            for entry in all_entries:
                h = entry["race"]["horses"][0]
                h["result"] = "LOST"
                h["_note"] = "AI resolve failed — defaulted to LOST (conservative)"
                for ro in d["results"].get(entry["tab"], []):
                    if ro.get("result") in ["PENDING", "", None]:
                        ro.update({"result":"LOST","winReturn":0.0,
                                   "placeReturn":0.0,"totalReturn":0.0,
                                   "_note":"AI resolve failed — defaulted to LOST"})

    # Mark day complete
    d["results"]["complete"] = True
    d["results"]["resolvedAt"] = datetime.now(timezone.utc).isoformat()
    d["results"]["_resolveNote"] = "Finalised by morning second pass"

    # Save archive
    with open(ARCHIVE_FILE, "w") as f:
        json.dump(d, f, indent=2)
    log(f"✅ {YESTERDAY}.json marked complete")

    # Update picks.json if it's still yesterday's picks
    try:
        with open(PICKS_FILE) as f:
            picks = json.load(f)
        if picks.get("date") == YESTERDAY:
            picks["results"] = d["results"]
            with open(PICKS_FILE, "w") as f:
                json.dump(picks, f, indent=2)
            log("✅ picks.json updated")
    except Exception as e:
        log(f"⚠️ picks.json update failed: {e}")

    # Regenerate performance.json
    run_performance()

    # Push everything
    push_to_github()

if __name__ == "__main__":
    main()
