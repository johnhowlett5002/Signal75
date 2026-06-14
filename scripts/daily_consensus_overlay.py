#!/usr/bin/env python3
"""
daily_consensus_overlay.py — Signal 75
Fetches public tipster/consensus data using Anthropic web search and
matches ONLY against today's Betfair runners.

Design rules:
- NEVER blocks picks.json generation
- Tipster consensus supports Signal 75; it is not a hard gate
- NEVER replaces the core scoring engine
- Exact consensus overlay: 0, 4, 8, 12, 16, or 20 points
- Fails safely and silently if anything goes wrong
"""
import json, re, os, subprocess
from datetime import datetime

DATA_DIR = '/Users/johnhowlett/Signal75/data'
os.makedirs(DATA_DIR, exist_ok=True)

RUNNERS_CACHE = '/Users/johnhowlett/Signal75/data/today_runners.json'
CONFIRMED_TIPS_TEMPLATE = '/Users/johnhowlett/Signal75/data/confirmed_tips_{}.json'
SYSTEM_CONFIG = '/Users/johnhowlett/Signal75/data/system_config.json'
SOURCES = [
    'RacingPost', 'RacingPost NAPs', 'RacingPost Spotlight', 'RacingPost Postdata',
    'RacingPost Newmarket', 'Racing Post Press Challenge',
    'SportingLife', 'SportingLife NAPs', 'SportingLife Ben Linfoot', 'SportingLife David Ord',
    'Timeform', 'AtTheRaces', 'AtTheRaces Verdict', 'RacingTV',
    'The Sun Templegate', 'Daily Mirror Newsboy', 'Daily Mail Robin Goodfellow',
    'Telegraph Marlborough', 'The Times Rob Wright', 'Daily Express Garry Biggs',
    'Daily Express Melissa Jones', 'Morning Star Farringdon', 'Ipswich Star Matt Polley',
    'Yorkshire Evening Post Lee Sobot', 'Daily Record Garry Owen', 'Sunday Mail Rockavon',
    'HorseRacingNet NAPs', 'BetHQ NAPs', 'Oddschecker', 'OLBG', 'GG',
    'Betfred Insights', 'Betfair Tips', 'FreeBets', 'RacingTips', 'Tipstrr', 'Punters Lounge'
]

RACE_CONSENSUS_LIMIT = int(os.environ.get('SIGNAL75_RACE_CONSENSUS_LIMIT', '20'))
RACE_CONSENSUS_MAX_WEB_USES = int(os.environ.get('SIGNAL75_RACE_CONSENSUS_MAX_WEB_USES', '1'))
DIRECT_CONSENSUS_LIMIT = int(os.environ.get('SIGNAL75_DIRECT_CONSENSUS_LIMIT', '10'))
DIRECT_CONSENSUS_MAX_WEB_USES = int(os.environ.get('SIGNAL75_DIRECT_CONSENSUS_MAX_WEB_USES', '2'))
DIRECT_CONSENSUS_ONLY = os.environ.get('SIGNAL75_DIRECT_CONSENSUS_ONLY', '1').strip() != '0'

SOURCE_ALIASES = {
    'racing post': 'RacingPost',
    'racingpost': 'RacingPost',
    'the racing post': 'RacingPost',
    'racingpost.com': 'RacingPost',
    'racing post naps': 'RacingPost',
    'racing post naps table': 'RacingPost',
    'racing post postdata': 'RacingPost',
    'postdata': 'RacingPost',
    'spotlight': 'RacingPost',
    'sporting life': 'SportingLife',
    'sportinglife': 'SportingLife',
    'sportinglife.com': 'SportingLife',
    'sporting life naps': 'SportingLife',
    'sporting life naps table': 'SportingLife',
    'ben linfoot': 'SportingLife',
    'david ord': 'SportingLife',
    'timeform': 'Timeform',
    'timeform.com': 'Timeform',
    'at the races': 'AtTheRaces',
    'attheraces': 'AtTheRaces',
    'at the races verdict': 'AtTheRaces',
    'atr verdict': 'AtTheRaces',
    'attheraces.com': 'AtTheRaces',
    'racing tv': 'RacingTV',
    'racingtv': 'RacingTV',
    'racingtv.com': 'RacingTV',
    'betfred': 'BetfredInsights',
    'betfred insights': 'BetfredInsights',
    'betfredinsights.com': 'BetfredInsights',
    'freebets': 'FreeBets',
    'free bets': 'FreeBets',
    'freebets.com': 'FreeBets',
    'oddschecker': 'Oddschecker',
    'oddschecker.com': 'Oddschecker',
    'olbg': 'OLBG',
    'olbg.com': 'OLBG',
    'myracing': 'MyRacing',
    'my racing': 'MyRacing',
    'myracing.com': 'MyRacing',
    'gg': 'GG',
    'gg racing': 'GG',
    'ggracing': 'GG',
    'ggcouk': 'GG',
    'gg.co.uk': 'GG',
    'gg racing tips': 'GG',
    'horse racing net': 'HorseRacingNet',
    'horseracing.net': 'HorseRacingNet',
    'horseracingnet': 'HorseRacingNet',
    'bethq': 'BetHQ',
    'bethq naps': 'BetHQ',
    'bet hq': 'BetHQ',
    'betfair tips': 'BetfairTips',
    'betfair articles': 'BetfairTips',
    'betfair': 'BetfairTips',
    'racingtips': 'RacingTips',
    'racing tips': 'RacingTips',
    'tipstrr': 'Tipstrr',
    'punters lounge': 'PuntersLounge',
    'punterslounge': 'PuntersLounge',
    'daily mail': 'DailyMail',
    'dailymail': 'DailyMail',
    'mail': 'DailyMail',
    'dailymail.co.uk': 'DailyMail',
    'daily mirror': 'DailyMirror',
    'dailymirror': 'DailyMirror',
    'mirror': 'DailyMirror',
    'mirror.co.uk': 'DailyMirror',
    'the sun': 'TheSun',
    'thesun': 'TheSun',
    'sun': 'TheSun',
    'thesun.co.uk': 'TheSun',
    'the telegraph': 'Telegraph',
    'daily telegraph': 'Telegraph',
    'telegraph': 'Telegraph',
    'telegraph.co.uk': 'Telegraph',
    'the times': 'TheTimes',
    'thetimes': 'TheTimes',
    'thetimes.co.uk': 'TheTimes',
    'racing post spotlight': 'RacingPost',
    'sporting life naps': 'SportingLife',
    'daily mail robin goodfellow': 'DailyMail',
    'robin goodfellow': 'DailyMail',
    'daily mirror newsboy': 'DailyMirror',
    'newsboy': 'DailyMirror',
    'the sun templegate': 'TheSun',
    'templegate': 'TheSun',
    'telegraph marlborough': 'Telegraph',
    'marlborough': 'Telegraph',
    'the times rob wright': 'TheTimes',
    'rob wright': 'TheTimes',
    'daily express': 'DailyExpress',
    'dailyexpress': 'DailyExpress',
    'express': 'DailyExpress',
    'dailyexpress.co.uk': 'DailyExpress',
    'garry biggs': 'DailyExpress',
    'melissa jones': 'DailyExpress',
    'morning star': 'MorningStar',
    'morningstar': 'MorningStar',
    'farringdon': 'MorningStar',
    'ipswich star': 'IpswichStar',
    'ipswichstar': 'IpswichStar',
    'matt polley': 'IpswichStar',
    'yorkshire evening post': 'YorkshireEveningPost',
    'yep': 'YorkshireEveningPost',
    'lee sobot': 'YorkshireEveningPost',
    'daily record': 'DailyRecord',
    'dailyrecord': 'DailyRecord',
    'garry owen': 'DailyRecord',
    'sunday mail': 'SundayMail',
    'sundaymail': 'SundayMail',
    'rockavon': 'SundayMail',
    'guardian': 'Guardian',
    'the guardian': 'Guardian',
    'betfair/timeform': 'Timeform',
    'betfair timeform': 'Timeform',
    'tipster consensus': 'TipsterConsensus',
    'national tipsters': 'TipsterConsensus',
    'daily racing press': 'TipsterConsensus',
    'press consensus': 'TipsterConsensus',
    'major tipster leaderboards': 'TipsterConsensus',
}

