#!/usr/bin/env python3
"""
Signal 75 - Evening Results Updater
Uses Betfair API for results — reliable, free, instant.
Falls back to web search if Betfair API fails.
"""
import os, json, re, subprocess, traceback, importlib.util, urllib.request, html
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
RUNNERS_CACHE = os.path.join(REPO_PATH, "data/today_runners.json")
LOG_FILE = os.path.join(REPO_PATH, "data", "signal75-results.log")
INTEL_DIR = os.path.join(REPO_PATH, "data", "horse_intelligence")
HORSE_PROFILES_FILE = os.path.join(INTEL_DIR, "horse_profiles.json")
HORSE_HISTORY_MASTER = os.path.join(INTEL_DIR, "horse_history_master.jsonl")
STAKE_EW = 1.00
TOTAL_PATENT_STAKE = 14.0

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
    pos = int(position) if position else 0
    if s in ("PU","PULLED UP","F","FELL","UR","UNSEATED","BD","BROUGHT DOWN","RO","RAN OUT","SU","SLIPPED UP","REF","REFUSED"):
        return "LOST"
    if s == "LOSER" and pos == 0:
        return "LOST"
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

def get_market_lookup(race_date):
    return load_market_ids_from_cache(race_date)

def course_slug(course):
    slug = (course or "").lower()
    slug = re.sub(r"\s+\d+(st|nd|rd|th)?\s+\w+$", "", slug)
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug

def parse_ordinal_position(text):
    if not text:
        return 0
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", html.unescape(str(text)), re.I)
    return int(m.group(1)) if m else 0

def fetch_horseracing_net_positions(horses_needed, race_date):
    """Public fallback for finish order when Betfair settles LOSER without a place."""
    try:
        dt = datetime.strptime(race_date, "%Y-%m-%d")
    except Exception:
        return {}

    wanted_by_course = {}
    for h in horses_needed:
        slug = course_slug(h.get("course", ""))
        if slug:
            wanted_by_course.setdefault(slug, []).append(h)

    found = {}
    for slug, course_horses in wanted_by_course.items():
        url = f"https://www.horseracing.net/results/{slug}/{dt.strftime('%d-%m-%y')}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", "ignore")
        except Exception as e:
            log(f"  Finish-position fallback failed for {slug}: {e}")
            continue

        rows = re.split(r'<li class="results-table-row"', text)
        course_positions = {}
        for row in rows[1:]:
            name_match = re.search(r'class="runner-title"[^>]*>\s*([^<]+?)\s*</a>', row, re.I | re.S)
            if not name_match:
                continue
            name = html.unescape(re.sub(r"\s+", " ", name_match.group(1))).strip()
            pos_match = re.search(r'class="number position"[^>]*>(.*?)</span>\s*</div>', row, re.I | re.S)
            pos = parse_ordinal_position(pos_match.group(1) if pos_match else "")
            if name and pos:
                course_positions[normalise_name(name)] = pos

        for h in course_horses:
            key = normalise_name(h.get("name", ""))
            if key in course_positions:
                found[key] = course_positions[key]
                log(f"  Finish-position fallback: {h.get('name')} — pos:{course_positions[key]}")

    return found

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
    finish_positions = fetch_horseracing_net_positions(horses_needed, race_date)
    positions = []
    for h in horses_needed:
        norm = normalise_name(h["name"])
        horse_name = h["name"]
        fallback_pos = finish_positions.get(norm, 0)
        if norm not in name_to_market:
            if fallback_pos:
                positions.append({"name": horse_name, "position": fallback_pos, "status": "OK", "ran": h.get("runners", 8), "sp": None})
                continue
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": 8, "sp": None})
            continue
        market_info = name_to_market[norm]
        market_id = market_info["market_id"]
        selection_id = market_info["selection_id"]
        field_size = market_info["field_size"]
        if market_id not in market_results:
            if fallback_pos:
                positions.append({"name": horse_name, "position": fallback_pos, "status": "OK", "ran": field_size, "sp": None})
                continue
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": field_size, "sp": None})
            continue
        runner_data = market_results[market_id].get(selection_id)
        if not runner_data:
            if fallback_pos:
                positions.append({"name": horse_name, "position": fallback_pos, "status": "OK", "ran": field_size, "sp": None})
                continue
            positions.append({"name": horse_name, "position": 0, "status": "PENDING", "ran": field_size, "sp": None})
            continue
        bf_status = str(runner_data["status"]).upper()
        sort_priority = runner_data.get("sort_priority", 0)
        sp = runner_data.get("sp")
        if bf_status == "WINNER": position, status = 1, "OK"
        elif bf_status == "PLACED": position, status = sort_priority or 2, "OK"
        elif bf_status == "LOSER": position, status = sort_priority or finish_positions.get(norm, 0), "LOSER"
        elif bf_status == "REMOVED": position, status = 0, "NR"
        elif bf_status == "ACTIVE" and finish_positions.get(norm, 0):
            position, status = finish_positions.get(norm, 0), "OK"
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

