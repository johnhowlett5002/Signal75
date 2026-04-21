#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator
Runs at 10am daily via GitHub Action
Claude uses web search to find today's UK racecards
ZERO extra cost — no Racing API subscription needed
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

    prompt = f"""You are Signal 75's AI racing analyst. Today is {TODAY_DISPLAY}.

Your task: Search the web for today's UK horse racing cards, analyse every runner using the Signal 75 8-signal scoring system, and select the best 3 flat picks and 3 jumps picks.

## STEP 1 — SEARCH FOR TODAY'S RACECARDS
Search for:
- "UK horse racing today {TODAY_DISPLAY} racecards"
- "horse racing tips today {TODAY_DISPLAY} tipsters"
- "At The Races today {TODAY_DISPLAY}"
- "Sporting Life racing today {TODAY_DISPLAY}"
- For each potential pick search: "[horse name] form going course wins"

## STEP 2 — SCORE EVERY HORSE (0-100 per signal)

Signal 1 — MARKET MOVEMENT (22% weight)
Compare morning price to current price:
- Odds shortening = steamer = score 80-100, add +12 bonus points
- Odds stable = score 50, no bonus
- Odds drifting/lengthening = score 0-30, subtract 20 penalty points

Signal 2 — TIPSTER CONSENSUS (20% weight)
Count how many professional tipsters are backing the horse today:
- 10+ tipsters = score 100
- 8-9 tipsters = score 80
- 6-7 tipsters = score 60
- Under 6 tipsters = DISQUALIFY immediately

Signal 3 — GOING PREFERENCE (15% weight)
Does the horse have a proven record on today's going?
- 3+ previous wins on this going = score 100
- 2 wins = score 80
- 1 win = score 60
- Run on it but not won = score 20
- Never run on this going = score 35

Signal 4 — ODDS SWEET SPOT (13% weight)
Best each-way patent value zone:
- Decimal 4.0 to 6.0 (3/1 to 5/1) = score 100
- Decimal 3.0 to 4.0 (2/1 to 3/1) = score 80
- Decimal 6.0 to 8.0 (5/1 to 7/1) = score 65
- Decimal 2.0 to 3.0 (evens to 2/1) = score 45
- Below 2.0 or above 9.0 = DISQUALIFY immediately

Signal 5 — RECENT FORM (12% weight)
Last 3 runs, weighted most recent first (5x, 3x, 1x):
- W (win) = full weight points
- P (place) = half weight points
- F/U/R (unplaced/fell/refused) = zero points
- Back-to-back wins bonus: add +8 points

Signal 6 — COURSE AND DISTANCE RECORD (10% weight)
- Won at this course AND this distance = score 100
- Won at course only = score 65
- Won at distance only = score 55
- Unproven at both = score 25

Signal 7 — TRAINER IN FORM (5% weight)
- Trainer winning 15%+ of runs in last 14 days = score 100
- Below 15% or unknown = score 30

Signal 8 — FIELD SIZE (3% weight)
- 8 to 12 runners = score 100 (optimal for each-way)
- 6 to 7 runners = score 75
- 13 to 16 runners = score 60
- Under 6 or over 16 = DISQUALIFY immediately

## STEP 3 — CALCULATE COMPOSITE SCORE
composite = (signal1×22 + signal2×20 + signal3×15 + signal4×13 + signal5×12 + signal6×10 + signal7×5 + signal8×3) / 100
Apply steamer bonus (+12) or drifter penalty (-20)
Minimum score to qualify: 62 out of 100

## STEP 4 — SELECT PICKS
- Pick the single highest-scoring horse from each qualifying race
- Flat picks: 3 horses from 3 different flat races
- Jumps picks: 3 horses from 3 different jumps/hurdle/chase races
- If fewer than 3 flat races qualify: fewer picks or no flat picks
- If fewer than 3 jumps races qualify: fewer picks or no jumps picks
- NEVER force a selection below 62

## STEP 5 — WRITE THE REASON FIELD
The reason must be written in plain English for someone who has never placed a bet before.
Good example: "The betting market has shortened this horse from 5 to 1 down to 3 to 1 this morning — that means people who know racing are putting their money on it. It has won twice before on today's soft ground and 9 racing experts are tipping it."
Bad example: "Strong RPR with positive going profile and tipster consensus."

## OUTPUT FORMAT
Return ONLY valid JSON — no markdown, no explanation, no preamble:

{{
  "date": "{TODAY}",
  "noBetDay": false,
  "noBetReason": "",
  "flat": [
    {{
      "time": "HH:MM",
      "course": "Course Name",
      "type": "flat",
      "distance": "1m2f",
      "going": "good",
      "runners": 10,
      "horses": [
        {{
          "num": 1,
          "name": "HORSE NAME IN CAPITALS",
          "jockey": "F. Surname",
          "trainer": "T. Surname",
          "odds": 4.5,
          "prevOdds": 5.5,
          "tipsters": 8,
          "formStr": "WWPWP",
          "goingWins": 2,
          "goingRuns": 4,
          "courseWins": 1,
          "distanceWins": 2,
          "trainerInForm": true,
          "rpr": 112,
          "reason": "Plain English reason here for a complete beginner.",
          "result": "",
          "position": 0
        }}
      ]
    }}
  ],
  "jumps": [
    {{
      "time": "HH:MM",
      "course": "Course Name",
      "type": "chase",
      "distance": "2m4f",
      "going": "soft",
      "runners": 9,
      "horses": [
        {{
          "num": 3,
          "name": "HORSE NAME IN CAPITALS",
          "jockey": "F. Surname",
          "trainer": "T. Surname",
          "odds": 3.5,
          "prevOdds": 4.0,
          "tipsters": 9,
          "formStr": "WWWPW",
          "goingWins": 3,
          "goingRuns": 5,
          "courseWins": 2,
          "distanceWins": 2,
          "trainerInForm": true,
          "rpr": 158,
          "reason": "Plain English reason here for a complete beginner.",
          "result": "",
          "position": 0
        }}
      ]
    }}
  ],
  "results": {{
    "flat": [
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}},
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}},
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}}
    ],
    "jumps": [
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}},
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}},
      {{"position": 0, "result": "", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}}
    ],
    "patentReturn": 0,
    "patentProfit": 0,
    "complete": false
  }}
}}"""

    print("🔍 Claude searching for today's racecards...")

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract final text block after all web searches complete
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()

    if not response_text:
        raise ValueError("No text response from Claude")

    # Strip accidental markdown fences if present
    if "```" in response_text:
        parts = response_text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                response_text = part
                break

    picks = json.loads(response_text)
    assert "date" in picks and "flat" in picks and "jumps" in picks
    return picks


