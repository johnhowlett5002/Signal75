import csv, json
from collections import defaultdict

def sf(x):
    try:
        v=float(x); return v if v>0 else None
    except: return None

CSV='/Users/johnhowlett/Desktop/Signal75-Engine/betfair_uk_races_full_v2.csv'
OUTPUT='/Users/johnhowlett/Desktop/roi_tables.json'

print("Loading...")
with open(CSV) as f:
    rows=list(csv.DictReader(f))

# Calculate actual field size per market
market_runners=defaultdict(int)
for r in rows:
    if r['market_type']=='WIN' and r['status'] in ('WINNER','LOSER','REMOVED'):
        market_runners[r['market_id']]+=1

win_rows=[r for r in rows if r['market_type']=='WIN'
          and sf(r['bsp']) and r['status'] in ('WINNER','LOSER')]
for r in win_rows:
    r['_bsp']=sf(r['bsp'])
    r['_rc']=market_runners[r['market_id']]

place_rows=[r for r in rows if r['market_type']=='PLACE']
place_lookup=defaultdict(set)
for r in place_rows:
    if r['status']=='WINNER':
        place_lookup[(r['venue'],r['race_time'])].add(r['horse_name'].strip().lower())

print(f"WIN rows: {len(win_rows):,}")

# ── ODDS BANDS ────────────────────────────────────────────────
bands=[('1.01-2.0',1.01,2.0),('2.1-3.0',2.1,3.0),('3.1-5.0',3.1,5.0),
       ('5.1-8.0',5.1,8.0),('8.1-12.0',8.1,12.0),('12.1-20.0',12.1,20.0),('20+',20.1,9999)]

odds_bands={}
for label,lo,hi in bands:
    band=[r for r in win_rows if lo<=r['_bsp']<=hi and 6<=r['_rc']<=16]
    if not band: continue
    total=len(band)
    winners=[r for r in band if r['status']=='WINNER']
    ew=0.50; staked=total*ew*2; returned=0
    for r in winners:
        bsp=r['_bsp']; n=r['_rc']
        pf=0.20 if n>=12 else 0.25
        returned+=bsp*ew+(1+(bsp-1)*pf)*ew
    for r in band:
        if r['status']=='LOSER':
            key=(r['venue'],r['race_time']); h=r['horse_name'].strip().lower()
            if h in place_lookup.get(key,set()):
                bsp=r['_bsp']; n=r['_rc']
                pf=0.20 if n>=12 else 0.25
                returned+=(1+(bsp-1)*pf)*ew
    roi=round((returned-staked)/staked*100,2)
    sr=round(len(winners)/total*100,2)
    # confidence multiplier: scale from 0.85-1.15 based on ROI vs baseline (-6%)
    baseline=-6.0
    deviation=roi-baseline
    multiplier=round(1.0+(deviation/100),4)
    multiplier=max(0.85,min(1.15,multiplier))
    odds_bands[label]={
        'lo':lo,'hi':hi,
        'runners':total,'wins':len(winners),
        'strike_rate':sr,'ew_roi':roi,
        'confidence_multiplier':multiplier,
        'sample_reliable': total>=1000
    }
    print(f"  {label}: ROI {roi:+.1f}% multiplier {multiplier}")

# ── RACE TYPES ────────────────────────────────────────────────
type_stats=defaultdict(lambda:{'total':0,'wins':0,'staked':0.0,'returned':0.0})
ew=0.50
for r in win_rows:
    bsp=r['_bsp']; n=r['_rc']
    if not(2.1<=bsp<=10.0 and 6<=n<=16): continue
    k=r['race_type']+' / '+r['race_subtype']
    type_stats[k]['total']+=1
    type_stats[k]['staked']+=ew*2
    if r['status']=='WINNER':
        type_stats[k]['wins']+=1
        pf=0.20 if n>=12 else 0.25
        type_stats[k]['returned']+=bsp*ew+(1+(bsp-1)*pf)*ew
    elif r['status']=='LOSER':
        mk=(r['venue'],r['race_time']); h=r['horse_name'].strip().lower()
        if h in place_lookup.get(mk,set()):
            pf=0.20 if n>=12 else 0.25
            type_stats[k]['returned']+=(1+(bsp-1)*pf)*ew