def settle_late_value_shadow(race_date):
    shadow_path = os.path.join(REPO_PATH, "data", f"late_value_shadow_{race_date}.json")
    if not os.path.exists(shadow_path):
        return None

    try:
        with open(shadow_path) as f:
            shadow = json.load(f)
    except Exception as e:
        log(f"⚠️ late-value shadow load failed: {e}")
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

    log(f"Settling late-value shadow: {len(horses_needed)} unique horses")
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
            odds = pick.get("late_bsp") or pick.get("morning_bsp") or 2.0
            w, p, t = calculate_ew_return(float(odds), result_str, ran)
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
        log(f"  Late-value {name}: £{patent_return} | Profit £{patent_profit}")

    shadow["results"] = settled
    shadow["settledAt"] = datetime.now(timezone.utc).isoformat()
    with open(shadow_path, "w") as f:
        json.dump(shadow, f, indent=2)
    log(f"✅ late-value shadow settled: data/late_value_shadow_{race_date}.json")
    return shadow_path

def safe_float(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None

def safe_int(value):
    try:
        if value in ("", None):
            return None
        return int(value)
    except Exception:
        return None

def ordinal_suffix(position):
    if not position:
        return None
    if position % 10 == 1 and position % 100 != 11:
        return "st"
    if position % 10 == 2 and position % 100 != 12:
        return "nd"
    if position % 10 == 3 and position % 100 != 13:
        return "rd"
    return "th"

def get_position_map_for_candidates(candidates, race_date):
    needed, seen = [], set()
    for c in candidates:
        name = c.get("horse_name") or c.get("name")
        if not name:
            continue
        key = normalise_name(name) + "|" + str(c.get("time", "")) + "|" + str(c.get("course", ""))
        if key in seen:
            continue
        seen.add(key)
        needed.append({"name": name, "course": c.get("course", ""), "time": c.get("time", "")})
    if not needed:
        return {}
    raw = get_positions(needed, race_date)
    return {normalise_name(p.get("name", "")): p for p in raw.get("positions", [])}

def result_from_position_data(candidate, position_data):
    runners = safe_int(position_data.get("ran")) or safe_int(candidate.get("field_size")) or safe_int(candidate.get("runners")) or 8
    pos = safe_int(position_data.get("position")) or 0
    status = position_data.get("status", "")
    result = determine_result(pos, status, runners)
    return result, pos, runners

def public_result_text(result, position):
    pos = safe_int(position) or 0
    pos_text = f"{pos}{ordinal_suffix(pos)}".upper() if pos else ""
    if result == "WON":
        return f"WON - {pos_text or '1ST'}"
    if result == "PLACED":
        return f"PLACED - {pos_text}" if pos_text else "PLACED"
    if result == "VOID":
        return "NON-RUNNER"
    if result == "PENDING":
        return "Race run — result TBC"
    if pos_text:
        return pos_text
    return "UNPLACED"

def settle_radar_cards(picks, race_date):
    radar_lists = ("topRated", "topRatedFlat", "topRatedJumps")
    candidates, seen = [], set()

    for list_name in radar_lists:
        for h in picks.get(list_name, []):
            name = h.get("name") or h.get("horse")
            if not name:
                continue
            key = normalise_name(name) + "|" + str(h.get("time", "")) + "|" + str(h.get("venue") or h.get("course") or "")
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "name": name,
                "course": h.get("venue") or h.get("course", ""),
                "time": h.get("time", ""),
                "field_size": h.get("runners"),
            })

    if not candidates:
        return 0

    raw = get_positions(candidates, race_date)
    positions = {normalise_name(p.get("name", "")): p for p in raw.get("positions", [])}
    updated = 0

    for list_name in radar_lists:
        for h in picks.get(list_name, []):
            name = h.get("name") or h.get("horse")
            if not name:
                continue
            pd = positions.get(normalise_name(name), {})
            result, pos, runners = result_from_position_data(h, pd) if pd else ("PENDING", safe_int(h.get("position")) or 0, safe_int(h.get("runners")) or None)
            h["result"] = result
            h["position"] = pos
            h["status"] = pd.get("status", h.get("status", ""))
            h["runners"] = runners or h.get("runners")
            h["radarResult"] = public_result_text(result, pos)
            h["radarSettled"] = result not in ("", "PENDING")
            updated += 1
            log(f"  Radar {name} — {h['radarResult']}")

    return updated

