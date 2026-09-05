#!/usr/bin/env python3
"""
Signal 75 - Evening Results Updater
Uses Betfair API for results — reliable, free, instant.
Falls back to web search if Betfair API fails.
"""
import os, json, re, subprocess, sys, traceback, importlib.util, urllib.request, html
from datetime import date, datetime, timezone
import anthropic

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
REPO_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_BIN = sys.executable
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
RUNNERS_CACHE = os.path.join(REPO_PATH, "data/today_runners.json")
LOG_FILE = os.path.join(REPO_PATH, "data", "signal75-results.log")
BOOKMAKER_PRICE_OVERRIDES = os.path.join(REPO_PATH, "data", "bookmaker_price_overrides.json")
RESULTS_DEPLOY_STATE = os.path.join(REPO_PATH, "data", "results_deploy_state.json")
INTEL_DIR = os.path.join(REPO_PATH, "data", "horse_intelligence")
HORSE_PROFILES_FILE = os.path.join(INTEL_DIR, "horse_profiles.json")
HORSE_HISTORY_MASTER = os.path.join(INTEL_DIR, "horse_history_master.jsonl")
STAKE_EW = 1.00
TOTAL_PATENT_STAKE = 14.0
EARLY_REFRESH = os.environ.get("SIGNAL75_EARLY_REFRESH") == "1"
FORCE_RESULTS_PUBLISH = os.environ.get("SIGNAL75_FORCE_RESULTS_PUBLISH") == "1"
ALLOW_EARLY_RESULTS_PUBLISH = os.environ.get("SIGNAL75_ALLOW_EARLY_RESULTS_PUBLISH") == "1"
RESULTS_DEPLOY_MIN_SECONDS = int(os.environ.get("SIGNAL75_RESULTS_DEPLOY_MIN_SECONDS", "2700"))

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

def default_place_fraction(runners):
    runners = safe_int(runners) or 8
    return 0.20 if runners >= 16 else 0.25

def calculate_ew_return(odds, result, runners, place_frac=None):
    w, p, t = calculate_ew_return_exact(odds, result, runners, place_frac)
    return round(w, 2), round(p, 2), round(t, 2)

def calculate_ew_return_exact(odds, result, runners, place_frac=None):
    if place_frac is None:
        place_frac = default_place_fraction(runners)
    place_multiplier = 1 + odds * place_frac
    if result == "WON":
        w = (odds + 1) * STAKE_EW
        p = place_multiplier * STAKE_EW
    elif result == "PLACED":
        w, p = 0.0, place_multiplier * STAKE_EW
    elif result == "VOID":
        w, p = STAKE_EW, STAKE_EW
    else:
        w, p = 0.0, 0.0
    return w, p, w + p

def parse_fractional_odds(value):
    text = str(value or "").strip()
    if not text:
        return None
    if "/" in text:
        try:
            a, b = text.split("/", 1)
            return round(float(a.strip()) / float(b.strip()), 4)
        except Exception:
            return None
    try:
        return float(text)
    except Exception:
        return None

def parse_rule4_deduction(value):
    if value in (None, ""):
        return 0.0
    text = str(value).strip().replace("%", "")
    try:
        amount = float(text)
    except Exception:
        return 0.0
    if amount > 1:
        amount = amount / 100.0
    return max(0.0, min(amount, 1.0))

def apply_rule4_to_profit_odds(odds, deduction):
    return round(float(odds) * (1.0 - float(deduction or 0.0)), 4)

def parse_each_way_places(*values):
    for value in values:
        if value in (None, ""):
            continue
        try:
            places = int(float(value))
            if places > 0:
                return places
        except Exception:
            pass
        match = re.search(r"(?<!/)\b(\d+)\s*places?", str(value), re.I)
        if match:
            return int(match.group(1))
    return None

