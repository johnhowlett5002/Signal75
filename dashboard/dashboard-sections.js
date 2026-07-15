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
    qualified: 'Three horses passed every official rule, so today is an each-way Patent.',
    topRatedOnly: 'One or two horses passed every official rule. Signal 75 does not force extra horses, so the bet becomes a Single or Double.',
    noBetDay: 'No horse passed every official rule today. No official bet is placed.'
  };
  return messages[mode] || 'The day\'s published selection mode is being checked.';
}

function officialBetModel(count){
  count = Number(count || 0);
  if(count >= 3) return {
    count:count, kind:'patent', label:'Each-way Patent', shortLabel:'Patent', stake:14, lines:14,
    summary:'3 official selections. Full Patent available.',
    explanation:'Three official selections make a £1 each-way Patent: 3 singles, 3 doubles and 1 treble, all each-way.'
  };
  if(count === 2) return {
    count:count, kind:'double', label:'Each-way Double', shortLabel:'Double', stake:6, lines:6,
    summary:'2 official selections. Not enough for a Patent, so today is a Double.',
    explanation:'Two horses backed — one win double, one place double, plus two singles.'
  };
  if(count === 1) return {
    count:count, kind:'single', label:'Each-way Single', shortLabel:'Single', stake:2, lines:2,
    summary:'1 official selection. Not enough for a Double or Patent, so today is a Single.',
    explanation:'One official selection makes a £1 each-way Single: £1 win and £1 place.'
  };
  return {
    count:0, kind:'none', label:'No official bet', shortLabel:'No bet', stake:0, lines:0,
    summary:'0 official selections. No bet today.',
    explanation:'No horse passed every official rule, so Signal 75 stays out.'
  };
}

function officialBetModelFromPicks(){
  return officialBetModel((pick('officialPicks') || []).length);
}

function cleanKey(value){
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function raceCodeFromText(value){
  var raw = cleanKey(value);
  if(!raw) return '';
  if(raw.indexOf('hurdle') >= 0 || raw.indexOf('hrd') >= 0 ||
     raw.indexOf('chase') >= 0 || raw.indexOf('chs') >= 0 ||
     raw.indexOf('bumper') >= 0 || raw.indexOf('nhf') >= 0 ||
     raw.indexOf('national hunt') >= 0 || raw.indexOf('jump') >= 0) return 'jumps';
  if(raw.indexOf('flat') >= 0) return 'flat';
  return '';
}

function raceCodeFromRace(race){
  var fromName = raceCodeFromText((race.race_name || '')+' '+(race.name || ''));
  if(fromName) return fromName;
  var fromType = raceCodeFromText((race.race_type || '')+' '+(race.type || ''));
  if(fromType) return fromType;
  var course = cleanKey(race.course);
  var raceText = cleanKey((race.race_name || '')+' '+(race.name || '')+' '+(race.distance || ''));
  if(course === 'uttoxeter' && /\b[23]m/.test(raceText)) return 'jumps';
  return '';
}

function raceCodeFromSelection(sel, typeLookup){
  var key = cleanKey(sel.course)+'|'+String(sel.time || '');
  if(typeLookup[key]) return typeLookup[key];
  var fromText = raceCodeFromText((sel.race || '')+' '+(sel.race_name || '')+' '+(sel.type || '')+' '+(sel.race_type || ''));
  if(fromText) return fromText;
  var course = cleanKey(sel.course);
  var raceText = cleanKey(sel.race || sel.race_name || '');
  if(course === 'uttoxeter' && /\b[23]m/.test(raceText)) return 'jumps';
  return '';
}

function officialSelectionGroups(){
  var official = pick('officialPicks') || [];
  var raceView = pick('raceView') || {};
  var typeLookup = {};
  (raceView.races || []).forEach(function(race){
    var key = cleanKey(race.course)+'|'+String(race.time || '');
    typeLookup[key] = raceCodeFromRace(race);
  });
  var groups = {flat:[], jumps:[], unknown:[]};
  official.forEach(function(sel){
    var type = raceCodeFromSelection(sel, typeLookup);
    if(type === 'jumps') groups.jumps.push(sel);
    else if(type === 'flat') groups.flat.push(sel);
    else groups.unknown.push(sel);
  });
  if(groups.unknown.length && !groups.flat.length && !groups.jumps.length) groups.flat = groups.unknown.splice(0);
  return groups;
}

function officialBetSections(){
  var groups = officialSelectionGroups();
  var sections = [];
  if(groups.flat.length) sections.push({name:'Flat', picks:groups.flat, model:officialBetModel(groups.flat.length)});
  if(groups.jumps.length) sections.push({name:'Jumps', picks:groups.jumps, model:officialBetModel(groups.jumps.length)});
  if(groups.unknown.length) sections.push({name:'Other', picks:groups.unknown, model:officialBetModel(groups.unknown.length)});
  if(!sections.length) sections.push({name:'Today', picks:[], model:officialBetModel(0)});
  return sections;
}

function officialBetSummaryText(){
  var sections = officialBetSections().filter(function(s){ return s.picks.length; });
  if(!sections.length) return 'No official bet';
  return sections.map(function(s){ return s.name+' '+s.model.shortLabel; }).join(' + ');
}

function officialBetCardsHtml(){
  return officialBetSections().map(function(section){
    var model = section.model;
    var bg = model.kind === 'patent' ? 'rgba(240,192,64,.10)' : model.kind === 'double' ? 'rgba(56,189,248,.10)' : model.kind === 'single' ? 'rgba(148,163,184,.10)' : 'rgba(31,41,55,.75)';
    var border = model.kind === 'patent' ? 'rgba(240,192,64,.42)' : model.kind === 'double' ? 'rgba(56,189,248,.35)' : model.kind === 'single' ? 'rgba(148,163,184,.32)' : 'rgba(107,114,128,.35)';
    var color = model.kind === 'double' ? 'var(--blue)' : model.kind === 'single' ? 'var(--muted)' : 'var(--gold)';
    var headline = model.kind === 'patent' ? 'FULL PATENT TODAY' : model.kind === 'double' ? 'EACH-WAY DOUBLE TODAY' : model.kind === 'single' ? 'EACH-WAY SINGLE TODAY' : 'NO BET TODAY';
    var line = model.kind === 'patent' ? '3 picks found · £14 total stake · 14 lines' : model.kind === 'double' ? '2 picks found · £6 total stake · 6 lines' : model.kind === 'single' ? '1 pick found · £2 total stake · 2 lines' : 'No horse met all the required criteria today';
    return '<div class="card" style="border-color:'+border+';background:'+bg+';margin:0 0 12px 0;padding:16px 18px">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase;letter-spacing:.08em">'+esc(section.name)+' official bet</div>'+
      '<div style="font-family:var(--display);font-size:24px;color:'+color+';line-height:1.3;margin-top:4px">'+esc(headline)+'</div>'+
      '<div style="font-size:15px;line-height:1.8;color:var(--text);margin-top:4px;font-weight:750">'+esc(line)+'</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--muted);margin-top:4px">'+esc(model.explanation)+'</div>'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.7;margin-top:8px">No weak extra horse forced.</div>'+
    '</div>';
  }).join('');
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

function asArray(v){ return Array.isArray(v) ? v : []; }
function firstDefined(){
  for(var i=0;i<arguments.length;i++){
    if(arguments[i] !== undefined && arguments[i] !== null && arguments[i] !== '') return arguments[i];
  }
  return '';
}
function num(v, fallback){
  var n = Number(v);
  return Number.isFinite(n) ? n : (fallback || 0);
}
function signedMoney(v){
  var n = num(v, 0);
  return (n > 0 ? '+' : (n < 0 ? '-' : '')) + '£' + Math.abs(n).toFixed(2).replace(/\.00$/, '');
}
function signedPct(v){
  var n = num(v, 0);
  return (n > 0 ? '+' : '') + n.toFixed(1).replace(/\.0$/, '') + '%';
}

var TRAFFIC_TEXT = {
  COLLECTING: {
    label:'Collecting evidence',
    verdict:'Under 14 settled days. Too early to say anything.'
  },
  WATCHING: {
    label:'Watching - needs more data',
    verdict:'14-29 settled days. Evidence building. Not enough to act on.'
  },
  PROMISING: {
    label:'Promising - ready for review',
    verdict:'30+ settled days. Positive delta. Still positive without best day.'
  },
  RISKY: {
    label:'Risky - not improving results',
    verdict:'Negative delta vs live. Consistently worse than the live system.'
  },
  PROMOTION_CANDIDATE: {
    label:'Review needed - awaiting your decision',
    verdict:'All criteria met. No challenger goes live without John\'s approval.'
  },
  APPROVED_BY_JOHN: {
    label:'Approved by John - ready to promote',
    verdict:'Approved, but still shown separately from live proof until switched on.'
  },
  ARCHIVED: {
    label:'Archived',
    verdict:'This challenger was tested and archived.'
  }
};
function trafficState(stage){
  var s = String(stage || 'COLLECTING').toUpperCase();
  if(s === 'TOO_EARLY' || s === 'MISSING') return 'COLLECTING';
  if(s === 'DO_NOT_USE' || s === 'FAILED' || s === 'FAIL') return 'RISKY';
  if(s === 'READY_FOR_REVIEW') return 'PROMISING';
  if(s === 'APPROVED') return 'APPROVED_BY_JOHN';
  if(s === 'TESTED_AND_REJECTED' || s === 'INCONCLUSIVE_AT_30_DAYS') return 'ARCHIVED';
  return TRAFFIC_TEXT[s] ? s : 'COLLECTING';
}
function trafficLight(stage, size, includeText){
  var state = trafficState(stage);
  var text = TRAFFIC_TEXT[state] || TRAFFIC_TEXT.COLLECTING;
  var cls = 'traffic-light traffic-light-'+(size || 'large')+' state-'+state.toLowerCase().replace(/_/g, '-');
  var label = includeText === false ? '' : '<div class="traffic-copy"><div class="traffic-label">'+esc(text.label)+'</div><div class="traffic-verdict">'+esc(text.verdict)+'</div></div>';
  return '<div class="'+cls+'">'+
    '<svg class="traffic-svg" viewBox="0 0 48 116" role="img" aria-label="'+esc(text.label)+'">'+
      '<rect x="7" y="4" width="34" height="108" rx="17" class="tl-case"></rect>'+
      '<circle cx="24" cy="25" r="11" class="tl-bulb tl-red"></circle>'+
      '<circle cx="24" cy="58" r="11" class="tl-bulb tl-amber"></circle>'+
      '<circle cx="24" cy="91" r="11" class="tl-bulb tl-green"></circle>'+
      '<circle cx="24" cy="91" r="15" class="tl-gold-ring"></circle>'+
    '</svg>'+label+
  '</div>';
}
function challengerSummaryData(){
  var nested = window.S75.LIVE.challengerSummary || {};
  var legacy = pick('challengerLab') || {};
  return nested && (nested.pre_race_challengers || nested.live || nested.promotion_candidates) ? nested : legacy;
}
function challengerLatestData(){ return window.S75.LIVE.challengerLatest || {}; }
function promotionCandidateRows(){
  var p = window.S75.LIVE.promotionCandidates || {};
  var s = challengerSummaryData();
  return asArray(p.promotion_candidates || p.candidates || s.promotion_candidates || s.promotionCandidates);
}
function challengerRows(){
  var s = challengerSummaryData();
  var latest = challengerLatestData();
  return asArray(s.pre_race_challengers || s.challengers || latest.pre_race_challengers);
}
function normalizeChallenger(row){
  return {
    id:firstDefined(row.id, row.rule_id, row.name, 'challenger'),
    name:firstDefined(row.name, row.label, row.id, 'Challenger'),
    stage:trafficState(firstDefined(row.promotion_stage, row.promotion_status, row.status, 'COLLECTING')),
    days:num(firstDefined(row.days_tested, row.daysTested), 0),
    settled:num(firstDefined(row.settled_days, row.settledDays), 0),
    picks:num(firstDefined(row.total_picks, row.totalPicks), 0),
    roi:num(firstDefined(row.roi, row.paper_roi), 0),
    profit:num(firstDefined(row.total_profit, row.profit), 0),
    deltaRoi:num(firstDefined(row.delta_vs_live_roi, row.deltaVsLiveRoi, row.delta_roi), 0),
    deltaProfit:num(firstDefined(row.delta_vs_live_profit, row.deltaVsLiveProfit, row.delta_profit), 0),
    warning:firstDefined(row.sample_warning, row.sampleWarning, row.warning, ''),
    criteria:row.promotion_criteria || row.promotionCriteria || {},
    raw:row
  };
}
function bestChallengerState(rows, candidates){
  if(asArray(candidates).length) return 'PROMOTION_CANDIDATE';
  var states = asArray(rows).map(function(r){ return normalizeChallenger(r).stage; });
  if(states.indexOf('APPROVED_BY_JOHN') >= 0) return 'APPROVED_BY_JOHN';
  if(states.indexOf('PROMOTION_CANDIDATE') >= 0) return 'PROMOTION_CANDIDATE';
  if(states.indexOf('PROMISING') >= 0) return 'PROMISING';
  if(states.indexOf('WATCHING') >= 0) return 'WATCHING';
  if(states.length && states.every(function(s){ return s === 'RISKY'; })) return 'RISKY';
  if(states.indexOf('RISKY') >= 0) return 'WATCHING';
  return 'COLLECTING';
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
      card('Official selections today', gauge({value:d.officialCount,max:3,color:'var(--green)',label:d.officialCount,sub:'passed every rule'}))+
      card('Daily extra watchlist', gauge({value:d.watchlistCount,max:6,color:'var(--blue)',label:d.watchlistCount,sub:'learning only'}))+
      card('Today\'s official bet', '<div class="card-big" style="font-size:17px">'+esc(officialBetSummaryText())+'</div><div class="card-sub">Flat and Jumps are kept separate. The bet type is based on official selections in each section.</div>')+
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
    'Horse memory matches':'Runners recognised in the historic horse-memory database.',
    'Rival graph edges':'Stored horse-vs-horse links: who beat who, who lost to who, and short chain evidence.',
    'Tipster matches':'Runners with trusted tipster evidence. Support alone does not make an official pick.',
    'Warnings recorded':'Caution notes stored for review. They are not all automatic failures.',
    'Official picks':'Official selections that passed every rule.',
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
      '<div class="card"><div class="card-big" style="font-size:20px">No official selections today</div><div class="plain">'+esc(statusText)+'</div></div>';
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
            '<span style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted2);align-self:center">Official Selection '+p.pickNumber+'</span>'+
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
    '<div class="plain" style="margin-bottom:14px"><strong>What this page shows:</strong> the <strong>Daily extra watchlist</strong> from <code>picks.json topRated</code>. It is not the full Flat or Jumps radar list. Example: a 100 score can still stay here if its price is too short or its race does not meet the official each-way rules. Watchlist horses never enter proof or the official bet.</div>'+
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
        '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted2)">'+(run.score||'\u2014')+(run.warnings&&run.warnings.length?' <span title="'+esc(run.warnings[0])+'">\u26a0</span>':'')+'</div>'+
        '<div class="rodds">'+run.odds+'</div>'+
      '</div>';
    }).join('');
    return '<div class="card" style="margin-bottom:14px">'+
      '<div class="racepick"><div style="font-family:var(--body);font-weight:800;font-size:15px;letter-spacing:0">'+esc(r.course)+' '+esc(r.time)+'</div>'+
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
        '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted)">Runs logged: '+h.runsLogged+'<br>Wins '+h.knownWins+' \u00b7 Places '+h.knownPlaces+' \u00b7 Losses '+h.knownLosses+'<br>Last seen '+h.lastSeen+' at '+h.lastCourse+'</div></div>'+
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
  var betSections = officialBetSections();
  var hasSelections = betSections.some(function(section){ return section.picks.length; });
  document.getElementById('panel-patent').innerHTML =
    '<div class="section-hero protect"><div><div class="hero-kicker">Official bet type</div><div class="section-hero-title">'+esc(officialBetSummaryText())+'</div><div class="section-hero-copy">Flat and Jumps are kept separate. They are not combined into a Patent unless one section has three official selections.</div></div></div>'+
    (hasSelections ? officialBetCardsHtml() : '<div class="card"><div class="card-big" style="font-size:20px">No official bet</div><div class="plain">No horse met every required rule. No Single, Double or Patent is placed.</div></div>');
}

