#!/usr/bin/env python3
"""
runner_matcher.py — Signal 75
Matches today's Betfair runners to historical horse profiles.
Returns profile or None. Never crashes. Never blocks a pick.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROI_TABLES = REPO / 'data' / 'roi_tables.json'

def load_profiles():
    with open(ROI_TABLES) as f:
        data = json.load(f)
    return data['horse_profiles']

def normalise(name):
    """Normalise horse name for matching."""
    name = name.strip().lower()
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name

def match_runner(name, profiles, normalised_index):
    """
    Match a runner name to historical profiles.
    Returns profile dict or None.
    """
    key = normalise(name)
    if key in normalised_index:
        original = normalised_index[key]
        return profiles[original]
    return None

def build_index(profiles):
    """Build normalised name -> original name index."""
    index = {}
    for name in profiles:
        norm = normalise(name)
        index[norm] = name
    return index

def enrich_runners(races, profiles):
    """
    Add historical profile data to each runner in each race.
    Modifies races in place.
    """
    index = build_index(profiles)
    matched = 0
    total = 0

    for race in races:
        for runner in race['runners']:
            total += 1
            profile = match_runner(runner['name'], profiles, index)
            if profile:
                matched += 1
                runner['history'] = profile
            else:
                runner['history'] = None

    print(f"Runner matching: {matched}/{total} matched ({matched/total*100:.1f}%)")
    return races

if __name__ == '__main__':
    print("Testing runner_matcher.py...")

    # Load profiles
    profiles = load_profiles()
    print(f"Loaded {len(profiles):,} horse profiles")

    # Test with sample runners from betfair_client
    test_runners = [
        'Roman Dragon',
        'Harry Skelton',
        'Oisin Murphy',
        'Spioradalta',
        'Crowd Quake',
        'Yorkshire Glory',
    ]

    index = build_index(profiles)
    for name in test_runners:
        profile = match_runner(name, profiles, index)
        if profile:
            print(f"  MATCHED {name}: {profile['runs']} runs, {profile['wins']} wins, "
                  f"{profile['win_rate']}% WR, avg BSP {profile['avg_bsp']}, "
                  f"multiplier {profile['history_multiplier']}")
        else:
            print(f"  NO MATCH: {name}")

    print("\nrunner_matcher.py test complete.")
