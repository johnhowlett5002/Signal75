#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator (GitHub Actions version)
Runs via GitHub Actions at 10am BST daily
Uses Claude with web search — same rules as Mac version
All Signal 75 rules enforced in Python
"""

import os, json, re, traceback
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

# ── HARD RULES (enforced in Python) ─────────────────────────────
MIN_ODDS = 2.1
MAX_ODDS = 10.0
MIN_RUNNERS = 6
MAX_RUNNERS = 16
# ────────────────────────────────────────────────────────────────

def enforce_rules(picks):
    """Remove any horse that fails rules. Enforced in Python, not prompt."""
    cleaned_flat, cleaned_jumps, removed = [], [], []

    for race in picks.get("flat", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"FLAT {race.get('time')} {race.get('course')}: {runners} runners — REMOVED")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS:
            removed.append(f"FLAT {h.get('name')}: odds {odds} below {MIN_ODDS} — REMOVED")
            continue
        if odds > MAX_ODDS:
            removed.append(f"FLAT {h.get('name')}: odds {odds} above {MAX_ODDS} — REMOVED")
            continue
        cleaned_flat.append(race)

    for race in picks.get("jumps", []):
        runners = race.get("runners", 0)
        if runners < MIN_RUNNERS or runners > MAX_RUNNERS:
            removed.append(f"JUMPS {race.get('time')} {race.get('course')}: {runners} runners — REMOVED")
            continue
        if not race.get("horses"):
            continue
        h = race["horses"][0]
        odds = h.get("odds", 0)
        if odds < MIN_ODDS:
            removed.append(f"JUMPS {h.get('name')}: odds {odds} below {MIN_ODDS} — REMOVED")
            continue
        if odds > MAX_ODDS:
            removed.append(f"JUMPS {h.get('name')}: odds {odds} above {MAX_ODDS} — REMOVED")
            continue
        cleaned_jumps.append(race)

    for msg in removed:
        print(f"   🚫 {msg}")

    picks["flat"] = cleaned_flat[:3]
    picks["jumps"] = cleaned_jumps[:3]

    blank = {"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}
    picks["results"]["flat"] = [blank.copy() for _ in range(len(picks["flat"]))]
    picks["results"]["jumps"] = [blank.copy() for _ in range(len(picks["jumps"]))]

    if len(picks["flat"]) == 0 and len(picks["jumps"]) == 0:
        picks["noBetDay"] = True
        picks["noBetReason"] = "No horses met the Signal 75 qualifying criteria today."

    return picks

def generate_picks():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Today is {TODAY_DISPLAY}. You are Signal 75's horse racing analyst.

Search sportinglife.com, attheraces.com, racingpost.com and gg.co.uk for today's UK racing.

Score each horse on: market movement, tipster mentions, going form, odds range (4-6 decimal ideal), recent form, course/distance record, trainer form, field size.

Pick the best horse from each qualifying race. Up to 3 flat picks and 3 jumps picks.
Confidence: "high", "medium", or "each-way".
Reason: one plain English sentence for a complete beginner.

Return ONLY valid JSON:
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"HH:MM","course":"Course","type":"flat","distance":"1m","going":"good","runners":9,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":4.5,"prevOdds":5.5,"tipsters":5,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":95,"confidence":"high","reason":"Plain English reason.","result":"","position":0}}]}}],"jumps":[],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""

    print("🔍 Claude searching today's UK racecards...")

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

    print(f"📝 Response: {len(response_text)} chars")
    print(f"📝 Preview: {response_text[:200]}")

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
    """Write immutable daily archive. Never overwrites."""
    os.makedirs("data", exist_ok=True)
    archive_path = f"data/{TODAY}.json"
    if os.path.exists(archive_path):
        print(f"⚠️  Archive already exists for {TODAY} — not overwriting")
        return
    with open(archive_path, "w") as f:
        json.dump(picks, f, indent=2)
    print(f"✅ Archive written: {archive_path}")

def write_no_bet(reason):
    picks = {
        "date": TODAY,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "noBetDay": True, "noBetReason": reason,
        "flat": [], "jumps": [],
        "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
    }
    write_archive(picks)
    with open("picks.json", "w") as f:
        json.dump(picks, f, indent=2)
    print(f"⚠️  No bet day written: {reason}")

def main():
    print(f"🏇 Signal 75 Morning Picks — {TODAY_DISPLAY}")
    print("=" * 50)
    try:
        picks = generate_picks()
        write_archive(picks)
        with open("picks.json", "w") as f:
            json.dump(picks, f, indent=2)
        if picks.get("noBetDay"):
            print(f"🚫 No bet: {picks.get('noBetReason','')}")
        else:
            print(f"✅ {len(picks.get('flat',[]))} flat, {len(picks.get('jumps',[]))} jumps picks")
            for r in picks.get("flat", []):
                h = r["horses"][0] if r.get("horses") else None
                if h: print(f"   FLAT  {r['time']} {r['course']}: {h['name']} @ {h['odds']}")
            for r in picks.get("jumps", []):
                h = r["horses"][0] if r.get("horses") else None
                if h: print(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']}")
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
        write_no_bet("AI analysis error — check back tomorrow.")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        print(traceback.format_exc())
        write_no_bet("System error — check back tomorrow.")

if __name__ == "__main__":
    main()
