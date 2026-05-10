#!/usr/bin/env python3
"""
scoring_engine.py — Signal 75
Takes a runner + race context + roi_tables and produces a Signal 75 score.
No Betfair calls. No database calls. Pure scoring logic.
"""
import json
import re

ROI_TABLES = '/Users/johnhowlett/Signal75/data/roi_tables.json'

def load_roi_tables():
    with open(ROI_TABLES) as f:
        return json.load(f)

def parse_race_type(race_name):
    """Parse race type and subtype from Betfair race name."""
    name = race_name.lower()
    if 'hrd' in name or 'hurdle' in name:
        race_type = 'Hurdle'
    elif 'chs' in name or 'chase' in name:
        race_type = 'Chase'
    elif 'nhf' in name or 'bumper' in name:
        race_type = 'Bumper'
    else:
        race_type = 'Flat'

    if 'hcap' in name or 'handicap' in name:
        subtype = 'Handicap'
    elif 'mdn' in name or 'maiden' in name:
        subtype = 'Maiden'
    elif 'nov' in name or 'novice' in name:
        subtype = 'Novice'
    elif 'list' in name:
        subtype = 'Listed'
    elif 'grp' in name or 'gr' in name or 'group' in name:
        subtype = 'Group'
    else:
        subtype = 'Other'

    return race_type, subtype

def get_odds_band(bsp, tables):
    """Return the confidence multiplier for a given BSP."""
    for band_name, band in tables['odds_bands'].items():
        if band['lo'] <= bsp <= band['hi']:
            return band['confidence_multiplier'], band_name
    return 1.0, 'unknown'

def get_race_type_multiplier(race_type, subtype, tables):
    """Return confidence multiplier for race type/subtype."""
    key = f"{race_type} / {subtype}"
    if key in tables['race_types']:
        return tables['race_types'][key]['confidence_multiplier'], key
    return 1.0, key

def get_course_multiplier(venue, tables):
    """Return course personality multiplier."""
    if venue in tables['courses']:
        c = tables['courses'][venue]
        return c['confidence_multiplier'], c['personality']
    return 1.0, 'unknown'

def score_form(form_string):
    """
    Score recent form string from Betfair metadata.
    Looks at last 5 characters for recency.
    """
    if not form_string:
        return 1.0
    recent = form_string.replace('-', '').replace('/', '')[-5:]
    if not recent:
        return 1.0
    score = 0
    weights = [0.1, 0.15, 0.2, 0.25, 0.3]  # most recent weighted highest
    chars = recent[-5:].zfill(5)
    for i, c in enumerate(chars):
        if c == '1':
            score += weights[i] * 1.0
        elif c == '2':
            score += weights[i] * 0.6
        elif c == '3':
            score += weights[i] * 0.3
        elif c == '4':
            score += weights[i] * 0.1
    multiplier = 1.0 + (score * 0.3)
    return round(min(1.20, max(0.90, multiplier)), 4)

def score_days_since_last_run(days_str):
    """Penalise horses returning from very long absences."""
    try:
        days = int(days_str)
        if days <= 14:
            return 1.05   # fresh and fit
        elif days <= 30:
            return 1.02   # normal gap
        elif days <= 60:
            return 0.98   # slightly rusty
        elif days <= 120:
            return 0.95   # long absence
        else:
            return 0.90   # very long absence
    except:
        return 1.0

def score_field_size(field_size):
    """Optimal EW field size is 8-12. Large fields penalised heavily."""
    if 8 <= field_size <= 12:
        return 1.05   # optimal EW structure
    elif 6 <= field_size <= 7:
        return 0.92   # poor EW value in small fields
    elif 13 <= field_size <= 16:
        return 0.97   # acceptable but more chaos
    elif 17 <= field_size <= 19:
        return 0.88   # significant chaos penalty
    elif field_size >= 20:
        return 0.82   # extreme chaos — very strong penalty
    elif field_size < 6:
        return 0.88   # tiny field — poor EW
    else:
        return 1.0

