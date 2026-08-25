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

function dashboardDate(){
  var status = pick('status') || {};
  var ready = pick('dashboardReady') || {};
  var selectionAudit = pick('selectionAudit') || {};
  var raceView = pick('raceView') || {};
  var official = pick('officialPicks') || [];
  return status.date || raceView.date || selectionAudit.date || ready.date || ((official[0] || {}).date) || '';
}

function raceContext(row, race){
  row = row || {};
  race = race || {};
  var bits = [];
  var date = row.date || race.date || dashboardDate();
  var course = row.course || row.venue || race.course || '';
  var time = row.time || row.race_time || race.time || '';
  var raceName = row.race || row.race_name || row.raceName || race.race || race.race_name || '';
  if(date) bits.push(date);
  if(course) bits.push(course);
  if(time) bits.push(time);
  if(raceName) bits.push(raceName);
  return bits.join(' · ');
}

function raceContextHtml(row, race){
  return esc(raceContext(row, race));
}

function modeExplanation(mode){
  var messages = {
    qualified: 'Three horses passed every official rule, so today is an each-way Patent.',
    topRatedOnly: 'One or two horses passed every official rule. Signal 75 does not force extra horses, so the bet becomes a Single or Double.',
    noBetDay: 'No horse passed every official rule today. No official bet is placed.'
  };
  return messages[mode] || 'The day\'s published selection mode is being checked.';
}

function proofDayContext(perf){
  perf = perf || {};
  var betting = Number(perf.bettingDays || 0);
  var total = Number(perf.totalDays || betting || 0);
  var noBet = Number(perf.noBetDays || 0);
  var text = 'ROI is calculated from '+betting+' official betting days only.';
  if(noBet > 0){
    text += ' '+noBet+' no-bet or recovery day'+(noBet === 1 ? '' : 's')+' are excluded from stake, profit and ROI.';
  }
  if(total && total !== betting){
    text += ' '+total+' calendar/result days are tracked separately.';
  }
  return text;
}

function proofGuardHtml(){
  var proof = pick('proofStatus') || {};
  var status = String(proof.status || 'UNKNOWN').toUpperCase();
  var tone = status === 'OK' ? 'var(--green)' : status === 'WARNING' ? 'var(--gold)' : 'var(--red)';
  var current = proof.current || {};
  var bits = [];
  if(current.roi !== undefined) bits.push('ROI '+esc(current.roi)+'%');
  if(proof.roiChangePoints !== null && proof.roiChangePoints !== undefined) bits.push('movement '+(Number(proof.roiChangePoints) >= 0 ? '+' : '')+esc(proof.roiChangePoints)+' pts');
  var detail = bits.length ? bits.join(' · ') : 'Snapshot not available yet';
  return '<div class="plain" style="border-left:3px solid '+tone+';margin-top:10px">'+
    '<strong style="color:'+tone+'">Proof guard: '+esc(status)+'</strong>'+
    '<div style="margin-top:4px">'+detail+'</div>'+
    ((proof.warnings || []).length ? '<div style="margin-top:4px;color:var(--gold)">Warnings: '+esc((proof.warnings || []).length)+'</div>' : '')+
    ((proof.errors || []).length ? '<div style="margin-top:4px;color:var(--red)">Errors: '+esc((proof.errors || []).length)+'</div>' : '')+
  '</div>';
}

function sqliteBrain(){
  var intel = pick('sqliteIntelligence') || {};
  var coverage = intel.learningCoverage || {};
  var status = intel.summaryStatus || {};
  var asOf = status.asOfDate || intel.asOfDate || intel.date || '';
  var today = dashboardDate() || new Date().toISOString().slice(0, 10);
  var fresh = asOf && String(asOf).slice(0, 10) === String(today).slice(0, 10);
  var horses = num(coverage.horsesProfiled, 0);
  var h2h = num(coverage.h2hPairs, 0);
  var forms = num(coverage.formPatterns, 0);
  var races = num(coverage.raceReviewDays, 0);
  var challengers = num(coverage.challengersTracked, 0);
  var healthy = fresh && horses > 0 && h2h > 0 && forms > 0 && races > 0;
  var tone = healthy ? 'green' : (asOf ? 'gold' : 'red');
  return {
    raw:intel,
    coverage:coverage,
    status:status,
    asOf:asOf,
    fresh:fresh,
    healthy:healthy,
    tone:tone,
    horses:horses,
    h2h:h2h,
    forms:forms,
    races:races,
    challengers:challengers,
    latestRaceReview:intel.latestRaceReview || {},
    challengerSummary:asArray(intel.challengerSummary)
  };
}

function sqliteBrainCard(title, copy){
  var brain = sqliteBrain();
  var color = brain.tone === 'green' ? 'var(--green)' : (brain.tone === 'gold' ? 'var(--gold)' : 'var(--red)');
  return '<div class="card" style="border-color:'+color+'55">'+
    '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px">'+
      '<div><div class="card-label">'+esc(title || 'SQLite summary brain')+'</div>'+
      '<div class="card-sub">'+esc(copy || 'Fast summary tables for dashboard and review pages.')+'</div></div>'+
      pill(brain.healthy ? 'fresh' : (brain.asOf ? 'check' : 'missing'), brain.tone)+
    '</div>'+
    '<div class="grid grid-4" style="gap:8px">'+
      '<div class="lab-stat-tile"><span>Horses</span><strong>'+esc(brain.horses.toLocaleString('en-GB'))+'</strong></div>'+
      '<div class="lab-stat-tile"><span>H2H pairs</span><strong>'+esc(brain.h2h.toLocaleString('en-GB'))+'</strong></div>'+
      '<div class="lab-stat-tile"><span>Form patterns</span><strong>'+esc(brain.forms.toLocaleString('en-GB'))+'</strong></div>'+
      '<div class="lab-stat-tile"><span>Race reviews</span><strong>'+esc(brain.races.toLocaleString('en-GB'))+'</strong></div>'+
    '</div>'+
    '<div class="card-sub" style="margin-top:10px">Summary date: '+esc(brain.asOf || 'not exported')+' · scoring impact: none</div>'+
  '</div>';
}

function officialBetModel(count){
  count = Number(count || 0);
  if(count >= 3) return {
    count:count, kind:'patent', label:'Each-way Patent', shortLabel:'Patent', stake:14, lines:14,
    summary:'3 official selections. Full Patent available.',
    explanation:'Three official selections make a Patent: 3 singles, 3 doubles and 1 treble, all each-way.'
  };
  if(count === 2) return {
    count:count, kind:'double', label:'Each-way Double', shortLabel:'Double', stake:14, lines:6,
    summary:'2 official selections. Not enough for a Patent, so today is a Double.',
    explanation:'Two official selections make a Double. Signal 75 measures the day against a £14 proof stake.'
  };
  if(count === 1) return {
    count:count, kind:'single', label:'Each-way Single', shortLabel:'Single', stake:14, lines:2,
    summary:'1 official selection. Not enough for a Double or Patent, so today is a Single.',
    explanation:'One official selection makes an each-way Single. Signal 75 measures the day against a £14 proof stake.'
  };
  return {
    count:0, kind:'none', label:'No official bet', shortLabel:'No bet', stake:0, lines:0,
    summary:'0 official selections. No bet today.',
    explanation:'No horse passed every official rule, so Signal 75 stays out.'
  };
}

function rawBetStakeForKind(kind){
  kind = String(kind || '').toLowerCase();
  if(kind === 'patent') return 14;
  if(kind === 'double') return 6;
  if(kind === 'single') return 2;
  return 0;
}

function proofStakeForGroup(rawStake, rawTotal){
  rawStake = Number(rawStake || 0);
  rawTotal = Number(rawTotal || 0);
  if(!rawStake || !rawTotal) return 0;
  return Math.round((rawStake * (14 / rawTotal)) * 100) / 100;
}

function moneyText(value){
  value = Number(value || 0);
  return value % 1 === 0 ? value.toFixed(0) : value.toFixed(2);
}

function officialBetModelFromPicks(){
  return officialBetModel((pick('officialPicks') || []).length);
}

function formatCount(value){
  var n = Number(value || 0);
  if(!isFinite(n)) n = 0;
  return n.toLocaleString();
}

function sqliteHeadToHeadRows(){
  var db = pick('dbStatus') || {};
  var challenger = pick('challengerLab') || {};
  var rows = Number(
    db.headToHeadRows ||
    db.head_to_head_rows ||
    db.headToHeadRecordCount ||
    db.recordCount ||
    0
  );
  if(!rows && Array.isArray(challenger.challengers)){
    challenger.challengers.some(function(row){
      if(row && row.id === 'rival_evidence_v1'){
        rows = Number(row.recordCount || row.recordsChecked || row.headToHeadRows || 0);
        return rows > 0;
      }
      return false;
    });
  }
  return rows;
}

function sqliteHeadToHeadRowsLabel(){
  var rows = sqliteHeadToHeadRows();
  return rows ? formatCount(rows) : 'Checking';
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
    var line = model.kind === 'patent' ? '3 picks found · £14 proof stake · 14 lines' : model.kind === 'double' ? '2 picks found · £14 proof stake · 6 lines' : model.kind === 'single' ? '1 pick found · £14 proof stake · 2 lines' : 'No horse met all the required criteria today';
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
    verdict:'Worse than live picks. Consistently worse than the current system.'
  },
  REJECTED: {
    label:'Rejected',
    verdict:'Tested and rejected. Kept for audit trail only.'
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
  if(s === 'TESTED_AND_REJECTED' || s === 'REJECTED') return 'REJECTED';
  if(s === 'INCONCLUSIVE_AT_30_DAYS') return 'ARCHIVED';
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
  var rows = asArray(s.pre_race_challengers || s.challengers);
  var seen = {};
  rows.forEach(function(row){ seen[firstDefined(row.id, row.rule_id, row.name)] = true; });
  asArray(latest.pre_race_challengers).forEach(function(row){
    var id = firstDefined(row.id, row.rule_id, row.name);
    if(!seen[id]) rows.push(row);
  });
  return rows.length ? rows : asArray(latest.pre_race_challengers);
}
function normalizeChallenger(row){
  return {
    id:firstDefined(row.id, row.rule_id, row.name, 'challenger'),
    name:firstDefined(row.name, row.label, row.id, 'Challenger'),
    stage:trafficState(firstDefined(row.promotion_stage, row.promotion_status, row.status, 'COLLECTING')),
    days:num(firstDefined(row.days_tested, row.daysTested), 0),
    settled:num(firstDefined(row.settled_days, row.settledDays), 0),
    roiReadyDays:num(firstDefined(row.roi_ready_days, row.roiReadyDays, row.settled_days, row.settledDays), 0),
    daysWithPicks:num(firstDefined(row.days_with_picks, row.daysWithPicks), 0),
    pickResultDays:num(firstDefined(row.pick_result_days, row.pickResultDays), 0),
    completePickResultDays:num(firstDefined(row.complete_pick_result_days, row.completePickResultDays), 0),
    settledPickCount:num(firstDefined(row.settled_pick_count, row.settledPickCount), 0),
    picks:num(firstDefined(row.total_picks, row.totalPicks), 0),
    roi:num(firstDefined(row.roi, row.paper_roi), 0),
    profit:num(firstDefined(row.total_profit, row.profit), 0),
    deltaRoi:num(firstDefined(row.delta_vs_live_roi, row.deltaVsLiveRoi, row.delta_roi), 0),
    deltaProfit:num(firstDefined(row.delta_vs_live_profit, row.deltaVsLiveProfit, row.delta_profit), 0),
    warning:firstDefined(row.sample_warning, row.sampleWarning, row.warning, ''),
    settlementExplanation:firstDefined(row.settlement_explanation, row.settlementExplanation, ''),
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
      card('Today\'s official bet', '<div class="card-big" style="font-size:17px">'+esc(officialBetSummaryText())+'</div><div class="card-sub">The official proof stake is £14 for the day. Flat and Jumps can be shown as separate bet groups when needed.</div>')+
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
          '<div class="card-sub">'+raceContextHtml(p)+' \u00b7 '+esc(p.jockey)+' / '+esc(p.trainer)+'</div>'+
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
          '<div class="card-sub">'+raceContextHtml(w)+' \u00b7 '+esc(w.odds)+' odds</div>'+
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
      '<div class="racepick"><div style="font-family:var(--body);font-weight:800;font-size:15px;letter-spacing:0">'+raceContextHtml(r, {date:data.date})+'</div>'+
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
  var liveStatus = db.liveLearningStatus || 'UNKNOWN';
  var formStatus = db.richFormArchiveStatus || 'UNKNOWN';
  var liveTone = liveStatus === 'OK' ? 'var(--green)' : 'var(--red)';
  var formTone = formStatus === 'OK' ? 'var(--green)' : 'var(--amber)';
  var freshnessBlock = '<div class="card" style="margin-bottom:18px"><div class="card-label">Data freshness</div>'+
    '<div class="grid grid-2">'+
      '<div><div style="font-family:var(--display);font-size:30px;color:'+liveTone+'">'+esc(liveStatus)+'</div><div class="card-sub">Daily rival memory latest: '+esc(db.liveLearningLatestDate || db.latestHeadToHeadDate || 'unknown')+'</div><div class="plain">Central daily learning store: who beat who, class, weight, draw, trainer, jockey and result context.</div></div>'+
      '<div><div style="font-family:var(--display);font-size:30px;color:'+formTone+'">'+esc(formStatus)+'</div><div class="card-sub">Rich form archive latest: '+esc(db.richFormArchiveLatestDate || 'unknown')+'</div><div class="plain">Imported historical form archive. If stale, it stays as old pattern evidence until a fresh source is added.</div></div>'+
    '</div>'+
    (db.richFormArchiveWarning ? '<div class="plain" style="border-left-color:var(--amber);margin-top:12px">'+esc(db.richFormArchiveWarning)+'</div>' : '')+
  '</div>';
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
    freshnessBlock+
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
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start"><div><div style="font-size:18px;font-weight:800">'+esc(item.horse)+'</div><div class="card-sub">'+raceContextHtml(item)+' · '+esc(item.selection_type)+'</div></div>'+pill('Score '+item.signal_score,'gold')+'</div>'+
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
    '<div class="section-hero protect"><div><div class="hero-kicker">Official bet type</div><div class="section-hero-title">'+esc(officialBetSummaryText())+'</div><div class="section-hero-copy">Signal 75 uses one £14 proof stake for the day. Flat and Jumps can be shown as separate bet groups when needed.</div></div></div>'+
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
        '<div class="card-sub">'+fmtGBP(perf.totalProfit)+' total \u00b7 '+perf.bettingDays+' official betting days \u00b7 win rate '+perf.winRate+'%</div>'+
        '<div class="plain" style="margin-top:10px">'+esc(proofDayContext(perf))+'</div>'+
        proofGuardHtml())+
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
  var maxSettled = rows.reduce(function(m,r){ return Math.max(m, normalizeChallenger(r).roiReadyDays); }, 0);
  var candidateCount = candidates.length;
  var manual = a.manualByDesign || a.manual_by_design || [];
  var brain = sqliteBrain();
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
        '<div class="card-sub">'+esc(rows.length)+' challengers running · '+esc(maxSettled || (summary.live || {}).betting_days || 0)+' ROI-ready days</div></div>'+
      '<div class="challenger-system-action">'+
        '<span class="candidate-badge '+(candidateCount ? 'gold' : 'grey')+'">'+esc(candidateCount)+' '+(candidateCount===1?'candidate':'candidates')+'</span>'+
        '<button type="button" class="text-link" onclick="window.S75ui.activate(\'learn\')">View Lab</button>'+
      '</div>'+
    '</div>'+
  '</div>';
  document.getElementById('panel-automation').innerHTML = badge('automation') +
    sqliteBrainCard('SQLite data health', 'Central summary tables now power quick dashboard checks without changing live picks.')+
    '<div class="grid grid-3" style="margin:18px 0">'+
      card('Summary freshness', '<div class="card-big" style="font-size:20px;color:'+(brain.fresh?'var(--green)':'var(--gold)')+'">'+esc(brain.asOf || 'missing')+'</div><div class="card-sub">'+(brain.fresh?'Updated for the current dashboard date':'Needs checking if this is not today')+'</div>')+
      card('Race-review memory', '<div class="card-big" style="font-size:20px;color:var(--blue)">'+esc(brain.races.toLocaleString('en-GB'))+'</div><div class="card-sub">settled review days summarized for fast lookup</div>')+
      card('Challenger memory', '<div class="card-big" style="font-size:20px;color:var(--gold)">'+esc(brain.challengers.toLocaleString('en-GB'))+'</div><div class="card-sub">paper-test rows summarized from SQLite</div>')+
    '</div>'+
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
      rows.push(Object.assign({date: data.date || race.date, course: race.course, time: race.time, race_name: race.race_name, field_size: race.field_size}, r));
    });
  });
  return rows;
}