/* ---------------- 12. PROOF VS WATCHLIST ---------------- */
function renderProof(){
  var perf = pick('performance');
  var l = pick('continuousLearning');
  var sections = officialBetSections();
  var hasSelections = sections.some(function(section){ return section.picks.length; });
  var betHtml = hasSelections ? sections.map(function(section){
    if(!section.picks.length) return '';
    var rows = section.picks.map(function(leg){
      return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-soft);font-size:12.5px"><span>'+esc(leg.name)+'</span><span style="font-family:var(--mono)">'+leg.odds+'</span></div>';
    }).join('');
    return '<div style="margin-bottom:12px"><div class="card-label">'+esc(section.name)+' — '+esc(section.model.label)+'</div>'+rows+
      '<div class="card-sub" style="margin-top:8px">Stake guide '+fmtGBP(section.model.stake)+' · '+esc(section.model.lines)+' lines</div><div class="card-sub">'+esc(section.model.summary)+'</div></div>';
  }).join('') :
    '<div class="card-sub">No official bet was available for this day. No Single, Double or Patent is counted in proof.</div>';
  document.getElementById('panel-proof').innerHTML =
    '<div class="grid grid-3">'+
      card('Official proof', gauge({value:perf.roi,max:150,color:'var(--gold)',label:perf.roi+'%',sub:'ROI'})+
        sparkline(perf.recentProfits,'var(--gold)',200,46)+
        '<div class="card-sub">'+fmtGBP(perf.totalProfit)+' total \u00b7 '+perf.bettingDays+' betting days \u00b7 win rate '+perf.winRate+'%</div>')+
      card('Watchlist learning', gauge({value:l.watchlistPlaceRate,max:100,color:'var(--blue)',label:l.watchlistPlaceRate+'%',sub:'PLACE RATE'})+
        '<div class="card-sub">'+l.watchlistPlaced+' placed of '+l.watchlistAnalysed+' tracked \u2014 separate record, never counted in proof</div>')+
      card('Official bet type', betHtml)+
    '</div>';
}

/* ---------------- 13. AUTOMATION HEALTH ---------------- */
function renderAutomation(){
  var a = pick('automation');
  var cost = pick('apiCostControl') || {};
  var cov = pick('dataCoverage') || {};
  var rows = challengerRows();
  var candidates = promotionCandidateRows();
  var summary = challengerSummaryData();
  var bestState = bestChallengerState(rows, candidates);
  var maxSettled = rows.reduce(function(m,r){ return Math.max(m, normalizeChallenger(r).settled); }, 0);
  var candidateCount = candidates.length;
  var manual = a.manualByDesign || a.manual_by_design || [];
  var tiles = a.jobs.map(function(j){
    if(j.name === 'daily_health_check'){
      var failed = j.status === 'failed';
      var detail = j.detail || (failed ? 'ATTENTION: checks failed - review needed' : 'All checks passed');
      return '<div class="autotile" style="'+(failed?'border-left:3px solid var(--gold);':'')+'"><div class="ah">'+trafficDot(failed?'red':'green')+'<span class="at-time">'+esc(j.time||'\u2014')+'</span></div>'+
        '<div class="at-label">Daily health check</div><div class="card-sub">'+esc(detail)+'</div></div>';
    }
    return '<div class="autotile"><div class="ah">'+trafficDot(U.JOB_COLOR[j.status])+'<span class="at-time">'+esc(j.time||'\u2014')+'</span></div>'+
      '<div class="at-label">'+esc(j.label)+'</div>'+(j.detail?'<div class="card-sub">'+esc(j.detail)+'</div>':'')+'</div>';
  }).join('');
  var labRow = '<div class="challenger-system-wrap">'+
    '<div class="system-subhead">Challenger Lab</div>'+
    '<div class="challenger-system-row '+(candidateCount ? 'has-candidate' : '')+'">'+
      trafficLight(bestState, 'small', false)+
      '<div class="challenger-system-main"><div class="challenger-system-title">Challenger Lab</div>'+
        '<div class="card-sub">'+esc(rows.length)+' challengers running · '+esc(maxSettled || (summary.live || {}).betting_days || 0)+' settled days</div></div>'+
      '<div class="challenger-system-action">'+
        '<span class="candidate-badge '+(candidateCount ? 'gold' : 'grey')+'">'+esc(candidateCount)+' '+(candidateCount===1?'candidate':'candidates')+'</span>'+
        '<button type="button" class="text-link" onclick="window.S75ui.activate(\'learn\')">View Lab</button>'+
      '</div>'+
    '</div>'+
  '</div>';
  document.getElementById('panel-automation').innerHTML = badge('automation') +
    '<div class="autogrid" style="margin-bottom:18px">'+tiles+'</div>'+
    labRow+
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
    '<div class="strategy-step"><div class="strategy-num">02</div><div class="strategy-word">CHECK</div><div class="strategy-text">tipsters, rival memory and horse history</div></div>'+
    '<div class="strategy-step"><div class="strategy-num">03</div><div class="strategy-word">PROTECT</div><div class="strategy-text">bad form, weak price, small field and weak extra legs</div></div>'+
    '<div class="strategy-step"><div class="strategy-num">04</div><div class="strategy-word">LAB</div><div class="strategy-text">test future ideas safely before any live change</div></div>'+
  '</div>';
}

