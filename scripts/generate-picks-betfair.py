#!/usr/bin/env python3
"""
generate-picks-betfair.py — Signal 75
Betfair API picks generator — exact picks.json format match.
"""
import json, os, sys, subprocess, re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

SCRIPTS = '/Users/johnhowlett/Signal75/scripts'
sys.path.insert(0, SCRIPTS)

TEST_OUTPUT   = '/Users/johnhowlett/Signal75/data/picks_test.json'
PICKS_JSON    = '/Users/johnhowlett/Signal75/picks.json'
RUNNERS_CACHE = '/Users/johnhowlett/Signal75/data/today_runners.json'
CONSENSUS_SHADOW = '/Users/johnhowlett/Signal75/data/consensus_shadow_{}.json'
TEST_MODE     = False

# ── FUTURE-PROOFING CONSTANTS ──────────────────────────────────────────────
ENGINE_VERSION = "v1"          # Bump to "v2" when scoring_engine_v2 goes live
DATA_SOURCE    = "betfair_api" # Change if paid API added
ODDS_SOURCE    = "betfair_bsp" # Change if bookmaker odds used
# ──────────────────────────────────────────────────────────────────────────

COURSE_WEATHER_LOCATIONS = {
    "Aintree": (53.4769, -2.9439),
    "Ascot": (51.4115, -0.6748),
    "Ayr": (55.4586, -4.6138),
    "Bath": (51.3810, -2.4090),
    "Beverley": (53.8428, -0.4256),
    "Brighton": (50.8370, -0.1190),
    "Carlisle": (54.8950, -2.9380),
    "Cartmel": (54.2000, -2.9500),
    "Catterick": (54.3750, -1.6350),
    "Chelmsford City": (51.8469, 0.4800),
    "Cheltenham": (51.9190, -2.0685),
    "Chepstow": (51.6400, -2.6900),
    "Chester": (53.1850, -2.8950),
    "Doncaster": (53.5200, -1.1100),
    "Epsom": (51.3098, -0.2569),
    "Epsom Downs": (51.3098, -0.2569),
    "Exeter": (50.6410, -3.4790),
    "Ffos Las": (51.7220, -4.2420),
    "Goodwood": (50.8940, -0.7370),
    "Hamilton": (55.7810, -4.0400),
    "Haydock": (53.4820, -2.6260),
    "Hexham": (54.9580, -2.1020),
    "Kempton": (51.4210, -0.4050),
    "Leicester": (52.6070, -1.0750),
    "Lingfield": (51.1690, -0.0070),
    "Lingfield Park": (51.1690, -0.0070),
    "Market Rasen": (53.3830, -0.3380),
    "Musselburgh": (55.9410, -3.0500),
    "Newbury": (51.3970, -1.3070),
    "Newcastle": (55.0360, -1.6160),
    "Newmarket": (52.2400, 0.3740),
    "Newton Abbot": (50.5300, -3.5950),
    "Nottingham": (52.9490, -1.0860),
    "Perth": (56.4070, -3.4330),
    "Plumpton": (50.9320, -0.0600),
    "Pontefract": (53.6980, -1.3060),
    "Redcar": (54.6070, -1.0520),
    "Ripon": (54.1350, -1.5210),
    "Salisbury": (51.0710, -1.8060),
    "Sandown": (51.3740, -0.3610),
    "Southwell": (53.0710, -0.9080),
    "Stratford": (52.1920, -1.7090),
    "Taunton": (50.9940, -3.0830),
    "Thirsk": (54.2320, -1.3430),
    "Uttoxeter": (52.8980, -1.8640),
    "Warwick": (52.2770, -1.5850),
    "Wetherby": (53.9290, -1.3670),
    "Windsor": (51.4830, -0.6110),
    "Wolverhampton": (52.5970, -2.1290),
    "Worcester": (52.1960, -2.2350),
    "Yarmouth": (52.6170, 1.7280),
    "York": (53.9390, -1.0970),
}

def get_today():
    return datetime.now().strftime('%Y-%m-%d')

def format_time_uk(race_time_str):
    try:
        dt = datetime.fromisoformat(race_time_str.replace('Z', '+00:00'))
        uk = dt + timedelta(hours=1)
        return uk.strftime('%H:%M')
    except:
        return '00:00'

