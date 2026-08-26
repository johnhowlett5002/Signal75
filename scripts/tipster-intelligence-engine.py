#!/usr/bin/env python3
"""Signal 75 paste-first tipster intelligence engine.

This is a separate intelligence layer. It does not change scoring, picks,
settlement, proof maths, unlock logic, or existing public JSON structures.

Input is manually pasted racing content from a local text file or stdin.
No scraping is performed.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / 'data' / 'tipster_intelligence'
RUNNERS_CACHE = REPO / 'data' / 'today_runners.json'

COURSES = [
    'Aintree', 'Ascot', 'Ayr', 'Bath', 'Beverley', 'Brighton', 'Carlisle',
    'Cartmel', 'Catterick', 'Chelmsford', 'Cheltenham', 'Chepstow', 'Chester',
    'Doncaster', 'Epsom', 'Exeter', 'Ffos Las', 'Goodwood', 'Hamilton',
    'Haydock', 'Hexham', 'Kempton', 'Leicester', 'Lingfield', 'Market Rasen',
    'Musselburgh', 'Newbury', 'Newcastle', 'Newmarket', 'Newton Abbot',
    'Nottingham', 'Perth', 'Plumpton', 'Pontefract', 'Redcar', 'Ripon',
    'Salisbury', 'Sandown', 'Southwell', 'Stratford', 'Taunton', 'Thirsk',
    'Uttoxeter', 'Warwick', 'Wetherby', 'Windsor', 'Wolverhampton', 'Worcester',
    'Yarmouth', 'York'
]

SOURCE_PATTERNS = {
    'Racing Post': r'\bracing\s+post\b',
    'Sporting Life': r'\bsporting\s+life\b',
    'At The Races': r'\bat\s+the\s+races\b|\battheraces\b',
    'Timeform': r'\btimeform\b',
    'Racing TV': r'\bracing\s+tv\b',
    'GG': r'\bgg\b|\bgg\.co\.uk\b',
    'Oddschecker': r'\boddschecker\b',
    'OLBG': r'\bolbg\b',
    'MyRacing': r'\bmyracing\b|\bmy\s+racing\b',
    'Daily Mail': r'\bdaily\s+mail\b|\brobin\s+goodfellow\b',
    'Daily Mirror': r'\bdaily\s+mirror\b|\bnewsboy\b',
    'The Sun': r'\bthe\s+sun\b|\btemplegate\b',
    'Telegraph': r'\btelegraph\b|\bmarlborough\b',
    'The Times': r'\bthe\s+times\b|\brob\s+wright\b',
    'Google AI': r'\bgoogle\b|\bai\s+overview\b',
}

POSITIVE = [
    'nap', 'best bet', 'banker', 'hard to beat', 'major chance', 'leading claims',
    'strong claims', 'clear pick', 'well backed', 'money arriving', 'market support',
    'most tipped', 'majority of experts', 'backed by', 'strong favourite', 'solid chance'
]
NEGATIVE = [
    'questions to answer', 'hard to recommend', 'opposable', 'weak favourite',
    'drifting', 'market negative', 'poor value', 'vulnerable', 'risky', 'concern'
]
VALUE = ['value', 'each-way', 'each way', 'overpriced', 'big price', 'hidden value']
DANGER = ['danger', 'main danger', 'threat', 'rival', 'alternative', 'challenger']
MARKET_POSITIVE = ['well backed', 'strong market support', 'money arriving', 'steaming', 'shortening']
MARKET_NEGATIVE = ['drifting', 'weak favourite', 'opposable', 'market negative', 'easy to back']
CONFIDENCE_WORDS = {
    'Elite': ['nap', 'banker', 'best bet', 'hard to beat', 'majority of experts'],
    'Strong': ['major chance', 'leading claims', 'strong claims', 'well backed'],
    'Moderate': ['place chance', 'interesting', 'chance', 'claims'],
}


def normalise(value: str) -> str:
    value = str(value or '').lower()
    value = re.sub(r"['’\-()]", '', value)
    value = re.sub(r'[^a-z0-9 ]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def load_today_runners() -> list[dict]:
    if not RUNNERS_CACHE.exists():
        return []
    try:
        payload = json.loads(RUNNERS_CACHE.read_text())
    except Exception:
        return []
    runners = []
    for race in payload.get('races', []):
        course = clean_course(race.get('venue', ''))
        time = display_time(race.get('race_time', ''))
        for runner in race.get('runners', []):
            runners.append({
                'horse_name': runner.get('name', ''),
                'horse_norm': normalise(runner.get('name', '')),
                'course': course,
                'race_time': time,
                'race_name': race.get('race_name', ''),
                'market_id': race.get('market_id', ''),
            })
    return runners


def clean_course(value: str) -> str:
    text = str(value or '').strip()
    return re.sub(r'\s+\d{1,2}(st|nd|rd|th)?\s+\w+$', '', text, flags=re.I).strip()


def display_time(value: str) -> str:
    raw = str(value or '')
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo:
            dt = dt.astimezone()
        return dt.strftime('%H:%M')
    except Exception:
        match = re.search(r'\b(\d{1,2})[:.](\d{2})\b', raw)
        if match:
            return f"{int(match.group(1)):02d}:{match.group(2)}"
    return ''


def detect_sources(text: str) -> list[str]:
    found = []
    for source, pattern in SOURCE_PATTERNS.items():
        if re.search(pattern, text, flags=re.I):
            found.append(source)
    return sorted(found)


def split_sentences(text: str) -> list[str]:
    rough = re.split(r'(?<=[.!?])\s+|\n+', text)
    return [x.strip() for x in rough if x.strip()]


def window_text(text: str, phrase: str, span: int = 180) -> str:
    lower = text.lower()
    idx = lower.find(phrase.lower())
    if idx < 0:
        return ''
    start = max(0, idx - span)
    end = min(len(text), idx + len(phrase) + span)
    return text[start:end]


def explicit_tip_count(text: str, horse: str) -> int | None:
    escaped = re.escape(horse)
    patterns = [
        rf'{escaped}\s*[:\-–]\s*(\d+)\s+tipsters?',
        rf'{escaped}[^\n\.]*?backed\s+by\s+(\d+)\s+(?:trusted\s+)?tipsters?',
        rf'{escaped}[^\n\.]*?(\d+)\s+(?:trusted\s+)?tips?',
        rf'(\d+)\s+(?:trusted\s+)?tips?[^\n\.]*?{escaped}',
        rf'(\d+)\s+tipsters?[^\n\.]*?{escaped}',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
    return None


def detect_course_time(text: str, runner: dict | None = None) -> tuple[str, str]:
    if runner:
        return runner.get('course', ''), runner.get('race_time', '')
    course = ''
    for c in COURSES:
        if re.search(rf'\b{re.escape(c)}\b', text, flags=re.I):
            course = c
            break
    m = re.search(r'\b(\d{1,2})[:.](\d{2})\b', text)
    time = f"{int(m.group(1)):02d}:{m.group(2)}" if m else ''
    return course, time


def consensus_label(count: int) -> str:
    if count >= 10:
        return 'Elite Consensus'
    if count >= 7:
        return 'Strong Consensus'
    if count >= 4:
        return 'Moderate Consensus'
    if count >= 1:
        return 'Weak Consensus'
    return 'No Consensus'


def market_confidence(text: str) -> str:
    pos = sum(1 for k in MARKET_POSITIVE if k in text.lower())
    neg = sum(1 for k in MARKET_NEGATIVE if k in text.lower())
    if pos >= 2 and pos > neg:
        return 'Strong Positive'
    if pos > neg:
        return 'Positive'
    if neg >= 2 and neg > pos:
        return 'Strong Negative'
    if neg > pos:
        return 'Negative'
    return 'Neutral'


def confidence_score(mentions: int, positive: int, negative: int, market: str, value_flag: bool) -> int:
    score = min(70, mentions * 7)
    score += min(20, positive * 4)
    score -= min(25, negative * 6)
    if market == 'Strong Positive':
        score += 12
    elif market == 'Positive':
        score += 7
    elif market == 'Negative':
        score -= 7
    elif market == 'Strong Negative':
        score -= 14
    if value_flag:
        score += 5
    return max(0, min(100, score))


def ai_view(signal_score: float | None, consensus: int, market: str, negative: int, value_flag: bool) -> str:
    if signal_score is not None and signal_score >= 75 and consensus >= 7 and market in {'Positive', 'Strong Positive'}:
        return 'Validated'
    if signal_score is not None and signal_score >= 75 and consensus >= 7:
        return 'Consensus Support'
    if signal_score is not None and signal_score >= 75 and (negative > 0 or market in {'Negative', 'Strong Negative'}):
        return 'Caution'
    if signal_score is not None and signal_score < 75 and consensus >= 4 and value_flag:
        return 'Value Opportunity'
    if consensus >= 7 and signal_score is not None and signal_score < 70:
        return 'Overhyped Watch'
    if consensus >= 7:
        return 'Consensus Leader'
    if consensus == 0 and signal_score is not None and signal_score >= 80:
        return 'Contrarian Signal'
    return 'Information Only'


def extract_signal_scores() -> dict[str, dict]:
    scores = {}
    picks = REPO / 'picks.json'
    if not picks.exists():
        return scores
    try:
        payload = json.loads(picks.read_text())
    except Exception:
        return scores
    cards = []
    for key in ('flat', 'jumps'):
        for race in payload.get(key, []) or []:
            for horse in race.get('horses', []) or []:
                cards.append((horse, race))
    for key in ('topRated', 'topRatedFlat', 'topRatedJumps'):
        for horse in payload.get(key, []) or []:
            cards.append((horse, {}))
    for horse, race in cards:
        name = horse.get('name') or horse.get('horse')
        if not name:
            continue
        scores[normalise(name)] = {
            'signal_score': horse.get('signal_score') or horse.get('score'),
            'odds': horse.get('odds'),
            'race_time': race.get('time') or horse.get('time', ''),
            'course': race.get('course') or horse.get('venue', ''),
        }
    return scores


def analyse_text(text: str, date: str) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    runners = load_today_runners()
    signal_scores = extract_signal_scores()
    text_norm = normalise(text)
    sources = detect_sources(text)
    sentences = split_sentences(text)

    matched = []
    known = {r['horse_norm']: r for r in runners if r.get('horse_norm')}
    if known:
        for norm, runner in known.items():
            if norm and re.search(rf'\b{re.escape(norm)}\b', text_norm):
                matched.append(runner)
    else:
        # Fallback for pasted Google-style lists without today_runners.json.
        for line in text.splitlines():
            m = re.match(r'\s*[•\-*]?\s*([A-Z][A-Za-z\'’\-]+(?:\s+[A-Z][A-Za-z\'’\-]+){0,4})\s*[:\-–]\s*\d+\s+tipsters?', line)
            if m:
                name = m.group(1).strip()
                matched.append({'horse_name': name, 'horse_norm': normalise(name), 'course': '', 'race_time': '', 'race_name': '', 'market_id': ''})

    records = []
    for runner in matched:
        horse = runner['horse_name']
        norm = runner['horse_norm']
        explicit = explicit_tip_count(text, horse)
        raw_mentions = len(re.findall(rf'\b{re.escape(norm)}\b', text_norm))
        mention_count = max(explicit or 0, raw_mentions)
        area = window_text(text, horse)
        area_lower = area.lower()
        positive_hits = [k for k in POSITIVE if k in area_lower]
        negative_hits = [k for k in NEGATIVE if k in area_lower]
        value_hits = [k for k in VALUE if k in area_lower]
        danger_hits = [k for k in DANGER if k in area_lower]
        market = market_confidence(area or text)
        score_info = signal_scores.get(norm, {})
        signal_score = score_info.get('signal_score')
        try:
            signal_score_f = float(signal_score) if signal_score not in (None, '') else None
        except Exception:
            signal_score_f = None
        conf = confidence_score(mention_count, len(positive_hits), len(negative_hits), market, bool(value_hits))
        course, race_time = detect_course_time(area or text, runner)
        records.append({
            'date': date,
            'course': course,
            'race_time': race_time,
            'race_name': runner.get('race_name', ''),
            'market_id': runner.get('market_id', ''),
            'horse_name': horse,
            'mention_count': mention_count,
            'explicit_tip_count': explicit or 0,
            'positive_score': round((len(positive_hits) / max(1, len(positive_hits) + len(negative_hits))) * 100, 1) if positive_hits or negative_hits else 0,
            'negative_score': round((len(negative_hits) / max(1, len(positive_hits) + len(negative_hits))) * 100, 1) if positive_hits or negative_hits else 0,
            'confidence_score': conf,
            'consensus_label': consensus_label(mention_count),
            'value_flag': bool(value_hits),
            'danger_flag': bool(danger_hits),
            'market_confidence': market,
            'source_count': len(sources),
            'sources': sources,
            'positive_terms': positive_hits,
            'negative_terms': negative_hits,
            'value_terms': value_hits,
            'danger_terms': danger_hits,
            'signal_score': signal_score_f,
            'odds': score_info.get('odds'),
            'ai_view': ai_view(signal_score_f, mention_count, market, len(negative_hits), bool(value_hits)),
            'evidence': area[:500],
        })

    grouped = defaultdict(list)
    for record in records:
        grouped[(record['course'], record['race_time'])].append(record)

    races = []
    for (course, race_time), items in grouped.items():
        ranked = sorted(items, key=lambda r: (r['mention_count'], r['confidence_score']), reverse=True)
        races.append({
            'course': course,
            'race_time': race_time,
            'most_tipped': ranked[0]['horse_name'] if ranked else '',
            'second_most_tipped': ranked[1]['horse_name'] if len(ranked) > 1 else '',
            'third_most_tipped': ranked[2]['horse_name'] if len(ranked) > 2 else '',
            'horses': ranked,
        })

    return {
        'version': '1.0',
        'date': date,
        'generatedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'mode': 'paste_intelligence_only',
        'message': 'Separate evidence layer. No scoring, picks, proof, results, unlock or automation changes.',
        'source_count': len(sources),
        'sources_detected': sources,
        'total_horses_detected': len(records),
        'races': sorted(races, key=lambda r: (r.get('race_time') or '', r.get('course') or '')),
        'records': sorted(records, key=lambda r: (r.get('race_time') or '', r.get('course') or '', -r.get('mention_count', 0))),
        'learning_targets': {
            'track_after_results': [
                'most_tipped_win_place_rate', 'strong_consensus_with_market_support',
                'strong_consensus_with_market_drift', 'value_flag_results',
                'danger_flag_results', 'signal75_plus_consensus_roi'
            ]
        }
    }


def write_csv(records: list[dict], path: Path) -> None:
    fields = [
        'date', 'course', 'race_time', 'horse_name', 'mention_count',
        'positive_score', 'negative_score', 'confidence_score', 'value_flag',
        'danger_flag', 'market_confidence', 'source_count', 'consensus_label',
        'signal_score', 'odds', 'ai_view'
    ]
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in records:
            writer.writerow({key: row.get(key, '') for key in fields})


def main() -> int:
    parser = argparse.ArgumentParser(description='Paste racing text into the Signal 75 tipster intelligence layer.')
    parser.add_argument('--input', '-i', help='Text file containing pasted racing content. Reads stdin if omitted.')
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--output', help='Optional JSON output path.')
    parser.add_argument('--csv', action='store_true', help='Also write CSV table beside the JSON output.')
    args = parser.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding='utf-8')
    else:
        text = sys.stdin.read()

    if not text.strip():
        print('No pasted text supplied.', file=sys.stderr)
        return 2

    payload = analyse_text(text, args.date)
    out = Path(args.output) if args.output else DATA_DIR / f'tipster_intelligence_{args.date}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    if args.csv:
        write_csv(payload['records'], out.with_suffix('.csv'))

    print(f"Saved: {out}")
    print(f"Horses detected: {payload['total_horses_detected']} | Sources: {', '.join(payload['sources_detected']) or 'none'}")
    for race in payload['races'][:10]:
        print(f"{race['race_time']} {race['course']} — most tipped: {race['most_tipped']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
