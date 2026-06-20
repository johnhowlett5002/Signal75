/* ==========================================================================
   SIGNAL 75 — INTELLIGENCE DASHBOARD ENGINE
   Read-only. No function in this file writes picks, scores, results or
   proof. Every render* function below only ever reads data and draws it.
   ========================================================================== */
(function(){
"use strict";

/* ---------------------------------------------------------------------
   0. UTILITIES
   --------------------------------------------------------------------- */
function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g, function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }
function clamp(n,a,b){ return Math.max(a, Math.min(b, n)); }
function fmtGBP(n){ n = Number(n)||0; return (n<0?'-£':'£') + Math.abs(n).toFixed(2).replace(/\.00$/,''); }
function uid(){ return 'id'+Math.random().toString(36).slice(2,10); }

function scoreColor(score){
  if (score >= 88) return 'var(--gold)';
  if (score >= 75) return 'var(--green)';
  if (score >= 50) return 'var(--blue)';
  return 'var(--grey)';
}
var STATUS_COLOR = { official:'var(--green)', watchlist:'var(--blue)', runner:'var(--muted2)', not_scored:'var(--grey)', rejected:'var(--grey)' };
var STATUS_PILL = { official:'green', watchlist:'blue', runner:'grey', not_scored:'grey', rejected:'grey' };
var SEVERITY_COLOR = { good:'var(--green)', warn:'var(--amber)', bad:'var(--red)', info:'var(--blue)' };
var JOB_COLOR = { ok:'green', pending:'amber', failed:'red', scheduled:'grey' };

/* ---------------------------------------------------------------------
   1. SVG / GRAPHICAL COMPONENTS — these are the building blocks used
   throughout every section. Gauges are the default for any 0-100 style
   number; bars/waterfalls are reserved for genuinely additive values.
   --------------------------------------------------------------------- */

function gauge(opts){
  opts = opts || {};
  var max = opts.max||100;
  var value = clamp(Number(opts.value)||0, 0, max);
  var size = opts.size||92;
  var stroke = opts.stroke || 8;
  var color = opts.color || scoreColor(value);
  var label = opts.label != null ? opts.label : Math.round(value);
  var sub = opts.sub != null ? opts.sub : '';
  var r = size/2 - stroke - 1;
  var c = 2*Math.PI*r;
  var frac = max>0 ? value/max : 0;
  var id = uid();
  return (
    '<div class="gauge" style="width:'+size+'px;height:'+size+'px">'+
      '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'+
        '<circle class="track" cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" stroke-width="'+stroke+'"></circle>'+
        '<circle id="'+id+'" class="fill" cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" stroke-width="'+stroke+'" '+
          'stroke="'+color+'" stroke-dasharray="'+c+'" stroke-dashoffset="'+c+'"></circle>'+
      '</svg>'+
      '<div class="center">'+
        '<div class="v" style="color:'+color+'; font-size:'+(size*0.24)+'px">'+esc(label)+'</div>'+
        (sub!==''?'<div class="l">'+esc(sub)+'</div>':'')+
      '</div>'+
    '</div>'+
    '<script>(function(){var e=document.getElementById("'+id+'");if(e)requestAnimationFrame(function(){e.style.strokeDashoffset="'+(c-c*frac)+'";});})();</script>'
  );
}

function miniGauge(value, color, size){
  return gauge({value:value, color:color, size:size||46, stroke:5, label:'', sub:''});
}

function donut(segments, size){
  size = size || 120;
  var r = size/2 - 12;
  var c = 2*Math.PI*r;
  var total = segments.reduce(function(s,seg){return s+(seg.value||0);},0) || 1;
  var offset = 0;
  var ids = [];
  var circles = segments.map(function(seg){
    var frac = (seg.value||0)/total;
    var len = c*frac;
    var id = uid();
    var dashoffset = c - offset;
    offset += len;
    ids.push(id);
    return '<circle id="'+id+'" cx="'+size/2+'" cy="'+size/2+'" r="'+r+'" fill="none" stroke="'+seg.color+'" '+
      'stroke-width="11" stroke-dasharray="'+len+' '+(c-len)+'" stroke-dashoffset="'+dashoffset+'" opacity="0"></circle>';
  });
  var script = '<script>(function(){var ids=['+ids.map(function(i){return '"'+i+'"';}).join(',')+'];'+
    'ids.forEach(function(id,i){setTimeout(function(){var e=document.getElementById(id);if(e)e.style.opacity=1;},i*130);});})();</script>';
  return '<div class="donut" style="width:'+size+'px;height:'+size+'px">'+
    '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'+circles.join('')+'</svg></div>'+script;
}

function sparkline(points, color, w, h){
  w = w||140; h = h||40;
  if(!points || points.length<2) return '<div class="empty" style="padding:6px;font-size:9px">Not enough history yet</div>';
  var min = Math.min.apply(null, points), max = Math.max.apply(null, points);
  var range = (max-min) || 1;
  var step = w/(points.length-1);
  var pts = points.map(function(p,i){
    var x = i*step, y = h - ((p-min)/range)*(h-6) - 3;
    return x.toFixed(1)+','+y.toFixed(1);
  });
  var path = 'M'+pts.join(' L');
  var last = pts[pts.length-1].split(',');
  var id = uid();
  return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">'+
    '<path id="'+id+'" class="spark-line" d="'+path+'" stroke="'+color+'"></path>'+
    '<circle class="spark-dot" cx="'+last[0]+'" cy="'+last[1]+'" r="3" fill="'+color+'"></circle>'+
    '</svg><script>requestAnimationFrame(function(){var e=document.getElementById("'+id+'");if(e)e.style.strokeDashoffset=0;});</script>';
}

function trafficDot(level){ return '<span class="tdot '+level+'"></span>'; }

function waterfall(rows){
  var maxAbs = Math.max.apply(null, rows.map(function(r){return Math.abs(r.value);}).concat([1]));
  return '<div class="waterfall">' + rows.map(function(r){
    var w = clamp(Math.abs(r.value)/maxAbs*100, 3, 100);
    var cls = r.value > 0 ? 'pos' : (r.value < 0 ? 'neg' : 'neu');
    var color = r.color || (r.value>0?'var(--green)':(r.value<0?'var(--red)':'var(--muted2)'));
    var id = uid();
    return '<div class="wf-row"><div class="wf-label">'+esc(r.label)+'</div>'+
      '<div class="wf-track"><div id="'+id+'" class="wf-fill" style="background:'+color+'"></div></div>'+
      '<div class="wf-val '+cls+'">'+(r.value>0?'+':'')+r.value+'</div></div>'+
      '<script>requestAnimationFrame(function(){var e=document.getElementById("'+id+'");if(e)e.style.width="'+w+'%";});</script>';
  }).join('') + '</div>';
}

function pill(text, cls){ return '<span class="pill '+cls+'">'+esc(text)+'</span>'; }
function card(label, inner, extraClass){ return '<div class="card '+(extraClass||'')+'"><div class="card-label">'+esc(label)+'</div>'+inner+'</div>'; }

/* ---------------------------------------------------------------------
   2. DATA LAYER
   --------------------------------------------------------------------- */
var LIVE = {}, SOURCE = {};
function tryFetch(path){
  return fetch(path, {cache:'no-store'}).then(function(r){ if(!r.ok) throw 0; return r.json(); });
}
function loadReal(key, relPaths){
  // Private dashboard exports are deliberately served only from dashboard/data.
  // Do not reach into the public site data folder or silently substitute samples.
  var roots = ['./data/'];
  var tries = [];
  relPaths.forEach(function(p){ roots.forEach(function(root){ tries.push(root+p); }); });
  function attempt(i){
    if(i >= tries.length) return Promise.reject(0);
    return tryFetch(tries[i]).catch(function(){ return attempt(i+1); });
  }
  return attempt(0).then(function(json){ LIVE[key]=json; SOURCE[key]='live'; return json; })
    .catch(function(){ SOURCE[key]='unavailable'; return null; });
}
function sourceBadge(key){
  return SOURCE[key]==='live' ? '<span class="stage-flag flag-live">LIVE DATA</span>' : '<span class="stage-flag flag-preview">DATA UNAVAILABLE</span>';
}

/* ---------------------------------------------------------------------
   3. DEMO DATA — grounded in a real Signal 75 audit snapshot
   (2026-06-19 / 06-20) plus the latest automation update from Codex.
   Replaced section-by-section the moment loadReal() finds a real file.
   --------------------------------------------------------------------- */
var DEMO = {

  status: {
    date:"2026-06-20", picksGenerated:true, picksTime:"10:02", mode:"qualified",
    officialCount:3, watchlistCount:3, resultsSettled:"partial", resultsNote:"racing not complete",
    learningRefreshed:false, learningTime:"22:00", anthropicUsedToday:false, apiCallsAvoided:7,
    proofUnchanged:true
  },

  systemConfig: {
    proof_basis:"£1 each-way Patent", daily_stake:14.0, official_pick_count:3,
    live_odds_gate_low:2.75, live_odds_gate_high:8.0, score_gate_strict:75,
    odds_gate_strict_low:4.1, odds_gate_strict_high:6.0
  },
  apiCostControl: {
    anthropic_enabled:true, anthropic_fallback_only:true, max_anthropic_calls_per_day:1,
    preferred_model:"claude-haiku-4-5-20251001", calls_today:0, calls_avoided:7
  },

  performance: {
    bettingDays:12, profitableDays:6, totalStaked:168.0, totalReturn:295.48, totalProfit:127.48,
    roi:75.9, winRate:50, selectionStats:{total:36, winners:9, placed:12},
    recentProfits:[-14, 22.47, 76.53, -14, 8.2, -3, 14.5]
  },

  journey: [
    {ico:'\u2696', label:'Races loaded', num:'37', pct:1},
    {ico:'\u2713', label:'Runners matched', num:'412', pct:1},
    {ico:'\u2317', label:'Profile match', num:'76.2%', pct:.762},
    {ico:'\u270e', label:'Base score', num:'412', pct:1},
    {ico:'\u2605', label:'Tipster overlay', num:'39', pct:.6},
    {ico:'\u26a0', label:'Form warnings', num:'6', pct:.2},
    {ico:'\u00a3', label:'Market checked', num:'412', pct:1},
    {ico:'\u2713', label:'Patent viability', num:'GREEN', pct:1},
    {ico:'\u2605', label:'Official picks', num:'3', pct:1},
    {ico:'\u25c9', label:'Watchlist tracked', num:'3', pct:1},
    {ico:'\u29c9', label:'Picks written', num:'JSON', pct:1},
    {ico:'\u2191', label:'Site updated', num:'10:05', pct:1}
  ],

  officialPicks: [
    { name:"Carry The Flag", course:"Royal Ascot", time:"14:30", race:"5f Grp 2", odds:4.2,
      score:100.0, badge:"Banker", jockey:"Ryan Moore", trainer:"Aidan O'Brien",
      tipsters:6, consensusLevel:"strong",
      parts:[{label:"BASE",value:60,color:"var(--muted2)"},{label:"FORM",value:29,color:"var(--green)"},
             {label:"RACE/COURSE",value:27,color:"var(--green)"},{label:"TIPS",value:20,color:"var(--gold)"},
             {label:"PRICE",value:24,color:"var(--blue)"}],
      warnings:[], pickNumber:1,
      why:"Maxed-out Signal 75 score, strong consensus across Racing Post, Timeform and MyRacing, and odds inside the strict value band." },
    { name:"No More Bolero", course:"Worcester", time:"15:05", race:"2m4f Hcap Chase", odds:5.5,
      score:88.0, badge:"Strong", jockey:"H Cobden", trainer:"P Nicholls",
      tipsters:2, consensusLevel:"useful",
      parts:[{label:"BASE",value:60,color:"var(--muted2)"},{label:"FORM",value:30,color:"var(--green)"},
             {label:"RACE/COURSE",value:25,color:"var(--green)"},{label:"TIPS",value:12,color:"var(--gold)"},
             {label:"PRICE",value:21,color:"var(--blue)"}],
      warnings:[], pickNumber:2,
      why:"Strong recent form and a course/race-type lift carried this over the 75-point bar despite modest tipster support." },
    { name:"Blue Bolt", course:"Newbury", time:"16:10", race:"1m Hcap", odds:4.6,
      score:84.0, badge:"Value", jockey:"O Murphy", trainer:"W Haggas",
      tipsters:1, consensusLevel:"weak",
      parts:[{label:"BASE",value:60,color:"var(--muted2)"},{label:"FORM",value:32,color:"var(--green)"},
             {label:"RACE/COURSE",value:24,color:"var(--green)"},{label:"TIPS",value:8,color:"var(--gold)"},
             {label:"PRICE",value:20,color:"var(--blue)"}],
      warnings:[], pickNumber:3,
      why:"Solid score on form and price alone — tipster support was thin, which is exactly the kind of pick the model can find that consensus-driven sites miss." }
  ],

  watchlist: [
    { name:"Star Prospect", course:"Royal Ascot", time:"14:30", odds:12.0, score:72.5,
      reason:"ODDS_TOO_BIG_FOR_CURRENT_GATE",
      reasonText:"Strongly liked by the model, but priced outside the strict 4.1\u20136.0 official band.", result:null },
    { name:"Orthodox", course:"Royal Ascot", time:"14:30", odds:11.0, score:72.1,
      reason:"ODDS_TOO_BIG_FOR_CURRENT_GATE",
      reasonText:"Solid score, but the price sits well outside the official value band.", result:null },
    { name:"Ez Tina", course:"Royal Ascot", time:"14:30", odds:11.5, score:72.1,
      reason:"MISSED_TOP_THREE_RANK",
      reasonText:"Scored well but was outranked in a strong race \u2014 only the top 3 per day go official.", result:null }
  ],

  raceView: {
    races: [
      { course:"Royal Ascot", time:"14:30", race_name:"5f Grp 2", field_size:21,
        runners:[
          {number:1, name:"Carry The Flag", score:100.0, status:"official", odds:4.2, jockey:"Ryan Moore", trainer:"Aidan O'Brien", tipsters:6, warnings:[]},
          {number:4, name:"Star Prospect", score:72.5, status:"watchlist", odds:12.0, jockey:"D. McMonagle", trainer:"J P O'Brien", tipsters:0, warnings:[]},
          {number:2, name:"Orthodox", score:72.1, status:"watchlist", odds:11.0, jockey:"Rossa Ryan", trainer:"Clive Cox", tipsters:0, warnings:[]},
          {number:3, name:"Ez Tina", score:72.1, status:"watchlist", odds:11.5, jockey:"J Hernandez", trainer:"Wesley Ward", tipsters:0, warnings:[]},
          {number:5, name:"Force Noir", score:0, status:"not_scored", odds:12.5, jockey:"David Egan", trainer:"K P de Foy", tipsters:0, warnings:["Outside current Signal 75 scoring range"]},
          {number:6, name:"Savage Mariner", score:0, status:"not_scored", odds:13.5, jockey:"Tom Marquand", trainer:"Hugo Palmer", tipsters:0, warnings:["Outside current Signal 75 scoring range"]}
        ] },
      { course:"Worcester", time:"15:05", race_name:"2m4f Hcap Chase", field_size:9,
        runners:[
          {number:1, name:"No More Bolero", score:88.0, status:"official", odds:5.5, jockey:"H Cobden", trainer:"P Nicholls", tipsters:2, warnings:[]},
          {number:3, name:"Going The Distance", score:69.0, status:"runner", odds:6.5, jockey:"S Bowen", trainer:"D Pipe", tipsters:0, warnings:[]},
          {number:5, name:"Midnight Caller", score:54.0, status:"runner", odds:9.0, jockey:"R Johnson", trainer:"O Sherwood", tipsters:0, warnings:["Pulled up last time, no recent place"]}
        ] }
    ]
  },

  ledger: {
    horse:"Carry The Flag", race:"Royal Ascot 14:30",
    gathered:[
      {label:"Tipster mentions found", v:"6 (3 sources)"}, {label:"Historical profile match", v:"No (fresh to course)"},
      {label:"Market volume seen", v:"Heavy"}, {label:"Weather risk flag", v:"None"}, {label:"Head-to-head data", v:"Not available"}
    ],
    used:[
      {label:"Price contribution", v:"+24"}, {label:"Tips contribution", v:"+20"},
      {label:"Race/course contribution", v:"+27"}, {label:"Form contribution", v:"+29"}, {label:"History contribution", v:"+0 (no match)"}
    ],
    note:"Head-to-head data wasn't available for this horse and wasn't used \u2014 the gap here isn't a bug, it's exactly what 'no match' should look like."
  },

  tipsterIntel: {
    sourcesAttempted:16, sourcesSuccessful:3, totalRunnersChecked:404, totalMatched:39, tier1SourceFound:true,
    anthropicUsed:false, estimatedCallsAvoided:7,
    tierMix:[ {tier:1,value:14,color:"var(--gold)"}, {tier:2,value:6,color:"var(--blue)"},
              {tier:3,value:5,color:"var(--green)"}, {tier:4,value:14,color:"var(--muted2)"} ],
    matched:[
      { horse:"Carry The Flag", sources:["RacingPost","Timeform","MyRacing"], weighted:4.5, level:"strong" },
      { horse:"No More Bolero", sources:["SportingLife","Timeform"], weighted:3.0, level:"useful" },
      { horse:"Blue Bolt", sources:["OLBG"], weighted:0.5, level:"weak" }
    ]
  },

  dbStatus: {
    profileCount:297000, dbSizeMb:880,
    matchHistory:[ {date:"06-18", matched:249, total:342}, {date:"06-19", matched:291, total:398}, {date:"06-20", matched:308, total:404} ]
  },
  horseMemory: {
    "UNDERCOVER AFFAIR": { name:"Undercover Affair", runsLogged:2, knownWins:1, knownPlaces:0, knownLosses:0, unknownResults:1,
      lastSeen:"2026-06-12", lastCourse:"York", insight:"Came in with recent winning form \u2014 keep that pattern visible.", confidence:"Medium" },
    "CARRY ON CHAOS": { name:"Carry On Chaos", runsLogged:1, knownWins:0, knownPlaces:0, knownLosses:0, unknownResults:1,
      lastSeen:"2026-06-18", lastCourse:"Ripon", insight:"Logged for future course, price, trainer and form comparison.", confidence:"Low" }
  },

  winnerIntel: [
    { winner:"No More Bolero", status:"watchlist", score:97, learning:"Model found the horse but the official gate blocked it.", action:"WATCHLIST_OUTPERFORMED_OFFICIAL" }
  ],
  highConfidenceMisses: {
    today: {count:0,cases:[],rule:"No high-confidence miss has met the review threshold today."},
    history: {case_count:0,cases:[],repeated_patterns:[]}
  },
  radarVsOfficial: [
    { tab:"flat", officialLost:["Poets Dawn"], radarDidBetter:["Rajapour \u2014 placed 3rd"], verdict:"RADAR_SHOULD_HAVE_QUALIFIED" },
    { tab:"jumps", officialLost:["Sea The Clouds","Mojo Ego"], radarDidBetter:["Evenwood Sonofagun \u2014 placed 2nd"], verdict:"RADAR_SHOULD_HAVE_QUALIFIED" }
  ],

  continuousLearning: {
    daysAnalysed:15, officialAnalysed:20, officialPlaced:8, watchlistAnalysed:44, watchlistPlaced:26,
    officialPlaceRate:40.0, watchlistPlaceRate:59.1,
    findings:[
      { code:"FULL_CRITERIA_MET_AND_PLACED", count:33, threshold:5, severity:"good" },
      { code:"SURFACE_DATA_MISSING", count:20, threshold:5, severity:"warn" },
      { code:"UNPROVEN_COURSE", count:20, threshold:5, severity:"warn" },
      { code:"UNPROVEN_GOING", count:20, threshold:5, severity:"warn" },
      { code:"UNPROVEN_TRIP", count:20, threshold:5, severity:"warn" },
      { code:"FALSE_CONSENSUS", count:6, threshold:5, severity:"bad" },
      { code:"SHADOW_BEAT_LIVE_RULE", count:4, threshold:4, severity:"info" },
      { code:"SAME_COURSE_CLUSTER", count:4, threshold:5, severity:"info" }
    ]
  },

  shadowRules: {
    live:{ name:"baseline_live_rule", picks:3, roi:75.9, profit:127.48 },
    variants:[
      { name:"consensus_prefer_tipped_v1", picks:3, roi:81.2, profit:142.1, daysBeatLive:6, status:"watching" },
      { name:"consensus_rank_v1", picks:3, roi:68.4, profit:95.0, daysBeatLive:2, status:"watching" },
      { name:"consensus_strict_tipped_v1", picks:2, roi:90.0, profit:0.0, daysBeatLive:11, status:"candidate" },
      { name:"signal_first_consensus_overlay_v1", picks:3, roi:70.1, profit:101.2, daysBeatLive:3, status:"watching" },
      { name:"tipster_first_live_rule", picks:2, roi:55.0, profit:22.0, daysBeatLive:1, status:"watching" },
      { name:"late_value_band_v1", picks:2, roi:64.0, profit:48.0, daysBeatLive:5, status:"watching", note:"Late-market value band, not consensus-based" }
    ],
    promotionRule:"\u226510 days beating live + positive total edge + zero catastrophic days \u2014 then flagged for manual review only. Nothing here auto-promotes."
  },

  patentViability: {
    stake:14.0, lines:14, legs:[
      { name:"Carry The Flag", odds:4.2 }, { name:"No More Bolero", odds:5.5 }, { name:"Blue Bolt", odds:4.6 }
    ], placeFraction:0.2
  },

  automation: {
    jobs:[
      { name:"config_check", label:"System config check", status:"ok", time:"10:00" },
      { name:"scoring_tests", label:"Scoring regression tests", status:"ok", time:"10:00", detail:"4 passed" },
      { name:"picks_generator", label:"Picks generated", status:"ok", time:"10:02" },
      { name:"selection_diagnostics", label:"Selection diagnostics", status:"ok", time:"10:02" },
      { name:"deployment", label:"Site deployment", status:"ok", time:"10:05" },
      { name:"results_updater", label:"Results updater", status:"pending", time:"19:20" },
      { name:"tipster_memory", label:"Tipster memory", status:"scheduled", time:"23:10" },
      { name:"post_race_diagnosis", label:"Post-race diagnosis", status:"scheduled", time:"23:10" },
      { name:"grandad_memory", label:"Grandad / race memory", status:"scheduled", time:"23:10" },
      { name:"head_to_head", label:"Head-to-head & rivals", status:"scheduled", time:"23:10" },
      { name:"combined_learning", label:"Combined learning", status:"scheduled", time:"23:10" },
      { name:"calibration", label:"Calibration check", status:"scheduled", time:"23:10" },
      { name:"winner_intel", label:"Winner intelligence", status:"scheduled", time:"23:10" },
      { name:"drift_detection", label:"Drift detection", status:"scheduled", time:"23:10" },
      { name:"shadow_review", label:"Shadow review", status:"scheduled", time:"23:10" },
      { name:"scorecard", label:"Public scorecard", status:"scheduled", time:"23:10" },
      { name:"scenario_roi", label:"Scenario ROI review", status:"scheduled", time:"23:10" },
      { name:"pipeline_health", label:"Pipeline health report", status:"scheduled", time:"23:10" },
      { name:"github_tests", label:"GitHub regression check", status:"ok", time:"on code change" }
    ],
    manualByDesign:["Recovery / restore tools","Legacy duplicate result tools","Database lookup tools","Deployment trigger","Outward-facing email / social posting"]
  },

  dataCoverage: { runnersLoaded:412, runnersMatched:308, racesProcessed:37, tipsterMatched:39, resultsSettled:28, resultsTotal:32 },

  timeline: [
    { time:"09:00", label:"Morning resolve", status:"done" },
    { time:"10:00", label:"Config check + scoring tests", status:"done" },
    { time:"10:02", label:"Picks generated \u2014 3 official, 3 watchlist", status:"done" },
    { time:"10:05", label:"Site updated", status:"done" },
    { time:"14:30", label:"Royal Ascot 14:30 \u2014 Carry The Flag runs", status:"pending" },
    { time:"19:20", label:"Results updater", status:"pending" },
    { time:"23:10", label:"Nightly learning loop (11 jobs)", status:"scheduled" }
  ]
};

window.S75 = { util:{esc,clamp,fmtGBP,scoreColor,STATUS_COLOR,STATUS_PILL,SEVERITY_COLOR,JOB_COLOR},
  comp:{gauge,miniGauge,donut,sparkline,trafficDot,waterfall,pill,card},
  DEMO:DEMO, LIVE:LIVE, SOURCE:SOURCE, loadReal:loadReal, sourceBadge:sourceBadge };

})();
