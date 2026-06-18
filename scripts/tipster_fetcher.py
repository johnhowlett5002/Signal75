#!/usr/bin/env python3
"""
Signal 75 script-first tipster fetcher.

This is deliberately deterministic and low-cost:
- fetch known source pages directly
- match visible text against today's Betfair runners
- save a script overlay for daily_consensus_overlay.py
- never calls Anthropic or changes picks/proof/results
"""
import gzip
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path('/Users/johnhowlett/Signal75')
DATA_DIR = ROOT / 'data'
RUNNERS_CACHE = DATA_DIR / 'today_runners.json'

SOURCE_ALIASES = {
    'Racing Post': 'RacingPost',
    'Racing Post NAPs': 'RacingPost',
    'Racing Post Spotlight': 'RacingPost',
    'Paul Jacobs': 'PaulJacobs',
    'Tom Segal Pricewise': 'Pricewise',
    'Pricewise': 'Pricewise',
    'Sporting Life': 'SportingLife',
    'Ben Linfoot': 'SportingLife',
    'Timeform': 'Timeform',
    'At The Races': 'AtTheRaces',
    'Hugh Taylor': 'HughTaylor',
    'Racing TV': 'RacingTV',
    'The Sun Templegate': 'TheSun',
    'Daily Mirror Newsboy': 'DailyMirror',
    'Daily Mail Robin Goodfellow': 'DailyMail',
    'Telegraph Marlborough': 'Telegraph',
    'The Times Rob Wright': 'TheTimes',
    'OLBG': 'OLBG',
    'myracing': 'MyRacing',
    'GG': 'GG',
    'Oddschecker': 'Oddschecker',
    'HorseRacingNet': 'HorseRacingNet',
    'The Bookies Enemy': 'BookiesEnemy',
    'Gary Poole': 'BookiesEnemy',
    'Winning Post Profits': 'WinningPostProfits',
}

SOURCE_TIERS = {
    'RacingPost': 1,
    'PaulJacobs': 1,
    'Pricewise': 1,
    'SportingLife': 1,
    'Timeform': 1,
    'AtTheRaces': 1,
    'HughTaylor': 1,
    'RacingTV': 1,
    'TheSun': 2,
    'DailyMirror': 2,
    'DailyMail': 2,
    'Telegraph': 2,
    'TheTimes': 2,
    'OLBG': 4,
    'MyRacing': 4,
    'GG': 4,
    'Oddschecker': 4,
    'HorseRacingNet': 3,
    'BookiesEnemy': 3,
    'WinningPostProfits': 3,
}

SOURCE_WEIGHTS = {
    1: 2.0,
    2: 1.5,
    3: 1.0,
    4: 0.5,
}

