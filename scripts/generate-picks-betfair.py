#!/usr/bin/env python3
"""
generate-picks-betfair.py — Signal 75
Betfair API picks generator — exact picks.json format match.
"""
import json, os, sys, subprocess, re, sqlite3
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
FIELD_RELATIVE_ARCHIVE = '/Users/johnhowlett/Signal75/data/field_relative_archive_{}.json'
FIELD_GRAPH = '/Users/johnhowlett/Signal75/data/horse_intelligence/field_graph_{}.json'
HEAD_TO_HEAD_MASTER = '/Users/johnhowlett/Signal75/data/horse_intelligence/head_to_head_master.jsonl'
HEAD_TO_HEAD_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/head_to_head_profiles.json'
HISTORIC_RIVAL_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/historic_rival_profiles.json'
FIELD_RELATIONSHIP_PROFILES = '/Users/johnhowlett/Signal75/data/horse_intelligence/field_relationship_profiles.json'
FORM_HISTORY_SQLITE = '/Users/johnhowlett/Signal75/data/horse_intelligence/form_history.sqlite'
TEST_MODE     = False

# ── FUTURE-PROOFING CONSTANTS ──────────────────────────────────────────────
ENGINE_VERSION = "v1"          # Bump to "v2" when scoring_engine_v2 goes live
DATA_SOURCE    = "betfair_api" # Change if paid API added
ODDS_SOURCE    = "betfair_bsp" # Change if bookmaker odds used
# ──────────────────────────────────────────────────────────────────────────

STRONG_FORM_PATTERNS = {
    '111', '112', '121', '211', '113',
    '1111', '1112', '1121', '2111', '1122',
}
_FORM_PATTERN_CACHE = {}

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

def bet_model_for_count(count):
    count = int(count or 0)
    if count >= 3:
        return {
            'betType': 'each_way_patent',
            'label': 'Full Patent',
            'count': count,
            'totalStake': 14.0,
            'betLines': 14,
            'summary': '3 picks found · £14 total stake · 14 lines',
        }
    if count == 2:
        return {
            'betType': 'each_way_double',
            'label': 'Each-Way Double',
            'count': count,
            'totalStake': 14.0,
            'betLines': 6,
            'summary': '2 picks found · £14 proof stake · 6 lines',
        }
    if count == 1:
        return {
            'betType': 'each_way_single',
            'label': 'Each-Way Single',
            'count': count,
            'totalStake': 14.0,
            'betLines': 2,
            'summary': '1 pick found · £14 proof stake · 2 lines',
        }
    return {
        'betType': 'no_bet',
        'label': 'No Bet Today',
        'count': 0,
        'totalStake': 0.0,
        'betLines': 0,
        'summary': 'No horse met all the required criteria today',
    }

def build_official_bet_summary(flat_count, jumps_count):
    total_official = int(flat_count or 0) + int(jumps_count or 0)
    model = bet_model_for_count(total_official)
    return {
        **model,
        'flatCount': int(flat_count or 0),
        'jumpsCount': int(jumps_count or 0),
        'totalOfficial': total_official,
        'totalBetLines': model['betLines'],
        'summary': model['summary'],
    }

def _archive_confidence_tier(horse):
    score = float(horse.get('signal_score') or horse.get('score') or 0)
    tipsters = int(horse.get('tipsters') or 0)
    if score >= 95 and tipsters >= 4:
        return 'STRONG'
    if score >= 85 and tipsters >= 2:
        return 'SOLID'
    if score >= 75:
        return 'MODERATE'
    if score >= 70:
        return 'WEAK'
    return 'LOW'

def _archive_top_reasons(horse):
    score = float(horse.get('signal_score') or horse.get('score') or 0)
    tipsters = int(horse.get('tipsters') or 0)
    reasons = []
    if tipsters >= 6:
        reasons.append(f"{tipsters} professional tipsters")
    elif tipsters >= 3:
        reasons.append(f"{tipsters} tipsters backing this horse")
    elif tipsters > 0:
        reasons.append(f"{tipsters} tipster{'s' if tipsters != 1 else ''}")
    if score >= 100:
        reasons.append("Score 100 — maximum signal")
    elif score >= 95:
        reasons.append(f"Score {score:.0f} — elite signal")
    elif score >= 85:
        reasons.append(f"Score {score:.0f} — strong signal")
    overlay = horse.get('rivalMemoryOverlay') or {}
    if isinstance(overlay, dict) and int(overlay.get('points') or 0) > 0:
        reasons.append("Positive rival memory in today’s field")
    if not horse.get('formWarning'):
        reasons.append("Clean recent form")
    return reasons[:3]

