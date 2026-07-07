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
RACE_COMPARISON = '/Users/johnhowlett/Signal75/data/race_comparison_{}.json'
MEMORY_OVERLAY = '/Users/johnhowlett/Signal75/data/memory_overlay_{}.json'
HEAD_TO_HEAD_MASTER = '/Users/johnhowlett/Signal75/data/horse_intelligence/head_to_head_master.jsonl'
HEAD_TO_HEAD_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/head_to_head_profiles.json'
HISTORIC_RIVAL_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/historic_rival_profiles.json'
FIELD_RELATIONSHIP_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/field_relationship_profiles.json'
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

def parse_distance_furlongs(value):
    text = str(value or '').lower()
    match = re.search(r'(\d+)m\s*(\d+)?f?', text)
    if match:
        return float(int(match.group(1)) * 8 + int(match.group(2) or 0))
    match = re.search(r'(\d+(?:\.\d+)?)f', text)
    if match:
        return float(match.group(1))
    return None

def safe_float(value, default=None):
    try:
        if value in (None, ''):
            return default
        return float(value)
    except Exception:
        return default

def safe_int(value, default=0):
    try:
        if value in (None, ''):
            return default
        return int(float(value))
    except Exception:
        return default

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
    if os.environ.get('SIGNAL75_DISABLE_AI_EXPLANATIONS', '').strip() == '1':
        history = pick.get('history')
        if history:
            return (f"Signal 75 selected this horse from score, price, form and race fit. "
                   f"Historical win rate: {history['win_rate']}%.")
        return f"Signal 75 selected this horse from score, price, form and race fit."

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
        'rivalMemoryOverlay': pick.get('rival_memory_overlay'),
    }
    race = {
        'market_id': pick.get('market_id'),
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
        'market_id': r.get('market_id'),
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
        'rivalMemoryOverlay': r.get('rival_memory_overlay'),
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

def _public_score_parts(score, consensus):
    score = int(max(0, min(100, round(score or 0))))
    price_pts = int(score * 0.24)
    tip_overlay = int((consensus or {}).get('overlay_points') or 0)
    tip_pts = min(20, int(score * 0.20) + min(10, tip_overlay // 2))
    race_pts = int(score * 0.27)
    form_pts = max(0, score - price_pts - tip_pts - race_pts)
    return {
        'price': price_pts,
        'tips': tip_pts,
        'race': race_pts,
        'form': form_pts,
    }

def save_race_comparison(scored, races, official_picks):
    official_keys = {
        (p.get('market_id'), normalise_name_for_compare(p.get('name', '')))
        for p in official_picks
    }
    scored_lookup = {}
    for runner in scored:
        scored_lookup[(runner.get('market_id'), normalise_name_for_compare(runner.get('name', '')))] = runner

    output_races = []
    for race in races:
        runners = []
        for idx, raw in enumerate(race.get('runners', []), 1):
            key = (race.get('market_id'), normalise_name_for_compare(raw.get('name', '')))
            runner = scored_lookup.get(key)
            if runner:
                consensus = runner.get('consensus') or {}
                score = float(runner.get('score') or 0)
                status = 'official' if key in official_keys else ('watchlist' if score >= 65 else 'runner')
                runners.append({
                    'number': idx,
                    'name': runner.get('name'),
                    'score': round(score, 1),
                    'scored': True,
                    'status': status,
                    'odds': runner.get('bsp'),
                    'jockey': runner.get('jockey', ''),
                    'trainer': runner.get('trainer', ''),
                    'form': runner.get('form', ''),
                    'tipsters': _consensus_count(runner),
                    'consensus': {
                        'count': _consensus_count(runner),
                        'source_count': len(consensus.get('sources') or []) or consensus.get('source_count', 0),
                        'tip_count': consensus.get('tip_count', 0),
                        'consensus_count': _consensus_count(runner),
                        'level': consensus.get('consensus_level', 'none'),
                        'consensus_level': consensus.get('consensus_level', 'none'),
                        'overlay_points': consensus.get('overlay_points', 0),
                        'warning': consensus.get('warning', None),
                        'sources': consensus.get('sources', []),
                        'tipsters': consensus.get('tipsters', []),
                    },
                    'parts': _public_score_parts(score, consensus),
                    'warnings': [
                        w for w in [
                            runner.get('form_warning'),
                            'Hard form risk' if runner.get('form_risk') else '',
                            'Rival memory +{} pts'.format(runner.get('rival_memory_overlay', {}).get('points')) if runner.get('rival_memory_overlay') else '',
                        ] if w
                    ],
                    'rivalMemoryOverlay': runner.get('rival_memory_overlay'),
                })
            else:
                runners.append({
                    'number': idx,
                    'name': raw.get('name'),
                    'score': 0,
                    'scored': False,
                    'status': 'not_scored',
                    'odds': raw.get('best_back'),
                    'jockey': raw.get('jockey', ''),
                    'trainer': raw.get('trainer', ''),
                    'form': raw.get('form', ''),
                    'tipsters': 0,
                    'consensus': {
                        'count': 0,
                        'source_count': 0,
                        'tip_count': 0,
                        'consensus_count': 0,
                        'level': 'none',
                        'consensus_level': 'none',
                        'overlay_points': 0,
                        'sources': [],
                        'tipsters': [],
                    },
                    'parts': {'price': 0, 'tips': 0, 'race': 0, 'form': 0},
                    'warnings': ['Outside current Signal 75 scoring range'],
                })

        runners.sort(key=lambda r: (r.get('scored') is True, r.get('score') or 0, r.get('tipsters') or 0), reverse=True)
        output_races.append({
            'market_id': race.get('market_id'),
            'course': clean_course_name(race.get('venue')),
            'time': format_time_uk(race.get('race_time', '')),
            'race_name': race.get('race_name', ''),
            'race_type': infer_race_type_from_name(race.get('race_name', '')),
            'field_size': race.get('field_size') or len(race.get('runners', [])),
            'runners': runners,
        })

    payload = {
        'date': get_today(),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'status': 'display_only',
        'message': 'Race comparison data for the public pop-up. Does not alter scoring, picks, proof, or results.',
        'races': output_races,
    }
    path = RACE_COMPARISON.format(get_today())
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
    print(f"  Race comparison saved: {path}")
    return path

def normalise_name_for_compare(name):
    return re.sub(r'[^a-z0-9 ]', '', str(name or '').lower()).strip()

def normalise_memory_name(name):
    return re.sub(r'[^a-z0-9]', '', str(name or '').lower())

def load_json_safe(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def iter_jsonl_safe(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return

def parse_memory_date(value):
    try:
        return datetime.strptime(str(value or '')[:10], '%Y-%m-%d').date()
    except Exception:
        return None

def memory_recency_days(value):
    item_date = parse_memory_date(value)
    if not item_date:
        return None
    return (datetime.now().date() - item_date).days

def load_rival_memory_support():
    """
    Build a small, controlled support map from Signal 75's own race memory.
    This is not an override. It rewards proven rival strength only where the
    stored evidence says a horse beat a strong Signal 75 runner before.
    """
    support = {}

    for record in iter_jsonl_safe(HEAD_TO_HEAD_MASTER):
        winner = record.get('winner')
        loser_score = float(record.get('loser_signal_score') or 0)
        winner_key = normalise_memory_name(winner)
        if not winner_key or loser_score < 75:
            continue
        days = memory_recency_days(record.get('date'))
        if days is None or days > 365:
            continue
        points = 6 if days <= 90 else 4
        item = support.setdefault(winner_key, {
            'points': 0,
            'signals': [],
            'notes': [],
            'source': 'head_to_head_master',
            'source_types': [],
            'historic_distances_furlongs': [],
            'historic_races': [],
        })
        item['source_types'].append('head_to_head_master')
        item['points'] = min(8, item['points'] + points)
        item['signals'].append('BEAT_HIGH_SIGNAL_HORSE')
        item['notes'].append(record.get('evidence_note') or f"{winner} beat a strong Signal 75 horse.")
        race_name = record.get('race_name')
        item['historic_races'].append(race_name)
        parsed_distance = parse_distance_furlongs(race_name)
        if parsed_distance is not None:
            item['historic_distances_furlongs'].append(parsed_distance)

    for profile_file in (HEAD_TO_HEAD_PROFILES, HISTORIC_RIVAL_PROFILES):
        payload = load_json_safe(profile_file, {})
        for profile in (payload.get('pairs') or {}).values():
            tier = profile.get('evidence_tier')
            if tier not in ('strong_warning_or_support', 'useful_pattern'):
                continue
            dominant = profile.get('dominant_horse')
            dominant_key = normalise_memory_name(dominant)
            if not dominant_key:
                continue
            dominance_rate = float(profile.get('dominance_rate') or 0)
            meetings = int(profile.get('meetings_logged') or profile.get('historic_meetings_found') or 0)
            if meetings < 2 or dominance_rate < 0.67:
                continue
            days = memory_recency_days(profile.get('last_seen') or profile.get('latest_target_date') or profile.get('latest_historic_date'))
            if days is not None and days > 730:
                continue
            points = 8 if tier == 'strong_warning_or_support' else 5
            item = support.setdefault(dominant_key, {
                'points': 0,
                'signals': [],
                'notes': [],
                'source': 'rival_profiles',
                'source_types': [],
            })
            item['source_types'].append('rival_profiles')
            item['points'] = min(12, item['points'] + points)
            item['signals'].append('DOMINANT_RIVAL_MEMORY')
            item['notes'].append(profile.get('last_note') or profile.get('latest_note') or f"{dominant} has a proven rival-memory edge.")
            item.setdefault('historic_distances_furlongs', profile.get('historic_distances_furlongs_seen') or [])
            item.setdefault('latest_historic_distance_furlongs', profile.get('latest_historic_distance_furlongs'))
            item.setdefault('latest_historic_race', profile.get('latest_historic_race'))
            item.setdefault('latest_target_race', profile.get('latest_target_race'))

    field_payload = load_json_safe(FIELD_RELATIONSHIP_PROFILES, {})
    for profile in (field_payload.get('profiles') or {}).values():
        signal = profile.get('selection_signal')
        if signal not in ('strong_positive', 'positive'):
            continue
        horse_key = normalise_memory_name(profile.get('horse_key') or profile.get('horse_name'))
        if not horse_key:
            continue
        relationship_score = int(profile.get('relationship_score') or 0)
        if relationship_score < 16:
            continue
        points = min(8, int(profile.get('overlay_points') or (8 if signal == 'strong_positive' else 5)))
        if points <= 0:
            continue
        item = support.setdefault(horse_key, {
            'points': 0,
            'signals': [],
            'notes': [],
            'source': 'field_relationship_memory',
            'source_types': [],
        })
        item['source_types'].append('field_relationship_memory')
        item['points'] = min(12, item['points'] + points)
        item['signals'].append('FIELD_RELATIONSHIP_MEMORY')
        if signal == 'strong_positive':
            item['signals'].append('STRONG_FIELD_MEMORY')
        if profile.get('beat_high_signal_horses'):
            item['signals'].append('BEAT_HIGH_SIGNAL_HORSE')
        if profile.get('decisive_wins'):
            item['signals'].append('DECISIVE_WIN_MEMORY')
        note = profile.get('public_label') or profile.get('last_evidence') or f"{profile.get('horse_name')} has positive field relationship evidence."
        item['notes'].append(note)
        item['rivals_beaten'] = profile.get('rivals_beaten') or {}
        item['relationship_score'] = relationship_score
        item['public_label'] = profile.get('public_label')
        item['same_or_known_condition_edges'] = int(profile.get('same_or_known_condition_edges') or 0)
        item['recent_edges_180d'] = int(profile.get('recent_edges_180d') or 0)
        item['top_signals'] = profile.get('top_signals') or []

    return support

def memory_context_review(runner, item):
    """
    Guard the Grandad/rival-memory boost so old rival evidence does not
    overreach when today's race setup is materially different or thin.
    """
    warnings = []
    boost_cap = 8
    signals = set(item.get('signals') or [])
    source = item.get('source') or ''
    source_types = set(item.get('source_types') or [source])
    tipsters = _consensus_count(runner)
    current_distance = parse_distance_furlongs(runner.get('race_name'))

    historic_distances = []
    for value in (item.get('historic_distances_furlongs') or []):
        parsed = safe_float(value)
        if parsed is not None:
            historic_distances.append(parsed)
    latest_distance = safe_float(item.get('latest_historic_distance_furlongs'))
    if latest_distance is not None:
        historic_distances.append(latest_distance)

    if current_distance is not None and historic_distances:
        closest_gap = min(abs(current_distance - distance) for distance in historic_distances)
        if closest_gap >= 3:
            warnings.append(f"Memory evidence came from a different trip ({closest_gap:.0f}f gap).")
            boost_cap = min(boost_cap, 2)

    if 'field_relationship_memory' in source_types:
        same_condition_edges = int(item.get('same_or_known_condition_edges') or 0)
        exceptional = bool({'BEAT_HIGH_SIGNAL_HORSE', 'DECISIVE_WIN_MEMORY', 'STRONG_FIELD_MEMORY'}.intersection(signals))
        if same_condition_edges <= 0 and not exceptional:
            warnings.append("Memory has rival wins, but no confirmed same-condition evidence yet.")
            boost_cap = min(boost_cap, 2)
            if tipsters == 0:
                boost_cap = 0

    if tipsters == 0 and runner.get('score', 0) < 90 and boost_cap <= 2:
        warnings.append("No tipster support, so weak-context memory cannot make this an official pick.")
        runner['memory_context_risk'] = True

    return boost_cap, warnings

def apply_rival_memory_overlay(scored):
    support = load_rival_memory_support()
    applied = []
    market_runners = {}
    market_display = {}
    for runner in scored:
        market_id = runner.get('market_id')
        if not market_id:
            continue
        key = normalise_memory_name(runner.get('name'))
        market_runners.setdefault(market_id, set()).add(key)
        market_display.setdefault(market_id, {})[key] = runner.get('name')

    for runner in scored:
        key = normalise_memory_name(runner.get('name'))
        item = support.get(key)
        if not item:
            continue
        if 'FIELD_RELATIONSHIP_MEMORY' in (item.get('signals') or []):
            beaten_keys = {normalise_memory_name(name) for name in (item.get('rivals_beaten') or {})}
            same_race_rivals = sorted(
                market_runners.get(runner.get('market_id'), set()).intersection(beaten_keys)
            )
            direct_rival_match = [
                market_display.get(runner.get('market_id'), {}).get(rival_key, rival_key)
                for rival_key in same_race_rivals
                if rival_key != key
            ]
            has_exceptional_evidence = bool(
                {'BEAT_HIGH_SIGNAL_HORSE', 'DECISIVE_WIN_MEMORY', 'STRONG_FIELD_MEMORY'}.intersection(set(item.get('signals') or []))
            )
            if not direct_rival_match and not has_exceptional_evidence:
                continue
            if direct_rival_match:
                item = dict(item)
                item['notes'] = list(item.get('notes') or [])
                item['notes'].insert(0, 'Horse memory: previously beat today\'s rival(s) {}.'.format(', '.join(direct_rival_match[:3])))

        base_score = float(runner.get('score') or 0)
        recency_penalty = int(runner.get('recency_form_penalty') or 0)
        if base_score < 60 or recency_penalty >= 12 or runner.get('form_risk'):
            continue
        boost_cap, context_warnings = memory_context_review(runner, item)
        boost = min(8, boost_cap, int(item.get('points') or 0))
        if context_warnings:
            runner['memory_context_warnings'] = context_warnings[:3]
        if boost <= 0:
            if context_warnings:
                runner['rival_memory_overlay'] = {
                    'points': 0,
                    'signals': sorted(set(item.get('signals') or [])),
                    'notes': (context_warnings + (item.get('notes') or []))[:3],
                    'source': item.get('source') or 'rival_memory',
                    'scoringImpact': 'blocked_context_risk',
                }
            continue
        runner['score_before_memory_overlay'] = base_score
        runner['score'] = round(min(100, base_score + boost), 1)
        runner['rival_memory_overlay'] = {
            'points': boost,
            'signals': sorted(set(item.get('signals') or [])),
            'notes': (context_warnings + (item.get('notes') or []))[:3],
            'source': item.get('source') or 'rival_memory',
            'scoringImpact': 'positive_overlay',
        }
        applied.append({
            'horse': runner.get('name'),
            'course': runner.get('venue'),
            'time': format_time_uk(runner.get('race_time', '')),
            'market_id': runner.get('market_id'),
            'score_before': base_score,
            'score_after': runner['score'],
            'points': boost,
            'signals': runner['rival_memory_overlay']['signals'],
            'notes': runner['rival_memory_overlay']['notes'],
            'contextWarnings': runner.get('memory_context_warnings') or [],
        })

    payload = {
        'date': get_today(),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'status': 'live_positive_overlay',
        'message': 'Rival memory can add a small positive overlay when a horse previously beat strong Signal 75 opposition. Normal price, field, and form gates still apply.',
        'matched': len(applied),
        'records': applied,
    }
    path = MEMORY_OVERLAY.format(get_today())
    with open(path, 'w') as f:
        json.dump(payload, f, indent=2)
    return payload

def infer_race_type_from_name(race_name):
    text = str(race_name or '').lower()
    if 'chase' in text:
        return 'Chase'
    if 'hurdle' in text:
        return 'Hurdle'
    if 'bumper' in text or 'nh flat' in text:
        return 'Bumper'
    return 'Flat'

def _consensus_count(runner):
    consensus = runner.get('consensus') or {}
    return int(
        consensus.get('consensus_count')
        or consensus.get('tip_count')
        or consensus.get('source_count')
        or 0
    )

def _strong_consensus(runner):
    consensus = runner.get('consensus') or {}
    return (
        _consensus_count(runner) >= 4 or
        int(consensus.get('overlay_points') or 0) >= 16 or
        float(consensus.get('weighted_consensus_score') or 0) >= 4.0
    )

def _official_candidate(runner):
    bsp = runner.get('bsp')
    field_size = runner.get('field_size', 0)
    if (
        runner.get('score', 0) < 75 or
        bsp is None or
        int(field_size or 0) < 8 or
        runner.get('form_risk')
    ):
        return False

    price = float(bsp)
    recency_penalty = int(runner.get('recency_form_penalty') or 0)
    if runner.get('memory_context_risk') and _consensus_count(runner) == 0 and float(runner.get('score') or 0) < 90:
        return False

    if _strong_consensus(runner):
        return 4.1 <= price <= 8.0 and recency_penalty < 20

    return (
        4.1 <= price <= 6.0 and
        recency_penalty < 12
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
        runner.get('score', 0) >= 70 and
        runner.get('score', 0) >= 50 and
        bsp is not None and
        2.75 <= float(bsp) <= 8.0 and
        int(field_size or 0) >= 8 and
        not runner.get('form_risk') and
        int(runner.get('recency_form_penalty') or 0) < 20
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

def pick_radar_watchlist(scored, picked_names=None, picked_market_ids=None, limit=3):
    picked_names = picked_names or set()
    picked_market_ids = picked_market_ids or set()
    candidates = [
        r for r in scored
        if (
            r.get('name') not in picked_names and
            r.get('market_id') not in picked_market_ids and
            _radar_candidate(r)
        )
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
        used_market_ids = {p.get('market_id') for p in picks}
        for runner in ranked:
            name_key = runner.get('name', '').lower()
            if name_key in used_names or runner.get('market_id') in used_market_ids:
                continue
            picks.append(runner)
            used_names.add(name_key)
            used_market_ids.add(runner.get('market_id'))
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
    from scoring_engine import load_roi_tables, score_all_runners
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

    # Step 4a — Rival memory overlay
    print("Step 4a: Rival memory overlay...")
    try:
        memory_overlay_data = apply_rival_memory_overlay(scored)
        print(f"  Rival memory: {memory_overlay_data.get('matched', 0)} horse(s) received proven-rival support")
    except Exception as e:
        print(f"  Rival memory overlay failed safely: {e}")
        memory_overlay_data = {
            'status': 'failed_or_partial',
            'matched': 0,
            'records': [],
        }

    # Step 5 — Select picks
    print("Step 5: Selecting picks...")
    flat_scored  = [r for r in scored if r['race_type'] == 'Flat']
    jumps_scored = [r for r in scored if r['race_type'] in ('Hurdle', 'Chase', 'Bumper')]

    # Signal 75 proof is a 3-horse daily Patent. From 14 June, live official
    # picks use Signal 75 first, with exact consensus points as an overlay.
    official_picks, value_candidate_count = select_signal_first_official(scored)
    print(f"  Signal-first live rule: {len(official_picks)} official pick(s) from {value_candidate_count} value candidates")
    save_consensus_shadow(scored, official_picks, overlay_data)
    save_race_comparison(scored, races, official_picks)
    flat_picks = [x for x in official_picks if x['race_type'] == 'Flat']
    jumps_picks = [x for x in official_picks if x['race_type'] in ('Hurdle', 'Chase', 'Bumper')]

    picks = flat_picks + jumps_picks
    picked_market_ids = {p.get('market_id') for p in official_picks}
    picked_names = set(p['name'] for p in flat_picks + jumps_picks)
    top_radar_flat_runners = pick_radar_watchlist(flat_scored, picked_names, picked_market_ids)
    top_radar_jumps_runners = pick_radar_watchlist(jumps_scored, picked_names, picked_market_ids)
    radar = _pick_three(sorted(
        top_radar_flat_runners + top_radar_jumps_runners,
        key=lambda r: (_consensus_count(r), r.get('score', 0), -(r.get('bsp') or 99)),
        reverse=True
    ))

    print(f"  Flat picks: {len(flat_picks)} | Jumps picks: {len(jumps_picks)}")
    print(f"  Flat watchlist: {len(top_radar_flat_runners)} | Jumps watchlist: {len(top_radar_jumps_runners)}")

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

    top_radar_flat  = [build_radar_card(r) for r in top_radar_flat_runners]
    top_radar_jumps = [build_radar_card(r) for r in top_radar_jumps_runners]

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
        'rivalMemoryOverlay': {
            'status': memory_overlay_data.get('status'),
            'matched': memory_overlay_data.get('matched', 0),
        },
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
    if not TEST_MODE:
        try:
            challenger_script = os.path.join(SCRIPTS, "generate-challenger-lab.py")
            subprocess.run([sys.executable, challenger_script, "--date", get_today()], check=False, timeout=60)
        except Exception as exc:
            print(f"  Challenger Lab skipped: {exc}")
    print("\nDone.")

if __name__ == '__main__':
    main()