function renderSystemMap(){
  var perf = pick('performance') || {};
  var dataCoverage = pick('dataCoverage') || {};
  var db = pick('dbStatus') || {};
  var api = pick('apiCostControl') || {};
  var sqliteIntel = pick('sqliteIntelligence') || {};
  var learningCoverage = sqliteIntel.learningCoverage || {};
  function flowStep(num, title, body, tone){
    return '<div style="position:relative;border:1px solid rgba(255,255,255,.10);border-radius:var(--r-sm);background:linear-gradient(135deg,rgba(255,255,255,.055),rgba(255,255,255,.02));padding:16px;min-height:142px">'+
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px">'+
        '<div style="width:34px;height:34px;border-radius:50%;display:grid;place-items:center;background:'+tone+';color:#06100b;font-weight:900;font-family:var(--mono);font-size:13px">'+esc(num)+'</div>'+
        '<div style="font-family:var(--mono);font-size:10px;color:var(--muted2);letter-spacing:.11em;text-transform:uppercase">read only</div>'+
      '</div>'+
      '<div style="font-size:18px;font-weight:850;line-height:1.3;color:var(--text);margin-bottom:8px">'+esc(title)+'</div>'+
      '<div style="font-size:13px;line-height:1.75;color:var(--muted)">'+body+'</div>'+
    '</div>';
  }
  function arrow(){ return '<div style="display:grid;place-items:center;color:var(--gold);font-family:var(--mono);font-size:24px;opacity:.9">→</div>'; }
  function miniCard(title, rows, tone){
    return '<div class="card" style="padding:18px;border-color:'+tone+'">'+
      '<div style="font-family:var(--mono);font-size:11px;color:'+tone+';letter-spacing:.12em;text-transform:uppercase;line-height:1.6;margin-bottom:10px">'+esc(title)+'</div>'+
      rows.map(function(row){
        return '<div style="display:flex;gap:10px;align-items:flex-start;border-top:1px solid rgba(255,255,255,.07);padding:10px 0">'+
          '<span style="color:'+tone+';font-family:var(--mono);font-size:13px;line-height:1.6">●</span>'+
          '<div style="font-size:13px;line-height:1.65;color:var(--muted)">'+row+'</div>'+
        '</div>';
      }).join('')+
    '</div>';
  }
  function scriptRow(time, label, script, output, tone){
    return '<div style="display:grid;grid-template-columns:88px minmax(150px,1fr) minmax(190px,1.25fr);gap:12px;align-items:start;border-top:1px solid rgba(255,255,255,.075);padding:12px 0">'+
      '<div style="font-family:var(--mono);font-size:12px;color:'+tone+';line-height:1.6">'+esc(time)+'</div>'+
      '<div><div style="font-weight:800;font-size:14px;line-height:1.45;color:var(--text)">'+esc(label)+'</div><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6">'+esc(script)+'</div></div>'+
      '<div style="font-size:13px;line-height:1.65;color:var(--muted)">'+output+'</div>'+
    '</div>';
  }
  function storeRow(name, path, purpose){
    return '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:13px;background:rgba(255,255,255,.025)">'+
      '<div style="font-weight:850;font-size:14px;line-height:1.45;color:var(--text)">'+esc(name)+'</div>'+
      '<div style="font-family:var(--mono);font-size:11px;line-height:1.7;color:var(--gold);word-break:break-word">'+esc(path)+'</div>'+
      '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:6px">'+purpose+'</div>'+
    '</div>';
  }
  var h2hRows = firstDefined(learningCoverage.h2hPairs, db.headToHeadRows, db.head_to_head_rows, db.totalHeadToHeadRows, dataCoverage.headToHeadRows, '');
  var runnerLoaded = firstDefined(dataCoverage.runnersLoaded, dataCoverage.runnerCount, '');
  var runnerMatched = firstDefined(dataCoverage.runnersMatched, dataCoverage.matchedRunners, '');
  document.getElementById('panel-systemmap').innerHTML =
    '<style>'+
      '#panel-systemmap .system-balanced-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:stretch}'+
      '#panel-systemmap .system-balanced-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;align-items:stretch}'+
      '@media(max-width:980px){#panel-systemmap .system-balanced-3{grid-template-columns:repeat(2,minmax(0,1fr))}}'+
      '@media(max-width:680px){#panel-systemmap .system-balanced-2,#panel-systemmap .system-balanced-3{grid-template-columns:1fr}}'+
    '</style>'+
    '<div class="section-hero system"><div><div class="hero-kicker">Private system map</div><div class="section-hero-title">How Signal 75 Works</div>'+
    '<div class="section-hero-copy">A visual map of the live betting process, the learning layers, where data is stored, what backs up to iCloud, and which scripts run through the day.</div></div>'+
    '<div class="hero-stat">'+scoreChip(perf.bettingDays || 0, 'BET DAYS', 'var(--green)')+'</div></div>'+

    '<div class="card" style="padding:18px 20px;margin-bottom:18px;border-color:rgba(34,197,94,.32);background:linear-gradient(135deg,rgba(34,197,94,.08),rgba(255,255,255,.025))">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--green);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">Plain English</div>'+
      '<div style="font-size:18px;font-weight:850;line-height:1.55;color:var(--text);margin-top:5px">Signal 75 is a controlled pipeline: collect race data, score runners, block weak cases, choose 1-3 official picks, settle the result, update proof, then store learning evidence for future review.</div>'+
      '<div style="font-size:13px;line-height:1.75;color:var(--muted);margin-top:8px">The dashboard is read-only. Challenger Lab, V1 and warnings do not change official proof until John explicitly promotes a rule.</div>'+
    '</div>'+

    '<div class="section-block-h"><h2>Main flow</h2><span class="n">morning to proof</span></div>'+
    '<div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px">'+
      flowStep(1, 'Collect today', 'Betfair runners/prices, racecards, tipster feeds, stored form history, rival memory, class/setup evidence and weather context.', 'var(--blue)')+
      flowStep(2, 'Score runners', 'Price, tips, race fit and form produce the visible score. Then penalties/warnings are attached for bad form, class/setup gaps, large fields and unsafe race types.', 'var(--gold)')+
      flowStep(3, 'Apply gates', 'Official picks must pass price band, score gate, field-size rules, race-type exclusions, same-race duplicate checks and quality audit checks.', 'var(--green)')+
      flowStep(4, 'Settle and learn', 'After racing, returns are calculated, proof/ROI updates, who beat us is recorded, H2H memory grows, challengers settle and the dashboard refreshes.', 'var(--red)')+
    '</div>'+

    '<div class="card" style="padding:18px 20px;margin-bottom:18px">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.12em;text-transform:uppercase;margin-bottom:12px">Pipeline drawing</div>'+
      '<div class="system-balanced-2">'+
        flowStep('A','Inputs','Betfair exchange morning price<br>Racecard runners<br>Tipster sources<br>Rich form archive<br>Head-to-head memory','rgba(56,189,248,.9)')+
        flowStep('B','Official engine','<strong>generate-picks-betfair.py</strong><br>Scores every runner<br>Blocks unsafe races<br>Writes picks.json and race_comparison_DATE.json','rgba(240,192,64,.95)')+
        flowStep('C','Dashboard layers','Official picks<br>Watchlist<br>V1 field analysis<br>Challenger Lab<br>Race Review','rgba(34,197,94,.95)')+
        flowStep('D','Post-race learning','Official settlement<br>Proof ROI guard<br>Race memory<br>H2H records<br>Rich form sync<br>iCloud mirror','rgba(255,77,109,.95)')+
      '</div>'+
    '</div>'+

    '<div class="grid grid-3" style="margin-bottom:18px">'+
      miniCard('Live gates', [
        '<strong>Price band:</strong> official each-way value band is 4.1-6.0 unless John promotes a wider challenger.',
        '<strong>Score gate:</strong> live picks need the official score threshold, then quality audit checks can block publication.',
        '<strong>Race exclusions:</strong> Arabian races, identical-score races, unsuitable field sizes and duplicate same-race picks are blocked.',
        '<strong>Class/setup caution:</strong> Group/Listed or class-up horses with no stored same-level/course/trip/going proof are highlighted before trust.'
      ], 'var(--green)')+
      miniCard('Learning only', [
        '<strong>Challenger Lab:</strong> paper tests such as class setup caution, short-price safety, price source review, Lucky 15, field graph and form penalties.',
        '<strong>V1 field analysis:</strong> compares field-relative scores and H2H evidence against official Signal 75 without changing the official bet.',
        '<strong>Race Review:</strong> after racing, shows who beat us, warnings visible before racing, and rejected danger horses.',
        '<strong>No promotion rule:</strong> no single signal goes live without the combined guardrail: form + class + H2H + distance + going + weight + draw + jockey/trainer.'
      ], 'var(--blue)')+
      miniCard('Proof and safety', [
        '<strong>Official proof:</strong> only Signal 75 official picks count in public ROI. Watchlist and challengers do not.',
        '<strong>Accountancy:</strong> result files, proof checks and ROI guard verify stake, return, profit and settlement basis.',
        '<strong>Integrity:</strong> pre-pick and post-race checks watch stale data, invalid JSON, missing results and broken challenger settlement.',
        '<strong>API cost:</strong> Anthropic AI punter is removed/disabled. Normal operation should not rely on paid AI calls.'
      ], 'var(--gold)')+
    '</div>'+

    '<div class="section-block-h"><h2>SQLite summary brain</h2><span class="n">fast dashboard layer</span></div>'+
    '<div class="grid grid-3" style="margin-bottom:18px">'+
      miniCard('Stored knowledge', [
        '<strong>Horses profiled:</strong> '+esc(learningCoverage.horsesProfiled || 0),
        '<strong>Head-to-head pairs:</strong> '+esc(learningCoverage.h2hPairs || 0),
        '<strong>Form patterns:</strong> '+esc(learningCoverage.formPatterns || 0),
        '<strong>Course/distance buckets:</strong> '+esc(learningCoverage.courseDistanceBuckets || 0)
      ], 'var(--green)')+
      miniCard('Used for dashboard', [
        '<strong>Race Review days:</strong> '+esc(learningCoverage.raceReviewDays || 0),
        '<strong>Challengers tracked:</strong> '+esc(learningCoverage.challengersTracked || 0),
        '<strong>Class movement buckets:</strong> '+esc(learningCoverage.classBuckets || 0),
        '<strong>Last built:</strong> '+esc(((sqliteIntel.summaryStatus || {}).asOfDate) || 'not exported yet')
      ], 'var(--blue)')+
      miniCard('Why this matters', [
        'The browser reads this compact summary instead of scanning thousands of race files.',
        'It makes Race Review, Challenger Lab and How It Works faster and easier to audit.',
        'It is display-only: it cannot change official picks, scoring, proof or ROI.',
        'Integrity checks now warn if this summary layer is missing or stale.'
      ], 'var(--gold)')+
    '</div>'+

    '<div class="section-block-h"><h2>Daily automation</h2><span class="n">actual Mac schedule</span></div>'+
    '<div class="card" style="padding:18px 20px;margin-bottom:18px">'+
      scriptRow('09:00','Morning resolver','/Users/johnhowlett/signal75-run-resolve.sh','Cleans/repairs morning state where possible and runs proof consistency checks.', 'var(--blue)')+
      scriptRow('10:00','Morning picks','/Users/johnhowlett/signal75-run-picks.sh','Runs config checks, tests, official pick generation, rich data verification, diagnostics, quality audit, field graph, Challenger Lab, dashboard publish and public pick push.', 'var(--green)')+
      scriptRow('10:20 / 10:50','Picks watchdog','/Users/johnhowlett/signal75-run-picks-watchdog.sh','Checks that picks actually generated. Used as a safety net if the morning run failed or the Mac restarted.', 'var(--gold)')+
      scriptRow('11:30 / 13:30 / 15:30','Late market watch','/Users/johnhowlett/signal75-run-late-market.sh','Checks late market movement and value changes. Learning/dashboard context only unless already wired into a live gate.', 'var(--blue)')+
      scriptRow('Every 15 min','Early results refresh','/Users/johnhowlett/signal75-run-early-results.sh','Polls for early result availability so the dashboard can move from pending to settled sooner.', 'var(--gold)')+
      scriptRow('19:00 / 20:30 / 21:30 / 22:15','Evening results','/Users/johnhowlett/signal75-run-results.sh','Settles official results, recalculates performance, runs proof consistency, builds race memory, H2H, rival intelligence, rich form sync, challenger settlement and dashboard export.', 'var(--red)')+
      scriptRow('23:10','Self learning','/Users/johnhowlett/signal75-run-self-learning.sh','Runs the nightly learning stack and publishes local dashboard reports. Does not change official historical proof.', 'var(--blue)')+
      scriptRow('10:45 / 23:45','iCloud mirror','/Users/johnhowlett/.signal75-tools/backup_signal75_to_icloud.sh','Copies the live repo and engine folder to iCloud mirror folders with secrets/cache/git excluded.', 'var(--green)')+
      scriptRow('Always on','Private dashboard','/Users/johnhowlett/signal75-run-dashboard.sh','Runs the local read-only dashboard at 127.0.0.1:8750. It is not the public customer site.', 'var(--green)')+
    '</div>'+

    '<div class="section-block-h"><h2>Data stores</h2><span class="n">where knowledge lives</span></div>'+
    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:12px;margin-bottom:18px">'+
      storeRow('Official picks', 'picks.json', 'Today’s official selections, stake model and public-facing pick data.')+
      storeRow('Daily proof files', 'data/YYYY-MM-DD.json', 'Settled official result, per-horse result, stake, return, profit and settlement basis.')+
      storeRow('Performance proof', 'performance.json', 'All-time ROI, betting days, profit, stake and place/win rates used by public results.')+
      storeRow('Race comparison feed', 'data/race_comparison_YYYY-MM-DD.json', 'Every runner scored before racing: prices, form, tipsters, warnings, race info and source labels.')+
      storeRow('H2H memory', 'data/horse_intelligence/signal75_history.sqlite', 'Horse-vs-horse memory: who beat who, date, course and rival relationships used by field evidence.')+
      storeRow('Rich form archive', 'data/horse_intelligence/form_history.sqlite', 'Large historical form/race data store: class, going, distance, runners, SP/BSP context where available.')+
      storeRow('Race memory JSONL', 'data/horse_intelligence/*_master.jsonl', 'Append-style learning records for horse history, race memory and rival profiles.')+
      storeRow('Challenger Lab', 'data/challenger_lab/*.json', 'Paper-only daily challenger picks and settled comparison versus live Signal 75.')+
      storeRow('Dashboard feed', 'dashboard/data/*.json', 'Small local JSON files read by this private dashboard. These are display feeds, not the proof source.')+
      storeRow('iCloud mirror', '/Users/johnhowlett/Documents/Projects/Signal75/Live_Signal75_Mirror', 'Backup copy made by rsync. It excludes .git, caches, virtual envs, secrets and token/cookie files.')+
    '</div>'+

    '<div class="section-block-h"><h2>What happens after a race</h2><span class="n">learning loop</span></div>'+
    '<div class="card" style="padding:18px 20px;margin-bottom:18px">'+
      '<div class="system-balanced-3">'+
        flowStep('1','Settle official pick','Position, placed/lost/won status, BSP/locked price and return are written into data/YYYY-MM-DD.json.', 'var(--green)')+
        flowStep('2','Check accountancy','Proof consistency and ROI guard compare total stake, total return, profit and public performance output.', 'var(--gold)')+
        flowStep('3','Record who beat us','Race Review stores winner, official pick finish position, rejected dangers and any pre-race rival warning visible before the race.', 'var(--blue)')+
        flowStep('4','Grow memory','Race memory, H2H memory, field relationships and rich form sync update learning stores for future days.', 'var(--green)')+
        flowStep('5','Settle challengers','Paper tests are settled independently so we can see what would have worked without changing proof.', 'var(--red)')+
        flowStep('6','Publish dashboard','Local dashboard feeds refresh last, so the private view shows the latest proof and learning state.', 'var(--blue)')+
      '</div>'+
    '</div>'+

    '<div class="grid grid-2" style="margin-bottom:18px">'+
      miniCard('Current live facts', [
        '<strong>Official betting days:</strong> '+esc(perf.bettingDays || 0),
        '<strong>Official ROI:</strong> '+esc(perf.roi || 0)+'%',
        '<strong>Runner matching:</strong> '+esc(runnerMatched || 0)+' of '+esc(runnerLoaded || 0),
        '<strong>H2H rows:</strong> '+esc(h2hRows || 'stored in SQLite/dashboard feed')
      ], 'var(--green)')+
      miniCard('Recovery notes', [
        '<strong>Main repo:</strong> /Users/johnhowlett/Signal75',
        '<strong>Logs:</strong> /Users/johnhowlett/signal75-*.log and /Users/johnhowlett/Signal75/logs/',
        '<strong>LaunchAgents:</strong> /Users/johnhowlett/Library/LaunchAgents/co.signal75.*.plist',
        '<strong>API keys:</strong> stored in macOS Keychain where still needed; do not put secrets in Git or iCloud.'
      ], 'var(--gold)')+
    '</div>'+

    '<div class="card" style="padding:18px 20px;border-color:rgba(255,77,109,.28);background:linear-gradient(135deg,rgba(255,77,109,.08),rgba(255,255,255,.02))">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--red);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">Go-live guardrail</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--muted);margin-top:6px">Before any dashboard or Challenger Lab idea becomes live scoring, review <span style="font-family:var(--mono);color:var(--gold)">/Users/johnhowlett/Signal75/docs/go-live-intelligence-guardrails.md</span>. A single signal is never enough. Check form, class movement, H2H, distance, going, weight, draw, jockey and trainer evidence together.</div>'+
    '</div>';
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
        '<div class="metric-tile"><div class="label">ROI</div><div class="value" style="color:var(--green)">'+esc(perf.roi || 0)+'%</div><div class="hint">'+fmtGBP(perf.totalProfit || 0)+' from '+esc(perf.bettingDays || 0)+' official betting days</div></div>'+
      '</div>'+
    '</div>'+
    '<div class="grid grid-3">'+
      '<div class="chart-card"><div class="chart-title">Today at a glance</div>'+
        visualBar('Official selections', official.length, 3, 'var(--green)')+
        visualBar('Watchlist', watchlist.length, Math.max(3, watchlist.length), 'var(--blue)')+
        visualBar('Tipster matches', cover.tipsterMatched || 0, Math.max(1, cover.runnersLoaded || 1), 'var(--gold)')+
      '</div>'+
      '<div class="chart-card"><div class="chart-title">Official record</div>'+
        '<div class="donut-wrap">'+donut([{value:Number(perf.profitableDays || 0), color:'var(--green)'},{value:Math.max(0, Number(perf.bettingDays || 0)-Number(perf.profitableDays || 0)), color:'var(--red)'}], 112)+
        '<div class="donut-legend"><div class="li"><span class="sw" style="background:var(--green)"></span>Betting days that made money</div><div class="li"><span class="sw" style="background:var(--red)"></span>Betting days that did not</div><div class="li">'+esc(perf.profitableDays || 0)+' profitable from '+esc(perf.bettingDays || 0)+' official betting days</div><div class="li" style="color:var(--muted2);line-height:1.55">'+esc(proofDayContext(perf))+'</div></div></div>'+
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
  var weatherWarning = pick('weatherWarning') || {};
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
    if(parts.os !== undefined || parts.ts !== undefined || parts.fs !== undefined || parts.fm !== undefined){
      return [
        {label:'PRICE', value:Number(parts.os || 0), color:'var(--blue)'},
        {label:'TIPS', value:Number(parts.ts || 0), color:'var(--gold)'},
        {label:'RACE', value:Number(parts.fs || 0), color:'var(--green)'},
        {label:'FORM', value:Number(parts.fm || 0), color:'var(--green)'}
      ];
    }
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
  function raceForPick(p){
    var data = pick('raceView') || {};
    var courseKey = normaliseNameLocal(p.course);
    var timeKey = String(p.time || '');
    var races = data.races || [];
    for(var i=0;i<races.length;i++){
      var race = races[i] || {};
      if(normaliseNameLocal(race.course) === courseKey && String(race.time || '') === timeKey) return race;
    }
    return null;
  }
  function fieldGraphForPick(p){
    var graph = pick('fieldGraph') || {};
    var target = normaliseNameLocal(p.name);
    var rows = graph.currentRunners || [];
    for(var i=0;i<rows.length;i++){
      var row = rows[i] || {};
      if(normaliseNameLocal(row.horse_name || row.horse) === target) return row;
    }
    return null;
  }
  function richFormForPick(p){
    var feed = pick('richForm') || {};
    var target = normaliseNameLocal(p.name)+'|'+normaliseNameLocal(p.course)+'|'+String(p.time || '');
    var fallback = null;
    var rows = feed.rows || [];
    for(var i=0;i<rows.length;i++){
      var row = rows[i] || {};
      var key = normaliseNameLocal(row.name)+'|'+normaliseNameLocal(row.course)+'|'+String(row.time || '');
      if(key === target) return row;
      if(!fallback && normaliseNameLocal(row.name) === normaliseNameLocal(p.name)) fallback = row;
    }
    return fallback;
  }
  function richFormBlock(p){
    var row = richFormForPick(p);
    if(!row || (!row.patternStats && !row.latestArchiveRun)) return '';
    var stat = row.patternStats || {};
    var latest = row.latestArchiveRun || null;
    var tone = String(stat.tone || 'neutral');
    var color = tone === 'good' ? 'var(--green)' : (tone === 'poor' ? 'var(--gold)' : 'var(--blue)');
    var bg = tone === 'good' ? 'rgba(0,232,122,.06)' : (tone === 'poor' ? 'rgba(240,192,64,.08)' : 'rgba(56,189,248,.06)');
    var latestLine = '';
    if(latest){
      var bits = [];
      if(latest.date) bits.push(latest.date);
      if(latest.course) bits.push(latest.course);
      if(latest.distance) bits.push(latest.distance);
      if(latest.going) bits.push(latest.going);
      var finish = latest.position ? 'finished '+latest.position+(latest.runners ? ' of '+latest.runners : '') : '';
      if(finish) bits.push(finish);
      latestLine = '<div style="font-size:13px;line-height:1.65;color:var(--muted2);margin-top:6px">Latest archive run: '+esc(bits.join(' · '))+
        (latest.rpr ? ' · RPR '+esc(latest.rpr) : '')+
        (latest.topspeed ? ' · TS '+esc(latest.topspeed) : '')+
        (latest.officialRating ? ' · OR '+esc(latest.officialRating) : '')+
      '</div>';
    }
    return '<div style="padding:14px 16px;background:'+bg+';border-top:1px solid rgba(255,255,255,.08);border-left:3px solid '+color+'">'+
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">'+
        '<div style="font-weight:850;font-size:15px;line-height:1.4;color:var(--text)">Similar form record</div>'+
        (stat.label ? '<span style="font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:'+color+'">'+esc(stat.label)+'</span>' : '')+
      '</div>'+
      (stat.plainEnglish ? '<div style="font-size:14px;line-height:1.7;color:var(--muted);margin-top:6px">'+esc(stat.plainEnglish)+'</div>' : '')+
      latestLine+
      '<div style="font-family:var(--mono);font-size:10px;line-height:1.6;color:var(--muted2);margin-top:8px">12-year form archive · dashboard evidence only · no scoring impact</div>'+
    '</div>';
  }
  function richContextForPick(p, run){
    run = run || runnerForPick(p) || {};
    return run.richContext || p.richContext || {};
  }
  function richSetupBlock(p, run){
    var ctx = richContextForPick(p, run);
    if(!ctx || !Object.keys(ctx).length) return '';
    var latest = ctx.latestArchiveRun || {};
    var chips = [];
    if(ctx.raceClass) chips.push('Class: '+ctx.raceClass);
    if(ctx.classMovement) chips.push('Class movement: '+ctx.classMovement);
    if(ctx.distance) chips.push('Trip: '+ctx.distance);
    if(ctx.going) chips.push('Going: '+ctx.going);
    if(ctx.weightLbs) chips.push('Weight: '+ctx.weightLbs+' lb');
    if(ctx.draw) chips.push('Draw: '+ctx.draw);
    if(ctx.jockey) chips.push('Jockey: '+ctx.jockey);
    if(ctx.trainer) chips.push('Trainer: '+ctx.trainer);
    var latestBits = [];
    if(latest.date) latestBits.push(latest.date);
    if(latest.course) latestBits.push(latest.course);
    if(latest.distance) latestBits.push(latest.distance);
    if(latest.going) latestBits.push(latest.going);
    if(latest.race_class) latestBits.push('class '+latest.race_class);
    if(latest.position) latestBits.push('finished '+latest.position+(latest.runners ? ' of '+latest.runners : ''));
    var notes = asArray(ctx.notes).slice(0,4);
    var noteHtml = notes.length
      ? notes.map(function(note){ return '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:5px">• '+esc(note)+'</div>'; }).join('')
      : '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:5px">No strong setup change stored yet. Missing fields are shown as unavailable rather than guessed.</div>';
    return '<div style="padding:14px 16px;background:rgba(56,189,248,.055);border-top:1px solid rgba(255,255,255,.08);border-left:3px solid var(--blue)">'+
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">'+
        '<div style="font-weight:850;font-size:15px;line-height:1.4;color:var(--text)">Setup context</div>'+
        '<span style="font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue)">rich archive</span>'+
      '</div>'+
      '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:8px">'+chips.slice(0,8).map(function(chip){ return pill(chip, 'grey'); }).join('')+'</div>'+
      (latestBits.length ? '<div style="font-size:13px;line-height:1.65;color:var(--muted2);margin-top:8px">Latest stored run: '+esc(latestBits.join(' · '))+'</div>' : '')+
      noteHtml+
      '<div style="font-family:var(--mono);font-size:10px;line-height:1.6;color:var(--muted2);margin-top:8px">Dashboard evidence only · no live scoring or proof impact</div>'+
    '</div>';
  }
  function marketRankForRival(p, rivalName){
    var race = raceForPick(p);
    if(!race) return null;
    var target = normaliseNameLocal(rivalName);
    var priced = (race.runners || []).filter(function(r){ return r && r.odds != null && Number(r.odds) > 0; })
      .sort(function(a,b){ return Number(a.odds) - Number(b.odds); });
    for(var i=0;i<priced.length;i++){
      if(normaliseNameLocal(priced[i].name) === target){
        return {rank:i+1, odds:priced[i].odds, topThree:i < 3};
      }
    }
    return null;
  }
  function rankText(rank){
    if(!rank) return 'Rival in today\'s race';
    if(rank.rank === 1) return 'Favourite today';
    if(rank.rank === 2) return '2nd favourite today';
    if(rank.rank === 3) return '3rd favourite today';
    return 'Market rank '+rank.rank+' today';
  }
  function bar(width, color){
    return '<span style="display:inline-block;width:82px;height:10px;border-radius:999px;background:rgba(255,255,255,.08);overflow:hidden;border:1px solid rgba(255,255,255,.08);vertical-align:middle;margin-right:8px">'+
      '<span style="display:block;width:'+clamp(width,12,100)+'%;height:100%;background:'+color+'"></span></span>';
  }
  function splitRivals(text){
    return String(text || '').split(',').map(function(v){ return v.trim(); }).filter(Boolean);
  }
  function rivalEvidenceBlock(p){
    var graph = fieldGraphForPick(p);
    if(graph){
      function edgeContext(edge){
        var bits = [];
        var margin = Number(edge.max_margin || 0);
        if(margin >= 5) bits.push('clear previous beating by '+margin.toFixed(margin % 1 ? 1 : 0)+' lengths');
        else if(margin >= 3) bits.push('won that match-up by '+margin.toFixed(margin % 1 ? 1 : 0)+' lengths');
        var setup = edge.setup || {};
        var matches = setup.matches || [];
        if(matches.length){
          bits.push('similar setup: '+matches.slice(0,3).join(', '));
        }
        return bits.length ? ' '+bits.join('. ')+'.' : '';
      }
      var graphRows = [];
      var negativeEdges = (graph.negative_edges || []).slice().sort(function(a,b){
        return Number(b.points || 0) - Number(a.points || 0);
      });
      var directEdges = (graph.direct_edges || []).slice().sort(function(a,b){
        return Number(b.points || 0) - Number(a.points || 0);
      });
      negativeEdges.slice(0,4).forEach(function(edge){
        var rank = marketRankForRival(p, edge.rival);
        var meetings = Number(edge.meetings || 1);
        graphRows.push({
          kind:'warn',
          name:edge.rival,
          detail:'This rival has beaten '+esc(p.name)+' '+meetings+' time'+(meetings === 1 ? '' : 's')+' before. '+rankText(rank)+'.'+edgeContext(edge),
          points:Number(edge.points || 0),
          meetings:meetings,
          rank:rank
        });
      });
      directEdges.slice(0,4).forEach(function(edge){
        var rank = marketRankForRival(p, edge.rival);
        var meetings = Number(edge.meetings || 1);
        graphRows.push({
          kind:'good',
          name:edge.rival,
          detail:'Beaten '+meetings+' time'+(meetings === 1 ? '' : 's')+' before. '+rankText(rank)+'.'+edgeContext(edge),
          points:Number(edge.points || 0),
          rank:rank
        });
      });
      (graph.indirect_edges || []).slice(0,2).forEach(function(edge){
        var rank = marketRankForRival(p, edge.rival);
        graphRows.push({
          kind:'chain',
          name:edge.rival,
          detail:'Linked form line via '+esc(edge.via || 'another runner')+'. '+rankText(rank)+'.',
          points:Number(edge.points || 0),
          rank:rank
        });
      });
      if(graphRows.length){
        var threatHtml = '';
        if(negativeEdges.length){
          var strongestThreats = negativeEdges.slice(0,3).map(function(edge){
            var meetings = Number(edge.meetings || 1);
            return '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:5px">'+
              '<span style="font-weight:850;color:var(--text)">'+esc(edge.rival)+'</span> beat '+esc(p.name)+' '+meetings+' time'+(meetings === 1 ? '' : 's')+' before'+esc(edgeContext(edge))+'</div>';
          }).join('');
          var hasHighThreat = negativeEdges.some(function(edge){
            return Number(edge.meetings || 0) >= 2 || Number(edge.points || 0) >= 14;
          });
          threatHtml = '<div style="margin-bottom:13px;padding:12px 14px;border-left:3px solid '+(hasHighThreat ? 'var(--red)' : 'var(--gold)')+';background:'+(hasHighThreat ? 'rgba(255,77,109,.08)' : 'rgba(240,192,64,.10)')+';border-radius:0 var(--r-sm) var(--r-sm) 0">'+
            '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:'+(hasHighThreat ? 'var(--red)' : 'var(--gold)')+';line-height:1.6">'+(hasHighThreat ? 'High rival threat' : 'Rival threat')+'</div>'+
            '<div style="font-size:14px;line-height:1.65;color:var(--text);font-weight:850;margin-top:4px">Today&apos;s field includes '+negativeEdges.length+' rival'+(negativeEdges.length === 1 ? '' : 's')+' with past wins over '+esc(p.name)+'.</div>'+
            strongestThreats+
            '<div style="font-family:var(--mono);font-size:10px;line-height:1.6;color:var(--muted2);margin-top:8px">Dashboard warning only · does not change live score</div>'+
          '</div>';
        }
        var html = graphRows.map(function(row, idx){
          var color = row.kind === 'good' ? 'rgba(0,232,122,.58)' : (row.kind === 'warn' ? 'rgba(255,77,109,.62)' : 'rgba(56,189,248,.54)');
          var textColor = row.kind === 'good' ? 'var(--green)' : (row.kind === 'warn' ? 'var(--red)' : 'var(--blue)');
          var label = row.kind === 'good' ? 'BEATEN BEFORE' : (row.kind === 'warn' ? 'BEAT US BEFORE' : 'FORM LINE');
          var width = row.kind === 'good' ? Math.min(100, 42 + row.points * 5) : (row.kind === 'warn' ? Math.min(100, 38 + row.points * 4) : 48);
          return '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:'+(idx ? '10' : '0')+'px">'+
            '<div style="min-width:0">'+
              '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">'+
                '<div style="font-weight:850;font-size:14px;line-height:1.35;color:var(--text)">'+esc(row.name)+'</div>'+
                (row.rank && row.rank.topThree ? '<span style="font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:.08em;text-transform:uppercase">TOP 3 MARKET</span>' : '')+
              '</div>'+
              '<div style="font-size:12px;line-height:1.6;color:var(--muted2)">'+row.detail+'</div>'+
            '</div>'+
            '<div style="display:flex;align-items:center;gap:4px;white-space:nowrap">'+bar(width,color)+'<span style="font-family:var(--mono);font-weight:800;color:'+textColor+';font-size:11px">'+label+'</span></div>'+
          '</div>';
        }).join('');
        return '<div style="padding:14px 16px;background:rgba(255,255,255,.035);border-top:1px solid rgba(255,255,255,.08)">'+
          '<div style="font-weight:850;font-size:15px;line-height:1.4;color:var(--text);margin-bottom:10px">Race memory against today&apos;s field</div>'+
          threatHtml+
          html+
        '</div>';
      }
      return '';
    }
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
      return '';
    }
    return '<div style="padding:14px 16px;background:rgba(255,255,255,.035);border-top:1px solid rgba(255,255,255,.08)">'+
      '<div style="display:flex;gap:10px;align-items:flex-start">'+
        '<div style="color:var(--gold);font-size:18px;line-height:1">✦</div>'+
        '<div style="min-width:0;flex:1"><div style="font-weight:850;font-size:15px;line-height:1.4;color:var(--text)">Our special race memory</div>'+
        '<div style="font-size:13px;line-height:1.6;color:var(--muted)">Signal 75 checked whether this horse has beaten rivals in today&apos;s race before.</div>'+
        rows+warningHtml+'</div></div></div>';
  }
  function postRaceReviewForPick(p){
    var feed = pick('postRaceReview') || {};
    var rows = feed.picks || [];
    var target = normaliseNameLocal(p.name)+'|'+normaliseNameLocal(p.course)+'|'+String(p.time || '');
    for(var i=0;i<rows.length;i++){
      var row = rows[i] || {};
      var rowKey = normaliseNameLocal(row.name)+'|'+normaliseNameLocal(row.course)+'|'+String(row.time || '');
      if(rowKey === target) return row;
    }
    for(var j=0;j<rows.length;j++){
      var fallback = rows[j] || {};
      if(normaliseNameLocal(fallback.name) === normaliseNameLocal(p.name)) return fallback;
    }
    return null;
  }
  function postRaceReviewBlock(p){
    var row = postRaceReviewForPick(p);
    if(!row || !row.result || String(row.result).toUpperCase() === 'PENDING') return '';
    var result = String(row.result || '').toUpperCase();
    var won = result === 'WON';
    var placed = result === 'PLACED';
    var border = won ? 'var(--green)' : (placed ? 'var(--gold)' : 'var(--red)');
    var resultLine = won ? 'Our pick won.' : (placed ? 'Our pick placed '+esc(row.position || '')+'.' : 'Our pick finished '+esc(row.position || row.result)+'.');
    var winnerLine = row.winnerKnown && row.winner
      ? 'Winner: '+esc(row.winner)
      : 'Winner name is not in the compact dashboard feed yet.';
    var warningRows = (row.warningEdges || []).slice(0,3).map(function(edge){
      return '<div style="font-size:13px;line-height:1.65;color:var(--muted2);margin-top:6px">Before the race: '+esc(edge.text || '')+'</div>';
    }).join('');
    return '<div style="padding:13px 16px;background:rgba(255,255,255,.04);border-top:1px solid rgba(255,255,255,.08);border-left:3px solid '+border+'">'+
      '<div style="font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:'+border+';line-height:1.6">Post-race check</div>'+
      '<div style="font-size:14px;line-height:1.65;color:var(--text);font-weight:800;margin-top:4px">'+resultLine+'</div>'+
      '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:4px">'+winnerLine+'</div>'+
      '<div style="font-size:13px;line-height:1.65;color:var(--muted);margin-top:4px">'+esc(row.relationshipSummary || 'Race-memory relationship stored for review.')+'</div>'+
      warningRows+
      '<div style="font-family:var(--mono);font-size:10px;line-height:1.6;color:var(--muted2);margin-top:8px">Learning display only · no scoring or proof impact</div>'+
    '</div>';
  }
  function confidenceTier(p, run){
    var score = Number(p.score || p.signal_score || 0);
    var tips = Number(p.tipsters || (run.consensus || {}).source_count || 0);
    var risks = topRisks(p, run);
    var raceType = String(p.raceType || p.section || run.race_type || '').toLowerCase();
    var flatNoTipster = raceType !== 'jumps' && tips === 0;
    if(flatNoTipster && score >= 75) return {label:'MODERATE', color:'var(--gold)', bg:'rgba(240,192,64,.10)'};
    if(score >= 95 && tips >= 4 && !risks.length) return {label:'STRONG', color:'var(--green)', bg:'rgba(0,232,122,.10)'};
    if(score >= 85 && tips >= 2 && risks.length <= 1) return {label:'SOLID', color:'var(--blue)', bg:'rgba(56,189,248,.10)'};
    if(score >= 75) return {label:'MODERATE', color:'var(--gold)', bg:'rgba(240,192,64,.10)'};
    if(score >= 70 || risks.length) return {label:'WEAK', color:'var(--muted2)', bg:'rgba(148,163,184,.08)'};
    return {label:'LOW', color:'var(--muted2)', bg:'rgba(148,163,184,.06)'};
  }
  function topReasons(p, run){
    run = run || {};
    var tips = Number(p.tipsters || (run.consensus || {}).source_count || 0);
    var score = Number(p.score || p.signal_score || 0);
    var reasons = [];
    if(tips >= 6) reasons.push(tips+' professional tipsters');
    else if(tips >= 3) reasons.push(tips+' tipsters backing this horse');
    else if(tips > 0) reasons.push(tips+' tipster'+(tips === 1 ? '' : 's'));
    var overlay = run.rivalMemoryOverlay || p.rivalMemoryOverlay || {};
    if(overlay && Number(overlay.points || overlay.overlay_points || 0) > 0) reasons.push("Positive rival memory in today's field");
    var consensus = run.consensus || p.consensus || {};
    var level = String(consensus.consensus_level || p.consensusLevel || '').toLowerCase();
    if(level === 'strong' || level === 'useful') reasons.push(level === 'strong' ? 'Strong tipster consensus' : 'Useful tipster consensus');
    if(!(p.warnings || []).length && !run.formWarning && !p.formWarning) reasons.push('Clean recent form');
    if(score >= 100) reasons.push('Score 100 — maximum signal');
    else if(score >= 95) reasons.push('Elite score '+score);
    var ctx = richContextForPick(p, run);
    if(ctx.classMovement === 'down') reasons.push('Dropping in class from latest stored run');
    if(asArray(ctx.notes).some(function(note){ return String(note).toLowerCase().indexOf('same trip') >= 0; })) reasons.push('Same trip as latest stored run');
    return reasons.filter(Boolean).slice(0,3);
  }
  function topRisks(p, run){
    run = run || {};
    var risks = [];
    var tips = Number(p.tipsters || (run.consensus || {}).source_count || 0);
    var raceType = String(p.raceType || p.section || run.race_type || '').toLowerCase();
    if(tips === 0 && raceType === 'jumps') risks.push('Tipster data not available for jumps racing');
    else if(tips === 0) risks.push('No flat tipster support');
    var warnings = (p.warnings || []).concat(run.warnings || []);
    if(run.formWarning) warnings.push(run.formWarning);
    if(p.formWarning) warnings.push(p.formWarning);
    asArray(run.scoreAdjustments || p.scoreAdjustments).forEach(function(adj){
      if(adj && adj.type === 'penalty' && adj.reason) warnings.push(adj.reason);
    });
    var warningText = warnings.join(' ').toLowerCase();
    if(
      warningText.indexOf('group') >= 0 ||
      warningText.indexOf('listed') >= 0 ||
      warningText.indexOf('same-level') >= 0 ||
      warningText.indexOf('class history missing') >= 0 ||
      warningText.indexOf('course/trip/going') >= 0
    ){
      risks.push('Class/setup caution: stronger race or missing same-setup proof');
    }
    warnings.filter(Boolean).slice(0,1).forEach(function(w){ risks.push(String(w)); });
    var race = raceForPick(p);
    if(race && Number(race.field_size || race.runners || 0) > 14) risks.push('Large field — harder to place');
    var overlay = run.rivalMemoryOverlay || p.rivalMemoryOverlay || {};
    if(overlay && Number(overlay.points || overlay.overlay_points || 0) < 0) risks.push('Rival memory warning');
    var setupGaps = [];
    if(Number(firstDefined(p.courseWins, run.courseWins, 0)) === 0) setupGaps.push('course');
    if(Number(firstDefined(p.goingRuns, run.goingRuns, 0)) === 0) setupGaps.push('going');
    if(Number(firstDefined(p.distanceWins, run.distanceWins, 0)) === 0) setupGaps.push('trip');
    if(setupGaps.length >= 2) risks.push('Stored setup proof incomplete: '+setupGaps.slice(0,3).join(', '));
    var ctx = richContextForPick(p, run);
    if(ctx.classMovement === 'up') risks.push('Rising in class from latest stored run');
    if(Number(ctx.weightChangeLbs || 0) >= 7) risks.push('Carries '+ctx.weightChangeLbs+' lb more than latest run');
    var seenRisks = {};
    return risks.filter(Boolean).filter(function(risk){
      var key = String(risk).toLowerCase();
      if(seenRisks[key]) return false;
      seenRisks[key] = true;
      return true;
    }).slice(0,2);
  }
  function tickRows(rows, kind){
    if(!rows.length) return '<div style="font-size:14px;line-height:1.7;color:var(--muted2)">None showing today.</div>';
    var mark = kind === 'risk' ? '⚠' : '✓';
    var color = kind === 'risk' ? 'var(--gold)' : 'var(--green)';
    return rows.map(function(row){
      return '<div style="display:flex;gap:9px;align-items:flex-start;font-size:14px;line-height:1.7;color:var(--text);margin-top:5px">'+
        '<span style="color:'+color+';font-weight:900">'+mark+'</span><span>'+esc(row)+'</span></div>';
    }).join('');
  }
  function tipsterSourceBlock(p, run){
    var consensus = run.consensus || p.consensus || {};
    var sources = consensus.sources || [];
    var tipsters = consensus.tipsters || [];
    var rows = [];
    sources.slice(0,8).forEach(function(src){ rows.push(String(src)); });
    tipsters.slice(0,8).forEach(function(src){ if(rows.indexOf(String(src)) < 0) rows.push(String(src)); });
    if(!rows.length) return '<div style="font-size:13px;line-height:1.7;color:var(--muted2)">No named tipster sources in the compact feed.</div>';
    return '<div style="display:flex;gap:8px;flex-wrap:wrap">'+rows.map(function(src){ return pill(src, 'grey'); }).join('')+'</div>';
  }
  function fullAnalysisBlock(p, run){
    var parts = p.parts || p.bd || p.score_parts || p.scoreParts || run.parts || run.bd || run.score_parts || run.scoreParts || {};
    return '<details style="border-top:1px solid rgba(255,255,255,.08);padding:0 16px 14px">'+
      '<summary style="cursor:pointer;font-family:var(--mono);font-size:12px;line-height:1.8;color:var(--blue);padding:12px 0;letter-spacing:.06em;text-transform:uppercase">Show full analysis ▶</summary>'+
      '<div style="display:grid;gap:12px">'+
        '<div><div class="chart-title">Score breakdown</div>'+waterfall(scoreRows(parts))+'</div>'+
        '<div><div class="chart-title">Tipster sources</div>'+tipsterSourceBlock(p, run)+'</div>'+
        rivalEvidenceBlock(p)+
        richSetupBlock(p, run)+
        richFormBlock(p)+
        postRaceReviewBlock(p)+
        qualityAuditBlock(p)+
      '</div>'+
    '</details>';
  }
  function officialCard(p){
    var run = runnerForPick(p);
    var tier = confidenceTier(p, run);
    var reasons = topReasons(p, run);
    var risks = topRisks(p, run);
    var model = officialBetModel(official.length);
    return '<div class="card" style="margin-bottom:14px;padding:0;overflow:hidden;border-color:'+tier.color+';background:rgba(255,255,255,.035)">'+
      '<div style="display:grid;grid-template-columns:minmax(128px,190px) 1fr;gap:0;align-items:stretch">'+
        '<div style="background:'+tier.bg+';border-right:1px solid rgba(255,255,255,.08);padding:18px 16px;display:flex;align-items:center;justify-content:center;text-align:center">'+
          '<div style="min-width:0;max-width:100%"><div style="font-family:var(--display);font-size:clamp(20px,2.2vw,28px);line-height:1;color:'+tier.color+';white-space:normal;overflow-wrap:anywhere">'+esc(tier.label)+'</div>'+
          '<div style="font-family:var(--mono);font-size:11px;line-height:1.6;color:var(--muted2);letter-spacing:.12em;text-transform:uppercase;margin-top:6px">confidence</div></div>'+
        '</div>'+
        '<div style="padding:18px 20px">'+
          '<div style="font-family:var(--display);font-size:34px;line-height:1.05;color:var(--text)">'+esc(p.name)+'</div>'+
          '<div style="font-size:14px;line-height:1.7;color:var(--muted2);margin-top:4px">'+raceContextHtml(p)+'</div>'+
          '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:14px">'+
            '<div><div style="font-size:15px;font-weight:850;color:var(--text);line-height:1.6">Back each-way at '+esc(p.odds)+'</div>'+
            '<div style="font-size:13px;line-height:1.7;color:var(--muted2);font-family:var(--mono)">'+esc(model.label)+' · £'+moneyText(model.stake)+' proof stake</div></div>'+
            '<div style="display:flex;gap:8px;flex-wrap:wrap">'+pill('Score '+esc(p.score),'blue')+pill(esc(p.tipsters || 0)+' tipsters','green')+'</div>'+
          '</div>'+
        '</div>'+
      '</div>'+
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;border-top:1px solid rgba(255,255,255,.08)">'+
        '<div style="padding:14px 16px;border-right:1px solid rgba(255,255,255,.08)"><div class="chart-title">Top reasons</div>'+tickRows(reasons, 'reason')+'</div>'+
        '<div style="padding:14px 16px"><div class="chart-title">Top risks</div>'+tickRows(risks, 'risk')+'</div>'+
      '</div>'+
      fullAnalysisBlock(p, run)+
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
      var rawTotal = active.reduce(function(sum, s){ return sum + rawBetStakeForKind(s.model.kind); }, 0);
      stake = 14;
      sub = active.map(function(s){
        var groupStake = proofStakeForGroup(rawBetStakeForKind(s.model.kind), rawTotal);
        return '£'+moneyText(groupStake)+' '+s.name;
      }).join(' + ');
      copy = active.map(function(s){
        return 'Place an '+s.model.label+' on the '+s.name+' pick'+(s.count === 1 ? '' : 's');
      }).join(' and ');
    } else if(total >= 3) {
      title = 'TODAY: FULL PATENT';
      copy = '3 picks · £14 · 14 lines';
    } else if(total === 2) {
      title = 'TODAY: EACH-WAY DOUBLE';
      copy = '2 picks · £14 proof stake · 6 lines';
    } else {
      title = 'TODAY: EACH-WAY SINGLE';
      copy = '1 pick · £14 proof stake · 2 lines';
    }
    return '<div class="card" style="border-color:rgba(240,192,64,.35);background:linear-gradient(135deg,rgba(240,192,64,.10),rgba(56,189,248,.06));padding:18px 20px;margin:0 0 18px">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">'+esc(title)+'</div>'+
      '<div style="font-size:18px;font-weight:850;color:var(--text);line-height:1.55;margin-top:4px">'+esc(copy)+'</div>'+
      '<div style="font-size:14px;color:var(--muted);line-height:1.7;margin-top:8px">Total outlay: £'+esc(stake)+' today'+(sub ? ' ('+esc(sub)+')' : '')+'.</div>'+
    '</div>';
  }
  function weatherWarningBlock(){
    if(!weatherWarning || !weatherWarning.active) return '';
    var courses = (weatherWarning.courses || []).join(', ');
    return '<div class="card" style="border-color:rgba(240,192,64,.55);background:linear-gradient(135deg,rgba(240,192,64,.14),rgba(255,77,109,.06));padding:16px 18px;margin:0 0 18px">'+
      '<div style="font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">Weather caution</div>'+
      '<div style="font-size:17px;font-weight:850;color:var(--text);line-height:1.55;margin-top:4px">'+esc(weatherWarning.message || 'Weather may affect today&apos;s races.')+'</div>'+
      (courses ? '<div style="font-size:14px;color:var(--muted);line-height:1.7;margin-top:6px">Courses: '+esc(courses)+'</div>' : '')+
      '<div style="font-family:var(--mono);font-size:10px;color:var(--muted2);line-height:1.6;margin-top:8px">Dashboard warning only · no scoring or proof impact</div>'+
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
        '<div><div style="font-weight:750;font-size:16px;line-height:1.4;color:var(--text)">'+esc(w.name)+'</div><div style="font-size:14px;line-height:1.7;color:var(--muted2)">'+raceContextHtml(w)+'</div></div>'+
        '<div>'+pill('Score '+esc(w.score || w.signal_score || 0),'blue')+'</div>'+
      '</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--muted);margin-top:10px">'+esc(watchReason(w))+'</div>'+
    '</div>';
  }
  function fieldRelativeDailyBlock(){
    var daily = pick('fieldRelativeDaily') || {};
    if(!daily.available && !daily.reason && !(daily.picks || []).length) return '';
    var picks = daily.picks || [];
    var unavailable = daily.available === false;
    var body = '';
    if(unavailable){
      body = '<div style="font-size:14px;line-height:1.8;color:var(--muted)">Field analysis daily selection is not available for this dashboard date yet. '+esc(daily.reason || '')+'</div>';
    } else if(!picks.length){
      body = '<div style="font-size:14px;line-height:1.8;color:var(--muted)">v1 found no analysis-only horses passing its daily comparison gates.</div>';
    } else {
      body = picks.map(function(p, idx){
        var reasons = (p.top_reasons || []).slice(0,3).map(function(reason){
          return '<div style="display:flex;gap:8px;align-items:flex-start;font-size:14px;line-height:1.7;color:var(--text);margin-top:5px"><span style="color:var(--green);font-weight:900">✓</span><span>'+esc(reason)+'</span></div>';
        }).join('');
        return '<div style="padding:14px 0;border-top:'+(idx ? '1px solid rgba(255,255,255,.08)' : '0')+'">'+
          '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap">'+
            '<div><div style="font-family:var(--display);font-size:28px;line-height:1.05;color:var(--text)">'+esc(p.horse)+'</div>'+
            '<div style="font-size:14px;line-height:1.7;color:var(--muted2)">'+raceContextHtml(p)+' · field score '+esc(p.field_score)+'</div></div>'+
            '<div style="display:flex;gap:8px;flex-wrap:wrap">'+pill(esc(p.odds)+' odds','gold')+pill(esc(p.h2h_beaten || 0)+' rivals beaten','green')+'</div>'+
          '</div>'+
          (reasons || '<div style="font-size:14px;line-height:1.7;color:var(--muted2);margin-top:8px">No short reason in the compact feed.</div>')+
        '</div>';
      }).join('');
    }
    return '<div class="section-block-h" style="margin-top:24px"><h2>Field analysis daily selection</h2><span class="n">v1 comparison only · not the official bet</span></div>'+
      '<div class="card" style="border-color:rgba(56,189,248,.35);background:linear-gradient(135deg,rgba(56,189,248,.08),rgba(255,255,255,.025));padding:18px 20px">'+
        '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;margin-bottom:10px">'+
          '<div><div style="font-family:var(--mono);font-size:11px;color:var(--blue);letter-spacing:.12em;text-transform:uppercase;line-height:1.6">analysis only — not live</div>'+
          '<div style="font-size:17px;font-weight:850;color:var(--text);line-height:1.55">'+esc(daily.bet_label || 'Field-relative daily selector')+'</div></div>'+
          '<div style="font-family:var(--mono);font-size:12px;line-height:1.7;color:var(--muted2)">'+esc(picks.length)+' pick'+(picks.length === 1 ? '' : 's')+' · £'+moneyText(daily.total_stake || 0)+' paper stake</div>'+
        '</div>'+
        body+
        '<div style="font-size:13px;line-height:1.7;color:var(--muted2);margin-top:10px">Compare after racing: Signal 75 official result versus this v1 field-analysis list.</div>'+
      '</div>';
  }
  function skinInGameTodayBlock(){
    return '';
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
    weatherWarningBlock()+
    '<div class="section-block-h"><h2>Official selections</h2><span class="n">passed every live rule</span></div>'+
    officialHtml+
    fieldRelativeDailyBlock()+
    skinInGameTodayBlock()+
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
  var headToHeadRowsLabel = sqliteHeadToHeadRowsLabel();
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
        '<div class="graph-meta">'+raceContextHtml(row)+'</div>'+
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
    var oldRows = changes.filter(function(r){ return num(r.old_points || r.oldPoints, 0) > 0 && firstDefined(r.actual_result, r.actualResult, 'pending') !== 'pending'; });
    var newRows = changes.filter(function(r){ return num(r.new_points || r.newPoints, 0) > 0 && firstDefined(r.actual_result, r.actualResult, 'pending') !== 'pending'; });
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
    var tabPlain = {
      overlay: {
        title:'Overlay Fix',
        purpose:'This is already live. It makes rival evidence fairer by only counting a past rival if that rival is actually running in today&apos;s race.',
        lookingFor:'We are checking whether this stops the system giving confidence for old history that is not relevant today.',
        plain:'Simple version: only count the horses in today&apos;s race.'
      },
      quality: {
        title:'Tipster Quality',
        purpose:'This tests whether one strong trusted source should count more than several weaker mentions.',
        lookingFor:'We are looking for proof that better-quality tipster support improves results without adding risky picks.',
        plain:'Simple version: not all tips are equal.'
      },
      history: {
        title:'Rival History',
        purpose:'This tests whether the stored horse-vs-horse memory helps when a horse has already beaten rivals it faces today.',
        lookingFor:'We are looking for repeatable evidence that past wins over today&apos;s field help more than normal scoring alone.',
        plain:'Simple version: has this horse beaten these rivals before?'
      },
      combined: {
        title:'Combined',
        purpose:'This tests the full package together: field-aware rival evidence plus the bigger history check.',
        lookingFor:'We are checking whether using both together beats the current live method over enough settled days.',
        plain:'Simple version: all the new intelligence working together, but still paper-only.'
      }
    };
    function simpleHelpCard(item){
      return '<div class="chart-card" style="padding:14px 16px">'+
        '<div style="font-family:var(--display);font-size:20px;line-height:1.2;color:var(--text)">'+esc(item.title)+'</div>'+
        '<div style="font-size:13px;line-height:1.7;color:var(--muted);margin-top:6px">'+item.purpose+'</div>'+
        '<div style="font-size:13px;line-height:1.7;color:var(--muted2);margin-top:8px"><strong style="color:var(--gold)">What we are looking for:</strong> '+item.lookingFor+'</div>'+
        '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--blue);margin-top:8px">'+item.plain+'</div>'+
      '</div>';
    }
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
        return 'This is the newer field-aware/full-history evidence. It uses the current field-matched sample, so watch settled days and live delta rather than one early example.';
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
      var dataComplete = daily.data_complete !== false;
      var comparison = daily.comparison || {};
      var selectedDeltaRaw = comparison.delta_vs_live;
      var selectedDeltaKnown = selectedDeltaRaw !== null && selectedDeltaRaw !== undefined && selectedDeltaRaw !== '';
      var selectedDelta = num(selectedDeltaRaw, 0);
      var selectedDeltaColor = selectedDelta >= 0 ? 'var(--green)' : 'var(--red)';
      var selectedDateFigure = !dataComplete
        ? '<div class="card-big" style="font-size:24px;color:var(--amber)">Skipped</div><div class="card-sub">no field graph data for this date</div>'
        : (selectedDeltaKnown
          ? gauge({value:Math.min(Math.abs(selectedDelta), 100), max:100, size:80, color:selectedDeltaColor, label:signedMoney(selectedDelta), sub:'selected date'})
          : '<div class="card-big" style="font-size:24px;color:var(--muted2)">Pending</div><div class="card-sub">settles after results are stored</div>');
      var title = tab.id === 'quality' ? 'Fix 2 — Quality-Weighted Tipster Grading' : (tab.id === 'history' ? 'Fix 3 — Full SQLite Rival History in Picks' : 'Fix 4 — Field-Aware + Full History Combined');
      var sub = tab.id === 'quality' ? 'Would picks change if tipster sources were weighted by quality (Tier 1-4) instead of raw count?' : (tab.id === 'history' ? 'Would picks change if the full SQLite head-to-head record directly influenced scoring instead of the summary profile file?' : 'The overlay fix plus the full SQLite head-to-head record, working together. The most complete picture of what rival evidence can do.');
      var sampleLabel = challengerSampleLabel(tab, summary);
      var sampleNote = challengerSampleNote(tab, summary);
      var help = tabPlain[tab.id] || {};
      return '<div class="chart-card"><div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap"><div><div style="font-family:var(--display);font-size:24px;color:var(--text);line-height:1.2">'+esc(title)+'</div><div style="font-size:14px;color:var(--muted);line-height:1.8;max-width:760px">'+esc(sub)+'</div></div>'+pill(String(status).replace(/_/g,' '), stateColor(status))+'</div>'+
        '<div style="margin-top:12px;padding:12px 14px;border-left:3px solid var(--blue);background:rgba(56,189,248,.06);border-radius:0 var(--r-sm) var(--r-sm) 0">'+
          '<div style="font-size:14px;line-height:1.7;color:var(--text);font-weight:750">'+esc(help.plain || 'Simple version: this is a paper test only.')+'</div>'+
          '<div style="font-size:13px;line-height:1.7;color:var(--muted);margin-top:4px">'+(help.lookingFor || 'We are checking whether this would improve picks over time without changing live picks today.')+'</div>'+
        '</div>'+
        (tab.id === 'history' ? '<div style="margin-top:12px"><div style="font-family:var(--display);font-size:28px;color:var(--gold);line-height:1">'+esc(headToHeadRowsLabel)+'</div><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase">historical matchups available</div></div>' : '')+
        (tab.id === 'combined' ? '<div style="margin-top:12px">'+changeBadge('Current field-matched sample','var(--blue)')+'<div style="font-size:14px;color:var(--muted);line-height:1.8">Uses the latest challenger sample. The old 9 July proof case is archived, not the main live status.</div></div>' : '')+
        (!dataComplete ? '<div style="margin-top:12px;color:var(--amber);font-size:13px;line-height:1.8">Field graph data not available for this date. This challenger skipped this day.</div>' : '')+
        '<div class="grid grid-4" style="margin-top:16px"><div class="chart-card">'+trafficLight(status, 'large', true)+'</div>'+
          '<div class="chart-card"><div class="chart-title">'+esc(sampleLabel)+'</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px"><div><div class="card-big">'+esc(summary.days_tested || 0)+'</div><div class="card-sub">tested</div></div><div><div class="card-big">'+esc(summary.settled_days || 0)+'</div><div class="card-sub">settled</div></div></div><div class="card-sub" style="margin-top:10px;line-height:1.7">'+esc(sampleNote)+'</div></div>'+
          '<div class="chart-card"><div class="chart-title">Selected date vs live</div>'+selectedDateFigure+'</div>'+
          '<div class="chart-card"><div class="chart-title">Overall settled vs live</div>'+gauge({value:Math.min(Math.abs(delta), 100), max:100, size:80, color:color, label:signedMoney(delta), sub:'all settled sample'})+'</div></div>'+
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
      var selectedComparison = selected && selected.comparison ? selected.comparison : null;
      return '<div><div style="display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:12px"><div><div style="font-family:var(--display);font-size:24px;line-height:1.2">Fix 1 — Field-Aware Rival Overlay</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6">LIVE FROM 10 JULY 2026</div></div>'+pill('LIVE','green')+'</div>'+
        '<div style="border:1px solid rgba(56,189,248,.35);background:rgba(56,189,248,.06);border-radius:var(--r-md);padding:20px;margin-bottom:14px">'+
          '<div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap"><div><div style="font-family:var(--display);font-size:26px;color:var(--blue);line-height:1.2">Current field-aware evidence</div><div style="font-size:14px;color:var(--muted);line-height:1.8;max-width:760px">This now shows the running evidence, not an old case study. Rival points only count when the rival is actually running in today&apos;s race.</div></div>'+trafficLight(totalCompared < 7 ? 'COLLECTING' : (better < oldBetter ? 'RISKY' : (totalCompared >= 14 && better > oldBetter ? 'PROMOTION_CANDIDATE' : 'WATCHING')), 'small', false)+'</div>'+ 
          '<div class="grid grid-4" style="margin-top:16px"><div class="chart-card"><div class="chart-title">Days compared</div><div class="card-big">'+esc(totalCompared)+'</div><div class="card-sub">field-aware vs old overlay</div></div><div class="chart-card"><div class="chart-title">Field-aware better</div><div class="card-big" style="color:var(--green)">'+esc(better)+'</div><div class="card-sub">days</div></div><div class="chart-card"><div class="chart-title">Old overlay better</div><div class="card-big" style="color:var(--red)">'+esc(oldBetter)+'</div><div class="card-sub">days</div></div><div class="chart-card"><div class="chart-title">Same result</div><div class="card-big" style="color:var(--muted2)">'+esc(same)+'</div><div class="card-sub">days</div></div></div>'+ 
          '<div style="font-size:13px;color:var(--muted2);line-height:1.8;margin-top:12px">Original 9 July proof case is archived, but this panel now focuses on what the evidence says today.</div></div>'+
        '<div class="grid grid-3" style="margin-bottom:14px"><div class="chart-card"><div class="chart-title">Today: same or different?</div>'+(selectedComparison ? (selectedComparison.same_as_live ? '<div class="card-big" style="color:var(--green);line-height:1.4;margin-bottom:8px">✓</div><div class="card-sub" style="font-size:14px;line-height:1.8;color:var(--muted)">Field-aware agrees with live today.</div>' : '<div><div style="font-size:15px;font-weight:700;line-height:1.8;margin-bottom:8px">Different picks today</div><div style="font-size:13px;color:var(--muted);line-height:1.8">Live: '+esc((selectedComparison.only_live||[]).join(', ')||'none')+'</div><div style="font-size:13px;color:var(--muted);line-height:1.8">Challenger: '+esc((selectedComparison.only_challenger||[]).join(', ')||'none')+'</div></div>') : '<div><div style="font-size:16px;color:var(--gold);line-height:1.8;margin-bottom:8px;text-align:center;font-weight:700">Waiting for 10:00</div><div style="margin-top:8px;color:var(--muted);font-size:14px;line-height:1.8;text-align:center">Today&apos;s comparison will appear here after picks generate at 10:00 and the Challenger Lab feed updates. Check back after 10:05.</div></div>')+'</div><div class="chart-card"><div class="chart-title">Running score</div>'+runningScoreHtml+'</div><div class="chart-card"><div class="chart-title">Traffic light status</div>'+trafficLight(totalCompared < 7 ? 'COLLECTING' : (better < oldBetter ? 'RISKY' : (totalCompared >= 14 && better > oldBetter ? 'PROMOTION_CANDIDATE' : 'WATCHING')), 'large', false)+'<div style="margin-top:8px;font-family:var(--mono);line-height:1.8"><div style="font-size:15px;color:var(--text);margin-bottom:8px">'+esc(comparedLabel)+'</div><div style="font-size:13px;color:var(--muted2)">'+esc(trafficReview)+'</div></div></div></div>'+
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
      '<div class="grid grid-4" style="margin-bottom:16px">'+
        simpleHelpCard(tabPlain.overlay)+simpleHelpCard(tabPlain.quality)+simpleHelpCard(tabPlain.history)+simpleHelpCard(tabPlain.combined)+
      '</div>'+
      renderTabs()+'<div id="what-would-change-dates">'+renderDatePills()+'</div><div id="what-would-change-active">'+renderActivePanel()+'</div></div>';
  }
  document.getElementById('panel-confirm').innerHTML =
    '<div style="background:linear-gradient(135deg, rgba(240,192,64,.08), rgba(56,189,248,.05));border:1px solid rgba(240,192,64,.3);border-radius:18px;padding:28px 28px 22px;margin-bottom:22px">'+
      '<div style="font-family:var(--display);font-size:28px;color:var(--gold);text-align:center">Signal 75 has watched every horse race in Britain for the last 11 years.</div>'+
      '<div style="font-family:var(--body);font-size:14px;color:var(--text);margin-top:8px;text-align:center">That&apos;s '+esc(headToHeadRowsLabel)+' recorded times one horse finished in front of another. We remember all of it.</div>'+
      '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:24px">'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--gold)">4,015</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">days of racing remembered</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">When two horses line up today that last met at Cheltenham in 2023, Signal 75 knows exactly what happened. Who won. By how much. What the ground was like. It never forgets.</div></div>'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--green)">'+esc(positiveRelationshipEdge)+'</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">horses with a proven edge today</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">'+esc(positiveRelationshipEdge)+' of today&apos;s runners have beaten at least one of their rivals before. Not a guess. Not a rating. An actual race result, stored and remembered. That is the advantage.</div></div>'+
        '<div><div style="font-family:var(--display);font-size:34px;color:var(--blue)">'+esc(headToHeadRowsLabel)+'</div><div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.6;text-transform:uppercase">head-to-head records checked this morning</div><div style="color:var(--muted);font-size:14px;line-height:1.8;margin-top:8px">Every morning Signal 75 checks every horse against every rival they might face, across the stored race memory. No human could do this. The system does it in seconds.</div></div>'+
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
  var officialSections = officialBetSections();
  var officialPickCount = officialSections.reduce(function(sum, section){ return sum + asArray(section.picks).length; }, 0);
  var runnerWarningRows = runners.filter(function(r){ return asArray(r.warnings).length; }).slice(0,5);
  var trustWarnings = warningCount + runnerWarningRows.length;
  var trustState = officialPickCount ? (trustWarnings ? 'WATCHING' : 'PROMISING') : 'COLLECTING';
  var trustTone = trustState === 'PROMISING' ? 'green' : (trustState === 'WATCHING' ? 'amber' : 'grey');
  var trustTitle = officialPickCount
    ? (trustWarnings ? 'AMBER - picks are valid, but review the warnings' : 'GREEN - today&apos;s picks passed the main checks')
    : 'NO BET - no official selections passed today';
  var trustCopy = officialPickCount
    ? (trustWarnings ? 'Signal 75 has an official bet, but there is rival or runner evidence worth reading before staking.' : 'The official picks passed price, score, field and confirmation checks. No major warning is showing in this feed.')
    : 'No qualifying horse met the live rules. The correct action is no official bet.';
  function confirmCheck(label, ok, detail){
    return '<div class="confirm-check '+(ok ? 'ok' : 'watch')+'">'+
      '<div><strong>'+esc(label)+'</strong><span>'+esc(detail)+'</span></div>'+
      pill(ok ? 'OK' : 'Review', ok ? 'green' : 'amber')+
    '</div>';
  }
  function confirmWarnings(){
    var rows = [];
    asArray(fg.warnings).slice(0,4).forEach(function(row){
      rows.push('<div class="confirm-warning"><strong>'+esc(row.horse || 'Runner')+'</strong><span>'+esc(row.label || row.reason || 'Rival graph warning stored for review.')+'</span></div>');
    });
    runnerWarningRows.forEach(function(row){
          rows.push('<div class="confirm-warning"><strong>'+esc(row.name || 'Runner')+'</strong><span>'+raceContextHtml(row)+' · '+esc(asArray(row.warnings).join(' | '))+'</span></div>');
    });
    return rows.length ? rows.slice(0,6).join('') : '<div class="empty">No major warnings showing today.</div>';
  }
  var technicalConfirmDetail =
    '<details class="confirm-details"><summary>Show racing memory and challenger detail</summary>'+
      '<div class="confirm-memory">'+
        '<div><strong>'+esc(headToHeadRowsLabel)+'</strong><span>head-to-head records checked this morning</span></div>'+
        '<div><strong>'+esc(positiveRelationshipEdge)+'</strong><span>horses with a proven edge today</span></div>'+
        '<div><strong>'+esc(graphTotal)+'</strong><span>runners checked by the rival graph</span></div>'+
      '</div>'+
      fieldAwareSection()+
    '</details>'+
    '<details class="confirm-details"><summary>Show source and graph counts</summary>'+
      '<div class="grid grid-3" style="margin-top:14px">'+
        '<div class="chart-card"><div class="chart-title">Tipster coverage</div>'+gauge({value:matchPct,color:'var(--gold)',label:tip.totalMatched || 0,sub:'MATCHED'})+
          '<div class="card-sub">'+esc(tip.sourcesSuccessful || 0)+' sources worked · '+esc(tip.estimatedCallsAvoided || 0)+' paid calls avoided</div></div>'+
        '<div class="chart-card"><div class="chart-title">Horse memory</div>'+gauge({value:horseCount,max:Math.max(1, horseCount),color:'var(--blue)',label:horseCount,sub:'ACTIVE'})+
          '<div class="card-sub">'+esc(db.profileCount || 0)+' stored profiles in the database.</div></div>'+
        '<div class="chart-card"><div class="chart-title">Rival graph checked</div>'+gauge({value:graphTotal,max:Math.max(1, graphTotal),color:'var(--blue)',label:graphTotal,sub:'RUNNERS'})+
          '<div class="card-sub">'+esc(fg.edgeCount || 0)+' historical matchups checked.</div></div>'+
      '</div>'+
      '<div class="grid grid-2" style="margin-top:14px">'+
        '<div class="chart-card"><div class="chart-title">Best horse-memory edges</div>'+
          (bestEdges.length ? bestEdges.slice(0,6).map(function(row){return graphRow(row, 'var(--green)');}).join('') : positiveFallback)+
        '</div>'+
        '<div class="chart-card"><div class="chart-title">Live memory overlay actually used</div>'+
          (rivalRows.length ? rivalRows.map(signalBar).join('') : '<div class="empty">No runner in the current comparison has a rival-memory boost today.</div>')+
        '</div>'+
      '</div>'+
    '</details>';
  document.getElementById('panel-confirm').innerHTML =
    '<div class="confirm-hero state-'+trustState.toLowerCase()+'">'+
      '<div class="confirm-traffic">'+trafficLight(trustState, 'large', false)+'</div>'+
      '<div><div class="hero-kicker">Confirm</div><div class="confirm-title">'+trustTitle+'</div><div class="confirm-copy">'+trustCopy+'</div></div>'+
      '<div class="hero-stat">'+scoreChip(officialPickCount, 'OFFICIAL', trustState === 'PROMISING' ? 'var(--green)' : 'var(--gold)')+'</div>'+
    '</div>'+
    '<div class="confirm-main-grid">'+
      '<div class="confirm-panel">'+
        '<div class="chart-title">Today&apos;s official bet</div>'+
        officialBetCardsHtml()+
        '<div class="card-sub">Flat and Jumps stay separate unless the live rules create a Patent. No weak extra horse is forced.</div>'+
      '</div>'+
      '<div class="confirm-panel">'+
        '<div class="chart-title">Warnings to review</div>'+
        confirmWarnings()+
      '</div>'+
    '</div>'+
    '<div class="confirm-panel" style="margin-top:16px">'+
      '<div class="chart-title">What was checked</div>'+
      '<div class="confirm-check-grid">'+
        confirmCheck('Price band', true, 'Official selections must be inside the live value band.')+
        confirmCheck('Score gate', true, 'Official selections must pass the live score threshold.')+
        confirmCheck('Field size', true, 'Very large and unsuitable fields are protected against.')+
        confirmCheck('Form confidence', !runnerWarningRows.length, runnerWarningRows.length ? runnerWarningRows.length+' runner warnings found.' : 'No major form warning showing today.')+
        confirmCheck('Rival history', warningCount === 0, warningCount ? warningCount+' rival graph warnings found.' : 'No major rival warning showing today.')+
        confirmCheck('Tipster support', true, esc(tip.totalMatched || 0)+' tipster matches across the feed.')+
      '</div>'+
    '</div>'+
    '<div class="plain" style="margin-top:16px;background:rgba(56,189,248,.06);border-left-color:var(--blue)"><strong>Learning only:</strong> Challenger and graph evidence can explain confidence or warnings, but it does not change today&apos;s official picks unless a rule has already been approved live.</div>'+
    technicalConfirmDetail;
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
    var resultDays = firstDefined(row.pickResultDays, row.completePickResultDays, 0);
    return '<div class="challenger-card">'+
      '<div class="challenger-top"><div><div class="challenger-name">'+esc(row.name || 'Challenger')+'</div><div class="card-sub">'+esc(row.daysTested || 0)+' days tested · '+esc(row.daysWithPicks || 0)+' with picks · '+esc(resultDays)+' pick-result days · '+esc(row.roiReadyDays || row.settledDays || 0)+' ROI-ready</div></div>'+challengerStatus(row)+'</div>'+
      '<div class="challenger-metrics">'+
        '<div><span>Trial return</span><strong style="color:'+tone+'">'+esc(row.roi || 0)+'%</strong></div>'+
        '<div><span>Paper profit</span><strong style="color:'+tone+'">'+esc(money(row.profit))+'</strong></div>'+
        '<div><span>Vs live</span><strong style="color:'+deltaTone+'">'+esc(money(row.deltaVsLiveProfit))+'</strong></div>'+
      '</div>'+
      '<div class="challenger-rule">ROI-ready days need a complete paper bet and live comparison. Pick-result days mean individual horse results are stored but may not yet be complete enough for ROI proof.</div>'+
      '<div class="challenger-rule">Needs enough ROI-ready days, enough picks, positive result versus live, no data leakage, and manual approval before it can affect selections.</div>'+
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
  var maxSettled = rows.reduce(function(m,r){ return Math.max(m, r.roiReadyDays); }, 0);
  var liveRoi = num(firstDefined(live.roi, live.proof_roi), 0);
  var liveProfit = num(firstDefined(live.total_profit, live.profit), 0);
  var brain = sqliteBrain();
  function raceWarningLookup(){
    var data = pick('raceView') || {};
    var map = {};
    asArray(data.races).forEach(function(race){
      asArray(race.runners).forEach(function(runner){
        var key = cleanKey(runner.name)+'|'+cleanKey(race.course)+'|'+String(race.time || '');
        map[key] = asArray(runner.warnings);
      });
    });
    return map;
  }
  var raceWarnings = raceWarningLookup();
  function warningsForPick(pick){
    var key = cleanKey(pick.horse || pick.name)+'|'+cleanKey(pick.course)+'|'+String(pick.time || '');
    return raceWarnings[key] || asArray(pick.warnings);
  }
  function pickFlags(pick){
    var flags = [];
    var warningText = warningsForPick(pick).join(' | ');
    if(warningText.indexOf('Recent form confidence penalty') >= 0){
      flags.push('BLOCKED BY LIVE GATE');
    }
    if(num(pick.odds, 0) > 0 && num(pick.odds, 0) < 4.1){
      flags.push('BELOW PRICE FLOOR');
    }
    return flags;
  }
  function outputDate(data){
    return data.date || data.generated_at || data.generatedAt || ((data.history || {}).generated_at) || '';
  }
  function shortDate(value){
    var text = String(value || '');
    return text ? text.slice(0, 10) : '';
  }
  function toolStatus(tool){
    var status = pick('status') || {};
    var toolData = {};
    if(tool.id === 'excuse_interpreter_v1') toolData = pick('captureIntel') || {};
    if(tool.id === 'high_confidence_miss_v1') toolData = pick('highConfidenceMisses') || {};
    if(tool.id === 'balanced_fallback_v1') toolData = pick('diagnostics') || {};
    var hasOutput = toolData && Object.keys(toolData).length > 0;
    if(status.date === getTodayDate() && status.picksGenerated && status.resultsSettled !== true && status.resultsSettled !== 'settled'){
      return 'Scheduled for tonight';
    }
    if(hasOutput){
      var d = shortDate(outputDate(toolData) || outputDate(toolData.history || {}));
      return d ? 'Last run: '+d : 'Last run: stored output found';
    }
    return 'Never run';
  }
  function getTodayDate(){
    return new Date().toISOString().slice(0, 10);
  }
  function statePill(state){
    var s = trafficState(state);
    var tone = (s === 'RISKY') ? 'red' : ((s === 'PROMOTION_CANDIDATE' || s === 'APPROVED_BY_JOHN') ? 'gold' : (s === 'PROMISING' ? 'green' : (s === 'WATCHING' ? 'amber' : 'grey')));
    return pill(TRAFFIC_TEXT[s].label, tone);
  }
  function statTile(label, value, tone){
    return '<div class="lab-stat-tile '+(tone || '')+'"><span>'+esc(label)+'</span><strong>'+esc(value)+'</strong></div>';
  }
  function challengerPlainText(row){
    var id = String(row.id || '').toLowerCase();
    function info(title, simple, looking, proof, example){
      return {title:title, simple:simple, looking:looking, proof:proof, example:example || ''};
    }
    if(id.indexOf('class_setup') >= 0){
      return info(
        'Class Setup Caution',
        'Checks whether a horse is being asked to do something tougher than it has proved before.',
        'It compares today&apos;s race class or level with the horse&apos;s stored history. If a horse is stepping into a higher grade with no proof at that level, the test marks it as a caution.',
        'It would matter only if these cautions repeatedly avoid poor live picks without blocking good winners.',
        'Example: a horse wins a lower-grade handicap, then runs in a Group race today. This test asks: has it already shown it can cope with that higher level?'
      );
    }
    if(id.indexOf('consensus_quality') >= 0){
      return info(
        'Tipster Quality',
        'Tests whether trusted racing sources matter more than simply counting all tips equally.',
        'Live Signal 75 counts tipster support. This test gives more weight to stronger sources such as Racing Post or Timeform and less weight to weaker/noisier sources.',
        'It needs to beat live Signal 75 when it picks differently. If it keeps losing, it should stay rejected.',
        'Example: two horses both have 4 tips, but one has 4 high-quality sources and the other has 4 weaker sources. This test would prefer the high-quality-source horse.'
      );
    }
    if(id.indexOf('field_graph') >= 0){
      return info(
        'Field Graph',
        'Checks whether today&apos;s horse has already beaten the actual rivals it faces today.',
        'It builds a race-by-race map of horse relationships. A horse gets paper credit only when its past wins are against horses running in the same field today.',
        'It needs repeated settled proof that those head-to-head clues find better winners or placed horses than live Signal 75.',
        'Example: Horse A has beaten Horse B and Horse C before, and both B and C run against it today. This test treats that as useful evidence.'
      );
    }
    if(id.indexOf('form_soft_penalty') >= 0){
      return info(
        'Form Soft Penalty',
        'Tests whether patchy recent form should reduce a horse&apos;s score instead of blocking it completely.',
        'Bad recent figures are marked down gently. A strong horse can still survive if other evidence is good enough.',
        'It must show it protects us from weak-form losers without throwing away horses that still win or place.',
        'Example: form 7471 is mixed but includes a last-time win. This test would caution it, not automatically reject it.'
      );
    }
    if(id.indexOf('freshness_penalty') >= 0){
      return info(
        'Freshness Penalty',
        'Tests whether horses returning from a break need a small warning.',
        'It looks at days since the horse last ran. A horse coming back after a moderate break may be less reliable, so this test applies a paper caution.',
        'It needs to prove that break warnings avoid more bad picks than they cost in missed good picks.',
        'Example: a horse has not raced for 60 days. This test asks whether that absence should reduce confidence today.'
      );
    }
    if(id.indexOf('jumps_score_gate') >= 0){
      return info(
        'Jumps Score Gate 70',
        'Tests whether jumps racing should allow slightly lower scores than flat racing.',
        'Live Signal 75 usually wants stronger scores. This paper test asks whether jumps horses scoring around 70-74 are still good enough to place, because jumps races often have less tipster data.',
        'It needs to find extra jumps winners or placed horses without adding too many poor losers.',
        'Example: a jumps horse scores 72, so live Signal 75 would normally leave it out. This test asks: would it have been worth including anyway?'
      );
    }
    if(id.indexOf('large_field_penalty') >= 0){
      return info(
        'Large Field Penalty',
        'Tests whether crowded races should be treated as harder to place in.',
        'Fields with 15+ runners are more chaotic. This test marks those races down because even good horses can get blocked, crowded out, or find more rivals improving past them.',
        'It needs to improve results by avoiding bad large-field picks while not removing too many good ones.',
        'Example: a horse looks strong but runs in an 18-runner race. This test asks whether the big field should reduce confidence.'
      );
    }
    if(id.indexOf('lucky15') >= 0){
      return info(
        'Lucky 15',
        'Tests whether four paper picks would beat the normal one-to-three horse Signal 75 structure.',
        'Signal 75 normally uses Single, Double or Patent logic. Lucky 15 tests a four-horse bet structure on paper only.',
        'It needs enough settled days to show the bigger bet is genuinely worth the extra stake.',
        'Example: if four horses pass the paper rules, this test compares a Lucky 15 return against the normal official bet.'
      );
    }
    if(id.indexOf('price_source') >= 0){
      return info(
        'Price Source Review',
        'Checks whether the price source changes which horses qualify for Signal 75.',
        'Signal 75 uses morning Betfair exchange prices for the official price band. This test compares those prices with bookmaker prices and final BSP where available.',
        'It needs 30+ days to show whether Betfair exchange, bookmaker price or BSP would have made better filtering decisions.',
        'Example: Betfair shows 6.2 but bookmakers show 5/1. This test records whether that horse would be inside or outside the value band depending on the price source.'
      );
    }
    if(id.indexOf('rich_form_confidence') >= 0){
      return info(
        'Rich Form Confidence',
        'Checks whether the horse that beat us already had stronger evidence in the archive.',
        'After racing, it compares our pick with the winner or main rival using form pattern, class, weight, distance, going, draw, jockey and trainer data where available.',
        'It needs repeated examples where the warning was visible before the race and the warned-about rival then beat us.',
        'Example: our pick loses to a rival with better same-distance and same-going proof. This test asks whether that should become a future warning.'
      );
    }
    if(id.indexOf('rival_evidence') >= 0){
      return info(
        'Field-Aware Rival History',
        'Checks rival memory only against horses actually running in today&apos;s race.',
        'Old rival memory can be misleading if it boosts a horse for beating a rival that is not even in today&apos;s field. This test only counts relevant rivals in the current race.',
        'It needs to prove that field-aware rival evidence beats the older rival overlay and live Signal 75.',
        'Example: a horse once beat three rivals, but only one of them runs today. This test counts one relevant rival, not all three old wins.'
      );
    }
    if(id.indexOf('short_price_safety') >= 0){
      return info(
        'Short Price Safety',
        'Tests whether strong horses below the normal price band should be shown as safer singles, not value each-way picks.',
        'Live Signal 75 focuses on the 4.1-6.0 each-way value band. This test watches shorter-priced horses separately because they win/place more often but may offer less value.',
        'It needs to prove whether short-priced horses improve safety or simply reduce long-term return.',
        'Example: a horse is 3.2 and looks very strong. Live Signal 75 may reject it as too short; this test tracks whether that rejection was sensible.'
      );
    }
    if(id.indexOf('wider_price') >= 0){
      return info(
        'Wider Price Band',
        'Tests whether horses just above the normal price ceiling are worth considering.',
        'Live Signal 75 normally stops at 6.0. This paper test watches horses up to around 7.5 when the rest of the evidence is strong.',
        'It needs to beat live results after settlement, not just find occasional bigger-priced winners.',
        'Example: a horse is 6.8, so live Signal 75 says it is too big a price. This test asks whether strong evidence should still allow it.'
      );
    }
    return info(
      row.name || 'Challenger',
      'Tests one possible future improvement in the background.',
      'It compares a paper-only rule against live Signal 75 without changing today&apos;s official bet.',
      'It needs enough settled days, a better result than live, and manual approval before it can go live.',
      'Example: the dashboard records what it would have picked, then checks after racing whether that would have helped.'
    );
  }
  function challengerPlainBox(row){
    var text = challengerPlainText(row);
    return '<div style="margin-top:12px;padding:12px 14px;border-left:3px solid var(--blue);background:rgba(56,189,248,.06);border-radius:0 var(--r-sm) var(--r-sm) 0">'+
      '<div style="font-size:14px;line-height:1.7;color:var(--text);font-weight:800">'+esc(text.title)+': '+text.simple+'</div>'+
      '<div style="font-size:13px;line-height:1.7;color:var(--muted);margin-top:4px"><strong style="color:var(--gold)">What this means:</strong> '+text.looking+'</div>'+
      (text.example ? '<div style="font-size:13px;line-height:1.7;color:var(--muted);margin-top:4px"><strong>Example:</strong> '+text.example+'</div>' : '')+
      '<div style="font-size:13px;line-height:1.7;color:var(--muted2);margin-top:4px"><strong>What would prove it:</strong> '+text.proof+'</div>'+
    '</div>';
  }
  function challengerFamily(row){
    var id = String(row.id || '').toLowerCase();
    if(id.indexOf('field_graph') >= 0 || id.indexOf('rival') >= 0 || id.indexOf('rich_form') >= 0){
      return {label:'Horse evidence', note:'Checks rivals, form history and what actually beat us.'};
    }
    if(id.indexOf('lucky15') >= 0){
      return {label:'Bet structure test', note:'Checks whether a four-horse Lucky 15 would improve the paper return.'};
    }
    if(id.indexOf('form_soft') >= 0 || id.indexOf('freshness') >= 0 || id.indexOf('large_field') >= 0 || id.indexOf('jumps_score') >= 0){
      return {label:'Safety filter', note:'Checks whether a small caution would avoid weak picks.'};
    }
    if(id.indexOf('wider_price') >= 0){
      return {label:'Price test', note:'Checks whether slightly bigger prices are worth considering.'};
    }
    if(id.indexOf('consensus') >= 0){
      return {label:'Tipster test', note:'Checks whether tipster quality improves the raw tip count.'};
    }
    return {label:'Paper test', note:'Checks a possible future rule without changing live picks.'};
  }
  function challengerDecision(row){
    if(row.stage === 'RISKY'){
      return {tone:'red', label:'Do not use', text:'Losing against live Signal 75. Keep it away from real picks.'};
    }
    if(row.stage === 'PROMOTION_CANDIDATE' || row.stage === 'APPROVED_BY_JOHN'){
      return {tone:'gold', label:'Review', text:'Enough evidence to review manually before any live change.'};
    }
    if(row.roiReadyDays < 14){
      if(row.deltaProfit > 10) return {tone:'green', label:'Promising early', text:'Interesting, but still too few settled days.'};
      if(row.deltaProfit < -10) return {tone:'red', label:'Weak early', text:'Early sample, but currently hurting results.'};
      return {tone:'amber', label:'Too early', text:'Not enough settled evidence yet.'};
    }
    if(row.deltaProfit > 0){
      return {tone:'green', label:'Watch closely', text:'Ahead of live on paper. Needs combined evidence review.'};
    }
    if(row.deltaProfit < 0){
      return {tone:'red', label:'Weak', text:'Behind live on paper. Do not promote.'};
    }
    return {tone:'blue', label:'Neutral', text:'No clear improvement yet.'};
  }
  function combinedEvidenceBoard(){
    rows = rows.filter(function(row){ return String(row.id || '').toLowerCase().indexOf('skin_in_game') < 0; });
    var sortedRows = rows.slice().sort(function(a,b){
      var da = challengerDecision(a), db = challengerDecision(b);
      var rank = {gold:0, green:1, amber:2, blue:3, red:4, grey:5};
      return (rank[da.tone] || 9) - (rank[db.tone] || 9) || b.deltaProfit - a.deltaProfit;
    });
    var watchRows = sortedRows.filter(function(r){ var d=challengerDecision(r); return d.tone === 'green' || d.tone === 'gold'; });
    var avoidRows = sortedRows.filter(function(r){ return challengerDecision(r).tone === 'red'; });
    var readyRows = sortedRows.filter(function(r){ return r.stage === 'PROMOTION_CANDIDATE' || r.stage === 'APPROVED_BY_JOHN'; });
    var bestWatch = watchRows[0] || null;
    var worstAvoid = avoidRows[0] || null;
    function simpleTestCard(row){
      var plain = challengerPlainText(row);
      var family = challengerFamily(row);
      var decision = challengerDecision(row);
      var dotState = decision.tone === 'red' ? 'RISKY' : (decision.tone === 'green' ? 'PROMISING' : (decision.tone === 'gold' ? 'PROMOTION_CANDIDATE' : 'COLLECTING'));
      var evidence = row.roiReadyDays+' proper day'+(row.roiReadyDays === 1 ? '' : 's')+' checked · '+esc(signedMoney(row.deltaProfit))+' vs live';
      return '<div class="chart-card" style="padding:14px;display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;align-items:start">'+
        '<div>'+trafficLight(dotState, 'mini', false)+'</div>'+ 
        '<div><div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px"><strong style="font-size:16px;color:var(--text);line-height:1.3">'+esc(plain.title)+'</strong>'+pill(decision.label, decision.tone)+'</div>'+ 
          '<div style="font-size:13px;color:var(--muted);line-height:1.7"><strong style="color:var(--text)">What it tests:</strong> '+plain.simple+'</div>'+ 
          '<div style="font-size:13px;color:var(--muted);line-height:1.7;margin-top:4px"><strong style="color:var(--gold)">Example:</strong> '+plain.example+'</div>'+ 
          '<div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px"><strong>Current read:</strong> '+esc(decision.text)+'</div>'+ 
          '<div style="font-family:var(--mono);font-size:12px;color:var(--muted2);line-height:1.7;margin-top:6px">'+esc(family.label)+' · '+evidence+'</div>'+ 
        '</div>'+ 
      '</div>';
    }
    return '<div class="lab-section combined-board">'+
      '<div class="section-block-h"><h2>Simple Challenger View</h2><span class="n">Deb view</span></div>'+ 
      '<div class="plain big" style="margin-bottom:14px"><strong>Plain English:</strong> these are paper tests. They do not change today&apos;s bet. We only care whether a test repeatedly beats live Signal 75 after results are settled.</div>'+ 
      '<div class="grid grid-3" style="margin-bottom:14px">'+
        card('Anything ready?', '<div class="lab-count '+(readyRows.length?'gold-pulse':'blue')+'">'+esc(readyRows.length ? 'YES' : 'NO')+'</div><div class="card-sub">'+(readyRows.length ? 'John review needed' : 'nothing should go live')+'</div>')+
        card('Best thing to watch', bestWatch ? '<div class="card-big" style="font-size:22px;color:var(--green)">'+esc(challengerPlainText(bestWatch).title)+'</div><div class="card-sub">'+esc(signedMoney(bestWatch.deltaProfit))+' vs live · '+esc(bestWatch.roiReadyDays)+' proper days</div>' : '<div class="card-big" style="font-size:22px;color:var(--muted2)">None yet</div><div class="card-sub">still collecting</div>')+
        card('Biggest concern', worstAvoid ? '<div class="card-big" style="font-size:22px;color:var(--red)">'+esc(challengerPlainText(worstAvoid).title)+'</div><div class="card-sub">'+esc(signedMoney(worstAvoid.deltaProfit))+' vs live</div>' : '<div class="card-big" style="font-size:22px;color:var(--green)">No red flag</div><div class="card-sub">nothing clearly harmful</div>')+
      '</div>'+ 
      '<div class="plain" style="margin-bottom:12px"><strong>How to read the list:</strong> green means interesting, amber means too early, red means avoid. A test needs around 30 settled days and John approval before it can affect live picks.</div>'+ 
      '<div style="display:grid;gap:10px">'+(sortedRows.length ? sortedRows.map(simpleTestCard).join('') : '<div class="empty">No challenger rows are available yet.</div>')+'</div>'+ 
    '</div>';
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
            challengerPlainBox(row)+
            '<div class="card-sub">Date range tested: '+esc(range.start || 'unknown')+' to '+esc(range.end || 'unknown')+' · Pick-result days: '+esc(row.pickResultDays)+' · ROI-ready days: '+esc(row.roiReadyDays)+' · Paper profit: '+esc(signedMoney(row.profit))+' · Vs live '+esc(signedMoney(row.deltaProfit))+'</div>'+
            (row.raw.archived_reason ? '<div class="card-sub" style="margin-top:8px">'+esc(row.raw.archived_reason)+'</div>' : '')+
          '</div>'+
        '</div>'+
      '</div>';
    }
    if(row.id === 'lucky15_v1'){
      var raw = row.raw || {};
      var scenarioA = num(firstDefined(raw.scenario_a_triggered_days, raw.scenarioATriggeredDays), 0);
      var scenarioB = num(firstDefined(raw.scenario_b_triggered_days, raw.scenarioBTriggeredDays), 0);
      var deltaA = num(firstDefined(raw.scenario_a_delta_vs_patent, raw.scenarioADeltaVsPatent), 0);
      var deltaB = num(firstDefined(raw.scenario_b_delta_vs_patent, raw.scenarioBDeltaVsPatent), 0);
      return '<div class="lab-card state-'+row.stage.toLowerCase().replace(/_/g, '-')+'">'+
        '<div class="lab-card-row top">'+
          trafficLight(row.stage, 'large', false)+
          '<div class="lab-card-title"><div>Lucky 15 Challenger</div><span>lucky15_v1</span>'+
            '<div class="lab-traffic-summary"><strong>'+esc(verdict.label)+'</strong><small>'+esc(verdict.verdict)+'</small></div></div>'+
          '<div class="lab-stat-pair">'+statTile('Days tested', row.days, '')+statTile('ROI-ready', row.roiReadyDays, '')+'</div>'+
        '</div>'+
        challengerPlainBox(row)+
        '<div class="lab-gauges">'+
          '<div class="lab-meter"><span>Lucky 15 vs live</span><strong class="'+(row.deltaProfit >= 0 ? 'good' : 'bad')+'">'+esc(signedMoney(row.deltaProfit))+' · '+esc(signedPct(row.deltaRoi))+'</strong></div>'+
          '<div class="lab-meter"><span>Lucky 15 trial ROI</span><strong class="'+(row.roi >= 0 ? 'good' : 'bad')+'">'+esc(row.roi.toFixed(1).replace(/\.0$/,''))+'%</strong></div>'+
        '</div>'+
        '<div class="grid grid-2" style="margin-top:12px">'+
          '<div class="chart-card"><div class="chart-title">Scenario A</div><div class="card-big" style="font-size:26px">'+esc(scenarioA)+'</div><div class="card-sub">4 normal 75+ picks found naturally</div><div class="card-sub">Vs Patent: '+esc(signedMoney(deltaA))+'</div></div>'+
          '<div class="chart-card"><div class="chart-title">Scenario B</div><div class="card-big" style="font-size:26px">'+esc(scenarioB)+'</div><div class="card-sub">3 official picks plus one 72-74 extra leg</div><div class="card-sub">Vs Patent: '+esc(signedMoney(deltaB))+'</div></div>'+
        '</div>'+
        '<details class="lab-details"><summary>Show criteria and notes</summary>'+
          '<div class="card-sub">Paper stake: £30 · 30 each-way lines. This never changes the live £14 Signal 75 proof stake.</div>'+
          '<div class="challenger-warning">Manual approval required before any Lucky 15 idea affects live bets.</div>'+
        '</details>'+
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
          '<div class="lab-stat-pair">'+statTile('Days tested', row.days, '')+statTile('ROI-ready', row.roiReadyDays, '')+'</div>'+
        '</div>'+
        '<div style="font-family:var(--display);font-size:34px;color:var(--gold);margin-top:10px">'+esc(sqliteHeadToHeadRowsLabel())+'</div>'+
        '<div style="font-family:var(--mono);font-size:12px;line-height:1.6;color:var(--muted2);text-transform:uppercase">records · field-matched only</div>'+
        challengerPlainBox(row)+
        '<div class="plain" style="margin-top:12px">Same scoring as live Signal 75, but rival evidence only counts when the rival is actually running today. Use the settled days, ROI-ready days and live delta above to judge whether it is improving the system now.</div>'+
        '<div class="lab-status-line">'+running+'</div>'+
        '<details class="lab-details"><summary>Show criteria and notes</summary>'+
          '<div class="card-sub">Picks tested: '+esc(row.picks)+' · Pick-result days: '+esc(row.pickResultDays)+' · ROI-ready days: '+esc(row.roiReadyDays)+' · Paper profit: '+esc(signedMoney(row.profit))+' · Vs live '+esc(signedMoney(row.deltaProfit))+'</div>'+
          '<div class="challenger-warning">Manual approval required before any rival challenger affects live picks.</div>'+
        '</details>'+
      '</div>';
    }
    return '<div class="lab-card state-'+row.stage.toLowerCase().replace(/_/g, '-')+'">'+
      '<div class="lab-card-row top">'+
        trafficLight(row.stage, 'large', false)+
        '<div class="lab-card-title"><div>'+esc(row.name)+'</div><span>'+esc(row.id)+'</span>'+
          '<div class="lab-traffic-summary"><strong>'+esc(verdict.label)+'</strong><small>'+esc(verdict.verdict)+'</small></div></div>'+
        '<div class="lab-stat-pair">'+statTile('Days tested', row.days, '')+statTile('ROI-ready', row.roiReadyDays, '')+'</div>'+
      '</div>'+
      '<div class="lab-gauges">'+
        '<div class="lab-meter"><span>Vs live picks</span><strong class="'+deltaTone+'">'+esc(signedMoney(row.deltaProfit))+' · '+esc(signedPct(row.deltaRoi))+'</strong></div>'+
        '<div class="lab-meter"><span>Trial return</span><strong class="'+(row.roi >= 0 ? 'good' : 'bad')+'">'+esc(row.roi.toFixed(1).replace(/\.0$/,''))+'%</strong></div>'+
      '</div>'+
      '<div class="lab-spark">'+(spark.length ? sparkline(spark, row.deltaProfit >= 0 ? 'var(--green)' : 'var(--red)', 220, 42) : '<div class="empty mini">Collecting data...</div>')+'</div>'+
      challengerPlainBox(row)+
        '<div class="lab-status-line">'+statePill(row.stage)+'</div>'+
        '<div class="card-sub" style="margin-top:8px">Pick-result days: '+esc(row.pickResultDays)+' · Complete pick-result days: '+esc(row.completePickResultDays)+' · ROI-ready comparison days: '+esc(row.roiReadyDays)+'</div>'+
      '<details class="lab-details"><summary>Show criteria and notes</summary>'+
        '<div class="card-sub">Picks tested: '+esc(row.picks)+' · Pick-result days: '+esc(row.pickResultDays)+' · ROI-ready days: '+esc(row.roiReadyDays)+' · Paper profit: '+esc(signedMoney(row.profit))+'</div>'+
        (row.warning ? '<div class="challenger-warning">'+esc(row.warning)+'</div>' : '<div class="card-sub">No additional warning stored.</div>')+
      '</details>'+
    '</div>';
  }
  function liveVsChallenger(){
    var livePicks = asArray(latest.live_system && latest.live_system.official_picks);
    var firstChallenger = latestRows[0] || {};
    var challengerPicks = asArray(firstChallenger.picks);
    return '<div class="lab-section"><div class="section-block-h"><h2>Today: live vs challenger</h2><span class="n">paper comparison only</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> left is what Signal 75 actually picked today. Right is what the first test rule would have picked. The right side is not a bet and does not count in results.</div>'+
      '<div class="lab-compare-grid">'+
        '<div class="compare-card"><div class="chart-title">Live official selections</div>'+
          (livePicks.length ? livePicks.map(function(p){ return '<div class="pick-pill live"><strong>'+esc(p.horse || p.name)+'</strong><span>'+raceContextHtml(p)+' · '+esc(p.odds || '')+'</span></div>'; }).join('') : '<div class="empty">No live pick list in this dashboard feed.</div>')+
        '</div>'+
        '<div class="compare-card"><div class="chart-title">'+esc(firstChallenger.name || 'Best challenger')+'</div>'+
          (challengerPicks.length ? challengerPicks.map(function(p){ return '<div class="pick-pill challenger"><strong>'+esc(p.horse || p.name)+'</strong><span>'+raceContextHtml(p)+' · '+esc(p.odds || '')+(p.live_selected ? ' · also live' : ' · paper only')+'</span></div>'; }).join('') : '<div class="empty">No challenger pick list in this dashboard feed yet.</div>')+
        '</div>'+
      '</div></div>';
  }
  function differenceTable(){
    var diffs = [];
    latestRows.forEach(function(ch){
      asArray(ch.picks).forEach(function(p){
        if(!p.live_selected){
          diffs.push({
            rule:ch.name || ch.id,
            horse:p.horse || p.name,
            course:p.course,
            time:p.time,
            odds:p.odds,
            score:firstDefined(p.combined_score,p.base_score,p.score),
            why:'Challenger only',
            flags:pickFlags(p)
          });
        }
      });
    });
    return '<div class="lab-section"><div class="section-block-h"><h2>Pick difference view</h2><span class="n">what changed on paper</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> this lists horses the test rule noticed but the live system did not pick. It helps us see whether the test is finding better horses or just adding noise.</div>'+
      '<div class="diff-table">'+
        '<div class="diff-head"><span>Challenger</span><span>Horse</span><span>Race</span><span>Score</span><span>Why</span></div>'+
        (diffs.length ? diffs.slice(0,12).map(function(d){
          var flags = asArray(d.flags).map(function(f){ return '<span style="color:var(--amber);font-family:var(--mono);font-size:11px;line-height:1.6;margin-left:6px">'+esc(f)+'</span>'; }).join('');
          return '<div class="diff-row"><span>'+esc(d.rule)+'</span><strong>'+esc(d.horse)+flags+'</strong><span>'+raceContextHtml(d)+' · '+esc(d.odds||'')+'</span><span>'+esc(d.score || '')+'</span><span>'+esc(d.why)+'</span></div>';
        }).join('') : '<div class="empty">No pick differences stored yet.</div>')+
      '</div></div>';
  }
  function dials(){
    var positives = rows.filter(function(r){ return r.deltaProfit > 0 && (r.stage === 'PROMISING' || r.stage === 'WATCHING'); }).length;
    var negatives = rows.filter(function(r){ return r.stage === 'RISKY'; }).length;
    var neutral = rows.filter(function(r){ return r.stage === 'COLLECTING'; }).length;
    return '<div class="lab-section"><div class="section-block-h"><h2>Improvement vs damage</h2><span class="n">quick read</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> this is the quick safety check. Green means a test is helping on paper. Red means it may be hurting. Amber means we do not have enough evidence yet.</div>'+
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
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> these checks run after racing. They look for lessons such as good horses we missed, bad picks we should have avoided, and patterns worth tracking tomorrow.</div>'+
      '<div class="grid grid-auto">'+(tools.length ? tools.map(function(t){
        var statusText = toolStatus(t);
        var dot = statusText.indexOf('Last run') === 0 ? 'green' : (statusText.indexOf('Scheduled') === 0 ? 'amber' : 'grey');
        return '<div class="autotile"><div class="ah">'+trafficDot(dot)+'<span class="at-time">'+esc(t.time || '')+'</span></div><div class="at-label">'+esc(t.label || t.name || 'Learning tool')+'</div><div class="card-sub">'+esc(statusText)+'</div></div>';
      }).join('') : '<div class="card"><div class="card-big" style="font-size:18px">No post-race tool list available</div><div class="card-sub">The normal learning jobs still run from the main pipeline.</div></div>')+'</div></div>';
  }
  function promotionQueue(){
    return '<div class="lab-section"><div class="section-block-h"><h2>Promotion queue</h2><span class="n">manual approval only</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> if a test proves itself, it appears here for John to review. Nothing moves into live picks automatically.</div>'+
      '<div class="lab-queue '+(candidates.length ? 'has-candidate' : '')+'">'+
        (candidates.length ? candidates.map(function(c){
          return '<div class="queue-row">'+trafficLight('PROMOTION_CANDIDATE','mini',false)+'<div><strong>'+esc(c.name || c.id || 'Promotion candidate')+'</strong><div class="card-sub">'+esc(c.reason || 'Ready for John to review. No automatic live change.').replace(/</g,'&lt;')+'</div></div></div>';
        }).join('') : '<div class="empty">No challenger is ready for approval. This is normal while evidence builds.</div>')+
      '</div></div>';
  }
  function richFormOutcomeSection(){
    var outcome = pick('richFormOutcome') || {};
    var summary = outcome.summary || {};
    var cases = asArray(outcome.cases);
    function pct(value){
      if(value === null || value === undefined || value === '') return 'unknown';
      return String(value).replace(/\.0$/, '')+'%';
    }
    function caseCard(row){
      var pickRow = row.ourPick || {};
      var rival = row.rival || {};
      var hasRival = !!rival.horse;
      var missing = asArray(row.missingFields).slice(0,4);
      return '<div class="chart-card" style="padding:14px">'+
        '<div class="chart-title">'+raceContextHtml(row)+'</div>'+
        '<div style="font-size:14px;line-height:1.7;color:var(--text);font-weight:800;margin-bottom:8px">'+esc(row.plainEnglish || 'Rich form outcome stored for review.')+'</div>'+
        '<div class="grid grid-2" style="gap:10px">'+
          '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px;background:rgba(255,255,255,.03)">'+
            '<div style="font-family:var(--mono);font-size:11px;color:var(--muted2);text-transform:uppercase;letter-spacing:.08em">Our pick</div>'+
            '<div style="font-size:15px;line-height:1.6;color:var(--text);font-weight:800">'+esc(pickRow.horse || 'Unknown')+'</div>'+
            '<div style="font-size:13px;line-height:1.7;color:var(--muted)">Result: '+esc(pickRow.result || 'pending')+' · Form pattern: '+esc(pickRow.pattern || 'unknown')+'</div>'+
            '<div style="font-size:13px;line-height:1.7;color:var(--muted2)">Archive: '+esc(pct(pickRow.winRate))+' win · '+esc(pct(pickRow.placeRate))+' place from '+esc(pickRow.starts || 0)+' similar runs</div>'+
          '</div>'+
          '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px;background:rgba(255,255,255,.03)">'+
            '<div style="font-family:var(--mono);font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:.08em">Horse that challenged us</div>'+
            (hasRival ? '<div style="font-size:15px;line-height:1.6;color:var(--text);font-weight:800">'+esc(rival.horse)+'</div>'+
              '<div style="font-size:13px;line-height:1.7;color:var(--muted)">Result: '+esc(rival.result || 'pending')+' · Form pattern: '+esc(rival.pattern || 'unknown')+'</div>'+
              '<div style="font-size:13px;line-height:1.7;color:var(--muted2)">Archive: '+esc(pct(rival.winRate))+' win · '+esc(pct(rival.placeRate))+' place from '+esc(rival.starts || 0)+' similar runs</div>'+
              '<div style="font-size:13px;line-height:1.7;color:var(--muted2)">Extra clues: '+esc([rival.weightLbs ? rival.weightLbs+' lb' : '', rival.distance ? rival.distance+'f' : '', rival.going || '', rival.draw ? 'draw '+rival.draw : '', rival.officialRating ? 'rating '+rival.officialRating : ''].filter(Boolean).join(' · ') || 'No extra clue stored')+'</div>'
              : '<div style="font-size:13px;line-height:1.7;color:var(--muted2)">No clear richer-form rival warning was found for this pick.</div>')+
          '</div>'+
        '</div>'+
        (missing.length ? '<div style="font-size:12px;line-height:1.7;color:var(--muted2);margin-top:8px">Still missing from this check: '+esc(missing.join(', '))+'.</div>' : '')+
      '</div>';
    }
    return '<div class="lab-section"><div class="section-block-h"><h2>What beat us?</h2><span class="n">rich form review</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> this checks after racing whether the horse that beat our pick already had stronger archive evidence. It does not change picks today. It tells us whether a future warning is worth trusting.</div>'+
      '<div class="grid grid-4" style="margin-bottom:14px">'+
        card('Picks checked', '<div class="lab-count blue">'+esc(summary.official_picks_checked || 0)+'</div><div class="card-sub">official picks reviewed</div>')+
        card('Beaten picks', '<div class="lab-count">'+esc(summary.official_picks_beaten || 0)+'</div><div class="card-sub">finished behind a rival</div>')+
        card('Possible warnings', '<div class="lab-count gold">'+esc(summary.warning_candidates || 0)+'</div><div class="card-sub">stronger archive rival found</div>')+
        card('Warnings proved', '<div class="lab-count '+((summary.warnings_validated || 0) ? 'gold-pulse' : 'blue')+'">'+esc(summary.warnings_validated || 0)+'</div><div class="card-sub">rival then beat our pick</div>')+
      '</div>'+
      (cases.length ? cases.slice(0,4).map(caseCard).join('') : '<div class="empty">No rich-form outcome file is available yet. It will appear after results settle and the learning job runs.</div>')+
    '</div>';
  }
  function sqliteChallengerContext(){
    var sqliteRows = brain.challengerSummary;
    var bestSql = sqliteRows.slice().sort(function(a,b){
      return num(b.delta_vs_live_profit, 0) - num(a.delta_vs_live_profit, 0);
    })[0] || {};
    var bestId = bestSql.id || bestSql.challenger_id;
    var bestText = bestId
      ? esc(bestId)+' · '+esc(signedMoney(bestSql.delta_vs_live_profit || 0))+' vs live'
      : 'No SQLite challenger summary yet';
    return '<div class="chart-card" style="margin-bottom:16px;border-color:rgba(59,190,246,.28)">'+
      '<div class="section-block-h"><h2>SQLite challenger memory</h2><span class="n">fast summary layer</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> the lab still shows the normal paper-test detail, but the headline counts now also come from the central SQLite summary. That makes it easier to spot stale or missing challenger evidence.</div>'+
      '<div class="grid grid-3">'+
        card('Tests summarized', '<div class="lab-count blue">'+esc(brain.challengers.toLocaleString('en-GB'))+'</div><div class="card-sub">stored in SQLite</div>')+
        card('Latest summary', '<div class="card-big" style="font-size:20px;color:'+(brain.fresh?'var(--green)':'var(--gold)')+'">'+esc(brain.asOf || 'missing')+'</div><div class="card-sub">dashboard-only, no scoring impact</div>')+
        card('Best SQLite signal', '<div class="card-big" style="font-size:16px;color:var(--gold);line-height:1.45">'+bestText+'</div><div class="card-sub">paper comparison only</div>')+
      '</div>'+
    '</div>';
  }
  document.getElementById('panel-learn').innerHTML =
    '<div class="lab-warning"><strong>Challenger Lab - paper tests only</strong><span>Nothing here changes official selections, proof, ROI, results or public picks.</span></div>'+
    '<div class="plain big" style="margin-bottom:16px"><strong>Simple version:</strong> this page tells us which test ideas are worth watching, which are too early, and which should be avoided. If it is not clearly proven, it stays out of live Signal 75.</div>'+
    sqliteChallengerContext()+
    '<div class="grid grid-4" style="margin-bottom:16px">'+
      card('Live system', '<div class="card-big" style="font-size:24px;color:var(--gold)">'+esc(liveRoi)+'%</div><div class="card-sub">ROI in comparison period</div>')+
      card('Best test', best ? '<div class="card-big" style="font-size:22px;color:'+(best.deltaProfit >= 0 ? 'var(--green)' : 'var(--red)')+'">'+esc(challengerPlainText(best).title)+'</div><div class="card-sub">'+esc(signedMoney(best.deltaProfit))+' vs live</div>' : '<div class="card-big" style="font-size:22px;color:var(--muted2)">No data</div>')+
      card('Evidence depth', '<div class="lab-count blue">'+esc(maxSettled)+'</div><div class="card-sub">best proper-day sample</div>')+
      card('Ready for review', '<div class="lab-count '+(candidates.length?'gold-pulse':'')+'">'+esc(candidates.length)+'</div><div class="card-sub">'+(candidates.length?'manual review':'none')+'</div>')+
    '</div>'+
    combinedEvidenceBoard()+
    '<details class="lab-full-details"><summary>Show today’s paper picks</summary>'+liveVsChallenger()+'</details>'+ 
    '<details class="lab-full-details"><summary>Show full technical audit</summary>'+ 
      '<div class="lab-section"><div class="section-block-h"><h2>Full challenger cards</h2><span class="n">developer audit view</span></div>'+ 
        (rows.length ? rows.map(challengerCard).join('') : '<div class="card">'+trafficLight('COLLECTING','large',true)+'<div class="empty">No challenger rows are available yet.</div></div>')+ 
      '</div>'+richFormOutcomeSection()+differenceTable()+dials()+postRaceTools()+promotionQueue()+ 
    '</details>';
}