def score_market_confidence(runner_matched, market_matched, field_size):
    """
    Score market confidence from Betfair volume.
    High matched volume relative to field = market support signal.
    """
    if not runner_matched or not market_matched or market_matched == 0:
        return 1.0
    # Runner's share of total market volume
    share = runner_matched / market_matched
    # Expected equal share
    expected = 1.0 / max(field_size, 1)
    # How many times more backed than expected
    ratio = share / expected
    if ratio >= 3.0:
        return 1.08   # heavily backed — strong market signal
    elif ratio >= 2.0:
        return 1.05   # well backed
    elif ratio >= 1.5:
        return 1.02   # slightly preferred
    elif ratio <= 0.3:
        return 0.95   # market ignoring this horse
    else:
        return 1.0    # neutral

def assign_badge(final_score, bsp):
    """Assign Signal 75 badge based on score and odds.
    No Risky badge — if risky it should not qualify.
    """
    if final_score >= 88:
        return 'Banker'
    elif final_score >= 82:
        return 'Strong'
    elif final_score >= 75:
        if bsp and bsp >= 6.0:
            return 'Each Way'
        elif bsp and bsp >= 4.0:
            return 'Value'
        return 'Strong'
    else:
        return None  # below threshold — no badge, Radar only

def score_runner(runner, race, tables):
    """
    Score a single runner.
    Returns score dict with breakdown.
    """
    name = runner['name']
    bsp = runner.get('best_back')
    venue = race['venue'].replace(' 7th May', '').replace(' 8th May', '').strip()
    # Clean venue - remove date suffix
    venue = re.sub(r'\s+\d+\w+\s+\w+$', '', venue).strip()
    race_name = race['race_name']
    field_size = race['field_size']
    history = runner.get('history')

    # Base score — all runners start at 60
    base = 60.0

    # CHESTER DRAW PENALTY — stalls 10+ in fields of 12+ runners
    chester_penalty = 1.0
    stall_draw = runner.get('stall_draw', 0)
    if venue == 'Chester' and field_size >= 12 and stall_draw >= 10:
        chester_penalty = 0.88  # significant draw disadvantage
    elif venue == 'Chester' and field_size >= 16 and stall_draw >= 8:
        chester_penalty = 0.85  # very wide draw in big Chester field

    # 1. Odds band multiplier
    if bsp:
        odds_mult, odds_band = get_odds_band(bsp, tables)
        # Filter: only score horses in 2.1-20.0 range
        if bsp < 2.1 or bsp > 20.0:
            return None  # outside Signal 75 range
    else:
        odds_mult, odds_band = 1.0, 'unknown'
        bsp = None

    # 2. Race type multiplier
    race_type, subtype = parse_race_type(race_name)
    race_mult, race_key = get_race_type_multiplier(race_type, subtype, tables)

    # 3. Course multiplier
    course_mult, course_personality = get_course_multiplier(venue, tables)

    # 4. Horse history multiplier
    if history:
        history_mult = history['history_multiplier']
        # Scale by sample confidence
        sample_conf = history['sample_confidence']
        history_mult = 1.0 + ((history_mult - 1.0) * sample_conf)
    else:
        history_mult = 1.0

    # 5. Form multiplier
    form_mult = score_form(runner.get('form', ''))

    # 6. Days since last run
    days_mult = score_days_since_last_run(runner.get('days_since', ''))

    # 7. Field size
    field_mult = score_field_size(field_size)

    # 8. Market confidence
    market_mult = score_market_confidence(
        runner.get('total_matched', 0),
        runner.get('market_matched', 0),
        field_size
    )

    # Combine all multipliers
    combined = (odds_mult * race_mult * course_mult *
                history_mult * form_mult * days_mult * 
                field_mult * market_mult * chester_penalty)

    final_score = round(base * combined, 1)

    badge = assign_badge(final_score, bsp)

    # PATCH 3 — BSP >12.0 requires higher threshold to qualify
    effective_min_score = 75
    if bsp and bsp > 12.0:
        effective_min_score = 80

    return {
        'name': name,
        'venue': venue,
        'race_name': race_name,
        'race_time': race['race_time'],
        'market_id': race['market_id'],
        'bsp': bsp,
        'field_size': field_size,
        'race_type': race_type,
        'subtype': subtype,
        'score': final_score,
        'badge': badge,
        'qualifies': final_score >= effective_min_score,
        'breakdown': {
            'base': base,
            'odds_band': odds_band,
            'odds_mult': round(odds_mult, 4),
            'race_type': race_key,
            'race_mult': round(race_mult, 4),
            'course': course_personality,
            'course_mult': round(course_mult, 4),
            'history_mult': round(history_mult, 4),
            'form_mult': round(form_mult, 4),
            'days_mult': round(days_mult, 4),
            'field_mult': round(field_mult, 4),
            'market_mult': round(market_mult, 4),
            'chester_penalty': round(chester_penalty, 4),
            'combined': round(combined, 4),
        },
        'jockey': runner.get('jockey', ''),
        'trainer': runner.get('trainer', ''),
        'form': runner.get('form', ''),
        'history': history,
    }