def get_result_by_name(results, name):
    norm = normalise_name(name or "")
    for r in results or []:
        if normalise_name(r.get("name", "")) == norm:
            return r
    return {}

def derive_interpretation(record):
    labels = []
    result = record.get("result")
    score = record.get("signal_score") or 0
    consensus_count = record.get("consensus_count") or 0
    market_conflict = record.get("market_conflict") is True
    is_positive = result in ("WON", "PLACED")

    if record.get("official_pick") and is_positive:
        labels.append("CONFIRMED_MODEL")
    if result == "WON" and score and score < 75:
        labels.append("OUTRAN_SCORE")
    if result == "LOST" and score and score >= 85:
        labels.append("UNDERPERFORMED")
    if is_positive and record.get("bsp"):
        labels.append("MARKET_WAS_RIGHT")
    if record.get("official_pick") and is_positive:
        labels.append("MODEL_WAS_RIGHT")
    if consensus_count > 0 and is_positive:
        labels.append("TIPSTERS_RIGHT")
    if consensus_count > 0 and result == "LOST":
        labels.append("TIPSTERS_WRONG")
    if market_conflict and result == "LOST":
        labels.append("MARKET_WAS_RIGHT")
    if result == "PLACED" and score and score >= 75:
        labels.append("POSSIBLE_NEXT_TIME_OUT")
    return labels

def base_intel_record(race_date, selection_type, name, course="", time="", race_type=None):
    is_shadow = selection_type in ("SHADOW_CONSENSUS_PICK", "SHADOW_LATE_VALUE_PICK")
    return {
        "date": race_date,
        "horse_name": name,
        "normalised_name": normalise_name(name or ""),
        "selection_type": selection_type,
        "course": course or None,
        "time": time or None,
        "race_type": race_type,
        "market_id": None,
        "signal_score": None,
        "rank": None,
        "bsp": None,
        "sp": None,
        "official_pick": selection_type == "OFFICIAL_PICK",
        "radar_pick": selection_type == "RADAR_PICK",
        "shadow_pick": is_shadow,
        "was_public_pick": selection_type == "OFFICIAL_PICK",
        "was_radar": selection_type == "RADAR_PICK",
        "was_shadow_pick": is_shadow,
        "was_rejected": selection_type == "REJECTED_BY_GATE",
        "consensus_count": 0,
        "consensus_sources": [],
        "confidence_flags": [],
        "decay_flags": [],
        "market_conflict": False,
        "result": "PENDING",
        "finishing_position": None,
        "position_text": None,
        "return": 0.0,
        "patent_contribution": 0.0,
        "beaten_distance": None,
        "winning_distance": None,
        "field_size": None,
        "going": None,
        "class": None,
        "distance": None,
        "jockey": None,
        "trainer": None,
        "raw": {},
        "interpretation": [],
    }

def record_id(record):
    return "|".join([
        record.get("date") or "",
        record.get("selection_type") or "",
        record.get("shadow_variant") or "",
        record.get("normalised_name") or "",
        record.get("course") or "",
        record.get("time") or "",
    ])

def attach_record_id(record):
    record["record_id"] = record_id(record)
    return record

