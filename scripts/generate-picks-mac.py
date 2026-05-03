#!/usr/bin/env python3
"""
Signal 75 — Morning Picks Generator (Mac/launchd version)
Sonnet finds candidates. Python scores, qualifies, and decides mode.
Test mode: S75_TEST_MODE=1 — no API credits used.
"""

import os, json, re, subprocess, traceback
from datetime import date, datetime, timezone

TODAY = date.today().isoformat()
TODAY_DISPLAY = date.today().strftime("%A %d %B %Y")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
TEST_MODE = os.environ.get("S75_TEST_MODE", "0") == "1"
REPO_PATH = os.path.expanduser("~/Signal75")
PICKS_FILE = os.path.join(REPO_PATH, "picks.json")
ARCHIVE_DIR = os.path.join(REPO_PATH, "data")
ARCHIVE_FILE = os.path.join(ARCHIVE_DIR, f"{TODAY}.json")
LOG_FILE = os.path.expanduser("~/signal75-picks.log")

MIN_ODDS=2.1; MAX_ODDS=10.0; MIN_RUNNERS=6; MAX_RUNNERS=16
QUALIFY_SCORE=75; MIN_TIPSTERS=3; MIN_RPR=85
W_TIPSTERS=25; W_ODDS=20; W_MARKET=20; W_FIELD=10; W_FORM=10; W_TRAINER=10; W_COURSE=5
BANDS=[(80,"Elite Signal"),(75,"Qualified Signal"),(65,"Near Miss"),(55,"Watchlist"),(0,"Ignore")]

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(f"{msg}\n")

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