def score_all_runners(races, tables):
    """Score every runner in every qualifying race."""
    all_scored = []
    for race in races:
        if race['field_size'] < 5:
            continue  # skip tiny fields
        for runner in race['runners']:
            result = score_runner(runner, race, tables)
            if result:
                all_scored.append(result)

    # Sort by score descending
    all_scored.sort(key=lambda x: x['score'], reverse=True)
    return all_scored

def select_picks(scored_runners, max_picks=3, min_score=75, min_radar_score=65):
    """
    Select top picks ensuring different races.
    Radar is a fallback — max 3 horses, min score 65, different races.
    Radar purpose changes by mode:
      qualified — horses that nearly qualified (score 65-74)
      topRatedOnly — next best horses after partial picks
      noBetDay — top 3 horses as consolation
    Returns qualified picks and radar horses.
    """
    picks = []
    used_markets = set()

    for runner in scored_runners:
        if runner['score'] >= min_score:
            if runner['market_id'] not in used_markets:
                picks.append(runner)
                used_markets.add(runner['market_id'])
        if len(picks) >= max_picks:
            break

    # Radar — top 3 only, from different races, min score 65
    # Never includes qualified picks
    # On qualified days: only show horses scoring 65-74 (near misses)
    # On lean days: show top scoring horses regardless
    radar = []
    radar_markets = set()
    pick_markets = set(p['market_id'] for p in picks)

    qualified_day = len(picks) >= max_picks

    for runner in scored_runners:
        # Never duplicate a pick
        if runner in picks:
            continue
        # Must meet minimum radar score
        if runner['score'] < min_radar_score:
            continue
        # Must be from a different race to existing radar entries
        if runner['market_id'] in radar_markets:
            continue
        # On a fully qualified day — only show near misses (65-74)
        # to protect the integrity of the qualified picks
        if qualified_day and runner['score'] >= min_score:
            continue
        radar.append(runner)
        radar_markets.add(runner['market_id'])
        if len(radar) >= 3:
            break

    return picks, radar

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/Users/johnhowlett/Desktop')

    print("Testing scoring_engine.py...")
    tables = load_roi_tables()
    print(f"ROI tables loaded: {len(tables['horse_profiles']):,} profiles")

    # Import betfair_client and runner_matcher
    from betfair_client import get_client, get_uk_win_markets, get_market_odds, extract_runners
    from runner_matcher import load_profiles, enrich_runners

    trading = get_client()
    markets = get_uk_win_markets(trading)
    print(f"Markets: {len(markets)}")

    market_ids = [m.market_id for m in markets]
    odds = get_market_odds(trading, market_ids)
    races = extract_runners(markets, odds)

    profiles = load_profiles()
    races = enrich_runners(races, profiles)

    scored = score_all_runners(races, tables)
    print(f"\nScored {len(scored)} runners")

    picks, radar = select_picks(scored)

    print(f"\n=== SIGNAL 75 PICKS ===")
    if picks:
        for i, p in enumerate(picks, 1):
            print(f"\nPick {i}: {p['name']} — {p['venue']} {p['race_name']} @ {p['race_time']}")
            print(f"  Score: {p['score']} | Badge: {p['badge']} | BSP: {p['bsp']}")
            print(f"  Form: {p['form']} | Jockey: {p['jockey']}")
            print(f"  Breakdown: {p['breakdown']}")
            if p['history']:
                print(f"  History: {p['history']['runs']} runs, {p['history']['wins']} wins, {p['history']['win_rate']}% WR")
    else:
        print("No picks qualified at score >= 75")

    print(f"\n=== RADAR (top {len(radar)}) ===")
    for r in radar:
        print(f"  {r['name']} — {r['venue']} — score:{r['score']} bsp:{r['bsp']}")

    print("\nscoring_engine.py test complete.")