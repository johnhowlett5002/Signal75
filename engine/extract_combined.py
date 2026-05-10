#!/usr/bin/env python3
import os, bz2, json, csv

FOLDERS = [
    os.path.expanduser("~/Desktop/BASIC"),
    os.path.expanduser("~/Desktop/BASIC2"),
    os.path.expanduser("~/Desktop/BASIC 3"),
    os.path.expanduser("~/Desktop/BASIC 4"),
]
OUTPUT_CSV = os.path.expanduser("~/Desktop/Signal75-Engine/betfair_uk_races_full_v2.csv")

def parse_file(filepath):
    try:
        with bz2.open(filepath, 'rt', encoding='utf-8') as f:
            lines = f.readlines()
    except:
        return []

    markets = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except:
            continue
        for mc in obj.get('mc', []):
            mid = mc.get('id', '')
            md = mc.get('marketDefinition', {})
            if not md:
                continue
            if md.get('countryCode') != 'GB':
                continue
            if md.get('marketType') not in ('WIN', 'PLACE'):
                continue
            markets[mid] = md

    results = []
    for mid, md in markets.items():
        if md.get('status') != 'CLOSED':
            continue

        mtype = md.get('marketType')
        runners = md.get('runners', [])
        
        # Parse distance from race name
        import re
        race_name = md.get('name', '')
        dist_match = re.search(r'(\d+)m(\d+f)?', race_name)
        if dist_match:
            miles = int(dist_match.group(1))
            furlongs_extra = int(dist_match.group(2)[:-1]) if dist_match.group(2) else 0
            distance_f = miles * 8 + furlongs_extra
        else:
            dist_match2 = re.search(r'(\d+)f', race_name)
            distance_f = int(dist_match2.group(1)) if dist_match2 else 0

        # Parse race type
        name_lower = race_name.lower()
        if 'hrd' in name_lower or 'hurdle' in name_lower:
            race_type = 'Hurdle'
        elif 'chs' in name_lower or 'chase' in name_lower:
            race_type = 'Chase'
        elif 'nhf' in name_lower or 'bumper' in name_lower:
            race_type = 'Bumper'
        else:
            race_type = 'Flat'

        # Parse sub-type
        if 'hcap' in name_lower or 'handicap' in name_lower:
            race_subtype = 'Handicap'
        elif 'mdn' in name_lower or 'maiden' in name_lower:
            race_subtype = 'Maiden'
        elif 'nov' in name_lower or 'novice' in name_lower:
            race_subtype = 'Novice'
        elif 'list' in name_lower:
            race_subtype = 'Listed'
        elif 'gr' in name_lower:
            race_subtype = 'Group'
        else:
            race_subtype = 'Other'

        runner_rows = []
        for r in runners:
            name_raw = r.get('name', '').strip()
            # Strip cloth number prefix e.g. "1. Horse Name"
            name_clean = re.sub(r'^\d+\.\s*', '', name_raw).strip()
            cloth = re.match(r'^(\d+)\.', name_raw)
            cloth_num = int(cloth.group(1)) if cloth else None
            
            af = r.get('adjustmentFactor', 0)
            bsp = round(100/af, 2) if af and af > 0 else None
            
            runner_rows.append({
                'market_id': mid,
                'market_type': mtype,
                'betfair_runner_id': r.get('id'),
                'horse_name': name_clean,
                'cloth_number': cloth_num,
                'bsp': bsp,
                'status': r.get('status'),
                'sort_priority': r.get('sortPriority'),
                'venue': md.get('venue', ''),
                'race_time': md.get('marketTime', ''),
                'race_name': race_name,
                'race_type': race_type,
                'race_subtype': race_subtype,
                'distance_furlongs': distance_f,
                'runner_count': md.get('numberOfActiveRunners', 0),
            })
        results.extend(runner_rows)
    return results

def main():
    print("Starting combined extraction...")
    all_rows = []
    files_checked = 0
    files_matched = 0

    for folder in FOLDERS:
        if not os.path.exists(folder):
            print(f"Skipping {folder} — not found")
            continue
        print(f"Scanning {folder}...")
        for root, dirs, files in os.walk(folder):
            dirs.sort()
            for fname in sorted(files):
                if not fname.endswith('.bz2'):
                    continue
                fpath = os.path.join(root, fname)
                if os.path.getsize(fpath) > 500000:
                    continue
                files_checked += 1
                rows = parse_file(fpath)
                if rows:
                    files_matched += 1
                    all_rows.extend(rows)
                if files_checked % 5000 == 0:
                    print(f"  {files_checked} files checked, {len(all_rows)} runner records so far...")

    print(f"\nDone. {files_checked} files, {files_matched} matched, {len(all_rows)} runner records.")

    if all_rows:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"Saved to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
