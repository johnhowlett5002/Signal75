#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator (Mac version)
Runs on Mac at 10am via launchd
Uses Claude with web search to find real UK racing data
Enforces all Signal 75 rules in Python — not in prompt
Writes picks.json + daily archive /data/YYYY-MM-DD.json
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

# ── HARD RULES (enforced in Python — not negotiable) ────────────
MIN_ODDS = 2.1        # Below this = disqualified
MAX_ODDS = 10.0       # Above this = disqualified
MIN_RUNNERS = 6       # Below this = race disqualified
MAX_RUNNERS = 16      # Above this = race disqualified
MIN_SCORE = 55        # Below this = not picked
# ────────────────────────────────────────────────────────────────

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def enforce_rules(picks):
    """
    Hard Python enforcement of all Signal 75 rules.
    Removes any horse that fails the rules AFTER Claude returns them.
    This is the safety net — rules are enforced here regardless of what Claude returns.
    """
    cleaned_flat = []
    cleaned_jumps = []
    removed = []

    for race in picks.get("flat", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"FLAT {race.get('time')} {race.get('course')}: field size {runners} — REMOVED")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS:
            removed.append(f"FLAT {race.get('time')} {race.get('course')}: {h.get('name')} odds {odds} below {MIN_ODDS} — REMOVED")
            continue
        if odds > MAX_ODDS:
            removed.append(f"FLAT {race.get('time')} {race.get('course')}: {h.get('name')} odds {odds} above {MAX_ODDS} — REMOVED")
            continue
        cleaned_flat.append(race)

    for race in picks.get("jumps", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"JUMPS {race.get('time')} {race.get('course')}: field size {runners} — REMOVED")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS:
            removed.append(f"JUMPS {race.get('time')} {race.get('course')}: {h.get('name')} odds {odds} below {MIN_ODDS} — REMOVED")
            continue
        if odds > MAX_ODDS:
            removed.append(f"JUMPS {race.get('time')} {race.get('course')}: {h.get('name')} odds {odds} above {MAX_ODDS} — REMOVED")
            continue
        cleaned_jumps.append(race)

    for msg in removed:
        log(f"   🚫 {msg}")

    picks["flat"] = cleaned_flat[:3]   # Max 3 flat picks
    picks["jumps"] = cleaned_jumps[:3] # Max 3 jumps picks

    # Fix results arrays to match actual pick count
    flat_count = len(picks["flat"])
    jumps_count = len(picks["jumps"])
    blank = {"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}
    picks["results"]["flat"] = [blank.copy() for _ in range(flat_count)]
    picks["results"]["jumps"] = [blank.copy() for _ in range(jumps_count)]

    # If nothing qualifies, mark as no bet day
    if flat_count == 0 and jumps_count == 0:
        picks["noBetDay"] = True
        picks["noBetReason"] = "No horses met the Signal 75 qualifying criteria today. All picks require odds between 2.1 and 10.0 and fields of 6-16 runners."

    return picks

def generate_picks():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Today is {TODAY_DISPLAY}. You are Signal 75's horse racing analyst.

Search these sources for today's UK racing:
- sportinglife.com/racing/racecards
- attheraces.com/racecards
- racingpost.com/racecards
- gg.co.uk racecards

For each UK flat and jumps race today, find the best selection using these signals:

1. Market movement — odds shortening (steamer) or drifting
2. Tipster mentions — how many sources tip this horse
3. Going form — wins on today's going
4. Odds range — 4.0-6.0 decimal is ideal
5. Recent form — last 3 runs
6. Course and distance — previous wins here
7. Trainer form — trainer in good form
8. Field size — number of runners

Pick the best horse from each qualifying race.
Select up to 3 flat picks and up to 3 jumps picks.
If a race has very short-priced horses (below 2.1) or very few runners (below 6), note it but still try to find better races.

The confidence field must be: "high" (strong pick), "medium" (decent pick), or "each-way" (speculative).

The reason must be one plain English sentence for someone who has never bet before.

Return ONLY valid JSON — no other text:
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"HH:MM","course":"Course","type":"flat","distance":"1m","going":"good","runners":9,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":4.5,"prevOdds":5.5,"tipsters":5,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":95,"confidence":"high","reason":"Plain English reason.","result":"","position":0}}]}}],"jumps":[{{"time":"HH:MM","course":"Course","type":"chase","distance":"2m4f","going":"soft","runners":8,"horses":[{{"num":2,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":5.0,"prevOdds":6.0,"tipsters":4,"formStr":"WWWPW","goingWins":3,"goingRuns":5,"courseWins":2,"distanceWins":2,"trainerInForm":true,"rpr":145,"confidence":"high","reason":"Plain English reason.","result":"","position":0}}]}}],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""

    log("🔍 Searching Racing Post, Sporting Life, At The Races, GG...")

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=3000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()

    log(f"📝 Response: {len(response_text)} chars")

    if not response_text:
        raise ValueError("No response from Claude")

    # Strip markdown
    if "```" in response_text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if match:
            response_text = match.group(1)

    # Find JSON
    start = response_text.find('{')
    if start == -1:
        raise ValueError("No JSON found in response")

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

    # Add timestamp
    picks["date"] = TODAY
    picks["generatedAt"] = datetime.now(timezone.utc).isoformat()

    # Enforce rules in Python
    picks = enforce_rules(picks)

    return picks

def write_archive(picks):
    """Write immutable daily archive. Never overwrites existing file."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    if os.path.exists(ARCHIVE_FILE):
        log(f"⚠️  Archive already exists for {TODAY} — not overwriting")
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
        ["git", "-C", REPO_PATH, "pull", "--rebase", "--quiet"],
        ["git", "-C", REPO_PATH, "add", "picks.json", f"data/{TODAY}.json"],
        ["git", "-C", REPO_PATH, "commit", "-m", f"🏇 Auto picks — {TODAY_DISPLAY}"],
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
    picks = {
        "date": TODAY,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "noBetDay": True,
        "noBetReason": reason,
        "flat": [], "jumps": [],
        "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
    }
    write_archive(picks)
    with open(PICKS_FILE, "w") as f:
        json.dump(picks, f, indent=2)
    subprocess.run(["git", "-C", REPO_PATH, "add", "picks.json", f"data/{TODAY}.json"], capture_output=True)
    subprocess.run(["git", "-C", REPO_PATH, "commit", "-m", f"🚫 No bet — {TODAY_DISPLAY}"], capture_output=True)
    subprocess.run(["git", "-C", REPO_PATH, "push"], capture_output=True)

def main():
    log(f"\n{'='*50}")
    log(f"🏇 Signal 75 — {TODAY_DISPLAY}")
    log(f"{'='*50}")
    if not ANTHROPIC_KEY:
        log("❌ No API key — set ANTHROPIC_API_KEY")
        return

    # Only run once per day — check if we already have today's picks
    if os.path.exists(PICKS_FILE):
        try:
            with open(PICKS_FILE) as f:
                existing = json.load(f)
            if existing.get("date") == TODAY and not existing.get("noBetDay"):
                log(f"✅ Picks already generated for {TODAY} — skipping")
                log("   To force regenerate, delete picks.json first")
                return
        except:
            pass
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
