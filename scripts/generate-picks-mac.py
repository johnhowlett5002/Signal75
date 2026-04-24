#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator (Mac version)
Multi-source free data + resilient scoring
Runs on Mac at 10am via launchd
"""

import os, json, re, subprocess, traceback
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
ARCHIVE_DIR = os.path.join(REPO_PATH, "data")
ARCHIVE_FILE = os.path.join(ARCHIVE_DIR, f"{TODAY}.json")
LOG_FILE = os.path.expanduser("~/signal75-picks.log")

# Hard rules — enforced in Python, non-negotiable
MIN_ODDS = 2.1
MAX_ODDS = 10.0
MIN_RUNNERS = 6
MAX_RUNNERS = 16

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def enforce_rules(picks):
    """Remove any horse failing hard rules. Python enforced — not prompt."""
    cleaned_flat, cleaned_jumps, removed = [], [], []
    for race in picks.get("flat", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"FLAT {race.get('course')}: {runners} runners — REMOVED")
            continue
        if not race.get("horses"): continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS or odds > MAX_ODDS:
            removed.append(f"FLAT {h.get('name')}: odds {odds} — REMOVED")
            continue
        cleaned_flat.append(race)
    for race in picks.get("jumps", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"JUMPS {race.get('course')}: {runners} runners — REMOVED")
            continue
        if not race.get("horses"): continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS or odds > MAX_ODDS:
            removed.append(f"JUMPS {h.get('name')}: odds {odds} — REMOVED")
            continue
        cleaned_jumps.append(race)
    for msg in removed:
        log(f"   REMOVED: {msg}")
    picks["flat"] = cleaned_flat[:3]
    picks["jumps"] = cleaned_jumps[:3]
    blank = {"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}
    picks["results"]["flat"] = [blank.copy() for _ in range(len(picks["flat"]))]
    picks["results"]["jumps"] = [blank.copy() for _ in range(len(picks["jumps"]))]
    if not picks["flat"] and not picks["jumps"]:
        picks["noBetDay"] = True
        picks["noBetReason"] = "No horses met qualifying criteria today."
    return picks

def generate_picks():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Today is {TODAY_DISPLAY}. You are Signal 75's AI racing analyst.

Search ALL of these sources for today's UK racing:
1. sportinglife.com/racing/racecards - today's cards and NAPs
2. attheraces.com/racecards - runners, odds, tips
3. racingpost.com/racecards - form, ratings, tips
4. gg.co.uk - expert verdicts and tips
5. sunracing.co.uk - daily NAPs
6. mirror.co.uk/sport/racing - tips and NAPs
7. oddschecker.com - compare bookmaker odds to spot steamers

For today's UK flat and jumps races, find the best selections using this RESILIENT scoring system.

IMPORTANT: Missing data is NOT a failure. Score what you can find. A horse with strong market movement and good form is a valid pick even without full tipster data.

SCORING SIGNALS (use what you can find — estimate where data is unavailable):

Signal 1 — MARKET MOVEMENT (25% weight) — MOST IMPORTANT
Search oddschecker or multiple bookmakers. Is the price shortening (steamer) or drifting?
- Strong steamer (20%+ odds drop): 95 + 15 bonus points
- Mild steamer (5-20% drop): 75
- Stable: 50
- Drifter: 20 — 15 penalty
- Cannot find: estimate 50 (neutral)

Signal 2 — TIPSTER CONSENSUS (20% weight)
Count mentions across ALL 7 sources above. NAP = counts double.
- NAP on 2+ sources: 100
- Tipped on 3+ sources: 85
- Tipped on 2 sources: 70
- Tipped on 1 source: 55
- Not tipped anywhere found: 35 (not zero — data may be missing)

Signal 3 — GOING PREFERENCE (15% weight)
Has horse won on today's going before?
- 3+ wins on this going: 100
- 2 wins: 80
- 1 win: 65
- Ran on it, not won: 35
- Unknown: 45 (estimate — not zero)

Signal 4 — ODDS SWEET SPOT (13% weight)
Best each-way patent value:
- 4.0-6.0 decimal: 100
- 3.0-4.0: 80
- 6.0-8.0: 70
- 2.5-3.0: 55
- 8.0-10.0: 40
- Outside 2.1-10.0: HARD DISQUALIFY

Signal 5 — RECENT FORM (12% weight)
Last 3 runs weighted 5/3/1:
- W=full, P=half, F/U=zero
- Back to back wins: +8 bonus
- Unknown form: 40 (estimate)

Signal 6 — COURSE AND DISTANCE (10% weight)
- Won at both: 100
- Course only: 65
- Distance only: 55
- Neither: 30
- Unknown: 40

Signal 7 — TRAINER FORM (5% weight)
- Known in-form trainer: 85
- Average: 50
- Unknown: 50

COMPOSITE = (s1x25 + s2x20 + s3x15 + s4x13 + s5x12 + s6x10 + s7x5) / 100
Apply steamer/drifter bonus/penalty
Minimum qualifying score: 52 (lowered to allow picks with partial data)

SELECTION:
- Pick best horse from each qualifying race
- Up to 3 flat picks from 3 different races
- Up to 3 jumps picks from 3 different races
- Confidence: "high" (score 70+), "medium" (55-69), "each-way" (52-54)
- ALWAYS pick if horses qualify — partial data picks are valid

REASON: One sentence plain English for a complete beginner. Mention the strongest signal you found.

Return ONLY valid JSON:
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"HH:MM","course":"Course","type":"flat","distance":"1m","going":"good","runners":9,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":4.5,"prevOdds":5.5,"tipsters":5,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":95,"confidence":"high","reason":"Plain English reason.","result":"","position":0}}]}}],"jumps":[{{"time":"HH:MM","course":"Course","type":"chase","distance":"2m4f","going":"soft","runners":8,"horses":[{{"num":2,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":5.0,"prevOdds":6.0,"tipsters":4,"formStr":"WWWPW","goingWins":3,"goingRuns":5,"courseWins":2,"distanceWins":2,"trainerInForm":true,"rpr":145,"confidence":"high","reason":"Plain English reason.","result":"","position":0}}]}}],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""

    log("🔍 Searching 7 sources: Racing Post, Sporting Life, At The Races, GG, Sun Racing, Mirror, Oddschecker...")

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()

    log(f"📝 Response: {len(response_text)} chars")
    log(f"📝 Preview: {response_text[:300]}")

    if not response_text:
        raise ValueError("No response from Claude")

    if "```" in response_text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if match:
            response_text = match.group(1)

    start = response_text.find('{')
    if start == -1:
        raise ValueError("No JSON found")

    depth, end = 0, -1
    for i, c in enumerate(response_text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    picks = json.loads(response_text[start:end])
    assert "date" in picks and "flat" in picks and "jumps" in picks
    picks["date"] = TODAY
    picks["generatedAt"] = datetime.now(timezone.utc).isoformat()
    picks = enforce_rules(picks)
    return picks

def write_archive(picks):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    if os.path.exists(ARCHIVE_FILE):
        log(f"⚠️  Archive exists for {TODAY} — not overwriting morning file")
        return
    with open(ARCHIVE_FILE, "w") as f:
        json.dump(picks, f, indent=2)
    log(f"✅ Archive written: data/{TODAY}.json")

def push_to_github(picks):
    write_archive(picks)
    with open(PICKS_FILE, "w") as f:
        json.dump(picks, f, indent=2)
    log("✅ picks.json written")
    cmds = [
        ["git", "-C", REPO_PATH, "pull", "--quiet"],
        ["git", "-C", REPO_PATH, "add", "picks.json", f"data/{TODAY}.json"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"Auto picks {TODAY_DISPLAY}"],
        ["git", "-C", REPO_PATH, "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout + result.stderr:
            log(f"⚠️  {' '.join(cmd[2:])}: {result.stderr.strip()}")
        else:
            log(f"✅ {' '.join(cmd[2:])}")
    log("🚀 Pushed! signal75.co.uk updating...")

def write_no_bet(reason):
    picks = {"date": TODAY, "generatedAt": datetime.now(timezone.utc).isoformat(),
             "noBetDay": True, "noBetReason": reason, "flat": [], "jumps": [],
             "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}}
    write_archive(picks)
    with open(PICKS_FILE, "w") as f:
        json.dump(picks, f, indent=2)
    subprocess.run(["git", "-C", REPO_PATH, "add", "picks.json", f"data/{TODAY}.json"], capture_output=True)
    subprocess.run(["git", "-C", REPO_PATH, "commit", "-m", f"No bet {TODAY}"], capture_output=True)
    subprocess.run(["git", "-C", REPO_PATH, "push"], capture_output=True)

def main():
    log(f"\n{'='*50}")
    log(f"🏇 Signal 75 — {TODAY_DISPLAY}")
    log(f"{'='*50}")
    if not ANTHROPIC_KEY:
        log("❌ No API key")
        return

    # Once per day lock
    if os.path.exists(PICKS_FILE):
        try:
            with open(PICKS_FILE) as f:
                existing = json.load(f)
            if existing.get("date") == TODAY and not existing.get("noBetDay"):
                log(f"✅ Picks already done for {TODAY} — skipping")
                log("   Delete picks.json to force regenerate")
                return
        except: pass

    try:
        picks = generate_picks()
        if picks.get("noBetDay"):
            log(f"🚫 No bet: {picks.get('noBetReason','')}")
        else:
            log(f"✅ {len(picks.get('flat',[]))} flat, {len(picks.get('jumps',[]))} jumps picks")
            for r in picks.get("flat", []):
                h = r["horses"][0] if r.get("horses") else None
                if h: log(f"   FLAT  {r['time']} {r['course']}: {h['name']} @ {h['odds']} [{h.get('confidence','?')}]")
            for r in picks.get("jumps", []):
                h = r["horses"][0] if r.get("horses") else None
                if h: log(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']} [{h.get('confidence','?')}]")
        push_to_github(picks)
    except Exception as e:
        log(f"❌ {type(e).__name__}: {e}")
        log(traceback.format_exc())
        write_no_bet("System error — check back tomorrow.")

if __name__ == "__main__":
    main()
