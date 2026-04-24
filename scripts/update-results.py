#!/usr/bin/env python3
"""
Signal 75 — Evening Results Updater
Runs via GitHub Actions at 7pm BST daily
Claude searches web for finishing positions ONLY
All patent calculations done in Python — never by AI
"""

import os, json, re, traceback
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

# ── STAKE BASIS ──────────────────────────────────────────────────
STAKE_EW = 0.50          # £0.50 each-way per horse
TOTAL_PATENT_STAKE = 7.0 # 7 bets × £1.00 (£0.50 win + £0.50 place)
PLACE_FRACTION = 0.25    # 1/4 odds place terms
# ────────────────────────────────────────────────────────────────

def calculate_ew_return(odds_decimal, result, runners):
    """
    Calculate each-way return for a single horse.
    All maths done in Python — never delegated to AI.
    
    Args:
        odds_decimal: decimal odds (e.g. 4.5 = 7/2)
        result: "WON", "PLACED", or "LOST"
        runners: number of runners (affects place terms)
    
    Returns:
        (win_return, place_return, total_return)
    """
    # Place fraction: 1/5 for 8+ runners in handicaps, 1/4 standard
    place_frac = 0.20 if runners >= 16 else PLACE_FRACTION

    win_profit = odds_decimal - 1  # profit per £1 staked

    if result == "WON":
        win_return = odds_decimal * STAKE_EW          # win part
        place_return = (1 + win_profit * place_frac) * STAKE_EW  # place part
    elif result == "PLACED":
        win_return = 0.0
        place_return = (1 + win_profit * place_frac) * STAKE_EW
    else:  # LOST or PENDING
        win_return = 0.0
        place_return = 0.0

    total_return = round(win_return + place_return, 2)
    return round(win_return, 2), round(place_return, 2), total_return

def calculate_patent(flat_results, jumps_results, flat_races, jumps_races):
    """
    Full patent each-way calculation in Python.
    
    A patent = 7 bets:
    - 3 singles (one per horse)
    - 3 doubles (every pair)
    - 1 treble (all three)
    Each bet is each-way so total = 14 unit bets = £7.00 at £0.50 EW.
    
    For EW multiples: win legs use win returns, place legs use place returns.
    A double pays if BOTH horses win or place (separately).
    """
    all_results = flat_results + jumps_results
    all_races = flat_races + jumps_races

    if len(all_results) < 3:
        # Can't do full patent with fewer than 3 picks
        total = sum(r.get("totalReturn", 0) for r in all_results)
        stake = len(all_results) * 2 * STAKE_EW  # singles only
        return round(total, 2), round(total - stake, 2)

    # Get win and place returns for each of the 3 horses
    picks_data = []
    for i, result in enumerate(all_results[:3]):
        odds = all_races[i]["horses"][0]["odds"] if i < len(all_races) and all_races[i].get("horses") else 1.0
        runners = all_races[i].get("runners", 8) if i < len(all_races) else 8
        w, p, _ = calculate_ew_return(odds, result.get("result", "LOST"), runners)
        picks_data.append({"win": w, "place": p, "result": result.get("result", "LOST")})

    h1, h2, h3 = picks_data[0], picks_data[1], picks_data[2]

    # Singles (3 bets EW = 6 unit bets)
    singles = h1["win"] + h1["place"] + h2["win"] + h2["place"] + h3["win"] + h3["place"]

    # Doubles — EW double: win leg = h1_win × h2_win, place leg = h1_place × h2_place
    # Double 1: h1 × h2
    d1_win = h1["win"] * h2["win"] / STAKE_EW if h1["win"] > 0 and h2["win"] > 0 else 0
    d1_place = h1["place"] * h2["place"] / STAKE_EW if h1["place"] > 0 and h2["place"] > 0 else 0
    # Double 2: h1 × h3
    d2_win = h1["win"] * h3["win"] / STAKE_EW if h1["win"] > 0 and h3["win"] > 0 else 0
    d2_place = h1["place"] * h3["place"] / STAKE_EW if h1["place"] > 0 and h3["place"] > 0 else 0
    # Double 3: h2 × h3
    d3_win = h2["win"] * h3["win"] / STAKE_EW if h2["win"] > 0 and h3["win"] > 0 else 0
    d3_place = h2["place"] * h3["place"] / STAKE_EW if h2["place"] > 0 and h3["place"] > 0 else 0

    doubles = d1_win + d1_place + d2_win + d2_place + d3_win + d3_place

    # Treble — EW treble: win = h1 × h2 × h3 (all win), place = h1 × h2 × h3 (all place)
    t_win = h1["win"] * h2["win"] * h3["win"] / (STAKE_EW ** 2) if all(h["win"] > 0 for h in picks_data) else 0
    t_place = h1["place"] * h2["place"] * h3["place"] / (STAKE_EW ** 2) if all(h["place"] > 0 for h in picks_data) else 0

    treble = t_win + t_place

    total_return = round(singles + doubles + treble, 2)
    total_profit = round(total_return - TOTAL_PATENT_STAKE, 2)

    return total_return, total_profit