def get_distance(race_name):
    m = re.search(r'(\d+m\d*f?|\d+f)', race_name.lower())
    return m.group(1) if m else 'unknown'

def clean_course_name(value):
    text = re.sub(r'\s+\d+(st|nd|rd|th)?\s+\w+$', '', str(value or ''), flags=re.I).strip()
    return text

def weather_code_text(code):
    code = int(code or 0)
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow/sleet"
    if code in (95, 96, 99):
        return "storm"
    return "clear/unknown"

def weather_risk_level(current_mm, hourly_mm, probability, code):
    rain_code = weather_code_text(code) in {"drizzle", "rain", "snow/sleet", "storm"}
    if current_mm >= 1.5 or hourly_mm >= 4.0 or probability >= 80 or weather_code_text(code) == "storm":
        return "high"
    if current_mm >= 0.4 or hourly_mm >= 1.5 or probability >= 55 or rain_code:
        return "medium"
    if current_mm > 0 or hourly_mm > 0.4 or probability >= 35:
        return "low"
    return "none"

def fetch_course_weather(course):
    course = clean_course_name(course)
    coords = COURSE_WEATHER_LOCATIONS.get(course)
    if not coords:
        return {
            "course": course,
            "status": "unknown",
            "risk": "unknown",
            "message": "Weather check unavailable for this course.",
            "scoringImpact": "none",
        }

    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "precipitation,rain,showers,weather_code",
        "hourly": "precipitation_probability,precipitation,rain,showers",
        "forecast_days": 1,
        "timezone": "Europe/London",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {
            "course": course,
            "status": "failed",
            "risk": "unknown",
            "message": f"Weather check failed safely: {type(e).__name__}.",
            "scoringImpact": "none",
        }

    current = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    current_mm = float(current.get("precipitation") or current.get("rain") or current.get("showers") or 0)
    code = current.get("weather_code") or 0
    hourly_precip = hourly.get("precipitation") or []
    hourly_prob = hourly.get("precipitation_probability") or []
    next_3h_mm = sum(float(x or 0) for x in hourly_precip[:3])
    max_probability = max([int(x or 0) for x in hourly_prob[:3]] or [0])
    risk = weather_risk_level(current_mm, next_3h_mm, max_probability, code)
    if risk == "high":
        message = "Heavy rain risk today. Treat confidence with caution."
    elif risk == "medium":
        message = "Rain risk today. Conditions may change."
    elif risk == "low":
        message = "Some rain possible. Watch conditions."
    else:
        message = "No major rain risk detected."

    return {
        "course": course,
        "status": "ok",
        "risk": risk,
        "message": message,
        "condition": weather_code_text(code),
        "currentPrecipMm": round(current_mm, 2),
        "next3hPrecipMm": round(next_3h_mm, 2),
        "next3hPrecipProbability": max_probability,
        "source": "open-meteo",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "scoringImpact": "none",
    }

def build_weather_checks(races):
    courses = sorted({clean_course_name(r.get("venue")) for r in races if r.get("venue")})
    checks = {}
    for course in courses:
        checks[course] = fetch_course_weather(course)
    return checks

def get_anthropic_key():
    env_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if env_key:
        return env_key
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', 'signal75', '-s', 'anthropic-api-key', '-w'],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def save_runners_cache(races):
    """Save full runner list so evening results script can use Betfair API."""
    os.makedirs(os.path.dirname(RUNNERS_CACHE), exist_ok=True)
    cache = {
        'date': get_today(),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'races': races
    }
    with open(RUNNERS_CACHE, 'w') as f:
        json.dump(cache, f, indent=2)
    total = sum(len(r.get('runners', [])) for r in races)
    print(f"  Saved {total} runners across {len(races)} races to today_runners.json")

def generate_explanation(pick):
    try:
        import anthropic
        key = get_anthropic_key()
        client = anthropic.Anthropic(api_key=key)
        history = pick.get('history')
        hist_text = ''
        if history:
            hist_text = (f"{history['runs']} runs, {history['wins']} wins "
                        f"({history['win_rate']}% win rate). ")
        prompt = (
            f"Write one confident sentence (max 20 words) explaining why "
            f"{pick['name']} is selected for Signal 75 today. "
            f"Race: {pick['race_name']} at {pick['venue']}. "
            f"Form: {pick['form']}. Jockey: {pick['jockey']}. "
            f"Record: {hist_text}Be factual. No hype."
        )
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=60,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"  Explanation fallback: {e}")
        history = pick.get('history')
        if history:
            return (f"Consistent performer with {history['win_rate']}% win rate "
                   f"from {history['runs']} career runs.")
        return f"Selected by Signal 75 scoring engine. Form: {pick['form']}."