def _archive_top_risks(horse, race):
    risks = []
    if int(horse.get('tipsters') or 0) == 0:
        risks.append("No tipster support")
    if horse.get('formWarning'):
        risks.append(str(horse.get('formWarning')))
    if int(race.get('runners') or 0) > 14:
        risks.append("Large field — harder to place")
    overlay = horse.get('rivalMemoryOverlay') or {}
    if isinstance(overlay, dict) and int(overlay.get('points') or 0) < 0:
        risks.append("Rival memory warning")
    return risks[:2]

def write_field_relative_prerace_archive_from_picks(picks_path=PICKS_JSON):
    """Write a read-only pre-race archive from the already-saved picks.json."""
    try:
        with open(picks_path) as handle:
            picks_data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  Field-relative archive skipped: could not read picks.json ({exc})")
        return None

    date_str = picks_data.get('date') or get_today()
    archived = []
    for race in (picks_data.get('flat') or []) + (picks_data.get('jumps') or []):
        horses = race.get('horses') or []
        if not horses:
            continue
        horse = horses[0]
        archived.append({
            'horse': horse.get('name'),
            'course': race.get('course'),
            'time': race.get('time'),
            'odds_at_pick': horse.get('odds'),
            'base_score': horse.get('signal_score'),
            'field_relative_score': None,
            'confidence_tier': _archive_confidence_tier(horse),
            'field_size': race.get('runners'),
            'race_class': race.get('race_class'),
            'tipsters': horse.get('tipsters', 0),
            'top_reasons': _archive_top_reasons(horse),
            'top_risks': _archive_top_risks(horse, race),
            'divergence': False,
            'challenger_would_pick': None,
            'live_result': None,
            'bsp': None,
            'position': None,
            'learning_note': None,
        })

    archive = {
        'date': date_str,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'snapshot_type': 'pre_race',
        'settled': False,
        'picks': archived,
    }
    out_path = FIELD_RELATIVE_ARCHIVE.format(date_str)
    with open(out_path, 'w') as handle:
        json.dump(archive, handle, indent=2)
        handle.write('\n')
    print(f"  Field-relative pre-race archive saved: {out_path}")
    return out_path

