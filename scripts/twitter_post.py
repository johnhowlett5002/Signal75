#!/usr/bin/env python3
"""
twitter_post.py — Signal 75
Generates tweet text from picks.json for manual or automated posting.
Run at 10am for picks, 7pm for results.
"""
import json, sys
from datetime import datetime

PICKS_JSON = '/Users/johnhowlett/Signal75/picks.json'

def load_picks():
    with open(PICKS_JSON) as f:
        return json.load(f)

def generate_picks_tweet(data):
    """Generate morning picks tweet."""
    mode = data.get('mode', 'noBetDay')
    date = data.get('date', '')
    
    if mode == 'noBetDay':
        return (
            "🔍 Signal 75 scanned today's UK racing\n\n"
            "No horses cleared the Signal 75 threshold today.\n\n"
            "The model only picks when the data says so. No forced selections.\n\n"
            "📊 Results + full proof at signal75.co.uk\n\n"
            "#HorseRacing #UKRacing #Signal75"
        )
    
    flat = data.get('flat', [])
    jumps = data.get('jumps', [])
    all_races = flat + jumps
    
    if not all_races:
        return None
    
    # Get picks
    picks = []
    for race in all_races:
        for h in race.get('horses', []):
            picks.append({
                'name': h['name'],
                'course': race['course'],
                'time': race['time'],
                'odds': h.get('odds', 0),
                'badge': h.get('badge', 'Strong'),
                'score': h.get('signal_score', 0)
            })
    
    if not picks:
        return None
    
    # Badge emoji
    def badge_emoji(badge):
        if 'Banker' in str(badge): return '🔥'
        if 'Strong' in str(badge): return '💪'
        if 'Each' in str(badge) or 'EW' in str(badge): return '🎯'
        return '⚡'
    
    lines = []
    lines.append("🏇 Signal 75 — Today's Patent Picks")
    lines.append("")
    
    for i, p in enumerate(picks[:3], 1):
        odds = p['odds']
        try:
            odds_str = f"@ {float(odds):.1f}"
        except:
            odds_str = f"@ {odds}"
        
        emoji = badge_emoji(p['badge'])
        lines.append(f"{emoji} Leg {i}: {p['name']}")
        lines.append(f"   {p['course']} · {p['time']} · {odds_str}")
    
    lines.append("")
    lines.append("Pick 1 always free 👇")
    lines.append("signal75.co.uk")
    lines.append("")
    lines.append("#HorseRacing #UKRacing #PatentBet #Signal75")
    
    return '\n'.join(lines)

def generate_results_tweet(data):
    """Generate evening results tweet."""
    flat = data.get('flat', [])
    jumps = data.get('jumps', [])
    all_races = flat + jumps
    
    winners = []
    losers = []
    
    for race in all_races:
        for h in race.get('horses', []):
            result = h.get('result', '').upper()
            name = h['name']
            odds = h.get('odds', 0)
            try:
                odds_f = float(odds)
            except:
                odds_f = 0
            
            if result in ('WON', 'WIN', '1ST', 'WINNER'):
                winners.append({'name': name, 'odds': odds_f, 'course': race['course']})
            elif result:
                losers.append({'name': name, 'course': race['course']})
    
    total = len(all_races)
    win_count = len(winners)
    
    lines = []
    lines.append(f"📊 Signal 75 Results — {data.get('date', '')}")
    lines.append("")
    
    if win_count == 3:
        lines.append("🎉 FULL PATENT LANDED!")
        lines.append("")
    elif win_count == 2:
        lines.append("💪 2 from 3 — strong day")
        lines.append("")
    elif win_count == 1:
        lines.append("✅ 1 winner today")
        lines.append("")
    else:
        lines.append("❌ No winners today — full results below")
        lines.append("")
    
    for race in all_races:
        for h in race.get('horses', []):
            result = h.get('result', 'PENDING').upper()
            name = h['name']
            if result in ('WON', 'WIN', '1ST', 'WINNER'):
                lines.append(f"✅ {name} — WON")
            elif result == 'PENDING' or not result:
                lines.append(f"⏳ {name} — result pending")
            else:
                lines.append(f"❌ {name} — {result}")
    
    lines.append("")
    lines.append("Full proof + ROI tracking:")
    lines.append("signal75.co.uk")
    lines.append("")
    lines.append("#HorseRacing #UKRacing #PatentBet #Signal75")
    
    return '\n'.join(lines)

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'picks'
    
    data = load_picks()
    
    if mode == 'results':
        tweet = generate_results_tweet(data)
        print("\n=== RESULTS TWEET ===")
    else:
        tweet = generate_picks_tweet(data)
        print("\n=== PICKS TWEET ===")
    
    if tweet:
        print(tweet)
        print(f"\nCharacter count: {len(tweet)}/280")
        if len(tweet) > 280:
            print("⚠️  WARNING — over 280 characters, needs trimming")
        else:
            print("✅ Within Twitter limit")
    else:
        print("No tweet generated — check picks.json")

if __name__ == '__main__':
    main()
