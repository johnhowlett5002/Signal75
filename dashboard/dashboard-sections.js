/* ==========================================================================
   SIGNAL 75 — DASHBOARD SECTION RENDERERS + NAV/BOOT
   Loaded after dashboard.js. Every render fn reads from DEMO or LIVE only.
   ========================================================================== */
(function(){
"use strict";
var U = window.S75.util, C = window.S75.comp, DEMO = window.S75.DEMO;
var esc=U.esc, clamp=U.clamp, fmtGBP=U.fmtGBP, scoreColor=U.scoreColor;
var gauge=C.gauge, miniGauge=C.miniGauge, donut=C.donut, sparkline=C.sparkline, trafficDot=C.trafficDot, waterfall=C.waterfall, pill=C.pill, card=C.card;

function pick(key){ return window.S75.SOURCE[key]==='live' ? window.S75.LIVE[key] : DEMO[key]; }
function badge(key){ return window.S75.sourceBadge(key); }

function modeExplanation(mode){
  var messages = {
    qualified: 'Three horses passed every official rule, so a full three-horse Patent is available today.',
    topRatedOnly: 'One or two horses passed every official rule. They are shown as official picks, but there is no full three-horse Patent today.',
    noBetDay: 'No horse passed every official rule today. Only the watchlist is shown, and it is not part of proof.'
  };
  return messages[mode] || 'The day\'s published selection mode is being checked.';
}

function plainReason(code){
  var messages = {
    ODDS_TOO_SHORT_FOR_CURRENT_GATE: 'The price was shorter than the official value range.',
    ODDS_TOO_BIG_FOR_CURRENT_GATE: 'The price was outside the official value range.',
    FIELD_TOO_SMALL: 'The field was too small for an official each-way selection.',
    NO_TIPSTER_CONSENSUS: 'No trusted tipster support was found.',
    SCORE_BELOW_TIPSTER_FLOOR_70: 'The score was below the required level.',
    SCORE_BELOW_75: 'The score was below the official 75-point line.',
    ENGINE_QUALIFIES_FALSE: 'The core engine gate did not pass.'
  };
  return messages[code] || String(code || '').replace(/_/g, ' ').toLowerCase();
}

/* ---------------- 1. STATUS ---------------- */
function renderStatus(){
  var d = pick('status');
  var audit = pick('selectionAudit') || {};
  var rows = [
    {label:'Morning picks', ok:d.picksGenerated, time:d.picksTime, sub:'selection run completed'},
    {label:'Results', ok:d.resultsSettled==='complete', time:d.resultsSettled==='complete'?'up to date':'still settling', sub:'results never change morning picks'},
    {label:'Learning', ok:d.learningRefreshed, time:d.learningTime, sub:d.learningRefreshed?'nightly memory refreshed':'nightly refresh scheduled'},
    {label:'AI cost', ok:!d.anthropicUsedToday, time:d.anthropicUsedToday?'fallback used':'paid search avoided', sub:(d.apiCallsAvoided||0)+' calls avoided'},
    {label:'Proof', ok:d.proofUnchanged, time:'unchanged', sub:'dashboard cannot alter proof'}
  ];
  var grid = rows.map(function(r){
    var level = r.ok ? 'green' : 'amber';
    return '<div class="card"><div class="card-label">'+trafficDot(level)+' '+esc(r.label)+'</div>'+
      '<div class="card-big">'+esc(r.time)+'</div><div class="card-sub">'+esc(r.sub)+'</div></div>';
  }).join('');
  var officialNames = ((audit.official||{}).names || []).join(', ') || 'None';
  var watchlistNames = ((audit.daily_watchlist||{}).names || []).join(', ') || 'None';
  var flatRadarNames = ((audit.flat_radar||{}).names || []).join(', ') || 'None today';
  var jumpsRadarNames = ((audit.jumps_radar||{}).names || []).join(', ') || 'None today';
  document.getElementById('panel-status').innerHTML =
    '<div class="plain" style="margin-bottom:18px"><strong>What this page shows:</strong> a simple health check for today\'s published data. Example: “Morning picks 10:00” means the selection run finished; it does not mean a bet has been placed.</div>'+
    '<div class="grid grid-auto" style="margin-bottom:18px">'+grid+'</div>'+
    '<div class="grid grid-3">'+
      card('Official picks today', gauge({value:d.officialCount,max:3,color:'var(--green)',label:d.officialCount,sub:'passed every rule'}))+
      card('Daily extra watchlist', gauge({value:d.watchlistCount,max:6,color:'var(--blue)',label:d.watchlistCount,sub:'learning only'}))+
      card('Today\'s format', '<div class="card-big" style="font-size:17px">'+esc(d.mode==='qualified'?'Full Patent':d.mode==='topRatedOnly'?'Partial day':'Watchlist only')+'</div><div class="card-sub">'+esc(modeExplanation(d.mode))+'</div>')+
    '</div>'+
    '<div class="card" style="margin-top:18px"><div class="card-label">Published selection check '+(audit.verified?'✓':'!')+'</div>'+
      '<div style="font-size:13px;font-weight:700">Official: '+esc(officialNames)+'</div><div class="card-sub">From '+esc(((audit.official||{}).source)||'picks.json')+'</div>'+
      '<div style="font-size:13px;font-weight:700;margin-top:10px">Daily extra watchlist: '+esc(watchlistNames)+'</div><div class="card-sub">From '+esc(((audit.daily_watchlist||{}).source)||'picks.json')+'</div>'+
      '<div class="card-sub" style="margin-top:10px">Separate Flat radar: '+esc(flatRadarNames)+'</div>'+
      '<div class="card-sub">Separate Jumps radar: '+esc(jumpsRadarNames)+'</div>'+
      '<div class="plain">'+esc(audit.note || 'Every dashboard list is checked against its matching published picks.json list.')+'</div></div>';
}

/* ---------------- 2. JOURNEY (signature) ---------------- */
function renderJourney(){
  var steps = pick('journey');
  var meanings = {
    'Races loaded':'Race cards received for today. This is a count, not a score.',
    'Runners scored':'Every runner assessed by Signal 75. Most will not become selections.',
    'Grandad matches':'Runners recognised in the historic horse-memory database.',
    'Tipster matches':'Runners with trusted tipster evidence. Support alone does not make an official pick.',
    'Warnings recorded':'Caution notes stored for review. They are not all automatic failures.',
    'Official picks':'Horses that passed every official rule.',
    'Watchlist tracked':'Extra horses stored for learning only, never added to proof.',
    'Learning days':'Completed days of evidence held for future review.'
  };
  var html = steps.map(function(s,i){
    var r=23,c=2*Math.PI*r;
    var color = s.pct>=0.9 ? 'var(--green)' : (s.pct>=0.5?'var(--gold)':'var(--red)');
    var id = 'jr'+i;
    var node = '<div class="jnode" style="animation-delay:'+(i*0.06)+'s">'+
      '<div class="jring"><svg width="52" height="52" viewBox="0 0 52 52">'+
        '<circle cx="26" cy="26" r="'+r+'" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="3"></circle>'+
        '<circle id="'+id+'" cx="26" cy="26" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="3" stroke-linecap="round" stroke-dasharray="'+c+'" stroke-dashoffset="'+c+'"></circle></svg>'+
        '<span class="ico">'+s.ico+'</span></div>'+
      '<div class="jnum">'+esc(s.num)+'</div><div class="jlabel">'+esc(s.label)+'</div></div>';
    return node + (i<steps.length-1 ? '<div class="jconn"></div>' : '');
  }).join('');
  var guide = steps.map(function(s){
    return '<div class="card"><div class="card-label">'+esc(s.label)+'</div><div class="card-big" style="font-size:18px">'+esc(s.num)+'</div><div class="card-sub">'+esc(meanings[s.label] || 'A recorded step in the daily selection process.')+'</div></div>';
  }).join('');
  document.getElementById('panel-journey').innerHTML =
    '<div class="plain" style="margin-bottom:18px"><strong>What this page shows:</strong> the path from raw race cards to published horses. The circles are counts, not ratings. Example: a runner can have a tipster match but still miss the official price or field-size rule.</div>'+
    '<div class="journey">'+html+'</div>'+
    '<div class="plain">Use Full Race View to see what was gathered for one horse and what actually moved its score.</div>'+
    '<div class="grid grid-auto" style="margin-top:18px">'+guide+'</div>';
  steps.forEach(function(s,i){
    setTimeout(function(){
      var el=document.getElementById('jr'+i); if(!el)return;
      var r=23,c=2*Math.PI*r; el.style.transition='stroke-dashoffset 1s ease'; el.style.strokeDashoffset=c-c*s.pct;
    }, 200+i*80);
  });
}

/* ---------------- 3. OFFICIAL PICKS ---------------- */
function renderOfficial(){
  var picks = pick('officialPicks');
  var audit = pick('selectionAudit') || {};
  var statusText = modeExplanation(audit.mode);
  if (!picks.length) {
    document.getElementById('panel-official').innerHTML = badge('officialPicks')+
      '<div class="plain" style="margin-bottom:14px"><strong>What this page shows:</strong> horses that passed every official check: score, price, field size and form-risk gates.</div>'+
      '<div class="card"><div class="card-big" style="font-size:20px">No official picks today</div><div class="plain">'+esc(statusText)+'</div></div>';
    return;
  }
  var html = picks.map(function(p){
    var eid = 'exp'+p.pickNumber;
    return '<div class="card raised" style="margin-bottom:14px">'+
      '<div style="display:flex; align-items:center; gap:18px; flex-wrap:wrap">'+
        gauge({value:p.score, color:scoreColor(p.score), size:84, sub:'SCORE'})+
        '<div style="flex:1; min-width:200px">'+
          '<div style="font-family:var(--body); font-weight:800; font-size:19px">'+esc(p.name)+'</div>'+
          '<div class="card-sub">'+esc(p.course)+' \u00b7 '+esc(p.time)+' \u00b7 '+esc(p.race)+' \u00b7 '+esc(p.jockey)+' / '+esc(p.trainer)+'</div>'+
          '<div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap">'+
            pill(p.badge.toUpperCase(),'gold')+pill(p.odds+' odds','green')+pill(p.tipsters+' tipsters \u00b7 '+p.consensusLevel,'blue')+
            '<span style="font-family:var(--mono);font-size:9px;color:var(--muted2);align-self:center">Official Pick '+p.pickNumber+'</span>'+
          '</div>'+
        '</div>'+
      '</div>'+
      '<div class="plain">'+esc(p.why)+'</div>'+
      '<div class="expand-toggle" onclick="window.S75ui.toggleExpand(\''+eid+'\')" id="tog'+eid+'"><span class="chev">\u203a</span> Score breakdown</div>'+
      '<div class="expand" id="'+eid+'">'+waterfall(p.parts)+'</div>'+
    '</div>';
  }).join('');
  document.getElementById('panel-official').innerHTML =
    '<div class="plain" style="margin-bottom:14px"><strong>What this page shows:</strong> horses that passed every official check: score, price, field size and form-risk gates. Example: a high score by itself is not enough; it must also pass the value and race rules. '+esc(statusText)+'</div>'+ badge('officialPicks') + html;
}

/* ---------------- 4. WATCHLIST ---------------- */
function renderWatchlist(){
  var list = pick('watchlist');
  var html = list.map(function(w){
    var reasons = (w.officialRejectionReasons || []).map(plainReason);
    var officialNote = reasons.length ? 'Why it is not official: '+reasons.join(' ') :
      (w.officialGate==='PASS' ? 'It passed the core gate but was not used as an official daily selection.' : 'Its official gate result was not available for this dashboard run.');
    return '<div class="card" style="margin-bottom:12px; border-color:rgba(56,189,248,.25)">'+
      '<div style="display:flex; align-items:center; gap:16px">'+
        gauge({value:w.score, color:'var(--blue)', size:64, sub:''})+
        '<div style="flex:1">'+
          '<div style="font-weight:700; font-size:15px">'+esc(w.name)+'</div>'+
          '<div class="card-sub">'+esc(w.course)+' \u00b7 '+esc(w.time)+' \u00b7 '+esc(w.odds)+' odds</div>'+
          '<div style="margin-top:6px"><span class="pill grey">'+esc(w.publishedList || 'Daily extra watchlist')+'</span></div>'+
        '</div>'+
      '</div><div class="plain">'+esc(w.reasonText)+'</div><div class="plain" style="border-left-color:var(--blue)">'+esc(officialNote)+'</div></div>';
  }).join('');
  document.getElementById('panel-watchlist').innerHTML =
    '<div class="plain" style="margin-bottom:14px"><strong>What this page shows:</strong> the <strong>Daily extra watchlist</strong> from <code>picks.json topRated</code>. It is not the full Flat or Jumps radar list. Example: a 100 score can still stay here if its price is too short or its race does not meet the official each-way rules. Watchlist horses never enter proof or the Patent.</div>'+
    badge('watchlist') + html;
}

/* ---------------- 5. FULL RACE VIEW ---------------- */
function renderRaceView(){
  var data = pick('raceView') || {};
  if (!data.races || !data.races.length) {
    document.getElementById('panel-raceview').innerHTML = badge('raceView') +
      '<div class="card"><div class="card-big" style="font-size:20px">Race comparison is not ready yet</div>'+
      '<div class="plain">This appears after the morning picks export has saved the runner-by-runner comparison. It does not affect the public picks or results.</div></div>';
    return;
  }
  var html = data.races.map(function(r, ri){
    var rows = r.runners.map(function(run){
      var color = U.STATUS_COLOR[run.status] || 'var(--muted2)';
      var rowCls = run.status==='official' ? 'official' : (run.status==='watchlist' ? 'watchlist' : (run.status==='not_scored'?'rejected':''));
      var id = 'rb'+ri+'_'+run.number;
      return '<div class="runner-row '+rowCls+'">'+
        '<div class="rnum">'+run.number+'</div>'+
        '<div><div class="rname">'+esc(run.name)+'</div><div class="rjt">'+esc(run.jockey)+' / '+esc(run.trainer)+'</div></div>'+
        '<div class="scorebar-mini"><div class="fill" id="'+id+'" style="background:'+color+'"></div></div>'+
        '<div style="font-family:var(--mono);font-size:10px;color:var(--muted2)">'+(run.score||'\u2014')+(run.warnings&&run.warnings.length?' <span title="'+esc(run.warnings[0])+'">\u26a0</span>':'')+'</div>'+
        '<div class="rodds">'+run.odds+'</div>'+
      '</div>';
    }).join('');
    return '<div class="card" style="margin-bottom:14px">'+
      '<div class="racepick"><div style="font-family:var(--display);font-size:16px;letter-spacing:1px">'+esc(r.course)+' '+esc(r.time)+'</div>'+
      '<span class="card-sub">'+esc(r.race_name)+' \u00b7 '+r.field_size+' runners</span></div>'+rows+'</div>';
  }).join('');
  document.getElementById('panel-raceview').innerHTML =
    badge('raceView') + html +
    '<div class="legend" style="margin-top:4px">'+
      '<span class="pill green">Official</span><span class="pill blue">Watchlist</span><span class="pill grey">Outside scoring range</span>'+
    '</div>';
  data.races.forEach(function(r,ri){
    r.runners.forEach(function(run){
      setTimeout(function(){
        var el=document.getElementById('rb'+ri+'_'+run.number);
        if(el) el.style.width = clamp(run.score,2,100)+'%';
      }, 150+run.number*70);
    });
  });
}

/* ---------------- 6. SCORE BREAKDOWN + PER-RACE LEDGER ---------------- */
function renderBreakdown(){
  var picks = pick('officialPicks');
  if (!picks.length) {
    document.getElementById('panel-breakdown').innerHTML = badge('officialPicks')+
      '<div class="card"><div class="card-big" style="font-size:20px">No official score breakdown today</div><div class="plain">There is no official pick because no horse passed every required gate. Use Full race view to see the score and warning breakdown for all runners.</div></div>';
    return;
  }
  var p = picks[0];
  var ledger = pick('ledger');
  document.getElementById('panel-breakdown').innerHTML =
    '<div class="grid grid-2">'+
      card(p.name+' \u2014 score breakdown', waterfall(p.parts))+
      card('What helped / what hurt / what\'s missing',
        '<div class="plain" style="border-color:var(--green); border-left-color:var(--green)">What helped: elite recent form, strong tipster consensus across 3 trusted sources.</div>'+
        '<div class="plain" style="border-left-color:var(--amber)">What hurt: nothing material today \u2014 no warnings fired.</div>'+
        '<div class="plain" style="border-left-color:var(--grey)">What\'s missing: no historical course profile match \u2014 this horse is fresh to Royal Ascot.</div>')+
    '</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Per-race ledger \u2014 '+esc(ledger.horse)+', '+esc(ledger.race)+'</h2></div>'+
    '<div class="ledger">'+
      '<div class="ledger-col"><h4>Gathered</h4>'+ledger.gathered.map(function(g){return '<div class="ledger-item"><span>'+esc(g.label)+'</span><span class="lv" style="color:var(--blue)">'+esc(g.v)+'</span></div>';}).join('')+'</div>'+
      '<div class="ledger-col"><h4>Used in score</h4>'+ledger.used.map(function(g){return '<div class="ledger-item"><span>'+esc(g.label)+'</span><span class="lv" style="color:var(--green)">'+esc(g.v)+'</span></div>';}).join('')+'</div>'+
    '</div>'+
    '<div class="plain">'+esc(ledger.note)+'</div>';
}

/* ---------------- 7. TIPSTER INTELLIGENCE ---------------- */
function renderTipster(){
  var t = pick('tipsterIntel');
  var matchPct = t.totalRunnersChecked ? (t.totalMatched/t.totalRunnersChecked*100) : 0;
  document.getElementById('panel-tipster').innerHTML = badge('tipsterIntel') +
    '<div class="grid grid-4" style="margin-bottom:18px">'+
      card('Matched', gauge({value:matchPct,color:'var(--gold)',label:t.totalMatched,sub:'of '+t.totalRunnersChecked}))+
      card('Sources tried', gauge({value:t.sourcesSuccessful,max:t.sourcesAttempted,color:'var(--blue)',label:t.sourcesSuccessful,sub:'of '+t.sourcesAttempted}))+
      card('Anthropic used', gauge({value:t.anthropicUsed?1:0,max:1,color:t.anthropicUsed?'var(--amber)':'var(--green)',label:t.anthropicUsed?'YES':'NO',sub:''}))+
      card('Calls avoided', gauge({value:t.estimatedCallsAvoided,max:10,color:'var(--green)',label:t.estimatedCallsAvoided,sub:'today'}))+
    '</div>'+
    '<div class="card" style="margin-bottom:16px"><div class="card-label">Source tier mix</div>'+
      '<div class="donut-wrap">'+donut(t.tierMix,116)+
      '<div class="donut-legend">'+
        '<div class="li"><span class="sw" style="background:var(--gold)"></span>Tier 1 \u2014 Racing Post, Timeform, Sporting Life</div>'+
        '<div class="li"><span class="sw" style="background:var(--blue)"></span>Tier 2 \u2014 named newspapers</div>'+
        '<div class="li"><span class="sw" style="background:var(--green)"></span>Tier 3 \u2014 NAP tables</div>'+
        '<div class="li"><span class="sw" style="background:var(--muted2)"></span>Tier 4 \u2014 OLBG, Oddschecker etc</div>'+
      '</div></div></div>'+
    '<div class="card"><div class="card-label">Strongest matches today</div>'+
      t.matched.map(function(m){
        return '<div style="display:flex;align-items:center;gap:14px;padding:9px 0;border-bottom:1px solid var(--border-soft)">'+
          miniGauge(m.weighted/8*100, 'var(--gold)', 40)+
          '<div style="flex:1"><div style="font-weight:700;font-size:13px">'+esc(m.horse)+'</div>'+
          '<div class="card-sub">'+m.sources.join(', ')+'</div></div>'+
          '<span class="pill blue">'+esc(m.level)+'</span></div>';
      }).join('') + '</div>';
}

/* ---------------- 8. GRANDAD'S BOOK / HORSE MEMORY ---------------- */
function renderMemory(){
  var db = pick('dbStatus');
  var hm = pick('horseMemory');
  var w = pick('winnerIntel') || [];
  var missData = pick('highConfidenceMisses') || {};
  var missCases = ((missData.today || {}).cases || []);
  var today = (db.matchHistory || [])[Math.max(0, (db.matchHistory || []).length-1)] || {matched:0,total:0};
  var todayPct = today.total ? today.matched/today.total*100 : 0;
  var horses = Object.keys(hm).map(function(k){ return hm[k]; });
  document.getElementById('panel-memory').innerHTML = badge('dbStatus') +
    '<div class="grid grid-3" style="margin-bottom:18px">'+
      card('Match rate today', gauge({value:todayPct,color:'var(--gold)',label:todayPct.toFixed(1)+'%',sub:today.matched+' / '+today.total}))+
      card('Profiles stored', '<div class="card-big">'+db.profileCount.toLocaleString()+'</div><div class="card-sub">individual horse profiles</div>')+
      card('Database size', '<div class="card-big">'+db.dbSizeMb+' MB</div><div class="card-sub">refreshed nightly at 23:10</div>')+
    '</div>'+
    '<div class="card" style="margin-bottom:18px"><div class="card-label">Match rate \u2014 recent runs</div>'+
      sparkline((db.matchHistory || []).filter(function(d){return d.total;}).map(function(d){return d.matched/d.total*100;}), 'var(--gold)', 240, 56)+
      '<div class="card-sub" style="margin-top:6px">'+((db.matchHistory || []).filter(function(d){return d.total;}).map(function(d){return d.date+': '+(d.matched/d.total*100).toFixed(1)+'%';}).join(' \u00b7 ') || 'First dashboard match record is being built today.')+'</div>'+
    '</div>'+
    '<div class="plain" style="margin-bottom:16px">An unmatched horse is never ignored \u2014 it still gets a normal Signal 75 score, it simply has no historical-profile lift or penalty. Loose guessing is deliberately avoided here: matching the wrong horse would be worse than using neutral history.</div>'+
    '<div class="grid grid-2">' + (horses.length ? horses.map(function(h){
      var conf = h.confidence==='Medium' ? 50 : (h.confidence==='High'?85:25);
      var confColor = h.confidence==='High'?'var(--green)':(h.confidence==='Medium'?'var(--amber)':'var(--grey)');
      return card(h.name, '<div style="display:flex;gap:14px;align-items:center">'+
        gauge({value:conf,color:confColor,size:60,label:h.confidence,sub:'CONF'})+
        '<div style="font-family:var(--mono);font-size:10px;color:var(--muted)">Runs logged: '+h.runsLogged+'<br>Wins '+h.knownWins+' \u00b7 Places '+h.knownPlaces+' \u00b7 Losses '+h.knownLosses+'<br>Last seen '+h.lastSeen+' at '+h.lastCourse+'</div></div>'+
        '<div class="plain">'+esc(h.insight)+'</div>');
    }).join('') : '<div class="card-sub">No current runners had a stored horse-memory match today.</div>') + '</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Post-race learning notes</h2></div>'+
    '<div class="grid grid-2">'+
      card('Winner intelligence', w.length ? w.slice(0,3).map(function(x){
        return '<div style="padding:8px 0;border-bottom:1px solid var(--border-soft)"><strong>'+esc(x.winner)+'</strong><div class="card-sub">'+esc(x.learning || x.action || 'Stored for future review.')+'</div></div>';
      }).join('') : '<div class="card-sub">Winner notes appear after settled results and the nightly learning run.</div>')+
      card('High-score misses', missCases.length ? missCases.slice(0,3).map(function(item){
        return '<div style="padding:8px 0;border-bottom:1px solid var(--border-soft)"><strong>'+esc(item.horse)+'</strong><div class="card-sub">Score '+esc(item.signal_score)+' · finished '+esc(item.finishing_position || 'unplaced')+' · '+esc(item.lesson || 'Logged for review.')+'</div></div>';
      }).join('') : '<div class="card-sub">No unusually strong horse with tipster support has been logged as a bad miss today.</div>')+
    '</div>';
}

/* ---------------- 9. WINNER INTELLIGENCE ---------------- */
function renderWinner(){
  var w = pick('winnerIntel');
  var rv = pick('radarVsOfficial');
  document.getElementById('panel-winner').innerHTML =
    '<div class="plain" style="margin-bottom:16px">Evidence only \u2014 nothing here automatically changes a rule.</div>'+
    (w.length ? w.map(function(x){
      return card(x.winner, '<div style="display:flex;gap:14px;align-items:center">'+
        gauge({value:x.score,color:'var(--blue)',size:60,sub:'SCORE'})+
        '<div><span class="pill blue">'+esc(x.status)+'</span><div class="card-sub" style="margin-top:6px">'+esc(x.learning)+'</div></div></div>'+
        '<div class="plain">Action: '+esc(x.action)+'</div>');
    }).join('') : '<div class="card"><div class="card-sub">Winner intelligence will appear after settled results and the nightly learning run.</div></div>') +
    '<div class="section-block-h" style="margin-top:18px"><h2>Radar vs official</h2></div>'+
    (rv.length ? rv.map(function(r){
      return '<div class="card" style="margin-bottom:10px; border-color:rgba(255,176,32,.3)">'+
        '<div class="card-label">'+r.tab.toUpperCase()+' \u2014 '+esc(r.verdict)+'</div>'+
        '<div style="font-size:12.5px"><span style="color:var(--red)">Official lost:</span> '+r.officialLost.join(', ')+'</div>'+
        '<div style="font-size:12.5px;margin-top:4px"><span style="color:var(--green)">Radar did better:</span> '+r.radarDidBetter.join(', ')+'</div></div>';
    }).join('') : '<div class="card"><div class="card-sub">No radar-versus-official comparison is available yet.</div></div>');
}

/* ---------------- 9B. HIGH-CONFIDENCE MISSES ---------------- */
function renderHighConfidenceMisses(){
  var data = pick('highConfidenceMisses') || {};
  var today = data.today || {};
  var history = data.history || {};
  var cases = today.cases || [];
  var html = cases.length ? cases.map(function(item){
    var position = item.finishing_position ? item.finishing_position+'th' : 'unplaced';
    var sources = (item.tipster_sources || []).join(', ') || 'stored tipster support';
    var warnings = (item.warning_signs_before_race || []).join(' ') || 'No clear pre-race warning was stored.';
    var missing = (item.missing_or_limited_data || []).join(', ') || 'No major stored-data gap.';
    return '<div class="card raised" style="margin-bottom:12px;border-color:rgba(239,68,68,.35)">'+
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><div style="font-size:18px;font-weight:800">'+esc(item.horse)+'</div><div class="card-sub">'+esc(item.course)+' · '+esc(item.time)+' · '+esc(item.selection_type)+'</div></div>'+pill('Score '+item.signal_score,'gold')+'</div>'+
      '<div style="display:flex;gap:7px;margin:10px 0;flex-wrap:wrap">'+pill(item.tipster_count+' tipster signal(s)','blue')+pill('Finished '+position,'red')+pill('BSP '+item.bsp,'grey')+'</div>'+
      '<div class="plain"><strong>What looked strong:</strong> '+esc((item.positive_signs_before_race || []).join(' ') || 'High Signal 75 score and tipster support.')+'</div>'+
      '<div class="plain" style="border-left-color:var(--amber)"><strong>What we are checking:</strong> '+esc(warnings)+'</div>'+
      '<div class="plain" style="border-left-color:var(--grey)"><strong>Data still missing:</strong> '+esc(missing)+'</div>'+
      '<div class="plain" style="border-left-color:var(--blue)"><strong>Learning note:</strong> '+esc(item.lesson || 'Continue collecting evidence.')+'</div>'+
      '<div class="card-sub">Tipster sources: '+esc(sources)+'</div></div>';
  }).join('') : '<div class="card"><div class="card-big" style="font-size:19px">No high-confidence misses today</div><div class="card-sub">A case appears only after a settled loss with a Signal 75 score of 90+ and recorded tipster support.</div></div>';
  var patterns = (history.repeated_patterns || []).length ? history.repeated_patterns.map(function(p){return pill(p.label.replace(/_/g,' ')+' · '+p.count,'amber');}).join(' ') : '<span class="card-sub">No repeated pattern proven yet.</span>';
  document.getElementById('panel-highmiss').innerHTML = badge('highConfidenceMisses')+
    '<div class="plain" style="margin-bottom:16px">This is a learning log for unusually strong horses that ran badly. One loss never changes a rule; repeated evidence is reviewed manually.</div>'+html+
    '<div class="card" style="margin-top:16px"><div class="card-label">Stored history</div><div class="card-big" style="font-size:22px">'+(history.case_count || 0)+' case(s)</div><div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">'+patterns+'</div></div>';
}

/* ---------------- 10. CONTINUOUS LEARNING ---------------- */
function renderLearning(){
  var l = pick('continuousLearning');
  var s = pick('shadowRules') || {variants:[], promotionRule:''};
  var tiles = l.findings.map(function(f){
    var color = U.SEVERITY_COLOR[f.severity];
    var pct = clamp(f.count/(f.threshold*2)*100, 5, 100);
    return '<div class="card"><div class="card-label">'+esc(f.code)+'</div>'+
      '<div style="display:flex;align-items:center;gap:12px">'+miniGauge(pct,color,50)+
      '<div><div class="card-big" style="font-size:20px">'+f.count+'</div><div class="card-sub">threshold '+f.threshold+'</div></div></div></div>';
  }).join('');
  document.getElementById('panel-learning').innerHTML = badge('continuousLearning') +
    '<div class="plain" style="margin-bottom:16px">ANALYSIS ONLY \u2014 no live rule has been changed by anything on this page. '+l.daysAnalysed+' days analysed.</div>'+
    '<div class="grid grid-2" style="margin-bottom:18px">'+
      card('Official place rate', gauge({value:l.officialPlaceRate,color:'var(--green)',label:l.officialPlaceRate+'%',sub:l.officialPlaced+'/'+l.officialAnalysed}))+
      card('Watchlist place rate', gauge({value:l.watchlistPlaceRate,color:'var(--blue)',label:l.watchlistPlaceRate+'%',sub:l.watchlistPlaced+'/'+l.watchlistAnalysed}))+
    '</div>'+
    '<div class="grid grid-auto">'+tiles+'</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Shadow rules being watched</h2></div>'+
    '<div class="plain" style="margin-bottom:12px">'+esc(s.promotionRule || 'Shadow rules are alternatives we monitor without changing the public picks.')+'</div>'+
    (s.variants && s.variants.length ? s.variants.map(function(v){
      return '<div class="card" style="margin-bottom:10px"><div class="card-label">'+esc(v.name)+'</div><div class="card-big" style="font-size:20px">'+esc(v.roi)+'% ROI</div><div class="card-sub">'+esc(v.picks)+' picks · '+fmtGBP(v.profit)+' · beat live '+esc(v.daysBeatLive)+'/15 days'+(v.note?' · '+esc(v.note):'')+'</div></div>';
    }).join('') : '<div class="card"><div class="card-sub">No shadow comparison has been published for this run yet.</div></div>');
}

/* ---------------- 18. SHADOW & UNUSED OPTIONS (NEW) ---------------- */
function renderShadow(){
  var s = pick('shadowRules');
  var rows = s.variants.map(function(v){
    var cls = v.status==='candidate' ? 'candidate' : '';
    return '<div class="shadow-row '+cls+'">'+
      '<div class="shadow-side">'+gauge({value:s.live.roi,max:120,color:'var(--muted2)',size:54,label:s.live.roi+'%',sub:'ROI'})+
        '<div class="info"><div class="name">LIVE \u2014 '+esc(s.live.name)+'</div><div class="meta">'+s.live.picks+' picks \u00b7 '+fmtGBP(s.live.profit)+'</div></div></div>'+
      '<div class="shadow-vs">vs</div>'+
      '<div class="shadow-side">'+gauge({value:v.roi,max:120,color:v.status==='candidate'?'var(--green)':'var(--gold)',size:54,label:v.roi+'%',sub:'ROI'})+
        '<div class="info"><div class="name">'+esc(v.name)+'</div><div class="meta">'+v.picks+' picks \u00b7 '+fmtGBP(v.profit)+' \u00b7 beat live '+v.daysBeatLive+'/15 days'+(v.note?' \u00b7 '+esc(v.note):'')+'</div></div></div>'+
    '</div>';
  }).join('') || '<div class="card"><div class="card-sub">No shadow comparison has been published for this run yet.</div></div>';
  document.getElementById('panel-shadow').innerHTML = badge('shadowRules') +
    '<div class="plain" style="margin-bottom:16px">'+esc(s.promotionRule)+'</div>'+
    rows +
    '<div class="legend" style="margin-top:10px"><span class="pill green">Promotion candidate</span><span class="pill gold">Still watching</span></div>';
}

/* ---------------- 11. PATENT VIABILITY ---------------- */
function renderPatent(){
  var p = pick('patentViability');
  if (!p.legs.length) {
    document.getElementById('panel-patent').innerHTML = '<div class="card"><div class="card-big" style="font-size:20px">No Patent today</div><div class="plain">Signal 75 did not create a three-horse official Patent because no horse met every required rule. This is a no-bet day, not a missing calculation.</div></div>';
    return;
  }
  var ewReturns = p.legs.map(function(l){ return l.odds * p.placeFraction; });
  var worstTwoWin = p.legs.reduce(function(sum,l,i){
    var others = p.legs.filter(function(_,j){return j!==i;});
    return Math.max(sum, others.reduce(function(s,o){return s+o.odds;},0));
  }, 0);
  var status = worstTwoWin >= p.stake ? 'GREEN' : (worstTwoWin >= p.stake*0.8 ? 'AMBER' : 'RED');
  var color = status==='GREEN'?'var(--green)':(status==='AMBER'?'var(--amber)':'var(--red)');
  document.getElementById('panel-patent').innerHTML =
    '<div class="grid grid-2">'+
      card('Viability', gauge({value:status==='GREEN'?100:(status==='AMBER'?60:25),color:color,label:status,sub:'STATUS'})+
        '<div class="plain">Projected, based on displayed odds \u2014 if one leg loses, the other two winners are projected to recover the stake. Not guaranteed.</div>')+
      card('Today\'s legs', p.legs.map(function(l){return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-soft);font-size:12.5px"><span>'+esc(l.name)+'</span><span style="font-family:var(--mono)">'+l.odds+'</span></div>';}).join('') +
        '<div class="card-sub" style="margin-top:8px">Stake: '+fmtGBP(p.stake)+' \u00b7 '+p.lines+' lines \u00b7 1/'+(1/p.placeFraction)+' place fraction</div>')+
    '</div>';
}

/* ---------------- 12. PROOF VS WATCHLIST ---------------- */
function renderProof(){
  var perf = pick('performance');
  var l = pick('continuousLearning');
  var p = pick('patentViability') || {legs:[]};
  var patentHtml = p.legs && p.legs.length ? p.legs.map(function(leg){
    return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-soft);font-size:12.5px"><span>'+esc(leg.name)+'</span><span style="font-family:var(--mono)">'+leg.odds+'</span></div>';
  }).join('') + '<div class="card-sub" style="margin-top:8px">Stake: '+fmtGBP(p.stake)+' · '+p.lines+' lines</div>' :
    '<div class="card-sub">No full three-horse Patent was available for this day. Partial days are not treated like normal full Patent days.</div>';
  document.getElementById('panel-proof').innerHTML =
    '<div class="grid grid-3">'+
      card('Official proof', gauge({value:perf.roi,max:150,color:'var(--gold)',label:perf.roi+'%',sub:'ROI'})+
        sparkline(perf.recentProfits,'var(--gold)',200,46)+
        '<div class="card-sub">'+fmtGBP(perf.totalProfit)+' total \u00b7 '+perf.bettingDays+' betting days \u00b7 win rate '+perf.winRate+'%</div>')+
      card('Watchlist learning', gauge({value:l.watchlistPlaceRate,max:100,color:'var(--blue)',label:l.watchlistPlaceRate+'%',sub:'PLACE RATE'})+
        '<div class="card-sub">'+l.watchlistPlaced+' placed of '+l.watchlistAnalysed+' tracked \u2014 separate record, never counted in proof</div>')+
      card('Patent check', patentHtml)+
    '</div>';
}

/* ---------------- 13. AUTOMATION HEALTH ---------------- */
function renderAutomation(){
  var a = pick('automation');
  var cost = pick('apiCostControl') || {};
  var cov = pick('dataCoverage') || {};
  var manual = a.manualByDesign || a.manual_by_design || [];
  var tiles = a.jobs.map(function(j){
    return '<div class="autotile"><div class="ah">'+trafficDot(U.JOB_COLOR[j.status])+'<span class="at-time">'+esc(j.time||'\u2014')+'</span></div>'+
      '<div class="at-label">'+esc(j.label)+'</div>'+(j.detail?'<div class="card-sub">'+esc(j.detail)+'</div>':'')+'</div>';
  }).join('');
  document.getElementById('panel-automation').innerHTML = badge('automation') +
    '<div class="autogrid" style="margin-bottom:18px">'+tiles+'</div>'+
    '<div class="card"><div class="card-label">Manual by design \u2014 not automation failures</div>'+
      manual.map(function(m){return '<div style="font-size:12.5px;padding:5px 0;border-bottom:1px solid var(--border-soft)">'+esc(m)+'</div>';}).join('')+
      '<div class="plain">These run only with explicit approval on purpose \u2014 recovery, deployment, and outward-facing posting are exactly the categories that shouldn\'t run unattended.</div></div>'+
    '<div class="grid grid-3" style="margin-top:18px">'+
      card('AI/API cost control', gauge({value:cost.calls_today || 0,max:cost.max_anthropic_calls_per_day || 1,color:(cost.calls_today||0)===0?'var(--green)':'var(--amber)',label:cost.calls_today || 0,sub:'paid calls today'})+
        '<div class="card-sub">'+esc(cost.anthropic_fallback_only?'Fallback only':'Standard mode')+' · '+esc(cost.calls_avoided || 0)+' calls avoided</div>')+
      card('Data coverage', '<div class="card-big" style="font-size:20px">'+esc(cov.runnersLoaded || 0)+' runners</div><div class="card-sub">'+esc(cov.racesProcessed || 0)+' races · '+esc(cov.runnersMatched || 0)+' history matches · '+esc(cov.tipsterMatched || 0)+' tipster matches</div>')+
      card('Safety', '<div class="safe-row"><div class="safe-check">✓</div><div style="font-size:13px">Read-only local dashboard</div></div><div class="safe-row"><div class="safe-check">✓</div><div style="font-size:13px">No picks, scoring, proof or settlement changed here</div></div><div class="safe-row"><div class="safe-check">✓</div><div style="font-size:13px">Private data stays on this Mac</div></div>')+
    '</div>';
}

/* ---------------- 14. API COST ---------------- */
function renderApiCost(){
  var a = pick('apiCostControl');
  document.getElementById('panel-apicost').innerHTML = badge('apiCostControl') +
    '<div class="grid grid-3">'+
      card('Calls today', gauge({value:a.calls_today,max:a.max_anthropic_calls_per_day,color:a.calls_today===0?'var(--green)':'var(--amber)',label:a.calls_today,sub:'of '+a.max_anthropic_calls_per_day+' cap'}))+
      card('Calls avoided', gauge({value:a.calls_avoided,max:10,color:'var(--green)',label:a.calls_avoided,sub:'today'}))+
      card('Mode', '<div class="card-big" style="font-size:16px">'+(a.anthropic_fallback_only?'FALLBACK ONLY':'STANDARD')+'</div><div class="card-sub">'+esc(a.preferred_model)+'</div>')+
    '</div>';
}

/* ---------------- 15. DATA COVERAGE ---------------- */
function renderCoverage(){
  var c = pick('dataCoverage');
  var matchPct = c.runnersLoaded ? c.runnersMatched/c.runnersLoaded*100 : 0;
  var resultsPct = c.resultsTotal ? c.resultsSettled/c.resultsTotal*100 : 0;
  document.getElementById('panel-coverage').innerHTML =
    '<div class="grid grid-4">'+
      card('Runners loaded', '<div class="card-big">'+c.runnersLoaded+'</div><div class="card-sub">across '+c.racesProcessed+' races</div>')+
      card('Profile matched', gauge({value:matchPct,color:'var(--gold)',label:matchPct.toFixed(0)+'%',sub:c.runnersMatched+' matched'}))+
      card('Tipster matched', '<div class="card-big">'+c.tipsterMatched+'</div><div class="card-sub">runners with tipster mentions</div>')+
      card('Results settled', gauge({value:resultsPct,color:'var(--blue)',label:resultsPct.toFixed(0)+'%',sub:c.resultsSettled+' of '+c.resultsTotal}))+
    '</div>'+
    '<div class="plain">Unmatched horses are new or limited-history runners, not an error.</div>';
}

/* ---------------- 16. TIMELINE ---------------- */
function renderTimeline(){
  var t = pick('timeline');
  var html = t.map(function(e){
    var color = e.status==='done'?'var(--green)':(e.status==='pending'?'var(--amber)':'var(--grey)');
    return '<div class="trow"><div class="tmark" style="background:'+color+'"></div>'+
      '<div class="ttime">'+esc(e.time)+'</div><div class="tlabel">'+esc(e.label)+'</div>'+
      '<div class="tsub">'+esc(e.status)+'</div>'+
      (e.detail?'<div class="card-sub" style="grid-column:2 / -1;margin-top:-4px">'+esc(e.detail)+'</div>':'')+'</div>';
  }).join('');
  document.getElementById('panel-timeline').innerHTML =
    '<div class="plain" style="margin-bottom:18px"><strong>What this page shows:</strong> today\'s planned process, not a race-by-race result list. Green means finished, amber means waiting for races/results, and grey means scheduled. Example: “10:00 picks published” means the morning list is locked in.</div>'+
    '<div class="timeline">'+html+'</div>';
}

/* ---------------- 17. SAFETY ---------------- */
function renderSafety(){
  var rows = [
    'Read-only dashboard \u2014 yes',
    'No proof files changed \u2014 yes',
    'No picks changed \u2014 yes',
    'No scoring logic changed \u2014 yes',
    'No settlement changed \u2014 yes',
    'Access control: dashboard is bound to this Mac only (127.0.0.1)',
    'Admin-only files live in local dashboard/data/, ignored by Git and separate from public site data'
  ];
  document.getElementById('panel-safety').innerHTML = '<div class="card">' +
    rows.map(function(r){ return '<div class="safe-row"><div class="safe-check">\u2713</div><div style="font-size:13px">'+esc(r)+'</div></div>'; }).join('') +
    '</div><div class="card-sub" style="margin-top:10px">Last dashboard refresh: '+new Date().toLocaleString('en-GB')+'</div>';
}

/* ---------------- EXECUTIVE STRATEGY DASHBOARD ---------------- */
function visualBar(label, value, max, color){
  max = max || 100;
  var pct = clamp((Number(value)||0) / max * 100, 2, 100);
  return '<div class="bar-row"><div class="bar-label">'+esc(label)+'</div>'+
    '<div class="bar-track"><div class="bar-fill" style="width:'+pct+'%;background:'+color+'"></div></div>'+
    '<div class="bar-value">'+esc(value)+'</div></div>';
}

function scoreChip(value, label, color){
  return '<div class="score-chip" style="--chip:'+color+'"><div class="score-chip-value">'+esc(value)+'</div><div class="score-chip-label">'+esc(label)+'</div></div>';
}

function strategyStrip(){
  return '<div class="strategy-strip">'+
    '<div class="strategy-step"><div class="strategy-num">01</div><div class="strategy-word">FIND</div><div class="strategy-text">score, price, race fit, form and market data</div></div>'+
    '<div class="strategy-step"><div class="strategy-num">02</div><div class="strategy-word">CONFIRM</div><div class="strategy-text">tipsters, rival memory and horse history</div></div>'+
    '<div class="strategy-step"><div class="strategy-num">03</div><div class="strategy-word">PROTECT</div><div class="strategy-text">bad form, weak price, small field and weak Patent blocks</div></div>'+
    '<div class="strategy-step"><div class="strategy-num">04</div><div class="strategy-word">LEARN</div><div class="strategy-text">what won, what beat us, what we missed</div></div>'+
  '</div>';
}

function allRaceRunners(){
  var data = pick('raceView') || {};
  var rows = [];
  (data.races || []).forEach(function(race){
    (race.runners || []).forEach(function(r){
      rows.push(Object.assign({course: race.course, time: race.time, race_name: race.race_name}, r));
    });
  });
  return rows;
}

function renderStrategyToday(){
  var status = pick('status') || {};
  var perf = pick('performance') || {};
  var cover = pick('dataCoverage') || {};
  var learning = pick('continuousLearning') || {};
  var official = pick('officialPicks') || [];
  var watchlist = pick('watchlist') || [];
  var matchedPct = cover.runnersLoaded ? cover.runnersMatched / cover.runnersLoaded * 100 : 0;
  var placePct = Number(learning.watchlistPlaceRate || 0);
  var mode = status.mode==='qualified' ? 'Full Patent' : (status.mode==='topRatedOnly' ? 'Partial day' : 'Watchlist only');
  document.getElementById('panel-status').innerHTML =
    '<div class="hero-grid">'+
      '<div class="hero-card"><div class="hero-kicker">Signal 75 strategy</div><div class="hero-title">Find. Confirm. Protect. Learn.</div>'+
      '<div class="hero-copy">A simple view of how the system works. First it finds strong horses, then checks outside evidence, protects the bet, and learns from the result.</div>'+
      strategyStrip()+'</div>'+
      '<div class="metric-wall">'+
        '<div class="metric-tile"><div class="label">Today</div><div class="value" style="color:var(--gold)">'+esc(mode)+'</div><div class="hint">'+esc(modeExplanation(status.mode))+'</div></div>'+
        '<div class="metric-tile"><div class="label">Official picks</div><div class="value" style="color:var(--green)">'+official.length+'</div><div class="hint">passed every live rule</div></div>'+
        '<div class="metric-tile"><div class="label">History matched</div><div class="value" style="color:var(--blue)">'+matchedPct.toFixed(0)+'%</div><div class="hint">'+esc(cover.runnersMatched || 0)+' of '+esc(cover.runnersLoaded || 0)+' runners</div></div>'+
        '<div class="metric-tile"><div class="label">ROI</div><div class="value" style="color:var(--green)">'+esc(perf.roi || 0)+'%</div><div class="hint">'+fmtGBP(perf.totalProfit || 0)+' current proof profit</div></div>'+
      '</div>'+
    '</div>'+
    '<div class="grid grid-3">'+
      '<div class="chart-card"><div class="chart-title">Today at a glance</div>'+
        visualBar('Official picks', official.length, 3, 'var(--green)')+
        visualBar('Watchlist', watchlist.length, Math.max(3, watchlist.length), 'var(--blue)')+
        visualBar('Tipster matches', cover.tipsterMatched || 0, Math.max(1, cover.runnersLoaded || 1), 'var(--gold)')+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Proof and learning</div>'+
        '<div class="donut-wrap">'+donut([{value:Number(perf.profitableDays || 0), color:'var(--green)'},{value:Math.max(0, Number(perf.bettingDays || 0)-Number(perf.profitableDays || 0)), color:'var(--red)'}], 112)+
        '<div class="donut-legend"><div class="li"><span class="sw" style="background:var(--green)"></span>Profitable days</div><div class="li"><span class="sw" style="background:var(--red)"></span>Losing days</div><div class="li">'+esc(perf.profitableDays || 0)+' of '+esc(perf.bettingDays || 0)+' days</div></div></div>'+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Learning strength</div>'+
        gauge({value:placePct,color:'var(--blue)',label:placePct.toFixed(0)+'%',sub:'WATCHLIST PLACE'})+
        '<div class="card-sub">Watchlist is learning evidence only. It does not count in proof.</div>'+
      '</div>'+
    '</div>';
}

function renderFind(){
  var official = pick('officialPicks') || [];
  var runners = allRaceRunners().filter(function(r){return r.scored !== false;}).sort(function(a,b){return (b.score||0)-(a.score||0);}).slice(0,8);
  var officialHtml = official.length ? official.map(function(p){
    return '<div class="sport-card sport-green" style="margin-bottom:12px">'+
      '<div class="sport-card-head">'+
        gauge({value:p.score,color:scoreColor(p.score),size:76,sub:'SCORE'})+
        '<div style="flex:1"><div class="sport-horse">'+esc(p.name)+'</div><div class="sport-meta">'+esc(p.course)+' · '+esc(p.time)+' · '+esc(p.odds)+' odds · '+esc(p.tipsters)+' tipsters</div></div>'+
        scoreChip(p.score, 'PTS', scoreColor(p.score))+
      '</div>'+
      waterfall(p.parts || [])+'</div>';
  }).join('') : '<div class="card"><div class="card-big" style="font-size:20px">No official picks today</div><div class="card-sub">The system did not find enough horses passing the live rules.</div></div>';
  document.getElementById('panel-find').innerHTML =
    '<div class="section-hero find"><div><div class="hero-kicker">Stage 01</div><div class="section-hero-title">Find the strongest runners</div><div class="section-hero-copy">Signal 75 ranks every runner by score, price, race fit, form, field size, market data and history.</div></div>'+
      '<div class="hero-stat">'+scoreChip(runners.length, 'TOP RUNNERS', 'var(--blue)')+'</div></div>'+
    '<div class="grid grid-2" style="margin-top:16px">'+
      '<div>'+officialHtml+'</div>'+
      '<div class="chart-card"><div class="chart-title">Top scored runners</div>'+
        (runners.length ? runners.map(function(r){return visualBar(r.name, Math.round(r.score || 0), 100, r.status==='official'?'var(--green)':(r.status==='watchlist'?'var(--blue)':'var(--gold)'));}).join('') : '<div class="empty">Runner comparison will appear after picks run.</div>')+
      '</div>'+
    '</div>';
}

function renderConfirm(){
  var tip = pick('tipsterIntel') || {};
  var db = pick('dbStatus') || {};
  var hm = pick('horseMemory') || {};
  var runners = allRaceRunners();
  var rivalRows = runners.filter(function(r){return r.rivalMemoryOverlay;}).slice(0,6);
  var matchPct = tip.totalRunnersChecked ? tip.totalMatched / tip.totalRunnersChecked * 100 : 0;
  var horseCount = Object.keys(hm).length;
  document.getElementById('panel-confirm').innerHTML =
    '<div class="section-hero confirm"><div><div class="hero-kicker">Stage 02</div><div class="section-hero-title">Confirm with outside evidence</div><div class="section-hero-copy">This checks trusted tipsters, stored horse memory, and rival evidence before the horse is trusted publicly.</div></div>'+
      '<div class="hero-stat">'+scoreChip(tip.totalMatched || 0, 'TIP MATCHES', 'var(--gold)')+'</div></div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      '<div class="chart-card"><div class="chart-title">Tipster coverage</div>'+gauge({value:matchPct,color:'var(--gold)',label:tip.totalMatched || 0,sub:'MATCHED'})+
        '<div class="card-sub">'+esc(tip.sourcesSuccessful || 0)+' sources worked · '+esc(tip.estimatedCallsAvoided || 0)+' paid calls avoided</div></div>'+
      '<div class="chart-card"><div class="chart-title">Source mix</div><div class="donut-wrap">'+donut(tip.tierMix || [], 112)+'<div class="donut-legend"><div class="li"><span class="sw" style="background:var(--gold)"></span>Top sources</div><div class="li"><span class="sw" style="background:var(--blue)"></span>Named papers/sites</div><div class="li"><span class="sw" style="background:var(--green)"></span>NAP tables</div></div></div></div>'+
      '<div class="chart-card"><div class="chart-title">Horse memory</div>'+gauge({value:horseCount,max:Math.max(1, horseCount),color:'var(--blue)',label:horseCount,sub:'ACTIVE'})+
        '<div class="card-sub">'+esc(db.profileCount || 0)+' stored profiles in the database.</div></div>'+
    '</div>'+
    '<div class="chart-card" style="margin-top:16px"><div class="chart-title">Rival memory support</div>'+
      (rivalRows.length ? rivalRows.map(function(r){return visualBar(r.name, r.rivalMemoryOverlay.points || 0, 8, 'var(--green)');}).join('') : '<div class="empty">No runner in the current comparison has a rival-memory boost today.</div>')+
    '</div>';
}

function renderProtect(){
  var status = pick('status') || {};
  var p = pick('patentViability') || {legs:[]};
  var runners = allRaceRunners();
  var warningRows = runners.filter(function(r){return (r.warnings || []).length;}).slice(0,8);
  var legCount = (p.legs || []).length;
  document.getElementById('panel-protect').innerHTML =
    '<div class="section-hero protect"><div><div class="hero-kicker">Stage 03</div><div class="section-hero-title">Protect the bet</div><div class="section-hero-copy">Bad form, poor value, small fields, same-race clashes and weak Patent legs are blocked before publication.</div></div>'+
      '<div class="hero-stat">'+scoreChip(warningRows.length, 'WARNINGS', 'var(--red)')+'</div></div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      card('Patent protection', gauge({value:legCount,max:3,color:legCount===3?'var(--green)':'var(--amber)',label:legCount+'/3',sub:'LEGS'})+
        '<div class="card-sub">'+esc(modeExplanation(status.mode))+'</div>')+
      card('Official gates', '<div class="funnel">'+
        '<div class="funnel-step"><div class="funnel-name">Score</div><div class="funnel-block" style="width:100%"></div><div class="bar-value">75+</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Price</div><div class="funnel-block" style="width:82%"></div><div class="bar-value">value</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Field</div><div class="funnel-block" style="width:70%"></div><div class="bar-value">8+</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Form</div><div class="funnel-block" style="width:62%"></div><div class="bar-value">safe</div></div></div>')+
      card('One race rule', '<div class="card-big" style="font-size:24px;color:var(--green)">ON</div><div class="card-sub">No two official picks should come from the same race.</div>')+
    '</div>'+
    '<div class="chart-card" style="margin-top:16px"><div class="chart-title">Current warnings</div>'+
      (warningRows.length ? warningRows.map(function(r){return visualBar(r.name, (r.warnings || []).length, 4, 'var(--red)');}).join('') : '<div class="empty">No active runner warnings in the current comparison.</div>')+
    '</div>';
}

function renderLearnDashboard(){
  var l = pick('continuousLearning') || {findings:[]};
  var s = pick('shadowRules') || {variants:[]};
  var margin = pick('resultMarginIntel') || {summary:{}, records:[]};
  var marginRows = margin.records || [];
  var maxFinding = Math.max.apply(null, (l.findings || []).map(function(f){return f.count || 0;}).concat([1]));
  var marginCards = marginRows.length ? marginRows.slice(0,4).map(function(row){
    var tone = ((row.flags || []).indexOf('HEAVILY_BEATEN') >= 0) ? 'var(--red)' : ((row.position === 1 || row.position === '1') ? 'var(--green)' : 'var(--gold)');
    return '<div class="sport-card" style="margin-bottom:10px;border-color:'+tone+'55">'+
      '<div class="sport-card-head"><div>'+scoreChip(row.signal_score || 0, 'SCORE', tone)+'</div><div style="flex:1">'+
        '<div class="sport-name">'+esc(row.horse || 'Unknown')+'</div>'+
        '<div class="sport-meta">'+esc(row.date || '')+' · '+esc(row.course || '')+' '+esc(row.time || '')+' · '+esc(row.selection_type || 'learning')+'</div>'+
      '</div></div>'+
      '<div class="plain" style="border-left-color:'+tone+'"><strong>'+esc(row.finish_impression || 'Result note')+':</strong> '+esc(row.distance_summary || 'Margin stored.')+'</div>'+
      (row.beat_high_signal_horses && row.beat_high_signal_horses.length ? '<div class="card-sub" style="margin-top:8px">Beat high-signal horse(s): '+esc(row.beat_high_signal_horses.join(', '))+'</div>' : '')+
    '</div>';
  }).join('') : '<div class="empty">Margin notes appear when verified result notes include winning distances or beaten lengths.</div>';
  document.getElementById('panel-learn').innerHTML =
    '<div class="section-hero learn"><div><div class="hero-kicker">Stage 04</div><div class="section-hero-title">Learn from every result</div><div class="section-hero-copy">The system records winners, beaten picks, watchlist performance, false consensus and repeat horse patterns.</div></div>'+
      '<div class="hero-stat">'+scoreChip((l.findings || []).length, 'FINDINGS', 'var(--blue)')+'</div></div>'+
    '<div class="grid grid-2" style="margin-top:16px">'+
      '<div class="chart-card"><div class="chart-title">Learning findings</div>'+
        ((l.findings || []).length ? l.findings.slice(0,9).map(function(f){return visualBar(f.code.replace(/_/g,' '), f.count, maxFinding, U.SEVERITY_COLOR[f.severity] || 'var(--blue)');}).join('') : '<div class="empty">Learning findings appear after the morning review.</div>')+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Shadow rules</div>'+
        ((s.variants || []).length ? s.variants.slice(0,6).map(function(v){return visualBar(v.name, v.roi || 0, 150, v.status==='candidate'?'var(--green)':'var(--gold)');}).join('') : '<div class="empty">No shadow rule comparison available yet.</div>')+
      '</div>'+
    '</div>'+
    '<div class="grid grid-2" style="margin-top:16px">'+
      card('Official place rate', gauge({value:l.officialPlaceRate || 0,color:'var(--green)',label:(l.officialPlaceRate || 0)+'%',sub:'OFFICIAL'}))+
      card('Watchlist place rate', gauge({value:l.watchlistPlaceRate || 0,color:'var(--blue)',label:(l.watchlistPlaceRate || 0)+'%',sub:'WATCHLIST'}))+
    '</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Winning margins and beaten distances</h2></div>'+
    '<div class="grid grid-3" style="margin-bottom:16px">'+
      card('Margin notes stored', gauge({value:(margin.summary || {}).with_margin_notes || 0,max:Math.max(1,(margin.summary || {}).with_margin_notes || 0),color:'var(--blue)',label:(margin.summary || {}).with_margin_notes || 0,sub:'RUNS'}))+
      card('Decisive winners', gauge({value:(margin.summary || {}).decisive_winners || 0,max:Math.max(1,(margin.summary || {}).decisive_winners || 0),color:'var(--green)',label:(margin.summary || {}).decisive_winners || 0,sub:'WON WELL'}))+
      card('Well beaten', gauge({value:(margin.summary || {}).well_beaten || 0,max:Math.max(1,(margin.summary || {}).well_beaten || 0),color:'var(--red)',label:(margin.summary || {}).well_beaten || 0,sub:'WARNING'}))+
    '</div>'+
    '<div class="grid grid-2">'+
      '<div>'+marginCards+'</div>'+
      '<div class="chart-card"><div class="chart-title">What this teaches</div>'+
        '<div class="plain"><strong>Won well:</strong> horses that win clearly can be marked as stronger future evidence, especially if they beat one of our high-score horses.</div>'+
        '<div class="plain"><strong>Well beaten:</strong> horses beaten a long way can be tracked as a warning next time unless conditions clearly change.</div>'+
        '<div class="plain"><strong>Close finish:</strong> horses beaten under a length may deserve a softer view than a normal losing result.</div>'+
      '</div>'+
    '</div>';
}

/* ---------------------------------------------------------------------
   NAV CONFIG + BOOT
   --------------------------------------------------------------------- */
var NAV = [
  {group:'SIGNAL 75', items:[
    {id:'status', label:'Today', ico:'\u29bf', render:renderStrategyToday, keys:['status','selectionAudit','performance','dataCoverage','continuousLearning','officialPicks','watchlist']},
    {id:'find', label:'Find', ico:'\u2315', render:renderFind, keys:['officialPicks','raceView']},
    {id:'confirm', label:'Confirm', ico:'\u2726', render:renderConfirm, keys:['tipsterIntel','dbStatus','horseMemory','raceView']},
    {id:'protect', label:'Protect', ico:'\u26a0', render:renderProtect, keys:['status','patentViability','raceView']},
    {id:'learn', label:'Learn', ico:'\u27f2', render:renderLearnDashboard, keys:['continuousLearning','shadowRules','resultMarginIntel']},
    {id:'proof', label:'Results', ico:'\u21d5', render:renderProof, keys:['performance','continuousLearning','patentViability']},
    {id:'automation', label:'System', ico:'\u2699', render:renderAutomation, keys:['automation','apiCostControl','dataCoverage']}
  ]}
];
var FLAT = [];
NAV.forEach(function(g){ g.items.forEach(function(it){ FLAT.push(it); }); });

var loadedOnce = {};
function activate(id){
  FLAT.forEach(function(it){
    var panel = document.getElementById('panel-'+it.id);
    var railBtn = document.getElementById('rail-'+it.id);
    var tabBtn = document.getElementById('tab-'+it.id);
    var active = it.id===id;
    if(panel) panel.classList.toggle('active', active);
    if(railBtn) railBtn.classList.toggle('active', active);
    if(tabBtn) tabBtn.classList.toggle('active', active);
  });
  var it = FLAT.filter(function(x){return x.id===id;})[0];
  if(!it) return;
  if(!loadedOnce[id]){
    loadedOnce[id] = true;
    var fetches = (it.keys||[]).map(function(k){ return window.S75.loadReal(k, [k+'.json']); });
    Promise.all(fetches).then(function(){ it.render(); });
  }
  it.render();
}

function buildNav(){
  var rail = document.getElementById('rail-groups');
  var tabbar = document.getElementById('tabbar');
  var stage = document.getElementById('stage-panels');
  var railHtml = '', tabHtml = '', stageHtml = '';
  NAV.forEach(function(g){
    railHtml += '<div class="rail-group"><div class="rail-group-label">'+g.group+'</div>';
    g.items.forEach(function(it){
      railHtml += '<button class="rail-btn" id="rail-'+it.id+'" onclick="window.S75ui.activate(\''+it.id+'\')">'+
        '<span class="ico">'+it.ico+'</span>'+it.label+'</button>';
      tabHtml += '<button class="tb-btn" id="tab-'+it.id+'" onclick="window.S75ui.activate(\''+it.id+'\')">'+
        '<span class="ico">'+it.ico+'</span>'+it.label+'</button>';
      stageHtml += '<div class="panel" id="panel-'+it.id+'"></div>';
    });
    railHtml += '</div>';
  });
  rail.innerHTML = railHtml;
  tabbar.innerHTML = tabHtml;
  stage.innerHTML = stageHtml;
}

function toggleExpand(id){
  var el = document.getElementById(id), tog = document.getElementById('tog'+id);
  if(!el) return;
  el.classList.toggle('open'); if(tog) tog.classList.toggle('open');
}

function boot(){
  // A dashboard build without the local marker must never show sample data.
  // This is what public GitHub Pages visitors see: no private operational data.
  window.S75.loadReal('dashboardReady', ['dashboard_ready.json']).then(function(marker){
    if (!marker || marker.local_only !== true) {
      document.body.innerHTML = '<main style="max-width:640px;margin:14vh auto;padding:32px;font-family:Arial,sans-serif;color:#f4f4f5;background:#0d0d12;border:1px solid #30303a;border-radius:8px"><div style="color:#f4c542;font-weight:700;letter-spacing:1px">SIGNAL 75 INTELLIGENCE</div><h1 style="font-size:30px;margin:18px 0 10px">Private dashboard</h1><p style="line-height:1.6;color:#c8c8d2">This read-only dashboard is available only on the protected local Signal 75 system. No private intelligence data is published on the public website.</p></main>';
      return;
    }
    buildNav();
    activate('status');
    var clock = document.getElementById('liveClock');
    function tick(){ if(clock) clock.textContent = new Date().toLocaleString('en-GB',{weekday:'short',hour:'2-digit',minute:'2-digit'}); }
    tick(); setInterval(tick, 30000);
    // Keep an open local dashboard current after the scheduled morning and
    // nightly exports, without touching any Signal 75 data or decisions.
    var feedVersion = marker.generated_at || '';
    setInterval(function(){
      fetch('./data/dashboard_ready.json', {cache:'no-store'})
        .then(function(response){ return response.ok ? response.json() : null; })
        .then(function(latest){
          if (latest && latest.generated_at && latest.generated_at !== feedVersion) window.location.reload();
        })
        .catch(function(){});
    }, 60000);
  });
}

window.S75ui = { activate:activate, toggleExpand:toggleExpand, boot:boot };
document.addEventListener('DOMContentLoaded', boot);

})();