def build_radar_card(r):
    consensus = r.get('consensus') or {}
    weather = r.get('weatherRisk') or {}
    graph_watch = r.get('graph_evidence_watchlist') or {}
    tipster_count = _consensus_count(r)
    score = int(r['score'])
    odds_text = f"{r['bsp']:.1f}" if r.get('bsp') else "N/A"
    reason = graph_watch.get('reason') or f"Radar watchlist: Signal {score}, odds {odds_text}, form {r.get('form') or 'unknown'}."
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
        'graphEvidenceWatchlist': graph_watch or None,
        'reason': reason,
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
    consensus = consensus or {}
    tip_overlay = int(consensus.get('overlay_points') or 0)
    consensus_count = int(consensus.get('count') or consensus.get('consensus_count') or consensus.get('source_count') or 0)
    tip_count = int(consensus.get('tip_count') or 0)
    has_tip_evidence = bool(consensus_count or tip_count or tip_overlay)
    tip_pts = 0 if not has_tip_evidence else min(20, int(score * 0.20) + min(10, tip_overlay // 2))
    race_pts = int(score * 0.27)
    form_pts = max(0, score - price_pts - tip_pts - race_pts)
    return {
        'price': price_pts,
        'tips': tip_pts,
        'race': race_pts,
        'form': form_pts,
    }

def _official_display_price_penalty(runner):
    bsp = runner.get('bsp')
    if bsp is None:
        return 0, ''
    price = float(bsp)
    upper = 8.0 if _strong_consensus(runner) else 6.0
    if price < 4.1:
        return 10, 'price too short for official value band'
    if price > upper:
        if price > 10:
            return 12, 'price too big for official value band'
        return 8, 'price outside official value band'
    return 0, ''

def _official_display_adjusted_score(runner):
    score = float(runner.get('score') or 0)
    adjustments = []

    if 'formPatternProfile' not in runner:
        _apply_live_form_pattern_profile(runner)

    form_pattern_bonus = int(runner.get('formPatternBonus') or 0)
    if form_pattern_bonus > 0:
        adjustments.append({
            'type': 'bonus',
            'points': form_pattern_bonus,
            'reason': 'strong rich-form pattern',
        })
    elif form_pattern_bonus < 0:
        adjustments.append({
            'type': 'penalty',
            'points': abs(form_pattern_bonus),
            'reason': 'weak rich-form pattern',
        })

    price_penalty, price_reason = _official_display_price_penalty(runner)
    if price_penalty:
        adjustments.append({
            'type': 'penalty',
            'points': price_penalty,
            'reason': price_reason,
        })

    rival_penalty = runner.get('rival_threat_penalty') or {}
    if rival_penalty.get('points'):
        adjustments.append({
            'type': 'penalty',
            'points': int(rival_penalty.get('points') or 0),
            'reason': 'rival has beaten this horse before',
        })

    form_penalty = runner.get('recent_unplaced_form_penalty') or {}
    if form_penalty.get('points'):
        adjustments.append({
            'type': 'penalty',
            'points': int(form_penalty.get('points') or 0),
            'reason': 'recent form confidence warning',
        })

    form_gate_penalty = int(runner.get('formGatePenalty') or 0)
    if form_gate_penalty:
        adjustments.append({
            'type': 'penalty',
            'points': form_gate_penalty,
            'reason': 'form pattern confidence warning',
        })

    adjusted = (
        score
        + sum(item['points'] for item in adjustments if item['type'] == 'bonus')
        - sum(item['points'] for item in adjustments if item['type'] == 'penalty')
    )
    adjusted = max(0, min(100, round(adjusted, 1)))
    return adjusted, adjustments

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
                adjusted_score, score_adjustments = _official_display_adjusted_score(runner)
                is_graph_watchlist = bool(runner.get('graph_evidence_watchlist'))
                status = 'official' if key in official_keys else ('watchlist' if score >= 65 or is_graph_watchlist else 'runner')
                runners.append({
                    'number': idx,
                    'name': runner.get('name'),
                    'score': round(score, 1),
                    'officialAdjustedScore': adjusted_score,
                    'scoreAdjustments': score_adjustments,
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
                            runner.get('form_confidence_warning'),
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

def load_field_graph_watchlist_support(date_text):
    graph = load_json_safe(FIELD_GRAPH.format(date_text), {})
    support = {}
    for runner in graph.get('currentRunners') or []:
        market_id = runner.get('market_id')
        name_key = normalise_name_for_compare(runner.get('horse_name', ''))
        if market_id and name_key:
            support[(market_id, name_key)] = runner
    return support

def direct_field_win_count(graph_runner):
    rivals = set()
    for edge in graph_runner.get('direct_edges') or []:
        rival_key = edge.get('rival_key') or normalise_memory_name(edge.get('rival', ''))
        if rival_key:
            rivals.add(rival_key)
    return len(rivals)

def field_graph_positive_overlay_points(graph_runner):
    direct_wins = direct_field_win_count(graph_runner)
    if direct_wins <= 0:
        return 0
    return min(6, direct_wins * 2)

def annotate_graph_evidence_watchlist(scored, date_text):
    graph_support = load_field_graph_watchlist_support(date_text)
    matched = 0
    for runner in scored:
        key = (runner.get('market_id'), normalise_name_for_compare(runner.get('name', '')))
        graph_runner = graph_support.get(key)
        if not graph_runner:
            continue

        positive_points = field_graph_positive_overlay_points(graph_runner)
        if positive_points:
            original_score = float(runner.get('score') or 0)
            runner['field_graph_positive_overlay'] = {
                'points': positive_points,
                'direct_field_wins': direct_field_win_count(graph_runner),
                'rivals': [
                    edge.get('rival')
                    for edge in (graph_runner.get('direct_edges') or [])[:4]
                    if edge.get('rival')
                ],
                'scoringImpact': 'positive_overlay',
            }
            runner['score'] = round(min(100, original_score + positive_points), 1)

        negative_edges = graph_runner.get('negative_edges') or []
        if negative_edges:
            strongest_threats = sorted(
                negative_edges,
                key=lambda edge: (
                    int(edge.get('points') or 0),
                    int(edge.get('meetings') or 0),
                ),
                reverse=True,
            )
            runner['field_graph_rival_threat'] = {
                'points': int(strongest_threats[0].get('points') or 0),
                'rivals': [
                    edge.get('rival')
                    for edge in strongest_threats[:4]
                    if edge.get('rival')
                ],
                'negative_edges': strongest_threats[:4],
                'public_label': graph_runner.get('public_label'),
                'scoringImpact': 'relationship_warning',
            }

        graph_score = int(graph_runner.get('relationship_score') or 0)
        direct_wins = direct_field_win_count(graph_runner)
        current_score = float(runner.get('score') or 0)
        if not (
            graph_score >= 60 and
            direct_wins >= 3 and
            50 <= current_score <= 74
        ):
            continue

        runner['graph_evidence_watchlist'] = {
            'reason': "GRAPH_EVIDENCE: High historical dominance over today's field despite current form. Not an official pick. Evidence only.",
            'graph_score': graph_score,
            'direct_field_wins': direct_wins,
            'recommended_use': graph_runner.get('recommended_use'),
            'public_label': graph_runner.get('public_label'),
        }
        matched += 1
    return matched

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

def load_rival_memory_support(scored=None):
    """
    Build a small, controlled support map from Signal 75's own race memory.
    This is not an override. It rewards proven rival strength only where the
    stored evidence says a horse beat a strong Signal 75 runner before.
    """
    support = {}
    scored = scored or []
    market_runners = {}
    market_display = {}
    for runner in scored:
        market_id = runner.get('market_id')
        if not market_id:
            continue
        key = normalise_memory_name(runner.get('name'))
        if not key:
            continue
        market_runners.setdefault(market_id, set()).add(key)
        market_display.setdefault(market_id, {})[key] = runner.get('name')

    def same_race_rivals(horse_key, rival_keys):
        matches = []
        if not horse_key or not rival_keys:
            return matches
        for market_id, runner_keys in market_runners.items():
            if horse_key not in runner_keys:
                continue
            for rival_key in rival_keys:
                if rival_key in runner_keys and rival_key != horse_key:
                    matches.append(market_display.get(market_id, {}).get(rival_key, rival_key))
        return sorted(set(matches))

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
            pair_horses = profile.get('horses') or []
            rival_keys = [
                normalise_memory_name(horse)
                for horse in pair_horses
                if normalise_memory_name(horse) and normalise_memory_name(horse) != dominant_key
            ]
            direct_rivals = same_race_rivals(dominant_key, rival_keys)
            if market_runners:
                for rival_key in rival_keys:
                    warning_rivals = same_race_rivals(rival_key, [dominant_key])
                    if not warning_rivals:
                        continue
                    warning_item = support.setdefault(rival_key, {
                        'points': 0,
                        'signals': [],
                        'notes': [],
                        'source': 'rival_profiles',
                        'source_types': [],
                        'relationship_warnings': [],
                    })
                    warning_item['source_types'].append('rival_profiles')
                    warning_item['signals'].append('DOMINATED_BY_RIVAL_MEMORY')
                    note = profile.get('last_note') or profile.get('latest_note') or f"{dominant} has previously dominated this runner."
                    warning_item.setdefault('relationship_warnings', []).append({
                        'rival': dominant,
                        'points': -8 if tier == 'strong_warning_or_support' else -5,
                        'note': f"Warning: previously dominated by today's rival(s) {', '.join(warning_rivals[:3])}. {note}",
                    })
            if market_runners and not direct_rivals:
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
            if direct_rivals:
                item['notes'].append("Horse memory: previously dominated today's rival(s) {}.".format(', '.join(direct_rivals[:3])))
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
    support = load_rival_memory_support(scored)
    applied = []
    warnings = []
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
        relationship_warnings = item.get('relationship_warnings') or []
        if relationship_warnings:
            warning_points = min((int(row.get('points') or 0) for row in relationship_warnings), default=0)
            runner['rival_memory_overlay'] = {
                'points': warning_points,
                'signals': sorted(set(item.get('signals') or [])),
                'notes': [row.get('note') for row in relationship_warnings if row.get('note')][:3],
                'source': item.get('source') or 'rival_memory',
                'scoringImpact': 'relationship_warning',
            }
            warnings.append({
                'horse': runner.get('name'),
                'course': runner.get('venue'),
                'time': format_time_uk(runner.get('race_time', '')),
                'market_id': runner.get('market_id'),
                'score_before': float(runner.get('score') or 0),
                'score_after': runner.get('score'),
                'points': warning_points,
                'signals': runner['rival_memory_overlay']['signals'],
                'notes': runner['rival_memory_overlay']['notes'],
            })
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
        'message': "Rival memory can add a small positive overlay only when the proven rival evidence is in today's field. Reverse evidence is shown as a warning.",
        'matched': len(applied),
        'warnings': len(warnings),
        'records': applied,
        'warningRecords': warnings,
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

def _completed_form_digits(form):
    return [int(char) for char in re.sub(r'[^0-9A-Z]', '', str(form or '').upper()) if char.isdigit()]

def _completed_form_markers(form):
    return [
        char for char in re.sub(r'[^0-9A-Z]', '', str(form or '').upper())
        if char.isdigit() or char in {'P', 'F', 'U', 'R', 'B', 'S'}
    ]

def _form_pattern_from_string(form_value, length=4):
    text = str(form_value or '').upper()
    cleaned = re.sub(r'[^0-9PFURBS]', '', text)
    if not cleaned:
        return ''
    return cleaned[-length:]

def _form_pattern_stats_for_form(form_value):
    pattern = _form_pattern_from_string(form_value, 4)
    if not pattern:
        return {
            'pattern': '',
            'pattern_length': 0,
            'starts': 0,
            'place_rate': None,
            'source': 'missing_form',
        }

    cache_key = pattern
    if cache_key in _FORM_PATTERN_CACHE:
        return dict(_FORM_PATTERN_CACHE[cache_key])

    if os.path.exists(FORM_HISTORY_SQLITE):
        try:
            conn = sqlite3.connect(FORM_HISTORY_SQLITE)
            conn.execute('PRAGMA query_only = ON')
            candidates = [pattern]
            if len(pattern) >= 4:
                candidates.append(pattern[-3:])
            for candidate in candidates:
                row = conn.execute(
                    '''
                    SELECT pattern_length, pattern, starts, wins, places, win_rate, place_rate
                    FROM form_pattern_stats
                    WHERE pattern_length = ? AND pattern = ?
                    ''',
                    (len(candidate), candidate),
                ).fetchone()
                if not row:
                    continue
                rate = float(row[6] or 0)
                if rate > 1:
                    rate = rate / 100.0
                conn.close()
                payload = {
                    'pattern_length': int(row[0]),
                    'pattern': str(row[1]),
                    'starts': int(row[2] or 0),
                    'wins': int(row[3] or 0),
                    'places': int(row[4] or 0),
                    'win_rate': float(row[5] or 0),
                    'place_rate': rate,
                    'source': 'form_pattern_stats',
                }
                _FORM_PATTERN_CACHE[cache_key] = payload
                return dict(payload)
            conn.close()
        except Exception:
            pass

    fallback_pattern = pattern if len(pattern) >= 3 else pattern[-3:]
    if fallback_pattern in STRONG_FORM_PATTERNS or pattern[-3:] in STRONG_FORM_PATTERNS:
        payload = {
            'pattern': fallback_pattern,
            'pattern_length': len(fallback_pattern),
            'starts': 0,
            'place_rate': 0.45,
            'source': 'strong_pattern_fallback',
        }
    elif len(fallback_pattern) >= 3 and not any(ch in '123' for ch in fallback_pattern if ch.isdigit()):
        payload = {
            'pattern': fallback_pattern,
            'pattern_length': len(fallback_pattern),
            'starts': 0,
            'place_rate': 0.14,
            'source': 'all_unplaced_fallback',
        }
    else:
        payload = {
            'pattern': fallback_pattern,
            'pattern_length': len(fallback_pattern),
            'starts': 0,
            'place_rate': None,
            'source': 'no_pattern_stats',
        }
    _FORM_PATTERN_CACHE[cache_key] = payload
    return dict(payload)

def _form_pattern_strength(place_rate):
    if place_rate is None:
        return 'UNKNOWN'
    if place_rate >= 0.45:
        return 'STRONG'
    if place_rate >= 0.35:
        return 'GOOD'
    if place_rate >= 0.20:
        return 'WEAK'
    return 'AVOID'

def _form_pattern_score_bonus(place_rate):
    if place_rate is None:
        return 0
    if place_rate >= 0.55:
        return 5
    if place_rate >= 0.45:
        return 3
    if place_rate >= 0.35:
        return 0
    if place_rate < 0.15:
        return -8
    if place_rate < 0.25:
        return -3
    return 0

def _field_h2h_beaten_count(runner):
    for key in ('h2h_beaten', 'field_h2h_beaten', 'rivals_beaten'):
        try:
            value = int(runner.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            return value

    overlay = runner.get('rivalMemoryOverlay') or runner.get('rival_memory_overlay')
    if isinstance(overlay, dict) and _rival_overlay_points(runner) > 0:
        rivals = overlay.get('rivals') or overlay.get('opponents') or []
        if isinstance(rivals, list):
            return len([rival for rival in rivals if rival])
    return 0

def _live_form_pattern_profile(runner):
    stats = _form_pattern_stats_for_form(runner.get('form'))
    place_rate = stats.get('place_rate')
    bonus = _form_pattern_score_bonus(place_rate)
    raw_score = float(runner.get('score') or 0)
    adjusted = round(max(0, min(100, raw_score + bonus)), 1)
    return {
        **stats,
        'strength': _form_pattern_strength(place_rate),
        'bonus': bonus,
        'raw_score': round(raw_score, 1),
        'adjusted_score': adjusted,
    }

def _apply_live_form_pattern_profile(runner):
    profile = _live_form_pattern_profile(runner)
    runner['formPatternProfile'] = profile
    runner['formPatternStrength'] = profile.get('strength')
    runner['formPatternPlaceRate'] = profile.get('place_rate')
    runner['formPatternBonus'] = profile.get('bonus')
    current_adjusted = float(runner.get('live_adjusted_score', runner.get('score') or 0) or 0)
    runner['live_adjusted_score'] = round(max(0, min(100, current_adjusted + int(profile.get('bonus') or 0))), 1)
    return profile

def _form_gate_review(form_string, race_type='flat'):
    """
    Live official-pick safety gate for poor recent form.
    It does not rescore the horse; it only blocks form profiles that have
    repeatedly caused weak official selections.
    """
    markers = _completed_form_markers(form_string)
    if not markers:
        return {'passes': True, 'reason': None, 'code': None}

    recent = markers[-7:]
    last_four = markers[-4:]
    last_two = markers[-2:]
    first_two = markers[:2]
    non_completion = {'P', 'F', 'U', 'R'}

    if (
        len(last_two) == 2 and all(marker in non_completion for marker in last_two)
    ) or (
        len(first_two) == 2 and all(marker in non_completion for marker in first_two)
    ):
        return {
            'passes': False,
            'reason': 'two consecutive non-completions in recent form',
            'code': 'FORM_GATE_NON_COMPLETION',
        }

    placed_last_four = sum(1 for marker in last_four if marker in {'1', '2', '3'})
    if len(last_four) >= 4 and placed_last_four == 0:
        return {
            'passes': True,
            'reason': 'zero placed runs in last 4 starts',
            'code': 'FORM_GATE_ZERO_PLACED_LAST_4',
            'penalty': 6,
        }

    completed_last_two = [int(marker) for marker in last_two if marker.isdigit()]
    if (
        len(markers) <= 4 and
        len(completed_last_two) == 2 and
        any(1 <= value <= 3 for value in completed_last_two) and
        completed_last_two[-1] >= 4
    ):
        return {
            'passes': True,
            'reason': 'won or placed recently, but latest run was outside the places',
            'code': 'FORM_GATE_RECENT_WIN_THEN_UNPLACED',
            'penalty': 3,
        }

    if len(markers) <= 4 and len(completed_last_two) == 2 and all(value >= 4 or value == 0 for value in completed_last_two):
        return {
            'passes': False,
            'reason': 'short recent form has no credible placed evidence',
            'code': 'FORM_GATE_SHORT_POOR_FORM',
        }

    recent_digits = [int(marker) for marker in recent if marker.isdigit()]
    placed_count = sum(1 for value in recent_digits if 1 <= value <= 3)
    weak_count = sum(1 for value in recent_digits if value == 0 or value >= 4)
    if len(recent_digits) >= 6 and weak_count >= 4 and placed_count <= 3:
        return {
            'passes': True,
            'reason': 'messy recent form profile needs stronger proof before official selection',
            'code': 'FORM_GATE_MESSY_RECENT_FORM',
            'penalty': 4,
        }

    return {'passes': True, 'reason': None, 'code': None, 'penalty': 0}

def _form_gate_passes(form_string, race_type='flat'):
    return bool(_form_gate_review(form_string, race_type).get('passes'))

def _rival_overlay_points(runner):
    overlay = runner.get('rivalMemoryOverlay') or runner.get('rival_memory_overlay')
    if isinstance(overlay, dict):
        return int(overlay.get('points') or overlay.get('overlay_points') or overlay.get('score') or 0)
    try:
        return int(overlay or 0)
    except (TypeError, ValueError):
        return 0

def _rival_threat_warning(runner):
    field_graph_threat = runner.get('field_graph_rival_threat')
    if isinstance(field_graph_threat, dict):
        points = int(field_graph_threat.get('points') or 0)
        if points >= 12:
            rivals = [
                rival for rival in field_graph_threat.get('rivals') or []
                if rival
            ]
            return {
                'source': 'field_graph',
                'points': points,
                'rivals': rivals,
                'reason': "today's field contains a rival that has previously beaten this runner",
            }

    overlay = runner.get('rivalMemoryOverlay') or runner.get('rival_memory_overlay')
    if not isinstance(overlay, dict):
        return None

    points = int(overlay.get('points') or overlay.get('overlay_points') or overlay.get('score') or 0)
    signals = set(overlay.get('signals') or [])
    scoring_impact = overlay.get('scoringImpact') or overlay.get('scoring_impact')
    if (
        points < 0 or
        scoring_impact == 'relationship_warning' or
        'DOMINATED_BY_RIVAL_MEMORY' in signals
    ):
        return {
            'source': 'rival_memory',
            'points': points,
            'rivals': overlay.get('rivals') or overlay.get('opponents') or [],
            'reason': "rival memory says today's field contains a horse that previously dominated this runner",
            }
    return None

def _rival_threat_penalty_points(runner):
    threat = _rival_threat_warning(runner)
    if not threat:
        return 0

    source = threat.get('source')
    points = abs(int(threat.get('points') or 0))
    if source == 'field_graph':
        if points >= 16:
            return 6
        if points >= 14:
            return 4
        return 2

    return min(6, max(2, points))

def _has_zero_validation_rival_warning(runner):
    return _consensus_count(runner) == 0 and _rival_threat_warning(runner) is not None

def _recent_unplaced_form_live_penalty(runner):
    digits = _completed_form_digits(runner.get('form'))
    last_two = digits[-2:] if len(digits) >= 2 else []
    last_three = digits[-3:] if len(digits) >= 3 else []
    penalty = 0
    reasons = []

    if len(last_two) == 2 and all(value >= 4 for value in last_two):
        penalty += 4
        reasons.append('last two completed runs were both unplaced')

    if len(last_two) == 2 and all(value >= 5 for value in last_two):
        penalty += 3
        reasons.append('last two completed runs were both 5th or worse')

    if len(last_three) == 3 and not any(value <= 3 for value in last_three):
        penalty += 3
        reasons.append('no placed run in the last three completed starts')

    if _rival_overlay_points(runner) == 0:
        penalty += 2
        reasons.append("no positive rival evidence against today's field")

    if _strong_consensus(runner) and penalty:
        penalty = max(0, penalty - 2)
        reasons.append('strong tipster consensus softened the penalty')

    penalty = min(10, penalty)
    adjusted_score = round(max(0, float(runner.get('score') or 0) - penalty), 1)
    return {
        'points': penalty,
        'adjusted_score': adjusted_score,
        'would_clear_live_gate': adjusted_score >= 75,
        'last_two_completed': last_two,
        'last_three_completed': last_three,
        'reasons': reasons,
    }

def _has_severe_recent_form_warning(runner):
    return int(runner.get('recency_form_penalty') or 0) >= 12

def _has_recent_unplaced_form_pattern(form_confidence):
    reasons = form_confidence.get('reasons') or []
    return any(
        reason in reasons
        for reason in (
            'last two completed runs were both unplaced',
            'last two completed runs were both 5th or worse',
            'no placed run in the last three completed starts',
        )
    )

def _has_strong_form_counter_evidence(runner):
    return _strong_consensus(runner) or _rival_overlay_points(runner) >= 6

def _official_candidate(runner):
    bsp = runner.get('bsp')
    field_size = runner.get('field_size', 0)
    form_pattern_profile = _apply_live_form_pattern_profile(runner)
    live_score = float(form_pattern_profile.get('adjusted_score') or runner.get('score') or 0)
    if (
        live_score < 75 or
        bsp is None or
        int(field_size or 0) < 8 or
        runner.get('form_risk')
    ):
        return False

    if form_pattern_profile.get('strength') == 'AVOID':
        runner['form_pattern_block'] = True
        runner['form_confidence_block'] = True
        runner['form_confidence_warning'] = (
            f"Rich form pattern avoid: {runner.get('form', '') or 'unknown'} "
            f"has a historical place rate below 20%"
        )
        return False

    if (
        form_pattern_profile.get('strength') == 'WEAK'
        and _consensus_count(runner) < 3
        and _field_h2h_beaten_count(runner) < 2
    ):
        runner['form_pattern_block'] = True
        runner['form_confidence_block'] = True
        runner['form_confidence_warning'] = (
            f"Rich form pattern weak: {runner.get('form', '') or 'unknown'} "
            "needs 3+ tipsters or 2+ field-rival wins before official selection"
        )
        return False

    price = float(bsp)
    recency_penalty = int(runner.get('recency_form_penalty') or 0)
    if runner.get('memory_context_risk') and _consensus_count(runner) == 0 and float(runner.get('score') or 0) < 90:
        return False

    if _has_severe_recent_form_warning(runner):
        return False

    form_review = _form_gate_review(runner.get('form', ''), runner.get('race_type', 'flat'))
    if form_review.get('code') and form_review.get('passes'):
        runner['formGateWarning'] = True
        runner['formGateReason'] = (
            f"Form warning: {form_review.get('reason')} "
            f"({runner.get('form', '') or 'unknown'})"
        )
        runner['formGateCode'] = form_review.get('code')
        runner['formGatePenalty'] = int(form_review.get('penalty') or 0)
        if (
            form_review.get('code') == 'FORM_GATE_RECENT_WIN_THEN_UNPLACED'
            and not _has_strong_form_counter_evidence(runner)
        ):
            runner['form_confidence_block'] = True
            runner['form_confidence_warning'] = (
                f"Recent form caution: {form_review.get('reason')}; "
                "needs stronger tipster or rival evidence"
            )
            return False
    if not form_review.get('passes'):
        warnings = runner.setdefault('warnings', [])
        reason = form_review.get('reason') or 'poor recent form profile'
        form_string = runner.get('form', '') or 'unknown'
        warning = f"Form gate: {reason} ({form_string})"
        if warning not in warnings:
            warnings.append(warning)
        runner['formGateBlocked'] = True
        runner['formGateReason'] = warning
        runner['formGateCode'] = form_review.get('code')
        return False

    rival_threat = _rival_threat_warning(runner)
    if rival_threat:
        penalty_points = _rival_threat_penalty_points(runner)
        adjusted_score = round(max(0, float(runner.get('score') or 0) - penalty_points), 1)
        runner['rival_threat_penalty'] = {
            'points': penalty_points,
            'adjusted_score': adjusted_score,
            'rivals': rival_threat.get('rivals') or [],
            'source': rival_threat.get('source'),
        }
        runner['live_adjusted_score'] = adjusted_score
        rivals = ', '.join(rival_threat.get('rivals') or []) or 'a rival in today\'s race'
        runner['rival_threat_warning'] = (
            f"Rival threat penalty -{penalty_points}: {rivals} has beaten this horse before"
        )
        if adjusted_score < 75:
            runner['rival_threat_block'] = True
            return False
        if _has_zero_validation_rival_warning(runner):
            runner['zero_validation_rival_warning_block'] = True
            runner['zero_validation_rival_warning'] = (
                "Zero external validation plus a rival warning: no tipsters "
                "and today's field contains a horse that has beaten this runner before"
            )
            return False

    form_confidence = _recent_unplaced_form_live_penalty(runner)
    runner['recent_unplaced_form_penalty'] = form_confidence
    if (
        _has_recent_unplaced_form_pattern(form_confidence)
        and not _has_strong_form_counter_evidence(runner)
        and form_confidence['adjusted_score'] < 78
    ):
        runner['form_confidence_block'] = True
        runner['form_confidence_warning'] = (
            f"Recent form confidence penalty -{form_confidence['points']} "
            f"adjusted score to {form_confidence['adjusted_score']}; "
            "messy recent form needs stronger proof"
        )
        return False

    if form_confidence['points'] >= 7 and not form_confidence['would_clear_live_gate']:
        runner['form_confidence_block'] = True
        runner['form_confidence_warning'] = (
            f"Recent form confidence penalty -{form_confidence['points']} "
            f"adjusted score to {form_confidence['adjusted_score']}"
        )
        return False

    if _strong_consensus(runner):
        return 4.1 <= price <= 8.0

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
        not _has_severe_recent_form_warning(runner)
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
            r.get('live_adjusted_score', r.get('score', 0)),
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

def _graph_evidence_watchlist_candidate(runner):
    return bool(runner.get('graph_evidence_watchlist'))

def _radar_protection_ok(runner):
    """
    Watchlist is not proof, but it is still public-facing.
    Rank horses that pass basic value/field/form protection ahead of horses
    that only look strong because of tips or raw score.
    """
    bsp = runner.get('bsp')
    if bsp is None:
        return False
    return (
        4.1 <= float(bsp) <= 8.0 and
        int(runner.get('field_size') or 0) >= 8 and
        not runner.get('form_risk') and
        not _has_severe_recent_form_warning(runner)
    )

def _radar_sort_key(runner):
    price = float(runner.get('bsp') or 99)
    graph_watch = runner.get('graph_evidence_watchlist') or {}
    return (
        1 if _radar_protection_ok(runner) else 0,
        1 if graph_watch else 0,
        graph_watch.get('graph_score', 0),
        runner.get('score', 0),
        _consensus_count(runner),
        -price,
    )

def pick_radar_watchlist(scored, picked_names=None, picked_market_ids=None, limit=3):
    picked_names = picked_names or set()
    picked_market_ids = picked_market_ids or set()
    candidates = [
        r for r in scored
        if (
            r.get('name') not in picked_names and
            r.get('market_id') not in picked_market_ids and
            (_radar_candidate(r) or _graph_evidence_watchlist_candidate(r))
        )
    ]
    ranked = sorted(candidates, key=_radar_sort_key, reverse=True)
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
    graph_watchlist_count = annotate_graph_evidence_watchlist(scored, get_today())
    if graph_watchlist_count:
        print(f"  Graph evidence watchlist: {graph_watchlist_count} horse(s) marked as evidence-only")

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
        key=_radar_sort_key,
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
    official_bet_summary = build_official_bet_summary(len(flat), len(jumps))

    output = {
        'date': get_today(),
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'mode': mode,
        'betType': official_bet_summary['betType'],
        'totalStake': official_bet_summary['totalStake'],
        'totalBetLines': official_bet_summary['betLines'],
        'officialBetSummary': official_bet_summary,
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
    if not TEST_MODE and output_path == PICKS_JSON:
        write_field_relative_prerace_archive_from_picks(PICKS_JSON)
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
        try:
            field_relative_script = os.path.join(SCRIPTS, "select-field-relative-v1.py")
            field_relative_daily_script = os.path.join(SCRIPTS, "select-field-relative-daily.py")
            subprocess.run([sys.executable, field_relative_script, "--date", get_today()], check=False, timeout=90)
            subprocess.run([sys.executable, field_relative_daily_script, "--date", get_today()], check=False, timeout=30)
        except Exception as exc:
            print(f"  Field-relative analysis skipped: {exc}")
    print("\nDone.")

if __name__ == '__main__':
    main()