def load_bookmaker_price_overrides(race_date):
    if not os.path.exists(BOOKMAKER_PRICE_OVERRIDES):
        return {}
    try:
        with open(BOOKMAKER_PRICE_OVERRIDES) as f:
            payload = json.load(f)
    except Exception as e:
        log(f"  Bookmaker price override load failed: {e}")
        return {}

    rows = payload.get(race_date, []) if isinstance(payload, dict) else []
    lookup = {}
    for row in rows:
        key = (
            normalise_name(row.get("horse", "")),
            normalise_name(row.get("course", "")),
            str(row.get("time", "")).strip(),
        )
        if key[0]:
            lookup[key] = row
    return lookup

def verified_slip_return_from_overrides(lookup):
    for row in (lookup or {}).values():
        for key in ("verifiedSlipReturn", "slipReturn", "bookmakerReturn", "actualReturn"):
            if row.get(key) in (None, ""):
                continue
            try:
                return round(float(str(row.get(key)).replace("£", "").strip()), 2)
            except Exception:
                continue
    return None

def verified_proof_return_from_overrides(lookup, proof_stake=None):
    """Return the Signal 75 proof-normalised verified slip return.

    Bet365 screenshots sometimes show the user's real stake, which can differ
    from the standard Signal 75 proof stake. Use an explicit proof return when
    supplied; otherwise scale the verified slip return to the proof stake.
    """
    for row in (lookup or {}).values():
        explicit = row.get("verifiedProofReturn")
        if explicit not in (None, ""):
            try:
                return round(float(str(explicit).replace("£", "").strip()), 2)
            except Exception:
                pass

        actual_return = None
        for key in ("verifiedSlipReturn", "slipReturn", "bookmakerReturn", "actualReturn"):
            if row.get(key) in (None, ""):
                continue
            try:
                actual_return = float(str(row.get(key)).replace("£", "").strip())
                break
            except Exception:
                continue
        if actual_return is None:
            continue

        slip_stake = row.get("verifiedSlipStake") or row.get("slipStake") or row.get("actualStake")
        if slip_stake not in (None, "") and proof_stake not in (None, ""):
            try:
                stake = float(str(slip_stake).replace("£", "").strip())
                target = float(proof_stake)
                if stake > 0 and target > 0:
                    return round(actual_return * target / stake, 2)
            except Exception:
                pass
        return round(actual_return, 2)
    return None

def apply_verified_slip_return(bet_meta, verified_return):
    if verified_return is None:
        return bet_meta
    adjusted = dict(bet_meta)
    stake = float(adjusted.get("totalStake", 0.0) or 0.0)
    adjusted["calculatedReturnBeforeVerifiedSlip"] = round(float(adjusted.get("totalReturn", 0.0) or 0.0), 2)
    adjusted["verifiedSlipReturn"] = round(float(verified_return), 2)
    adjusted["totalReturn"] = round(float(verified_return), 2)
    adjusted["totalProfit"] = round(float(verified_return) - stake, 2)
    adjusted["return"] = adjusted["totalReturn"]
    adjusted["profit"] = adjusted["totalProfit"]
    section_bets = []
    for section in adjusted.get("sectionBets", []) or []:
        row = dict(section)
        if len(adjusted.get("sectionBets", []) or []) == 1:
            row["calculatedReturnBeforeVerifiedSlip"] = round(float(row.get("return", 0.0) or 0.0), 2)
            row["verifiedSlipReturn"] = adjusted["verifiedSlipReturn"]
            row["return"] = adjusted["totalReturn"]
            row["profit"] = adjusted["totalProfit"]
            row["rawReturn"] = adjusted["totalReturn"]
        section_bets.append(row)
    if section_bets:
        adjusted["sectionBets"] = section_bets
    return adjusted

def find_bookmaker_override(lookup, horse_name, course, race_time):
    exact = (
        normalise_name(horse_name),
        normalise_name(course),
        str(race_time or "").strip(),
    )
    if exact in lookup:
        return lookup[exact]
    loose = normalise_name(horse_name)
    matches = [row for key, row in lookup.items() if key[0] == loose]
    return matches[0] if len(matches) == 1 else None