SOURCE_PAGES = [
    {
        'source': 'Racing Post',
        'tier': 1,
        'urls': [
            'https://www.racingpost.com/horse-racing-tips/',
            'https://www.racingpost.com/horse-racing-tips/naps-table/',
        ],
    },
    {
        'source': 'Sporting Life',
        'tier': 1,
        'urls': [
            'https://www.sportinglife.com/racing/tips',
            'https://www.sportinglife.com/racing/news',
        ],
    },
    {
        'source': 'Timeform',
        'tier': 1,
        'urls': [
            'https://www.timeform.com/horse-racing/tips',
            'https://www.timeform.com/horse-racing',
        ],
    },
    {
        'source': 'At The Races',
        'tier': 1,
        'urls': [
            'https://www.attheraces.com/tips',
            'https://www.attheraces.com/racecards',
        ],
    },
    {
        'source': 'Racing TV',
        'tier': 1,
        'urls': [
            'https://www.racingtv.com/tips',
            'https://www.racingtv.com/racecards',
        ],
    },
    {
        'source': 'The Sun Templegate',
        'tier': 2,
        'urls': [
            'https://www.thesun.co.uk/sport/horseracing/',
            'https://www.thesun.co.uk/topic/templegate/',
        ],
    },
    {
        'source': 'Daily Mirror Newsboy',
        'tier': 2,
        'urls': [
            'https://www.mirror.co.uk/sport/horse-racing/',
            'https://www.mirror.co.uk/all-about/newsboy',
        ],
    },
    {
        'source': 'Daily Mail Robin Goodfellow',
        'tier': 2,
        'urls': [
            'https://www.dailymail.co.uk/sport/racing/index.html',
        ],
    },
    {
        'source': 'Telegraph Marlborough',
        'tier': 2,
        'urls': [
            'https://www.telegraph.co.uk/racing/',
        ],
    },
    {
        'source': 'The Times Rob Wright',
        'tier': 2,
        'urls': [
            'https://www.thetimes.com/sport/racing',
        ],
    },
    {
        'source': 'OLBG',
        'tier': 4,
        'urls': [
            'https://www.olbg.com/betting-tips/Horse_Racing',
        ],
    },
    {
        'source': 'myracing',
        'tier': 4,
        'urls': [
            'https://myracing.com/horse-racing-tips/',
        ],
    },
    {
        'source': 'GG',
        'tier': 4,
        'urls': [
            'https://www.gg.co.uk/racing/tips/',
            'https://www.gg.co.uk/racing/racecards/',
        ],
    },
    {
        'source': 'Oddschecker',
        'tier': 4,
        'urls': [
            'https://www.oddschecker.com/tips/horse-racing',
            'https://www.oddschecker.com/horse-racing',
        ],
    },
    {
        'source': 'The Bookies Enemy',
        'tier': 3,
        'urls': [
            'https://thegreattipoff.com/tipsters/horse-racing',
        ],
    },
    {
        'source': 'Winning Post Profits',
        'tier': 3,
        'urls': [
            'https://www.winningpostprofits.co.uk/',
        ],
    },
]

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
    'Accept-Encoding': 'gzip',
    'Cache-Control': 'no-cache',
}

TIP_CONTEXT_RE = re.compile(
    r'\b(?:tip|tips|tipster|tipsters|nap|naps|selection|selections|selected|'
    r'best bet|banker|most tipped|most-backed|most backed|newsboy|templegate|'
    r'robin goodfellow|marlborough|rob wright|spotlight|verdict|timeform|'
    r'paul jacobs|hugh taylor|pricewise|tom segal|bookies enemy|gary poole|'
    r'winning post profits|naps table leaders|next tips off|raceolly)\b',
    re.I,
)

GENERIC_SINGLE_WORDS = {
    'rating', 'ratings', 'odds', 'race', 'racing', 'runner', 'runners',
    'selection', 'tip', 'tips', 'form', 'class', 'distance', 'going',
    'market', 'winner', 'place', 'today', 'tomorrow',
}


def normalise(name):
    name = str(name or '').strip().lower()
    name = re.sub(r"['\u2019\-\(\)]", '', name)
    name = re.sub(r'[^a-z0-9 ]', '', name)
    return re.sub(r'\s+', ' ', name).strip()


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
        return dt.astimezone().strftime('%H:%M') if dt.tzinfo else dt.strftime('%H:%M')
    except Exception:
        match = re.search(r'\b(\d{1,2}:\d{2})\b', raw)
        return match.group(1) if match else raw


def source_name(source):
    return SOURCE_ALIASES.get(source, source)


def source_tier(source):
    return SOURCE_TIERS.get(source_name(source), 5)


def source_weight(source):
    return SOURCE_WEIGHTS.get(source_tier(source), 0.0)


def load_runners():
    if not RUNNERS_CACHE.exists():
        return {}
    data = json.loads(RUNNERS_CACHE.read_text())
    runners = {}
    for race in data.get('races', []):
        course = clean_course(race.get('venue', ''))
        time_text = display_race_time(race.get('race_time', ''))
        field_size = race.get('field_size') or len(race.get('runners', []))
        for runner in race.get('runners', []):
            name = runner.get('name', '')
            norm = normalise(name)
            if not norm:
                continue
            runners[norm] = {
                'betfair_name': name,
                'course': course,
                'time': time_text,
                'race_name': race.get('race_name', ''),
                'field_size': field_size,
                'market_id': race.get('market_id', ''),
            }
    return runners