def build_official_records(picks):
    race_date = picks.get("date", TODAY)
    records = []
    flat_results = picks.get("results", {}).get("flat", [])
    jumps_results = picks.get("results", {}).get("jumps", [])
    rank = 1

    for tab, races, results in (("flat", picks.get("flat", []), flat_results), ("jumps", picks.get("jumps", []), jumps_results)):
        for idx, race in enumerate(races):
            horses = race.get("horses", [])
            if not horses:
                continue
            h = horses[0]
            res = results[idx] if idx < len(results) else {}
            consensus = h.get("consensus") or {}
            rec = base_intel_record(race_date, "OFFICIAL_PICK", h.get("name", ""), race.get("course", ""), race.get("time", ""), race.get("type"))
            rec.update({
                "signal_score": safe_float(h.get("signal_score")),
                "rank": rank,
                "bsp": safe_float(h.get("odds")),
                "result": res.get("result") or h.get("result") or "PENDING",
                "finishing_position": safe_int(res.get("position", h.get("position"))),
                "return": safe_float(res.get("totalReturn")) or 0.0,
                "patent_contribution": safe_float(res.get("totalReturn")) or 0.0,
                "field_size": safe_int(race.get("runners")),
                "going": race.get("going") or None,
                "distance": race.get("distance") or None,
                "jockey": h.get("jockey") or None,
                "trainer": h.get("trainer") or None,
                "consensus_count": safe_int(consensus.get("source_count")) or safe_int(h.get("tipsters")) or 0,
                "consensus_sources": consensus.get("sources") or [],
                "market_conflict": bool(consensus.get("warning")),
                "raw": {"tab": tab, "horse": h, "race": race, "result": res},
            })
            if rec["finishing_position"]:
                rec["position_text"] = f"{rec['finishing_position']}{ordinal_suffix(rec['finishing_position'])}"
            rec["interpretation"] = derive_interpretation(rec)
            records.append(attach_record_id(rec))
            rank += 1
    return records

def build_radar_records(picks, position_map):
    race_date = picks.get("date", TODAY)
    records, seen = [], set()
    radar_sources = [
        ("topRated", picks.get("topRated", [])),
        ("topRatedFlat", picks.get("topRatedFlat", [])),
        ("topRatedJumps", picks.get("topRatedJumps", [])),
    ]
    for source_name, horses in radar_sources:
        for idx, h in enumerate(horses):
            name = h.get("name") or h.get("horse")
            if not name:
                continue
            key = normalise_name(name) + "|" + h.get("time", "") + "|" + (h.get("venue") or h.get("course") or "")
            if key in seen:
                continue
            seen.add(key)
            pd = position_map.get(normalise_name(name), {})
            result, pos, runners = result_from_position_data(h, pd) if pd else ("PENDING", safe_int(h.get("position")), safe_int(h.get("runners")) or None)
            if h.get("radarResult") and h.get("radarResult") not in ("", "Race run — result TBC"):
                if "1st" in h["radarResult"]:
                    result, pos = "WON", 1
                elif h["radarResult"].lower().startswith("non-runner"):
                    result, pos = "VOID", 0
            rec = base_intel_record(race_date, "RADAR_PICK", name, h.get("venue") or h.get("course", ""), h.get("time", ""), h.get("race_type") or h.get("type"))
            rec.update({
                "signal_score": safe_float(h.get("signal_score") or h.get("qualificationScore")),
                "rank": idx + 1,
                "bsp": safe_float(h.get("odds")),
                "sp": safe_float(pd.get("sp")) if pd else None,
                "result": result or "PENDING",
                "finishing_position": pos,
                "return": 0.0,
                "patent_contribution": 0.0,
                "field_size": runners,
                "distance": h.get("race") or None,
                "consensus_count": safe_int((h.get("consensus") or {}).get("source_count")) or 0,
                "consensus_sources": (h.get("consensus") or {}).get("sources") or [],
                "raw": {"source": source_name, "horse": h, "position": pd},
            })
            if rec["finishing_position"]:
                rec["position_text"] = f"{rec['finishing_position']}{ordinal_suffix(rec['finishing_position'])}"
            rec["interpretation"] = derive_interpretation(rec)
            records.append(attach_record_id(rec))
    return records

def load_shadow_records(race_date):
    shadow_path = os.path.join(REPO_PATH, "data", f"consensus_shadow_{race_date}.json")
    if not os.path.exists(shadow_path):
        return []
    try:
        with open(shadow_path) as f:
            shadow = json.load(f)
    except Exception as e:
        log(f"⚠️ intelligence shadow load failed: {e}")
        return []
    records = []
    for variant_name, variant in shadow.get("variants", {}).items():
        results = shadow.get("results", {}).get(variant_name, {}).get("results", [])
        for idx, pick in enumerate(variant.get("picks", [])):
            name = pick.get("name")
            if not name:
                continue
            res = get_result_by_name(results, name)
            rec = base_intel_record(race_date, "SHADOW_CONSENSUS_PICK", name, pick.get("course", ""), pick.get("time", ""), pick.get("race_type"))
            rec.update({
                "shadow_variant": variant_name,
                "signal_score": safe_float(pick.get("score")),
                "rank": idx + 1,
                "market_id": pick.get("market_id") or None,
                "bsp": safe_float(pick.get("bsp")),
                "result": res.get("result", "PENDING"),
                "finishing_position": safe_int(res.get("position")),
                "return": safe_float(res.get("totalReturn")) or 0.0,
                "patent_contribution": safe_float(res.get("totalReturn")) or 0.0,
                "consensus_count": safe_int(pick.get("source_count")) or 0,
                "consensus_sources": pick.get("sources") or [],
                "raw": {"variant": variant_name, "pick": pick, "result": res},
            })
            if rec["finishing_position"]:
                rec["position_text"] = f"{rec['finishing_position']}{ordinal_suffix(rec['finishing_position'])}"
            rec["interpretation"] = derive_interpretation(rec)
            records.append(attach_record_id(rec))
    return records

