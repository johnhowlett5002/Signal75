#!/usr/bin/env python3
"""Signal 75 Evening Results Updater — rebuilt with test mode"""

import os, json, re, traceback, argparse
from datetime import date, datetime, timezone

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TEST_MODE = os.environ.get("S75_TEST_MODE", "0") == "1"
STAKE_EW = 0.50
TOTAL_PATENT_STAKE = 7.0

def log(msg): print(msg)

def calculate_ew_return(odds, result, runners):
    place_frac = 0.20 if runners >= 16 else 0.25
    win_profit = odds - 1
    if result == "WON":
        w = odds * STAKE_EW
        p = (1 + win_profit * place_frac) * STAKE_EW
    elif result == "PLACED":
        w, p = 0.0, (1 + win_profit * place_frac) * STAKE_EW
    else:
        w, p = 0.0, 0.0
    return round(w,2), round(p,2), round(w+p,2)

def calculate_patent(picks_data):
    if len(picks_data) < 3:
        total = sum(h["win"]+h["place"] for h in picks_data)
        return round(total,2), round(total - len(picks_data)*2*STAKE_EW,2)
    h1,h2,h3 = picks_data[0],picks_data[1],picks_data[2]
    singles = h1["win"]+h1["place"]+h2["win"]+h2["place"]+h3["win"]+h3["place"]
    d1w = h1["win"]*h2["win"]/STAKE_EW if h1["win"] and h2["win"] else 0
    d1p = h1["place"]*h2["place"]/STAKE_EW if h1["place"] and h2["place"] else 0
    d2w = h1["win"]*h3["win"]/STAKE_EW if h1["win"] and h3["win"] else 0
    d2p = h1["place"]*h3["place"]/STAKE_EW if h1["place"] and h3["place"] else 0
    d3w = h2["win"]*h3["win"]/STAKE_EW if h2["win"] and h3["win"] else 0
    d3p = h2["place"]*h3["place"]/STAKE_EW if h2["place"] and h3["place"] else 0
    doubles = d1w+d1p+d2w+d2p+d3w+d3p
    tw = h1["win"]*h2["win"]*h3["win"]/STAKE_EW**2 if all(h["win"] for h in picks_data) else 0
    tp = h1["place"]*h2["place"]*h3["place"]/STAKE_EW**2 if all(h["place"] for h in picks_data) else 0
    total = round(singles+doubles+tw+tp,2)
    return total, round(total-TOTAL_PATENT_STAKE,2)

def determine_result(position, runners):
    if position == 0: return "PENDING"
    if position == 1: return "WON"
    if runners < 8 and position == 2: return "PLACED"
    if 8 <= runners <= 11 and position <= 3: return "PLACED"
    if runners >= 12 and position <= 4: return "PLACED"
    return "LOST"

def get_positions_live(horses_needed):
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    log("LIVE MODE — Anthropic call starting")
    prompt = f"""Today is {TODAY_DISPLAY}. Find finishing positions of these horses: {json.dumps(horses_needed)}
Search attheraces.com, racingpost.com, sportinglife.com.
Return ONLY JSON: {{"positions":[{{"name":"HORSE","position":1,"ran":9}}]}}
position=0 if not available."""
    msg = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=800,
        tools=[{"type":"web_search_20250305","name":"web_search"}],
        messages=[{"role":"user","content":prompt}])
    log(f"Tokens: in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    txt = ""
    for b in msg.content:
        if hasattr(b,"text"): txt = b.text.strip()
    if not txt: raise ValueError("No response")
    if "```" in txt:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt)
        if m: txt = m.group(1)
    s = txt.find("{")
    if s == -1: raise ValueError("No JSON")
    d,e = 0,-1
    for i,c in enumerate(txt[s:],s):
        if c=="{": d+=1
        elif c=="}":
            d-=1
            if d==0: e=i+1; break
    return json.loads(txt[s:e])