def build_race_entry(pick, explanation):
    consensus = pick.get('consensus', {})
    weather = pick.get('weatherRisk') or {}
    tipster_count = _consensus_count(pick)
    overlay_pts = consensus.get('overlay_points', 0)
    ts_score = min(100, max(0, 50 + (overlay_pts * 10)))
    horse = {
        'num': 0,
        'name': pick['name'].upper(),
        'jockey': pick['jockey'],
        'trainer': pick['trainer'],
        'odds': round(pick['bsp'], 2) if pick['bsp'] else 0,
        'prevOdds': round(pick['bsp'], 2) if pick['bsp'] else 0,
        'tipsters': tipster_count,
        'formStr': pick['form'],
        'goingWins': 0,
        'goingRuns': 0,
        'courseWins': 0,
        'distanceWins': 0,
        'trainerInForm': False,
        'rpr': 0,
        'confidence': 'high' if pick['score'] >= 82 else 'medium',
        'reason': explanation,
        'signal_score': int(pick['score']),
        'badge': pick['badge'] or 'Strong',
        'result': '',
        'position': 0,
        'consensus': {
            'source_count': tipster_count,
            'tip_count': consensus.get('tip_count', 0),
            'consensus_count': tipster_count,
            'overlay_points': overlay_pts,
            'consensus_level': consensus.get('consensus_level', 'none'),
            'warning': consensus.get('warning', None),
            'sources': consensus.get('sources', []),
            'tipsters': consensus.get('tipsters', []),
        },
        'bd': {
            'os': min(100, int(pick['score'])),
            'ts': int(ts_score),
            'fs': min(100, int(pick['score'])),
            'fm': min(100, int(pick['score']))
        },
        'engineVersion': ENGINE_VERSION,
        'dataSource': DATA_SOURCE,
        'oddsSource': ODDS_SOURCE,
        'weatherRisk': weather,
        'formWarning': pick.get('form_warning'),
        'formPenalty': pick.get('form_penalty_mult', 1.0),
    }
    race = {
        'time': format_time_uk(pick['race_time']),
        'course': pick['venue'],
        'type': pick['race_type'].lower(),
        'distance': get_distance(pick['race_name']),
        'going': pick.get('going') or ('Weather caution' if weather.get('risk') in ('medium', 'high') else 'Not confirmed'),
        'runners': pick['field_size'],
        'weatherRisk': weather,
        'horses': [horse]
    }
    return race

def build_radar_card(r):
    consensus = r.get('consensus') or {}
    weather = r.get('weatherRisk') or {}
    tipster_count = _consensus_count(r)
    score = int(r['score'])
    odds_text = f"{r['bsp']:.1f}" if r.get('bsp') else "N/A"
    return {
        'name': r['name'],
        'race': r['race_name'],
        'venue': r['venue'],
        'time': format_time_uk(r['race_time']),
        'signal_score': score,
        'odds': odds_text,
        'form': r['form'],
        'race_type': r['race_type'],
        'jockey': r.get('jockey') or 'Radar pick',
        'trainer': r.get('trainer') or '',
        'tipsters': tipster_count,
        'consensus': {
            'source_count': tipster_count,
            'tip_count': consensus.get('tip_count', 0),
            'consensus_count': tipster_count,
            'overlay_points': consensus.get('overlay_points', 0),
            'consensus_level': consensus.get('consensus_level', 'none'),
            'warning': consensus.get('warning', None),
            'sources': consensus.get('sources', []),
            'tipsters': consensus.get('tipsters', []),
        },
        'weatherRisk': weather,
        'formWarning': r.get('form_warning'),
        'formPenalty': r.get('form_penalty_mult', 1.0),
        'reason': f"Radar watchlist: Signal {score}, odds {odds_text}, form {r.get('form') or 'unknown'}.",
        'runners': r.get('field_size'),
        'bd': {
            'os': min(100, score),
            'ts': min(100, max(0, 50 + int(consensus.get('overlay_points', 0) or 0) * 10)),
            'fs': min(100, score),
            'fm': min(100, score),
        },
        'radarResult': '',
    }