def load_late_value_records(race_date):
    shadow_path = os.path.join(REPO_PATH, "data", f"late_value_shadow_{race_date}.json")
    if not os.path.exists(shadow_path):
        return []
    try:
        with open(shadow_path) as f:
            shadow = json.load(f)
    except Exception as e:
        log(f"⚠️ intelligence late-value shadow load failed: {e}")
        return []
    records = []
    for variant_name, variant in shadow.get("variants", {}).items():
        results = shadow.get("results", {}).get(variant_name, {}).get("results", [])
        for idx, pick in enumerate(variant.get("picks", [])):
            name = pick.get("name")
            if not name:
                continue
            res = get_result_by_name(results, name)
            rec = base_intel_record(race_date, "SHADOW_LATE_VALUE_PICK", name, pick.get("course", ""), pick.get("time", ""), pick.get("race_type"))
            rec.update({
                "shadow_variant": variant_name,
                "signal_score": safe_float(pick.get("late_score")),
                "rank": idx + 1,
                "market_id": pick.get("market_id") or None,
                "bsp": safe_float(pick.get("late_bsp")),
                "result": res.get("result", "PENDING"),
                "finishing_position": safe_int(res.get("position")),
                "return": safe_float(res.get("totalReturn")) or 0.0,
                "patent_contribution": safe_float(res.get("totalReturn")) or 0.0,
                "jockey": pick.get("jockey") or None,
                "trainer": pick.get("trainer") or None,
                "confidence_flags": pick.get("signals") or [],
                "raw": {"variant": variant_name, "pick": pick, "result": res},
            })
            if rec["finishing_position"]:
                rec["position_text"] = f"{rec['finishing_position']}{ordinal_suffix(rec['finishing_position'])}"
            rec["interpretation"] = derive_interpretation(rec)
            records.append(attach_record_id(rec))
    return records

def load_tipster_alert_records(race_date, known_keys, position_map):
    overlay_path = os.path.join(REPO_PATH, "data", f"consensus_overlay_{race_date}.json")
    if not os.path.exists(overlay_path):
        return []
    try:
        with open(overlay_path) as f:
            overlay = json.load(f)
    except Exception as e:
        log(f"⚠️ intelligence overlay load failed: {e}")
        return []
    records = []
    for idx, item in enumerate(overlay.get("matched_to_betfair", [])):
        name = item.get("betfair_name") or item.get("horse")
        key = normalise_name(name or "") + "|" + item.get("time", "") + "|" + item.get("course", "")
        if not name or key in known_keys:
            continue
        pd = position_map.get(normalise_name(name), {})
        result, pos, runners = result_from_position_data(item, pd) if pd else ("PENDING", None, None)
        rec = base_intel_record(race_date, "TIPSTER_ONLY_ALERT", name, item.get("course", ""), item.get("time", ""), None)
        rec.update({
            "rank": idx + 1,
            "result": result,
            "finishing_position": pos,
            "field_size": runners,
            "consensus_count": safe_int(item.get("source_count")) or 0,
            "consensus_sources": item.get("sources") or [],
            "raw": {"overlay": item, "position": pd},
        })
        if rec["finishing_position"]:
            rec["position_text"] = f"{rec['finishing_position']}{ordinal_suffix(rec['finishing_position'])}"
        rec["interpretation"] = derive_interpretation(rec)
        records.append(attach_record_id(rec))
    return records

def choose_intelligence_path(race_date):
    os.makedirs(INTEL_DIR, exist_ok=True)
    canonical = os.path.join(INTEL_DIR, f"race_intelligence_{race_date}.json")
    if not os.path.exists(canonical):
        return canonical
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(INTEL_DIR, f"race_intelligence_{race_date}_{stamp}.json")