function renderRaceReview(){
  var liveReview = pick('postRaceReview') || {};
  var latestReview = pick('latestPostRaceReview') || {};
  var whatBeatUs = pick('whatBeatUs') || {};
  var margin = pick('resultMarginIntel') || {summary:{}, records:[]};
  var winners = pick('winnerIntel') || [];
  var v1Perf = pick('fieldRelativePerformance') || {};
  var perf = pick('performance') || {};
  var brain = sqliteBrain();

  function hasSettledRows(feed){
    return asArray(feed.picks).some(function(p){ return !!p && !!p.result && String(p.result).toUpperCase() !== 'PENDING'; });
  }
  var review = hasSettledRows(liveReview) ? liveReview : latestReview;
  var reviewPicks = asArray(review.picks);
  var reviewDate = review.date || latestReview.date || liveReview.date || 'latest settled day';
  function sameReviewDate(feed){
    return !!feed && !!feed.date && !!reviewDate && String(feed.date) === String(reviewDate);
  }
  var whatBeatUsCurrent = sameReviewDate(whatBeatUs);

  function ordinal(n){
    n = Number(n || 0);
    if(!n) return 'not stored';
    var mod100 = n % 100;
    if(mod100 >= 11 && mod100 <= 13) return n+'th';
    var mod10 = n % 10;
    return n + (mod10 === 1 ? 'st' : mod10 === 2 ? 'nd' : mod10 === 3 ? 'rd' : 'th');
  }
  function resultTone(result){
    result = String(result || '').toUpperCase();
    if(result === 'WON') return {label:'WON', color:'var(--green)', bg:'rgba(0,232,122,.10)'};
    if(result === 'PLACED') return {label:'PLACED', color:'var(--gold)', bg:'rgba(240,192,64,.10)'};
    if(result === 'LOST') return {label:'LOST', color:'var(--red)', bg:'rgba(255,79,119,.10)'};
    return {label:result || 'PENDING', color:'var(--muted2)', bg:'rgba(148,163,184,.08)'};
  }
  function pickName(p){ return p.name || p.horse || p.horse_name || 'Unknown horse'; }
  function pickReturn(p){ return Number(firstDefined(p.return, p.totalReturn, p.horseReturn, 0) || 0); }
  function reviewCounts(rows){
    var out = {total:rows.length, winners:0, placed:0, lost:0, warnings:0, returned:0};
    rows.forEach(function(p){
      var result = String(p.result || '').toUpperCase();
      if(result === 'WON') out.winners += 1;
      if(result === 'WON' || result === 'PLACED') out.placed += 1;
      if(result === 'LOST') out.lost += 1;
      out.warnings += asArray(p.warningEdges).length;
      out.returned += pickReturn(p);
    });
    out.returned = Math.round(out.returned * 100) / 100;
    return out;
  }
  var counts = reviewCounts(reviewPicks);
  var placeRate = counts.total ? Math.round((counts.placed / counts.total) * 100) : 0;

  function warningList(edges){
    edges = asArray(edges);
    if(!edges.length) return '<div class="card-sub">No pre-race rival warning stored for this horse.</div>';
    return edges.slice(0,3).map(function(edge){
      return '<div style="font-size:13px;line-height:1.65;color:var(--gold);margin-top:6px">'+
        esc(edge.text || ((edge.rival || 'A rival')+' had beaten this horse before.'))+
      '</div>';
    }).join('');
  }
  function officialReviewCard(p){
    var tone = resultTone(p.result);
    var winnerLine = p.winnerKnown && p.winner
      ? 'Winner: '+esc(p.winner)
      : 'Winner not stored in the compact feed yet.';
    var position = p.positionText || ordinal(p.position);
    var hadWarnings = asArray(p.warningEdges).length > 0;
    return '<div class="review-pick-card" style="border-color:'+tone.color+'55">'+
      '<div class="review-pick-main">'+
        '<div class="review-result-pill" style="color:'+tone.color+';background:'+tone.bg+'">'+tone.label+'</div>'+
        '<div class="review-pick-copy"><div class="review-horse">'+esc(pickName(p))+'</div>'+
          '<div class="review-meta">'+raceContextHtml(p, {date:reviewDate})+' · '+esc(p.section || p.race_type || 'official')+'</div></div>'+
        '<div class="review-position"><strong>'+esc(position)+'</strong><span>'+fmtGBP(pickReturn(p))+' £1 EW return</span></div>'+
      '</div>'+
      '<div class="review-simple-line">'+
        '<span>'+winnerLine+'</span>'+
        '<span class="'+(hadWarnings ? 'review-warning' : 'review-clear')+'">'+(hadWarnings ? 'Warning was visible before racing' : 'No stored rival warning before racing')+'</span>'+
      '</div>'+
      '<details class="review-detail"><summary>Show race memory</summary>'+
        '<div class="plain" style="margin-top:10px">'+esc(p.relationshipSummary || 'No race-memory relationship stored for this result yet.')+'</div>'+
        '<div class="plain" style="margin-top:10px;border-left-color:'+(hadWarnings ? 'var(--gold)' : 'var(--green)')+'">'+
          '<strong>Before-race rival warnings:</strong>'+warningList(p.warningEdges)+
        '</div>'+
      '</details>'+
    '</div>';
  }
  function dangerHorseCard(p){
    var reasons = asArray(p.reasons);
    var warnings = asArray(p.warnings);
    return '<div class="card" style="margin-bottom:10px;border-color:rgba(240,192,64,.28)">'+
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">'+
        '<div><div style="font-weight:850;font-size:16px;line-height:1.4">'+esc(p.name || 'Unknown horse')+'</div>'+
        '<div class="card-sub">'+raceContextHtml(p, {date:reviewDate})+' · score '+esc(p.score || 0)+' · odds '+esc(p.odds || 'n/a')+'</div></div>'+
        pill('rejected danger', 'gold')+
      '</div>'+
      '<div style="font-size:13px;line-height:1.75;color:var(--muted);margin-top:8px">'+
        esc((reasons.length ? reasons.join(' · ') : 'Strong signal was visible, but it did not pass the official gate.'))+
      '</div>'+
      (warnings.length ? '<div style="font-size:12px;line-height:1.7;color:var(--muted2);margin-top:8px">Warnings: '+esc(warnings.slice(0,2).join(' · '))+'</div>' : '')+
    '</div>';
  }
  function whatBeatUsCard(p){
    var warnings = asArray(p.warningEdges);
    return '<div class="card" style="margin-bottom:10px;border-color:'+(warnings.length?'rgba(240,192,64,.36)':'rgba(255,255,255,.08)')+'">'+
      '<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start">'+
        '<div><div style="font-weight:850;font-size:16px;line-height:1.4">'+esc(pickName(p))+'</div>'+
        '<div class="card-sub">'+raceContextHtml(p, {date:reviewDate})+' · finished '+esc(p.positionText || ordinal(p.position))+'</div></div>'+
        pill(String(p.result || 'review').toUpperCase(), String(p.result || '').toUpperCase() === 'LOST' ? 'red' : 'gold')+
      '</div>'+
      '<div class="plain" style="margin-top:10px">'+esc(p.relationshipSummary || 'No direct head-to-head link to the winner was found in the compact feed.')+'</div>'+
      (warnings.length ? '<div style="margin-top:10px">'+warningList(warnings)+'</div>' : '')+
    '</div>';
  }
  function marginRow(row){
    var flags = asArray(row.flags);
    var tone = flags.indexOf('WINNER') >= 0 ? 'var(--green)' : (flags.indexOf('HEAVILY_BEATEN') >= 0 ? 'var(--red)' : 'var(--gold)');
    var summary = row.distance_summary || row.result || 'stored';
    if(Number(row.position || 0) === 1 && /^Beaten 0(?:\.0)? lengths by winner/i.test(String(summary))){
      summary = Number(row.winning_margin_lengths || 0) > 0
        ? 'Won by '+row.winning_margin_lengths+' lengths'
        : '';
    }
    if(!summary) return '';
    return '<div style="display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--border-soft)">'+
      '<div style="min-width:0"><strong>'+esc(row.horse || 'Unknown')+'</strong>'+
      '<div class="card-sub">'+esc(row.date || '')+' · '+esc(row.course || '')+' '+esc(row.time || '')+'</div></div>'+
      '<div style="text-align:right;color:'+tone+';font-weight:850">'+esc(summary)+'</div>'+
    '</div>';
  }
  function winnerRow(row){
    var learning = row.learning || row.action || row.status || 'Stored for future race-memory review.';
    if(/^Beaten 0(?:\.0)? lengths by winner/i.test(String(learning))){
      learning = '';
    }
    if(!learning) return '';
    return '<div style="padding:9px 0;border-bottom:1px solid var(--border-soft)">'+
      '<strong>'+esc(row.winner || row.horse || 'Stored winner')+'</strong>'+
      '<div class="card-sub">'+esc(learning)+'</div>'+
    '</div>';
  }
  function sqliteRaceReviewContext(){
    var latest = brain.latestRaceReview || {};
    var latestDate = latest.date || latest.review_date || brain.asOf || 'not stored';
    var checked = num(firstDefined(latest.official_picks, latest.official_rows, latest.picks_reviewed, latest.picks, latest.reviewed_rows, 0), 0);
    var lost = num(firstDefined(latest.lost, latest.beaten_picks, 0), 0);
    var warnings = num(firstDefined(latest.rival_warnings, latest.warnings, 0), 0);
    return '<div class="chart-card" style="margin-bottom:16px;border-color:rgba(59,190,246,.28)">'+
      '<div class="section-block-h"><h2>SQLite race-review memory</h2><span class="n">central learning store</span></div>'+
      '<div class="plain" style="margin-bottom:12px"><strong>Plain English:</strong> this page shows the latest detailed review, while SQLite stores the running summary so we can quickly see whether beaten-horse and rival-warning learning is being collected.</div>'+
      '<div class="grid grid-4">'+
        card('Review days stored', '<div class="lab-count blue">'+esc(brain.races.toLocaleString('en-GB'))+'</div><div class="card-sub">settled days summarized</div>')+
        card('Latest SQLite day', '<div class="card-big" style="font-size:20px;color:'+(brain.fresh?'var(--green)':'var(--gold)')+'">'+esc(latestDate)+'</div><div class="card-sub">summary table date</div>')+
        card('Latest picks checked', '<div class="lab-count">'+esc(checked)+'</div><div class="card-sub">'+esc(lost)+' beaten or lost</div>')+
        card('Stored warnings', '<div class="lab-count gold">'+esc(warnings)+'</div><div class="card-sub">pre-race rival flags</div>')+
      '</div>'+
    '</div>';
  }
  var beatOfficial = whatBeatUsCurrent ? asArray(whatBeatUs.official) : [];
  var beatV1 = whatBeatUsCurrent ? asArray(whatBeatUs.v1) : [];
  var dangerHorses = asArray(review.dangerHorses);
  var marginRows = asArray(margin.records).slice(0,6);
  var winnerRows = asArray(winners).slice(0,5);
  var liveRoi = firstDefined(perf.roi, 'checking');
  var v1Roi = firstDefined(v1Perf.roi, v1Perf.paperRoi, 'collecting');
  function dayVerdict(){
    if(!counts.total) return {tone:'blue', title:'No settled review yet', text:'The post-race review will appear after results are stored.'};
    if(counts.placed === counts.total) return {tone:'green', title:'Good day', text:'Every official pick placed or won.'};
    if(counts.placed > 0) return {tone:'gold', title:'Mixed day', text:'Some picks returned money, but at least one did not place.'};
    return {tone:'red', title:'Tough day', text:'None of the official picks placed. This is learning-only; proof and ROI come from the result files.'};
  }
  var verdict = dayVerdict();
  var staleBeatNote = whatBeatUsCurrent ? '' : '<div class="plain" style="margin-top:12px;border-left-color:var(--gold)"><strong>Note:</strong> older “What beat us?” cards were hidden because their feed is dated '+esc(whatBeatUs.date || 'unknown')+', not '+esc(reviewDate)+'.</div>';

  document.getElementById('panel-ask').innerHTML =
    '<div class="section-hero confirm review-hero"><div><div class="hero-kicker">Post-race review</div><div class="section-hero-title">Race Review</div><div class="section-hero-copy">Plain-English review of the latest settled official picks. It shows the result first, then the evidence only if you want to open it.</div></div>'+
      '<div class="hero-stat">'+scoreChip(counts.total || '0', 'PICKS', 'var(--blue)')+'</div></div>'+
    sqliteRaceReviewContext()+
    '<div class="review-verdict review-'+verdict.tone+'">'+
      '<div><div class="review-verdict-kicker">Reviewed day · '+esc(reviewDate)+'</div>'+
        '<div class="review-verdict-title">'+esc(verdict.title)+'</div>'+
        '<div class="review-verdict-copy">'+esc(verdict.text)+'</div></div>'+
      '<div class="review-verdict-stats">'+
        '<div><strong>'+esc(counts.winners)+'</strong><span>winners</span></div>'+
        '<div><strong>'+esc(counts.placed)+'</strong><span>placed</span></div>'+
        '<div><strong>'+esc(counts.lost)+'</strong><span>lost</span></div>'+
        '<div><strong>'+esc(placeRate)+'%</strong><span>place rate</span></div>'+
      '</div>'+
    '</div>'+
    '<div class="review-proof-strip">'+
      '<div><span>Live proof ROI</span><strong>'+esc(liveRoi)+'%</strong><small>'+esc(perf.bettingDays || 0)+' official betting days</small></div>'+
      '<div><span>V1 paper ROI</span><strong>'+esc(v1Roi)+(String(v1Roi).match(/^[0-9.-]+$/) ? '%' : '')+'</strong><small>comparison only</small></div>'+
      '<div><span>Rival warnings</span><strong>'+esc(counts.warnings)+'</strong><small>visible before racing</small></div>'+
    '</div>'+
    '<div class="section-block-h"><h2>Official picks</h2><span class="n">latest settled day</span></div>'+
    (reviewPicks.length ? reviewPicks.map(officialReviewCard).join('') : '<div class="card"><div class="empty">No settled post-race review is available yet. This appears after results and learning files are published.</div></div>')+
    '<details class="review-advanced"><summary>Show learning detail</summary>'+
      staleBeatNote+
      '<div class="section-block-h" style="margin-top:18px"><h2>Rejected danger horses</h2><span class="n">same races</span></div>'+
      (dangerHorses.length ? dangerHorses.map(dangerHorseCard).join('') : '<div class="card"><div class="card-sub">No rejected danger horses were found in the latest reviewed races.</div></div>')+
      '<div class="grid grid-2" style="margin-top:18px">'+
        '<div><div class="section-block-h"><h2>What beat us?</h2><span class="n">rival warnings</span></div>'+
          (beatOfficial.length ? beatOfficial.map(whatBeatUsCard).join('') : '<div class="card"><div class="card-sub">No current official beaten-horse review is stored yet.</div></div>')+
        '</div>'+
        '<div><div class="section-block-h"><h2>V1 comparison</h2><span class="n">paper only</span></div>'+
          (beatV1.length ? beatV1.slice(0,5).map(whatBeatUsCard).join('') : '<div class="card"><div class="card-sub">No current V1 post-race comparison is stored yet.</div></div>')+
        '</div>'+
      '</div>'+
      '<div class="grid grid-2" style="margin-top:18px">'+
        card('Winning margin notes', marginRows.length ? marginRows.map(marginRow).join('') : '<div class="card-sub">No margin notes are available yet.</div>')+
        card('Recent winner intelligence', winnerRows.length ? winnerRows.map(winnerRow).join('') : '<div class="card-sub">Winner intelligence appears after the nightly learning run.</div>')+
      '</div>'+
    '</details>'+
    '<div class="plain" style="margin-top:16px;border-left-color:var(--blue)"><strong>Important:</strong> official proof, ROI and public results still come from the results/proof files, not this learning screen.</div>';
}