def _consensus_count(runner):
    consensus = runner.get('consensus') or {}
    return int(
        consensus.get('consensus_count')
        or consensus.get('tip_count')
        or consensus.get('source_count')
        or 0
    )

def _official_candidate(runner):
    bsp = runner.get('bsp')
    field_size = runner.get('field_size', 0)
    return (
        runner.get('score', 0) >= 75 and
        runner.get('score', 0) >= 50 and
        bsp is not None and
        4.1 <= float(bsp) <= 6.0 and
        int(field_size or 0) >= 8 and
        not runner.get('form_risk') and
        int(runner.get('recency_form_penalty') or 0) < 12
    )

def _consensus_official_candidate(runner):
    """
    Consensus-led live gate.
    Professional tips create the shortlist, but Signal 75 still rejects weak
    model scores, cramped fields, and poor value/price zones.
    """
    bsp = runner.get('bsp')
    field_size = runner.get('field_size', 0)
    return (
        _consensus_count(runner) > 0 and
        runner.get('qualifies') is True and
        runner.get('score', 0) >= 70 and
        runner.get('score', 0) >= 50 and
        bsp is not None and
        2.75 <= float(bsp) <= 8.0 and
        int(field_size or 0) >= 8 and
        not runner.get('form_risk') and
        int(runner.get('recency_form_penalty') or 0) < 12
    )

def select_signal_first_official(scored):
    """
    14 June live rule: Signal 75 first, consensus as points overlay.
    Consensus points are part of the live score after the overlay is applied.
    No weak third pick is forced.
    """
    official_pool = sorted(
        [r for r in scored if _official_candidate(r)],
        key=lambda r: (
            r.get('score', 0),
            _consensus_count(r),
            r.get('bsp') or 99
        ),
        reverse=True
    )
    return _pick_three(official_pool), len(official_pool)

def _pick_three(candidates):
    picks, used_markets, used_names = [], set(), set()
    for runner in candidates:
        name_key = runner.get('name', '').lower()
        if runner.get('market_id') in used_markets or name_key in used_names:
            continue
        picks.append(runner)
        used_markets.add(runner.get('market_id'))
        used_names.add(name_key)
        if len(picks) >= 3:
            break
    return picks

def _radar_candidate(runner):
    bsp = runner.get('bsp')
    if bsp is None:
        return False
    return (
        runner.get('score', 0) >= 65 and
        2.1 <= float(bsp) <= 12.0
    )

def pick_radar_watchlist(scored, picked_names=None, limit=3):
    picked_names = picked_names or set()
    candidates = [
        r for r in scored
        if r.get('name') not in picked_names and _radar_candidate(r)
    ]
    tipped = sorted(
        [r for r in candidates if _consensus_count(r) > 0],
        key=lambda r: (_consensus_count(r), r.get('score', 0)),
        reverse=True
    )
    untipped = sorted(
        [r for r in candidates if _consensus_count(r) == 0],
        key=lambda r: r.get('score', 0),
        reverse=True
    )
    ranked = tipped + untipped
    picks = _pick_three(ranked)
    if len(picks) < limit:
        used_names = {p.get('name', '').lower() for p in picks}
        for runner in ranked:
            name_key = runner.get('name', '').lower()
            if name_key in used_names:
                continue
            picks.append(runner)
            used_names.add(name_key)
            if len(picks) >= limit:
                break
    return picks[:limit]

def select_tipster_first_official(scored):
    """
    Live rule: the strongest professional consensus creates the shortlist.
    If several horses have the same consensus count, Signal 75 score ranks them.
    We do not drop to weaker consensus tiers just to fill the Patent.
    """
    official_pool = [r for r in scored if _consensus_official_candidate(r)]
    if not official_pool:
        return [], 0, 0

    selected_tier = max(_consensus_count(r) for r in official_pool)
    tier_pool = [
        r for r in official_pool
        if _consensus_count(r) == selected_tier
    ]
    tier_pool = sorted(
        tier_pool,
        key=lambda r: (r.get('score', 0), r.get('qualifies') is True),
        reverse=True
    )

    return _pick_three(tier_pool), selected_tier, len(official_pool)

