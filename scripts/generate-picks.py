#!/usr/bin/env python3
import os, json, sys
from datetime import date
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")

def main():
    print(f"Signal 75 picks — {TODAY_DISPLAY}")
    
    # Check API key exists
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        write_no_bet("API key missing")
        return
    print(f"API key found: {key[:10]}...")

    try:
        client = anthropic.Anthropic(api_key=key)
        
        prompt = f'Today is {TODAY_DISPLAY}. Give me 3 UK flat horse racing picks for today as JSON. Use this exact format, replacing values with real horses running today:\n\n{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"14:00","course":"Newbury","type":"flat","distance":"1m2f","going":"good","runners":10,"horses":[{{"num":1,"name":"REAL HORSE NAME","jockey":"J. Smith","trainer":"T. Jones","odds":4.5,"prevOdds":5.0,"tipsters":8,"formStr":"WWPWP","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":110,"reason":"Plain English reason for a beginner.","result":"","position":0}}]}},{{"time":"15:00","course":"Sandown","type":"flat","distance":"1m","going":"good","runners":8,"horses":[{{"num":3,"name":"REAL HORSE NAME","jockey":"J. Smith","trainer":"T. Jones","odds":5.0,"prevOdds":6.0,"tipsters":7,"formStr":"WPWWP","goingWins":1,"goingRuns":3,"courseWins":0,"distanceWins":2,"trainerInForm":true,"rpr":105,"reason":"Plain English reason for a beginner.","result":"","position":0}}]}},{{"time":"15:30","course":"Chelmsford","type":"flat","distance":"7f","going":"standard","runners":9,"horses":[{{"num":2,"name":"REAL HORSE NAME","jockey":"J. Smith","trainer":"T. Jones","odds":3.5,"prevOdds":4.5,"tipsters":9,"formStr":"WWWPF","goingWins":3,"goingRuns":4,"courseWins":2,"distanceWins":1,"trainerInForm":true,"rpr":115,"reason":"Plain English reason for a beginner.","result":"","position":0}}]}}],"jumps":[],"results":{{"flat":[{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}},{{"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}}],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}\n\nReturn ONLY the JSON object. No other text.'

        print("Calling Claude...")
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        raw = msg.content[0].text.strip()
        print(f"Response received: {len(raw)} chars")
        print(f"First 500 chars:\n{raw[:500]}")
        print(f"Last 200 chars:\n{raw[-200:]}")
        
        # Extract JSON robustly
        text = raw
        
        # Remove markdown code fences
        if "```" in text:
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1)
        
        # Find the outermost JSON object
        start = text.find('{')
        if start == -1:
            print(f"ERROR: No JSON object found in response")
            print(f"Full response: {raw}")
            write_no_bet("AI returned no JSON — check back tomorrow.")
            return
            
        # Find matching closing brace
        depth = 0
        end = -1
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        
        if end == -1:
            print("ERROR: Unbalanced JSON braces")
            print(f"Full response: {raw}")
            write_no_bet("AI returned malformed JSON — check back tomorrow.")
            return
            
        json_str = text[start:end]
        print(f"Extracted JSON: {len(json_str)} chars")
        
        picks = json.loads(json_str)
        print(f"Parsed successfully. Keys: {list(picks.keys())}")
        
        # Validate required fields
        for field in ["date", "flat", "jumps", "results"]:
            if field not in picks:
                picks[field] = [] if field in ["flat", "jumps"] else {}
        
        picks["date"] = TODAY
        
        with open("picks.json", "w") as f:
            json.dump(picks, f, indent=2)
        
        print("picks.json written successfully!")
        if picks.get("noBetDay"):
            print(f"No bet day: {picks.get('noBetReason','')}")
        else:
            for r in picks.get("flat", []):
                h = r.get("horses", [{}])[0]
                print(f"  FLAT {r.get('time')} {r.get('course')}: {h.get('name')} @ {h.get('odds')}")

    except anthropic.APIError as e:
        print(f"Anthropic API error: {type(e).__name__}: {e}")
        write_no_bet(f"API error — check back tomorrow.")
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Attempted to parse: {json_str[:500] if 'json_str' in dir() else 'N/A'}")
        write_no_bet("JSON parse error — check back tomorrow.")
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        write_no_bet("Unexpected error — check back tomorrow.")

def write_no_bet(reason):
    data = {
        "date": TODAY, "noBetDay": True, "noBetReason": reason,
        "flat": [], "jumps": [],
        "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
    }
    with open("picks.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Written no-bet-day: {reason}")

if __name__ == "__main__":
    main()
