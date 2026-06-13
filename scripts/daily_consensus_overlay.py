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
    'SportingLife', 'SportingLife NAPs', 'RacingPost', 'RacingPost Spotlight',
    'RacingPost Newmarket', 'Racing Post Press Challenge', 'Timeform',
    'AtTheRaces', 'RacingTV', 'Betfred Insights',
    'Daily Mail Robin Goodfellow', 'Daily Mirror Newsboy', 'The Sun Templegate',
    'Telegraph Marlborough', 'The Times Rob Wright', 'Oddschecker', 'OLBG', 'GG'
]

RACE_CONSENSUS_LIMIT = int(os.environ.get('SIGNAL75_RACE_CONSENSUS_LIMIT', '12'))
RACE_CONSENSUS_MAX_WEB_USES = int(os.environ.get('SIGNAL75_RACE_CONSENSUS_MAX_WEB_USES', '1'))
DIRECT_CONSENSUS_LIMIT = int(os.environ.get('SIGNAL75_DIRECT_CONSENSUS_LIMIT', '10'))
DIRECT_CONSENSUS_MAX_WEB_USES = int(os.environ.get('SIGNAL75_DIRECT_CONSENSUS_MAX_WEB_USES', '2'))
DIRECT_CONSENSUS_ONLY = os.environ.get('SIGNAL75_DIRECT_CONSENSUS_ONLY', '1').strip() != '0'

SOURCE_ALIASES = {
    'racing post': 'RacingPost',
    'racingpost': 'RacingPost',
    'the racing post': 'RacingPost',
    'racingpost.com': 'RacingPost',
    'sporting life': 'SportingLife',
    'sportinglife': 'SportingLife',
    'sportinglife.com': 'SportingLife',
    'timeform': 'Timeform',
    'timeform.com': 'Timeform',
    'at the races': 'AtTheRaces',
    'attheraces': 'AtTheRaces',
    'at the races verdict': 'AtTheRaces',
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
    'betfair/timeform': 'Timeform',
    'betfair timeform': 'Timeform',
    'tipster consensus': 'TipsterConsensus',
    'national tipsters': 'TipsterConsensus',
    'daily racing press': 'TipsterConsensus',
    'press consensus': 'TipsterConsensus',
    'major tipster leaderboards': 'TipsterConsensus',
}