def _shadow_pick_entry(runner):
    consensus = runner.get('consensus') or {}
    return {
        'name': runner.get('name'),
        'course': runner.get('venue'),
        'time': format_time_uk(runner.get('race_time', '')),
        'race_type': runner.get('race_type'),
        'market_id': runner.get('market_id'),
        'bsp': runner.get('bsp'),
        'score': runner.get('score'),
        'source_count': consensus.get('source_count', 0),
        'tip_count': consensus.get('tip_count', 0),
        'consensus_count': _consensus_count(runner),
        'sources': consensus.get('sources', []),
        'tipsters': consensus.get('tipsters', []),
        'overlay_points': consensus.get('overlay_points', 0),
    }

def save_consensus_shadow(scored, official_picks, overlay_data):
    """
    Paper-test consensus gates without changing public picks.
    True historical consensus is not in the Betfair master file, so this must be
    evaluated live from today forward.
    """
    date_str = get_today()
    pool = [r for r in scored if _official_candidate(r)]
    consensus_pool = [r for r in scored if _consensus_official_candidate(r)]
    baseline = _pick_three(sorted(pool, key=lambda x: x.get('score', 0), reverse=True))
    tipster_first_shadow, tipster_first_tier, _ = select_tipster_first_official(scored)

    ranked = sorted(
        pool,
        key=lambda r: (
            r.get('score', 0) + min(4, _consensus_count(r) * 2),
            _consensus_count(r),
            r.get('score', 0)
        ),
        reverse=True
    )

    tipped_first = sorted(
        pool,
        key=lambda r: (_consensus_count(r) > 0, r.get('score', 0)),
        reverse=True
    )

    tipped_only = sorted(
        [r for r in pool if _consensus_count(r) > 0],
        key=lambda r: (r.get('score', 0), _consensus_count(r)),
        reverse=True
    )

    variants = {
        'baseline_live_rule': {
            'description': 'Previous value-band rule; no consensus gate.',
            'picks': [_shadow_pick_entry(r) for r in baseline],
        },
        'tipster_first_live_rule': {
            'description': f'Current live rule: strongest consensus tier only ({tipster_first_tier} source(s)), Signal 75 score breaks ties.' if tipster_first_tier else 'Current live rule: no tipped horses passed Signal 75 value filters.',
            'picks': [_shadow_pick_entry(r) for r in tipster_first_shadow],
        },
        'consensus_rank_v1': {
            'description': 'Soft rank boost: consensus sources nudge ranking but do not block picks.',
            'picks': [_shadow_pick_entry(r) for r in _pick_three(ranked)],
        },
        'consensus_prefer_tipped_v1': {
            'description': 'Prefer tipped horses first, then fill with normal value-band picks if needed.',
            'picks': [_shadow_pick_entry(r) for r in _pick_three(tipped_first)],
        },
        'consensus_strict_tipped_v1': {
            'description': 'Strict paper test: only horses with at least one consensus source.',
            'picks': [_shadow_pick_entry(r) for r in _pick_three(tipped_only)],
        },
    }

    signal_first_live, signal_first_count = select_signal_first_official(scored)

    variants = {
        'signal_first_consensus_overlay_v1': {
            'description': '14 June live rule: Signal 75 score first, exact consensus points as overlay, no hard tipster gate.',
            'picks': [_shadow_pick_entry(r) for r in signal_first_live],
        },
        **variants,
    }

    shadow = {
        'date': date_str,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'status': 'shadow_only_not_live',
        'message': 'Consensus variants for comparison. Public picks use Signal 75 first with consensus as points overlay.',
        'overlayStatus': overlay_data.get('status') if overlay_data else 'missing',
        'overlayMatched': overlay_data.get('total_matched', 0) if overlay_data else 0,
        'overlaySources': overlay_data.get('sources_successful', []) if overlay_data else [],
        'officialCandidateCount': len(pool),
        'consensusCandidateCount': len(consensus_pool),
        'signalFirstCandidateCount': signal_first_count,
        'variants': variants,
        'results': {},
    }

    path = CONSENSUS_SHADOW.format(date_str)
    with open(path, 'w') as f:
        json.dump(shadow, f, indent=2)
    print(f"  Consensus shadow saved: {path}")
    return shadow