function renderAskSignal(){
  var suggestionGroups = [
    {title:'Today&apos;s picks', items:[
      'Why were today&apos;s horses picked?',
      'Explain today&apos;s official selections',
      'Which pick looks strongest today?',
      'Which pick has the most warnings?',
      'What is today&apos;s bet type?',
      'Is today a Single, Double or Patent?',
      'Why is this no-bet day?',
      'Which horses nearly made it?',
      'Why did the watchlist horses miss out?',
      'What was blocked today?',
      'Which pick has the best price?',
      'Which pick has the highest score?',
      'Which pick has the most tipsters?',
      'Are today&apos;s picks all in different races?'
    ]},
    {title:'Today&apos;s picks: rich form archive', items:[
      'What does the rich form archive say about today&apos;s picks?',
      'Show similar-form evidence for official picks',
      'Which pick has the strongest similar-form record?',
      'Which pick has the weakest similar-form record?',
      'Which pick has the best archive win rate?',
      'Which pick has the best archive place rate?',
      'Which pick has the biggest archive sample size?',
      'Do any picks have poor similar-form records?',
      'Do any picks have strong similar-form records?',
      'Are today&apos;s picks supported by similar form data?',
      'Which pick has the safest archive form pattern?',
      'Which pick has the riskiest archive form pattern?',
      'How often do today&apos;s pick form patterns win?',
      'How often do today&apos;s pick form patterns place?',
      'Is the rich form data changing today&apos;s picks?'
    ]},
    {title:'Horse lookup', items:[
      'Who beat [horse] last time out?',
      'Who did [horse] beat last time out?',
      'Show [horse] race history',
      'What is [horse]&apos;s recent form?',
      'What was [horse]&apos;s last stored race?',
      'Show [horse]&apos;s today context'
    ]},
    {title:'Rival memory', items:[
      'What rival history exists today?',
      'Has any pick beaten today&apos;s rivals before?',
      'Has any rival beaten our picks before?',
      'Which horse has the strongest race memory?',
      'Which pick has no rival evidence?',
      'Show me top 3 market rival evidence',
      'Show me rival warnings today',
      'Does race memory support today&apos;s picks?',
      'Which rivals have beaten our horses before?',
      'Which horses have beaten favourites before?',
      'Are any warnings against top three market rivals?'
    ]},
    {title:'Form and risk', items:[
      'Show me form warnings today',
      'Which horses have poor recent form?',
      'Which official pick has a form caution?',
      'Which horse has the safest form?',
      'Which horse has zero tipsters?',
      'Which pick has outside evidence?',
      'Are any picks risky today?',
      'What protection gates blocked horses?',
      'Which horses failed the form gate?',
      'Which horses failed the price gate?',
      'Which horses failed the score gate?'
    ]},
    {title:'Challenger Lab', items:[
      'Which challenger is closest to working?',
      'What is the difference between live and challenger picks?',
      'What is Overlay Fix testing?',
      'What is Tipster Quality testing?',
      'What is Rival History testing?',
      'What is Combined testing?',
      'Which challenger is improving?',
      'Which challenger is risky?',
      'Is anything ready to go live?',
      'What are we waiting for before changing rules?',
      'Which challenger picked different horses today?',
      'Did the live system beat the challengers today?'
    ]},
    {title:'Results and learning', items:[
      'How are results and ROI doing?',
      'What was the latest official result?',
      'How many winners do we have?',
      'What is the place rate?',
      'What has the system learned this week?',
      'Which learning warnings are active?',
      'Has the field graph been predictive?',
      'What evidence is still collecting?',
      'Which patterns are monitor only?',
      'What did yesterday teach the system?'
    ]},
    {title:'System and data', items:[
      'What data is being used?',
      'How many head-to-head records are available?',
      'Is SQLite being used?',
      'When was the dashboard updated?',
      'Are picks and results read-only here?',
      'What files power this page?',
      'Does anything here affect live picks?',
      'Is any paid AI being used?',
      'Is the dashboard using fresh data?',
      'When did the dashboard feed last refresh?',
      'Is the dashboard private?'
    ]}
  ];
  function qButton(q){
    var raw = q.replace(/&apos;/g, "'");
    return '<button type="button" data-question="'+esc(raw)+'" style="border:1px solid rgba(255,255,255,.10);background:rgba(255,255,255,.04);color:var(--text);border-radius:var(--r-sm);padding:10px 12px;text-align:left;font-size:13px;line-height:1.5;cursor:pointer" onclick="window.S75ui.askSignal(this.getAttribute(\'data-question\'))">'+q+'</button>';
  }
  function suggestionGroup(group){
    return '<div style="border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025);border-radius:var(--r-md);padding:12px">'+
      '<div style="font-family:var(--mono);font-size:11px;line-height:1.6;color:var(--gold);text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px">'+group.title+'</div>'+
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px">'+group.items.map(qButton).join('')+'</div>'+
    '</div>';
  }
  document.getElementById('panel-ask').innerHTML =
    '<div class="section-hero confirm"><div><div class="hero-kicker">Read-only question page</div><div class="section-hero-title">Ask Signal 75</div><div class="section-hero-copy">Ask plain-English questions about today&apos;s picks, rival memory, challenger tests, results and learning evidence. This page only reads dashboard data. It cannot change picks, scores, results or proof.</div></div>'+
      '<div class="hero-stat">'+scoreChip('Q', 'LOCAL', 'var(--blue)')+'</div></div>'+
    '<div class="plain big" style="margin:16px 0"><strong>For Deb:</strong> this is the simple question page. Instead of reading every chart, you can ask what you want to know and Signal 75 explains it from the data already on this Mac.</div>'+
    '<div class="chart-card" style="margin-bottom:16px"><div class="chart-title">Ask a question</div>'+
      '<div style="display:flex;gap:10px;align-items:stretch;flex-wrap:wrap">'+
        '<input id="ask-signal-input" type="text" placeholder="Example: why was today&apos;s pick selected?" onkeydown="if(event.key===\'Enter\') window.S75ui.askSignal()" style="flex:1;min-width:260px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.04);color:var(--text);border-radius:var(--r-sm);padding:12px 14px;font-size:14px;line-height:1.5;outline:none">'+
        '<button type="button" onclick="window.S75ui.askSignal()" style="border:1px solid rgba(240,192,64,.35);background:rgba(240,192,64,.12);color:var(--gold);border-radius:var(--r-sm);padding:12px 16px;font-weight:800;cursor:pointer">Ask</button>'+
      '</div>'+
      '<div id="ask-signal-answer" style="margin-top:14px;border:1px solid rgba(0,232,122,.26);border-left:3px solid var(--green);background:rgba(0,232,122,.055);border-radius:0 var(--r-sm) var(--r-sm) 0;padding:14px 16px;min-height:92px"><div class="chart-title" style="color:var(--green)">Answer</div><div style="font-size:14px;line-height:1.8;color:var(--green)">Choose a question above or type your own. Start with “Why were today&apos;s horses picked?”</div></div>'+
      '<div style="display:grid;grid-template-columns:1fr;gap:12px;margin-top:14px">'+suggestionGroups.map(suggestionGroup).join('')+'</div>'+
    '</div>'+
    '<div class="grid grid-3" style="margin-top:16px">'+
      card('What it can answer', '<div class="card-sub" style="font-size:13px;line-height:1.8">Today&apos;s picks, near misses, blocked horses, rival history, challenger tests, learning notes and results.</div>')+
      card('What it cannot do', '<div class="card-sub" style="font-size:13px;line-height:1.8">It cannot place a bet, change a score, promote a challenger or edit proof files.</div>')+
      card('How it works', '<div class="card-sub" style="font-size:13px;line-height:1.8">It matches your question to trusted local dashboard files. No paid AI call is used.</div>')+
    '</div>';
}

