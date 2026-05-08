#!/usr/bin/env python3
"""
fetch-results-betfair.py
Fetches race results from Betfair API and updates picks.json
"""
import json, sys, subprocess
from datetime import datetime

sys.path.insert(0, '/Users/johnhowlett/Signal75/scripts')

PICKS_JSON = '/Users/johnhowlett/Signal75/picks.json'

def get_betfair_key():
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', 'signal75', '-s', 'betfair-session', '-w'],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def main():
    with open(PICKS_JSON) as f:
        picks = json.load(f)

    date = picks.get('date', datetime.now().strftime('%Y-%m-%d'))
    flat_picks = picks.get('flat', [])
    jumps_picks = picks.get('jumps', [])
    all_picks = flat_picks + jumps_picks

    print(f"Fetching results for {date}")
    print(f"Horses to check: {len(all_picks)}")

    try:
        from betfair_client import login_interactive, get_uk_win_markets
        import betfairlightweight

        client = login_interactive()
        if not client:
            print("Could not login to Betfair")
            return

        # Get settled markets from today
        from betfairlightweight import filters
        market_filter = filters.market_filter(
            event_type_ids=['7', '4339'],  # Horse Racing
            market_countries=['GB'],
            market_type_codes=['WIN'],
        )

        markets = client.betting.list_market_catalogue(
            filter=market_filter,
            market_projection=['RUNNER_DESCRIPTION', 'EVENT', 'MARKET_START_TIME'],
            max_results=50
        )

        print(f"Found {len(markets)} markets")

        flat_results = []
        jumps_results = []

        for race_list, result_list in [(flat_picks, flat_results), (jumps_picks, jumps_results)]:
            for race in race_list:
                horse = race['horses'][0] if race.get('horses') else None
                if not horse:
                    result_list.append({'position': 0, 'result': 'PENDING', 'winReturn': 0.0, 'placeReturn': 0.0, 'totalReturn': 0.0})
                    continue

                horse_name = horse['name'].strip().upper()
                found = False

                for market in markets:
                    for runner in market.runners:
                        rname = (runner.runner_name or '').strip().upper()
                        if rname == horse_name or horse_name in rname or rname in horse_name:
                            # Check result
                            status = runner.status if hasattr(runner, 'status') else 'UNKNOWN'
                            sp = runner.sp.actual_sp if hasattr(runner, 'sp') and runner.sp else None

                            if status == 'WINNER':
                                odds = float(horse.get('odds', 0))
                                win_ret = odds * 0.50
                                place_ret = (1 + (odds-1) * 0.25) * 0.50
                                result_list.append({
                                    'position': 1,
                                    'result': 'WON',
                                    'winReturn': round(win_ret, 2),
                                    'placeReturn': round(place_ret, 2),
                                    'totalReturn': round(win_ret + place_ret, 2)
                                })
                            elif status == 'LOSER':
                                result_list.append({'position': 0, 'result': 'LOST', 'winReturn': 0.0, 'placeReturn': 0.0, 'totalReturn': 0.0})
                            elif status == 'REMOVED':
                                result_list.append({'position': 0, 'result': 'NR', 'winReturn': 0.0, 'placeReturn': 0.0, 'totalReturn': 0.0})
                            else:
                                result_list.append({'position': 0, 'result': 'PENDING', 'winReturn': 0.0, 'placeReturn': 0.0, 'totalReturn': 0.0})
                            found = True
                            print(f"  {horse_name}: {status}")
                            break
                    if found:
                        break

                if not found:
                    print(f"  {horse_name}: not found in markets")
                    result_list.append({'position': 0, 'result': 'PENDING', 'winReturn': 0.0, 'placeReturn': 0.0, 'totalReturn': 0.0})

        # Calculate patent
        all_results = flat_results + jumps_results
        complete = all(r['result'] not in ('PENDING',) for r in all_results)
        total_return = sum(r['totalReturn'] for r in all_results)
        patent_profit = round(total_return - 7.0, 2)

        picks['results']['flat'] = flat_results
        picks['results']['jumps'] = jumps_results
        picks['results']['complete'] = complete
        picks['results']['patentReturn'] = round(total_return, 2)
        picks['results']['patentProfit'] = patent_profit

        with open(PICKS_JSON, 'w') as f:
            json.dump(picks, f, indent=2)

        print(f"\nResults saved. Complete: {complete}")
        print(f"Patent return: £{total_return:.2f} | Profit: £{patent_profit:+.2f}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