def get_positions_test(fixture_path):
    log("TEST MODE — Anthropic call skipped")
    log(f"TEST MODE — Loading fixture: {fixture_path}")
    with open(fixture_path) as f: return json.load(f)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture")
    parser.add_argument("--picks-file", default="picks.json")
    parser.add_argument("--archive-dir", default="data")
    args = parser.parse_args()
    archive_path = os.path.join(args.archive_dir, f"{TODAY}.json")

    log(f"\n{'='*50}\nSignal 75 Results — {TODAY_DISPLAY}")
    log("TEST MODE — no API credits" if (TEST_MODE or args.fixture) else "LIVE MODE")
    log("="*50)

    try:
        with open(args.picks_file) as f: picks = json.load(f)
    except FileNotFoundError:
        log(f"picks.json not found"); return

    mode = picks.get("mode","")
    if picks.get("noBetDay") or mode == "topRatedOnly":
        log(f"Mode={mode} noBetDay={picks.get('noBetDay')} — skipping (not in proof)"); return

    horses_needed, all_entries = [], []
    for race in picks.get("flat",[]):
        if race.get("horses"):
            h = race["horses"][0]
            horses_needed.append({"name":h["name"],"course":race["course"],"time":race["time"]})
            all_entries.append({"tab":"flat","race":race})
    for race in picks.get("jumps",[]):
        if race.get("horses"):
            h = race["horses"][0]
            horses_needed.append({"name":h["name"],"course":race["course"],"time":race["time"]})
            all_entries.append({"tab":"jumps","race":race})

    if not horses_needed: log("No horses to check"); return

    try:
        if TEST_MODE or args.fixture:
            fixture_path = args.fixture or "tests/fixtures/results_positions.json"
            raw = get_positions_test(fixture_path)
        else:
            if not ANTHROPIC_KEY: log("No API key"); return
            raw = get_positions_live(horses_needed)
    except Exception as e:
        log(f"Failed to get positions: {e}"); return

    positions = {p["name"].upper():p for p in raw.get("positions",[])}
    flat_r,jumps_r,picks_calc = [],[],[]

    for entry in all_entries:
        race = entry["race"]
        h = race["horses"][0]
        name = h["name"].upper()
        pd = positions.get(name,{"position":0,"ran":race.get("runners",8)})
        pos = pd.get("position",0)
        ran = pd.get("ran",race.get("runners",8))
        odds = h.get("odds",2.0)
        result_str = determine_result(pos,ran)
        w,p,t = calculate_ew_return(odds,result_str,ran)
        ro = {"position":pos,"result":result_str,"winReturn":w,"placeReturn":p,"totalReturn":t}
        h["result"] = result_str; h["position"] = pos
        picks_calc.append({"win":w,"place":p})
        if entry["tab"]=="flat": flat_r.append(ro)
        else: jumps_r.append(ro)

    patent_return,patent_profit = calculate_patent(picks_calc)
    complete = all(r["result"] not in ["","PENDING"] for r in flat_r+jumps_r)

    picks["results"] = {"flat":flat_r,"jumps":jumps_r,"patentReturn":patent_return,
                        "patentProfit":patent_profit,"complete":complete,
                        "updatedAt":datetime.now(timezone.utc).isoformat()}
    picks["updatedAt"] = datetime.now(timezone.utc).isoformat()

    with open(args.picks_file,"w") as f: json.dump(picks,f,indent=2)
    log("picks.json updated")

    if os.path.exists(archive_path):
        with open(archive_path) as f: archive = json.load(f)
        if "morningSnapshot" not in archive:
            archive["morningSnapshot"] = {"flat":archive.get("flat",[]),"jumps":archive.get("jumps",[]),
                "topRated":archive.get("topRated",[]),"mode":archive.get("mode",""),
                "lockedAt":archive.get("generatedAt","")}
        archive["results"] = picks["results"]
        archive["updatedAt"] = picks["updatedAt"]
        with open(archive_path,"w") as f: json.dump(archive,f,indent=2)
        log(f"Archive updated: {archive_path}")

    log(f"Patent: £{patent_return} | Profit: £{patent_profit} | Complete: {complete}")
    for r in flat_r: log(f"   FLAT: {r['result']} pos={r['position']} → £{r['totalReturn']}")
    for r in jumps_r: log(f"   JUMPS: {r['result']} pos={r['position']} → £{r['totalReturn']}")

if __name__=="__main__": main()
