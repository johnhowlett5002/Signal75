#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator
Minimal test version to diagnose API issues
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

    # Absolute minimum prompt — just 50 tokens
    prompt = f"""Today is {TODAY_DISPLAY}. You are a horse racing tipster.

Pick 3 UK flat horse racing selections for today and return ONLY this JSON with real horses running today:

{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"14:00","course":"Newbury","type":"flat","distance":"1m2f","going":"good","runners":10,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"J. Surname","trainer":"T. Surname","odds":4.5,"prevOdds":5.0,"tipsters":8,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":110,"reason":"This horse has been shortening in the betting market all morning and 8 tipsters back it.","result":"","position":0}}]}},{{"time":"14:30","course":"Sandown","type":"flat","distance":"1m","going":"good","runners":8,"horses":[{{"num":2,"name":"HORSE NAME","jockey":"J. Surname","trainer":"T. Surname","odds":5.0,"prevOdds":6.0,"tipsters":7,"formStr":"WPWWP","goingWins":1,"goingRuns":3,"courseWins":0,"distanceWins":2,"trainerInForm":true,"rpr":105,"reason":"Strong each-way value at 5/1 with solid recent form.","result":"","position":0}}]}},{{"time":"15:00","course":"Kempton","type":"flat","distance":"7f","going":"standard","runners":9,"horses":[{{"num":4,"name":"HORSE NAME","jockey":"J. Surname","trainer":"T. Surname","odds":3.5,"prevOdds":4.5,"tipsters":9,"formStr":"WWWPF","goingWins":3,"goingRuns":4,"courseWins":2,"distanceWins":1,"trainerInForm":true,"rpr":115,"reason":"Market confidence is high with odds shortening significantly today.","result":"","position":0}}]}}],"jumps":[],"results":{{"flat":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}

Replace HORSE NAME with real horses running today at those courses. Return ONLY the JSON."""

    print("🤖 Calling Claude Haiku...")
    
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    print(f"📝 Got {len(response_text)} chars back")
    print(f"📝 Start: {response_text[:200]}")

    # Find and extract JSON
    if "```" in response_text:
        for part in response_text.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                response_text = part
                break

    if not response_text.startswith("{"):
        idx = response_text.find("{")
        if idx != -1:
            response_text = response_text[idx:]

    picks = json.loads(response_text)
    assert "date" in picks
    return picks

def write_picks(picks):
    with open("picks.json", "w") as f:
        json.dump(picks, f, indent=2)
    print(f"✅ picks.json written for {picks['date']}")
    for r in picks.get("flat", []):
        h = r["horses"][0] if r.get("horses") else None
        if h:
            print(f"   FLAT {r['time']} {r['course']}: {h['name']} @ {h['odds']}")

def write_no_bet_day(reason):
    with open("picks.json", "w") as f:
        json.dump({
            "date": TODAY, "noBetDay": True, "noBetReason": reason,
            "flat": [], "jumps": [],
            "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
        }, f, indent=2)
    print(f"⚠️ No bet: {reason}")

def main():
    print(f"🏇 Signal 75 — {TODAY_DISPLAY}")
    print("=" * 50)
    try:
        picks = generate_picks()
        write_picks(picks)
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
        print(f"❌ Check the response above for what Claude actually returned")
        write_no_bet_day("AI analysis error — check back tomorrow.")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        write_no_bet_day("System error — check back tomorrow.")

if __name__ == "__main__":
    main()