function askSignal(question){
  var input = document.getElementById('ask-signal-input');
  var q = String(question || (input ? input.value : '') || '').trim();
  if(input && question) input.value = question.replace(/&apos;/g, "'");
  var out = document.getElementById('ask-signal-answer');
  if(!out) return;
  function answer(title, body, source){
    var cleanTitle = String(title || '').replace(/&apos;/g, "'");
    out.innerHTML = '<div class="chart-title" style="color:var(--green)">'+esc(cleanTitle)+'</div>'+
      '<div style="font-size:14px;line-height:1.8;color:var(--green)">'+body+'</div>'+
      '<div style="font-family:var(--mono);font-size:12px;line-height:1.7;color:var(--muted2);margin-top:14px;border-top:1px solid rgba(0,232,122,.16);padding-top:10px">Data used: '+esc(source || 'dashboard local feed')+'</div>';
  }
  function listRows(rows){
    if(!rows.length) return '<div class="empty">No matching rows found in the current dashboard feed.</div>';
    return rows.map(function(row){
      return '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px 12px;margin:8px 0;background:rgba(255,255,255,.03)">'+row+'</div>';
    }).join('');
  }
  function runnerWarnings(){
    var rv = pick('raceView') || {};
    var rows = [];
    asArray(rv.races).forEach(function(race){
      asArray(race.runners).forEach(function(r){
        var warnings = asArray(r.warnings);
        if(warnings.length){
          rows.push('<strong>'+esc(r.name)+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+raceContextHtml(r, Object.assign({date:rv.date}, race))+' · '+esc(warnings.join(' · '))+'</div>');
        }
      });
    });
    return rows;
  }
  function officialQuestionRows(){
    var official = pick('officialPicks') || [];
    return official.map(function(p){
      return {
        name:p.name,
        course:p.course,
        time:p.time,
        odds:Number(p.odds || 0),
        score:Number(firstDefined(p.score, p.signal_score, 0)),
        tipsters:Number(firstDefined(p.tipsters, p.tip_count, 0)),
        warnings:asArray(p.warnings),
        raw:p
      };
    });
  }
  function officialMiniRow(p, note){
    var bits = [];
    if(p.course || p.time || p.date) bits.push(raceContextHtml(p));
    if(p.score) bits.push('score '+esc(p.score));
    if(p.odds) bits.push('odds '+esc(p.odds));
    if(p.tipsters || p.tipsters === 0) bits.push(esc(p.tipsters)+' tipsters');
    return '<strong>'+esc(p.name)+'</strong><div style="font-size:13px;color:var(--muted);line-height:1.7">'+bits.join(' · ')+'</div>'+(note ? '<div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px">'+note+'</div>' : '');
  }
  function officialMetricAnswer(kind){
    var rows = officialQuestionRows();
    if(!rows.length){
      return {title:'No official bet today', body:'<div>No horse passed every live rule, so Signal 75 has no official bet today.</div>', source:'officialPicks'};
    }
    var chosen = rows[0], title = 'Today&apos;s official selections', note = '';
    if(kind === 'score'){
      chosen = rows.slice().sort(function(a,b){ return b.score - a.score; })[0];
      title = 'Highest score today';
      note = 'This is the official pick with the highest Signal 75 score.';
    } else if(kind === 'price'){
      chosen = rows.slice().sort(function(a,b){ return b.odds - a.odds; })[0];
      title = 'Best price today';
      note = 'This is the biggest price among today&apos;s official picks, not a separate recommendation.';
    } else if(kind === 'tipsters'){
      chosen = rows.slice().sort(function(a,b){ return b.tipsters - a.tipsters; })[0];
      title = 'Most tipster support today';
      note = 'This is the official pick with the most visible tipster support in the dashboard feed.';
    } else if(kind === 'warnings'){
      chosen = rows.slice().sort(function(a,b){ return b.warnings.length - a.warnings.length; })[0];
      title = 'Most warnings today';
      note = chosen.warnings.length ? 'Warnings: '+esc(chosen.warnings.join(' · ')) : 'No official pick has a dashboard warning listed.';
    } else if(kind === 'races'){
      var raceKeys = {};
      rows.forEach(function(p){ raceKeys[cleanKey(p.course)+'|'+String(p.time || '')] = true; });
      title = 'Same-race check';
      note = Object.keys(raceKeys).length === rows.length ? 'Yes. Today&apos;s official selections are all in different races.' : 'No. At least two official selections appear to share a race in the current feed.';
      return {title:title, body:'<div>'+note+'</div>'+listRows(rows.map(function(p){ return officialMiniRow(p); })), source:'officialPicks and raceView'};
    }
    return {title:title, body:listRows([officialMiniRow(chosen, note)]), source:'officialPicks'};
  }
  function richFormOfficialRows(){
    var official = officialQuestionRows();
    var feed = pick('richForm') || {};
    var richRows = asArray(feed.rows);
    return official.map(function(p){
      var target = cleanKey(p.name)+'|'+cleanKey(p.course)+'|'+String(p.time || '');
      var fallback = null;
      var rich = null;
      richRows.some(function(row){
        var key = cleanKey(row.name)+'|'+cleanKey(row.course)+'|'+String(row.time || '');
        if(key === target){ rich = row; return true; }
        if(!fallback && cleanKey(row.name) === cleanKey(p.name)) fallback = row;
        return false;
      });
      rich = rich || fallback || {};
      var stat = rich.patternStats || {};
      return {
        name:p.name,
        course:p.course,
        time:p.time,
        odds:p.odds,
        score:p.score,
        form:rich.form || p.raw.form || '',
        pattern:rich.pattern || '',
        label:stat.label || 'No similar-form archive match',
        tone:String(stat.tone || 'missing'),
        starts:Number(stat.starts || 0),
        wins:Number(stat.wins || 0),
        places:Number(stat.places || 0),
        winRate:Number(stat.winRate || 0),
        placeRate:Number(stat.placeRate || 0),
        plain:stat.plainEnglish || 'No rich form pattern evidence is available for this pick in the compact dashboard feed.',
        matched:!!rich.matched
      };
    });
  }
  function richFormMiniRow(row, note){
    var toneColor = row.tone === 'good' ? 'var(--green)' : (row.tone === 'poor' ? 'var(--gold)' : 'var(--muted)');
    var bits = [];
    if(row.course || row.time || row.date) bits.push(raceContextHtml(row));
    if(row.form) bits.push('form '+esc(row.form));
    if(row.pattern) bits.push('pattern '+esc(row.pattern));
    if(row.starts) bits.push(esc(row.starts)+' examples');
    return '<strong>'+esc(row.name)+'</strong>'+
      '<div style="font-size:13px;color:var(--muted);line-height:1.7">'+bits.join(' · ')+'</div>'+
      '<div style="font-size:13px;color:'+toneColor+';line-height:1.7;margin-top:4px">'+esc(row.label)+'</div>'+
      '<div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px">'+esc(row.plain)+'</div>'+
      (note ? '<div style="font-size:13px;color:var(--green);line-height:1.7;margin-top:4px">'+note+'</div>' : '');
  }
  function richFormAnswer(kind){
    var rows = richFormOfficialRows();
    var feed = pick('richForm') || {};
    if(!rows.length){
      return {title:'Rich form archive', body:'<div>No official picks are available for a rich-form check today.</div>', source:'richForm and officialPicks'};
    }
    var matched = rows.filter(function(row){ return row.matched && row.starts > 0; });
    if(kind === 'impact'){
      return {
        title:'Rich form data impact',
        body:'<div>The rich form archive is <strong>not changing today&apos;s picks</strong>. It is dashboard evidence only.</div><div style="margin-top:8px">Use it to spot confidence warnings and support before we test any live rule in Challenger Lab.</div>',
        source:'richForm'
      };
    }
    if(!matched.length){
      return {
        title:'Rich form archive',
        body:listRows(rows.map(function(row){ return richFormMiniRow(row); })),
        source:'richForm and officialPicks'
      };
    }
    var title = 'Rich form archive for today&apos;s picks';
    var selectedRows = matched;
    if(kind === 'best_win' || kind === 'strongest' || kind === 'safest'){
      selectedRows = [matched.slice().sort(function(a,b){ return b.winRate - a.winRate || b.placeRate - a.placeRate || b.starts - a.starts; })[0]];
      title = kind === 'best_win' ? 'Best archive win rate' : (kind === 'safest' ? 'Safest archive form pattern' : 'Strongest similar-form record');
    } else if(kind === 'best_place'){
      selectedRows = [matched.slice().sort(function(a,b){ return b.placeRate - a.placeRate || b.winRate - a.winRate || b.starts - a.starts; })[0]];
      title = 'Best archive place rate';
    } else if(kind === 'sample'){
      selectedRows = [matched.slice().sort(function(a,b){ return b.starts - a.starts; })[0]];
      title = 'Biggest archive sample size';
    } else if(kind === 'poor' || kind === 'weakest' || kind === 'riskiest'){
      selectedRows = matched.filter(function(row){ return row.tone === 'poor'; });
      if(!selectedRows.length) selectedRows = [matched.slice().sort(function(a,b){ return a.winRate - b.winRate || a.placeRate - b.placeRate; })[0]];
      title = kind === 'poor' ? 'Poor similar-form records' : (kind === 'riskiest' ? 'Riskiest archive form pattern' : 'Weakest similar-form record');
    } else if(kind === 'good' || kind === 'supported'){
      selectedRows = matched.filter(function(row){ return row.tone === 'good'; });
      title = kind === 'good' ? 'Strong similar-form records' : 'Similar-form support check';
      if(!selectedRows.length){
        return {
          title:title,
          body:'<div>No official pick is marked as a strong similar-form archive match today.</div>'+listRows(matched.map(function(row){ return richFormMiniRow(row); })),
          source:'richForm and officialPicks'
        };
      }
    } else if(kind === 'win_rates'){
      title = 'Archive win rates for today&apos;s pick form patterns';
      selectedRows = matched.slice().sort(function(a,b){ return b.winRate - a.winRate; });
    } else if(kind === 'place_rates'){
      title = 'Archive place rates for today&apos;s pick form patterns';
      selectedRows = matched.slice().sort(function(a,b){ return b.placeRate - a.placeRate; });
    }
    var summary = '<div style="margin-bottom:10px">Rich form matched '+esc(matched.length)+' of '+esc(rows.length)+' official pick'+(rows.length === 1 ? '' : 's')+'. Today&apos;s full dashboard feed matched '+esc(feed.matchedCount || 0)+' of '+esc(feed.runnerCount || 0)+' runners.</div>';
    return {
      title:title,
      body:summary+listRows(selectedRows.map(function(row){ return richFormMiniRow(row); }))+
        '<div style="font-size:13px;line-height:1.7;color:var(--muted2);margin-top:10px">Display only. No live score, pick or proof change.</div>',
      source:'richForm, officialPicks'
    };
  }
  function betTypeAnswer(){
    var sections = officialBetSections();
    var live = sections.filter(function(s){ return s.picks.length; });
    if(!live.length){
      return {
        title:'No bet today',
        body:'<div>No official selections passed every rule, so Signal 75 stays out today.</div>',
        source:'officialPicks'
      };
    }
    return {
      title:'Today&apos;s bet type',
      body:listRows(live.map(function(s){
        return '<strong>'+esc(s.name)+' '+esc(s.model.shortLabel)+'</strong><div style="font-size:13px;color:var(--muted);line-height:1.7">'+esc(s.model.count)+' pick'+(s.model.count === 1 ? '' : 's')+' · '+esc(fmtGBP(s.model.stake))+' stake · '+esc(s.model.lines)+' lines</div><div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px">'+esc(s.model.explanation)+'</div>';
      })),
      source:'officialPicks and bet model'
    };
  }
  function gatesAnswer(kind){
    var runners = allRaceRunners();
    var rows = runners.filter(function(r){
      var reasons = (r.officialRejectionReasons || r.rejectionReasons || r.warnings || []).join(' ').toLowerCase();
      var odds = Number(r.odds || 0);
      var score = Number(r.score || r.signal_score || 0);
      if(kind === 'form') return reasons.indexOf('form') >= 0 || (r.warnings || []).join(' ').toLowerCase().indexOf('form') >= 0;
      if(kind === 'price') return reasons.indexOf('odds') >= 0 || reasons.indexOf('price') >= 0 || (odds && (odds < 2.75 || odds > 8));
      if(kind === 'score') return reasons.indexOf('score') >= 0 || (score > 0 && score < 75);
      return reasons.length;
    }).slice(0, 12);
    return {
      title:kind === 'form' ? 'Horses blocked or warned by form' : (kind === 'price' ? 'Horses blocked by price' : 'Horses below the score gate'),
      body:listRows(rows.map(function(r){
        var reason = (r.officialRejectionReasons || r.rejectionReasons || r.warnings || []).join(' · ') || 'Matched this gate check in the dashboard feed.';
        return '<strong>'+esc(r.name)+'</strong><div style="font-size:13px;color:var(--muted);line-height:1.7">'+raceContextHtml(r)+' · score '+esc(firstDefined(r.score, r.signal_score, '?'))+' · odds '+esc(r.odds || '?')+'</div><div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px">'+esc(reason)+'</div>';
      })),
      source:'raceView warnings and rejection reasons'
    };
  }
  function challengerExplanationAnswer(){
    var text = '';
    if(lower.indexOf('overlay') >= 0) text = '<strong>Overlay Fix</strong><div>Already live. It only counts a past rival when that rival is actually running today.</div>';
    else if(lower.indexOf('tipster quality') >= 0) text = '<strong>Tipster Quality</strong><div>Tests whether better trusted sources matter more than a raw count of tips.</div>';
    else if(lower.indexOf('rival history') >= 0) text = '<strong>Rival History</strong><div>Tests whether horse-vs-horse history against today&apos;s field improves the paper picks.</div>';
    else if(lower.indexOf('combined') >= 0) text = '<strong>Combined</strong><div>Tests the field-aware fix plus the fuller rival-history view together.</div>';
    else if(lower.indexOf('waiting') >= 0 || lower.indexOf('changing rules') >= 0 || lower.indexOf('go live') >= 0) text = '<strong>Before anything goes live</strong><div>We need enough settled days, positive results against live picks, no obvious risk pattern, and John approval. Nothing promotes itself.</div>';
    else text = '<strong>Challenger Lab</strong><div>It runs paper tests beside live Signal 75 so we can see what would have changed without affecting picks or proof.</div>';
    return {title:'Challenger explanation', body:'<div>'+text+'</div>', source:'challenger dashboard explanations'};
  }
  function learningAnswer(){
    var evidence = pick('learningEvidence') || {};
    var items = asArray(evidence.items).slice(0, 8);
    if(lower.indexOf('field graph') >= 0){
      var fg = pick('fieldGraph') || {};
      return {title:'Field graph evidence', body:'<div>The dashboard has '+esc(fg.edgeCount || 0)+' rival-history checks in the current feed. This is still learning/support evidence unless a specific approved rule uses it.</div>', source:'fieldGraph'};
    }
    return {
      title:'Learning evidence',
      body:listRows(items.map(function(item){
        return '<strong>'+esc(item.label || item.code)+'</strong><div style="font-size:13px;color:var(--muted);line-height:1.7">'+esc(item.count || 0)+' cases · '+esc(item.currentAction || 'Monitor only')+'</div><div style="font-size:13px;color:var(--text);line-height:1.7;margin-top:4px">'+esc(item.plainMeaning || 'Stored for review. No automatic live change.')+'</div>';
      })),
      source:'learningEvidence and continuousLearning'
    };
  }
  function systemAnswer(){
    var ready = pick('dashboardReady') || {};
    var dbRows = sqliteHeadToHeadRowsLabel();
    var parts = [];
    if(lower.indexOf('paid ai') >= 0) parts.push('<strong>No paid AI answer is used here.</strong><div>The Ask page uses fixed local dashboard checks, not an OpenAI/Anthropic call.</div>');
    if(lower.indexOf('private') >= 0) parts.push('<strong>Private dashboard.</strong><div>This page is designed for the protected local Signal 75 system, not the public website.</div>');
    if(lower.indexOf('fresh') >= 0 || lower.indexOf('refresh') >= 0 || lower.indexOf('updated') >= 0) parts.push('<strong>Dashboard feed.</strong><div>Last local marker: '+esc(ready.generated_at || 'checking')+'.</div>');
    if(lower.indexOf('affect') >= 0 || lower.indexOf('read-only') >= 0) parts.push('<strong>Read-only.</strong><div>Nothing on this page changes picks, scores, proof, results or ROI.</div>');
    if(lower.indexOf('sqlite') >= 0 || lower.indexOf('head-to-head') >= 0) parts.push('<strong>SQLite memory.</strong><div>'+esc(dbRows)+' head-to-head rows are visible in the dashboard status feed.</div>');
    if(!parts.length) parts.push('<strong>Data sources.</strong><div>Official picks, race view, field graph, challenger lab, learning evidence, results and compact horse lookup.</div>');
    return {title:'System and data', body:listRows(parts), source:'dashboardReady, dbStatus and local feeds'};
  }
  function horseLookupData(){
    return pick('horseLookup') || {};
  }
  function findHorseLookup(query){
    var data = horseLookupData();
    var horses = data.horses || {};
    var cleaned = cleanKey(query);
    var best = null;
    Object.keys(horses).forEach(function(key){
      var row = horses[key] || {};
      var name = row.name || key;
      var nameKey = cleanKey(name);
      if(!nameKey) return;
      if(cleaned === nameKey || cleaned.indexOf(nameKey) >= 0 || nameKey.indexOf(cleaned) >= 0){
        if(!best || nameKey.length > cleanKey(best.name || '').length) best = row;
      }
    });
    return best;
  }
  function likelyHorseQuestion(text){
    var words = ['last time', 'last run', 'last race', 'last stored race', 'today context', 'who beat', 'beat last', 'beaten last', 'recent form', 'race history'];
    return words.some(function(w){ return text.indexOf(w) >= 0; });
  }
  function horseLookupAnswer(query){
    if(query.indexOf('[horse]') >= 0){
      return {
        title:'Horse lookup',
        body:'<div>Replace <strong>[horse]</strong> with the horse name you want to check.</div><div style="margin-top:8px">Example format: <strong>Who beat [horse] last time out?</strong></div><div style="margin-top:8px">This lookup works for horses in the current dashboard feed.</div>',
        source:'horseLookup'
      };
    }
    var row = findHorseLookup(query);
    if(!row) return null;
    var race = row.lastRace || {};
    var current = row.current || {};
    var beatenBy = asArray(row.beatenBy);
    var beat = asArray(row.beat);
    var lines = [];
    var raceLine = [race.date, race.course, race.time, race.race].filter(Boolean).join(' · ');
    if(raceLine){
      lines.push('<div style="font-size:15px;line-height:1.8;color:var(--text)"><strong>Last stored race:</strong> '+esc(raceLine)+'</div>');
    }
    var detailBits = [];
    if(race.horsePosition) detailBits.push('finished '+race.horsePosition);
    if(race.horseBsp) detailBits.push('BSP '+race.horseBsp);
    if(race.distanceFurlongs) detailBits.push(race.distanceFurlongs+'f');
    if(race.going) detailBits.push('going '+race.going);
    if(race.raceType) detailBits.push(race.raceType);
    if(detailBits.length){
      lines.push('<div style="font-size:13px;line-height:1.8;color:var(--muted)">'+esc(detailBits.join(' · '))+'</div>');
    }
    if(beatenBy.length){
      lines.push('<div style="margin-top:12px;font-weight:850;color:var(--amber);font-size:15px;line-height:1.7">Horses that beat '+esc(row.name)+' last time:</div>');
      lines.push(listRows(beatenBy.map(function(item){
        var bits = [];
        if(item.position) bits.push('position '+item.position);
        if(item.bsp) bits.push('BSP '+item.bsp);
        return '<strong>'+esc(item.horse)+'</strong><div style="font-size:13px;color:var(--muted);line-height:1.7">'+esc(bits.join(' · ') || item.note || 'finished ahead')+'</div>';
      })));
    } else if(beat.length){
      lines.push('<div style="margin-top:12px;font-weight:850;color:var(--green);font-size:15px;line-height:1.7">'+esc(row.name)+' was not beaten in that stored race.</div>');
      lines.push('<div style="font-size:13px;color:var(--muted);line-height:1.8">It finished ahead of '+esc(beat.slice(0,5).map(function(item){ return item.horse; }).join(', '))+(beat.length > 5 ? ' and others' : '')+'.</div>');
    } else {
      lines.push('<div class="empty" style="margin-top:12px">No finished-ahead list is available for this horse in the compact dashboard lookup yet.</div>');
    }
    var currentBits = [];
    if(current.form) currentBits.push('form '+current.form);
    if(current.weight) currentBits.push('weight '+current.weight);
    if(current.jockey) currentBits.push('jockey '+current.jockey);
    if(current.trainer) currentBits.push('trainer '+current.trainer);
    if(current.distance) currentBits.push('today '+current.distance);
    if(currentBits.length){
      lines.push('<div style="margin-top:14px;padding:10px 12px;background:rgba(255,255,255,.035);border-radius:var(--r-sm);font-size:13px;line-height:1.8;color:var(--muted)"><strong style="color:var(--text)">Today&apos;s context:</strong> '+esc(currentBits.join(' · '))+'</div>');
    }
    return {
      title:'Horse lookup: '+row.name,
      body:lines.join(''),
      source:'horseLookup, SQLite head-to-head summary, raceView'
    };
  }
  var lower = q.toLowerCase();
  if(!q){
    answer('Ask Signal 75', '<div class="empty">Type a question or choose one of the buttons above.</div>', 'none');
    return;
  }
  if(lower.indexOf('rich form') >= 0 || lower.indexOf('similar-form') >= 0 ||
     lower.indexOf('similar form') >= 0 || lower.indexOf('archive form') >= 0 ||
     lower.indexOf('archive win') >= 0 || lower.indexOf('archive place') >= 0 ||
     lower.indexOf('form pattern') >= 0 || lower.indexOf('pick form patterns') >= 0){
    var richKind = 'all';
    if(lower.indexOf('changing') >= 0 || lower.indexOf('impact') >= 0) richKind = 'impact';
    else if(lower.indexOf('weakest') >= 0) richKind = 'weakest';
    else if(lower.indexOf('riskiest') >= 0) richKind = 'riskiest';
    else if(lower.indexOf('poor') >= 0) richKind = 'poor';
    else if(lower.indexOf('strongest') >= 0) richKind = 'strongest';
    else if(lower.indexOf('strong') >= 0) richKind = 'good';
    else if(lower.indexOf('supported') >= 0 || lower.indexOf('support') >= 0) richKind = 'supported';
    else if(lower.indexOf('best archive win') >= 0) richKind = 'best_win';
    else if(lower.indexOf('best archive place') >= 0) richKind = 'best_place';
    else if(lower.indexOf('win rate') >= 0 || lower.indexOf('patterns win') >= 0) richKind = 'win_rates';
    else if(lower.indexOf('place rate') >= 0 || lower.indexOf('patterns place') >= 0) richKind = 'place_rates';
    else if(lower.indexOf('sample') >= 0) richKind = 'sample';
    else if(lower.indexOf('safest') >= 0) richKind = 'safest';
    var richAnswer = richFormAnswer(richKind);
    answer(richAnswer.title, richAnswer.body, richAnswer.source);
    return;
  }
  if(likelyHorseQuestion(lower)){
    var horseAnswer = horseLookupAnswer(q);
    if(horseAnswer){
      answer(horseAnswer.title, horseAnswer.body, horseAnswer.source);
      return;
    }
  }
  if(lower.indexOf('bet type') >= 0 || lower.indexOf('single') >= 0 || lower.indexOf('double') >= 0 ||
     lower.indexOf('patent') >= 0 || lower.indexOf('no-bet') >= 0 || lower.indexOf('no bet') >= 0){
    var betAnswer = betTypeAnswer();
    answer(betAnswer.title, betAnswer.body, betAnswer.source);
    return;
  }
  if(lower.indexOf('strongest') >= 0 || lower.indexOf('highest score') >= 0){
    var scoreAnswer = officialMetricAnswer('score');
    answer(scoreAnswer.title, scoreAnswer.body, scoreAnswer.source);
    return;
  }
  if(lower.indexOf('best price') >= 0){
    var priceAnswer = officialMetricAnswer('price');
    answer(priceAnswer.title, priceAnswer.body, priceAnswer.source);
    return;
  }
  if(lower.indexOf('most tipster') >= 0 || lower.indexOf('most tipsters') >= 0 || lower.indexOf('zero tipster') >= 0 || lower.indexOf('zero tipsters') >= 0 || lower.indexOf('outside evidence') >= 0){
    var tipAnswer = officialMetricAnswer('tipsters');
    answer(tipAnswer.title, tipAnswer.body, tipAnswer.source);
    return;
  }
  if(lower.indexOf('most warnings') >= 0 || lower.indexOf('most warning') >= 0 || lower.indexOf('form caution') >= 0 || lower.indexOf('risky today') >= 0){
    var warningAnswer = officialMetricAnswer('warnings');
    answer(warningAnswer.title, warningAnswer.body, warningAnswer.source);
    return;
  }
  if(lower.indexOf('different races') >= 0 || lower.indexOf('same race') >= 0){
    var raceAnswer = officialMetricAnswer('races');
    answer(raceAnswer.title, raceAnswer.body, raceAnswer.source);
    return;
  }
  if(lower.indexOf('failed the form gate') >= 0 || lower.indexOf('poor recent form') >= 0 || lower.indexOf('failed form') >= 0){
    var formGateAnswer = gatesAnswer('form');
    answer(formGateAnswer.title, formGateAnswer.body, formGateAnswer.source);
    return;
  }
  if(lower.indexOf('failed the price gate') >= 0 || lower.indexOf('failed price') >= 0 || lower.indexOf('price gate') >= 0){
    var priceGateAnswer = gatesAnswer('price');
    answer(priceGateAnswer.title, priceGateAnswer.body, priceGateAnswer.source);
    return;
  }
  if(lower.indexOf('failed the score gate') >= 0 || lower.indexOf('failed score') >= 0 || lower.indexOf('score gate') >= 0){
    var scoreGateAnswer = gatesAnswer('score');
    answer(scoreGateAnswer.title, scoreGateAnswer.body, scoreGateAnswer.source);
    return;
  }
  if(lower.indexOf('overlay fix') >= 0 || lower.indexOf('tipster quality') >= 0 || lower.indexOf('rival history testing') >= 0 ||
     lower.indexOf('combined testing') >= 0 || lower.indexOf('ready to go live') >= 0 ||
     lower.indexOf('changing rules') >= 0 || lower.indexOf('what are we waiting') >= 0){
    var challengeExplain = challengerExplanationAnswer();
    answer(challengeExplain.title, challengeExplain.body, challengeExplain.source);
    return;
  }
  if(lower.indexOf('learned') >= 0 || lower.indexOf('learning') >= 0 || lower.indexOf('patterns') >= 0 ||
     lower.indexOf('monitor only') >= 0 || lower.indexOf('yesterday') >= 0 ||
     lower.indexOf('evidence is still collecting') >= 0 || lower.indexOf('field graph been predictive') >= 0){
    var learnAnswer = learningAnswer();
    answer(learnAnswer.title, learnAnswer.body, learnAnswer.source);
    return;
  }
  if(lower.indexOf('paid ai') >= 0 || lower.indexOf('private') >= 0 || lower.indexOf('fresh data') >= 0 ||
     lower.indexOf('feed last refresh') >= 0 || lower.indexOf('dashboard updated') >= 0 ||
     lower.indexOf('read-only') >= 0 || lower.indexOf('affect live') >= 0 ||
     lower.indexOf('sqlite') >= 0 || lower.indexOf('head-to-head') >= 0 ||
     lower.indexOf('files power') >= 0){
    var sysAnswer = systemAnswer();
    answer(sysAnswer.title, sysAnswer.body, sysAnswer.source);
    return;
  }
  if(lower.indexOf('nearly') >= 0 || lower.indexOf('watch') >= 0 || lower.indexOf('miss') >= 0){
    var watch = (pick('watchlist') || []).slice(0, 8);
    var rowsW = watch.map(function(w){
      return '<strong>'+esc(w.name)+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+raceContextHtml(w)+' · score '+esc(firstDefined(w.score, w.signal_score, '?'))+' · odds '+esc(w.odds || '?')+'</div><div style="color:var(--text);font-size:13px;line-height:1.7;margin-top:4px">'+esc(w.reasonText || 'Interesting, but missed at least one live rule. Learning only.').replace(/&amp;apos;/g,'&apos;')+'</div>';
    });
    answer('Horses that nearly made it', listRows(rowsW), 'watchlist');
    return;
  }
  if(lower.indexOf('picked') >= 0 || lower.indexOf('selected') >= 0 || lower.indexOf('selection') >= 0 || lower.indexOf('selections') >= 0 || lower.indexOf('why') >= 0){
    var official = pick('officialPicks') || [];
    var rows = official.map(function(p){
      var bits = [];
      if(p.score || p.signal_score) bits.push('score '+firstDefined(p.score, p.signal_score));
      if(p.odds) bits.push('odds '+p.odds);
      if(p.tipsters || p.tip_count) bits.push(firstDefined(p.tipsters, p.tip_count)+' tipsters');
      return '<strong>'+esc(p.name)+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+raceContextHtml(p)+' · '+esc(bits.join(' · '))+'</div><div style="color:var(--text);font-size:13px;line-height:1.7;margin-top:4px">Passed the live score, price, field and form checks. Any deeper warnings stay visible in Today&apos;s Picks and Confirm.</div>';
    });
    answer('Why today&apos;s official horses were picked', listRows(rows), 'officialPicks, raceView, pickQualityAudit');
    return;
  }
  if(lower.indexOf('rival') >= 0 || lower.indexOf('beaten') >= 0 || lower.indexOf('history') >= 0 || lower.indexOf('memory') >= 0){
    var fg = pick('fieldGraph') || {};
    var positives = asArray(fg.topEdges || fg.positiveEdges || fg.edges).slice(0, 8);
    var warnings = asArray(fg.warnings).slice(0, 5);
    var rowsR = positives.map(function(e){
      var horse = firstDefined(e.horse, e.winner, e.winner_name, e.source, e.name);
      var rival = firstDefined(e.rival, e.loser, e.loser_name, e.target, e.opponent);
      var wins = firstDefined(e.wins, e.count, e.weight, e.score, '');
      return '<strong>'+esc(horse || 'Horse')+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">has past field evidence against '+esc(rival || 'a rival')+(wins!=='' ? ' · '+esc(wins)+' evidence points' : '')+'</div>';
    });
    warnings.forEach(function(e){
      rowsR.push('<strong style="color:var(--amber)">'+esc(firstDefined(e.horse, e.name, 'Warning'))+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">warning: '+esc(firstDefined(e.reason, e.rival, e.warning, 'previous rival evidence against this horse'))+'</div>');
    });
    answer('Rival history in today&apos;s fields', listRows(rowsR), 'fieldGraph and raceView');
    return;
  }
  if(lower.indexOf('challenger') >= 0 || lower.indexOf('closest') >= 0 || lower.indexOf('working') >= 0 || lower.indexOf('live') >= 0){
    var rowsC = challengerRows().map(normalizeChallenger).sort(function(a,b){ return b.deltaProfit - a.deltaProfit; }).slice(0, 6).map(function(c){
      return '<strong>'+esc(c.name)+'</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+esc(c.status)+' · '+esc(c.pickResultDays)+' pick-result days · '+esc(c.roiReadyDays)+' ROI-ready days · '+signedMoney(c.deltaProfit)+' vs live</div><div style="color:var(--text);font-size:13px;line-height:1.7;margin-top:4px">Paper test only. It cannot affect live picks until John reviews it.</div>';
    });
    answer('Challenger Lab status', listRows(rowsC), 'challenger_summary and challenger_latest');
    return;
  }
  if(lower.indexOf('form') >= 0 || lower.indexOf('warning') >= 0 || lower.indexOf('blocked') >= 0){
    answer('Form warnings and blocked-risk notes', listRows(runnerWarnings().slice(0, 12)), 'raceView warnings');
    return;
  }
  if(lower.indexOf('result') >= 0 || lower.indexOf('roi') >= 0 || lower.indexOf('profit') >= 0 ||
     lower.indexOf('place rate') >= 0 || lower.indexOf('win rate') >= 0 ||
     lower.indexOf('winner') >= 0 || lower.indexOf('winners') >= 0 ||
     lower.indexOf('latest official') >= 0 || lower.indexOf('returned') >= 0 ||
     lower.indexOf('staked') >= 0){
    var perf = pick('performance') || {};
    var stats = perf.selectionStats || {};
    var winnerCount = firstDefined(stats.winners, perf.winners, 0);
    var placeRate = firstDefined(stats.placeRate, perf.placeRate, perf.officialPlaceRate, '');
    var winRate = firstDefined(perf.winRate, stats.winRate, '');
    var body = '<div style="font-size:20px;font-weight:800;color:var(--green);line-height:1.5">'+esc(signedMoney(perf.totalProfit || 0))+' profit</div>'+
      '<div style="color:var(--muted);line-height:1.8">ROI '+esc(signedPct(perf.roi || 0))+' · '+esc(perf.bettingDays || 0)+' official betting days · staked '+esc(fmtGBP(perf.totalStaked || 0))+' · returned '+esc(fmtGBP(perf.totalReturn || 0))+'</div>'+
      '<div style="color:var(--muted2);font-size:13px;line-height:1.7;margin-top:8px">'+esc(proofDayContext(perf))+'</div>'+
      '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:12px">'+
        '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px;background:rgba(255,255,255,.03)"><strong style="color:var(--green);font-size:18px">'+esc(winnerCount)+'</strong><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase">winners</div></div>'+
        '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px;background:rgba(255,255,255,.03)"><strong style="color:var(--gold);font-size:18px">'+esc(winRate !== '' ? winRate+'%' : 'n/a')+'</strong><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase">win rate</div></div>'+
        '<div style="border:1px solid rgba(255,255,255,.08);border-radius:var(--r-sm);padding:10px;background:rgba(255,255,255,.03)"><strong style="color:var(--blue);font-size:18px">'+esc(placeRate !== '' ? placeRate+'%' : 'n/a')+'</strong><div style="font-family:var(--mono);font-size:11px;color:var(--muted2);line-height:1.6;text-transform:uppercase">place rate</div></div>'+
      '</div>'+
      '<div style="color:var(--text);font-size:13px;line-height:1.8;margin-top:8px">Only official Signal 75 bets count in profit and ROI. Learning horses and challenger picks do not count.</div>';
    answer('Results and ROI', body, 'performance');
    return;
  }
  if(lower.indexOf('data') >= 0 || lower.indexOf('source') >= 0 || lower.indexOf('using') >= 0){
    var dbRows = sqliteHeadToHeadRowsLabel();
    var fg2 = pick('fieldGraph') || {};
    var bodyD = listRows([
      '<strong>Official picks</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">Today&apos;s live selections and watchlist.</div>',
      '<strong>Race view</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">Every runner, warnings, scores and status.</div>',
      '<strong>Field graph</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+esc(fg2.edgeCount || 0)+' rival checks in today&apos;s dashboard feed.</div>',
      '<strong>SQLite memory</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">'+esc(dbRows)+' stored head-to-head records visible to the dashboard.</div>',
      '<strong>Challenger Lab</strong><div style="color:var(--muted);font-size:13px;line-height:1.7">Paper tests that compare possible improvements without changing live picks.</div>'
    ]);
    answer('Data being used', bodyD, 'dashboard local feed');
    return;
  }
    answer('I can answer that if it matches a dashboard area', '<div class="plain">Try asking about today&apos;s picks, nearly-made-it horses, rival history, form warnings, challenger tests, results, ROI, data sources, or horse questions such as “who beat [horse] last time out?”. This version is intentionally controlled so it stays accurate and free.</div>', 'local question matcher');
}

/* ---------------------------------------------------------------------
   NAV CONFIG + BOOT
   --------------------------------------------------------------------- */
var NAV = [
  {group:'SIGNAL 75', items:[
    {id:'status', label:'Today', ico:'\u29bf', render:renderStrategyToday, keys:['status','selectionAudit','performance','proofStatus','dataCoverage','continuousLearning','officialPicks','watchlist']},
    {id:'systemmap', label:'How It Works', ico:'⌁', render:renderSystemMap, keys:['status','performance','dataCoverage','dbStatus','apiCostControl','sqliteIntelligence']},
		    {id:'picks', label:'Today\'s Picks', ico:'\u2315', render:renderTodaysPicks, keys:['officialPicks','watchlist','raceView','fieldGraph','richForm','postRaceReview','status','patentViability','pickQualityAudit','fieldRelativeDaily','challengerLab','weatherWarning']},
	    {id:'confirm', label:'Confirm', ico:'\u2726', render:renderConfirm, keys:['tipsterIntel','dbStatus','horseMemory','fieldGraph','richForm','raceView','challengerLab','challengerSummary','challengerLatest']},
	    {id:'learn', label:'Challenger Lab', ico:'\u27f2', render:renderChallengerLab, keys:['challengerLab','challengerSummary','challengerLatest','promotionCandidates','continuousLearning','learningEvidence','shadowRules','resultMarginIntel','fieldGraph','richFormOutcome','captureIntel','raceView','highConfidenceMisses','diagnostics','status','sqliteIntelligence']},
    {id:'ask', label:'Race Review', ico:'?', render:renderRaceReview, keys:['postRaceReview','latestPostRaceReview','whatBeatUs','resultMarginIntel','winnerIntel','performance','fieldRelativePerformance','proofStatus','status','sqliteIntelligence']},
    {id:'proof', label:'Results', ico:'\u21d5', render:renderProof, keys:['performance','proofStatus','continuousLearning','patentViability']},
    {id:'automation', label:'System', ico:'\u2699', render:renderAutomation, keys:['automation','apiCostControl','dataCoverage','performance','proofStatus','challengerLab','challengerSummary','promotionCandidates','sqliteIntelligence']}
  ]}
];
var FLAT = [];
NAV.forEach(function(g){ g.items.forEach(function(it){ FLAT.push(it); }); });

var DATA_PATHS = {
  challengerLab:['challengerLab.json'],
  challengerSummary:['challenger_lab/challenger_summary.json'],
  challengerLatest:['challenger_lab/challenger_latest.json'],
  promotionCandidates:['challenger_lab/promotion_candidates.json'],
  richFormOutcome:['richFormOutcome.json'],
  fieldRelativeDaily:['fieldRelativeDaily.json'],
  sqliteIntelligence:['sqliteIntelligence.json']
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

window.S75ui = { activate:activate, toggleExpand:toggleExpand, askSignal:askSignal, boot:boot };
document.addEventListener('DOMContentLoaded', boot);

})();