SOURCE_TIERS = {
    'RacingPost': 1,
    'SportingLife': 1,
    'Timeform': 1,
    'AtTheRaces': 1,
    'RacingTV': 1,
    'DailyMail': 2,
    'DailyMirror': 2,
    'TheSun': 2,
    'Telegraph': 2,
    'TheTimes': 2,
    'DailyExpress': 2,
    'MorningStar': 2,
    'IpswichStar': 2,
    'YorkshireEveningPost': 2,
    'DailyRecord': 2,
    'SundayMail': 2,
    'Guardian': 2,
    'HorseRacingNet': 3,
    'BetHQ': 3,
    'OLBG': 4,
    'Oddschecker': 4,
    'MyRacing': 4,
    'GG': 4,
    'BetfredInsights': 4,
    'BetfairTips': 4,
    'FreeBets': 4,
    'RacingTips': 4,
    'Tipstrr': 4,
    'PuntersLounge': 4,
    'TipsterConsensus': 3,
}

SOURCE_WEIGHTS = {
    1: 2.0,
    2: 1.5,
    3: 1.0,
    4: 0.5,
    5: 0.0,
}

SOURCE_RANK_ORDER = {
    'RacingPost': 1,
    'SportingLife': 2,
    'Timeform': 3,
    'AtTheRaces': 4,
    'RacingTV': 5,
    'TheSun': 6,
    'DailyMirror': 7,
    'DailyMail': 8,
    'Telegraph': 9,
    'TheTimes': 10,
    'DailyExpress': 11,
    'MorningStar': 12,
    'IpswichStar': 13,
    'YorkshireEveningPost': 14,
    'DailyRecord': 15,
    'SundayMail': 16,
    'Guardian': 17,
    'HorseRacingNet': 18,
    'BetHQ': 19,
    'Oddschecker': 20,
    'OLBG': 21,
    'GG': 22,
    'BetfredInsights': 23,
    'BetfairTips': 24,
    'FreeBets': 25,
    'RacingTips': 26,
    'Tipstrr': 27,
    'PuntersLounge': 28,
    'MyRacing': 29,
    'TipsterConsensus': 30,
}

DEFAULT_TRUSTED_SOURCES = {
    'Timeform', 'RacingPost', 'SportingLife',
    'AtTheRaces', 'RacingTV', 'BetfredInsights',
    'OLBG', 'MyRacing', 'Oddschecker', 'GG',
    'DailyMail', 'DailyMirror', 'TheSun',
    'Telegraph', 'TheTimes', 'DailyExpress', 'MorningStar',
    'IpswichStar', 'YorkshireEveningPost', 'DailyRecord',
    'SundayMail', 'Guardian', 'HorseRacingNet', 'BetHQ',
    'FreeBets', 'BetfairTips', 'RacingTips', 'Tipstrr',
    'PuntersLounge', 'TipsterConsensus',
}


def load_trusted_sources():
    try:
        with open(SYSTEM_CONFIG) as f:
            cfg = json.load(f)
        sources = cfg.get('trusted_tipster_sources')
        if isinstance(sources, list) and sources:
            return set(str(x).strip() for x in sources if str(x).strip())
    except Exception:
        pass
    return DEFAULT_TRUSTED_SOURCES


TRUSTED_SOURCES = load_trusted_sources()