race_types={}
baseline=-5.0
for k,v in type_stats.items():
    if v['total']<100: continue
    roi=round((v['returned']-v['staked'])/v['staked']*100,2)
    sr=round(v['wins']/v['total']*100,2)
    deviation=roi-baseline
    raw_multiplier=1.0+(deviation/100)
    # scale confidence by sample size
    sample_confidence=min(v['total']/2000,1.0)
    adjusted=1.0+((raw_multiplier-1.0)*sample_confidence)
    multiplier=round(max(0.85,min(1.15,adjusted)),4)
    race_types[k]={
        'runners':v['total'],'wins':v['wins'],
        'strike_rate':sr,'ew_roi':roi,
        'confidence_multiplier':multiplier,
        'sample_confidence':round(sample_confidence,2),
        'sample_reliable':v['total']>=500
    }
    print(f"  {k}: ROI {roi:+.1f}% multiplier {multiplier}")

# ── COURSE PROFILES ───────────────────────────────────────────
course_data=defaultdict(lambda:{'races':set(),'winner_bsps':[],'upsets':0})
for r in win_rows:
    if r['status'] not in ('WINNER','LOSER'): continue
    v=r['venue']; course_data[v]['races'].add(r['market_id'])
    if r['status']=='WINNER':
        bsp=r['_bsp']; course_data[v]['winner_bsps'].append(bsp)
        if bsp>10: course_data[v]['upsets']+=1

courses={}
for venue,d in course_data.items():
    if len(d['races'])<50: continue
    w=d['winner_bsps']
    if not w: continue
    avg=round(sum(w)/len(w),2)
    upset_pct=round(d['upsets']/len(w)*100,1)
    if avg<5.5: personality='fav_friendly'
    elif avg>8.0: personality='upset_heavy'
    else: personality='ew_sweet'
    # multiplier: ew_sweet gets boost, upset_heavy gets slight penalty
    if personality=='ew_sweet': multiplier=1.05
    elif personality=='fav_friendly': multiplier=0.98
    else: multiplier=0.95
    courses[venue]={
        'races':len(d['races']),
        'avg_winner_bsp':avg,
        'upset_pct':upset_pct,
        'personality':personality,
        'confidence_multiplier':multiplier
    }

# ── HORSE PROFILES ────────────────────────────────────────────
horse_data=defaultdict(lambda:{'runs':0,'wins':0,'places':0,'bsps':[],'last':''})
for r in win_rows:
    n=r['horse_name'].strip(); h=horse_data[n]
    h['runs']+=1
    if r['status']=='WINNER': h['wins']+=1
    key=(r['venue'],r['race_time'])
    if n.lower() in place_lookup.get(key,set()): h['places']+=1
    h['bsps'].append(r['_bsp'])
    if r['race_time']>h['last']: h['last']=r['race_time'][:10]

horse_profiles={}
for name,d in horse_data.items():
    if d['runs']<3: continue
    wr=d['wins']/d['runs']
    avg_bsp=round(sum(d['bsps'])/len(d['bsps']),2)
    sample_confidence=min(d['runs']/20,1.0)
    baseline_wr=0.15
    excess=wr-baseline_wr
    boost=1.0+(excess*sample_confidence*1.0)
    boost=round(max(0.80,min(1.25,boost)),4)
    horse_profiles[name]={
        'runs':d['runs'],'wins':d['wins'],'places':d['places'],
        'win_rate':round(wr*100,1),
        'avg_bsp':avg_bsp,
        'last_seen':d['last'],
        'sample_confidence':round(sample_confidence,2),
        'history_multiplier':boost
    }

# ── OUTPUT ────────────────────────────────────────────────────
output={
    'generated':'2026-05-07',
    'records_analysed':len(win_rows),
    'odds_bands':odds_bands,
    'race_types':race_types,
    'courses':courses,
    'horse_profiles':horse_profiles
}

with open(OUTPUT,'w') as f:
    json.dump(output,f,indent=2)

print(f"\nSaved to {OUTPUT}")
print(f"Odds bands: {len(odds_bands)}")
print(f"Race types: {len(race_types)}")
print(f"Courses: {len(courses)}")
print(f"Horse profiles: {len(horse_profiles):,}")
print("Done.")