def main():
    print("Signal 75 — Betfair picks generator")
    print(f"Date: {get_today()}")
    print()

    # Step 1 — Betfair
    print("Step 1: Betfair API...")
    from betfair_client import get_client, get_uk_win_markets, get_market_odds, extract_runners
    trading = get_client()
    markets = get_uk_win_markets(trading)
    print(f"  {len(markets)} UK WIN markets")
    if not markets:
        print("  No markets — exiting")
        sys.exit(1)

    market_ids = [m.market_id for m in markets]
    odds = get_market_odds(trading, market_ids)
    races = extract_runners(markets, odds)
    total_runners = sum(r['field_size'] for r in races)
    print(f"  {total_runners} runners across {len(races)} races")

    print("Step 1a: Live weather check...")
    weather_checks = build_weather_checks(races)
    for race in races:
        course = clean_course_name(race.get('venue'))
        race['weatherRisk'] = weather_checks.get(course, {
            'course': course,
            'status': 'unknown',
            'risk': 'unknown',
            'message': 'Weather check unavailable for this course.',
            'scoringImpact': 'none',
        })
    risky_courses = [
        course for course, check in weather_checks.items()
        if check.get('risk') in ('medium', 'high')
    ]
    if risky_courses:
        print(f"  Weather cautions: {', '.join(risky_courses)}")
    else:
        print("  No major weather cautions detected")

    # Step 1b — Save runner cache for evening results
    print("Step 1b: Saving runners cache...")
    save_runners_cache(races)

    # Step 2 — Match
    print("Step 2: Matching to database...")
    from runner_matcher import load_profiles, enrich_runners
    profiles = load_profiles()
    races = enrich_runners(races, profiles)

    # Step 3 — Score
    print("Step 3: Scoring...")
    from scoring_engine import load_roi_tables, score_all_runners, select_picks
    tables = load_roi_tables()
    scored = score_all_runners(races, tables)
    race_weather = {race.get('market_id'): race.get('weatherRisk') for race in races}
    for runner in scored:
        runner['weatherRisk'] = race_weather.get(runner.get('market_id'), {})
    print(f"  {len(scored)} runners scored")

    # Step 4 — Consensus overlay
    print("Step 4: Consensus overlay...")
    try:
        from daily_consensus_overlay import run_consensus_overlay, apply_overlay_to_runners
        betfair_runners = {}
        for r in scored:
            norm = re.sub(r'[^a-z0-9 ]', '', r['name'].lower()).strip()
            betfair_runners[norm] = {
                'betfair_name': r['name'],
                'course': r['venue'],
                'time': format_time_uk(r['race_time']),
                'race_name': r.get('race_name', ''),
                'race_type': r.get('race_type', ''),
                'field_size': r.get('field_size', 0),
                'market_id': r['market_id'],
                'score': r.get('score'),
                'bsp': r.get('bsp'),
                'qualifies': r.get('qualifies') is True,
                'form': r.get('form', ''),
            }
        overlay_data = run_consensus_overlay(betfair_runners=betfair_runners)
        scored = apply_overlay_to_runners(scored, overlay_data)
        matched = overlay_data.get('total_matched', 0)
        sources = overlay_data.get('sources_successful', [])
        print(f"  Overlay: {matched} horses matched from {sources}")
        try:
            subprocess.run(
                [
                    sys.executable,
                    os.path.join(SCRIPTS, 'build-tipster-memory.py'),
                    '--date',
                    datetime.now().strftime('%Y-%m-%d'),
                    '--csv',
                ],
                check=False,
                timeout=20,
            )
        except Exception as memory_error:
            print(f"  Tipster memory save skipped safely: {memory_error}")
    except Exception as e:
        print(f"  Consensus overlay failed safely: {e}")
        overlay_data = {'status': 'failed_or_partial', 'total_matched': 0, 'sources_successful': []}
        for r in scored:
            if 'consensus' not in r:
                r['consensus'] = {
                    'source_count': 0, 'tip_count': 0,
                    'overlay_points': 0, 'consensus_level': 'none',
                    'warning': None, 'sources': []
                }

    # Step 5 — Select picks
    print("Step 5: Selecting picks...")
    flat_scored  = [r for r in scored if r['race_type'] == 'Flat']
    jumps_scored = [r for r in scored if r['race_type'] in ('Hurdle', 'Chase', 'Bumper')]

    flat_picks,  flat_radar  = select_picks(flat_scored)
    jumps_picks, jumps_radar = select_picks(jumps_scored)

    # Signal 75 proof is a 3-horse daily Patent. From 14 June, live official
    # picks use Signal 75 first, with exact consensus points as an overlay.
    official_picks, value_candidate_count = select_signal_first_official(scored)
    print(f"  Signal-first live rule: {len(official_picks)} official pick(s) from {value_candidate_count} value candidates")
    save_consensus_shadow(scored, official_picks, overlay_data)
    flat_picks = [x for x in official_picks if x['race_type'] == 'Flat']
    jumps_picks = [x for x in official_picks if x['race_type'] in ('Hurdle', 'Chase', 'Bumper')]

    picks = flat_picks + jumps_picks
    radar = flat_radar + jumps_radar

    print(f"  Flat picks: {len(flat_picks)} | Jumps picks: {len(jumps_picks)}")
    print(f"  Flat radar: {len(flat_radar)} | Jumps radar: {len(jumps_radar)}")

    if len(picks) == 0:
        mode = 'noBetDay'
    elif len(picks) < 3:
        mode = 'topRatedOnly'
    else:
        mode = 'qualified'
    print(f"  Mode: {mode}")

    # Step 6 — Build output
    print("Step 6: Generating explanations and building output...")
    flat  = []
    jumps = []

    for pick in flat_picks:
        explanation = generate_explanation(pick)
        consensus = pick.get('consensus', {})
        print(f"  FLAT ✅ {pick['name']} score:{pick['score']} tipsters:{consensus.get('source_count',0)}")
        flat.append(build_race_entry(pick, explanation))

    for pick in jumps_picks:
        explanation = generate_explanation(pick)
        consensus = pick.get('consensus', {})
        print(f"  JUMPS ✅ {pick['name']} score:{pick['score']} tipsters:{consensus.get('source_count',0)}")
        jumps.append(build_race_entry(pick, explanation))

    # Radar cards — split by flat and jumps for tab display
    radar_cards = [build_radar_card(r) for r in radar]

    pick_names = set(p['name'] for p in flat_picks + jumps_picks)
    top_radar_flat  = [build_radar_card(r) for r in pick_radar_watchlist(flat_scored, pick_names)]
    top_radar_jumps = [build_radar_card(r) for r in pick_radar_watchlist(jumps_scored, pick_names)]

    output = {
        'date': get_today(),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'mode': mode,
        'noBetDay': mode == 'noBetDay',
        'noBetReason': '' if mode != 'noBetDay' else 'No qualifying selections today.',
        'threshold': 75,
        'topScore': int(picks[0]['score']) if picks else 0,
        'gapToThreshold': 0 if picks else 75,
        'flat': flat,
        'jumps': jumps,
        'topRated': radar_cards,
        'topRatedFlat': top_radar_flat,
        'topRatedJumps': top_radar_jumps,
        'results': {
            'flat': [], 'jumps': [],
            'patentReturn': 0, 'patentProfit': 0,
            'complete': False
        },
        'source': 'betfair_api',
        'engineVersion': ENGINE_VERSION,
        'dataSource': DATA_SOURCE,
        'weatherChecks': weather_checks,
    }

    import shutil
    output_path = TEST_OUTPUT if TEST_MODE else PICKS_JSON
    if not TEST_MODE and os.path.exists(PICKS_JSON):
        backup = PICKS_JSON.replace('.json', f'_backup_{get_today()}.json')
        shutil.copy2(PICKS_JSON, backup)
        print(f"  Backed up picks.json")
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to {output_path}")
    print("\n=== SUMMARY ===")
    for entry in flat + jumps:
        h = entry['horses'][0]
        print(f"  {h['name']} — {entry['course']} {entry['time']} score:{h['signal_score']} odds:{h['odds']} tipsters:{h['tipsters']}")
    print(f"\nRadar: {[r['name'] for r in radar_cards]}")
    print(f"Mode: {mode}")
    print("\nDone.")

if __name__ == '__main__':
    main()