def get_anthropic_key():
    env_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if env_key:
        return env_key
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', 'signal75', '-s', 'anthropic-api-key', '-w'],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def normalise(name):
    name = name.strip().lower()
    name = re.sub(r"['\u2019\-\(\)]", '', name)
    name = re.sub(r'[^a-z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def normalise_source(name):
    clean = str(name).strip()
    return SOURCE_ALIASES.get(clean.lower(), clean)


def source_tier(source):
    return SOURCE_TIERS.get(normalise_source(source), 5)


def source_weight(source):
    return SOURCE_WEIGHTS.get(source_tier(source), 0.0)


def source_sort_key(source):
    normalised = normalise_source(source)
    return (source_tier(normalised), SOURCE_RANK_ORDER.get(normalised, 999), normalised)


def ranked_sources(sources):
    return sorted(set(sources or []), key=source_sort_key)


def support_level(weighted_score):
    score = safe_float(weighted_score) or 0.0
    if score >= 5.0:
        return 'very_strong'
    if score >= 3.0:
        return 'strong'
    if score >= 1.5:
        return 'useful'
    if score >= 0.5:
        return 'weak'
    return 'none'


def ranking_adjustment(tip):
    ranking = tip.get('ranking_data') or {}
    adjustment = 0.0
    rank = safe_tip_count(ranking.get('rank_position'))
    if rank and rank <= 5:
        adjustment += 1.0
    elif rank and rank <= 10:
        adjustment += 0.75

    profit_loss = ranking.get('profit_loss')
    if profit_loss not in (None, ''):
        text = str(profit_loss).lower()
        value = safe_float(re.sub(r'[^0-9\.\-]', '', text))
        if value is not None:
            adjustment += 0.5 if value > 0 else (-0.25 if value < 0 else 0.0)
        elif 'positive' in text or 'profit' in text:
            adjustment += 0.5
        elif 'negative' in text or 'loss' in text:
            adjustment -= 0.25

    tip_type = str(tip.get('tip_type') or '').lower()
    notes = ' '.join(str(x) for x in (tip.get('notes') or [])) if isinstance(tip.get('notes'), list) else str(tip.get('notes') or '')
    notes = notes.lower()
    if tip.get('is_nap') is True or 'nap' in tip_type or re.search(r'\bnap\b', notes):
        adjustment += 0.75
    elif tip.get('is_nb') is True or tip_type in ('nb', 'next best') or 'next best' in notes:
        adjustment += 0.25
    return adjustment


def extract_json_payload(text):
    """Return the first JSON object containing tips, even if the model adds text."""
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != '{':
            continue
        try:
            payload, _ = decoder.raw_decode(text[idx:])
        except Exception:
            continue
        if isinstance(payload, dict) and 'tips' in payload:
            return payload
    return None


def safe_tip_count(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = re.search(r'\d+', str(value))
    return max(0, int(match.group(0))) if match else 0



def safe_float(value):
    try:
        if value in (None, ''):
            return None
        return float(value)
    except Exception:
        return None


def clean_course(course):
    course = str(course or '').strip()
    course = re.sub(r'\s+\d{1,2}(?:st|nd|rd|th)\s+\w+$', '', course, flags=re.I)
    return course.strip()


def display_race_time(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo:
            return dt.astimezone().strftime('%H:%M')
        return dt.strftime('%H:%M')
    except Exception:
        pass
    match = re.search(r'\b(\d{1,2}:\d{2})\b', raw)
    return match.group(1) if match else raw


def load_runner_races(betfair_runners=None):
    if os.path.exists(RUNNERS_CACHE):
        try:
            with open(RUNNERS_CACHE) as f:
                data = json.load(f)
            races = []
            for race in data.get('races', []):
                raw_runners = race.get('runners') or []
                runners = []
                for runner in raw_runners:
                    runners.append({
                        'name': runner.get('name', ''),
                        'price': safe_float(runner.get('best_back') or runner.get('bsp')),
                        'score': safe_float(runner.get('score')),
                        'jockey': runner.get('jockey', ''),
                        'trainer': runner.get('trainer', ''),
                    })
                races.append({
                    'market_id': race.get('market_id', ''),
                    'course': clean_course(race.get('venue', '')),
                    'time': display_race_time(race.get('race_time', '')),
                    'race_name': race.get('race_name', ''),
                    'field_size': race.get('field_size') or len(runners),
                    'market_total_matched': safe_float((raw_runners[:1] or [{}])[0].get('market_total_matched')) or 0,
                    'runners': runners,
                })
            return races
        except Exception as e:
            print(f"  Race cache failed: {e}")

    grouped = {}
    for runner in (betfair_runners or {}).values():
        market_id = runner.get('market_id') or f"{runner.get('course','')}|{runner.get('time','')}"
        grouped.setdefault(market_id, {
            'market_id': market_id,
            'course': clean_course(runner.get('course', '')),
            'time': display_race_time(runner.get('time', '')),
            'race_name': runner.get('race_name', ''),
            'field_size': 0,
            'market_total_matched': safe_float(runner.get('market_total_matched')) or 0,
            'runners': [],
        })
        grouped[market_id]['runners'].append({
            'name': runner.get('betfair_name') or runner.get('name', ''),
            'price': safe_float(runner.get('best_back') or runner.get('bsp')),
            'score': safe_float(runner.get('score')),
            'jockey': runner.get('jockey', ''),
            'trainer': runner.get('trainer', ''),
        })
    for race in grouped.values():
        race['field_size'] = len(race['runners'])
    return list(grouped.values())

def load_betfair_runners(betfair_runners=None):
    if betfair_runners:
        return betfair_runners

    if os.path.exists(RUNNERS_CACHE):
        try:
            with open(RUNNERS_CACHE) as f:
                data = json.load(f)
            runners = {}
            for race in data.get('races', []):
                for r in race.get('runners', []):
                    norm = normalise(r['name'])
                    runners[norm] = {
                        'betfair_name': r['name'],
                        'course': clean_course(race.get('venue', '')),
                        'time': display_race_time(race.get('race_time', '')),
                        'race_name': race.get('race_name', ''),
                        'field_size': race.get('field_size') or len(race.get('runners', [])),
                        'market_id': race.get('market_id', ''),
                        'best_back': r.get('best_back'),
                        'market_total_matched': r.get('market_total_matched'),
                    }
            print(f"  Loaded {len(runners)} runners from cache")
            return runners
        except Exception as e:
            print(f"  Runner cache failed: {e}")

    return {}


def build_runner_text(betfair_runners):
    runner_lines = []
    for v in betfair_runners.values():
        runner_lines.append(f"{v['betfair_name']} | {v.get('course','')} | {v.get('time','')}")
    return "\n".join(runner_lines[:350])


def build_targeted_prompts(date_str, names_text):
    return [
        (
            'national racing publications',
            (
                f"Today is {date_str}. Search ONLY these specific websites for today's UK horse racing NAPs and tips:\n"
                f"- sportinglife.com/racing/tips (Ben Linfoot NAP)\n"
                f"- racingpost.com/horse-racing-tips/naps-table\n"
                f"- timeform.com racing tips today\n"
                f"- attheraces.com/tips\n"
                f"- racingtv.com tips today\n\n"
                f"Return only horses from these exact sites that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["RacingPost"],"tipsters":["Spotlight"],"notes":["brief evidence"]}}]}}'
            ),
            5,
        ),
        (
            'newspaper named tipsters',
            (
                f"Today is {date_str}. Search for today's NAP selections from ONLY these named newspaper tipsters:\n"
                f"- Robin Goodfellow at dailymail.co.uk\n"
                f"- Templegate at thesun.co.uk\n"
                f"- Newsboy at mirror.co.uk\n"
                f"- Marlborough at telegraph.co.uk\n"
                f"- Rob Wright at thetimes.co.uk\n"
                f"- Garry Biggs or Melissa Jones at express.co.uk\n"
                f"- Farringdon at morningstaronline.co.uk\n"
                f"- Matt Polley at ipswichstar.co.uk\n"
                f"- Lee Sobot at yorkshireeveningpost.co.uk\n"
                f"- Garry Owen at dailyrecord.co.uk\n"
                f"- Rockavon at sundaymail.co.uk\n\n"
                f"Return only horses from these named tipsters that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["DailyMail"],"tipsters":["Robin Goodfellow"],"tip_type":"NAP","is_nap":true,"notes":["NAP"]}}]}}'
            ),
            5,
        ),
        (
            'ranked naps and performance tables',
            (
                f"Today is {date_str}. Search ONLY reputable NAP tables or tipster performance pages for today's UK racing tips:\n"
                f"- racingpost.com NAPs table\n"
                f"- sportinglife.com NAPs table\n"
                f"- horseracing.net NAPs table or tipster stats\n"
                f"- bethq.com NAPs or tipster rankings\n\n"
                f"Only use ranking, P/L, strike-rate, or table position if it is visible. Do not invent it.\n"
                f"Return only horses that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["HorseRacingNet"],"tipsters":["Tipster name"],"tip_type":"NAP","is_nap":true,"ranking_data":{{"rank_position":5,"profit_loss":"+12.00","strike_rate":null,"sample_size":null}},"notes":["ranked NAP table"]}}]}}'
            ),
            5,
        ),
        (
            'commercial and community sources',
            (
                f"Today is {date_str}. Search ONLY these sites for today's UK horse racing tips and most-tipped horses:\n"
                f"- olbg.com/betting-tips/Horse_Racing\n"
                f"- oddschecker.com horse racing tips\n"
                f"- betfredinsights.com today\n\n"
                f"- betfair.com tips/articles\n"
                f"- freebets.com racing tips\n"
                f"- racingtips.com today\n"
                f"- tipstrr.com racing tips\n"
                f"- punterslounge.com racing tips\n"
                f"These are weaker Tier 4 sources, so only return clear named selections or visible tip counts.\n\n"
                f"Return only horses that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["OLBG"],"tipsters":["OLBG"],"notes":["most tipped"]}}]}}'
            ),
            5,
        ),
        (
            'GG Racing tip counts',
            (
                f"Today is {date_str}. Search ONLY gg.co.uk for today's UK horse racing racecards, tips, "
                f"most-tipped horses, and visible tip counts.\n\n"
                f"Important: if GG shows a horse has '3 tips', '4 tips', or similar, return that number in tip_count. "
                f"Do not invent named tipsters. Use sources ['GG'] and notes like ['3 tips on GG racecard'].\n\n"
                f"Return only horses that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["GG"],"tip_count":3,"tipsters":[],"notes":["3 tips on GG racecard"]}}]}}'
            ),
            6,
        ),
    ]


def build_fallback_prompt(date_str, names_text):
    return (
        f"Today is {date_str}. You must find UK horse racing tips for TODAY only. "
        f"Search official and reputable UK racing tip sources, but keep the search concise. "
        f"Prioritise: Sporting Life/NAPs/Ben Linfoot, Racing Post Spotlight/Newmarket/Press Challenge, "
        f"Timeform, At The Races, Racing TV, ranked NAP tables, Betfred Insights, Oddschecker, OLBG, GG, "
        f"and named newspaper tipsters Robin Goodfellow, Newsboy, Templegate, Marlborough, Rob Wright, "
        f"Garry Biggs, Melissa Jones, Farringdon, Matt Polley, Lee Sobot, Garry Owen, Rockavon, "
        f"and other named newspaper naps from the trusted list. "
        f"Extract every named selection, including NAPs, next-best, value bets, lucky 15, spotlight, eyecatcher, next race tip, and best bets. "
        f"Count named tipsters/columns separately: examples include Racing Post Spotlight, Robin Goodfellow, Newsboy, Newmarket, "
        f"Ben Linfoot, David Ord, Timeform, Oddschecker, At The Races Verdict, Templegate, "
        f"Marlborough, Rob Wright, GG, Racing TV pundits, ranked NAP tables, and newspaper naps from the trusted list. "
        f"Then match ONLY against this exact Betfair runner list, using horse name plus time/course where possible:\n\n{names_text}\n\n"
        f"Return ONLY valid JSON. No explanation. Format exactly: "
        f'{{"tips":[{{"horse":"EXACT NAME FROM LIST","sources":["RacingPost"],"tipsters":["Spotlight","Robin Goodfellow"],"notes":["brief evidence"]}}]}}. '
        f"If a horse appears from multiple named tipsters on the same site, include each named tipster separately in tipsters. "
        f"Use exact horse names from the runner list. If no tips found, return {{\"tips\":[]}}."
    )




def runner_price(info):
    return safe_float(info.get('bsp') or info.get('best_back') or info.get('price') or info.get('odds'))


def signal_shortlist_for_direct_consensus(betfair_runners):
    candidates = []
    for norm, info in (betfair_runners or {}).items():
        score = safe_float(info.get('score'))
        price = runner_price(info)
        field_size = safe_float(info.get('field_size')) or 0
        qualifies = info.get('qualifies') is True
        if score is None:
            continue
        value_band = price is not None and 2.75 <= price <= 8.0
        official_band = price is not None and 4.1 <= price <= 6.0
        if score < 70 or not value_band or field_size < 8:
            continue
        candidates.append((
            norm,
            info,
            (
                1 if qualifies else 0,
                1 if official_band else 0,
                score,
                0 - abs((price or 5.0) - 5.0),
            ),
        ))

    candidates.sort(key=lambda item: item[2], reverse=True)
    if DIRECT_CONSENSUS_LIMIT <= 0:
        return []
    return candidates[:DIRECT_CONSENSUS_LIMIT]


def build_direct_horse_consensus_prompt(date_str, runner_info):
    horse = runner_info.get('betfair_name') or runner_info.get('name') or ''
    course = clean_course(runner_info.get('course', ''))
    time = display_race_time(runner_info.get('time', ''))
    race_name = runner_info.get('race_name', '')
    price = runner_price(runner_info)
    price_text = f" around {price:g}" if price is not None else ''
    return (
        f"Today is {date_str}. Search the web for this exact UK horse racing runner and race only:\n"
        f"Horse: {horse}\n"
        f"Race: {time} {course} {race_name}\n"
        f"Current price/BSP:{price_text}\n\n"
        f"Question: which horse is best tipped in the {time} at {course} today, and how does {horse} compare? "
        f"Give every visible most-tipped horse, how many trusted tipsters/sources each has, and whether another runner is more strongly tipped than {horse}.\n\n"
        f"Search these exact-style phrases before answering:\n"
        f"- most tipped horse today tipsters {time} {course}\n"
        f"- most tipped horses {time} {course} today how many tipsters\n"
        f"- how many tipsters have backed {time} {course} runners today\n"
        f"- {time} {course} most tipped horses tipsters\n"
        f"- {horse} {course} {time} tips today\n"
        f"- {horse} {time} {course} GG tips\n"
        f"- {horse} {course} Racing TV tips\n"
        f"- {horse} {course} Racing Post tips\n\n"
        f"Use tiered trusted sources only:\n"
        f"Tier 1: Racing Post, Racing Post NAPs/Spotlight/Postdata, Sporting Life, Sporting Life NAPs/Ben Linfoot/David Ord, Timeform, At The Races, Racing TV.\n"
        f"Tier 2: Templegate, Newsboy, Robin Goodfellow, Marlborough, Rob Wright, Garry Biggs, Melissa Jones, Farringdon, Matt Polley, Lee Sobot, Garry Owen, Rockavon.\n"
        f"Tier 3: Racing Post NAPs table, Sporting Life NAPs table, HorseRacing.net NAPs/tipster stats, BetHQ NAPs/tipster rankings.\n"
        f"Tier 4: Oddschecker, OLBG, GG, Betfred Insights, Betfair tips/articles, FreeBets, RacingTips, Tipstrr, Punters Lounge.\n\n"
        f"Do not count unnamed previews, odds-only snippets, forums, social media, copied tip pages, or bookmaker advertorials.\n"
        f"If a source says '{horse} has 6 tips' or similar, return tip_count 6. "
        f"If individual named tipsters are shown, list them. If ranking, P/L, strike-rate, or NAP-table position is visible, include ranking_data. "
        f"If only an aggregate trusted count is visible, use sources ['TipsterConsensus'] and put the count in tip_count.\n\n"
        f"Return ONLY valid JSON. No explanation. Format exactly: "
        f'{{"tips":[{{"horse":"EXACT RUNNER NAME","sources":["RacingPost"],"tip_count":1,"tipsters":["Spotlight"],"tip_type":"Selection","is_nap":false,"is_nb":false,"ranking_data":{{"rank_position":null,"profit_loss":null,"strike_rate":null,"sample_size":null}},"notes":["brief evidence"]}}],"stronger_tipped_horse_than_signal75_candidate":false,"stronger_tipped_horse_name":null}}. '
        f"If no trusted tip evidence is found, return {{\"tips\":[]}}."
    )


def fetch_direct_horse_consensus(client, date_str, betfair_runners, aggregated, sources_seen):
    if os.environ.get('SIGNAL75_DISABLE_DIRECT_CONSENSUS', '').strip() == '1':
        return aggregated, sources_seen, {
            'enabled': False,
            'reason': 'disabled by SIGNAL75_DISABLE_DIRECT_CONSENSUS',
            'horses_checked': [],
        }

    shortlist = signal_shortlist_for_direct_consensus(betfair_runners)
    meta = {
        'enabled': True,
        'limit': DIRECT_CONSENSUS_LIMIT,
        'max_web_uses_per_horse': DIRECT_CONSENSUS_MAX_WEB_USES,
        'direct_only': DIRECT_CONSENSUS_ONLY,
        'horses_checked': [],
    }
    if not shortlist:
        meta['reason'] = 'no scored Signal 75 shortlist supplied'
        return aggregated, sources_seen, meta

    print(f"  Direct horse consensus: checking {len(shortlist)} Signal 75 shortlist horse(s)")
    for norm, runner_info, _rank in shortlist:
        horse = runner_info.get('betfair_name') or runner_info.get('name') or norm
        label = f"direct {horse} {runner_info.get('time','')} {runner_info.get('course','')}"
        meta['horses_checked'].append({
            'horse': horse,
            'market_id': runner_info.get('market_id', ''),
            'course': runner_info.get('course', ''),
            'time': runner_info.get('time', ''),
            'race_name': runner_info.get('race_name', ''),
            'score': runner_info.get('score'),
            'bsp': runner_price(runner_info),
        })
        tips = run_ai_tip_search(
            client,
            label,
            build_direct_horse_consensus_prompt(date_str, runner_info),
            DIRECT_CONSENSUS_MAX_WEB_USES,
        )
        aggregated, sources_seen = aggregate_tips(tips, betfair_runners, aggregated, sources_seen)

    return aggregated, sources_seen, meta

def race_sort_key(race):
    runners = race.get('runners') or []
    value_band = 0
    wider_band = 0
    max_score = -1
    for runner in runners:
        price = runner.get('price')
        score = runner.get('score')
        if price is not None and 4.1 <= price <= 6.0:
            value_band += 1
        if price is not None and 3.5 <= price <= 8.0:
            wider_band += 1
        if score is not None:
            max_score = max(max_score, score)
    field_ok = 1 if (race.get('field_size') or len(runners)) >= 8 else 0
    return (
        1 if max_score >= 75 else 0,
        max_score,
        value_band,
        wider_band,
        field_ok,
        race.get('market_total_matched') or 0,
        race.get('time') or '',
    )


def select_races_for_consensus(betfair_runners):
    races = load_runner_races(betfair_runners)
    races = [race for race in races if race.get('runners')]
    races.sort(key=race_sort_key, reverse=True)
    if RACE_CONSENSUS_LIMIT <= 0:
        return []
    return races[:RACE_CONSENSUS_LIMIT]


def build_race_runner_text(race):
    lines = []
    for runner in race.get('runners', []):
        price = runner.get('price')
        details = []
        if price is not None:
            details.append(f"price {price:g}")
        if runner.get('jockey'):
            details.append(f"jockey {runner['jockey']}")
        if runner.get('trainer'):
            details.append(f"trainer {runner['trainer']}")
        suffix = f" ({'; '.join(details)})" if details else ''
        lines.append(f"- {runner.get('name', '')}{suffix}")
    return "\n".join(lines)


def build_race_consensus_prompt(date_str, race):
    course = race.get('course', '')
    time = race.get('time', '')
    race_name = race.get('race_name', '')
    runners_text = build_race_runner_text(race)
    return (
        f"Today is {date_str}. Search the web for trusted UK horse racing tips for this exact race only:\n"
        f"{time} {course} {race_name}\n\n"
        f"Only match tips to these exact runners:\n{runners_text}\n\n"
        f"Main question: which horse is most strongly tipped in this race, and are any Signal 75-style value candidates opposed by stronger trusted consensus?\n\n"
        f"Search these exact-style phrases first:\n"
        f"- most tipped horse today tipsters {time} {course}\n"
        f"- most tipped horses {time} {course} today how many tipsters\n"
        f"- how many tipsters have backed {time} {course} runners today\n"
        f"- {time} {course} most tipped horses tipsters\n\n"
        f"Use tiered trusted sources only:\n"
        f"Tier 1: Racing Post, Racing Post NAPs/Spotlight/Postdata, Sporting Life, Sporting Life NAPs/Ben Linfoot/David Ord, Timeform, At The Races, Racing TV.\n"
        f"Tier 2: Templegate, Newsboy, Robin Goodfellow, Marlborough, Rob Wright, Garry Biggs, Melissa Jones, Farringdon, Matt Polley, Lee Sobot, Garry Owen, Rockavon.\n"
        f"Tier 3: Racing Post NAPs table, Sporting Life NAPs table, HorseRacing.net NAPs/tipster stats, BetHQ NAPs/tipster rankings.\n"
        f"Tier 4: Oddschecker, OLBG, GG, Betfred Insights, Betfair tips/articles, FreeBets, RacingTips, Tipstrr, Punters Lounge.\n\n"
        f"Important rules:\n"
        f"- If GG or another racecard shows '3 tips', '4 tips', or similar, return that number in tip_count.\n"
        f"- If a trusted aggregator says a horse has '6 tips' or similar, return that horse even if it is not the first preview selection.\n"
        f"- If Google AI or an aggregator lists several horses with counts, return every exact runner from that list.\n"
        f"- Count named tipsters separately where they are clearly named.\n"
        f"- If ranking, P/L, strike-rate, or NAP-table position is visible, include it in ranking_data.\n"
        f"- Do not include runners outside the exact list above.\n"
        f"- Do not count unnamed previews, odds-only snippets, forums, social media, copied pages, or advertorials.\n"
        f"- Do not guess. If no trusted tip is found for this race, return an empty tips list.\n\n"
        f"Return ONLY valid JSON: "
        f'{{"tips":[{{"horse":"EXACT RUNNER NAME","sources":["GG"],"tip_count":3,"tipsters":[],"tip_type":"Most tipped","is_nap":false,"is_nb":false,"ranking_data":{{"rank_position":null,"profit_loss":null,"strike_rate":null,"sample_size":null}},"notes":["3 tips on GG racecard"]}}]}}'
    )


def fetch_race_level_consensus(client, date_str, betfair_runners, aggregated, sources_seen):
    if os.environ.get('SIGNAL75_DISABLE_RACE_CONSENSUS', '').strip() == '1':
        return aggregated, sources_seen, {
            'enabled': False,
            'reason': 'disabled by SIGNAL75_DISABLE_RACE_CONSENSUS',
            'races_checked': [],
        }

    races = select_races_for_consensus(betfair_runners)
    meta = {
        'enabled': True,
        'limit': RACE_CONSENSUS_LIMIT,
        'max_web_uses_per_race': RACE_CONSENSUS_MAX_WEB_USES,
        'races_checked': [],
    }
    if not races:
        return aggregated, sources_seen, meta

    print(f"  Race-by-race consensus: checking {len(races)} race(s)")
    for race in races:
        label = f"race {race.get('time','')} {race.get('course','')}"
        meta['races_checked'].append({
            'market_id': race.get('market_id', ''),
            'course': race.get('course', ''),
            'time': race.get('time', ''),
            'race_name': race.get('race_name', ''),
            'runner_count': len(race.get('runners') or []),
        })
        tips = run_ai_tip_search(
            client,
            label,
            build_race_consensus_prompt(date_str, race),
            RACE_CONSENSUS_MAX_WEB_USES,
        )
        aggregated, sources_seen = aggregate_tips(tips, betfair_runners, aggregated, sources_seen)

    return aggregated, sources_seen, meta

def run_ai_tip_search(client, label, prompt, max_uses):
    print(f"  Searching {label}...")
    try:
        message = client.messages.create(
            model='claude-sonnet-4-5',
            max_tokens=4000,
            system="You are a JSON API. Search the web and return only valid JSON, nothing else. No preamble, no explanation.",
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"  AI search failed for {label}: {e}")
        return []

    response_text = ''
    for block in message.content:
        if hasattr(block, 'text'):
            response_text += block.text

    response_text = response_text.strip()
    if not response_text:
        print(f"  No response from {label}")
        return []

    print(f"  {label} response: {len(response_text)} chars — {response_text[:150]}...")

    response_text = re.sub(r'```(?:json)?\s*', '', response_text)
    response_text = re.sub(r'```', '', response_text).strip()
    data = extract_json_payload(response_text)
    if not data:
        print(f"  No valid tips JSON found for {label}")
        return []

    tips = data.get('tips', [])
    print(f"  {label} found {len(tips)} tipped horses")
    return tips


def aggregate_tips(tips, betfair_runners, aggregated=None, sources_seen=None):
    if aggregated is None:
        aggregated = {}
    if sources_seen is None:
        sources_seen = set()

    for tip in tips:
        horse_name = tip.get('horse', '').strip()
        tip_sources = tip.get('sources', [])
        if isinstance(tip_sources, str):
            tip_sources = [tip_sources]
        if not horse_name or not tip_sources:
            continue

        norm = normalise(horse_name)
        if norm not in betfair_runners:
            found = None
            for br_norm in betfair_runners:
                if norm in br_norm or br_norm in norm:
                    found = br_norm
                    break
            if not found:
                continue
            norm = found

        trusted_sources = []
        for source in tip_sources:
            source = str(source).strip()
            if not source:
                continue
            normalised_source = normalise_source(source)
            if normalised_source not in TRUSTED_SOURCES:
                print(f"  UNVERIFIED SOURCE: {source} — ignored")
                continue
            trusted_sources.append(normalised_source)

        if not trusted_sources:
            continue

        if norm not in aggregated:
            aggregated[norm] = {
                'sources': set(),
                'tipsters': set(),
                'tip_count': 0,
                'weighted_score': 0.0,
                'tier_counts': {1: 0, 2: 0, 3: 0, 4: 0},
                'tips': [],
            }

        def add_tipster_marker(label):
            if label not in aggregated[norm]['tipsters']:
                aggregated[norm]['tipsters'].add(label)
                aggregated[norm]['tip_count'] += 1

        source_weight_total = 0.0
        new_sources_for_tip = []
        for normalised_source in trusted_sources:
            already_seen_for_horse = normalised_source in aggregated[norm]['sources']
            aggregated[norm]['sources'].add(normalised_source)
            sources_seen.add(normalised_source)
            if not already_seen_for_horse:
                tier = source_tier(normalised_source)
                if tier in aggregated[norm]['tier_counts']:
                    aggregated[norm]['tier_counts'][tier] += 1
                source_weight_total += source_weight(normalised_source)
                new_sources_for_tip.append(normalised_source)

        declared_tip_count = max(
            safe_tip_count(tip.get('tip_count')),
            safe_tip_count(tip.get('tips_count')),
            safe_tip_count(tip.get('count')),
            safe_tip_count(tip.get('number_of_tips')),
        )
        named_tipsters = tip.get('tipsters') or []
        if isinstance(named_tipsters, str):
            named_tipsters = [named_tipsters]
        clean_tipsters = [str(t).strip() for t in named_tipsters if str(t).strip()]
        if clean_tipsters:
            added_from_this_tip = 0
            for tipster in clean_tipsters:
                before = aggregated[norm]['tip_count']
                add_tipster_marker(tipster)
                if aggregated[norm]['tip_count'] > before:
                    added_from_this_tip += 1
            source_label = trusted_sources[0] if trusted_sources else 'Tip'
            for idx in range(added_from_this_tip + 1, declared_tip_count + 1):
                add_tipster_marker(f"{source_label} tip count {idx}")
        elif declared_tip_count:
            source_label = trusted_sources[0] if trusted_sources else 'Tip'
            for idx in range(1, declared_tip_count + 1):
                add_tipster_marker(f"{source_label} tip count {idx}")
        else:
            aggregated[norm]['tip_count'] += max(1, len(tip_sources))

        weighted_add = source_weight_total + ranking_adjustment(tip)
        declared_tip_count = max(
            safe_tip_count(tip.get('tip_count')),
            safe_tip_count(tip.get('tips_count')),
            safe_tip_count(tip.get('count')),
            safe_tip_count(tip.get('number_of_tips')),
        )
        if declared_tip_count and trusted_sources:
            # Aggregated counts are useful, but weaker than independent named sources.
            best_source = min(trusted_sources, key=source_sort_key)
            weighted_add = max(weighted_add, min(8.0, declared_tip_count * source_weight(best_source)))
        aggregated[norm]['weighted_score'] = round(min(8.0, aggregated[norm]['weighted_score'] + max(0.0, weighted_add)), 2)
        aggregated[norm]['tips'].append({
            'sources': ranked_sources(trusted_sources),
            'new_sources_counted': ranked_sources(new_sources_for_tip),
            'tipsters': clean_tipsters,
            'tip_type': tip.get('tip_type') or '',
            'is_nap': bool(tip.get('is_nap')),
            'is_nb': bool(tip.get('is_nb')),
            'ranking_data': tip.get('ranking_data') or {},
            'notes': tip.get('notes') or [],
            'weighted_add': round(max(0.0, weighted_add), 2),
        })

    return aggregated, sources_seen


def fetch_consensus_via_ai(betfair_runners):
    if os.environ.get('SIGNAL75_CONFIRMED_TIPS_ONLY', '').strip() == '1':
        print("  Confirmed tips only — AI/web consensus skipped")
        return {}, [], {'enabled': False, 'reason': 'confirmed tips only', 'races_checked': []}, {'enabled': False, 'reason': 'confirmed tips only', 'horses_checked': []}

    import anthropic

    key = get_anthropic_key()
    if not key:
        print("  No Anthropic key — consensus overlay skipped")
        return {}, [], {'enabled': False, 'races_checked': []}, {'enabled': False, 'horses_checked': []}

    client = anthropic.Anthropic(api_key=key, timeout=45.0)

    runner_names = [v['betfair_name'] for v in betfair_runners.values()]
    if not runner_names:
        print("  No runners to match against")
        return {}, [], {'enabled': False, 'races_checked': []}, {'enabled': False, 'horses_checked': []}

    names_text = build_runner_text(betfair_runners)
    date_str = datetime.now().strftime('%A %d %B %Y')
    aggregated = {}
    sources_seen = set()

    aggregated, sources_seen, direct_consensus = fetch_direct_horse_consensus(
        client, date_str, betfair_runners, aggregated, sources_seen
    )

    race_consensus = {
        'enabled': False,
        'reason': 'direct horse consensus used',
        'races_checked': [],
    }

    if not DIRECT_CONSENSUS_ONLY or not direct_consensus.get('horses_checked') or not aggregated:
        print("  Searching for tipster consensus via targeted web searches...")
        for label, prompt, max_uses in build_targeted_prompts(date_str, names_text):
            tips = run_ai_tip_search(client, label, prompt, max_uses)
            aggregated, sources_seen = aggregate_tips(tips, betfair_runners, aggregated, sources_seen)

        aggregated, sources_seen, race_consensus = fetch_race_level_consensus(
            client, date_str, betfair_runners, aggregated, sources_seen
        )

        if len(aggregated) < 3:
            print("  Low match count — running fallback search")
            fallback_prompt = build_fallback_prompt(date_str, names_text)
            tips = run_ai_tip_search(client, 'fallback broad search', fallback_prompt, 4)
            before = set(aggregated)
            aggregated, sources_seen = aggregate_tips(tips, betfair_runners, aggregated, sources_seen)
            for norm in sorted(set(aggregated) - before):
                print(f"  Fallback added: {betfair_runners.get(norm, {}).get('betfair_name', norm)}")

    sources_successful = sorted(list(sources_seen))
    print(f"  Matched {len(aggregated)} horses from sources: {sources_successful}")
    return aggregated, sources_successful, race_consensus, direct_consensus


def merge_confirmed_tips(aggregated, sources_successful, betfair_runners, date_str):
    path = CONFIRMED_TIPS_TEMPLATE.format(datetime.now().strftime('%Y-%m-%d'))
    if not os.path.exists(path):
        return aggregated, sources_successful

    try:
        with open(path) as f:
            payload = json.load(f)
    except Exception as e:
        print(f"  Confirmed tips file ignored: {e}")
        return aggregated, sources_successful

    if payload.get('date') and payload.get('date') != datetime.now().strftime('%Y-%m-%d'):
        return aggregated, sources_successful

    merged = 0
    for tip in payload.get('tips', []):
        horse_name = (tip.get('horse') or '').strip()
        if not horse_name:
            continue
        norm = normalise(horse_name)
        if norm not in betfair_runners:
            found = None
            for br_norm in betfair_runners:
                if norm in br_norm or br_norm in norm:
                    found = br_norm
                    break
            if not found:
                continue
            norm = found

        if norm not in aggregated:
            aggregated[norm] = {
                'sources': set(),
                'tipsters': set(),
                'tip_count': 0,
                'weighted_score': 0.0,
                'tier_counts': {1: 0, 2: 0, 3: 0, 4: 0},
                'tips': [],
            }

        sources = tip.get('sources') or ['Confirmed']
        tipsters = tip.get('tipsters') or tip.get('notes') or []
        if isinstance(sources, str):
            sources = [sources]
        if isinstance(tipsters, str):
            tipsters = [tipsters]

        trusted_sources = []
        for source in sources:
            source = str(source).strip()
            if not source:
                continue
            normalised_source = normalise_source(source)
            if normalised_source not in TRUSTED_SOURCES:
                continue
            trusted_sources.append(normalised_source)

        weighted_add = 0.0
        new_sources = []
        for source in trusted_sources:
            already_seen = source in aggregated[norm]['sources']
            aggregated[norm]['sources'].add(source)
            if source not in sources_successful:
                sources_successful.append(source)
            if not already_seen:
                tier = source_tier(source)
                if tier in aggregated[norm]['tier_counts']:
                    aggregated[norm]['tier_counts'][tier] += 1
                weighted_add += source_weight(source)
                new_sources.append(source)

        clean_tipsters = [str(t).strip() for t in tipsters if str(t).strip()]
        declared_tip_count = max(
            safe_tip_count(tip.get('tip_count')),
            safe_tip_count(tip.get('tips_count')),
            safe_tip_count(tip.get('count')),
            safe_tip_count(tip.get('number_of_tips')),
        )
        if clean_tipsters:
            for tipster in clean_tipsters:
                if tipster not in aggregated[norm]['tipsters']:
                    aggregated[norm]['tipsters'].add(tipster)
                    aggregated[norm]['tip_count'] += 1
            source_label = trusted_sources[0] if trusted_sources else 'Confirmed'
            for idx in range(len(clean_tipsters) + 1, declared_tip_count + 1):
                marker = f"{source_label} confirmed tip count {idx}"
                if marker not in aggregated[norm]['tipsters']:
                    aggregated[norm]['tipsters'].add(marker)
                    aggregated[norm]['tip_count'] += 1
        elif declared_tip_count:
            source_label = trusted_sources[0] if trusted_sources else 'Confirmed'
            for idx in range(1, declared_tip_count + 1):
                marker = f"{source_label} confirmed tip count {idx}"
                if marker not in aggregated[norm]['tipsters']:
                    aggregated[norm]['tipsters'].add(marker)
                    aggregated[norm]['tip_count'] += 1
        else:
            aggregated[norm]['tip_count'] += max(1, len(sources))
        if declared_tip_count and trusted_sources:
            best_source = min(trusted_sources, key=source_sort_key)
            weighted_add = max(weighted_add, min(8.0, declared_tip_count * source_weight(best_source)))
        aggregated[norm]['weighted_score'] = round(
            min(8.0, aggregated[norm].get('weighted_score', 0.0) + weighted_add),
            2,
        )
        aggregated[norm].setdefault('tips', []).append({
            'sources': ranked_sources(trusted_sources),
            'new_sources_counted': ranked_sources(new_sources),
            'tipsters': clean_tipsters,
            'tip_type': tip.get('tip_type') or '',
            'is_nap': bool(tip.get('is_nap')),
            'is_nb': bool(tip.get('is_nb')),
            'ranking_data': tip.get('ranking_data') or {},
            'notes': tip.get('notes') or [],
            'weighted_add': round(weighted_add, 2),
        })
        merged += 1

    if merged:
        print(f"  Merged {merged} confirmed tip records")
    return aggregated, sources_successful


def tier_count_value(tier_counts, tier):
    if not tier_counts:
        return 0
    return int(tier_counts.get(tier, tier_counts.get(str(tier), 0)) or 0)


def calculate_overlay(source_count, tip_count, market_drifting=False, weighted_score=None, tier_counts=None):
    consensus_count = max(int(source_count or 0), int(tip_count or 0))
    weighted = safe_float(weighted_score) or 0.0
    tier_counts = tier_counts or {}
    tier1_to_3 = sum(tier_count_value(tier_counts, tier) for tier in (1, 2, 3))
    tier4_only = tier1_to_3 == 0 and tier_count_value(tier_counts, 4) > 0
    if consensus_count <= 0:
        return 0, None
    if consensus_count >= 6 and market_drifting:
        return 14, "Elite public support but market drifting — consensus boost reduced"
    if consensus_count >= 6:
        pts = 20
        return (min(pts, 8), "Commercial/community-only support capped") if tier4_only else (pts, None)
    if weighted >= 7.5:
        return 20, None
    if weighted >= 5.0:
        return 16, None
    if consensus_count >= 4:
        pts = 16
        return (min(pts, 8), "Commercial/community-only support capped") if tier4_only else (pts, None)
    if weighted >= 3.0:
        return 12, None
    if consensus_count >= 3:
        pts = 12
        return (min(pts, 8), "Commercial/community-only support capped") if tier4_only else (pts, None)
    if weighted >= 1.5:
        return 8, None
    if consensus_count >= 2:
        return 8, None
    if weighted >= 0.5:
        return 4, None
    if consensus_count >= 1:
        return 4, None
    return 0, None


def add_race_consensus_flags(matched):
    grouped = {}
    for item in matched:
        key = (item.get('course', '').lower(), item.get('time', ''))
        grouped.setdefault(key, []).append(item)

    for items in grouped.values():
        ordered = sorted(
            items,
            key=lambda row: (
                row.get('weighted_consensus_score', 0),
                row.get('consensus_count', 0),
                row.get('source_count', 0),
            ),
            reverse=True,
        )
        best = ordered[0] if ordered else None
        for item in items:
            stronger = bool(
                best and
                best is not item and
                best.get('weighted_consensus_score', 0) > item.get('weighted_consensus_score', 0)
            )
            item['best_tipped_horse_in_race'] = best.get('horse') if best else None
            item['best_tipped_weighted_score'] = best.get('weighted_consensus_score', 0) if best else 0
            item['stronger_tipped_horse_than_this'] = stronger
            item['stronger_tipped_horse_name'] = best.get('horse') if stronger and best else None
    return matched


def run_consensus_overlay(betfair_runners=None):
    date_str = datetime.now().strftime('%Y-%m-%d')
    output_path = f'{DATA_DIR}/consensus_overlay_{date_str}.json'

    print(f"\nSignal 75 — Consensus Overlay — {date_str}")
    print("=" * 50)

    try:
        if os.path.exists(output_path) and os.environ.get('SIGNAL75_FORCE_CONSENSUS', '').strip() != '1':
            try:
                with open(output_path) as f:
                    cached = json.load(f)
                if (
                    cached.get('date') == date_str and
                    cached.get('status') == 'ok' and
                    isinstance(cached.get('matched_to_betfair'), list)
                ):
                    print(f"  Using saved consensus overlay: {output_path}")
                    return cached
            except Exception as e:
                print(f"  Saved overlay ignored: {e}")

        runners = load_betfair_runners(betfair_runners)

        if not runners:
            result = {
                "date": date_str,
                "status": "failed_or_partial",
                "matched_to_betfair": [],
                "message": "No Betfair runners available — consensus overlay skipped."
            }
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)
            return result

        aggregated, sources_successful, race_consensus, direct_consensus = fetch_consensus_via_ai(runners)
        aggregated, sources_successful = merge_confirmed_tips(aggregated, sources_successful, runners, date_str)

        matched = []
        for norm, data in aggregated.items():
            runner_info = runners.get(norm, {})
            source_count = len(data['sources'])
            tip_count = max(data['tip_count'], len(data.get('tipsters', [])), source_count)
            consensus_count = max(source_count, tip_count)
            weighted_score = round(min(8.0, safe_float(data.get('weighted_score')) or 0.0), 2)
            tier_counts = data.get('tier_counts') or {}
            overlay_pts, warning = calculate_overlay(
                consensus_count,
                tip_count,
                weighted_score=weighted_score,
                tier_counts=tier_counts,
            )
            level = support_level(weighted_score)

            matched.append({
                "horse": runner_info.get('betfair_name', norm),
                "betfair_name": runner_info.get('betfair_name', norm),
                "course": runner_info.get('course', ''),
                "time": runner_info.get('time', ''),
                "source_count": source_count,
                "tip_count": tip_count,
                "consensus_count": consensus_count,
                "sources": ranked_sources(data['sources']),
                "tipsters": sorted(list(data.get('tipsters', []))),
                "source_tiers": {str(k): int(v) for k, v in sorted(tier_counts.items()) if v},
                "tier1_count": int(tier_counts.get(1, 0)),
                "tier2_count": int(tier_counts.get(2, 0)),
                "tier3_count": int(tier_counts.get(3, 0)),
                "tier4_count": int(tier_counts.get(4, 0)),
                "weighted_consensus_score": weighted_score,
                "support_level": level,
                "tip_evidence": data.get('tips', [])[:8],
                "consensus_level": level,
                "overlay_points": overlay_pts,
                "warning": warning
            })

        matched = add_race_consensus_flags(matched)
        matched.sort(
            key=lambda x: (
                x.get('weighted_consensus_score', 0),
                x.get('consensus_count', 0),
                x.get('source_count', 0),
            ),
            reverse=True,
        )

        result = {
            "date": date_str,
            "generatedAt": datetime.now().isoformat(),
            "sources_attempted": SOURCES,
            "sources_successful": sources_successful,
            "total_runners_checked": len(runners),
            "total_matched": len(matched),
            "race_consensus": race_consensus,
            "direct_consensus": direct_consensus,
            "matched_to_betfair": matched,
            "status": "ok" if sources_successful else "failed_or_partial",
            "message": "" if sources_successful else "No sources returned data — core Signal 75 scoring unaffected."
        }

    except Exception as e:
        print(f"  Consensus overlay error (safe): {e}")
        result = {
            "date": date_str,
            "status": "failed_or_partial",
            "matched_to_betfair": [],
            "message": f"Overlay error — core Signal 75 scoring unaffected. ({e})"
        }

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"  Overlay saved: {output_path}")
    print(f"  Status: {result['status']} | Matched: {result.get('total_matched', 0)}")
    return result


def apply_overlay_to_runners(scored_runners, overlay_data):
    if not overlay_data or overlay_data.get('status') != 'ok':
        for runner in scored_runners:
            runner['consensus'] = {
                'source_count': 0, 'tip_count': 0,
                'overlay_points': 0, 'warning': None,
                'consensus_level': 'none', 'sources': []
            }
        return scored_runners

    overlay_lookup = {}
    for h in overlay_data.get('matched_to_betfair', []):
        norm = normalise(h['betfair_name'])
        overlay_lookup[norm] = h

    for runner in scored_runners:
        norm = normalise(runner['name'])
        if norm in overlay_lookup:
            overlay = overlay_lookup[norm]
            pts = max(0, min(20, overlay['overlay_points']))
            runner['consensus'] = {
                'source_count': overlay['source_count'],
                'tip_count': overlay['tip_count'],
                'consensus_count': overlay.get('consensus_count', max(overlay.get('source_count', 0), overlay.get('tip_count', 0))),
                'overlay_points': pts,
                'warning': overlay['warning'],
                'consensus_level': overlay['consensus_level'],
                'support_level': overlay.get('support_level', overlay.get('consensus_level', 'none')),
                'weighted_consensus_score': overlay.get('weighted_consensus_score', 0),
                'source_tiers': overlay.get('source_tiers', {}),
                'stronger_tipped_horse_than_this': overlay.get('stronger_tipped_horse_than_this', False),
                'stronger_tipped_horse_name': overlay.get('stronger_tipped_horse_name'),
                'best_tipped_horse_in_race': overlay.get('best_tipped_horse_in_race'),
                'sources': overlay['sources'],
                'tipsters': overlay.get('tipsters', []),
            }
            runner['score'] = round(min(100, runner['score'] + pts), 1)
        else:
            runner['consensus'] = {
                'source_count': 0, 'tip_count': 0,
                'overlay_points': 0, 'warning': None,
                'consensus_level': 'none', 'sources': []
            }

    return scored_runners


if __name__ == '__main__':
    result = run_consensus_overlay()
    print(f"\nStatus: {result['status']}")
    if result.get('matched_to_betfair'):
        print("\nTop consensus horses:")
        for h in result['matched_to_betfair'][:5]:
            print(f"  {h['horse']} — {h['source_count']} sources {h['sources']} — overlay: {h['overlay_points']:+d}")
    else:
        print("No horses matched to Betfair runners today.")