def result_value_is_pending(value):
    return str(value or "").upper() in {"", "PENDING", "RESULT PENDING", "RACE RUN — RESULT TBC", "RACE RUN - RESULT TBC"}

def collect_public_result_values(picks):
    values = []
    results = picks.get("results", {}) if isinstance(picks.get("results"), dict) else {}
    for tab in ("flat", "jumps"):
        rows = results.get(tab, [])
        if isinstance(rows, list):
            values.extend(row.get("result") for row in rows if isinstance(row, dict))
    for section in ("flat", "jumps", "topRated", "topRatedFlat", "topRatedJumps"):
        items = picks.get(section, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            horses = item.get("horses")
            if isinstance(horses, list) and horses:
                h = horses[0]
                if isinstance(h, dict):
                    values.append(h.get("result") or h.get("known_result") or h.get("radarResult"))
            else:
                values.append(item.get("result") or item.get("known_result") or item.get("radarResult"))
    return [v for v in values if v is not None]

def results_ready_for_public_publish(picks):
    if FORCE_RESULTS_PUBLISH:
        return True, "forced by SIGNAL75_FORCE_RESULTS_PUBLISH"
    if EARLY_REFRESH and not ALLOW_EARLY_RESULTS_PUBLISH:
        return False, "early refresh mode keeps result updates local"
    results = picks.get("results", {}) if isinstance(picks.get("results"), dict) else {}
    if not results.get("complete"):
        return False, "official results are not complete yet"
    pending = [v for v in collect_public_result_values(picks) if result_value_is_pending(v)]
    if pending:
        return False, f"{len(pending)} public result value(s) still pending"
    return True, "results complete"

def deploy_throttle_allows():
    if FORCE_RESULTS_PUBLISH:
        return True, "forced"
    try:
        with open(RESULTS_DEPLOY_STATE) as f:
            state = json.load(f)
    except Exception:
        state = {}
    last = state.get("last_publish_utc")
    if not last:
        return True, "no previous result deploy"
    try:
        last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
    except Exception:
        return True, "previous deploy time unreadable"
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
    if elapsed < RESULTS_DEPLOY_MIN_SECONDS:
        mins = int((RESULTS_DEPLOY_MIN_SECONDS - elapsed) // 60) + 1
        return False, f"last result deploy was too recent; wait about {mins} minute(s)"
    return True, "deploy window clear"

def mark_results_deployed(race_date):
    os.makedirs(os.path.dirname(RESULTS_DEPLOY_STATE), exist_ok=True)
    payload = {
        "last_publish_utc": datetime.now(timezone.utc).isoformat(),
        "last_race_date": race_date,
        "min_seconds": RESULTS_DEPLOY_MIN_SECONDS,
        "note": "Used to avoid repeated GitHub Pages result deploys while races are still settling."
    }
    with open(RESULTS_DEPLOY_STATE, "w") as f:
        json.dump(payload, f, indent=2)

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
    if not results:
        return 0.0, 0.0

    picks_data = [
        {
            "win": r.get("winReturnExact", r.get("winReturn", 0)),
            "place": r.get("placeReturnExact", r.get("placeReturn", 0)),
        }
        for r in results[:3]
    ]
    if len(picks_data) == 1:
        total = round(picks_data[0]["win"] + picks_data[0]["place"], 2)
        return total, round(total - 2 * STAKE_EW, 2)
    if len(picks_data) == 2:
        h1, h2 = picks_data
        singles = sum(h["win"] + h["place"] for h in picks_data)
        dw = (h1["win"] * h2["win"]) / STAKE_EW if h1["win"] and h2["win"] else 0
        dp = (h1["place"] * h2["place"]) / STAKE_EW if h1["place"] and h2["place"] else 0
        total = round(singles + dw + dp, 2)
        return total, round(total - 6 * STAKE_EW, 2)

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

def official_bet_meta(selection_count):
    if selection_count >= 3:
        return {"betType": "PATENT", "betLabel": "£1 each-way Patent", "betLines": 14, "totalStake": 14.0}
    if selection_count == 2:
        return {"betType": "DOUBLE", "betLabel": "Each-way Double", "betLines": 6, "totalStake": 6.0}
    if selection_count == 1:
        return {"betType": "SINGLE", "betLabel": "Each-way Single", "betLines": 2, "totalStake": 2.0}
    return {"betType": "NO_BET", "betLabel": "No bet", "betLines": 0, "totalStake": 0.0}

def section_bet_from_returns(results):
    results = results or []
    meta = official_bet_meta(len(results))
    picks_data = [
        {
            "win": r.get("winReturnExact", r.get("winReturn", 0)),
            "place": r.get("placeReturnExact", r.get("placeReturn", 0)),
        }
        for r in results[:3]
    ]
    if not picks_data:
        total = 0.0
    elif len(picks_data) == 1:
        total = picks_data[0]["win"] + picks_data[0]["place"]
    elif len(picks_data) == 2:
        h1, h2 = picks_data
        total = sum(h["win"] + h["place"] for h in picks_data)
        total += (h1["win"] * h2["win"]) / STAKE_EW if h1["win"] and h2["win"] else 0
        total += (h1["place"] * h2["place"]) / STAKE_EW if h1["place"] and h2["place"] else 0
    else:
        total, _ = calculate_patent_from_returns(results[:3])
    total = round(total, 2)
    return {**meta, "rawStake": meta["totalStake"], "rawReturn": total, "return": total, "profit": round(total - meta["totalStake"], 2)}

def sectioned_bet_summary(flat_results, jumps_results):
    def section_name(bet):
        return "Flat" if bet["section"] == "flat" else "Jumps"

    def section_count(bet):
        return len(flat_results if bet["section"] == "flat" else jumps_results)

    active = []
    if flat_results:
        active.append({"section": "flat", **section_bet_from_returns(flat_results)})
    if jumps_results:
        active.append({"section": "jumps", **section_bet_from_returns(jumps_results)})
    if not active:
        return {
            "betType": "NO_BET", "betLabel": "No bet", "betLines": 0, "totalStake": 0.0,
            "totalReturn": 0.0, "totalProfit": 0.0, "sectionBets": []
        }
    raw_total_stake = round(sum(b["rawStake"] for b in active), 2)
    proof_scale = (TOTAL_PATENT_STAKE / raw_total_stake) if raw_total_stake > 0 else 0
    for bet in active:
        bet["totalStake"] = round(bet["rawStake"] * proof_scale, 2)
        bet["return"] = round(bet["rawReturn"] * proof_scale, 2)
        bet["profit"] = round(bet["return"] - bet["totalStake"], 2)
    total_stake = round(sum(b["totalStake"] for b in active), 2)
    total_return = round(sum(b["return"] for b in active), 2)
    total_lines = sum(b["betLines"] for b in active)
    if len(active) == 1:
        label = active[0]["betLabel"]
        bet_type = active[0]["betType"]
    else:
        label = " + ".join(section_name(b) + " " + b["betLabel"].replace("£1 each-way ", "") for b in active)
        bet_type = "SPLIT_SECTION_BETS"
    summary_parts = []
    for bet in active:
        count = section_count(bet)
        pick_word = "pick" if count == 1 else "picks"
        summary_parts.append(
            f"{section_name(bet)}: {count} {pick_word} · £{bet['totalStake']:.0f} stake · {bet['betLines']} lines"
        )
    summary = " + ".join(summary_parts)
    return {
        "betType": bet_type,
        "betLabel": label,
        "betLines": total_lines,
        "totalStake": total_stake,
        "totalReturn": total_return,
        "totalProfit": round(total_return - total_stake, 2),
        "summary": summary,
        "sectionBets": active,
    }

def determine_result(position, status, runners, places_paid=None):
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
    paid_places = safe_int(places_paid) or 0
    if paid_places > 0:
        return "PLACED" if pos <= paid_places else "LOST"
    if runners < 8 and pos == 2: return "PLACED"
    if 8 <= runners <= 11 and pos <= 3: return "PLACED"
    if runners >= 12 and pos <= 3: return "PLACED"
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
    slug = slug.replace("royal ascot", "ascot")
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

        rows = re.split(r'<li class="(?:results-table-row|results-row)"', text)
        course_positions = {}
        for row in rows[1:]:
            name_match = re.search(r'class="runner-title"[^>]*>\s*([^<]+?)\s*</a>', row, re.I | re.S)
            if not name_match:
                name_match = re.search(r'class="inner-result-content position-name"[^>]*>\s*([^<]+?)\s*</span>', row, re.I | re.S)
            if not name_match:
                continue
            name = html.unescape(re.sub(r"\s+", " ", name_match.group(1))).strip()
            pos_match = re.search(r'class="number position"[^>]*>(.*?)</span>\s*</div>', row, re.I | re.S)
            if not pos_match:
                pos_match = re.search(r'class="inner-result-content place-content"[^>]*>\s*([^<]+?)\s*</span>', row, re.I | re.S)
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
    from betfair_client import get_client
    return get_client()

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
    places_paid = parse_each_way_places(
        position_data.get("placesPaid"),
        position_data.get("placePlaces"),
        position_data.get("eachWayPlaces"),
        position_data.get("ewPlaces"),
        position_data.get("eachWayTerms"),
        candidate.get("placesPaid"),
        candidate.get("placePlaces"),
        candidate.get("eachWayPlaces"),
        candidate.get("ewPlaces"),
        candidate.get("eachWayTerms"),
    )
    result = determine_result(pos, status, runners, places_paid)
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

def race_time_has_passed(candidate, race_date):
    race_time = str(candidate.get("time") or "").strip()
    if not re.match(r"^\d{1,2}:\d{2}$", race_time):
        return True
    try:
        race_dt = datetime.fromisoformat(f"{race_date}T{race_time}:00")
        return datetime.now() >= race_dt
    except Exception:
        return True

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
            if result == "PENDING" and not race_time_has_passed(h, race_date):
                h["radarResult"] = "Result pending"
            else:
                h["radarResult"] = public_result_text(result, pos)
            h["radarSettled"] = result not in ("", "PENDING")
            updated += 1
            log(f"  Radar {name} — {h['radarResult']}")

    return updated

def settle_official_cards_display_only(picks, race_date):
    """
    Settle visible official pick cards on non-proof/topRatedOnly days.
    This updates card result/position for the public display, but does not turn
    the day into an official proof day or alter proof maths.
    """
    candidates, entries = [], []
    for tab in ("flat", "jumps"):
        for race in picks.get(tab, []) or []:
            horses = race.get("horses") or []
            if not horses:
                continue
            horse = horses[0]
            current = str(horse.get("result") or "").upper()
            if current in {"WON", "PLACED", "LOST", "VOID", "NR"}:
                continue
            candidates.append({
                "name": horse.get("name"),
                "course": race.get("course"),
                "time": race.get("time"),
                "runners": race.get("runners", 8),
            })
            entries.append((tab, race, horse))

    if not candidates:
        return 0

    raw = get_positions(candidates, race_date)
    positions = {normalise_name(p.get("name", "")): p for p in raw.get("positions", [])}
    updated = 0
    display_results = {"flat": [], "jumps": []}

    for tab, race, horse in entries:
        pd = positions.get(normalise_name(horse.get("name", "")), {})
        result, pos, runners = result_from_position_data(
            horse,
            pd,
        ) if pd else ("PENDING", safe_int(horse.get("position")) or 0, safe_int(race.get("runners")) or None)
        if result in ("", "PENDING"):
            continue
        odds = horse.get("odds", 2.0)
        win_return, place_return, total_return = calculate_ew_return(
            odds,
            result,
            runners or race.get("runners", 8),
        )
        horse["result"] = result
        horse["position"] = pos
        display_results[tab].append({
            "position": pos,
            "result": result,
            "winReturn": win_return,
            "placeReturn": place_return,
            "totalReturn": total_return,
        })
        updated += 1
        log(f"  Official display {horse.get('name')} — {result} (pos:{pos})")

    results = picks.setdefault("results", {})
    for tab in ("flat", "jumps"):
        if display_results[tab]:
            results[tab] = display_results[tab]
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

def push_to_github(race_date, picks):
    ready, ready_reason = results_ready_for_public_publish(picks)
    if not ready:
        log(f"GitHub publish skipped: {ready_reason}. Local files were still updated.")
        return False
    allowed, throttle_reason = deploy_throttle_allows()
    if not allowed:
        log(f"GitHub publish skipped: {throttle_reason}. Local files were still updated.")
        return False

    publisher = os.path.join(REPO_PATH, "scripts", "publish-live-files.py")
    command = [
        PYTHON_BIN,
        publisher,
        "--kind",
        "results",
        "--date",
        race_date,
        "--message",
        f"Results and performance update {race_date}",
    ]
    result = subprocess.run(command, cwd=REPO_PATH, capture_output=True, text=True)
    if result.stdout.strip():
        log(result.stdout.strip())
    ok = result.returncode == 0
    if not ok:
        log(f"Warning: {result.stderr.strip()}")
    if ok:
        mark_results_deployed(race_date)
        log("Published to GitHub from a clean worktree")
    else:
        log("⚠️ Clean GitHub publish reported warnings — wrapper will retry final publish")
    return ok

def main():
    log(f"\n{'='*50}\nSignal 75 Results - {TODAY_DISPLAY}\n{'='*50}")
    if EARLY_REFRESH:
        log("Early refresh mode: public results can update, post-race intelligence waits for evening settlement")
    try:
        with open(PICKS_FILE) as f:
            picks = json.load(f)
        mode = picks.get("mode", "")
        official_pick_count = sum(
            1
            for tab in ("flat", "jumps")
            for race in picks.get(tab, [])
            if race.get("horses")
        )

        if picks.get("noBetDay") or (mode == "topRatedOnly" and official_pick_count == 0):
            race_date = picks.get("date", TODAY)
            official_display_count = settle_official_cards_display_only(picks, race_date)
            if official_display_count:
                log(f"✅ Official display positions updated: {official_display_count}")
            radar_count = settle_radar_cards(picks, picks.get("date", TODAY))
            if not radar_count and not official_display_count:
                log("No official picks and no radar horses to check — skipping")
                return

            picks["results"]["complete"] = True
            picks["results"]["stakeEW"] = STAKE_EW
            picks["results"]["totalStake"] = 0.0
            picks["results"]["betType"] = "NO_BET"
            picks["results"]["betLines"] = 0
            picks["results"]["proofBasis"] = "No official Signal 75 bet"
            picks["results"]["updatedAt"] = datetime.now(timezone.utc).isoformat()
            picks["results"]["_note"] = "No official Signal 75 bet — learning horses stored internally on topRated/topRatedFlat/topRatedJumps"

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
            if EARLY_REFRESH:
                log("Early refresh mode: skipped post-race intelligence write")
            else:
                write_post_race_intelligence(picks, race_date)
            pushed = push_to_github(race_date, picks)
            log("Radar results saved, archived" + (" and pushed" if pushed else " locally"))
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
        locked_flat_r, locked_jumps_r = [], []
        existing_results = picks.get("results", {})
        bookmaker_overrides = load_bookmaker_price_overrides(race_date)
        bookmaker_used = []
        for entry in all_entries:
            race = entry["race"]
            h = race["horses"][0]
            name = normalise_name(h["name"])
            pd = positions.get(name, {"position": 0, "ran": race.get("runners", 8)})
            existing_tab_results = existing_results.get(entry["tab"], [])
            existing_res = existing_tab_results[len(flat_r) if entry["tab"] == "flat" else len(jumps_r)] if len(existing_tab_results) > (len(flat_r) if entry["tab"] == "flat" else len(jumps_r)) else {}
            pos = pd.get("position", 0)
            ran = pd.get("ran", race.get("runners", 8))
            locked_odds = float(h.get("odds", 2.0) or 2.0)
            odds = locked_odds
            place_frac = None
            places_paid = None
            override = find_bookmaker_override(bookmaker_overrides, h.get("name"), race.get("course"), race.get("time"))
            if override:
                override_odds = parse_fractional_odds(override.get("odds") or override.get("price"))
                rule4_deduction = parse_rule4_deduction(
                    override.get("rule4Deduction")
                    if override.get("rule4Deduction") is not None
                    else override.get("rule4")
                    if override.get("rule4") is not None
                    else override.get("rule4Percent")
                )
                try:
                    override_place = float(override.get("placeFraction")) if override.get("placeFraction") is not None else None
                except Exception:
                    override_place = None
                places_paid = parse_each_way_places(
                    override.get("placesPaid"),
                    override.get("placePlaces"),
                    override.get("eachWayPlaces"),
                    override.get("ewPlaces"),
                    override.get("eachWayTerms"),
                )
                if override_odds:
                    odds = apply_rule4_to_profit_odds(override_odds, rule4_deduction)
                    h.setdefault("lockedSignalPrice", locked_odds)
                    h["settlementOdds"] = odds
                    h["settlementOddsSource"] = override.get("source", "bookmaker_override")
                    h["bookmakerOddsText"] = str(override.get("odds") or override.get("price") or "")
                    h["bookmaker"] = override.get("bookmaker", "")
                    if rule4_deduction:
                        h["settlementOddsBeforeRule4"] = override_odds
                        h["rule4Deduction"] = rule4_deduction
                    if override_place:
                        place_frac = override_place
                        h["eachWayTerms"] = override.get("eachWayTerms") or f"1/{round(1 / override_place)}"
                    if places_paid:
                        h["placesPaid"] = places_paid
                    bookmaker_used.append(h.get("name"))
            result_str = determine_result(pos, pd.get("status", ""), ran, places_paid)
            if result_str == "PENDING" and existing_res.get("result") and existing_res.get("result") != "PENDING":
                result_str = existing_res.get("result")
                pos = existing_res.get("position", pos)
                log(f"  Preserved existing result for {h['name']} — {result_str} (pos:{pos})")
            locked_w, locked_p, locked_t = calculate_ew_return(locked_odds, result_str, ran)
            w_exact, p_exact, t_exact = calculate_ew_return_exact(odds, result_str, ran, place_frac)
            w, p, t = round(w_exact, 2), round(p_exact, 2), round(t_exact, 2)
            ro = {
                "name": h.get("name", ""),
                "tipsters": safe_int(h.get("tipsters")) or safe_int((h.get("consensus") or {}).get("source_count")),
                "race_type": entry["tab"],
                "position": pos,
                "result": result_str,
                "winReturn": w,
                "placeReturn": p,
                "totalReturn": t,
                "winReturnExact": w_exact,
                "placeReturnExact": p_exact,
                "totalReturnExact": t_exact,
                "odds": odds,
                "settlementOdds": odds,
                "settlementOddsSource": h.get("settlementOddsSource", h.get("oddsSource", "")),
                "lockedSignalPrice": locked_odds,
                "lockedWinReturn": locked_w,
                "lockedPlaceReturn": locked_p,
                "lockedTotalReturn": locked_t
            }
            if h.get("bookmakerOddsText"):
                ro["bookmakerOddsText"] = h.get("bookmakerOddsText")
                ro["bookmaker"] = h.get("bookmaker", "")
            if h.get("settlementOddsBeforeRule4") is not None:
                ro["settlementOddsBeforeRule4"] = h.get("settlementOddsBeforeRule4")
                ro["rule4Deduction"] = h.get("rule4Deduction", 0.0)
            if place_frac is not None:
                ro["placeFraction"] = place_frac
                ro["eachWayTerms"] = h.get("eachWayTerms", "")
            if places_paid:
                ro["placesPaid"] = places_paid
            h["result"] = result_str
            h["position"] = pos
            if override and h.get("bookmakerOddsText"):
                log(f"  {h['name']} — {result_str} (pos:{pos}) settled at {h['bookmakerOddsText']} via {h.get('settlementOddsSource')}")
            else:
                log(f"  {h['name']} — {result_str} (pos:{pos})")
            if entry["tab"] == "flat":
                flat_r.append(ro); flat_races.append(race)
                locked_flat_r.append({"position": pos, "result": result_str, "winReturn": locked_w, "placeReturn": locked_p, "totalReturn": locked_t})
            else:
                jumps_r.append(ro); jumps_races.append(race)
                locked_jumps_r.append({"position": pos, "result": result_str, "winReturn": locked_w, "placeReturn": locked_p, "totalReturn": locked_t})

        locked_official_results = locked_flat_r + locked_jumps_r
        bet_meta = sectioned_bet_summary(flat_r, jumps_r)
        verified_slip_return = verified_proof_return_from_overrides(
            bookmaker_overrides,
            bet_meta.get("totalStake"),
        )
        bet_meta = apply_verified_slip_return(bet_meta, verified_slip_return)
        locked_bet_meta = sectioned_bet_summary(locked_flat_r, locked_jumps_r)
        patent_return = bet_meta["totalReturn"]
        patent_profit = bet_meta["totalProfit"]
        locked_patent_return = locked_bet_meta["totalReturn"]
        locked_patent_profit = locked_bet_meta["totalProfit"]
        complete = all(r["result"] not in ["", "PENDING"] for r in flat_r + jumps_r)

        picks["results"] = {
            "flat": flat_r, "jumps": jumps_r,
            "patentReturn": patent_return, "patentProfit": patent_profit,
            "totalReturn": patent_return,
            "totalProfit": patent_profit,
            "profit": round(float(patent_return or 0.0) - float(bet_meta.get("totalStake", 0.0) or 0.0), 2),
            "lockedPriceProof": {
                "patentReturn": locked_patent_return,
                "patentProfit": locked_patent_profit,
                "totalReturn": locked_patent_return,
                "totalProfit": locked_patent_profit,
                "basis": "Signal 75 locked pick-time prices",
                "betType": locked_bet_meta["betType"],
                "betLabel": locked_bet_meta["betLabel"],
                "betSummary": locked_bet_meta,
            },
            "bookmakerPriceOverridesUsed": bookmaker_used,
            "verifiedSlipReturn": verified_slip_return,
            "stakeEW": STAKE_EW,
            "totalStake": bet_meta["totalStake"],
            "betType": bet_meta["betType"],
            "betLines": bet_meta["betLines"],
            "proofBasis": bet_meta["betLabel"],
            "betSummary": bet_meta,
            "settlementBasis": "bookmaker/SP override where verified, otherwise Signal 75 locked pick-time price",
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

        log(f"Official result: £{patent_return} | Profit: £{patent_profit} | Complete: {complete}")

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
        if EARLY_REFRESH:
            log("Early refresh mode: skipped post-race intelligence write")
        else:
            write_post_race_intelligence(picks, race_date)
        try:
            challenger_script = os.path.join(REPO_PATH, "scripts", "settle-challenger-lab.py")
            subprocess.run([PYTHON_BIN, challenger_script, "--date", race_date], check=False, timeout=60)
            log("✅ Challenger Lab settlement checked")
        except Exception as cle:
            log(f"⚠️ Challenger Lab settlement skipped: {cle}")
        push_to_github(race_date, picks)

    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        log(traceback.format_exc())

if __name__ == "__main__":
    main()