def fetch_url(url, timeout=12):
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        if response.headers.get('Content-Encoding', '').lower() == 'gzip':
            body = gzip.decompress(body)
        charset = response.headers.get_content_charset() or 'utf-8'
        return body.decode(charset, errors='ignore')


def html_to_text(raw):
    raw = re.sub(r'(?is)<script.*?</script>', ' ', raw)
    raw = re.sub(r'(?is)<style.*?</style>', ' ', raw)
    raw = re.sub(r'(?is)<noscript.*?</noscript>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>', '\n', raw)
    raw = re.sub(r'(?i)</(?:p|div|li|tr|h[1-6])>', '\n', raw)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html.unescape(raw)
    raw = re.sub(r'\s+', ' ', raw)
    return raw.strip()


def runner_pattern(name):
    parts = [part for part in str(name).split() if part]
    pieces = [re.escape(part) for part in parts]
    pattern = r'\b' + r'[\s\u00a0\\-]+'.join(pieces) + r'\b'
    if len(parts) == 1:
        # Avoid matching "Tiger" inside "Tiger Beetle" or "Rating" inside page headings.
        pattern += r'(?![\s\u00a0\\-]+[A-Z][a-z])'
    return pattern


def has_tip_context(text, start, end):
    window = text[max(0, start - 220): min(len(text), end + 220)]
    return bool(TIP_CONTEXT_RE.search(window))


def nearby_tip_count(text, start, end):
    window = text[max(0, start - 170): min(len(text), end + 170)]
    count = 0
    for pattern in (
        r'\b(\d{1,2})\s*(?:tips?|tipsters?|selections?)\b',
        r'\bbacked\s+by\s+(\d{1,2})\b',
        r'\b(\d{1,2})\s*(?:experts?|pundits?)\b',
    ):
        for match in re.finditer(pattern, window, flags=re.I):
            value = int(match.group(1))
            if value <= 25:
                count = max(count, value)
    return count


def nearby_tip_type(text, start, end):
    window = text[max(0, start - 190): min(len(text), end + 190)].lower()
    if re.search(r'\bnap\b|best bet|selection of the day|banker', window):
        return 'NAP'
    if re.search(r'next best|\bnb\b', window):
        return 'NB'
    if 'each-way' in window or 'each way' in window or 'e/w' in window:
        return 'Each-way'
    if 'most tipped' in window or 'most-backed' in window or 'most backed' in window:
        return 'Most tipped'
    return 'Selection'


def nearby_evidence(text, start, end, size=115):
    snippet = text[max(0, start - size): min(len(text), end + size)]
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    return snippet[:260]


def match_source_text(source, url, text, runners):
    tips = []
    normalised_source = source_name(source)
    source_label = source
    seen = set()
    for norm, runner in runners.items():
        name = runner['betfair_name']
        if len(str(name).split()) == 1 and normalise(name) in GENERIC_SINGLE_WORDS:
            continue
        pattern = runner_pattern(name)
        for match in re.finditer(pattern, text, flags=re.I):
            if not has_tip_context(text, match.start(), match.end()):
                continue
            key = (norm, match.start())
            if key in seen:
                continue
            seen.add(key)
            declared_count = nearby_tip_count(text, match.start(), match.end())
            tip_type = nearby_tip_type(text, match.start(), match.end())
            evidence = nearby_evidence(text, match.start(), match.end())
            tips.append({
                'horse': name,
                'sources': [normalised_source],
                'source_url': url,
                'tip_count': declared_count or 1,
                'tipsters': [] if declared_count else [source_label],
                'tip_type': tip_type,
                'is_nap': tip_type == 'NAP',
                'is_nb': tip_type == 'NB',
                'ranking_data': {},
                'notes': [evidence] if evidence else [f'Matched on {source_label}'],
                'course': runner.get('course', ''),
                'time': runner.get('time', ''),
                'tier': source_tier(source),
                'weight': source_weight(source),
            })
            break
    return tips


