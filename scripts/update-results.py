#!/usr/bin/env python3
"""
Signal 75 — Evening Results Updater
Runs at 7pm daily via GitHub Action
Claude uses web search to find actual race results
ZERO extra cost — no Racing API subscription needed
"""

import os
import json
import anthropic
from datetime import date

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]


def load_picks():
    with open("picks.json", "r") as f:
        return json.load(f)


def update_results(picks):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Build a list of horses we need results for
    horses_needed = []
    for race in picks.get("flat", []):
        if race.get("horses"):
            h = race["horses"][0]
            horses_needed.append({
                "tab": "flat",
                "name": h["name"],
                "course": race["course"],
                "time": race["time"],
                "odds": h["odds"]
            })
    for race in picks.get("jumps", []):
        if race.get("horses"):
            h = race["horses"][0]
            horses_needed.append({
                "tab": "jumps",
                "name": h["name"],
                "course": race["course"],
                "time": race["time"],
                "odds": h["odds"]
            })

    if not horses_needed:
        print("No horses to check results for")
        return picks

    prompt = f"""You are Signal 75's results calculator. Today is {TODAY_DISPLAY}.

## HORSES TO CHECK:
{json.dumps(horses_needed, indent=2)}

## YOUR TASKS:

TASK 1 — SEARCH FOR RESULTS
For each horse above, search the web for the actual race result:
- Search: "[horse name] result {TODAY_DISPLAY} [course]"
- Search: "horse racing results {TODAY_DISPLAY} [course]"
- Use attheraces.com, racingpost.com, sportinglife.com

Find:
- Finishing position (1st, 2nd, 3rd, 4th etc)
- Whether it WON (1st), PLACED (2nd/3rd/4th in race with 8+ runners), or LOST

TASK 2 — CALCULATE PATENT EACH-WAY RETURNS
Stake basis: £0.50 each-way per horse
A patent = 7 bets all each-way:
- 3 single EW bets (one per horse)
- 3 double EW bets (every pair combination)
- 1 treble EW bet (all 3 horses)
Total stake per patent = £7.00 (7 bets × £0.50 EW = 7 × £1.00)

Place terms: 1/4 odds (standard for 8+ runner races)

For each horse, calculate:
WON: win return = odds × £0.50, place return = (1 + (odds-1) × 0.25) × £0.50
PLACED: win return = £0, place return = (1 + (odds-1) × 0.25) × £0.50  
LOST: win return = £0, place return = £0

For doubles: multiply the relevant win or place returns together
For treble: multiply all three win or place returns together

Sum everything for total patent return.
Patent profit = total patent return - £7.00 stake

## OUTPUT FORMAT
Return ONLY valid JSON — no markdown, no explanation:

{{
  "flat": [
    {{"position": 1, "result": "WON", "winReturn": 2.25, "placeReturn": 0.81, "totalReturn": 3.06}},
    {{"position": 3, "result": "PLACED", "winReturn": 0, "placeReturn": 0.69, "totalReturn": 0.69}},
    {{"position": 7, "result": "LOST", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}}
  ],
  "jumps": [
    {{"position": 2, "result": "PLACED", "winReturn": 0, "placeReturn": 0.81, "totalReturn": 0.81}},
    {{"position": 1, "result": "WON", "winReturn": 1.75, "placeReturn": 0.69, "totalReturn": 2.44}},
    {{"position": 5, "result": "LOST", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}}
  ],
  "patentReturn": 9.44,
  "patentProfit": 2.44,
  "complete": true
}}

If a result is not yet available for a horse, use:
{{"position": 0, "result": "PENDING", "winReturn": 0, "placeReturn": 0, "totalReturn": 0}}
And set "complete": false

Return ONLY the JSON."""

    print("🔍 Claude searching for today's results...")

    try:
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"⚠️  Web search tool failed ({e}), trying without tools...")
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

    # Extract final text response
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()
        elif hasattr(block, "type") and block.type == "text":
            response_text = block.text.strip()

    print(f"📝 Raw response: {response_text[:200]}")

    if not response_text:
        raise ValueError("No text response from Claude")

    # Strip markdown fences if present
    if "```" in response_text:
        parts = response_text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                response_text = part
                break

    results = json.loads(response_text)

    # Merge results back into picks
    picks["results"] = results

    # Also update individual horse position/result in race data
    flat_results  = results.get("flat", [])
    jumps_results = results.get("jumps", [])

    for i, race in enumerate(picks.get("flat", [])):
        if i < len(flat_results) and race.get("horses"):
            race["horses"][0]["result"]   = flat_results[i].get("result", "")
            race["horses"][0]["position"] = flat_results[i].get("position", 0)

    for i, race in enumerate(picks.get("jumps", [])):
        if i < len(jumps_results) and race.get("horses"):
            race["horses"][0]["result"]   = jumps_results[i].get("result", "")
            race["horses"][0]["position"] = jumps_results[i].get("position", 0)

    return picks


def main():
    print(f"📊 Signal 75 Evening Results — {TODAY_DISPLAY}")
    print("=" * 50)

    try:
        picks = load_picks()

        if picks.get("noBetDay"):
            print("🚫 No bet day — nothing to update")
            return

        updated = update_results(picks)

        with open("picks.json", "w") as f:
            json.dump(updated, f, indent=2)

        results = updated.get("results", {})
        print(f"✅ Results updated")
        print(f"   Patent return: £{results.get('patentReturn', 0):.2f}")
        print(f"   Patent profit: £{results.get('patentProfit', 0):.2f}")
        print(f"   Complete: {results.get('complete', False)}")

        # Print individual results
        for i, r in enumerate(results.get("flat", [])):
            if r.get("result"):
                print(f"   FLAT  Pick {i+1}: {r['result']} (pos {r['position']}) — £{r['totalReturn']:.2f}")
        for i, r in enumerate(results.get("jumps", [])):
            if r.get("result"):
                print(f"   JUMPS Pick {i+1}: {r['result']} (pos {r['position']}) — £{r['totalReturn']:.2f}")

    except FileNotFoundError:
        print("❌ picks.json not found — morning picks may not have run yet")
    except json.JSONDecodeError as e:
        print(f"❌ JSON error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