function allRaceRunners(){
  var data = pick('raceView') || {};
  var rows = [];
  (data.races || []).forEach(function(race){
    (race.runners || []).forEach(function(r){
      rows.push(Object.assign({course: race.course, time: race.time, race_name: race.race_name, field_size: race.field_size}, r));
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
  var betSummary = officialBetSummaryText();
  var matchedPct = cover.runnersLoaded ? cover.runnersMatched / cover.runnersLoaded * 100 : 0;
  var placePct = Number(learning.watchlistPlaceRate || 0);
  document.getElementById('panel-status').innerHTML =
    '<div class="hero-grid">'+
      '<div class="hero-card"><div class="hero-kicker">Signal 75 strategy</div><div class="hero-title">Find. Confirm. Protect. Learn.</div>'+
      '<div class="hero-copy">A simple view of how the system works. First it finds strong horses, then checks outside evidence, protects the bet, and learns from the result.</div>'+
      strategyStrip()+'</div>'+
      '<div class="metric-wall">'+
        '<div class="metric-tile"><div class="label">Today</div><div class="value" style="color:var(--gold)">'+esc(betSummary)+'</div><div class="hint">Flat and Jumps are measured separately.</div></div>'+
        '<div class="metric-tile"><div class="label">Official selections</div><div class="value" style="color:var(--green)">'+official.length+'</div><div class="hint">passed every live rule</div></div>'+
        '<div class="metric-tile"><div class="label">History matched</div><div class="value" style="color:var(--blue)">'+matchedPct.toFixed(0)+'%</div><div class="hint">'+esc(cover.runnersMatched || 0)+' of '+esc(cover.runnersLoaded || 0)+' runners</div></div>'+
        '<div class="metric-tile"><div class="label">ROI</div><div class="value" style="color:var(--green)">'+esc(perf.roi || 0)+'%</div><div class="hint">'+fmtGBP(perf.totalProfit || 0)+' current proof profit</div></div>'+
      '</div>'+
    '</div>'+
    '<div class="grid grid-3">'+
      '<div class="chart-card"><div class="chart-title">Today at a glance</div>'+
        visualBar('Official selections', official.length, 3, 'var(--green)')+
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

function renderTodaysPicks(){
  var official = pick('officialPicks') || [];
  var watchlist = pick('watchlist') || [];
  var runners = allRaceRunners().filter(function(r){return r.scored !== false;});
  var groups = officialSelectionGroups();
  var officialKeys = {};
  official.forEach(function(p){ officialKeys[normaliseNameLocal(p.name)+'|'+normaliseNameLocal(p.course)+'|'+String(p.time || '')] = true; });
  function normaliseNameLocal(value){
    return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
  }
	  function scoreRows(parts){
    if(Array.isArray(parts)) return parts;
    parts = parts || {};
    return [
      {label:'PRICE', value:Number(parts.price || 0), color:'var(--blue)'},
      {label:'TIPS', value:Number(parts.tips || 0), color:'var(--gold)'},
      {label:'RACE', value:Number(parts.race || 0), color:'var(--green)'},
      {label:'FORM', value:Number(parts.form || 0), color:'var(--green)'}
	    ];
	  }
	  function qualityClass(q){
	    var rating = String((q||{}).quality_rating || '').toLowerCase();
	    if(rating === 'strong') return 'green';
	    if(rating === 'solid') return 'blue';
	    if(rating === 'moderate') return 'gold';
	    return 'red';
	  }
	  function qualityAuditBlock(p){
	    var q = p.qualityAudit || {};
	    if(!q.quality_rating){
	      var audit = pick('pickQualityAudit') || {};
	      var target = normaliseNameLocal(p.name)+'|'+normaliseNameLocal(p.course)+'|'+String(p.time || '');
	      (audit.picks || []).some(function(row){
	        var key = normaliseNameLocal(row.name)+'|'+normaliseNameLocal(row.course)+'|'+String(row.time || '');
	        if(key === target){ q = row; return true; }
	        return false;
	      });
	    }
	    if(!q.quality_rating) return '';
	    var rating = String(q.quality_rating || 'MODERATE').toUpperCase();
	    var border = rating === 'FLAGGED' || rating === 'WEAK' ? 'var(--red)' : (rating === 'MODERATE' ? 'var(--gold)' : 'var(--green)');
	    var flags = (q.flags || []).slice(0, 4).map(function(flag){
	      return '<div style="font-family:var(--mono);font-size:10px;line-height:1.7;color:var(--muted2);margin-top:4px">- '+esc(flag)+'</div>';
	    }).join('');
	    return '<div style="margin:0 0 14px 0;padding:12px 14px;border-left:3px solid '+border+';background:rgba(255,255,255,.035);border-radius:0 var(--r-sm) var(--r-sm) 0">'+
	      '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">'+
	        pill((rating === 'FLAGGED' ? '⚠ ' : '')+'QUALITY: '+rating, qualityClass(q))+
	        '<span style="font-family:var(--mono);font-size:10px;color:var(--muted2);line-height:1.6">pre-race audit · scoring impact none</span>'+
	      '</div>'+
	      '<div style="font-size:13px;line-height:1.7;color:var(--muted)">'+esc(q.plain_english || 'Pre-race quality audit available.')+'</div>'+
	      flags+
	    '</div>';
	  }
  function runnerForPick(p){
    var key = normaliseNameLocal(p.name)+'|'+normaliseNameLocal(p.course)+'|'+String(p.time || '');
    for(var i=0;i<runners.length;i++){
      if(officialKeyForRunner(runners[i]) === key) return runners[i];
    }
    return {};
  }
  function bar(width, color){
    return '<span style="display:inline-block;width:82px;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;border:1px solid rgba(255,255,255,.08);vertical-align:middle;margin-right:8px">'+
      '<span style="display:block;width:'+clamp(width,12,100)+'%;height:100%;background:'+color+'"></span></span>';
  }
  function splitRivals(text){
    return String(text || '').split(',').map(function(v){ return v.trim(); }).filter(Boolean);
  }
  function rivalEvidenceBlock(p){
    var run = runnerForPick(p);
    var overlay = run.rivalMemoryOverlay || p.rivalMemoryOverlay || null;
    var direct = [], warnings = [], notes = overlay && overlay.notes ? overlay.notes : [];
    notes.forEach(function(note){
      var m = String(note || '').match(/previously beat today&apos;s rival\(s\) (.+)\.|previously beat today's rival\(s\) (.+)\./i);
      if(m) direct = direct.concat(splitRivals(m[1] || m[2]));
      var d = String(note || '').match(/previously dominated today&apos;s rival\(s\) (.+)\.|previously dominated today's rival\(s\) (.+)\./i);
      if(d) direct = direct.concat(splitRivals(d[1] || d[2]));
      var w = String(note || '').match(/previously beaten by today&apos;s rival\(s\) (.+)\.|previously beaten by today's rival\(s\) (.+)\./i);
      if(w) warnings = warnings.concat(splitRivals(w[1] || w[2]));
    });
    var seen = {};
    direct = direct.filter(function(v){ var k=normaliseNameLocal(v); if(!k || seen[k]) return false; seen[k]=true; return true; }).slice(0,4);
    warnings = warnings.filter(function(v){ return !!normaliseNameLocal(v); }).slice(0,2);
    var rows = direct.map(function(name, idx){
      var pct = 88 - (idx * 16);
      return '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:8px">'+
        '<div style="min-width:0"><div style="font-weight:800;font-size:14px;line-height:1.35;color:var(--text)">'+esc(name)+'</div>'+
        '<div style="font-size:12px;line-height:1.5;color:var(--muted2)">Beaten before in recorded race memory</div></div>'+
        '<div style="display:flex;align-items:center;gap:4px;white-space:nowrap">'+bar(pct,'rgba(0,232,122,.55)')+'<span style="font-weight:800;color:var(--green);font-size:13px">edge</span></div>'+
      '</div>';
    }).join('');
    var warningHtml = warnings.map(function(name){
      return '<div style="margin-top:9px;padding:9px 10px;border-radius:8px;background:rgba(240,192,64,.12);color:var(--gold);font-size:13px;line-height:1.55">'+
        bar(52,'rgba(240,192,64,.55)')+'Past warning against '+esc(name)+'</div>';
    }).join('');
    if(!rows && !warningHtml){
      rows = '<div style="margin-top:8px;font-size:13px;line-height:1.7;color:var(--muted)">No direct rival-memory edge found for today&apos;s field. Pick still passed the live score, price, race and form checks.</div>';
    }
    return '<div style="padding:14px 16px;background:rgba(255,255,255,.035);border-top:1px solid rgba(255,255,255,.08)">'+
      '<div style="display:flex;gap:10px;align-items:flex-start">'+
        '<div style="color:var(--gold);font-size:18px;line-height:1">✦</div>'+
        '<div style="min-width:0;flex:1"><div style="font-weight:850;font-size:15px;line-height:1.4;color:var(--text)">Our special race memory</div>'+
        '<div style="font-size:13px;line-height:1.6;color:var(--muted)">Signal 75 checked whether this horse has beaten rivals in today&apos;s race before.</div>'+
        rows+warningHtml+'</div></div></div>';
  }
  function officialCard(p){
    return '<div class="card" style="margin-bottom:14px;padding:0;overflow:hidden;border-color:rgba(240,192,64,.28);background:rgba(255,255,255,.035)">'+
      '<div style="background:linear-gradient(135deg,rgba(240,192,64,.82),rgba(176,132,30,.78));padding:18px 20px;color:#100d06">'+
        '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;opacity:.72;line-height:1.5">Official selection</div>'+
        '<div style="font-family:var(--display);font-size:34px;line-height:1.05;font-weight:850;margin-top:4px">'+esc(p.name)+'</div>'+
        '<div style="font-size:15px;line-height:1.7;margin-top:6px;opacity:.78;font-weight:750">'+esc(p.course)+' · '+esc(p.time)+' · '+esc(p.race || p.race_name || '')+'</div>'+
        '<div style="display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-top:16px">'+
          '<div><div style="font-family:var(--display);font-size:32px;line-height:1">'+esc(p.odds)+'</div><div style="font-size:12px;line-height:1.5;opacity:.75">odds</div></div>'+
          '<div style="display:flex;gap:8px;flex-wrap:wrap">'+pill('Score '+esc(p.score),'blue')+pill(esc(p.tipsters || 0)+' tipsters','green')+'</div>'+
        '</div>'+
      '</div>'+
      '<div style="padding:14px 16px">'+
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">'+
          '<div style="font-size:15px;font-weight:800;color:var(--text);line-height:1.5">Back each-way at '+esc(p.odds)+'</div>'+
          '<div style="font-size:13px;line-height:1.6;color:var(--muted)">Passed score, price, field size and form checks.</div>'+
        '</div>'+
      '</div>'+
      rivalEvidenceBlock(p)+
      '<div style="padding:12px 16px">'+qualityAuditBlock(p)+waterfall(scoreRows(p.parts))+'</div>'+
    '</div>';
  }
  function daySummaryBanner(){
    var total = official.length;
    var active = [];
    if(groups.flat.length) active.push({name:'flat', count:groups.flat.length, model:officialBetModel(groups.flat.length)});
    if(groups.jumps.length) active.push({name:'jumps', count:groups.jumps.length, model:officialBetModel(groups.jumps.length)});
    if(groups.unknown.length) active.push({name:'other', count:groups.unknown.length, model:officialBetModel(groups.unknown.length)});
    var mixed = active.length > 1;
    var model = officialBetModel(total);
    var title = 'TODAY: '+total+' OFFICIAL PICK'+(total === 1 ? '' : 'S');
    var copy = '';
    var stake = model.stake;
    var sub = model.lines+' lines';
    if(total === 0){
      title = 'TODAY: NO OFFICIAL BET';
      copy = 'No horse met every rule today.';
      stake = 0; sub = '0 lines';
    } else if(mixed) {
      stake = active.reduce(function(sum, s){ return sum + s.model.stake; }, 0);
      sub = active.map(function(s){ return '£'+s.model.stake+' '+s.name; }).join(' + ');
      copy = active.map(function(s){
        return 'Place an '+s.model.label+' on the '+s.name+' pick'+(s.count === 1 ? '' : 's');
      }).join(' and ');
    } else if(total >= 3) {
      title = 'TODAY: FULL PATENT';
      copy = '3 picks · £14 · 14 lines';
    } else if(total === 2) {
      title = 'TODAY: EACH-WAY DOUBLE';
      copy = '2 picks · £6 · 6 lines';
    } else {
      title = 'TODAY: EACH-WAY SINGLE';
      copy = '1 pick · £2 · 2 lines';
    }
    return '<div class="card" style="border-color:rgba(240,192,64,.35);background:linear-gradient(135deg,rgba(240,192,64,.10),rgba(56,189,248,.06));padding:18px 20px;margin:0 0 18px">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">'+esc(title)+'</div>'+
      '<div style="font-size:18px;font-weight:850;color:var(--text);line-height:1.55;margin-top:4px">'+esc(copy)+'</div>'+
      '<div style="font-size:14px;color:var(--muted);line-height:1.7;margin-top:8px">Total outlay: £'+esc(stake)+' today'+(sub ? ' ('+esc(sub)+')' : '')+'.</div>'+
    '</div>';
  }
  function groupedOfficialHtml(){
    var html = '';
    [
      {label:'FLAT', picks:groups.flat},
      {label:'JUMPS', picks:groups.jumps},
      {label:'OTHER', picks:groups.unknown}
    ].forEach(function(section){
      if(!section.picks.length) return;
      html += '<div style="font-family:var(--mono);font-size:11px;line-height:1.6;color:var(--muted2);letter-spacing:.16em;text-transform:uppercase;margin:18px 0 8px;border-top:1px solid rgba(255,255,255,.08);padding-top:12px">'+esc(section.label)+'</div>';
      html += section.picks.map(officialCard).join('');
    });
    return html;
  }
  function watchReason(w){
    var rawReasons = w.officialRejectionReasons || [];
    var codeText = rawReasons.join(' ');
    if(codeText.indexOf('ODDS_TOO_BIG') >= 0 || codeText.indexOf('ODDS_TOO_BIG_FOR_CURRENT_GATE') >= 0) return 'Price too high for value band.';
    if(codeText.indexOf('ODDS_TOO_SHORT') >= 0 || codeText.indexOf('ODDS_TOO_SHORT_FOR_CURRENT_GATE') >= 0) return 'Price too short for value band.';
    if(codeText.indexOf('FIELD_TOO_SMALL') >= 0) return 'Race had too few runners.';
    if(codeText.indexOf('NO_TIPSTER_CONSENSUS') >= 0) return 'No expert tips found today.';
    if(codeText.indexOf('SCORE_BELOW_75') >= 0) return 'Score just below required level.';
    if(codeText.toLowerCase().indexOf('one race') >= 0 || codeText.toLowerCase().indexOf('same race') >= 0) return 'Same race as an official pick.';
    var reasons = rawReasons.map(plainReason);
    if(reasons.length) return reasons.join(' ');
    if(w.reasonText) return w.reasonText;
    var odds = Number(w.odds || 0);
    if(odds && (odds < 2.75 || odds > 8)) return 'Price outside value band ('+w.odds+').';
    if(Number(w.score || 0) < 75) return 'Score just below the 75-point gate ('+w.score+').';
    return 'Interesting, but missed at least one final rule.';
  }
  function watchCard(w){
    return '<div class="card" style="border-color:rgba(56,189,248,.25);margin-bottom:10px">'+
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">'+
        '<div><div style="font-weight:750;font-size:16px;line-height:1.4;color:var(--text)">'+esc(w.name)+'</div><div style="font-size:14px;line-height:1.7;color:var(--muted2)">'+esc(w.course)+' · '+esc(w.time)+'</div></div>'+
        '<div>'+pill('Score '+esc(w.score || w.signal_score || 0),'blue')+'</div>'+
      '</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--muted);margin-top:10px">'+esc(watchReason(w))+'</div>'+
    '</div>';
  }
  function officialKeyForRunner(r){
    return normaliseNameLocal(r.name)+'|'+normaliseNameLocal(r.course)+'|'+String(r.time || '');
  }
  var blocked = runners.filter(function(r){ return !officialKeys[officialKeyForRunner(r)] && r.status !== 'official'; });
  var formWarnings = blocked.filter(function(r){ return (r.warnings || []).length; }).length;
  var outsidePrice = blocked.filter(function(r){
    var odds = Number(r.odds || 0);
    return odds && (odds < 2.75 || odds > 8);
  }).length;
  var officialRaceKeys = {};
  official.forEach(function(p){ officialRaceKeys[normaliseNameLocal(p.course)+'|'+String(p.time || '')] = true; });
  var sameRaceClashes = blocked.filter(function(r){ return officialRaceKeys[normaliseNameLocal(r.course)+'|'+String(r.time || '')]; }).length;
  var smallField = blocked.filter(function(r){ return Number(r.field_size || 0) > 0 && Number(r.field_size || 0) < 8; }).length;
  var officialHtml = official.length
    ? groupedOfficialHtml()
    : '<div class="card" style="border-color:rgba(107,114,128,.35);background:rgba(107,114,128,.06)"><div style="font-size:18px;font-weight:750;color:var(--text);line-height:1.5">No official bet today.</div><div style="font-size:14px;line-height:1.8;color:var(--muted)">No horse met all the criteria. No Single, Double or Patent is placed.</div></div>';
  document.getElementById('panel-picks').innerHTML =
    '<div class="section-hero find"><div><div class="hero-kicker">Today&apos;s selections</div><div class="section-hero-title">Today&apos;s Picks</div><div class="section-hero-copy">Official selections, learning-only watchlist horses and the protection summary in one place. Watchlist horses do not enter proof or the official bet.</div></div>'+
      '<div class="hero-stat">'+scoreChip(official.length, 'OFFICIAL', 'var(--green)')+'</div></div>'+
    daySummaryBanner()+
    '<div class="section-block-h"><h2>Official selections</h2><span class="n">passed every live rule</span></div>'+
    officialHtml+
    '<div class="section-block-h" style="margin-top:22px"><h2>Horses that nearly made it</h2><span class="n">Strong horses that missed one rule. Not part of today&apos;s bet.</span></div>'+
    (watchlist.length ? watchlist.map(watchCard).join('') : '<div class="empty">No watchlist horses are published for this dashboard run.</div>')+
    '<div class="section-block-h" style="margin-top:22px"><h2>What was blocked today</h2></div>'+
    '<div class="chart-card"><div class="chart-title">Protection summary</div>'+
      '<div style="font-size:16px;line-height:1.8;color:var(--muted)">'+
        esc(blocked.length)+' horses were considered and blocked.<br>'+
        esc(formWarnings)+' had form warnings.<br>'+
        esc(outsidePrice)+' were outside the price band.<br>'+
        esc(sameRaceClashes)+' clashed with a stronger pick in the same race.<br>'+
        esc(smallField)+' were in races with too few runners.'+
      '</div>'+
      '<div style="margin-top:14px">'+pill('One race rule: ON','green')+'</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--muted);margin-top:8px">No two picks from the same race today.</div>'+
    '</div>';
}

function renderConfirm(){
  var tip = pick('tipsterIntel') || {};
  var db = pick('dbStatus') || {};
  var hm = pick('horseMemory') || {};
  var fg = pick('fieldGraph') || {topEdges:[], warnings:[], signalCounts:{}};
  var challenger = pick('challengerLab') || {};
  var challengerSummary = challengerSummaryData() || {};
  var fieldAwareSummary = challenger.fieldAwareVsOldOverlay || challengerSummary.field_aware_vs_old_overlay || {};
  var runners = allRaceRunners();
  var rivalRows = runners.filter(function(r){return r.rivalMemoryOverlay;}).slice(0,6);
  var matchPct = tip.totalRunnersChecked ? tip.totalMatched / tip.totalRunnersChecked * 100 : 0;
  var horseCount = Object.keys(hm).length;
  var graphCounts = fg.signalCounts || {};
  var graphTotal = Number(fg.runnerCount || 0);
  var positiveRelationshipEdge = Number(graphCounts.positive_relationship_edge || 0);
  var positiveCount = Number(graphCounts.strong_relationship_edge || 0) + Number(graphCounts.positive_relationship_edge || 0);
  var warningCount = Number(graphCounts.relationship_warning || 0);
  var sourceTierRows = Array.isArray(tip.tierMix) ? tip.tierMix : [];
  var tierCounts = {1:0, 2:0, 3:0};
  sourceTierRows.forEach(function(seg){
    var tier = parseInt(seg.tier, 10);
    var value = parseInt(seg.value != null ? seg.value : seg.count, 10);
    if (tier >= 1 && tier <= 3) tierCounts[tier] += isNaN(value) ? 0 : value;
  });
  var tierMix = [
    {value:tierCounts[1], color:'var(--gold)'},
    {value:tierCounts[2], color:'var(--blue)'},
    {value:tierCounts[3], color:'var(--green)'}
  ];
  var bestEdges = fg.topEdges || [];
  var positiveFallback = positiveCount > 0 && !bestEdges.length
    ? '<div class="plain">'+esc(positiveCount)+' horses have positive relationship evidence today. Detail view coming in next dashboard update.</div>'
    : '<div class="empty">No positive rival graph evidence in the current dashboard feed.</div>';
  function graphRow(row, tone){
    return '<div class="graph-row">'+
      '<div class="graph-main"><div class="graph-name">'+esc(row.horse || 'Unknown')+'</div>'+
        '<div class="graph-meta">'+esc(row.course || '')+' '+esc(row.time || '')+' · '+esc(row.race || '')+'</div>'+
        '<div class="graph-note">'+esc(row.label || '')+'</div></div>'+
      '<div class="graph-score" style="color:'+tone+'">'+esc(row.score || 0)+'</div>'+
    '</div>';
  }
  function signalBar(row){
    var signals = Number((row.rivalMemoryOverlay || {}).points || 0);
    var pct = clamp(signals / 8 * 100, 2, 100);
    return '<div class="bar-row"><div class="bar-label">'+esc(row.name)+'</div>'+
      '<div class="bar-track"><div class="bar-fill" style="width:'+pct+'%;background:var(--green)"></div></div>'+
      '<div class="bar-value">'+esc(signals)+' signals</div></div>';
  }
  function changeBadge(label, tone){
    return '<span style="display:inline-block;background:'+tone+'22;border:1px solid '+tone+'66;color:'+tone+';font-family:var(--mono);font-size:12px;text-transform:uppercase;letter-spacing:.08em;line-height:1.6;padding:4px 9px;border-radius:999px;margin-bottom:8px">'+esc(label)+'</span>';
  }
  function resultTone(result){
    var r = String(result || '').toUpperCase();
    if(r === 'WON' || r === 'PLACED') return 'var(--green)';
    if(r === 'NR' || r === 'VOID' || r === 'LOST') return 'var(--red)';
    return 'var(--muted2)';
  }
  function fieldAwareDates(){
    return asArray(fieldAwareSummary.dates).slice().sort(function(a,b){ return String(b.date || '').localeCompare(String(a.date || '')); });
  }
  function renderHistoricalDetail(day){
    if(!day){
      return '<div class="chart-card" style="border-color:var(--border)"><div class="empty">Today&apos;s comparison available after picks generate at 10:00.</div></div>';
    }
    var old = (day.old_overlay || day.oldOverlay || {});
    var changes = asArray(old.notable_changes || old.notableChanges);
    var oldRows = changes.filter(function(r){ return num(r.old_points || r.oldPoints, 0) > 0; });
    var newRows = changes.filter(function(r){ return num(r.new_points || r.newPoints, 0) > 0; });
    function rowHtml(row, key){
      var pts = key === 'old' ? firstDefined(row.old_points, row.oldPoints, 0) : firstDefined(row.new_points, row.newPoints, 0);
      var result = firstDefined(row.actual_result, row.actualResult, 'pending');
      return '<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:8px;line-height:1.8">'+
        '<div style="flex:1;min-width:0"><div class="graph-name" style="display:block;font-size:15px;font-weight:700;line-height:1.8;margin-bottom:4px">'+esc(row.horse || 'Unknown')+' <span style="color:var(--gold)">+'+esc(pts)+'</span></div>'+
        '<div class="graph-note" style="display:block;font-size:14px;line-height:1.8;margin-bottom:4px">'+esc(row.reason || '')+'</div></div>'+
        '<div class="graph-score" style="margin-left:auto;color:'+resultTone(result)+';line-height:1.8;white-space:nowrap">'+esc(result)+'</div></div>';
    }
    var verdict = day.verdict || ((day.comparison || {}).verdict) || 'COLLECTING';
    var tone = verdict === 'FIELD_AWARE_BETTER' ? 'var(--green)' : (verdict === 'OLD_OVERLAY_BETTER' ? 'var(--amber)' : 'var(--muted2)');
    var verdictBg = verdict === 'FIELD_AWARE_BETTER' ? 'rgba(0,232,122,.06)' : (verdict === 'OLD_OVERLAY_BETTER' ? 'rgba(240,192,64,.06)' : 'rgba(255,255,255,.04)');
    return '<div class="chart-card"><div class="chart-title">'+esc(day.date || 'Selected date')+' — rival overlay comparison</div>'+
      '<div class="grid grid-2" style="margin-top:10px">'+
        '<div style="border-left:3px solid var(--red);background:rgba(255,77,109,.05);padding:14px;min-height:120px;line-height:1.8"><div class="card-sub" style="display:block;color:var(--red);font-family:var(--mono);font-size:12px;line-height:1.8;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em">OLD OVERLAY ON THIS DAY</div>'+
          (oldRows.length ? oldRows.map(function(r){ return rowHtml(r, 'old'); }).join('') : '<div class="empty">No old-only boosted horses stored.</div>')+'</div>'+
        '<div style="border-left:3px solid var(--green);background:rgba(0,232,122,.05);padding:14px;min-height:120px;line-height:1.8"><div class="card-sub" style="display:block;color:var(--green);font-family:var(--mono);font-size:12px;line-height:1.8;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em">FIELD-AWARE ON THIS DAY</div>'+
          (newRows.length ? newRows.map(function(r){ return rowHtml(r, 'new'); }).join('') : '<div class="empty">No field-aware boosted horses stored.</div>')+'</div>'+
      '</div>'+
      '<div style="margin-top:16px;padding:12px 16px;border-left:3px solid '+tone+';background:'+verdictBg+';border-radius:0 var(--r-sm) var(--r-sm) 0;font-size:14px;line-height:1.8"><strong>'+esc(verdict.replace(/_/g, ' '))+':</strong> '+esc(verdict === 'FIELD_AWARE_BETTER' ? 'Field-aware found better evidence on this day.' : (verdict === 'OLD_OVERLAY_BETTER' ? 'Old overlay performed better on this day.' : 'Same picks or still collecting evidence.'))+'</div>'+
    '</div>';
  }
  function fieldAwareSection(){
    var days = fieldAwareDates();
    var defaultDate = (days[0] || {}).date || ((challengerLatestData() || {}).date || '');
    window.S75.whatWouldChangeState = window.S75.whatWouldChangeState || {tab:'overlay', date:defaultDate, daily:{}};
    if(!window.S75.whatWouldChangeState.date) window.S75.whatWouldChangeState.date = defaultDate;
    var tabs = [
      {id:'overlay', label:'Overlay Fix (LIVE)', dot:'green'},
      {id:'quality', label:'Tipster Quality', cid:'consensus_quality_v1'},
      {id:'history', label:'Rival History', cid:'field_graph_v1'},
      {id:'combined', label:'Combined', cid:'rival_evidence_v1'}
    ];
    function challengerSummaryById(cid){
      return asArray(challengerSummary.pre_race_challengers || challengerSummary.challengers).filter(function(row){ return row.id === cid; })[0] || {};
    }
    function latestChallengerById(cid, dateValue){
      var daily = (window.S75.whatWouldChangeState.daily || {})[dateValue] || {};
      var latest = dateValue && daily.date === dateValue ? daily : challengerLatestData();
      return asArray(latest.pre_race_challengers).filter(function(row){ return row.id === cid; })[0] || {};
    }
    function stateColor(status){
      var s = trafficState(status);
      if(s === 'RISKY') return 'red';
      if(s === 'WATCHING') return 'amber';
      if(s === 'PROMISING') return 'green';
      if(s === 'PROMOTION_CANDIDATE' || s === 'APPROVED_BY_JOHN') return 'gold';
      if(s === 'ARCHIVED') return 'grey';
      return 'grey';
    }
    function renderTabs(){
      return '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px">'+tabs.map(function(tab){
        var summary = tab.cid ? challengerSummaryById(tab.cid) : {};
        var dot = tab.dot || stateColor(summary.promotion_status || summary.status);
        var active = window.S75.whatWouldChangeState.tab === tab.id;
        return '<button type="button" onclick="window.S75.selectWhatWouldChangeTab(\''+esc(tab.id)+'\')" style="display:inline-flex;align-items:center;gap:8px;background:'+(active?'var(--bg4)':'var(--bg3)')+';border:1px solid '+(active?'var(--gold)':'var(--border)')+';color:'+(active?'var(--gold)':'var(--muted)')+';font-family:var(--mono);font-size:12px;line-height:1.6;padding:7px 12px;border-radius:999px;cursor:pointer">'+trafficDot(dot)+esc(tab.label)+'</button>';
      }).join('')+'</div>';
    }
    function renderDatePills(){
      if(!days.length){
        return '<div style="font-size:14px;color:var(--muted);line-height:1.8;text-align:center;margin-bottom:16px">Date history builds automatically as each day settles. Check back after 10 July&apos;s picks settle.</div>';
      }
      return '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">'+days.slice(0,14).map(function(day, idx){
        var active = (window.S75.whatWouldChangeState.date || defaultDate) === day.date;
        return '<button type="button" data-field-aware-date="'+esc(day.date || '')+'" onclick="window.S75.selectWhatWouldChangeDate(\''+esc(day.date || '')+'\')" style="background:'+(active?'var(--bg4)':'var(--bg3)')+';border:1px solid '+(active?'var(--gold)':'var(--border)')+';color:'+(active?'var(--gold)':'var(--muted2)')+';font-family:var(--mono);font-size:12px;line-height:1.6;padding:5px 11px;border-radius:999px;cursor:pointer">'+esc(idx===0?'TODAY':day.date)+'</button>';
      }).join('')+'</div>';
    }
    function loadDate(dateValue){
      if(!dateValue || window.S75.whatWouldChangeState.daily[dateValue]) return;
      fetch('./data/challenger_lab/challenger_'+dateValue+'.json', {cache:'no-store'})
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(json){
          if(json) window.S75.whatWouldChangeState.daily[dateValue] = json;
          var el = document.getElementById('what-would-change-active');
          if(el) el.innerHTML = renderActivePanel();
        })
        .catch(function(){});
    }
    window.S75.selectWhatWouldChangeTab = function(tabId){
      window.S75.whatWouldChangeState.tab = tabId;
      var el = document.getElementById('what-would-change-active');
      if(el) el.innerHTML = renderActivePanel();
      loadDate(window.S75.whatWouldChangeState.date);
    };
    window.S75.selectWhatWouldChangeDate = function(dateValue){
      window.S75.whatWouldChangeState.date = dateValue;
      var el = document.getElementById('what-would-change-active');
      if(el) el.innerHTML = renderActivePanel();
      var tabsEl = document.getElementById('what-would-change-dates');
      if(tabsEl) tabsEl.innerHTML = renderDatePills();
      loadDate(dateValue);
    };
    function comparePicks(liveRows, challengerRows){
      var liveNames = asArray(liveRows).map(function(p){ return p.horse || p.name || ''; }).filter(Boolean);
      var challengerNames = asArray(challengerRows).map(function(p){ return p.horse || p.name || ''; }).filter(Boolean);
      var liveSet = {};
      var chalSet = {};
      liveNames.forEach(function(n){ liveSet[normaliseNameLocal(n)] = true; });
      challengerNames.forEach(function(n){ chalSet[normaliseNameLocal(n)] = true; });
      var same = liveNames.length === challengerNames.length && liveNames.every(function(n){ return chalSet[normaliseNameLocal(n)]; });
      function row(name, tone){ return '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px;font-size:14px;line-height:1.8;color:var(--muted)"><span>'+esc(name)+'</span>'+pill(tone, tone==='same'?'green':(tone==='challenger only'?'gold':'amber'))+'</div>'; }
      return '<div class="grid grid-2" style="margin-top:12px"><div style="padding:12px;border:1px solid var(--border);border-radius:var(--r-sm)"><div class="chart-title">Live picks today</div>'+
        (liveNames.length ? liveNames.map(function(n){ return row(n, chalSet[normaliseNameLocal(n)]?'same':'live only'); }).join('') : '<div class="empty">No live picks loaded.</div>')+'</div>'+
        '<div style="padding:12px;border:1px solid var(--border);border-radius:var(--r-sm)"><div class="chart-title">Challenger picks today</div>'+
        (challengerNames.length ? challengerNames.map(function(n){ return row(n, liveSet[normaliseNameLocal(n)]?'same':'challenger only'); }).join('') : '<div class="empty">No challenger picks loaded for this date.</div>')+'</div></div>'+
        '<div style="margin-top:10px">'+(same ? pill('Same picks today','green') : pill('Different picks today','gold'))+'</div>';
    }
    function normaliseNameLocal(value){
      return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    }
    function challengerVerdict(summary, kind){
      var settled = num(summary.settled_days, 0);
      var delta = num(summary.delta_vs_live_profit, 0);
      if(settled < 14) return 'Still collecting evidence. '+kind+' needs 14 settled days before the comparison means anything.';
      if(delta < 0) return 'Not improving results. The current live method is performing better so far.';
      if(settled < 30) return 'Showing promise. '+kind+' is being watched for a full 30 days.';
      return 'Strong evidence. Ready for John to review for live promotion.';
    }
    function challengerSampleLabel(tab, summary){
      if(tab.id === 'combined'){
        return 'New field-aware sample';
      }
      return 'Backfilled challenger sample';
    }
    function challengerSampleNote(tab, summary){
      var range = challengerSummary.date_range || {};
      if(tab.id === 'combined'){
        return 'This is the newer field-aware/full-history evidence. It starts with the confirmed 9 July case, so the sample is still small.';
      }
      return 'This count includes older backfilled challenger files from '+(range.start || 'the stored start date')+' to '+(range.end || 'the stored end date')+'. It is not the new field-aware/full-history sample.';
    }
    function challengerPanel(tab){
      var summary = challengerSummaryById(tab.cid);
      var dateValue = window.S75.whatWouldChangeState.date || defaultDate;
      var daily = latestChallengerById(tab.cid, dateValue);
      var latest = (window.S75.whatWouldChangeState.daily || {})[dateValue] || challengerLatestData();
      var liveRows = ((latest.live_system || {}).official_picks || []);
      var dailyPicks = daily.picks || [];
      var status = summary.promotion_status || daily.promotion_status || daily.status || 'COLLECTING';
      var delta = num(summary.delta_vs_live_profit, 0);
      var color = delta >= 0 ? 'var(--green)' : 'var(--red)';
      var title = tab.id === 'quality' ? 'Fix 2 — Quality-Weighted Tipster Grading' : (tab.id === 'history' ? 'Fix 3 — Full SQLite Rival History in Picks' : 'Fix 4 — Field-Aware + Full History Combined');
      var sub = tab.id === 'quality' ? 'Would picks change if tipster sources were weighted by quality (Tier 1-4) instead of raw count?' : (tab.id === 'history' ? 'Would picks change if 18 million head-to-head records directly influenced scoring instead of the summary profile file?' : 'The overlay fix plus the full 18 million records, working together. The most complete picture of what rival evidence can do.');
      var dataComplete = daily.data_complete !== false;
      var sampleLabel = challengerSampleLabel(tab, summary);
      var sampleNote = challengerSampleNote(tab, summary);
      return '<div class="chart-card"><div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap"><div><div style="font-family:var(--display);font-size:24px;color:var(--text);line-height:1.2">'+esc(title)+'</div><div style="font-size:14px;color:var(--muted);line-height:1.8;max-width:760px">'+esc(sub)+'</div></div>'+pill(String(status).replace(/_/g,' '), stateColor(status))+'</div>'+
        (tab.id === 'history' ? '<div style="margin-top:12px"><div style="font-family:var(--display);font-size:28px;color:var(--gold);line-height:1">18,000,000</div><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase">historical matchups available</div></div>' : '')+
        (tab.id === 'combined' ? '<div style="margin-top:12px">'+changeBadge('First confirmed case: 9 July 2026','var(--gold)')+'<div style="font-size:14px;color:var(--muted);line-height:1.8">Found Del Maro + Thunder Call (both placed). Old system boosted a non-runner.</div></div>' : '')+
        (!dataComplete ? '<div style="margin-top:12px;color:var(--amber);font-size:13px;line-height:1.8">Field graph data not available for this date. This challenger skipped this day.</div>' : '')+
        '<div class="grid grid-3" style="margin-top:16px"><div class="chart-card">'+trafficLight(status, 'large', true)+'</div>'+
          '<div class="chart-card"><div class="chart-title">'+esc(sampleLabel)+'</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div><div class="card-big">'+esc(summary.days_tested || 0)+'</div><div class="card-sub">tested</div></div><div><div class="card-big">'+esc(summary.settled_days || 0)+'</div><div class="card-sub">settled</div></div></div><div class="card-sub" style="margin-top:10px;line-height:1.7">'+esc(sampleNote)+'</div></div>'+
          '<div class="chart-card"><div class="chart-title">Delta vs live</div>'+gauge({value:Math.min(Math.abs(delta), 100), max:100, size:80, color:color, label:signedMoney(delta), sub:'vs live system'})+'</div></div>'+
        '<div class="grid grid-2" style="margin-top:16px"><div class="chart-card"><div class="chart-title">Today&apos;s picks comparison</div>'+comparePicks(liveRows, dailyPicks)+'</div>'+
          '<div class="chart-card"><div class="chart-title">Running score</div><div class="card-sub">Same picks: '+esc(summary.same_pick_days || 0)+' days<br>Different picks: '+esc(summary.different_pick_days || 0)+' days<br>When different, which was better: TBD</div><div style="margin-top:12px">'+sparkline(summary.daily_delta || summary.daily_profit || [0, delta], 'var(--blue)', 220, 42)+'</div></div></div>'+
        '<div class="plain" style="font-size:14px;line-height:1.8;margin-top:16px">'+esc(challengerVerdict(summary, title.replace(/^Fix \\d+ — /, '')))+'</div></div>';
    }
    function overlayPanel(){
      var selected = fieldAwareDates().filter(function(d){ return d.date === window.S75.whatWouldChangeState.date; })[0] || days[0] || null;
      var totalCompared = num(fieldAwareSummary.days_compared || fieldAwareSummary.daysCompared, 0);
      var better = num(fieldAwareSummary.days_field_aware_better || fieldAwareSummary.daysFieldAwareBetter, 0);
      var oldBetter = num(fieldAwareSummary.days_old_better || fieldAwareSummary.daysOldBetter, 0);
      var same = num(fieldAwareSummary.days_same || fieldAwareSummary.daysSame, 0);
      var pct = better + oldBetter ? Math.round(better / (better + oldBetter) * 100) : 0;
      var comparedLabel = totalCompared === 1 ? '1 day compared' : totalCompared+' days compared';
      var trafficReview = totalCompared < 7 ? 'Next review: after 7 days' : (totalCompared < 14 ? 'Next review: after 14 days' : 'Next review: manual review');
      var runningScoreHtml = totalCompared < 7 ? '<div style="font-family:var(--display);font-size:32px;color:var(--muted2);line-height:1.2;text-align:center;margin:8px 0 2px">'+esc(totalCompared)+'</div><div style="font-family:var(--mono);font-size:13px;color:var(--muted2);line-height:1.8;text-align:center;margin-bottom:8px">'+esc(totalCompared === 1 ? 'day compared' : 'days compared')+'</div><div style="font-family:var(--mono);font-size:13px;color:var(--muted2);line-height:1.8;text-align:center">Need 7 days before score is meaningful</div>' : gauge({value:pct,color:pct>60?'var(--green)':(pct<40?'var(--red)':'var(--amber)'),label:pct+'%',sub:'FIELD-AWARE'});
      return '<div><div style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:12px"><div><div style="font-family:var(--display);font-size:24px;line-height:1.2">Fix 1 — Field-Aware Rival Overlay</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6">LIVE FROM 10 JULY 2026</div></div>'+pill('LIVE','green')+'</div>'+
        '<div style="border:1px solid rgba(240,192,64,.4);background:rgba(240,192,64,.06);border-radius:var(--r-md);padding:24px;margin-bottom:14px">'+changeBadge('FIRST CONFIRMED CASE — 9 JULY 2026', 'var(--gold)')+
        '<div class="grid grid-2" style="margin-top:16px"><div style="background:rgba(255,77,109,.06);border-left:3px solid var(--red);padding:14px;min-height:120px;line-height:1.8"><div style="display:block;font-family:var(--mono);font-size:12px;color:var(--red);line-height:1.8;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em">OLD SYSTEM BOOSTED</div><div style="display:block;margin-bottom:16px;padding-bottom:8px;line-height:1.8"><div class="graph-name" style="display:block;font-size:15px;font-weight:700;line-height:1.8;margin-bottom:4px">Tenability — +8 pts (score 79.2)</div><div style="display:block;color:var(--red);font-size:14px;line-height:1.8">NON-RUNNER — coughing</div></div><div style="display:block;margin-bottom:16px;line-height:1.8"><div class="graph-name" style="display:block;font-size:15px;font-weight:700;line-height:1.8;margin-bottom:4px">Miss Rainbow — +8 pts (score 75.1)</div><div style="display:block;color:var(--amber);font-size:14px;line-height:1.8">3rd at 9.2 — marginal</div></div></div><div style="background:rgba(0,232,122,.06);border-left:3px solid var(--green);padding:14px;min-height:120px;line-height:1.8"><div style="display:block;font-family:var(--mono);font-size:12px;color:var(--green);line-height:1.8;margin-bottom:12px;text-transform:uppercase;letter-spacing:.08em">FIELD-AWARE FOUND</div><div style="display:block;margin-bottom:16px;line-height:1.8"><div class="graph-name" style="display:block;font-size:15px;font-weight:700;line-height:1.8;margin-bottom:4px">Del Maro — +8 pts (score 80.5)</div><div style="display:block;color:var(--green);font-size:14px;line-height:1.8">3rd at 3.0 — placed</div></div><div style="display:block;margin-bottom:16px;line-height:1.8"><div class="graph-name" style="display:block;font-size:15px;font-weight:700;line-height:1.8;margin-bottom:4px">Thunder Call — +8 pts (score 80.0)</div><div style="display:block;color:var(--green);font-size:14px;line-height:1.8">3rd at 5.1 — placed</div></div></div></div><div style="font-size:14px;font-weight:700;color:var(--gold);line-height:1.8;text-align:center;margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,.08)">Both field-aware picks placed. Old system was boosting a non-runner.</div></div>'+
        '<div class="grid grid-3" style="margin-bottom:14px"><div class="chart-card"><div class="chart-title">Today: same or different?</div>'+((selected && (selected.comparison || {}).same_as_live) ? '<div class="card-big" style="color:var(--green);line-height:1.4;margin-bottom:8px">✓</div><div class="card-sub" style="font-size:14px;line-height:1.8;color:var(--muted)">Field-aware agrees with live today.</div>' : '<div><div style="font-size:16px;color:var(--gold);line-height:1.8;margin-bottom:8px;text-align:center;font-weight:700">Waiting for 10:00</div><div style="margin-top:8px;color:var(--muted);font-size:14px;line-height:1.8;text-align:center">Today&apos;s comparison will appear here after picks generate at 10:00 and the Challenger Lab feed updates. Check back after 10:05.</div></div>')+'</div><div class="chart-card"><div class="chart-title">Running score</div>'+runningScoreHtml+'</div><div class="chart-card"><div class="chart-title">Traffic light status</div>'+trafficLight(totalCompared < 7 ? 'COLLECTING' : (better < oldBetter ? 'RISKY' : (totalCompared >= 14 && better > oldBetter ? 'PROMOTION_CANDIDATE' : 'WATCHING')), 'large', false)+'<div style="margin-top:8px;font-family:var(--mono);line-height:1.8"><div style="font-size:15px;color:var(--text);margin-bottom:8px">'+esc(comparedLabel)+'</div><div style="font-size:13px;color:var(--muted2)">'+esc(trafficReview)+'</div></div></div></div>'+
        '<div id="field-aware-detail">'+renderHistoricalDetail(selected)+'</div><div class="plain" style="font-size:14px;line-height:1.8;padding:14px 16px;border-left:3px solid var(--gold);background:rgba(240,192,64,.06);border-radius:0 var(--r-sm) var(--r-sm) 0;margin-top:16px">The fix is live. From 10 July 2026 onwards, Signal 75 only awards rival evidence points when the rival horse is actually in today&apos;s race. This section tracks whether that makes picks better over time.</div></div>';
    }
    function renderActivePanel(){
      var tab = tabs.filter(function(t){ return t.id === window.S75.whatWouldChangeState.tab; })[0] || tabs[0];
      if(tab.id === 'overlay') return overlayPanel();
      return challengerPanel(tab);
    }
    loadDate(window.S75.whatWouldChangeState.date);
    return '<div style="margin:0 0 18px;line-height:1.6"><div style="font-family:var(--display);font-size:24px;letter-spacing:0;color:var(--text);line-height:1.3;margin-bottom:8px">WHAT WOULD CHANGE IF WE TURNED THIS ON?</div>'+
      '<div style="font-family:var(--mono);font-size:13px;color:var(--muted2);line-height:1.8;margin-bottom:16px">Every experimental improvement runs silently alongside live Signal 75. This shows what each one would have changed. Nothing goes live until John approves it.</div>'+
      renderTabs()+'<div id="what-would-change-dates">'+renderDatePills()+'</div><div id="what-would-change-active">'+renderActivePanel()+'</div></div>';
  }
  document.getElementById('panel-confirm').innerHTML =
    '<div style="background:linear-gradient(135deg, rgba(240,192,64,.08), rgba(56,189,248,.05));border:1px solid rgba(240,192,64,.3);border-radius:18px;padding:28px 28px 22px;margin-bottom:22px">'+
      '<div style="font-family:var(--display);font-size:28px;color:var(--gold);text-align:center">Signal 75 has watched every horse race in Britain for the last 11 years.</div>'+
      '<div style="font-family:var(--body);font-size:14px;color:var(--text);margin-top:8px;text-align:center">That&apos;s 18 million times one horse finished in front of another. We remember all of it.</div>'+
      '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:24px">'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--gold)">4,015</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">days of racing remembered</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">When two horses line up today that last met at Cheltenham in 2023, Signal 75 knows exactly what happened. Who won. By how much. What the ground was like. It never forgets.</div></div>'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--green)">'+esc(positiveRelationshipEdge)+'</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">horses with a proven edge today</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">'+esc(positiveRelationshipEdge)+' of today&apos;s runners have beaten at least one of their rivals before. Not a guess. Not a rating. An actual race result, stored and remembered. That is the advantage.</div></div>'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--blue)">18,000,000</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">head-to-head records checked this morning</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">Every morning Signal 75 checks every horse against every rival they might face, across a decade of results. No human could do this. The system does it in 8 seconds.</div></div>'+
      '</div>'+
      '<div style="font-family:var(--mono);font-size:13px;line-height:1.6;color:var(--gold);text-align:center;margin-top:20px">This is what separates Signal 75 from a tipster with a spreadsheet.</div>'+
      '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted2);text-align:center;margin-top:8px">Analysis and intelligence only. Does not automatically change live picks or proof.</div>'+
    '</div>'+
    fieldAwareSection()+
    '<div class="chart-card" style="margin-bottom:16px;border-color:rgba(240,192,64,.26);background:rgba(240,192,64,.045)"><div class="chart-title">Today&apos;s official bet type</div>'+officialBetCardsHtml()+'<div class="card-sub">Flat and Jumps are kept separate. They are not combined into a Patent unless one section has 3 official selections.</div></div>'+
    '<div class="section-hero confirm"><div><div class="hero-kicker">Stage 02</div><div class="section-hero-title">Confirm with outside evidence</div><div class="section-hero-copy">This checks trusted tipsters, stored horse memory, and rival evidence before the horse is trusted publicly.</div></div>'+
      '<div class="hero-stat">'+scoreChip(tip.totalMatched || 0, 'TIP MATCHES', 'var(--gold)')+'</div></div>'+
    '<div class="plain" style="margin-top:16px">Today Signal 75 checked '+esc(fg.edgeCount || 0)+' historical matchups across '+esc(graphTotal)+' runners. '+esc(positiveCount)+' horses have a documented advantage over at least one rival they face today. '+esc(warningCount)+' horses carry a warning based on past results against today&apos;s field.</div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      '<div class="chart-card"><div class="chart-title">Tipster coverage</div>'+gauge({value:matchPct,color:'var(--gold)',label:tip.totalMatched || 0,sub:'MATCHED'})+
        '<div class="card-sub">'+esc(tip.sourcesSuccessful || 0)+' sources worked · '+esc(tip.estimatedCallsAvoided || 0)+' paid calls avoided</div></div>'+
      '<div class="chart-card"><div class="chart-title">Source mix</div><div class="donut-wrap">'+donut(tierMix, 112)+'<div class="donut-legend"><div class="li"><span class="sw" style="background:var(--gold)"></span>Tier 1 — Racing Post, Timeform, Sporting Life</div><div class="li"><span class="sw" style="background:var(--blue)"></span>Tier 2 — Newspapers &amp; specialist sites</div><div class="li"><span class="sw" style="background:var(--green)"></span>Tier 3 — NAP tables</div></div></div><div class="card-sub">'+esc(tip.sourcesSuccessful || 0)+' sources matched today. '+esc(tip.estimatedCallsAvoided || 0)+' paid API calls avoided.</div></div>'+
      '<div class="chart-card"><div class="chart-title">Horse memory</div>'+gauge({value:horseCount,max:Math.max(1, horseCount),color:'var(--blue)',label:horseCount,sub:'ACTIVE'})+
        '<div class="card-sub">'+esc(db.profileCount || 0)+' stored profiles in the database.</div></div>'+
    '</div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      card('Rival graph checked', gauge({value:graphTotal,max:Math.max(1, graphTotal),color:'var(--blue)',label:graphTotal,sub:'RUNNERS'})+
        '<div class="card-sub">'+esc(fg.edgeCount || 0)+' historical matchups checked<br>— 11 years of UK racing</div><div class="card-sub" style="color:var(--muted2)">Horses with direct or indirect evidence against today&apos;s rivals: '+esc(positiveCount)+'</div>')+
      card('Positive graph evidence', gauge({value:positiveCount,max:Math.max(1, graphTotal),color:'var(--green)',label:positiveCount,sub:'SUPPORT'})+
        '<div class="card-sub">Horses with direct or useful chain evidence.</div>')+
      card('Rival warnings', gauge({value:warningCount,max:Math.max(1, graphTotal),color:'var(--amber)',label:warningCount,sub:'CAUTION'})+
        '<div class="card-sub">Previously beaten by rival evidence. Review only for now.</div>')+
    '</div>'+
    '<div class="grid grid-2" style="margin-top:16px">'+
      '<div class="chart-card"><div class="chart-title">Best horse-memory edges</div>'+
        (bestEdges.length ? bestEdges.slice(0,6).map(function(row){return graphRow(row, 'var(--green)');}).join('') : positiveFallback)+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Rival warnings to review</div>'+
        ((fg.warnings || []).length ? (fg.warnings || []).slice(0,6).map(function(row){return graphRow(row, 'var(--red)');}).join('') : '<div class="empty">No rival graph warnings in the current dashboard feed.</div>')+
      '</div>'+
    '</div>'+
    '<div class="plain" style="margin-top:16px;background:rgba(240,192,64,.06);border-left:3px solid var(--gold);padding:12px 16px;font-family:var(--mono);font-size:13px;line-height:1.7;color:var(--muted2)"><strong>RIVAL GRAPH — ANALYSIS ONLY</strong><br>This evidence informs the dashboard view.<br>It does not automatically change live picks.</div>'+
    '<div class="chart-card" style="margin-top:16px"><div class="chart-title">Live memory overlay actually used</div><div class="chart-title" style="text-align:right;color:var(--muted2)">TIPSTER SIGNALS</div>'+
      (rivalRows.length ? rivalRows.map(signalBar).join('') : '<div class="empty">No runner in the current comparison has a rival-memory boost today.</div>')+
    '</div>';
}

function renderProtect(){
  var status = pick('status') || {};
  var sections = officialBetSections();
  var runners = allRaceRunners();
  var warningRows = runners.filter(function(r){return (r.warnings || []).length;}).slice(0,8);
  var legCount = sections.reduce(function(sum, section){ return sum + section.picks.length; }, 0);
  document.getElementById('panel-protect').innerHTML =
    '<div class="section-hero protect"><div><div class="hero-kicker">Stage 03</div><div class="section-hero-title">Protect the bet</div><div class="section-hero-copy">Bad form, poor value, small fields, same-race clashes and weak extra selections are blocked before publication.</div></div>'+
      '<div class="hero-stat">'+scoreChip(warningRows.length, 'WARNINGS', 'var(--red)')+'</div></div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      card('Official bet type', gauge({value:legCount,max:3,color:legCount===3?'var(--green)':'var(--amber)',label:officialBetSummaryText(),sub:legCount+' selections'})+
        '<div class="card-sub">Flat and Jumps are kept separate. No weak extra selections are forced.</div>')+
      card('Official gates', '<div class="funnel">'+
        '<div class="funnel-step"><div class="funnel-name">Score</div><div class="funnel-block" style="width:100%"></div><div class="bar-value">75+</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Price</div><div class="funnel-block" style="width:82%"></div><div class="bar-value">value</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Field</div><div class="funnel-block" style="width:70%"></div><div class="bar-value">8+</div></div>'+
        '<div class="funnel-step"><div class="funnel-name">Form</div><div class="funnel-block" style="width:62%"></div><div class="bar-value">safe</div></div></div>')+
      card('One race rule', '<div class="card-big" style="font-size:24px;color:var(--green)">ON</div><div class="card-sub">No two official selections should come from the same race.</div>')+
    '</div>'+
    '<div class="chart-card" style="margin-top:16px"><div class="chart-title">Current warnings</div>'+
      (warningRows.length ? warningRows.map(function(r){return visualBar(r.name, (r.warnings || []).length, 4, 'var(--red)');}).join('') : '<div class="empty">No active runner warnings in the current comparison.</div>')+
    '</div>';
}

function renderLearnDashboard(){
  var l = pick('continuousLearning') || {findings:[]};
  var evidence = pick('learningEvidence') || {items:[], summary:[]};
  var s = pick('shadowRules') || {variants:[]};
  var margin = pick('resultMarginIntel') || {summary:{}, records:[]};
  var capture = pick('captureIntel') || {categories:[], examples:[], recordCount:0, plainSummary:''};
  var fg = pick('fieldGraph') || {signalCounts:{}, topEdges:[], warnings:[]};
  var challenger = pick('challengerLab') || {challengers:[], live:{}, promotionCandidates:[], futureChallengersPlanned:[]};
  var marginRows = margin.records || [];
  var maxFinding = Math.max.apply(null, (l.findings || []).map(function(f){return f.count || 0;}).concat([1]));
  function toneColor(tone){
    return tone === 'good' ? 'var(--green)' : (tone === 'bad' ? 'var(--red)' : (tone === 'info' ? 'var(--blue)' : 'var(--amber)'));
  }
  function resultLabel(row){
    var result = row.result || 'UNKNOWN';
    var pos = row.position ? ' · '+row.position : '';
    return String(result).toUpperCase()+pos;
  }
  function evidenceCard(item){
    var color = toneColor(item.tone);
    var split = item.evidenceSplit || {};
    var total = Math.max(1, Number(split.sample || 0));
    var placedPct = Math.round((Number(split.placed || 0) / total) * 100);
    var lostPct = Math.round((Number(split.lost || 0) / total) * 100);
    var examples = (item.examples || []).slice(-3).reverse();
    var exHtml = examples.length ? examples.map(function(row){
      var exTone = row.resultGroup === 'placed' ? 'var(--green)' : (row.resultGroup === 'lost' ? 'var(--red)' : 'var(--muted2)');
      return '<div class="learn-example">'+
        '<div class="learn-example-top"><strong>'+esc(row.horse || 'Unknown')+'</strong><span style="color:'+exTone+'">'+esc(resultLabel(row))+'</span></div>'+
        '<div class="card-sub">'+esc(row.date || '')+' · '+esc(row.course || '')+' '+esc(row.time || '')+' · '+esc(row.details || '')+'</div>'+
        '<div class="learn-evidence-line">'+esc(row.evidence || 'No plain evidence note stored.')+'</div>'+
      '</div>';
    }).join('') : '<div class="empty">No horse examples stored for this finding yet.</div>';
    return '<div class="learn-card" style="--learn:'+color+'">'+
      '<div class="learn-head">'+
        '<div><div class="learn-title">'+esc(item.label || item.code)+'</div><div class="learn-code">'+esc(item.code || '')+'</div></div>'+
        '<div class="learn-count">'+esc(item.count || 0)+'<span>seen</span></div>'+
      '</div>'+
      '<div class="learn-split">'+
        '<div class="learn-split-bar"><span class="placed" style="width:'+placedPct+'%"></span><span class="lost" style="width:'+lostPct+'%"></span></div>'+
        '<div class="learn-split-text">'+esc(split.placed || 0)+' won/placed · '+esc(split.lost || 0)+' lost · '+esc(split.sample || 0)+' recent examples</div>'+
      '</div>'+
      '<div class="learn-meaning"><strong>Meaning:</strong> '+esc(item.plainMeaning || '')+'</div>'+
      '<div class="learn-meaning"><strong>Action:</strong> '+esc(item.currentAction || '')+'</div>'+
      '<div class="learn-examples">'+exHtml+'</div>'+
    '</div>';
  }
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
  function captureTile(cat){
    return '<div class="capture-tile"><h3>'+esc(cat.label || cat.key)+'</h3>'+
      '<div class="capture-value">'+esc(cat.count || 0)+'</div>'+
      '<div class="capture-copy">'+esc(cat.plain || '')+'</div>'+
      '<div class="capture-copy"><strong>Why it matters:</strong> '+esc(cat.why || 'Stored for future review.')+'</div></div>';
  }
  function captureRow(row){
    return '<div class="capture-row">'+
      '<div><div class="capture-horse">'+esc(row.horse || 'Unknown')+'</div>'+
        '<div class="capture-meta">'+esc(row.date || '')+' · '+esc(row.course || '')+' '+esc(row.time || '')+' · '+esc(row.selection_type || 'runner')+(row.score ? ' · score '+esc(row.score) : '')+'</div></div>'+
      '<div class="capture-chips">'+(row.chips || []).map(function(chip){ return pill(chip, 'blue'); }).join('')+'</div>'+
      '<div class="capture-note"><strong>Stored note:</strong> '+esc(row.note || 'Context captured for future comparison.')+'</div>'+
    '</div>';
  }
  function money(v){
    var n = Number(v || 0);
    var sign = n > 0 ? '+' : '';
    return sign+'£'+n.toFixed(2);
  }
  function challengerStatus(row){
    var status = row.status || 'COLLECTING';
    var cls = status === 'PROMOTION_CANDIDATE' ? 'good' : (status === 'DO_NOT_USE' ? 'bad' : 'amber');
    return '<span class="status-ribbon '+cls+'">'+esc(status.replace(/_/g,' ').toLowerCase())+'</span>';
  }
  function challengerCard(row){
    var profit = Number(row.profit || 0);
    var delta = Number(row.deltaVsLiveProfit || 0);
    var tone = profit >= 0 ? 'var(--green)' : 'var(--red)';
    var deltaTone = delta >= 0 ? 'var(--green)' : 'var(--red)';
    return '<div class="challenger-card">'+
      '<div class="challenger-top"><div><div class="challenger-name">'+esc(row.name || 'Challenger')+'</div><div class="card-sub">'+esc(row.daysTested || 0)+' days tested · '+esc(row.settledDays || 0)+' settled · '+esc(row.totalPicks || 0)+' paper picks</div></div>'+challengerStatus(row)+'</div>'+
      '<div class="challenger-metrics">'+
        '<div><span>Paper ROI</span><strong style="color:'+tone+'">'+esc(row.roi || 0)+'%</strong></div>'+
        '<div><span>Paper profit</span><strong style="color:'+tone+'">'+esc(money(row.profit))+'</strong></div>'+
        '<div><span>Vs live</span><strong style="color:'+deltaTone+'">'+esc(money(row.deltaVsLiveProfit))+'</strong></div>'+
      '</div>'+
      '<div class="challenger-rule">Needs enough settled days, enough picks, positive result versus live, no data leakage, and manual approval before it can affect selections.</div>'+
      (row.sampleWarning ? '<div class="challenger-warning">'+esc(row.sampleWarning)+'</div>' : '')+
    '</div>';
  }
  function challengerSection(){
    var rows = challenger.challengers || [];
    var live = challenger.live || {};
    var planned = challenger.futureChallengersPlanned || [];
    if(!challenger.available && !rows.length){
      return '<div class="chart-card"><div class="chart-title">Challenger Lab</div><div class="empty">Challenger Lab appears here after the dashboard feed refreshes.</div></div>';
    }
    return '<div class="section-block-h" style="margin-top:22px"><h2>Challenger Lab</h2><span class="n">future rules tested safely</span></div>'+
      '<div class="plain big"><strong>What this means:</strong> '+esc(challenger.plainSummary || 'Possible future rule changes are tested on paper only. They do not change live picks or proof.')+'</div>'+
      '<div class="challenger-board">'+
        '<div class="challenger-live">'+
          '<div class="chart-title">Current live rule</div>'+
          '<div class="live-metric"><span>ROI</span><strong>'+esc(live.roi || 0)+'%</strong></div>'+
          '<div class="live-metric"><span>Profit</span><strong>'+esc(money(live.profit))+'</strong></div>'+
          '<div class="card-sub">'+esc(live.bettingDays || 0)+' betting days · £'+esc(Number(live.stake || 0).toFixed(2))+' staked</div>'+
        '</div>'+
        '<div class="challenger-list">'+
          (rows.length ? rows.map(challengerCard).join('') : '<div class="empty">No challenger rules are being tested yet.</div>')+
        '</div>'+
      '</div>'+
      '<div class="challenger-footer">'+
        '<div><strong>Promotion candidates:</strong> '+esc((challenger.promotionCandidates || []).length || 0)+'</div>'+
        '<div><strong>Planned next tests:</strong> '+esc(planned.length ? planned.join(', ') : 'none listed')+'</div>'+
      '</div>';
  }
  document.getElementById('panel-learn').innerHTML =
    '<div class="section-hero learn"><div><div class="hero-kicker">Stage 04</div><div class="section-hero-title">Challenger Lab & learning</div><div class="section-hero-copy">This is now the single learning view. It shows paper-tested rule ideas, tipster evidence, horse memory, rival graph evidence, margins and repeat patterns. Nothing here changes public picks until manually approved.</div></div>'+
      '<div class="hero-stat">'+scoreChip((l.findings || []).length, 'FINDINGS', 'var(--blue)')+'</div></div>'+
    '<div class="learning-summary">'+
      (evidence.summary || []).map(function(row){return '<div>'+esc(row)+'</div>';}).join('')+
    '</div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      card('Days checked', gauge({value:evidence.newFormatDays || l.daysAnalysed || 0,max:Math.max(1,evidence.newFormatDays || l.daysAnalysed || 0),color:'var(--blue)',label:evidence.newFormatDays || l.daysAnalysed || 0,sub:'NEW FORMAT'}))+
      card('Official place rate', gauge({value:evidence.officialPlaceRate || l.officialPlaceRate || 0,color:'var(--green)',label:(evidence.officialPlaceRate || l.officialPlaceRate || 0)+'%',sub:'OFFICIAL'}))+
      card('Watchlist place rate', gauge({value:evidence.watchlistPlaceRate || l.watchlistPlaceRate || 0,color:'var(--blue)',label:(evidence.watchlistPlaceRate || l.watchlistPlaceRate || 0)+'%',sub:'WATCHLIST'}))+
    '</div>'+
    challengerSection()+
    '<div class="section-block-h" style="margin-top:22px"><h2>Learning evidence, with examples</h2></div>'+
    '<div class="learning-grid">'+
      ((evidence.items || []).length ? evidence.items.slice(0,10).map(evidenceCard).join('') : '<div class="empty">Learning evidence appears after the nightly training logs are published.</div>')+
    '</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Captured intelligence fields</h2></div>'+
    '<div class="plain" style="margin-bottom:14px"><strong>What this shows:</strong> '+esc(capture.plainSummary || 'The learning layer records context for every runner when the source data exists.')+' Blank fields mean the source did not provide that detail yet, not that the horse was ignored.</div>'+
    '<div class="capture-grid">'+
      ((capture.categories || []).length ? capture.categories.map(captureTile).join('') : '<div class="empty">Captured-field summary appears after the dashboard feed refreshes.</div>')+
    '</div>'+
    '<div class="chart-card" style="margin-top:16px"><div class="chart-title">Example records stored today</div>'+
      ((capture.examples || []).length ? capture.examples.slice(0,10).map(captureRow).join('') : '<div class="empty">No captured examples are available in this dashboard feed yet.</div>')+
    '</div>'+
    '<div class="grid grid-2" style="margin-top:16px">'+
      '<div class="chart-card"><div class="chart-title">Learning findings</div>'+
        ((l.findings || []).length ? l.findings.slice(0,9).map(function(f){return visualBar(f.code.replace(/_/g,' '), f.count, maxFinding, U.SEVERITY_COLOR[f.severity] || 'var(--blue)');}).join('') : '<div class="empty">Learning findings appear after the morning review.</div>')+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Shadow rules</div>'+
        ((s.variants || []).length ? s.variants.slice(0,6).map(function(v){return visualBar(v.name, v.roi || 0, 150, v.status==='candidate'?'var(--green)':'var(--gold)');}).join('') : '<div class="empty">No shadow rule comparison available yet.</div>')+
      '</div>'+
    '</div>'+
    '<div class="section-block-h" style="margin-top:22px"><h2>Horse-vs-horse graph learning</h2></div>'+
    '<div class="grid grid-3" style="margin-bottom:16px">'+
      card('Graph edges checked', gauge({value:fg.edgeCount || 0,max:Math.max(1,fg.edgeCount || 0),color:'var(--blue)',label:fg.edgeCount || 0,sub:'EDGES'}))+
      card('Strong edges', gauge({value:(fg.signalCounts || {}).strong_relationship_edge || 0,max:Math.max(1,fg.runnerCount || 0),color:'var(--green)',label:(fg.signalCounts || {}).strong_relationship_edge || 0,sub:'SUPPORT'}))+
      card('Warning edges', gauge({value:(fg.signalCounts || {}).relationship_warning || 0,max:Math.max(1,fg.runnerCount || 0),color:'var(--red)',label:(fg.signalCounts || {}).relationship_warning || 0,sub:'CAUTION'}))+
    '</div>'+
    '<div class="grid grid-2" style="margin-bottom:16px">'+
      '<div class="chart-card"><div class="chart-title">What the graph can teach</div>'+
        '<div class="plain"><strong>Direct edge:</strong> this horse has beaten one of today&#39;s rivals before.</div>'+
        '<div class="plain"><strong>Warning edge:</strong> today&#39;s rival has beaten this horse before.</div>'+
        '<div class="plain"><strong>Chain edge:</strong> this horse beat another horse that later beat today&#39;s rival. Useful, but weaker than direct proof.</div>'+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Latest graph examples</div>'+
        ((fg.topEdges || []).slice(0,4).map(function(row){return '<div class="graph-row"><div class="graph-main"><div class="graph-name">'+esc(row.horse)+'</div><div class="graph-note">'+esc(row.label)+'</div></div><div class="graph-score" style="color:var(--green)">'+esc(row.score)+'</div></div>';}).join('') || '<div class="empty">Graph examples appear after the field graph job runs.</div>')+
      '</div>'+
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

function renderChallengerLab(){
  var summary = challengerSummaryData();
  var legacyChallenger = pick('challengerLab') || {};
  var latest = challengerLatestData();
  var rows = challengerRows().map(normalizeChallenger);
  var candidates = promotionCandidateRows();
  var live = summary.live || latest.live_system || {};
  var latestRows = asArray(latest.pre_race_challengers);
  var best = rows.slice().sort(function(a,b){ return b.deltaProfit - a.deltaProfit; })[0] || null;
  var worst = rows.slice().sort(function(a,b){ return a.deltaProfit - b.deltaProfit; })[0] || null;
  var maxSettled = rows.reduce(function(m,r){ return Math.max(m, r.settled); }, 0);
  var liveRoi = num(firstDefined(live.roi, live.proof_roi), 0);
  var liveProfit = num(firstDefined(live.total_profit, live.profit), 0);
  function statePill(state){
    var s = trafficState(state);
    var tone = (s === 'RISKY') ? 'red' : ((s === 'PROMOTION_CANDIDATE' || s === 'APPROVED_BY_JOHN') ? 'gold' : (s === 'PROMISING' ? 'green' : (s === 'WATCHING' ? 'amber' : 'grey')));
    return pill(TRAFFIC_TEXT[s].label, tone);
  }
  function statTile(label, value, tone){
    return '<div class="lab-stat-tile '+(tone || '')+'"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>';
  }
  function challengerCard(row){
    var verdict = TRAFFIC_TEXT[row.stage] || TRAFFIC_TEXT.COLLECTING;
    var deltaTone = row.deltaProfit >= 0 ? 'good' : 'bad';
    var spark = asArray(row.raw.daily_profit || row.raw.dailyProfit || row.raw.profit_series || row.raw.profitSeries);
    var fieldAware = (legacyChallenger.fieldAwareVsOldOverlay || summary.field_aware_vs_old_overlay || summary.fieldAwareVsOldOverlay || {});
    if(row.stage === 'ARCHIVED'){
      var range = (challengerSummaryData().date_range || {});
      return '<div class="lab-card state-archived" style="border-color:rgba(107,114,128,.35);background:rgba(107,114,128,.06);padding:14px">'+
        '<div style="display:flex;gap:14px;align-items:flex-start">'+
          trafficLight('ARCHIVED', 'small', false)+
          '<div style="flex:1;min-width:0"><div class="lab-card-title"><div>'+esc(row.name)+'</div><span>'+esc(row.id)+'</span></div>'+
            '<div class="plain" style="margin-top:10px;border-left-color:var(--grey);background:rgba(107,114,128,.08)">This challenger was tested and archived. Verdict: '+esc(row.raw.promotion_status || 'ARCHIVED')+'</div>'+
            '<div class="card-sub">Date range tested: '+esc(range.start || 'unknown')+' to '+esc(range.end || 'unknown')+' · Settled days: '+esc(row.settled)+' · Paper profit: '+esc(signedMoney(row.profit))+' · Vs live '+esc(signedMoney(row.deltaProfit))+'</div>'+
            (row.raw.archived_reason ? '<div class="card-sub" style="margin-top:8px">'+esc(row.raw.archived_reason)+'</div>' : '')+
          '</div>'+
        '</div>'+
      '</div>';
    }
    if(row.id === 'rival_evidence_v1'){
      var better = num(fieldAware.days_field_aware_better || fieldAware.daysFieldAwareBetter, 0);
      var oldBetter = num(fieldAware.days_old_better || fieldAware.daysOldBetter, 0);
      var running = better > oldBetter
        ? '<span class="pill good">Leading old overlay '+esc(better)+' to '+esc(oldBetter)+'</span>'
        : (better === oldBetter ? '<span class="pill grey">Level so far</span>' : '<span class="pill amber">Old overlay leading '+esc(oldBetter)+' to '+esc(better)+'</span>');
      return '<div class="lab-card state-'+row.stage.toLowerCase().replace(/_/g, '-')+'">'+
        '<div class="lab-card-row top">'+
          trafficLight(row.stage, 'large', false)+
          '<div class="lab-card-title"><div>Field-Aware Rival History</div><span>rival_evidence_v1</span>'+
            '<div class="lab-traffic-summary"><strong>'+esc(verdict.label)+'</strong><small>'+esc(verdict.verdict)+'</small></div></div>'+
          '<div class="lab-stat-pair">'+statTile('Days tested', row.days, '')+statTile('Settled', row.settled, '')+'</div>'+
        '</div>'+
        '<div style="font-family:var(--display);font-size:34px;color:var(--gold);margin-top:10px">18,000,000</div>'+
        '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted2);text-transform:uppercase">records · field-matched only</div>'+
        '<div class="plain" style="margin-top:12px">Same scoring as live Signal 75, but rival evidence only counts when the rival is actually running today. Confirmed better than the old approach on 9 July — found Del Maro and Thunder Call, both placed, while the old system was boosting a non-runner.</div>'+
        '<div class="lab-status-line">'+running+'</div>'+
        '<details class="lab-details"><summary>Show criteria and notes</summary>'+
          '<div class="card-sub">Picks tested: '+esc(row.picks)+' · Paper profit: '+esc(signedMoney(row.profit))+' · Vs live '+esc(signedMoney(row.deltaProfit))+'</div>'+
          '<div class="challenger-warning">Manual approval required before any rival challenger affects live picks.</div>'+
        '</details>'+
      '</div>';
    }
    return '<div class="lab-card state-'+row.stage.toLowerCase().replace(/_/g, '-')+'">'+
      '<div class="lab-card-row top">'+
        trafficLight(row.stage, 'large', false)+
        '<div class="lab-card-title"><div>'+esc(row.name)+'</div><span>'+esc(row.id)+'</span>'+
          '<div class="lab-traffic-summary"><strong>'+esc(verdict.label)+'</strong><small>'+esc(verdict.verdict)+'</small></div></div>'+
        '<div class="lab-stat-pair">'+statTile('Days tested', row.days, '')+statTile('Settled', row.settled, '')+'</div>'+
      '</div>'+
      '<div class="lab-gauges">'+
        '<div class="lab-meter"><span>Delta vs live</span><strong class="'+deltaTone+'">'+esc(signedMoney(row.deltaProfit))+' · '+esc(signedPct(row.deltaRoi))+'</strong></div>'+
        '<div class="lab-meter"><span>Paper ROI</span><strong class="'+(row.roi >= 0 ? 'good' : 'bad')+'">'+esc(row.roi.toFixed(1).replace(/\.0$/,''))+'%</strong></div>'+
      '</div>'+
      '<div class="lab-spark">'+(spark.length ? sparkline(spark, row.deltaProfit >= 0 ? 'var(--green)' : 'var(--red)', 220, 42) : '<div class="empty mini">Collecting data...</div>')+'</div>'+
      '<div class="lab-status-line">'+statePill(row.stage)+'</div>'+
      '<details class="lab-details"><summary>Show criteria and notes</summary>'+
        '<div class="card-sub">Picks tested: '+esc(row.picks)+' · Paper profit: '+esc(signedMoney(row.profit))+'</div>'+
        (row.warning ? '<div class="challenger-warning">'+esc(row.warning)+'</div>' : '<div class="card-sub">No additional warning stored.</div>')+
      '</details>'+
    '</div>';
  }
  function liveVsChallenger(){
    var livePicks = asArray(latest.live_system && latest.live_system.official_picks);
    var firstChallenger = latestRows[0] || {};
    var challengerPicks = asArray(firstChallenger.picks);
    return '<div class="lab-section"><div class="section-block-h"><h2>Today: live vs challenger</h2><span class="n">paper comparison only</span></div>'+
      '<div class="lab-compare-grid">'+
        '<div class="compare-card"><div class="chart-title">Live official selections</div>'+
          (livePicks.length ? livePicks.map(function(p){ return '<div class="pick-pill live"><strong>'+esc(p.horse || p.name)+'</strong><span>'+esc(p.course || '')+' '+esc(p.time || '')+' · '+esc(p.odds || '')+'</span></div>'; }).join('') : '<div class="empty">No live pick list in this dashboard feed.</div>')+
        '</div>'+
        '<div class="compare-card"><div class="chart-title">'+esc(firstChallenger.name || 'Best challenger')+'</div>'+
          (challengerPicks.length ? challengerPicks.map(function(p){ return '<div class="pick-pill challenger"><strong>'+esc(p.horse || p.name)+'</strong><span>'+esc(p.course || '')+' '+esc(p.time || '')+' · '+esc(p.odds || '')+(p.live_selected ? ' · also live' : ' · paper only')+'</span></div>'; }).join('') : '<div class="empty">No challenger pick list in this dashboard feed yet.</div>')+
        '</div>'+
      '</div></div>';
  }
  function differenceTable(){
    var diffs = [];
    latestRows.forEach(function(ch){
      asArray(ch.picks).forEach(function(p){
        if(!p.live_selected){
          diffs.push({rule:ch.name || ch.id, horse:p.horse || p.name, course:p.course, time:p.time, odds:p.odds, score:firstDefined(p.combined_score,p.base_score,p.score), why:'Challenger only'});
        }
      });
    });
    return '<div class="lab-section"><div class="section-block-h"><h2>Pick difference view</h2><span class="n">what changed on paper</span></div>'+
      '<div class="diff-table">'+
        '<div class="diff-head"><span>Challenger</span><span>Horse</span><span>Race</span><span>Score</span><span>Why</span></div>'+
        (diffs.length ? diffs.slice(0,12).map(function(d){ return '<div class="diff-row"><span>'+esc(d.rule)+'</span><strong>'+esc(d.horse)+'</strong><span>'+esc((d.course||'')+' '+(d.time||'')+' · '+(d.odds||''))+'</span><span>'+esc(d.score || '')+'</span><span>'+esc(d.why)+'</span></div>'; }).join('') : '<div class="empty">No pick differences stored yet.</div>')+
      '</div></div>';
  }
  function dials(){
    var positives = rows.filter(function(r){ return r.deltaProfit > 0; }).length;
    var negatives = rows.filter(function(r){ return r.deltaProfit < 0; }).length;
    var neutral = Math.max(0, rows.length - positives - negatives);
    return '<div class="lab-section"><div class="section-block-h"><h2>Improvement vs damage</h2><span class="n">quick read</span></div>'+
      '<div class="grid grid-4">'+
        card('Improving', gauge({value:positives,max:Math.max(1,rows.length),color:'var(--green)',label:positives,sub:'rules'}))+
        card('Worse than live', gauge({value:negatives,max:Math.max(1,rows.length),color:'var(--red)',label:negatives,sub:'rules'}))+
        card('Neutral / collecting', gauge({value:neutral,max:Math.max(1,rows.length),color:'var(--amber)',label:neutral,sub:'rules'}))+
        card('Best paper gain', '<div class="card-big" style="font-size:24px;color:'+(best && best.deltaProfit >= 0 ? 'var(--green)' : 'var(--red)')+'">'+esc(best ? signedMoney(best.deltaProfit) : '£0')+'</div><div class="card-sub">'+esc(best ? best.name : 'No challenger data')+'</div>')+
      '</div></div>';
  }
  function postRaceTools(){
    var tools = asArray(latest.post_race_tools || []);
    return '<div class="lab-section"><div class="section-block-h"><h2>Post-race learning tools</h2><span class="n">after results</span></div>'+
      '<div class="grid grid-auto">'+(tools.length ? tools.map(function(t){
        return '<div class="autotile"><div class="ah">'+trafficDot(U.JOB_COLOR[t.status || 'pending'])+'<span class="at-time">'+esc(t.time || '')+'</span></div><div class="at-label">'+esc(t.label || t.name || 'Learning tool')+'</div><div class="card-sub">'+esc(t.detail || t.status || 'scheduled')+'</div></div>';
      }).join('') : '<div class="card"><div class="card-big" style="font-size:18px">No post-race tool list available</div><div class="card-sub">The normal learning jobs still run from the main pipeline.</div></div>')+'</div></div>';
  }
  function promotionQueue(){
    return '<div class="lab-section"><div class="section-block-h"><h2>Promotion queue</h2><span class="n">manual approval only</span></div>'+
      '<div class="lab-queue '+(candidates.length ? 'has-candidate' : '')+'">'+
        (candidates.length ? candidates.map(function(c){
          return '<div class="queue-row">'+trafficLight('PROMOTION_CANDIDATE','mini',false)+'<div><strong>'+esc(c.name || c.id || 'Promotion candidate')+'</strong><div class="card-sub">'+esc(c.reason || 'Ready for John to review. No automatic live change.').replace(/</g,'&lt;')+'</div></div></div>';
        }).join('') : '<div class="empty">No challenger is ready for approval. This is normal while evidence builds.</div>')+
      '</div></div>';
  }
  document.getElementById('panel-learn').innerHTML =
    '<div class="lab-warning"><strong>Challenger Lab - not live</strong><span>Experimental parallel signals only. No effect on official selections, proof, ROI, results or public selections.</span></div>'+
    '<div class="lab-summary-grid">'+
      card('Live ROI in period', gauge({value:Math.abs(liveRoi),max:150,color:'var(--gold)',label:liveRoi+'%',sub:signedMoney(liveProfit)}))+
      card('Best challenger delta', gauge({value:Math.abs(best ? best.deltaRoi : 0),max:100,color:(best && best.deltaProfit >= 0)?'var(--green)':'var(--red)',label:best?signedPct(best.deltaRoi):'0%',sub:best?signedMoney(best.deltaProfit):'no data'}))+
      card('Worst challenger delta', gauge({value:Math.abs(worst ? worst.deltaRoi : 0),max:100,color:(worst && worst.deltaProfit < 0)?'var(--red)':'var(--green)',label:worst?signedPct(worst.deltaRoi):'0%',sub:worst?signedMoney(worst.deltaProfit):'no data'}))+
      card('Settled days', '<div class="lab-count blue">'+esc(maxSettled)+'</div><div class="card-sub">maximum settled challenger sample</div>')+
      card('Challengers running', '<div class="lab-count">'+esc(rows.length)+'</div><div class="card-sub">paper rules active</div>')+
      card('Promotion candidates', '<div class="lab-count '+(candidates.length?'gold-pulse':'')+'">'+esc(candidates.length)+'</div><div class="card-sub">'+(candidates.length?'review required':'none ready')+'</div>')+
    '</div>'+
    liveVsChallenger()+
    '<div class="lab-section"><div class="section-block-h"><h2>Challenger cards</h2><span class="n">traffic light first</span></div>'+
      (rows.length ? rows.map(challengerCard).join('') : '<div class="card">'+trafficLight('COLLECTING','large',true)+'<div class="empty">No challenger rows are available yet.</div></div>')+
    '</div>'+
    differenceTable()+dials()+postRaceTools()+promotionQueue();
}

/* ---------------------------------------------------------------------
   NAV CONFIG + BOOT
   --------------------------------------------------------------------- */
var NAV = [
  {group:'SIGNAL 75', items:[
	    {id:'status', label:'Today', ico:'\u29bf', render:renderStrategyToday, keys:['status','selectionAudit','performance','dataCoverage','continuousLearning','officialPicks','watchlist']},
		    {id:'picks', label:'Today\'s Picks', ico:'\u2315', render:renderTodaysPicks, keys:['officialPicks','watchlist','raceView','status','patentViability','pickQualityAudit']},
	    {id:'confirm', label:'Confirm', ico:'\u2726', render:renderConfirm, keys:['tipsterIntel','dbStatus','horseMemory','fieldGraph','raceView','challengerLab','challengerSummary','challengerLatest']},
	    {id:'learn', label:'Challenger Lab', ico:'\u27f2', render:renderChallengerLab, keys:['challengerLab','challengerSummary','challengerLatest','promotionCandidates','continuousLearning','learningEvidence','shadowRules','resultMarginIntel','fieldGraph','captureIntel']},
    {id:'proof', label:'Results', ico:'\u21d5', render:renderProof, keys:['performance','continuousLearning','patentViability']},
    {id:'automation', label:'System', ico:'\u2699', render:renderAutomation, keys:['automation','apiCostControl','dataCoverage','challengerLab','challengerSummary','promotionCandidates']}
  ]}
];
var FLAT = [];
NAV.forEach(function(g){ g.items.forEach(function(it){ FLAT.push(it); }); });

var DATA_PATHS = {
  challengerLab:['challengerLab.json'],
  challengerSummary:['challenger_lab/challenger_summary.json'],
  challengerLatest:['challenger_lab/challenger_latest.json'],
  promotionCandidates:['challenger_lab/promotion_candidates.json']
};
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
    var fetches = (it.keys||[]).map(function(k){ return window.S75.loadReal(k, DATA_PATHS[k] || [k+'.json']); });
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
      document.body.innerHTML = '<main style="max-width:640px;margin:14vh auto;padding:32px;font-family:Arial,sans-serif;color:#f4f4f5;background:#0d0d12;border:1px solid #30303a;border-radius:8px"><div style="color:#f4c542;font-weight:800;letter-spacing:0">SIGNAL 75 INTELLIGENCE</div><h1 style="font-size:30px;margin:18px 0 10px">Private dashboard</h1><p style="line-height:1.6;color:#c8c8d2">This read-only dashboard is available only on the protected local Signal 75 system. No private intelligence data is published on the public website.</p></main>';
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