DEFAULT_TRUSTED_SOURCES = {
    'Timeform', 'RacingPost', 'SportingLife',
    'AtTheRaces', 'RacingTV', 'BetfredInsights',
    'OLBG', 'MyRacing', 'Oddschecker', 'GG',
    'DailyMail', 'DailyMirror', 'TheSun',
    'Telegraph', 'TheTimes', 'FreeBets', 'TipsterConsensus',
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
                f"- Rob Wright at thetimes.co.uk\n\n"
                f"Return only horses from these named tipsters that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["DailyMail"],"tipsters":["Robin Goodfellow"],"notes":["NAP"]}}]}}'
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
        f"Timeform, At The Races, Racing TV, Betfred Insights, Oddschecker, OLBG, GG, "
        f"and named newspaper tipsters Robin Goodfellow, Newsboy, Templegate, Marlborough, Rob Wright, "
        f"and other named newspaper naps from the trusted list. "
        f"Extract every named selection, including NAPs, next-best, value bets, lucky 15, spotlight, eyecatcher, next race tip, and best bets. "
        f"Count named tipsters/columns separately: examples include Racing Post Spotlight, Robin Goodfellow, Newsboy, Newmarket, "
        f"Ben Linfoot, Timeform, Oddschecker, At The Races Verdict, Templegate, "
        f"Marlborough, Rob Wright, GG, Racing TV pundits, and newspaper naps from the trusted list. "
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
        f"Question: give me the most tipped horses for the {time} at {course} today, including how many tipsters each horse has. "
        f"Then specifically say whether {horse} is listed and how many trusted tips it has.\n\n"
        f"Search these exact-style phrases before answering:\n"
        f"- most tipped horses {time} {course} today how many tipsters\n"
        f"- {time} {course} most tipped horses tipsters\n"
        f"- {horse} {course} {time} tips today\n"
        f"- {horse} {time} {course} GG tips\n"
        f"- {horse} {course} Racing TV tips\n"
        f"- {horse} {course} Racing Post tips\n\n"
        f"Use trusted sources only: Racing Post, Sporting Life, Timeform, At The Races, Racing TV, "
        f"Betfred Insights, Oddschecker, OLBG, GG, The Times Rob Wright, The Sun Templegate, "
        f"Daily Mail Robin Goodfellow, Daily Mirror Newsboy, Telegraph Marlborough, and named newspaper naps.\n\n"
        f"If a source says '{horse} has 6 tips' or similar, return tip_count 6. "
        f"If individual named tipsters are shown, list them. If only an aggregate trusted count is visible, "
        f"use sources ['TipsterConsensus'] and put the count in tip_count. Do not include rumours or untrusted forum posts.\n\n"
        f"Return ONLY valid JSON. No explanation. Format exactly: "
        f'{{"tips":[{{"horse":"EXACT RUNNER NAME","sources":["TipsterConsensus"],"tip_count":14,"tipsters":[],"notes":["14 trusted tips found for {time} {course}"]}}]}}. '
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
        f"Trusted sources only: Racing Post, Sporting Life, Timeform, At The Races, Racing TV, "
        f"Betfred Insights, Oddschecker, OLBG, GG, The Times Rob Wright, The Sun Templegate, "
        f"Daily Mail Robin Goodfellow, Daily Mirror Newsboy, Telegraph Marlborough, and named newspaper naps.\n\n"
        f"Important rules:\n"
        f"- If GG or another racecard shows '3 tips', '4 tips', or similar, return that number in tip_count.\n"
        f"- Count named tipsters separately where they are clearly named.\n"
        f"- Do not include runners outside the exact list above.\n"
        f"- Do not guess. If no trusted tip is found for this race, return an empty tips list.\n\n"
        f"Return ONLY valid JSON: "
        f'{{"tips":[{{"horse":"EXACT RUNNER NAME","sources":["GG"],"tip_count":3,"tipsters":[],"notes":["3 tips on GG racecard"]}}]}}'
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
            aggregated[norm] = {'sources': set(), 'tipsters': set(), 'tip_count': 0}

        def add_tipster_marker(label):
            if label not in aggregated[norm]['tipsters']:
                aggregated[norm]['tipsters'].add(label)
                aggregated[norm]['tip_count'] += 1

        for normalised_source in trusted_sources:
            aggregated[norm]['sources'].add(normalised_source)
            sources_seen.add(normalised_source)

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

    return aggregated, sources_seen


def fetch_consensus_via_ai(betfair_runners):
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
            aggregated[norm] = {'sources': set(), 'tipsters': set(), 'tip_count': 0}

        sources = tip.get('sources') or ['Confirmed']
        tipsters = tip.get('tipsters') or tip.get('notes') or []
        if isinstance(sources, str):
            sources = [sources]
        if isinstance(tipsters, str):
            tipsters = [tipsters]

        for source in sources:
            source = str(source).strip()
            if source:
                aggregated[norm]['sources'].add(source)
                if source not in sources_successful:
                    sources_successful.append(source)

        clean_tipsters = [str(t).strip() for t in tipsters if str(t).strip()]
        if clean_tipsters:
            for tipster in clean_tipsters:
                if tipster not in aggregated[norm]['tipsters']:
                    aggregated[norm]['tipsters'].add(tipster)
                    aggregated[norm]['tip_count'] += 1
        else:
            aggregated[norm]['tip_count'] += max(1, len(sources))
        merged += 1

    if merged:
        print(f"  Merged {merged} confirmed tip records")
    return aggregated, sources_successful


def calculate_overlay(source_count, tip_count, market_drifting=False):
    consensus_count = max(int(source_count or 0), int(tip_count or 0))
    if consensus_count <= 0:
        return 0, None
    if consensus_count >= 6 and market_drifting:
        return 14, "Elite public support but market drifting — consensus boost reduced"
    if consensus_count >= 6:
        return 20, None
    if consensus_count >= 4:
        return 16, None
    if consensus_count >= 3:
        return 12, None
    if consensus_count >= 2:
        return 8, None
    if consensus_count >= 1:
        return 4, None
    return 0, None


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
            overlay_pts, warning = calculate_overlay(consensus_count, tip_count)

            if consensus_count >= 3:
                level = 'high'
            elif consensus_count >= 1:
                level = 'medium'
            else:
                level = 'low'

            matched.append({
                "horse": runner_info.get('betfair_name', norm),
                "betfair_name": runner_info.get('betfair_name', norm),
                "course": runner_info.get('course', ''),
                "time": runner_info.get('time', ''),
                "source_count": source_count,
                "tip_count": tip_count,
                "consensus_count": consensus_count,
                "sources": sorted(list(data['sources'])),
                "tipsters": sorted(list(data.get('tipsters', []))),
                "consensus_level": level,
                "overlay_points": overlay_pts,
                "warning": warning
            })

        matched.sort(key=lambda x: (x.get('consensus_count', 0), x.get('source_count', 0)), reverse=True)

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