def add_to_aggregate(aggregate, tip, runners):
    norm = normalise(tip.get('horse'))
    if norm not in runners:
        return False
    if norm not in aggregate:
        aggregate[norm] = {
            'runner': runners[norm],
            'sources': set(),
            'tipsters': set(),
            'tip_count': 0,
            'weighted_score': 0.0,
            'tier_counts': {1: 0, 2: 0, 3: 0, 4: 0},
            'tips': [],
        }
    row = aggregate[norm]
    sources = [source_name(s) for s in tip.get('sources', []) if str(s).strip()]
    new_sources = []
    for source in sources:
        if source not in row['sources']:
            row['sources'].add(source)
            new_sources.append(source)
            tier = source_tier(source)
            if tier in row['tier_counts']:
                row['tier_counts'][tier] += 1
            row['weighted_score'] += source_weight(source)

    declared_count = int(tip.get('tip_count') or 0)
    tipsters = [str(t).strip() for t in tip.get('tipsters', []) if str(t).strip()]
    if tipsters:
        for tipster in tipsters:
            if tipster not in row['tipsters']:
                row['tipsters'].add(tipster)
                row['tip_count'] += 1
    if declared_count:
        source_label = sources[0] if sources else 'Script'
        for idx in range(1, declared_count + 1):
            marker = f'{source_label} script tip count {idx}'
            if marker not in row['tipsters']:
                row['tipsters'].add(marker)
                row['tip_count'] += 1
        if sources:
            best = min(sources, key=lambda s: source_tier(s))
            row['weighted_score'] = max(row['weighted_score'], min(8.0, declared_count * source_weight(best)))
    elif not tipsters and sources:
        row['tip_count'] += 1

    row['weighted_score'] = round(min(8.0, row['weighted_score']), 2)
    row['tips'].append({
        'sources': sources,
        'new_sources_counted': new_sources,
        'tipsters': tipsters,
        'tip_type': tip.get('tip_type') or '',
        'is_nap': bool(tip.get('is_nap')),
        'is_nb': bool(tip.get('is_nb')),
        'ranking_data': tip.get('ranking_data') or {},
        'notes': tip.get('notes') or [],
        'source_url': tip.get('source_url', ''),
        'weighted_add': round(sum(source_weight(s) for s in new_sources), 2),
    })
    return True


def overlay_points(source_count, tip_count, weighted_score, tier_counts):
    consensus_count = max(int(source_count or 0), int(tip_count or 0))
    tier1_to_3 = sum(int(tier_counts.get(tier, 0) or 0) for tier in (1, 2, 3))
    tier4_only = tier1_to_3 == 0 and int(tier_counts.get(4, 0) or 0) > 0
    if consensus_count >= 6:
        return 8 if tier4_only else 20
    if weighted_score >= 7.5:
        return 20
    if consensus_count >= 4:
        return 8 if tier4_only else 16
    if weighted_score >= 5.0:
        return 16
    if consensus_count >= 3:
        return 8 if tier4_only else 12
    if weighted_score >= 3.0:
        return 12
    if consensus_count >= 2 or weighted_score >= 1.5:
        return 8
    if consensus_count >= 1 or weighted_score >= 0.5:
        return 4
    return 0


def support_level(weighted_score):
    if weighted_score >= 5.0:
        return 'very_strong'
    if weighted_score >= 3.0:
        return 'strong'
    if weighted_score >= 1.5:
        return 'useful'
    if weighted_score >= 0.5:
        return 'weak'
    return 'none'