def no_bet(reason):
    return {"date":TODAY,"generatedAt":datetime.now(timezone.utc).isoformat(),
            "mode":"noBetDay","noBetDay":True,"noBetReason":reason,
            "threshold":QUALIFY_SCORE,"topScore":0,"gapToThreshold":QUALIFY_SCORE,
            "flat":[],"jumps":[],"topRated":[],
            "results":{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":False}}

def extract_json(raw):
    if not raw: return None
    text=raw.strip()
    text=re.sub(r"```(?:json)?\s*","",text,flags=re.IGNORECASE)
    text=re.sub(r"```","",text).strip()
    try:
        obj=json.loads(text)
        if "date" in obj and ("flat" in obj or "noBetDay" in obj): return obj
    except: pass
    s=text.find("{"); e=text.rfind("}")
    if s!=-1 and e!=-1 and e>s:
        try:
            obj=json.loads(text[s:e+1])
            if "date" in obj and ("flat" in obj or "noBetDay" in obj): return obj
        except: pass
    return None

def call_claude(attempt):
    import anthropic
    client=anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    strict=""
    if attempt==2: strict="CRITICAL: Previous response had no valid JSON. Return ONLY JSON."
    elif attempt>=3: strict="FINAL ATTEMPT: JSON only. No text before or after."
    prompt=f"""Today is {TODAY_DISPLAY}. You are a data extraction service. Search for UK horse racing data and return it in JSON format.

Step 1: Search sportinglife.com/racing for today's UK race meetings and tips.
Step 2: Search attheraces.com for today's runners and odds.
Step 3: Return the extracted data as JSON ONLY — no explanation, no text before or after.

Return up to 3 flat and 3 jumps race entries only — keep it short. For each horse include ALL fields:
time, course, type, distance, going, runners, num, name, jockey, trainer, odds, prevOdds, tipsters, formStr, goingWins, goingRuns, courseWins, distanceWins, trainerInForm, rpr, reason.

tipsters = count how many of these mention the horse: sportinglife, attheraces, racingpost, gg.co.uk, sunracing, oddschecker.
If you cannot find tipster count use 1.
If you cannot find form use "00000".
If you cannot find RPR use 90.
prevOdds = yesterday's odds or same as odds if unknown.

{strict}

YOUR ENTIRE RESPONSE MUST BE THIS JSON AND NOTHING ELSE:
{{"date":"{TODAY}","noBetDay":false,"noBetReason":"","flat":[{{"time":"14:00","course":"Newmarket","type":"flat","distance":"1m","going":"good","runners":10,"horses":[{{"num":3,"name":"ACTUAL HORSE NAME","jockey":"J. Name","trainer":"T. Name","odds":5.0,"prevOdds":6.0,"tipsters":2,"formStr":"11212","goingWins":2,"goingRuns":4,"courseWins":1,"distanceWins":2,"trainerInForm":true,"rpr":100,"confidence":"high","reason":"Short reason.","result":"","position":0}}]}}],"jumps":[],"results":{{"flat":[],"jumps":[],"patentReturn":0,"patentProfit":0,"complete":false}}}}

CRITICAL RULES:
- Return whatever horse data you can find — even if incomplete
- If you only know the horse name and odds, include those and use defaults for unknown fields
- Do NOT refuse to return JSON — always return the JSON structure
- Do NOT say you cannot find data — just return what you have
- Use tipsters=1 if unknown, formStr="00000" if unknown, rpr=90 if unknown
- It is better to return partial data than no data"""
    log(f"Attempt {attempt}: calling Sonnet...")
    message=client.messages.create(
        model="claude-sonnet-4-5",max_tokens=2000,
        system="You are a JSON API. Return only valid JSON, no explanation.",
        tools=[{"type":"web_search_20250305","name":"web_search"}],
        messages=[{"role":"user","content":prompt}])
    txt=""
    for b in message.content:
        if hasattr(b,"text"): txt+=b.text
    txt=txt.strip()
    log(f"Model: claude-sonnet-4-5 | {len(txt)} chars")
    log(f"Preview: {txt[:300]}")
    return txt

def load_fixture(path):
    log("TEST MODE — API skipped")
    log(f"Loading fixture: {path}")
    if not os.path.exists(path): raise FileNotFoundError(f"Fixture not found: {path}")
    with open(path) as f: return f.read()

def write_outputs(picks):
    os.makedirs(ARCHIVE_DIR,exist_ok=True)
    if not os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE,"w") as f: json.dump(picks,f,indent=2)
        log(f"Archive written: data/{TODAY}.json")
    else:
        log(f"Archive exists for {TODAY} — not overwriting")
    with open(PICKS_FILE,"w") as f: json.dump(picks,f,indent=2)
    log(f"picks.json written — mode={picks.get('mode')} noBetDay={picks.get('noBetDay')}")

def push_to_github():
    cmds=[
        ["git","-C",REPO_PATH,"pull","--quiet"],
        ["git","-C",REPO_PATH,"add","picks.json",f"data/{TODAY}.json"],
        ["git","-C",REPO_PATH,"commit","-m",f"Auto picks {TODAY_DISPLAY}"],
        ["git","-C",REPO_PATH,"push"],
    ]
    for cmd in cmds:
        r=subprocess.run(cmd,capture_output=True,text=True)
        if r.returncode!=0 and "nothing to commit" not in r.stdout+r.stderr:
            log(f"git warning: {r.stderr.strip()}")
        else:
            log(f"git {cmd[2]} ok")
    log("Pushed! signal75.co.uk updating...")

def main():
    log(f"\n{'='*50}\nSignal 75 — {TODAY_DISPLAY}")
    log("TEST MODE — no API credits" if TEST_MODE else "LIVE MODE")
    log("="*50)

    if not TEST_MODE:
        if not ANTHROPIC_KEY:
            write_outputs(no_bet("No API key.")); push_to_github(); return
        if os.path.exists(PICKS_FILE):
            try:
                with open(PICKS_FILE) as f: ex=json.load(f)
                if ex.get("date")==TODAY and ex.get("mode")=="qualified":
                    log("Picks already done — skipping"); return
            except: pass

    try:
        if TEST_MODE:
            fixture=os.path.join(REPO_PATH,"tests/fixtures/qualified_day_raw.json")
            raw=load_fixture(fixture)
        else:
            raw=None
            for attempt in range(1,4):
                try:
                    raw=call_claude(attempt)
                    if extract_json(raw): break
                    log(f"Attempt {attempt}: no valid JSON — retrying...")
                except Exception as e:
                    log(f"Attempt {attempt} error: {e}")
                    if attempt==3: raise

        picks_raw=extract_json(raw) if raw else None
        if not picks_raw:
            log("Could not extract valid JSON")
            write_outputs(no_bet("AI did not return valid race data."))
            if not TEST_MODE: push_to_github()
            return

        # Count total candidates Sonnet returned
        total_flat = len(picks_raw.get("flat", []))
        total_jumps = len(picks_raw.get("jumps", []))
        total_candidates = total_flat + total_jumps
        meetings = list(set(r.get("course","?") for r in picks_raw.get("flat",[]) + picks_raw.get("jumps",[])))
        log(f"Meetings found: {len(meetings)} — {meetings}")
        log(f"Candidates returned: {total_flat} flat, {total_jumps} jumps")

        # VALIDATION GATE: If Sonnet returned no candidates at all, this is an
        # incomplete AI response — NOT a genuine no-bet day
        if total_candidates == 0:
            log("⚠️  WARNING: Sonnet returned 0 candidates — AI response incomplete")
            log("⚠️  NOT writing noBetDay=True — this is a data failure not a betting decision")
            incomplete = {
                "date": TODAY,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "mode": "incomplete",
                "noBetDay": False,
                "noBetReason": "",
                "dataStatus": "INCOMPLETE_AI_RESPONSE",
                "warning": "Race meetings found but AI returned no candidate horses. Do not mark as no-bet day.",
                "threshold": QUALIFY_SCORE, "topScore": 0, "gapToThreshold": QUALIFY_SCORE,
                "flat": [], "jumps": [], "topRated": [],
                "results": {"flat": [], "jumps": [], "patentReturn": 0, "patentProfit": 0, "complete": False}
            }
            write_outputs(incomplete)
            if not TEST_MODE: push_to_github()
            return

        qf,qj,top=process_races(picks_raw)
        picks=build_output(qf,qj,top)
        picks["date"]=TODAY
        log(f"Races checked: {total_candidates} | Qualified: {len(qf)} flat {len(qj)} jumps | Radar: {len(top)}")

        if picks["mode"]=="qualified":
            log(f"QUALIFIED DAY — {len(qf)} flat {len(qj)} jumps")
            for r in qf:
                h=r["horses"][0]
                log(f"   FLAT  {r['time']} {r['course']}: {h['name']} @ {h['odds']} score={h['qualificationScore']} [{h['band']}]")
            for r in qj:
                h=r["horses"][0]
                log(f"   JUMPS {r['time']} {r['course']}: {h['name']} @ {h['odds']} score={h['qualificationScore']} [{h['band']}]")
        else:
            log(f"TOP RATED ONLY — {len(top)} radar horses")
            for t in top: log(f"   RADAR: {t['name']} @ {t['odds']} score={t['qualificationScore']} [{t['band']}]")

        write_outputs(picks)
        if not TEST_MODE: push_to_github()

    except Exception as e:
        log(f"Fatal: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        write_outputs(no_bet("System error."))
        if not TEST_MODE: push_to_github()

if __name__=="__main__": main()
