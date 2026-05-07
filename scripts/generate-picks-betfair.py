#!/usr/bin/env python3
"""
generate-picks-betfair-v2.py — Signal 75
Betfair API picks generator — exact picks.json format match.
TEST MODE only — writes picks_test.json, never touches picks.json
"""
import json, os, sys, subprocess, re
from datetime import datetime, timezone, timedelta

SCRIPTS = '/Users/johnhowlett/Signal75/scripts'
ENGINE  = '/Users/johnhowlett/Desktop/Signal75-Engine'
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, ENGINE)

TEST_OUTPUT = '/Users/johnhowlett/Desktop/Signal75-Engine/picks_test_v2.json'
PICKS_JSON  = '/Users/johnhowlett/Signal75/picks.json'
TEST_MODE   = False
ROI_TABLES  = '/Users/johnhowlett/Desktop/Signal75-Engine/roi_tables.json'

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

def get_anthropic_key():
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', 'signal75', '-s', 'anthropic-api-key', '-w'],
        capture_output=True, text=True
    )
    return result.stdout.strip()

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
    """Build a race entry in exact picks.json format."""
    horse = {
        'num': 0,
        'name': pick['name'].upper(),
        'jockey': pick['jockey'],
        'trainer': pick['trainer'],
        'odds': round(pick['bsp'], 2) if pick['bsp'] else 0,
        'prevOdds': round(pick['bsp'], 2) if pick['bsp'] else 0,
        'tipsters': 3,
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
        'position': 0
    }
    race = {
        'time': format_time_uk(pick['race_time']),
        'course': pick['venue'],
        'type': pick['race_type'].lower(),
        'distance': get_distance(pick['race_name']),
        'going': 'good',
        'runners': pick['field_size'],
        'horses': [horse]
    }
    return race

def main():
    print("Signal 75 — Betfair picks generator v2")
    print(f"Date: {get_today()}")
    print(f"Output: {TEST_OUTPUT}")
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
    print(f"  {len(scored)} runners scored")

    # Step 4 — Select
    print("Step 4: Selecting picks...")
    picks, radar = select_picks(scored)
    print(f"  Picks: {len(picks)} | Radar: {len(radar)}")

    if len(picks) == 0:
        mode = 'noBetDay'
    elif len(picks) < 3:
        mode = 'topRatedOnly'
    else:
        mode = 'qualified'
    print(f"  Mode: {mode}")

    # Step 5 — Build output
    print("Step 5: Generating explanations and building output...")
    flat = []
    jumps = []

    for i, pick in enumerate(picks):
        explanation = generate_explanation(pick)
        print(f"  ✅ {pick['name']} — score:{pick['score']} — {explanation[:50]}...")
        race_entry = build_race_entry(pick, explanation)
        if pick['race_type'] == 'Flat':
            flat.append(race_entry)
        else:
            jumps.append(race_entry)

    # Radar
    radar_cards = []
    for r in radar:
        radar_cards.append({
            'name': r['name'],
            'race': r['race_name'],
            'venue': r['venue'],
            'time': format_time_uk(r['race_time']),
            'signal_score': int(r['score']),
            'odds': f"{r['bsp']:.1f}" if r['bsp'] else 'N/A',
            'form': r['form'],
            'radarResult': '',
        })

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
        'results': {
            'flat': [],
            'jumps': [],
            'patentReturn': 0,
            'patentProfit': 0,
            'complete': False
        },
        'source': 'betfair_api'
    }

    # Write to correct output
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
        print(f"  {h['name']} — {entry['course']} {entry['time']} — score:{h['signal_score']} odds:{h['odds']}")
    print(f"\nRadar: {[r['name'] for r in radar_cards]}")
    print("\nDone. Review picks_test_v2.json before going live.")

if __name__ == '__main__':
    main()