#!/usr/bin/env python3
"""
daily_consensus_overlay.py — Signal 75
Fetches public tipster/consensus data using Anthropic web search and
matches ONLY against today's Betfair runners.

Design rules:
- NEVER blocks picks.json generation
- Live official picks may require tipster consensus, but failure still produces radar/no-bet output safely
- NEVER replaces the core scoring engine
- Maximum overlay: +3 / -3 points only
- Fails safely and silently if anything goes wrong
"""
import json, re, os, subprocess
from datetime import datetime

DATA_DIR = '/Users/johnhowlett/Signal75/data'
os.makedirs(DATA_DIR, exist_ok=True)

RUNNERS_CACHE = '/Users/johnhowlett/Signal75/data/today_runners.json'
CONFIRMED_TIPS_TEMPLATE = '/Users/johnhowlett/Signal75/data/confirmed_tips_{}.json'
SOURCES = [
    'SportingLife', 'SportingLife NAPs', 'RacingPost', 'RacingPost Spotlight',
    'RacingPost Newmarket', 'Racing Post Press Challenge', 'Timeform',
    'AtTheRaces', 'RacingTV', 'talkSPORT 2', 'Betfred Insights',
    'Daily Mail Robin Goodfellow', 'Daily Mirror Newsboy', 'The Sun Templegate',
    'Telegraph Marlborough', 'The Times Rob Wright', 'Daily Express Garry Biggs',
    'Daily Express Melissa Jones', 'Morning Star Farringdon',
    'Irish Herald Ian Gaughran', 'Ipswich Star Matt Polley', 'Oddschecker',
    'OLBG', 'Tipstrr', 'MyRacing', 'GG', 'RacingTips'
]

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
}

TRUSTED_SOURCES = {
    'Timeform', 'RacingPost', 'SportingLife',
    'AtTheRaces', 'RacingTV', 'BetfredInsights',
    'OLBG', 'MyRacing', 'Oddschecker', 'GG',
    'DailyMail', 'DailyMirror', 'TheSun',
    'Telegraph', 'TheTimes', 'FreeBets',
}


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
                        'course': race.get('venue', ''),
                        'time': race.get('race_time', ''),
                        'market_id': race.get('market_id', '')
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
                f"- myracing.com tips today\n"
                f"- oddschecker.com horse racing tips\n"
                f"- betfredinsights.com today\n\n"
                f"Return only horses that match this runner list:\n{names_text}\n\n"
                f"Return ONLY valid JSON: "
                f'{{"tips":[{{"horse":"EXACT NAME","sources":["OLBG"],"tipsters":["OLBG"],"notes":["most tipped"]}}]}}'
            ),
            5,
        ),
    ]


def build_fallback_prompt(date_str, names_text):
    return (
        f"Today is {date_str}. You must find UK horse racing tips for TODAY only. "
        f"Search official and reputable UK racing tip sources, but keep the search concise. "
        f"Prioritise: Sporting Life/NAPs/Ben Linfoot, Racing Post Spotlight/Newmarket/Press Challenge, "
        f"Timeform, At The Races, Racing TV, Betfred Insights, Oddschecker, OLBG, myracing, GG, RacingTips, "
        f"and named newspaper tipsters Robin Goodfellow, Newsboy, Templegate, Marlborough, Rob Wright, "
        f"Farringdon, Matt Polley, and Ian Gaughran. "
        f"Extract every named selection, including NAPs, next-best, value bets, lucky 15, spotlight, eyecatcher, next race tip, and best bets. "
        f"Count named tipsters/columns separately: examples include Racing Post Spotlight, Robin Goodfellow, Newsboy, Newmarket, "
        f"Farringdon, Matt Polley, Ian Gaughran, Ben Linfoot, Timeform, Oddschecker, At The Races Verdict, Templegate, "
        f"Marlborough, Rob Wright, myracing, GG, Racing TV pundits, talkSPORT 2 pundits, and newspaper naps. "
        f"Then match ONLY against this exact Betfair runner list, using horse name plus time/course where possible:\n\n{names_text}\n\n"
        f"Return ONLY valid JSON. No explanation. Format exactly: "
        f'{{"tips":[{{"horse":"EXACT NAME FROM LIST","sources":["RacingPost"],"tipsters":["Spotlight","Robin Goodfellow"],"notes":["brief evidence"]}}]}}. '
        f"If a horse appears from multiple named tipsters on the same site, include each named tipster separately in tipsters. "
        f"Use exact horse names from the runner list. If no tips found, return {{\"tips\":[]}}."
    )


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

        if norm not in aggregated:
            aggregated[norm] = {'sources': set(), 'tipsters': set(), 'tip_count': 0}

        for source in tip_sources:
            source = str(source).strip()
            if not source:
                continue
            normalised_source = normalise_source(source)
            if normalised_source not in TRUSTED_SOURCES:
                print(f"  UNVERIFIED SOURCE: {source} — counted but flagged")
            aggregated[norm]['sources'].add(normalised_source)
            sources_seen.add(normalised_source)

        named_tipsters = tip.get('tipsters') or tip.get('notes') or []
        if isinstance(named_tipsters, str):
            named_tipsters = [named_tipsters]
        clean_tipsters = [str(t).strip() for t in named_tipsters if str(t).strip()]
        if clean_tipsters:
            for tipster in clean_tipsters:
                if tipster not in aggregated[norm]['tipsters']:
                    aggregated[norm]['tipsters'].add(tipster)
                    aggregated[norm]['tip_count'] += 1
        else:
            aggregated[norm]['tip_count'] += max(1, len(tip_sources))

    return aggregated, sources_seen


def fetch_consensus_via_ai(betfair_runners):
    import anthropic

    key = get_anthropic_key()
    if not key:
        print("  No Anthropic key — consensus overlay skipped")
        return {}, []

    client = anthropic.Anthropic(api_key=key)

    runner_names = [v['betfair_name'] for v in betfair_runners.values()]
    if not runner_names:
        print("  No runners to match against")
        return {}, []

    names_text = build_runner_text(betfair_runners)
    date_str = datetime.now().strftime('%A %d %B %Y')
    aggregated = {}
    sources_seen = set()

    print("  Searching for tipster consensus via targeted web searches...")
    for label, prompt, max_uses in build_targeted_prompts(date_str, names_text):
        tips = run_ai_tip_search(client, label, prompt, max_uses)
        aggregated, sources_seen = aggregate_tips(tips, betfair_runners, aggregated, sources_seen)

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
    return aggregated, sources_successful


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
    if source_count == 0:
        return 0, None
    elif source_count >= 6 and market_drifting:
        return -2, "High public support but market drifting — possible overhype"
    elif source_count >= 6:
        return 2, None
    elif source_count >= 3:
        return 1, None
    elif source_count >= 1:
        return 0, None
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

        aggregated, sources_successful = fetch_consensus_via_ai(runners)
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
            pts = max(-3, min(3, overlay['overlay_points']))
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
            runner['score'] = round(runner['score'] + pts, 1)
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
