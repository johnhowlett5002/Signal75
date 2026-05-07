#!/usr/bin/env python3
"""
betfair_client.py — Signal 75
Isolated Betfair API login and market retrieval.
No scoring logic. No database calls. Pure data retrieval.
"""
import betfairlightweight
from betfairlightweight import filters
from datetime import datetime, timezone

USERNAME = 'john.howlett@madasafish.com'
PASSWORD = 'Mindlessprawn!234'
APP_KEY  = 'MMtmHw3b1lAkKBWf'

def get_client():
    trading = betfairlightweight.APIClient(
        username=USERNAME,
        password=PASSWORD,
        app_key=APP_KEY
    )
    trading.login_interactive()
    return trading

def get_uk_win_markets(trading, hours_ahead=10):
    """Return all UK WIN markets starting within the next N hours."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    to  = now + timedelta(hours=hours_ahead)

    racing_filter = filters.market_filter(
        event_type_ids=['7'],
        market_countries=['GB'],
        market_type_codes=['WIN'],
        market_start_time={
            'from': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'to':   to.strftime('%Y-%m-%dT%H:%M:%SZ')
        }
    )

    markets = trading.betting.list_market_catalogue(
        filter=racing_filter,
        market_projection=[
            'RUNNER_DESCRIPTION',
            'RUNNER_METADATA',
            'MARKET_START_TIME',
            'EVENT',
            'MARKET_DESCRIPTION'
        ],
        max_results=100,
        sort='FIRST_TO_START'
    )
    return markets

def get_market_odds(trading, market_ids):
    """Return live best available odds for a list of market IDs."""
    books = trading.betting.list_market_book(
        market_ids=market_ids,
        price_projection={
            'priceData': ['EX_BEST_OFFERS'],
            'exBestOffersOverrides': {'bestPricesDepth': 1}
        }
    )
    return {b.market_id: b for b in books}

def extract_runners(markets, odds_by_market):
    """
    Return a clean list of races with runners.
    Each race: venue, race_name, race_time, runners[]
    Each runner: name, selection_id, best_back_price, metadata
    """
    races = []
    for m in markets:
        market_id = m.market_id
        race_time = m.market_start_time
        race_name = m.market_name
        venue     = m.event.name if hasattr(m, 'event') and m.event else 'Unknown'

        # Get odds for this market
        book = odds_by_market.get(market_id)
        odds_map = {}
        if book:
            for runner in book.runners:
                if runner.ex and runner.ex.available_to_back:
                    best = runner.ex.available_to_back[0].price
                    odds_map[runner.selection_id] = best

        runners = []
        for r in m.runners:
            meta = r.metadata or {}
            best_price = odds_map.get(r.selection_id)
            runners.append({
                'name':         r.runner_name,
                'selection_id': r.selection_id,
                'best_back':    best_price,
                'jockey':       meta.get('JOCKEY_NAME', ''),
                'trainer':      meta.get('TRAINER_NAME', ''),
                'form':         meta.get('FORM', ''),
                'days_since':   meta.get('DAYS_SINCE_LAST_RUN', ''),
                'age':          meta.get('AGE', ''),
                'weight':       meta.get('WEIGHT_VALUE', ''),
                'official_rating': meta.get('OFFICIAL_RATING', ''),
                'stall_draw':   meta.get('STALL_DRAW', ''),
            })

        races.append({
            'market_id': market_id,
            'venue':     venue,
            'race_name': race_name,
            'race_time': str(race_time),
            'runners':   runners,
            'field_size': len(runners)
        })

    return races

if __name__ == '__main__':
    print("Testing betfair_client.py...")
    trading = get_client()
    print("Login OK")

    markets = get_uk_win_markets(trading)
    print(f"Found {len(markets)} UK WIN markets")

    market_ids = [m.market_id for m in markets]
    odds = get_market_odds(trading, market_ids)

    races = extract_runners(markets, odds)

    for race in races[:3]:
        print(f"\n{race['venue']} — {race['race_name']} — {race['race_time']}")
        print(f"  Field size: {race['field_size']}")
        for r in race['runners'][:3]:
            print(f"  {r['name']} | odds:{r['best_back']} | jockey:{r['jockey']} | form:{r['form']}")

    print("\nbetfair_client.py test complete.")