def write_picks(picks):
    with open("picks.json", "w") as f:
        json.dump(picks, f, indent=2)
    print(f"✅ picks.json written — {picks['date']}")
    if picks.get("noBetDay"):
        print(f"🚫 No bet day: {picks.get('noBetReason', '')}")
    else:
        for race in picks.get("flat", []):
            h = race["horses"][0] if race.get("horses") else None
            if h:
                print(f"   FLAT  {race['time']} {race['course']}: {h['name']} @ {h['odds']}")
        for race in picks.get("jumps", []):
            h = race["horses"][0] if race.get("horses") else None
            if h:
                print(f"   JUMPS {race['time']} {race['course']}: {h['name']} @ {h['odds']}")


def write_no_bet_day(reason):
    picks = {
        "date": TODAY, "noBetDay": True, "noBetReason": reason,
        "flat": [], "jumps": [],
        "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
    }
    with open("picks.json", "w") as f:
        json.dump(picks, f, indent=2)
    print(f"⚠️  No bet day: {reason}")


def main():
    print(f"🏇 Signal 75 Morning Picks — {TODAY_DISPLAY}")
    print("=" * 50)
    try:
        picks = generate_picks()
        write_picks(picks)
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
        write_no_bet_day("AI analysis error today — check back tomorrow.")
    except Exception as e:
        print(f"❌ Error: {e}")
        write_no_bet_day("System error today — check back tomorrow.")


if __name__ == "__main__":
    main()