def get_results_from_web(horses_needed):
    """
    Claude searches web for finishing positions ONLY.
    Returns raw position data — no calculations.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prompt = f"""Today is {TODAY_DISPLAY}. Search for the finishing positions of these horses in today's UK races:

{json.dumps(horses_needed, indent=2)}

For each horse search:
- "[horse name] result {TODAY_DISPLAY}"
- "[horse name] [course] result today"
- attheraces.com, racingpost.com, sportinglife.com results pages

Find ONLY the finishing position (1st, 2nd, 3rd, 4th etc).
Do NOT calculate any returns or profits — just positions.

Return ONLY this JSON:
{{"positions": [{{"name": "HORSE NAME", "position": 1, "ran": 9}}, {{"name": "HORSE NAME", "position": 3, "ran": 8}}, {{"name": "HORSE NAME", "position": 0, "ran": 0}}]}}

Use position 0 if result not yet available.
Include "ran" field = number of runners in the race."""

    print("🔍 Searching for today's results...")

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = ""
    for block in message.content:
        if hasattr(block, "text"):
            response_text = block.text.strip()

    if not response_text:
        raise ValueError("No response from Claude")

    if "```" in response_text:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if match:
            response_text = match.group(1)

    start = response_text.find('{')
    if start == -1:
        raise ValueError("No JSON in response")

    depth, end = 0, -1
    for i, c in enumerate(response_text[start:], start):
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    return json.loads(response_text[start:end])

def determine_result(position, runners):
    """
    Determine WON / PLACED / LOST from finishing position.
    Place terms: 1st-2nd in fields under 8, 1st-3rd in 8-11, 1st-4th in 12+
    """
    if position == 0:
        return "PENDING"
    if position == 1:
        return "WON"
    if runners < 8 and position == 2:
        return "PLACED"
    if 8 <= runners <= 11 and position <= 3:
        return "PLACED"
    if runners >= 12 and position <= 4:
        return "PLACED"
    return "LOST"

def main():
    print(f"📊 Signal 75 Evening Results — {TODAY_DISPLAY}")
    print("=" * 50)

    try:
        with open("picks.json", "r") as f:
            picks = json.load(f)

        if picks.get("noBetDay"):
            print("🚫 No bet day — nothing to update")
            return

        # Build list of horses to check
        horses_needed = []
        all_races = []
        for race in picks.get("flat", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_races.append({"tab": "flat", "race": race})
        for race in picks.get("jumps", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_races.append({"tab": "jumps", "race": race})

        if not horses_needed:
            print("No horses to check")
            return

        # Get positions from web (Claude search only — no calculations)
        raw = get_results_from_web(horses_needed)
        positions = {p["name"].upper(): p for p in raw.get("positions", [])}

        # Build results using Python calculations
        flat_results, jumps_results = [], []
        flat_races_data, jumps_races_data = [], []

        for entry in all_races:
            race = entry["race"]
            h = race["horses"][0]
            name = h["name"].upper()
            pos_data = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            position = pos_data.get("position", 0)
            runners = pos_data.get("ran", race.get("runners", 8))
            odds = h.get("odds", 2.0)

            result_str = determine_result(position, runners)

            # Python calculates returns
            win_ret, place_ret, total_ret = calculate_ew_return(odds, result_str, runners)

            result_obj = {
                "position": position,
                "result": result_str,
                "winReturn": win_ret,
                "placeReturn": place_ret,
                "totalReturn": total_ret
            }

            # Update horse in race data
            h["result"] = result_str
            h["position"] = position

            if entry["tab"] == "flat":
                flat_results.append(result_obj)
                flat_races_data.append(race)
            else:
                jumps_results.append(result_obj)
                jumps_races_data.append(race)

        # Calculate patent in Python
        all_flat_jumps = flat_results + jumps_results
        all_races_combined = flat_races_data + jumps_races_data
        patent_return, patent_profit = calculate_patent(flat_results, jumps_results, flat_races_data, jumps_races_data)

        complete = all(r["result"] not in ["", "PENDING"] for r in all_flat_jumps)

        picks["results"] = {
            "flat": flat_results,
            "jumps": jumps_results,
            "patentReturn": patent_return,
            "patentProfit": patent_profit,
            "complete": complete,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }

        # Write picks.json
        with open("picks.json", "w") as f:
            json.dump(picks, f, indent=2)

        # Update archive — overwrite allowed for results (archive was written at morning)
        archive_path = f"data/{TODAY}.json"
        if os.path.exists(archive_path):
            with open(archive_path, "w") as f:
                json.dump(picks, f, indent=2)
            print(f"✅ Archive updated: {archive_path}")

        print(f"✅ Results complete: {complete}")
        print(f"   Patent return: £{patent_return:.2f}")
        print(f"   Patent profit: £{patent_profit:.2f}")
        for r in flat_results:
            print(f"   FLAT: {r['result']} pos {r['position']} → £{r['totalReturn']:.2f}")
        for r in jumps_results:
            print(f"   JUMPS: {r['result']} pos {r['position']} → £{r['totalReturn']:.2f}")

    except FileNotFoundError:
        print("❌ picks.json not found")
    except Exception as e:
        print(f"❌ {type(e).__name__}: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    main()
