#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator
Short prompt version — stays within free tier token limits
"""

import os
import json
import anthropic
from datetime import date

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

def generate_picks():
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""You are Signal 75's horse racing AI. Today is {TODAY_DISPLAY}.

Search the web for today's UK horse racing and pick 3 flat and 3 jumps selections.

RULES:
- Odds must be 2.0-9.0 decimal
- Minimum 6 tipsters backing the horse
- Field size 6-16 runners
- Score each horse 0-100, minimum 62 to qualify
- Pick highest scorer from each race, 3 different races per type
- If under 3 qualify, set noBetDay true

SCORING (quick guide):
- Steaming odds (shortening) = good. Drifting = bad.
- More tipsters = better. Going form match = better.
- Best odds range 4.0-6.0 for each-way value.
- Recent wins weighted heavily. Course/distance wins = bonus.

Return ONLY this JSON (no other text):
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"HH:MM","course":"Name","type":"flat","distance":"1m2f","going":"good","runners":10,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":4.5,"prevOdds":5.5,"tipsters":8,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":110,"reason":"One sentence plain English for a beginner.","result":"","position":0}}]}}],"jumps":[{{"time":"HH:MM","course":"Name","type":"chase","distance":"2m4f","going":"soft","runners":9,"horses":[{{"num":3,"name":"HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":3.5,"prevOdds":4.0,"tipsters":9,"formStr":"WWWPW","goingWins":3,"goingRuns":5,"courseWins":2,"distanceWins":2,"trainerInForm":true,"rpr":155,"reason":"One sentence plain English for a beginner.","result":"","position":0}}]}}],"results":{{"flat":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"jumps":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""

    print("🤖 Calling Claude...")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    print(f"📝 Response: {len(response_text)} chars")
    print(f"📝 Preview: {response_text[:300]}")

    # Clean markdown if present
    if "```" in response_text:
        for part in response_text.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                response_text = part
                break

    if not response_text.startswith("{"):
        start = response_text.find("{")
        if start != -1:
            response_text = response_text[start:]

    picks = json.loads(response_text)
    assert "date" in picks and "flat" in picks and "jumps" in picks
    return picks

def write_picks(picks):
    with open("picks.json", "w") as f:
        json.dump(picks, f, indent=2)
    print(f"✅ Written: {picks['date']}")
    if picks.get("noBetDay"):
        print(f"🚫 No bet: {picks.get('noBetReason','')}")
    else:
        for r in picks.get("flat",[]):
            h = r["horses"][0] if r.get("horses") else None
            if h: print(f"   FLAT  {r['time']} {r['course']}: {h['name']} @ {h['odds']}")
        for r in picks.get("jumps",[]):
            h = r["horses"][0] if r.get("horses") else None
            if h: print(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']}")

def write_no_bet_day(reason):
    with open("picks.json", "w") as f:
        json.dump({"date":TODAY,"noBetDay":True,"noBetReason":reason,"flat":[],"jumps":[],
                   "results":{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":False}}, f, indent=2)
    print(f"⚠️  No bet: {reason}")

def main():
    print(f"🏇 Signal 75 — {TODAY_DISPLAY}")
    print("="*50)
    try:
        picks = generate_picks()
        write_picks(picks)
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
        write_no_bet_day("AI analysis error — check back tomorrow.")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        write_no_bet_day("System error — check back tomorrow.")

if __name__ == "__main__":
    main()
