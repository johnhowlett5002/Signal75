#!/usr/bin/env python3
"""
Signal 75 - Evening Results Updater
Uses Betfair API for results — reliable, free, instant.
Falls back to web search if Betfair API fails.
"""
import os, json, re, subprocess, traceback, importlib.util
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
RUNNERS_CACHE = os.path.join(REPO_PATH, "data/today_runners.json")
LOG_FILE = os.path.join(REPO_PATH, "data", "signal75-results.log")
STAKE_EW = 0.50
TOTAL_PATENT_STAKE = 7.0

def normalise_name(name):
    n = name.lower()
    n = n.replace("'", "").replace("\u2019", "")
    n = re.sub(r"[^a-z0-9 ]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

def calculate_ew_return(odds, result, runners):
    place_frac = 0.20 if runners >= 16 else 0.25
    win_profit = odds - 1
    if result == "WON":
        w = odds * STAKE_EW
        p = (1 + win_profit * place_frac) * STAKE_EW
    elif result == "PLACED":
        w, p = 0.0, (1 + win_profit * place_frac) * STAKE_EW
    elif result == "VOID":
        w, p = STAKE_EW, STAKE_EW
    else:
        w, p = 0.0, 0.0
    return round(w, 2), round(p, 2), round(w + p, 2)

def calculate_patent(flat_r, jumps_r, flat_races, jumps_races):
    all_r = flat_r + jumps_r
    all_races = flat_races + jumps_races
    if len(all_r) < 3:
        total = sum(r.get("totalReturn", 0) for r in all_r)
        return round(total, 2), round(total - len(all_r) * 2 * STAKE_EW, 2)
    picks_data = []
    for i, r in enumerate(all_r[:3]):
        odds = all_races[i]["horses"][0]["odds"] if i < len(all_races) and all_races[i].get("horses") else 2.0
        runners = all_races[i].get("runners", 8) if i < len(all_races) else 8
        w, p, _ = calculate_ew_return(odds, r.get("result", "LOST"), runners)
        picks_data.append({"win": w, "place": p})
    h1, h2, h3 = picks_data
    singles = sum(h["win"] + h["place"] for h in picks_data)
    d1w = (h1["win"]*h2["win"])/STAKE_EW if h1["win"] and h2["win"] else 0
    d1p = (h1["place"]*h2["place"])/STAKE_EW if h1["place"] and h2["place"] else 0
    d2w = (h1["win"]*h3["win"])/STAKE_EW if h1["win"] and h3["win"] else 0
    d2p = (h1["place"]*h3["place"])/STAKE_EW if h1["place"] and h3["place"] else 0
    d3w = (h2["win"]*h3["win"])/STAKE_EW if h2["win"] and h3["win"] else 0
    d3p = (h2["place"]*h3["place"])/STAKE_EW if h2["place"] and h3["place"] else 0
    doubles = d1w+d1p+d2w+d2p+d3w+d3p
    tw = (h1["win"]*h2["win"]*h3["win"])/STAKE_EW**2 if all(h["win"] for h in picks_data) else 0
    tp = (h1["place"]*h2["place"]*h3["place"])/STAKE_EW**2 if all(h["place"] for h in picks_data) else 0
    total = round(singles + doubles + tw + tp, 2)
    return total, round(total - TOTAL_PATENT_STAKE, 2)

def calculate_patent_from_returns(results):
    if len(results) < 3:
        return 0.0, 0.0

    picks_data = [{"win": r.get("winReturn", 0), "place": r.get("placeReturn", 0)} for r in results[:3]]
    h1, h2, h3 = picks_data
    singles = sum(h["win"] + h["place"] for h in picks_data)
    d1w = (h1["win"]*h2["win"])/STAKE_EW if h1["win"] and h2["win"] else 0
    d1p = (h1["place"]*h2["place"])/STAKE_EW if h1["place"] and h2["place"] else 0
    d2w = (h1["win"]*h3["win"])/STAKE_EW if h1["win"] and h3["win"] else 0
    d2p = (h1["place"]*h3["place"])/STAKE_EW if h1["place"] and h3["place"] else 0
    d3w = (h2["win"]*h3["win"])/STAKE_EW if h2["win"] and h3["win"] else 0
    d3p = (h2["place"]*h3["place"])/STAKE_EW if h2["place"] and h3["place"] else 0
    doubles = d1w+d1p+d2w+d2p+d3w+d3p
    tw = (h1["win"]*h2["win"]*h3["win"])/STAKE_EW**2 if all(h["win"] for h in picks_data) else 0
    tp = (h1["place"]*h2["place"]*h3["place"])/STAKE_EW**2 if all(h["place"] for h in picks_data) else 0
    total = round(singles + doubles + tw + tp, 2)
    return total, round(total - TOTAL_PATENT_STAKE, 2)

def determine_result(position, status, runners):
    s = str(status).upper().strip() if status else ""
    if s in ("NR","NON-RUNNER","WITHDRAWN","W","VOID","REMOVED"):
        return "VOID"
    if s in ("LOSER","PU","PULLED UP","F","FELL","UR","UNSEATED","BD","BROUGHT DOWN","RO","RAN OUT","SU","SLIPPED UP","REF","REFUSED"):
        return "LOST"
    pos = int(position) if position else 0
    if pos == 0: return "PENDING"
    if pos == 1: return "WON"
    if runners < 8 and pos == 2: return "PLACED"
    if 8 <= runners <= 11 and pos <= 3: return "PLACED"
    if runners >= 12 and pos <= 4: return "PLACED"
    return "LOST"

def load_market_ids_from_cache(race_date):
    if not os.path.exists(RUNNERS_CACHE):
        log("  No today_runners.json — will use web search fallback")
        return {}
    try:
        with open(RUNNERS_CACHE) as f:
            data = json.load(f)
        cache_date = data.get("date", "")
        if cache_date != race_date:
            log(f"  Runner cache is from {cache_date} not {race_date} — web search fallback")
            return {}
        name_to_market = {}
        for race in data.get("races", []):
            market_id = race.get("market_id", "")
            field_size = race.get("field_size", 8)
            for runner in race.get("runners", []):
                norm = normalise_name(runner["name"])
                name_to_market[norm] = {
                    "market_id": market_id,
                    "selection_id": runner.get("selection_id"),
                    "field_size": field_size,
                    "runner_name": runner["name"]
                }
        log(f"  Loaded {len(name_to_market)} runners from today_runners.json")
        return name_to_market
    except Exception as e:
        log(f"  Runner cache load failed: {e}")
        return {}

def get_betfair_client():
    import betfairlightweight
    USERNAME = "john.howlett@madasafish.com"
    PASSWORD = "Mindlessprawn!234"
    APP_KEY  = "MMtmHw3b1lAkKBWf"
    trading = betfairlightweight.APIClient(username=USERNAME, password=PASSWORD, app_key=APP_KEY)
    trading.login_interactive()
    return trading

def get_positions_betfair(horses_needed, race_date):
    log("  Fetching results from Betfair API...")
    name_to_market = load_market_ids_from_cache(race_date)
    if not name_to_market:
        return None
    try:
        trading = get_betfair_client()
        log("  Betfair login OK")
    except Exception as e:
        log(f"  Betfair login failed: {e}")
        return None
    market_ids_needed = set()
    for h in horses_needed:
        norm = normalise_name(h["name"])
        if norm in name_to_market:
            market_ids_needed.add(name_to_market[norm]["market_id"])
    if not market_ids_needed:
        log("  No market IDs found")
        return None
    try:
        books = trading.betting.list_market_book(
            market_ids=list(market_ids_needed),
            price_projection={"priceData": ["SP_TRADED"]}
        )
    except Exception as e:
        log(f"  list_market_book failed: {e}")
        return None
    market_results = {}
    for book in books:
        market_results[book.market_id] = {}
        for runner in book.runners:
            market_results[book.market_id][runner.selection_id] = {
                "status": runner.status,
                "sp": runner.sp.actual_sp if runner.sp and runner.sp.actual_sp else None,
                "sort_priority": getattr(runner, "sort_priority", 0),
            }
    positions = []
    for h in horses_needed:
        norm = normalise_name(h["name"])
        horse_name = h["name"]
        if norm not in name_to_market:
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": 8, "sp": None})
            continue
        market_info = name_to_market[norm]
        market_id = market_info["market_id"]
        selection_id = market_info["selection_id"]
        field_size = market_info["field_size"]
        if market_id not in market_results:
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": field_size, "sp": None})
            continue
        runner_data = market_results[market_id].get(selection_id)
        if not runner_data:
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": field_size, "sp": None})
            continue
        bf_status = str(runner_data["status"]).upper()
        sort_priority = runner_data.get("sort_priority", 0)
        sp = runner_data.get("sp")
        if bf_status == "WINNER": position, status = 1, "OK"
        elif bf_status == "PLACED": position, status = sort_priority or 2, "OK"
        elif bf_status == "LOSER": position, status = sort_priority or 0, "LOSER"
        elif bf_status == "REMOVED": position, status = 0, "NR"
        elif bf_status == "ACTIVE": position, status = 0, "PENDING"
        else: position, status = 0, "PENDING"
        log(f"  ✅ {horse_name} — {bf_status} pos:{position} sp:{sp}")
        positions.append({"name": horse_name, "position": position, "status": status, "ran": field_size, "sp": sp})
    log(f"  Betfair: {len(positions)} horses processed")
    return {"positions": positions}

def get_positions_websearch(horses_needed, race_date):
    log("  Using web search fallback...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    race_date_display = datetime.strptime(race_date, "%Y-%m-%d").strftime("%A %d %B %Y")
    names_with_details = []
    for h in horses_needed:
        detail = h["name"]
        if h.get("course"): detail += " (" + h.get("time","") + " " + h.get("course","") + ")"
        names_with_details.append(detail)
    prompt = (
        "Find official race results for these UK racehorses from " + race_date_display + ": "
        + ", ".join(names_with_details)
        + ". Check racingpost.com and sportinglife.com. "
        + "Return ONLY JSON: {\"positions\":[{\"name\":\"HORSE\",\"position\":3,\"status\":\"OK\",\"ran\":12}]}. "
        + "status=NR for non-runners, status=PU for pulled up, status=PENDING if not available. Include ALL horses."
    )
    message = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=800,
        system="You are a JSON API. Return only valid JSON, nothing else.",
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )
    response_text = ""
    for block in message.content:
        if hasattr(block, "text"): response_text += block.text
    response_text = response_text.strip()
    if not response_text: raise ValueError("No response from web search")
    response_text = re.sub(r"```(?:json)?\s*", "", response_text)
    response_text = re.sub(r"```", "", response_text).strip()
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1: raise ValueError("No JSON in response")
    result = json.loads(response_text[start:end+1])
    log(f"  Web search: {len(result.get('positions', []))} positions found")
    return result

def get_positions(horses_needed, race_date):
    try:
        result = get_positions_betfair(horses_needed, race_date)
        if result and result.get("positions"):
            non_pending = [p for p in result["positions"] if p["status"] != "PENDING"]
            if non_pending:
                log(f"✅ Results via Betfair API ({len(non_pending)} settled)")
                return result
            else:
                log("  Betfair: all PENDING — races may not have run yet")
                return result
    except Exception as e:
        log(f"  Betfair failed: {e} — trying web search")
    if not ANTHROPIC_KEY:
        log("⚠️  No Anthropic API key — cannot use web search fallback")
        return {"positions": [{"name": h["name"], "position": 0, "status": "PENDING", "ran": 8, "sp": None} for h in horses_needed]}
    log("⚠️  Falling back to web search")
    return get_positions_websearch(horses_needed, race_date)

def settle_consensus_shadow(race_date):
    shadow_path = os.path.join(REPO_PATH, "data", f"consensus_shadow_{race_date}.json")
    if not os.path.exists(shadow_path):
        return None

    try:
        with open(shadow_path) as f:
            shadow = json.load(f)
    except Exception as e:
        log(f"⚠️ consensus shadow load failed: {e}")
        return None

    horses_needed, seen = [], set()
    for variant in shadow.get("variants", {}).values():
        for pick in variant.get("picks", []):
            key = normalise_name(pick.get("name", "")) + "|" + pick.get("time", "") + "|" + pick.get("course", "")
            if pick.get("name") and key not in seen:
                seen.add(key)
                horses_needed.append({
                    "name": pick.get("name"),
                    "course": pick.get("course", ""),
                    "time": pick.get("time", ""),
                })

    if not horses_needed:
        return shadow_path

    log(f"Settling consensus shadow: {len(horses_needed)} unique horses")
    raw = get_positions(horses_needed, race_date)
    positions = {normalise_name(p["name"]): p for p in raw.get("positions", [])}

    settled = {}
    for name, variant in shadow.get("variants", {}).items():
        results = []
        for pick in variant.get("picks", []):
            pd = positions.get(normalise_name(pick.get("name", "")), {})
            pos = pd.get("position", 0)
            ran = pd.get("ran", pick.get("runners", 8) or 8)
            result_str = determine_result(pos, pd.get("status", ""), ran)
            w, p, t = calculate_ew_return(float(pick.get("bsp") or 2.0), result_str, ran)
            results.append({
                "name": pick.get("name"),
                "position": pos,
                "result": result_str,
                "winReturn": w,
                "placeReturn": p,
                "totalReturn": t,
            })

        patent_return, patent_profit = calculate_patent_from_returns(results)
        settled[name] = {
            "noBet": len(results) < 3,
            "complete": all(r["result"] not in ("", "PENDING") for r in results),
            "patentReturn": patent_return,
            "patentProfit": patent_profit,
            "results": results,
        }
        log(f"  Shadow {name}: £{patent_return} | Profit £{patent_profit}")

    shadow["results"] = settled
    shadow["settledAt"] = datetime.now(timezone.utc).isoformat()
    with open(shadow_path, "w") as f:
        json.dump(shadow, f, indent=2)
    log(f"✅ consensus shadow settled: data/consensus_shadow_{race_date}.json")
    return shadow_path

def push_to_github(race_date):
    archive_path = f"data/{race_date}.json"
    add_paths = ["picks.json", archive_path, "performance.json"]
    shadow_path = f"data/consensus_shadow_{race_date}.json"
    if os.path.exists(os.path.join(REPO_PATH, shadow_path)):
        add_paths.append(shadow_path)

    ok = True
    for cmd in [
        ["git", "-C", REPO_PATH, "pull", "--rebase", "--quiet"],
        ["git", "-C", REPO_PATH, "add"] + add_paths,
        ["git", "-C", REPO_PATH, "commit", "-m", f"Results {race_date}"],
        ["git", "-C", REPO_PATH, "push"],
    ]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 and "nothing to commit" not in r.stdout + r.stderr:
            log(f"Warning: {r.stderr.strip()}")
            ok = False
    if ok:
        log("Pushed to GitHub!")
    else:
        log("⚠️ GitHub push step reported warnings — wrapper will retry final publish")

def main():
    log(f"\n{'='*50}\nSignal 75 Results - {TODAY_DISPLAY}\n{'='*50}")
    try:
        with open(PICKS_FILE) as f:
            picks = json.load(f)
        mode = picks.get("mode", "")
        if picks.get("noBetDay"):
            log("Mode=noBetDay — skipping results"); return

        if mode == "topRatedOnly":
            radar_lists = ["topRated", "topRatedFlat", "topRatedJumps"]
            all_radar = []
            seen = set()

            for list_name in radar_lists:
                for h in picks.get(list_name, []):
                    key = normalise_name(h.get("name", "")) + "|" + h.get("time", "") + "|" + h.get("venue", h.get("course", ""))
                    if h.get("name") and key not in seen:
                        seen.add(key)
                        all_radar.append(h)

            if not all_radar:
                log("topRatedOnly but no radar horses — skipping")
                return

            horses_needed = [
                {"name": h["name"], "course": h.get("venue", h.get("course", "")), "time": h.get("time", "")}
                for h in all_radar
            ]

            raw = get_positions(horses_needed, picks.get("date", TODAY))
            positions = {normalise_name(p["name"]): p for p in raw.get("positions", [])}

            def radar_result_text(h):
                pd = positions.get(normalise_name(h.get("name", "")), {})
                pos = pd.get("position", 0)
                status = pd.get("status", "PENDING")

                if status == "PENDING" or (pos == 0 and status not in ("NR","PU","F","UR","BD","REMOVED")):
                    return "Race run — result TBC", pos, status
                if status in ("NR","REMOVED"):
                    return "Non-Runner", pos, status
                if pos == 1:
                    return "1st 🏆", pos, status
                if pos == 2:
                    return "2nd", pos, status
                if pos == 3:
                    return "3rd", pos, status
                if pos:
                    suffix = "th"
                    if pos % 10 == 1 and pos % 100 != 11: suffix = "st"
                    elif pos % 10 == 2 and pos % 100 != 12: suffix = "nd"
                    elif pos % 10 == 3 and pos % 100 != 13: suffix = "rd"
                    return f"{pos}{suffix}", pos, status
                return "Race run — result TBC", pos, status

            for list_name in radar_lists:
                updated = []
                for h in picks.get(list_name, []):
                    txt, pos, status = radar_result_text(h)
                    h["radarResult"] = txt
                    h["position"] = pos
                    h["status"] = status
                    updated.append(h)
                    log(f"  Radar {h.get('name','')} — {txt}")
                picks[list_name] = updated

            picks["results"]["complete"] = True
            picks["results"]["updatedAt"] = datetime.now(timezone.utc).isoformat()
            picks["results"]["_note"] = "Radar day — results stored on topRated/topRatedFlat/topRatedJumps"

            race_date = picks.get("date", TODAY)
            archive_file = os.path.join(REPO_PATH, "data", f"{race_date}.json")
            os.makedirs(os.path.dirname(archive_file), exist_ok=True)

            with open(PICKS_FILE, "w") as f:
                json.dump(picks, f, indent=2)

            with open(archive_file, "w") as f:
                json.dump(picks, f, indent=2)

            try:
                spec = importlib.util.spec_from_file_location("gp", os.path.join(REPO_PATH, "scripts/generate-performance.py"))
                gp = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gp)
                gp.main()
                log("✅ performance.json updated")
            except Exception as pe:
                log(f"⚠️ performance.json failed: {pe}")

            settle_consensus_shadow(race_date)
            push_to_github(race_date)
            log("Radar results saved, archived and pushed")
            return

        horses_needed, all_entries = [], []
        for race in picks.get("flat", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_entries.append({"tab": "flat", "race": race})
        for race in picks.get("jumps", []):
            if race.get("horses"):
                h = race["horses"][0]
                horses_needed.append({"name": h["name"], "course": race["course"], "time": race["time"]})
                all_entries.append({"tab": "jumps", "race": race})

        race_date = picks.get("date", TODAY)
        archive_file = os.path.join(REPO_PATH, "data", f"{race_date}.json")
        if not horses_needed:
            log("No horses to check"); return

        log(f"Fetching results for {len(horses_needed)} horses...")
        raw = get_positions(horses_needed, race_date)
        positions = {normalise_name(p["name"]): p for p in raw.get("positions", [])}

        flat_r, jumps_r, flat_races, jumps_races = [], [], [], []
        for entry in all_entries:
            race = entry["race"]
            h = race["horses"][0]
            name = normalise_name(h["name"])
            pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            pos = pd.get("position", 0)
            ran = pd.get("ran", race.get("runners", 8))
            odds = h.get("odds", 2.0)
            result_str = determine_result(pos, pd.get("status", ""), ran)
            w, p, t = calculate_ew_return(odds, result_str, ran)
            ro = {"position": pos, "result": result_str, "winReturn": w, "placeReturn": p, "totalReturn": t}
            h["result"] = result_str
            h["position"] = pos
            log(f"  {h['name']} — {result_str} (pos:{pos})")
            if entry["tab"] == "flat":
                flat_r.append(ro); flat_races.append(race)
            else:
                jumps_r.append(ro); jumps_races.append(race)

        patent_return, patent_profit = calculate_patent(flat_r, jumps_r, flat_races, jumps_races)
        complete = all(r["result"] not in ["", "PENDING"] for r in flat_r + jumps_r)

        picks["results"] = {
            "flat": flat_r, "jumps": jumps_r,
            "patentReturn": patent_return, "patentProfit": patent_profit,
            "complete": complete,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }

        with open(PICKS_FILE, "w") as f:
            json.dump(picks, f, indent=2)

        # Archive completed day for performance/history rebuild
        race_date = picks.get("date", TODAY)
        archive_file = os.path.join(REPO_PATH, "data", f"{race_date}.json")
        os.makedirs(os.path.dirname(archive_file), exist_ok=True)
        with open(archive_file, "w") as f:
            json.dump(picks, f, indent=2)
        log(f"✅ Archived completed day: data/{race_date}.json")
        if os.path.exists(archive_file):
            with open(archive_file, "w") as f:
                json.dump(picks, f, indent=2)

        log(f"Patent: £{patent_return} | Profit: £{patent_profit} | Complete: {complete}")

        try:
            spec = importlib.util.spec_from_file_location("gp", os.path.join(REPO_PATH, "scripts/generate-performance.py"))
            gp = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gp)
            gp.main()
            log("✅ performance.json updated")
        except Exception as pe:
            log(f"⚠️ performance.json failed: {pe}")

        settle_consensus_shadow(race_date)
        push_to_github(race_date)

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
