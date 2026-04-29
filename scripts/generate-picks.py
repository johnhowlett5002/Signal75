#!/usr/bin/env python3
"""Signal 75 Morning Picks Generator — rebuilt version with test mode"""

import os, sys, json, re, traceback, argparse
from datetime import date, datetime, timezone

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TEST_MODE = os.environ.get("S75_TEST_MODE", "0") == "1"

MIN_ODDS=2.1; MAX_ODDS=10.0; MIN_RUNNERS=6; MAX_RUNNERS=16
QUALIFY_SCORE=75; MIN_TIPSTERS=3; MIN_RPR=85
W_TIPSTERS=25; W_ODDS=20; W_MARKET=20; W_FIELD=10; W_FORM=10; W_TRAINER=10; W_COURSE=5
BANDS=[(80,"Elite Signal"),(75,"Qualified Signal"),(65,"Near Miss"),(55,"Watchlist"),(0,"Ignore")]

def log(msg): print(msg)

def band_for(score):
    for t,l in BANDS:
        if score>=t: return l
    return "Ignore"

def score_horse(h, runners):
    s=0
    tip=min(100,(h.get("tipsters",0)/8)*100); s+=tip*(W_TIPSTERS/100)
    odds=h.get("odds",0)
    if 3.0<=odds<=6.0: os2=100
    elif odds<3.0: os2=max(0,70-(3.0-odds)*30)
    else: os2=max(0,100-(odds-6.0)*15)
    s+=os2*(W_ODDS/100)
    prev=h.get("prevOdds",odds)
    if prev>odds: ms=min(100,((prev-odds)/prev)*300)
    elif prev<odds: ms=max(0,50-((odds-prev)/prev)*150)
    else: ms=50
    s+=ms*(W_MARKET/100)
    if 8<=runners<=12: fs=100
    elif runners<8: fs=max(0,60+(runners-MIN_RUNNERS)*10)
    else: fs=max(0,100-(runners-12)*12)
    s+=fs*(W_FIELD/100)
    fstr=h.get("formStr","")[-5:]; fv=0
    for i,c in enumerate(fstr):
        w=(i+1)*4
        if c in "1Ww": fv+=w*2
        elif c in "234Pp": fv+=w
    s+=min(100,(fv/60)*100)*(W_FORM/100)
    s+=(80 if h.get("trainerInForm") else 40)*(W_TRAINER/100)
    s+=min(100,(h.get("courseWins",0)+h.get("distanceWins",0))*25)*(W_COURSE/100)
    return round(s)

def hard_filter_passes(h, runners):
    odds=float(h.get("odds",0))
    if odds<MIN_ODDS or odds>MAX_ODDS: return False,f"odds {odds} outside {MIN_ODDS}-{MAX_ODDS}"
    if runners<MIN_RUNNERS or runners>MAX_RUNNERS: return False,f"runners {runners} outside {MIN_RUNNERS}-{MAX_RUNNERS}"
    return True,None

def process_races(raw):
    qf=[]; qj=[]; tr_all=[]
    for tab in ["flat","jumps"]:
        for race in raw.get(tab,[]):
            runners=race.get("runners",0)
            if not race.get("horses"): continue
            h=race["horses"][0]
            ok,reason=hard_filter_passes(h,runners)
            if not ok: log(f"   HARD FAIL {h.get('name','?')}: {reason}"); continue
            qs=score_horse(h,runners)
            h["qualificationScore"]=qs; h["band"]=band_for(qs)
            h["qualified"]=qs>=QUALIFY_SCORE and h.get("tipsters",0)>=MIN_TIPSTERS
            rpr=h.get("rpr",0)
            if rpr>0 and rpr<MIN_RPR:
                log(f"   RPR low: {h.get('name')} RPR={rpr}"); h["qualificationScore"]=max(0,qs-10); h["qualified"]=False
            re2=dict(race); re2["horses"]=[h]
            tr_all.append({"tab":tab,"race":re2,"horse":h,"score":h["qualificationScore"]})
            if h["qualified"]:
                if tab=="flat": qf.append(re2)
                else: qj.append(re2)
    tr_all.sort(key=lambda x:x["score"],reverse=True)
    top=[]
    for e in tr_all[:3]:
        h=e["horse"]; r=e["race"]
        top.append({"name":h.get("name"),"course":r.get("course"),"time":r.get("time"),
                    "odds":h.get("odds"),"qualificationScore":h.get("qualificationScore"),
                    "band":h.get("band"),"reason":h.get("reason",""),"qualified":False})
    return qf[:3],qj[:3],top

def build_output(qf,qj,top):
    now=datetime.now(timezone.utc).isoformat()
    has=len(qf)>0 or len(qj)>0
    blank={"position":0,"result":"","winReturn":0,"placeReturn":0,"totalReturn":0}
    mode="qualified" if has else "topRatedOnly"
    scores=[h.get("qualificationScore",0) for r in (qf+qj) for h in r.get("horses",[])]
    if not scores and top: scores=[top[0].get("qualificationScore",0)]
    return {"date":TODAY,"generatedAt":now,"mode":mode,"noBetDay":not has,
            "noBetReason":"" if has else "No horses met the Signal 75 qualifying threshold today.",
            "threshold":QUALIFY_SCORE,"topScore":max(scores) if scores else 0,
            "gapToThreshold":max(0,QUALIFY_SCORE-(max(scores) if scores else 0)),
            "flat":qf,"jumps":qj,"topRated":[] if has else top,
            "results":{"flat":[blank.copy() for _ in qf] if has else [],
                       "jumps":[blank.copy() for _ in qj] if has else [],
                       "patentReturn":0,"patentProfit":0,"complete":False}}

