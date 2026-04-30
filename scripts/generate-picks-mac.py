#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator (Mac version)
Robust JSON extraction with retry logic
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

MIN_ODDS = 2.1
MAX_ODDS = 10.0
MIN_RUNNERS = 6
MAX_RUNNERS = 16

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def extract_json(text):
    """
    Robust JSON extractor. Tries multiple strategies:
    1. Direct parse
    2. Extract from code block
    3. Find outermost { } and parse
    4. Find all { } candidates and try each
    """
    if not text or not text.strip():
        return None

    # Strategy 1: direct parse
    try:
        obj = json.loads(text.strip())
        if "date" in obj and "flat" in obj:
            return obj
    except:
        pass

    # Strategy 2: extract from markdown code block
    for pattern in [r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```']:
        m = re.search(pattern, text)
        if m:
            try:
                obj = json.loads(m.group(1))
                if "date" in obj and "flat" in obj:
                    return obj
            except:
                pass

    # Strategy 3: find outermost { }
    start = text.find('{')
    if start != -1:
        depth, end = 0, -1
        for i, c in enumerate(text[start:], start):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            try:
                obj = json.loads(text[start:end])
                if "date" in obj and "flat" in obj:
                    return obj
            except:
                pass

    # Strategy 4: find all { candidates
    candidates = [m.start() for m in re.finditer(r'\{', text)]
    for start in candidates:
        depth, end = 0, -1
        for i, c in enumerate(text[start:], start):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end != -1:
            chunk = text[start:end]
            try:
                obj = json.loads(chunk)
                if "date" in obj and ("flat" in obj or "noBetDay" in obj):
                    return obj
            except:
                continue

    return None

def enforce_rules(picks):
    """Remove any horse failing hard rules. Python enforced."""
    cleaned_flat, cleaned_jumps = [], []
    for race in picks.get("flat", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            log(f"   REMOVED flat {race.get('course','?')}: {runners} runners")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = float(h.get("odds", 0))
        if odds < MIN_ODDS or odds > MAX_ODDS:
            log(f"   REMOVED {h.get('name','?')}: odds {odds}")
            continue
        cleaned_flat.append(race)
    for race in picks.get("jumps", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            log(f"   REMOVED jumps {race.get('course','?')}: {runners} runners")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = float(h.get("odds", 0))
        if odds < MIN_ODDS or odds > MAX_ODDS:
            log(f"   REMOVED {h.get('name','?')}: odds {odds}")
            continue
        cleaned_jumps.append(race)
    picks["flat"] = cleaned_flat[:3]
    picks["jumps"] = cleaned_jumps[:3]
    blank = {"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}
    picks.setdefault("results", {})
    picks["results"]["flat"] = [blank.copy() for _ in picks["flat"]]
    picks["results"]["jumps"] = [blank.copy() for _ in picks["jumps"]]
    picks["results"].setdefault("patentReturn", 0)
    picks["results"].setdefault("patentProfit", 0)
    picks["results"].setdefault("complete", False)
    if not picks["flat"] and not picks["jumps"]:
        picks["noBetDay"] = True
        picks["noBetReason"] = "No horses met the Signal 75 qualifying threshold today."
        picks["mode"] = "noBetDay"
    else:
        picks["noBetDay"] = False
        picks["mode"] = "qualified"
    picks.setdefault("threshold", 75)
    picks.setdefault("topScore", 0)
    picks.setdefault("gapToThreshold", 0)
    picks.setdefault("topRated", [])
    return picks

PROMPT_TEMPLATE = """Today is {today}. Find UK horse racing tips.

Search sportinglife.com/racing and attheraces.com for today's UK races.

For each of the best 3 flat and 3 jumps selections return ONLY this JSON (no other text):

{{"date":"{date}","noBetDay":false,"noBetReason":"","generatedAt":"{now}","flat":[{{"time":"14:00","course":"Newmarket","type":"flat","distance":"1m","going":"good","runners":10,"horses":[{{"num":3,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":5.0,"prevOdds":6.0,"tipsters":4,"formStr":"11212","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":100,"confidence":"high","reason":"Tipped by multiple sources and market support.","result":"","position":0}}]}}],"jumps":[{{"time":"14:30","course":"Sandown","type":"hurdle","distance":"2m","going":"soft","runners":8,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":4.0,"prevOdds":5.0,"tipsters":3,"formStr":"11121","goingWins":3,"goingRuns":5,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":140,"confidence":"high","reason":"Strong form and market support.","result":"","position":0}}]}}],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}

Rules:
- Only include real horses running today in the UK
- Odds must be 2.1 to 10.0 decimal
- Runners must be 6 to 16
- If no good picks exist set noBetDay to true and flat/jumps to empty arrays
- Return ONLY valid JSON starting with {{ and ending with }}"""

def build_prompt(attempt):
    strict = ""
    if attempt == 2:
        strict = "CRITICAL: Your previous response did not contain valid JSON. You MUST return ONLY the JSON structure shown below. Nothing else."
    elif attempt >= 3:
        strict = "FINAL ATTEMPT: Return ONLY JSON. Do not write any English text. Do not explain. Do not apologise. Your entire response must be valid JSON starting with { and ending with }."
    return PROMPT_TEMPLATE.format(
        today=TODAY_DISPLAY,
        date=TODAY,
        now=datetime.now(timezone.utc).isoformat(),
        strict=strict
    )

def call_claude(attempt):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    log(f"🔍 Attempt {attempt}: Searching 7 sources...")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": build_prompt(attempt)}]
    )
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text += block.text
    return response_text.strip()

def generate_picks():
    """Try up to 3 times to get valid JSON picks."""
    last_response = ""
    for attempt in range(1, 4):
        try:
            response = call_claude(attempt)
            last_response = response
            log(f"📝 Response: {len(response)} chars")
            if len(response) > 50:
                log(f"📝 Preview: {response[:200]}")

            picks = extract_json(response)
            if picks:
                picks["date"] = TODAY
                picks["generatedAt"] = datetime.now(timezone.utc).isoformat()
                picks = enforce_rules(picks)
                log(f"✅ Valid picks on attempt {attempt}")
                return picks
            else:
                log(f"⚠️  Attempt {attempt}: No valid JSON found — retrying...")
        except Exception as e:
            log(f"⚠️  Attempt {attempt} error: {type(e).__name__}: {e}")
            if attempt == 3:
                raise

    # All attempts failed — return no bet day
    log(f"❌ All 3 attempts failed. Last response: {last_response[:300]}")
    return {
        "date": TODAY,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "noBetDay": True,
        "noBetReason": "System could not retrieve today's racing data. Check back tomorrow.",
        "flat": [], "jumps": [],
        "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
    }

def write_archive(picks):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    if os.path.exists(ARCHIVE_FILE):
        log(f"⚠️  Archive exists for {TODAY} — not overwriting")
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
            log(f"⚠️  git {cmd[2]}: {result.stderr.strip()}")
        else:
            log(f"✅ git {cmd[2]}")
    log("🚀 Pushed! signal75.co.uk updating...")

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
                if h:
                    log(f"   FLAT  {r['time']} {r['course']}: {h['name']} @ {h['odds']} [{h.get('confidence','?')}]")
            for r in picks.get("jumps", []):
                h = r["horses"][0] if r.get("horses") else None
                if h:
                    log(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']} [{h.get('confidence','?')}]")
        push_to_github(picks)
    except Exception as e:
        log(f"❌ Fatal: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        # Still write a no-bet day so site doesn't show stale data
        emergency = {
            "date": TODAY,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "noBetDay": True,
            "noBetReason": "Technical issue today — back tomorrow at 10am.",
            "flat": [], "jumps": [],
            "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
        }
        push_to_github(emergency)

if __name__ == "__main__":
    main()
