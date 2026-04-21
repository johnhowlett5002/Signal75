#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator v2
Fetches free public racing data, passes to Claude for analysis
Zero extra cost — no external API subscription needed
"""

import os
import json
import requests
import anthropic
from datetime import date

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/html, */*"
}

def fetch_racing_data():
    """Fetch today's UK racing data from free public sources."""
    racing_data = []

    sources = [
        ("Racing Post", f"https://www.racingpost.com/api/racecards/free?date={TODAY}"),
        ("At The Races", f"https://www.attheraces.com/api/racecards/{TODAY}"),
        ("Sporting Life", "https://www.sportinglife.com/api/racing/tips/today"),
    ]

    for name, url in sources:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                racing_data.append(f"{name}: {resp.text[:3000]}")
                print(f"✅ {name}: OK")
            else:
                print(f"⚠️  {name}: {resp.status_code}")
        except Exception as e:
            print(f"⚠️  {name} failed: {e}")

    return "\n\n".join(racing_data)

def generate_picks_with_claude(racing_data):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    data_section = f"## TODAY'S RACING DATA:\n{racing_data}" if racing_data else \
        f"## NOTE: Use your knowledge of UK racing for {TODAY_DISPLAY}. Set noBetDay true if uncertain."

    prompt = f"""You are Signal 75's AI racing analyst. Today is {TODAY_DISPLAY}.

{data_section}

Score each horse using the 8-signal system (minimum 62/100 to qualify):

1. MARKET MOVEMENT (22%) — steamer=80-100+12bonus, stable=50, drifter=0-30-20penalty
2. TIPSTER CONSENSUS (20%) — 10+=100, 8-9=80, 6-7=60, <6=DISQUALIFY
3. GOING PREFERENCE (15%) — 3+wins=100, 2wins=80, 1win=60, ran=20, unknown=35
4. ODDS SWEET SPOT (13%) — 4.0-6.0=100, 3-4=80, 6-8=65, 2-3=45, <2or>9=DISQUALIFY
5. RECENT FORM (12%) — last3 weighted 5/3/1, W=full, P=half, back2back+8
6. COURSE+DISTANCE (10%) — both=100, course=65, distance=55, neither=25
7. TRAINER FORM (5%) — 15%+strike=100, else=30
8. FIELD SIZE (3%) — 8-12=100, 6-7=75, 13-16=60, <6or>16=DISQUALIFY

Select 3 flat picks from 3 different races, 3 jumps picks from 3 different races.
Never force picks below 62. Reason field = plain English for a complete beginner.

Return ONLY valid JSON:
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"HH:MM","course":"Name","type":"flat","distance":"1m2f","going":"good","runners":10,"horses":[{{"num":1,"name":"HORSE NAME","jockey":"F. Surname","trainer":"T. Surname","odds":4.5,"prevOdds":5.5,"tipsters":8,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":112,"reason":"Plain English for beginner.","result":"","position":0}}]}}],"jumps":[],"results":{{"flat":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"jumps":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""

    print("🤖 Sending to Claude...")
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    print(f"📝 Response: {len(response_text)} chars")
    print(f"📝 Preview: {response_text[:200]}")

    # Clean up response
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
        racing_data = fetch_racing_data()
        print(f"📊 Data: {len(racing_data)} chars")
        picks = generate_picks_with_claude(racing_data)
        write_picks(picks)
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
        write_no_bet_day("AI analysis error — check back tomorrow.")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        write_no_bet_day("System error — check back tomorrow.")

if __name__ == "__main__":
    main()