def append_master_history(records):
    os.makedirs(INTEL_DIR, exist_ok=True)
    existing = set()
    if os.path.exists(HORSE_HISTORY_MASTER):
        with open(HORSE_HISTORY_MASTER) as f:
            for line in f:
                try:
                    existing.add(json.loads(line).get("record_id"))
                except Exception:
                    continue
    with open(HORSE_HISTORY_MASTER, "a") as f:
        for rec in records:
            if rec.get("record_id") in existing:
                continue
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            existing.add(rec.get("record_id"))

def iter_intelligence_records():
    if not os.path.isdir(INTEL_DIR):
        return []
    records = []
    for source_index, fname in enumerate(sorted(os.listdir(INTEL_DIR))):
        if not fname.startswith("race_intelligence_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(INTEL_DIR, fname)
        try:
            with open(fpath) as f:
                payload = json.load(f)
            for rec in payload.get("records", []):
                rec["_source_file"] = fname
                rec["_source_index"] = source_index
                records.append(rec)
        except Exception as e:
            log(f"⚠️ intelligence profile skip {fname}: {e}")
    return records

def profile_trend(records):
    settled = [r for r in records if r.get("result") in ("WON", "PLACED", "LOST")]
    if len(settled) < 2:
        return "UNKNOWN"
    last = settled[-3:]
    positives = sum(1 for r in last if r.get("result") in ("WON", "PLACED"))
    if positives >= 2 and last[-1].get("result") in ("WON", "PLACED"):
        return "IMPROVING"
    if sum(1 for r in last[-2:] if r.get("result") == "LOST") == 2:
        return "DECLINING"
    return "STABLE"

def build_horse_profiles():
    raw_records = iter_intelligence_records()
    by_event = {}
    priority = {
        "OFFICIAL_PICK": 5,
        "RADAR_PICK": 4,
        "SHADOW_CONSENSUS_PICK": 3,
        "REJECTED_BY_GATE": 2,
        "TIPSTER_ONLY_ALERT": 1,
    }
    for rec in raw_records:
        key = "|".join([rec.get("normalised_name", ""), rec.get("date", ""), rec.get("course") or "", rec.get("time") or ""])
        rec_priority = priority.get(rec.get("selection_type"), 0)
        current_priority = priority.get(by_event.get(key, {}).get("selection_type"), 0)
        if key not in by_event or rec_priority > current_priority or (
            rec_priority == current_priority and rec.get("_source_index", 0) >= by_event[key].get("_source_index", 0)
        ):
            by_event[key] = rec

    grouped = {}
    for rec in by_event.values():
        name = rec.get("horse_name")
        if not name:
            continue
        grouped.setdefault(name.upper(), []).append(rec)

    profiles = {}
    for horse, recs in grouped.items():
        recs.sort(key=lambda r: (r.get("date") or "", r.get("time") or ""))
        settled = [r for r in recs if r.get("result") in ("WON", "PLACED", "LOST")]
        wins = sum(1 for r in settled if r.get("result") == "WON")
        places_only = sum(1 for r in settled if r.get("result") == "PLACED")
        losses = sum(1 for r in settled if r.get("result") == "LOST")
        positive = wins + places_only
        scores = [safe_float(r.get("signal_score")) for r in recs if safe_float(r.get("signal_score")) is not None]
        bsps = [safe_float(r.get("bsp")) for r in recs if safe_float(r.get("bsp")) is not None]
        course_record = {}
        going_record = {}
        distance_record = {}

        for r in settled:
            course = r.get("course") or "Unknown"
            course_record.setdefault(course, {"runs": 0, "wins": 0, "places": 0, "losses": 0})
            course_record[course]["runs"] += 1
            if r.get("result") == "WON":
                course_record[course]["wins"] += 1
            elif r.get("result") == "PLACED":
                course_record[course]["places"] += 1
            elif r.get("result") == "LOST":
                course_record[course]["losses"] += 1

            going = r.get("going")
            if going:
                going_record.setdefault(going, {"runs": 0, "wins": 0, "places": 0, "losses": 0})
                going_record[going]["runs"] += 1
                if r.get("result") == "WON":
                    going_record[going]["wins"] += 1
                elif r.get("result") == "PLACED":
                    going_record[going]["places"] += 1
                elif r.get("result") == "LOST":
                    going_record[going]["losses"] += 1

            distance = r.get("distance")
            if distance:
                distance_record.setdefault(distance, {"runs": 0, "wins": 0, "places": 0, "losses": 0})
                distance_record[distance]["runs"] += 1
                if r.get("result") == "WON":
                    distance_record[distance]["wins"] += 1
                elif r.get("result") == "PLACED":
                    distance_record[distance]["places"] += 1
                elif r.get("result") == "LOST":
                    distance_record[distance]["losses"] += 1

        best_going = max(going_record, key=lambda g: (going_record[g]["wins"], going_record[g]["places"], going_record[g]["runs"]), default=None)
        worst_going = max(going_record, key=lambda g: (going_record[g]["losses"], going_record[g]["runs"]), default=None)
        best_distance = max(distance_record, key=lambda d: (distance_record[d]["wins"], distance_record[d]["places"], distance_record[d]["runs"]), default=None)
        last = settled[-1] if settled else (recs[-1] if recs else {})

        profiles[horse] = {
            "total_signal75_runs": len(recs),
            "settled_runs": len(settled),
            "wins": wins,
            "places": places_only,
            "losses": losses,
            "win_rate": round((wins / len(settled)) * 100, 1) if settled else 0.0,
            "place_rate": round((positive / len(settled)) * 100, 1) if settled else 0.0,
            "average_signal_score": round(sum(scores) / len(scores), 1) if scores else None,
            "average_bsp": round(sum(bsps) / len(bsps), 2) if bsps else None,
            "best_going": best_going,
            "worst_going": worst_going,
            "best_distance_band": best_distance,
            "course_record": course_record,
            "going_record": going_record,
            "distance_record": distance_record,
            "trend": profile_trend(recs),
            "last_run_date": last.get("date"),
            "last_result": last.get("result"),
            "signal75_confirmed_runs": sum(1 for r in settled if "CONFIRMED_MODEL" in r.get("interpretation", [])),
            "signal75_failed_runs": sum(1 for r in settled if "UNDERPERFORMED" in r.get("interpretation", [])),
            "selection_type_counts": {t: sum(1 for r in recs if r.get("selection_type") == t) for t in sorted(set(r.get("selection_type") for r in recs))},
        }

    os.makedirs(INTEL_DIR, exist_ok=True)
    with open(HORSE_PROFILES_FILE, "w") as f:
        json.dump(profiles, f, indent=2, sort_keys=True)
    return profiles

def write_post_race_intelligence(picks, race_date):
    os.makedirs(INTEL_DIR, exist_ok=True)
    official_records = build_official_records(picks)
    market_lookup = get_market_lookup(race_date)

    known_keys = set()
    for rec in official_records:
        known_keys.add(normalise_name(rec.get("horse_name", "")) + "|" + (rec.get("time") or "") + "|" + (rec.get("course") or ""))

    extra_candidates = []
    for list_name in ("topRated", "topRatedFlat", "topRatedJumps"):
        for h in picks.get(list_name, []):
            name = h.get("name") or h.get("horse")
            if name:
                extra_candidates.append({"horse_name": name, "course": h.get("venue") or h.get("course", ""), "time": h.get("time", ""), "field_size": h.get("runners")})
    overlay_path = os.path.join(REPO_PATH, "data", f"consensus_overlay_{race_date}.json")
    if os.path.exists(overlay_path):
        try:
            with open(overlay_path) as f:
                overlay = json.load(f)
            for item in overlay.get("matched_to_betfair", []):
                name = item.get("betfair_name") or item.get("horse")
                if name:
                    extra_candidates.append({"horse_name": name, "course": item.get("course", ""), "time": item.get("time", "")})
        except Exception:
            pass

    position_map = get_position_map_for_candidates(extra_candidates, race_date)
    radar_records = build_radar_records(picks, position_map)
    for rec in radar_records:
        known_keys.add(normalise_name(rec.get("horse_name", "")) + "|" + (rec.get("time") or "") + "|" + (rec.get("course") or ""))
    shadow_records = load_shadow_records(race_date)
    for rec in shadow_records:
        known_keys.add(normalise_name(rec.get("horse_name", "")) + "|" + (rec.get("time") or "") + "|" + (rec.get("course") or ""))
    late_value_records = load_late_value_records(race_date)
    for rec in late_value_records:
        known_keys.add(normalise_name(rec.get("horse_name", "")) + "|" + (rec.get("time") or "") + "|" + (rec.get("course") or ""))
    tipster_records = load_tipster_alert_records(race_date, known_keys, position_map)

    records = official_records + radar_records + shadow_records + late_value_records + tipster_records
    for rec in records:
        market_info = market_lookup.get(rec.get("normalised_name", ""))
        if market_info:
            rec["market_id"] = rec.get("market_id") or market_info.get("market_id")
            rec["field_size"] = rec.get("field_size") or market_info.get("field_size")
            rec["selection_id"] = market_info.get("selection_id")
    payload = {
        "date": race_date,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "phase": "logging_only",
        "scoringImpact": "none",
        "recordCount": len(records),
        "counts": {
            "OFFICIAL_PICK": 0,
            "RADAR_PICK": 0,
            "SHADOW_CONSENSUS_PICK": 0,
            "SHADOW_LATE_VALUE_PICK": 0,
            "REJECTED_BY_GATE": 0,
            "TIPSTER_ONLY_ALERT": 0,
        },
        "notes": [
            "Phase 1 logging only: no scoring, pick generation, settlement or public display changes.",
            "REJECTED_BY_GATE records require a future rejected-candidate source file; unknown data is stored as null.",
        ],
        "records": records,
    }
    for rec in records:
        payload["counts"][rec["selection_type"]] = payload["counts"].get(rec["selection_type"], 0) + 1

    out_path = choose_intelligence_path(race_date)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    append_master_history(records)
    profiles = build_horse_profiles()
    log(f"✅ post-race intelligence written: {os.path.relpath(out_path, REPO_PATH)} ({len(records)} records, {len(profiles)} profiles)")
    return out_path

def push_to_github(race_date):
    archive_path = f"data/{race_date}.json"
    add_paths = ["picks.json", archive_path, "performance.json"]
    shadow_path = f"data/consensus_shadow_{race_date}.json"
    if os.path.exists(os.path.join(REPO_PATH, shadow_path)):
        add_paths.append(shadow_path)
    late_shadow_path = f"data/late_value_shadow_{race_date}.json"
    if os.path.exists(os.path.join(REPO_PATH, late_shadow_path)):
        add_paths.append(late_shadow_path)
    intel_rel = "data/horse_intelligence"
    if os.path.isdir(os.path.join(REPO_PATH, intel_rel)):
        add_paths.append(intel_rel)

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

        if mode == "topRatedOnly" or picks.get("noBetDay"):
            radar_count = settle_radar_cards(picks, picks.get("date", TODAY))
            if not radar_count:
                log("No official picks and no radar horses to check — skipping")
                return

            picks["results"]["complete"] = True
            picks["results"]["stakeEW"] = STAKE_EW
            picks["results"]["totalStake"] = TOTAL_PATENT_STAKE
            picks["results"]["proofBasis"] = "£1 each-way Patent"
            picks["results"]["updatedAt"] = datetime.now(timezone.utc).isoformat()
            picks["results"]["_note"] = "No official proof picks — radar/watchlist results stored on topRated/topRatedFlat/topRatedJumps"

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
            settle_late_value_shadow(race_date)
            write_post_race_intelligence(picks, race_date)
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
        radar_count = settle_radar_cards(picks, race_date)
        if radar_count:
            log(f"✅ Radar/watchlist positions updated: {radar_count}")

        flat_r, jumps_r, flat_races, jumps_races = [], [], [], []
        existing_results = picks.get("results", {})
        for entry in all_entries:
            race = entry["race"]
            h = race["horses"][0]
            name = normalise_name(h["name"])
            pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            existing_tab_results = existing_results.get(entry["tab"], [])
            existing_res = existing_tab_results[len(flat_r) if entry["tab"] == "flat" else len(jumps_r)] if len(existing_tab_results) > (len(flat_r) if entry["tab"] == "flat" else len(jumps_r)) else {}
            pos = pd.get("position", 0)
            ran = pd.get("ran", race.get("runners", 8))
            odds = h.get("odds", 2.0)
            result_str = determine_result(pos, pd.get("status", ""), ran)
            if result_str == "PENDING" and existing_res.get("result") and existing_res.get("result") != "PENDING":
                result_str = existing_res.get("result")
                pos = existing_res.get("position", pos)
                log(f"  Preserved existing result for {h['name']} — {result_str} (pos:{pos})")
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
            "stakeEW": STAKE_EW,
            "totalStake": TOTAL_PATENT_STAKE,
            "proofBasis": "£1 each-way Patent",
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
        settle_late_value_shadow(race_date)
        write_post_race_intelligence(picks, race_date)
        push_to_github(race_date)

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