def build_overlay(aggregate, runners, source_logs, date_str):
    matched = []
    sources_successful = set()
    for norm, data in aggregate.items():
        runner = data['runner']
        sources = sorted(data['sources'], key=lambda s: (source_tier(s), s))
        for source in sources:
            sources_successful.add(source)
        source_count = len(sources)
        tip_count = max(data['tip_count'], len(data['tipsters']), source_count)
        consensus_count = max(source_count, tip_count)
        weighted_score = round(min(8.0, data['weighted_score']), 2)
        tier_counts = data['tier_counts']
        level = support_level(weighted_score)
        matched.append({
            'horse': runner['betfair_name'],
            'betfair_name': runner['betfair_name'],
            'course': runner.get('course', ''),
            'time': runner.get('time', ''),
            'source_count': source_count,
            'tip_count': tip_count,
            'consensus_count': consensus_count,
            'sources': sources,
            'tipsters': sorted(data['tipsters']),
            'source_tiers': {str(k): int(v) for k, v in sorted(tier_counts.items()) if v},
            'tier1_count': int(tier_counts.get(1, 0)),
            'tier2_count': int(tier_counts.get(2, 0)),
            'tier3_count': int(tier_counts.get(3, 0)),
            'tier4_count': int(tier_counts.get(4, 0)),
            'weighted_consensus_score': weighted_score,
            'support_level': level,
            'tip_evidence': data['tips'][:8],
            'consensus_level': level,
            'overlay_points': overlay_points(source_count, tip_count, weighted_score, tier_counts),
            'warning': None,
        })
    matched.sort(key=lambda row: (row['weighted_consensus_score'], row['consensus_count'], row['source_count']), reverse=True)
    tier1_found = any(row.get('tier1_count', 0) > 0 for row in matched)
    return {
        'date': date_str,
        'generatedAt': datetime.now().isoformat(),
        'status': 'ok' if matched else 'failed_or_partial',
        'method': 'script_first_direct_fetch',
        'sources_attempted': [page['source'] for page in SOURCE_PAGES],
        'sources_successful': sorted(sources_successful, key=lambda s: (source_tier(s), s)),
        'source_logs': source_logs,
        'total_runners_checked': len(runners),
        'total_matched': len(matched),
        'tier1_source_found': tier1_found,
        'matched_to_betfair': matched,
        'message': '' if matched else 'No script source matched today runners.',
    }


def run_tipster_fetcher():
    date_str = datetime.now().strftime('%Y-%m-%d')
    output_path = DATA_DIR / f'script_tipster_overlay_{date_str}.json'
    runners = load_runners()
    source_logs = []
    aggregate = {}

    if not runners:
        result = {
            'date': date_str,
            'generatedAt': datetime.now().isoformat(),
            'status': 'failed_or_partial',
            'method': 'script_first_direct_fetch',
            'sources_attempted': [page['source'] for page in SOURCE_PAGES],
            'sources_successful': [],
            'source_logs': [],
            'total_runners_checked': 0,
            'total_matched': 0,
            'tier1_source_found': False,
            'matched_to_betfair': [],
            'message': 'No Betfair runners available.',
        }
        output_path.write_text(json.dumps(result, indent=2))
        return result

    for page in SOURCE_PAGES:
        source = page['source']
        source_matched = 0
        for url in page['urls']:
            log = {
                'source': source_name(source),
                'source_label': source,
                'tier': source_tier(source),
                'url': url,
                'status': 'not_started',
                'matched_horses': 0,
                'error': '',
            }
            try:
                raw = fetch_url(url)
                text = html_to_text(raw)
                tips = match_source_text(source, url, text, runners)
                added = 0
                for tip in tips:
                    if add_to_aggregate(aggregate, tip, runners):
                        added += 1
                log['status'] = 'ok'
                log['matched_horses'] = added
                source_matched += added
            except HTTPError as e:
                log['status'] = 'blocked_or_unavailable'
                log['error'] = f'HTTP {e.code}'
            except URLError as e:
                log['status'] = 'network_error'
                log['error'] = str(e.reason)
            except Exception as e:
                log['status'] = 'error'
                log['error'] = str(e)
            source_logs.append(log)
            time.sleep(0.25)
        if source_matched:
            print(f"  {source}: matched {source_matched}")

    result = build_overlay(aggregate, runners, source_logs, date_str)
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Script tipster overlay saved: {output_path}")
    print(f"Status: {result['status']} | Matched: {result['total_matched']} | Tier 1: {result['tier1_source_found']}")
    return result


if __name__ == '__main__':
    try:
        payload = run_tipster_fetcher()
        if payload.get('matched_to_betfair'):
            print('Top script matches:')
            for row in payload['matched_to_betfair'][:8]:
                print(f"  {row['horse']} — {row['source_count']} sources / {row['tip_count']} tips — {row['overlay_points']:+d} pts")
        else:
            print('No script matches today.')
    except KeyboardInterrupt:
        sys.exit(130)