def call_claude_live():
    import anthropic
    client=anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    log("LIVE MODE — Anthropic call starting")
    prompt=f"""Today is {TODAY_DISPLAY}. Find today UK horse racing candidates.
Search sportinglife.com, attheraces.com, racingpost.com, gg.co.uk, sunracing.co.uk, oddschecker.com.
Return up to 6 flat and 6 jumps candidates with: time,course,type,distance,going,runners,num,name,jockey,trainer,odds,prevOdds,tipsters,formStr,goingWins,goingRuns,courseWins,distanceWins,trainerInForm,rpr,reason.
Return ONLY valid JSON: {{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[],"jumps":[],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}"""
    msg=client.messages.create(model="claude-haiku-4-5-20251001",max_tokens=2000,
        tools=[{"type":"web_search_20250305","name":"web_search"}],
        messages=[{"role":"user","content":prompt}])
    log(f"Tokens: in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    txt=""
    for b in msg.content:
        if hasattr(b,"text"): txt+=b.text
    return txt.strip()

def load_fixture(path):
    log("TEST MODE — Anthropic call skipped")
    log(f"TEST MODE — Loading fixture: {path}")
    if not os.path.exists(path): raise FileNotFoundError(f"Fixture not found: {path}")
    with open(path) as f: return f.read()

def extract_json(text):
    if not text: return None
    for pat in [r'```json\s*([\s\S]*?)\s*```',r'```\s*([\s\S]*?)\s*```']:
        m=re.search(pat,text)
        if m:
            try:
                o=json.loads(m.group(1))
                if "date" in o: return o
            except: pass
    try:
        o=json.loads(text.strip())
        if "date" in o: return o
    except: pass
    s=text.find("{")
    if s!=-1:
        d,e=0,-1
        for i,c in enumerate(text[s:],s):
            if c=="{": d+=1
            elif c=="}":
                d-=1
                if d==0: e=i+1; break
        if e!=-1:
            try:
                o=json.loads(text[s:e])
                if "date" in o: return o
            except: pass
    return None

def no_bet(reason):
    return {"date":TODAY,"generatedAt":datetime.now(timezone.utc).isoformat(),
            "mode":"noBetDay","noBetDay":True,"noBetReason":reason,
            "threshold":QUALIFY_SCORE,"topScore":0,"gapToThreshold":QUALIFY_SCORE,
            "flat":[],"jumps":[],"topRated":[],
            "results":{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":False}}

def write_outputs(picks,picks_file,archive_path):
    os.makedirs(os.path.dirname(archive_path),exist_ok=True)
    with open(archive_path,"w") as f: json.dump(picks,f,indent=2)
    with open(picks_file,"w") as f: json.dump(picks,f,indent=2)
    log(f"picks.json written — mode={picks.get('mode')} noBetDay={picks.get('noBetDay')}")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--fixture"); parser.add_argument("--picks-file",default="picks.json")
    parser.add_argument("--archive-dir",default="data")
    args=parser.parse_args()
    archive_path=os.path.join(args.archive_dir,f"{TODAY}.json")
    log(f"\n{'='*50}\nSignal 75 — {TODAY_DISPLAY}")
    log("TEST MODE — no API credits" if (TEST_MODE or args.fixture) else "LIVE MODE")
    log("="*50)
    if os.path.exists(args.picks_file) and not (TEST_MODE or args.fixture):
        try:
            with open(args.picks_file) as f: ex=json.load(f)
            if ex.get("date")==TODAY and ex.get("mode")=="qualified":
                log("Picks already done — skipping"); return
        except: pass
    try:
        if TEST_MODE or args.fixture:
            raw=load_fixture(args.fixture or "tests/fixtures/qualified_day_raw.json")
        else:
            if not ANTHROPIC_KEY:
                write_outputs(no_bet("No API key."),args.picks_file,archive_path); return
            raw=call_claude_live()
        picks_raw=extract_json(raw)
        if not picks_raw:
            log("Could not extract valid JSON")
            write_outputs(no_bet("AI did not return valid race data."),args.picks_file,archive_path); return
        qf,qj,top=process_races(picks_raw)
        picks=build_output(qf,qj,top); picks["date"]=TODAY
        if picks["mode"]=="qualified":
            log(f"QUALIFIED DAY — {len(qf)} flat {len(qj)} jumps")
            for r in qf:
                h=r["horses"][0]; log(f"   FLAT {r['time']} {r['course']}: {h['name']} @ {h['odds']} score={h['qualificationScore']} [{h['band']}]")
            for r in qj:
                h=r["horses"][0]; log(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']} score={h['qualificationScore']} [{h['band']}]")
        else:
            log(f"TOP RATED ONLY — {len(top)} horses")
            for t in top: log(f"   TOP: {t['name']} @ {t['odds']} score={t['qualificationScore']} [{t['band']}]")
        write_outputs(picks,args.picks_file,archive_path)
    except Exception as e:
        log(f"Fatal: {type(e).__name__}: {e}"); log(traceback.format_exc())
        write_outputs(no_bet("System error."),args.picks_file,archive_path)

if __name__=="__main__": main()
