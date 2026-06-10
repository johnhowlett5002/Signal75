/* DEV: To reset unlock state, run in console: localStorage.removeItem('s75unlock') */
/* ═══════════════════════════════════════════
   CONSTANTS
═══════════════════════════════════════════ */
var COFFEE_URL   = 'https://buymeacoffee.com/signal75';
var SITE_URL     = 'https://signal75.co.uk';
var S75_USER_ID  = localStorage.getItem('s75uid') || (function(){var id='u'+Math.random().toString(36).slice(2,10);localStorage.setItem('s75uid',id);return id;})();

/* ═══════════════════════════════════════════
   UNLOCK STATE
═══════════════════════════════════════════ */
var unlockState = {
  coffeePaid:  false,
  referrals:   0,
  tier:        0,
  sessionRefs: []
};

function allRacesComplete() {
  /* Check if all today's races have passed — if so show all picks */
  if (!PICKS_DATA) return false;
  var now = new Date();
  var allRaces = (PICKS_DATA.flat||[]).concat(PICKS_DATA.jumps||[]);
  if (!allRaces.length) return false;
  var lastRace = null;
  allRaces.forEach(function(race) {
    var t = race.time || '';
    var parts = t.split(':');
    if (parts.length === 2) {
      var raceDate = new Date();
      raceDate.setHours(parseInt(parts[0]), parseInt(parts[1]) + 30, 0); /* 30 min buffer after race */
      if (!lastRace || raceDate > lastRace) lastRace = raceDate;
    }
  });
  return lastRace && now > lastRace;
}

function raceAwaitingOfficialResult(race) {
  if (!race || !race.time) return false;
  var parts = String(race.time).split(':');
  if (parts.length !== 2) return false;
  var raceDate = new Date();
  raceDate.setHours(parseInt(parts[0], 10), parseInt(parts[1], 10) + 15, 0, 0);
  return new Date() >= raceDate;
}

function renderJumpsEmptyStateIfNeeded() {
  var jumpsContainer = document.getElementById('jumpsContainer');
  if (!jumpsContainer) return;
  var hasOfficialJumps = MOCK_JUMPS && MOCK_JUMPS.length > 0;
  var hasRadarJumps = TOP_RATED_JUMPS && TOP_RATED_JUMPS.length > 0;
  if (hasOfficialJumps || hasRadarJumps) return;
  jumpsContainer.innerHTML = emptyStateCardHtml('NO UK JUMPS SELECTIONS TODAY', 'Signal 75 currently tracks UK racing only.<br>Irish Jumps meetings are not included yet.<br><br>Today&apos;s official Patent picks are available on the Picks tab.');
}

function freeHorsesPerRace() {
  if (unlockState.coffeePaid) return 3;
  if (allRacesComplete()) return 3; /* all races done — show everything */
  var r = unlockState.referrals;
  if (r >= 2) return 3;
  if (r >= 1) return 2;
  return 1;
}

function saveUnlockState() {
  try {
    localStorage.setItem('s75unlock', JSON.stringify({
      coffeePaid: unlockState.coffeePaid,
      referrals:  unlockState.referrals,
      tier:       unlockState.tier
    }));
  } catch(e) {}
}

function loadUnlockState() {
  try {
    var raw = localStorage.getItem('s75unlock');
    if (raw) {
      var s = JSON.parse(raw);
      unlockState.coffeePaid = s.coffeePaid || false;
      unlockState.referrals  = s.referrals  || 0;
      unlockState.tier       = s.tier       || 0;
    }
    if (localStorage.getItem('supporterUnlocked') === 'true') {
      unlockState.coffeePaid = true;
    }
  } catch(e) {}
}

/* ═══════════════════════════════════════════
   TRACK RECORD — REAL 2026 DATA
═══════════════════════════════════════════ */
const trackRecord = [];


/* ═══════════════════════════════════════════
   STATS ENGINE
═══════════════════════════════════════════ */
var proofPeriod = 7;
var proofChartInst = null;
var PERF_DATA = null;
var LATEST_SCORECARD = null;
var LATEST_SCORECARD_LOADING = false;

function getProofEntries(days) {
  var cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - (days >= 9999 ? 36500 : days));
  return trackRecord.filter(function(e) { return new Date(e.date) >= cutoff; });
}

function calcStats(entries) {
  var wins = 0, placed = 0, total = entries.length, profit = 0, totalStake = 0;
  entries.forEach(function(e) {
    totalStake += e.stake;
    profit += e.pl;
    if (e.result === 'WON') wins++;
    if (e.result === 'PLACED') placed++;
  });
  return {
    total: total, wins: wins, placed: placed, profit: +profit.toFixed(2),
    winRate: total ? (wins / total) * 100 : 0,
    roi: totalStake ? (profit / totalStake) * 100 : 0,
    totalStake: +totalStake.toFixed(2)
  };
}

function calcPerfStats(days) {
  var entries = getProofEntries(days);
  var s = calcStats(entries);
  return { total:s.total, wins:s.wins, placed:s.placed, profit:s.profit, strike:Math.round(s.winRate), roi:Math.round(s.roi), entries:entries, totalStake:s.totalStake };
}

function calcPatentStats5(days) {
  var raw = calcPerfStats(days);
  return {
    total:raw.total, wins:raw.wins, placed:raw.placed, strike:raw.strike, roi:raw.roi,
    profit: +(raw.profit * 3.5).toFixed(2),
    totalStake: +(raw.totalStake * 3.5).toFixed(2)
  };
}

/* ═══════════════════════════════════════════
   ENGINE CONFIG
═══════════════════════════════════════════ */
const DEFAULT_CFG = {minOdds:2.0,maxOdds:15.0,maxRunners:14,wOdds:30,wTipsters:35,wField:20,wForm:15,minScore:55};
var cfg = Object.assign({}, DEFAULT_CFG);
var allHorses = [], raceGroups = [];

function decToFrac(dec) {
  dec = parseFloat(dec);
  if (!dec || dec <= 1) return 'EVS';
  var common = [[1,1],[5,4],[11,8],[6,4],[13,8],[7,4],[15,8],[2,1],[9,4],[5,2],[11,4],[3,1],[10,3],[7,2],[4,1],[9,2],[5,1],[11,2],[6,1],[13,2],[7,1],[15,2],[8,1],[10,1],[12,1],[14,1],[16,1],[20,1],[25,1],[33,1]];
  var diff=99,best='';
  common.forEach(function(p){var v=p[0]/p[1]+1;if(Math.abs(v-dec)<diff){diff=Math.abs(v-dec);best=p[0]+'/'+p[1];}});
  return best||Math.round((dec-1)*10)/10+'/1';
}

function sCol(s) {
  return s >= 70 ? 'var(--green)' : s >= 50 ? 'var(--gold)' : 'var(--muted2)';
}

function signalStrengthLabel(score) {
  score = parseInt(score || 0, 10);
  if (score >= 90) return '🔥 Elite signal';
  if (score >= 80) return '✅ Strong signal';
  if (score >= 70) return '🟢 Good signal';
  if (score >= 60) return '🟡 Watchlist';
  return '⚪ Pass';
}

var RADAR_ODDS_GATE_LOW = 2.75;
var RADAR_ODDS_GATE_HIGH = 8.0;
var RADAR_SCORE_GATE = 75;

function radarReason(h) {
  var bsp = parseFloat(h.odds || h.bsp || 0);
  var score = parseInt(h.signal_score || h.score || 0, 10);
  var tipCount = parseInt(h.tipsters || 0, 10);
  var muted = 'var(--muted)';

  if (bsp > 0 && bsp < RADAR_ODDS_GATE_LOW) {
    return {
      label: '⚡ Strong signal — odds too short for value band',
      colour: '#f0c040'
    };
  }
  if (bsp > RADAR_ODDS_GATE_HIGH) {
    return {
      label: '⚡ Strong signal — odds outside value band',
      colour: '#f0c040'
    };
  }
  if (score < RADAR_SCORE_GATE) {
    return {
      label: '📊 Watchlist — score just below qualifying threshold',
      colour: muted
    };
  }
  if (tipCount === 0) {
    return {
      label: '📊 Watchlist — no tipster support found today',
      colour: muted
    };
  }
  return {
    label: '📊 Watchlist — not an official pick',
    colour: muted
  };
}

function scorePart(value, fallback) {
  var n = parseInt(value, 10);
  if (!Number.isFinite(n)) n = parseInt(fallback, 10);
  if (!Number.isFinite(n)) n = 50;
  return Math.max(0, Math.min(100, n));
}

function signalDateLine() {
  var raw = (PICKS_DATA && PICKS_DATA.date) ? String(PICKS_DATA.date) : '';
  var d = raw && !PICKS_STALE && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(raw + 'T12:00:00') : new Date();
  return d.toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  }).toUpperCase();
}

function updateDateLines() {
  var text = signalDateLine() + (PICKS_STALE ? ' · SELECTIONS PREPARING' : ' · LIVE PICKS');
  ['todayDateLine', 'jumpsDateLine', 'patentDateLine'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  });
}

function emptyStateCardHtml(title, body) {
  return '<div style="background:var(--bg3);border:1px solid rgba(240,192,64,.25);border-radius:14px;padding:18px;margin:14px 0;text-align:center">' +
    '<div style="font-family:\'DM Mono\',monospace;font-size:12px;letter-spacing:.12em;color:var(--gold);text-transform:uppercase;margin-bottom:9px">' + signalDateLine() + '</div>' +
    '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:22px;letter-spacing:1px;color:var(--gold);margin-bottom:8px">' + title + '</div>' +
    '<div style="font-size:12px;line-height:1.6;color:#C8C8E0">' + body + '</div>' +
  '</div>';
}

function picksReturnTimeHtml() {
  return '<div style="font-family:\'DM Mono\',monospace;font-size:12px;letter-spacing:.08em;color:#F5F5FF;text-transform:uppercase;line-height:1.5;margin:10px auto 12px">Please check back after 10:15am UK time</div>';
}

function scoreBreakdownHtml(h, finalScore, isRadar) {
  var score = parseInt(finalScore || h.signal_score || h.score || 75, 10);
  if (!isFinite(score) || score < 0) score = 75;
  if (score > 100) score = 100;

  // Public-facing simplified explanation only.
  // This is NOT changing the engine score or official selection logic.
  var pricePts = Math.floor(score * 0.24);
  var tipsPts = Math.floor(score * 0.20);
  var racePts = Math.floor(score * 0.27);
  var formPts = score - pricePts - tipsPts - racePts;

  var tipCount = h.tipster_count || h.source_count || h.tipsters || 0;
  var tipWord = parseInt(tipCount, 10) === 1 ? "tipster" : "tipsters";

  var html = "";

  html += '<div class="s75-score-box-wrap">';
  html += '  <div class="s75-score-box-title">SIMPLIFIED SCORE BREAKDOWN</div>';
  html += '  <div class="s75-score-box-grid">';

  html += '    <div class="s75-score-box"><div class="s75-score-box-points">+' + pricePts + ' pts</div><div class="s75-score-box-label">Price</div><div class="s75-score-box-help">' + (isRadar ? 'Part of score' : 'Odds fit our range') + '</div></div>';
  html += '    <div class="s75-score-box"><div class="s75-score-box-points">+' + tipsPts + ' pts</div><div class="s75-score-box-label">Tips</div><div class="s75-score-box-help">Tipster support</div></div>';
  html += '    <div class="s75-score-box"><div class="s75-score-box-points">+' + racePts + ' pts</div><div class="s75-score-box-label">Race</div><div class="s75-score-box-help">Race looks suitable</div></div>';
  html += '    <div class="s75-score-box"><div class="s75-score-box-points">+' + formPts + ' pts</div><div class="s75-score-box-label">Form</div><div class="s75-score-box-help">Horse profile</div></div>';

  html += '  </div>';
  html += '  <div class="s75-score-box-total">Total = ' + score + ' pts / 100</div>';
  html += '  <div class="s75-score-box-note">' + (isRadar ? 'High score does not make this an official pick.' : 'Price + ' + (tipCount ? tipCount + ' ' + tipWord : 'tips') + ' + race fit + form = score.') + '</div>';
  html += '</div>';

  return html;
}

function weatherRiskHtml(race, horse) {
  var weather = (horse && horse.weatherRisk) || (race && race.weatherRisk) || null;
  if (!weather || !weather.risk) return '';

  var risk = String(weather.risk || '').toLowerCase();
  if (risk !== 'medium' && risk !== 'high') return '';

  var title = risk === 'high' ? 'Weather caution' : 'Rain watch';
  var message = weather.message || 'Weather may affect conditions today.';
  var detail = [];
  if (weather.currentPrecipMm !== undefined) detail.push('now ' + safeText(weather.currentPrecipMm) + 'mm');
  if (weather.next3hPrecipMm !== undefined) detail.push('next 3h ' + safeText(weather.next3hPrecipMm) + 'mm');
  if (weather.next3hPrecipProbability !== undefined) detail.push(safeText(weather.next3hPrecipProbability) + '% rain risk');

  return '' +
    '<div style="margin-top:8px;padding:8px 9px;border-radius:8px;border:1px solid rgba(240,192,64,.28);background:rgba(240,192,64,.08);font-family:\'DM Mono\',monospace;color:#F5F5FF;line-height:1.45">' +
      '<div style="font-size:10px;font-weight:900;color:var(--gold);text-transform:uppercase;letter-spacing:.08em">' + title + '</div>' +
      '<div style="font-size:10px;color:#E0E0F0;margin-top:3px">' + safeText(message) + '</div>' +
      (detail.length ? '<div style="font-size:9px;color:#A8A8BE;margin-top:3px">Score unchanged · ' + detail.join(' · ') + '</div>' : '<div style="font-size:9px;color:#A8A8BE;margin-top:3px">Score unchanged</div>') +
    '</div>';
}

/* ═══════════════════════════════════════════
   SCORING
═══════════════════════════════════════════ */
function scoreHorse(h) {
  // If Python engine has already scored this horse, use that score
  if (h.signal_score && h.signal_score > 0) {
    h.score = h.signal_score;
    if (!h.bd) {
      var s = h.signal_score;
      h.bd = {os: Math.min(100,s), ts: 75, fs: Math.min(100,s), fm: Math.min(100,s)};
    }
    h.reason = h.reason || 'Scored by Signal 75 data engine.';
    return h;
  }
  var os = 0, ts = 0, fs = 0, fm = 0;
  if (h.odds >= cfg.minOdds && h.odds <= cfg.maxOdds) {
    os = h.odds <= 8 ? ((h.odds - cfg.minOdds) / (8 - cfg.minOdds)) * 100 : Math.max(0, 100 - ((h.odds - 8) / (cfg.maxOdds - 8)) * 60);
    os = Math.min(100, os);
  }
  ts = Math.min(100, (h.tipsters / 12) * 100);
  fs = Math.min(100, h.runners <= cfg.maxRunners ? Math.max(0, 100 - ((h.runners - 4) / (cfg.maxRunners - 4)) * 100) : 0);
  var form = (h.formStr || 'FFFFF').slice(-5).split('');
  var fScore = 0;
  form.forEach(function(ch, i) {
    var w = (i + 1) * 4;
    if (ch === 'W') fScore += w * 2;
    else if (ch === 'P') fScore += w;
  });
  fm = Math.min(100, (fScore / 60) * 100);
  var raw = (os * cfg.wOdds + ts * cfg.wTipsters + fs * cfg.wField + fm * cfg.wForm) / 100;
  h.score = h.signal_score || Math.round(Math.min(99, Math.max(1, raw)));
  h.bd = {os: Math.round(os), ts: Math.round(ts), fs: Math.round(fs), fm: Math.round(fm)};
  h.reason = h.reason || 'Strong model signal across odds value, tipster consensus and field conditions.';
  return h;
}

/* ═══════════════════════════════════════════
   PICKS DATA — loaded from picks.json
═══════════════════════════════════════════ */
var NO_BET_DAY = false;
var NO_BET_REASON = '';
var TOP_RATED = [];
var PICKS_MODE = '';
var PICKS_DATA = null;
var MOCK_RACES = [];
var MOCK_JUMPS = [];
var DAILY_PICKS_GROUPS = []; /* combined flat+jumps top 3 — single source of truth */
var LAST_PICKS_SIGNATURE = '';
var LAST_PERFORMANCE_SIGNATURE = '';
var LIVE_REFRESH_STARTED = false;
var PICKS_STALE = false;

function stableDataSignature(data) {
  try {
    return JSON.stringify(data || {});
  } catch(e) {
    return String(Date.now());
  }
}

/* ═══════════════════════════════════════════
   PATENT EACH-WAY CALCULATOR
   Stake: £1 EW per bet line.
   Full patent = 7 bets EW: 3 singles, 3 doubles, 1 treble
   Default proof display: 14 bet lines x £1 = £14 total stake
═══════════════════════════════════════════ */
function calcEWReturn(odds, result, stake, placeTerms) {
  /* placeTerms default 1/4 odds */
  placeTerms = placeTerms || 0.25;
  if (result === 'WON') {
    var winRet = stake * odds;
    var placeRet = stake * (1 + (odds - 1) * placeTerms);
    return { win: +winRet.toFixed(2), place: +placeRet.toFixed(2), total: +(winRet + placeRet).toFixed(2) };
  } else if (result === 'PLACED') {
    var placeRet2 = stake * (1 + (odds - 1) * placeTerms);
    return { win: 0, place: +placeRet2.toFixed(2), total: +placeRet2.toFixed(2) };
  }
  return { win: 0, place: 0, total: 0 };
}

function calcPatentReturn(horses, stake) {
  /* horses = array of {odds, result} — max 3 */
  stake = stake || 1.00;
  var ewStake = stake; /* per bet */
  var total = 0;
  var h = horses.slice(0, 3);

  /* 3 Singles EW */
  h.forEach(function(horse) {
    var r = calcEWReturn(horse.odds, horse.result, ewStake);
    total += r.total;
  });

  /* 3 Doubles EW */
  var doubles = [[0,1],[0,2],[1,2]];
  doubles.forEach(function(pair) {
    if (h[pair[0]] && h[pair[1]]) {
      var r0 = calcEWReturn(h[pair[0]].odds, h[pair[0]].result, ewStake);
      var r1 = calcEWReturn(h[pair[1]].odds, h[pair[1]].result, ewStake);
      /* Win double */
      if (h[pair[0]].result === 'WON' && h[pair[1]].result === 'WON') {
        total += ewStake * h[pair[0]].odds * h[pair[1]].odds;
      }
      /* Place double */
      var p0 = (h[pair[0]].result === 'WON' || h[pair[0]].result === 'PLACED');
      var p1 = (h[pair[1]].result === 'WON' || h[pair[1]].result === 'PLACED');
      if (p0 && p1) {
        var pl0 = 1 + (h[pair[0]].odds - 1) * 0.25;
        var pl1 = 1 + (h[pair[1]].odds - 1) * 0.25;
        total += ewStake * pl0 * pl1;
      }
    }
  });

  /* 1 Treble EW */
  if (h.length === 3) {
    if (h[0].result === 'WON' && h[1].result === 'WON' && h[2].result === 'WON') {
      total += ewStake * h[0].odds * h[1].odds * h[2].odds;
    }
    var allPlaced = h.every(function(horse) { return horse.result === 'WON' || horse.result === 'PLACED'; });
    if (allPlaced) {
      var treblePl = h.reduce(function(acc, horse) {
        return acc * (1 + (horse.odds - 1) * 0.25);
      }, ewStake);
      total += treblePl;
    }
  }

  var totalStake = ewStake * 2 * 7; /* 7 bets, each EW = 2x stake */
  return { totalReturn: +total.toFixed(2), totalStake: +totalStake.toFixed(2), profit: +(total - totalStake).toFixed(2) };
}

/* ═══════════════════════════════════════════
   DATA PIPELINE
═══════════════════════════════════════════ */
function processRaces(races) {
  allHorses = []; raceGroups = [];
  races.forEach(function(race) {
    var list = race.horses || race.runners || [];
    var grp = {
      time:race.time||'',course:race.course||race.venue||'TBC',type:race.type||race.race_type||'flat',
      distance:race.distance||'',runners:list.length,horses:[]
    };
    list.forEach(function(h) {
      var horse = {
        num:h.num||'',name:h.name||'',jockey:h.jockey||'',trainer:h.trainer||'',
        odds:parseFloat(h.odds||0),prevOdds:parseFloat(h.prevOdds||h.odds||0),
        tipsters:parseInt(h.tipsters||0),formStr:h.formStr||'FFFFF',
        runners:grp.runners,reason:h.reason||'',
        signal_score:parseInt(h.signal_score||h.qualificationScore||0),bd:h.bd||null,badge:h.badge||''
      };
      scoreHorse(horse);
      horse.disqualified = null;
      if (horse.score < 30) horse.score = 30;
      grp.horses.push(horse);
      allHorses.push(horse);
    });
    grp.horses.sort(function(a,b){return b.score-a.score;});
    if (grp.horses.length) raceGroups.push(grp);
  });
  allHorses.sort(function(a,b){return b.score-a.score;});
}

/* ═══════════════════════════════════════════
   LOAD RACES
═══════════════════════════════════════════ */
function fetchJsonWithTimeout(url, timeoutMs) {
  timeoutMs = timeoutMs || 9000;
  var controller = window.AbortController ? new AbortController() : null;
  var timer = null;

  if (controller) {
    timer = setTimeout(function() {
      controller.abort();
    }, timeoutMs);
  }

  return fetch(url, {
    cache: 'no-store',
    signal: controller ? controller.signal : undefined
  }).then(function(r) {
    if (timer) clearTimeout(timer);
    if (!r || !r.ok) {
      throw new Error('Data request failed');
    }
    return r.json();
  }).then(function(data) {
    if (data && data.offline) {
      throw new Error('Offline data fallback');
    }
    return data;
  }).catch(function(err) {
    if (timer) clearTimeout(timer);
    throw err;
  });
}

function fetchJsonWithRetry(urlBuilder, attempts) {
  attempts = attempts || [
    { timeout: 12000, wait: 0 },
    { timeout: 18000, wait: 900 },
    { timeout: 26000, wait: 1600 }
  ];

  function runAttempt(index) {
    var attempt = attempts[index] || attempts[attempts.length - 1];
    var url = typeof urlBuilder === 'function' ? urlBuilder(index) : urlBuilder;
    return fetchJsonWithTimeout(url, attempt.timeout).catch(function(err) {
      if (index >= attempts.length - 1) {
        throw err;
      }

      return new Promise(function(resolve) {
        setTimeout(resolve, attempt.wait || 0);
      }).then(function() {
        return runAttempt(index + 1);
      });
    });
  }

  return runAttempt(0);
}

function showPicksConnectionIssue() {
  var btn = document.getElementById('loadBtn');
  if (btn) btn.style.display = 'none';

  var rc = document.getElementById('racesContainer');
  if (!rc) return;
  rc.innerHTML =
    '<div style="background:rgba(240,192,64,0.06);border:1px solid rgba(240,192,64,0.32);border-radius:14px;padding:22px 18px;text-align:center;margin:8px 0">' +
      '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:25px;letter-spacing:1px;color:var(--gold);margin-bottom:8px">Connection issue</div>' +
      '<div style="font-size:12px;color:#E0E0F0;line-height:1.7;max-width:310px;margin:0 auto 14px">Signal 75 has opened, but today\'s picks did not load properly. This can happen when a phone changes between WiFi and mobile data.</div>' +
      '<button type="button" onclick="loadRaces(false);loadPerformance(false)" style="width:100%;border:0;border-radius:12px;background:linear-gradient(135deg,#f0c040,#d99a18);color:#050608;font-weight:900;font-size:14px;padding:14px 16px">Retry loading picks</button>' +
    '</div>';
}

function todayIsoDate() {
  var now = new Date();
  var yyyy = now.getFullYear();
  var mm = String(now.getMonth() + 1).padStart(2, '0');
  var dd = String(now.getDate()).padStart(2, '0');
  return yyyy + '-' + mm + '-' + dd;
}

function isPicksFileStale(data) {
  if (!data || !data.date || !/^\d{4}-\d{2}-\d{2}$/.test(String(data.date))) return false;
  return String(data.date) < todayIsoDate();
}

function showPicksNotUpdatedYet(data) {
  var btn = document.getElementById('loadBtn');
  if (btn) btn.style.display = 'none';

  var rc = document.getElementById('racesContainer');
  if (!rc) return;

  PICKS_STALE = true;
  updateDateLines();
  updateProofStrip();

  var lastDate = data && data.date ? s75ResultDateLabel(String(data.date)) : 'yesterday';
  rc.innerHTML =
    '<div style="background:rgba(240,192,64,0.06);border:1px solid rgba(240,192,64,0.32);border-radius:14px;padding:22px 18px;text-align:center;margin:8px 0">' +
      '<div style="font-family:\'DM Mono\',monospace;font-size:12px;letter-spacing:.12em;color:var(--gold);text-transform:uppercase;margin-bottom:9px">' + signalDateLine() + '</div>' +
      '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:25px;letter-spacing:1px;color:var(--gold);margin-bottom:8px">Today’s selections are being prepared</div>' +
      picksReturnTimeHtml() +
      '<div style="font-size:12px;color:#E0E0F0;line-height:1.7;max-width:340px;margin:0 auto 14px">Signal 75 is open for today. The latest published selections are from ' + safeText(lastDate) + ', so today’s picks will appear here once the morning checks are complete.</div>' +
      '<button type="button" onclick="loadRaces(false);loadPerformance(false)" style="width:100%;border:0;border-radius:12px;background:linear-gradient(135deg,#f0c040,#d99a18);color:#050608;font-weight:900;font-size:14px;padding:14px 16px">Check again</button>' +
    '</div>';

  var jc = document.getElementById('jumpsContainer');
  if (jc) jc.innerHTML = emptyStateCardHtml('Today’s Jumps selections are being prepared', picksReturnTimeHtml() + 'Today’s Jumps picks will appear here once the morning checks are complete.');
}

function loadRaces(silent) {
  var btn = document.getElementById('loadBtn');
  var txt = document.getElementById('loadTxt');
  var horse = document.getElementById('loadHorse');
  silent = !!silent;
  if (!silent) {
    if (btn) btn.disabled = true;
    if (txt) txt.textContent = 'Analysing...';
    if (horse) horse.textContent = '⏳';
    showSkeletons('racesContainer');
  }

  /* Fetch picks.json with mobile-friendly retries */
  fetchJsonWithRetry(function(attempt) {
    return 'picks.json?v=' + Date.now() + '&try=' + attempt;
  })
    .then(function(data) {
      if (isPicksFileStale(data)) {
        PICKS_DATA = data;
        updateDateLines();
        showPicksNotUpdatedYet(data);
        updateNavDots();
        if (btn) { btn.style.display = 'none'; }
        return;
      }

      var signature = stableDataSignature(data);
      if (silent && signature === LAST_PICKS_SIGNATURE) return;
      LAST_PICKS_SIGNATURE = signature;

      PICKS_DATA = data;
      PICKS_STALE = false;
      NO_BET_DAY = data.noBetDay || false;
      NO_BET_REASON = data.noBetReason || '';
      MOCK_RACES = data.flat || [];
      MOCK_JUMPS = data.jumps || [];
      TOP_RATED = data.topRated || [];
      TOP_RATED_FLAT = data.topRatedFlat || [];
      TOP_RATED_JUMPS = data.topRatedJumps || [];
      PICKS_MODE = data.mode || '';
      updateDateLines();

      try {
        if (PICKS_MODE === 'topRatedOnly' || NO_BET_DAY) {
          var radarFlat = []; TOP_RATED_FLAT.forEach(function(h){ radarFlat.push({course:h.venue||h.course||"TBC",time:h.time||"",type:h.race_type||h.type||"flat",runners:h.runners||8,horses:[Object.assign({},h,{score:parseInt(h.signal_score||h.qualificationScore||0),signal_score:parseInt(h.signal_score||h.qualificationScore||0),badge:h.badge||"Watchlist",tipsters:h.tipsters||0,jockey:h.jockey||"Watchlist pick",bd:{fs:parseInt(h.signal_score||50),os:parseInt(h.signal_score||50),ts:50,fm:parseInt(h.signal_score||50)}})],isRadar:true}); });
          var radarJumps = []; TOP_RATED_JUMPS.forEach(function(h){ radarJumps.push({course:h.venue||h.course||"TBC",time:h.time||"",type:h.race_type||h.type||"jumps",runners:h.runners||8,horses:[Object.assign({},h,{score:parseInt(h.signal_score||h.qualificationScore||0),signal_score:parseInt(h.signal_score||h.qualificationScore||0),badge:h.badge||"Watchlist",tipsters:h.tipsters||0,jockey:h.jockey||"Watchlist pick",bd:{fs:parseInt(h.signal_score||50),os:parseInt(h.signal_score||50),ts:50,fm:parseInt(h.signal_score||50)}})],isRadar:true}); });
          renderPickCards('racesContainer', radarFlat);
          insertFreePickShareButton('racesContainer');
          renderPickCards('jumpsContainer', radarJumps);
          renderJumpsEmptyStateIfNeeded();
        } else {
          /* Add runners count from array length */
          MOCK_RACES.forEach(function(r){ r.horses.forEach(function(h){ h.runners = r.horses.length; }); });
          MOCK_JUMPS.forEach(function(r){ r.horses.forEach(function(h){ h.runners = r.horses.length; }); });

          /* Build combined daily picks — flat + jumps, top 3 by score */
          var allPicks = [];
          var combined = MOCK_RACES.concat(MOCK_JUMPS);
          combined.forEach(function(race) {
            if (race.horses && race.horses[0]) {
              allPicks.push({race: race, horse: race.horses[0], score: race.horses[0].signal_score || 0});
            }
          });
          allPicks.sort(function(a,b){ return b.score - a.score; });
          var top3 = allPicks.slice(0, 3);

          /* Build synthetic race groups for main picks tab */
          var dailyGroups = top3.map(function(p){ return p.race; });
          DAILY_PICKS_GROUPS = dailyGroups; /* store as single source of truth */

          /* Flat tab — flat official picks only, with flat radar fill if available */
          var flatDisplayGroups = buildFlatDisplayGroups();
          renderPickCards('racesContainer', flatDisplayGroups);
          insertFreePickShareButton('racesContainer');

          var rc = document.getElementById('racesContainer');
          if (rc && !document.getElementById('resultsTimeNote')) {
            rc.insertAdjacentHTML('afterbegin',
              '<div id="resultsTimeNote" style="background:rgba(240,192,64,.06);border:1px solid rgba(240,192,64,.22);border-radius:12px;padding:10px 12px;margin:0 0 10px;text-align:center;font-family:\'DM Mono\',monospace;font-size:10px;color:#f0c040;letter-spacing:.08em;text-transform:uppercase">Results updated daily after 7:15pm</div>'
            );
          }

          updateProofStrip();

          /* Jumps tab — jumps official picks only, with jumps radar fill if available */
          var jumpGroups = buildJumpsDisplayGroups();
          renderPickCards('jumpsContainer', jumpGroups);
          renderJumpsEmptyStateIfNeeded();

          /* Keep the global group list aligned with the visible flat tab. */
          raceGroups = flatDisplayGroups.slice();

          /* Render results if available */
          if (data.results) {
            renderResults('racesContainer', data.flat, data.results.flat, 'flat');
            renderResults('jumpsContainer', data.jumps, data.results.jumps, 'jumps');
          }
        }
      } catch(e) {
        console.error('Signal 75 render error:', e);
        var rc = document.getElementById('racesContainer');
        if (rc) rc.innerHTML = '<div style="padding:20px;color:#f0c040;text-align:center;font-size:12px;font-family:monospace">Error loading picks. Please refresh.</div>';
      }
      updateNavDots();
      if (btn) { btn.style.display = 'none'; }
    })
    .catch(function(err) {
      /* Fallback if picks.json not found */
      console.warn('picks.json not available:', err);
      if (silent && PICKS_DATA) return;
      showPicksConnectionIssue();
    });
}

/* ═══════════════════════════════════════════
   RESULTS RENDERER — transforms pick cards
   after race time has passed
═══════════════════════════════════════════ */
function renderResults(containerId, races, results, type) {
  if (!races || !results) return;
  var now = new Date();

  /* Build legs directly from qualified picks — already scored and filtered by Python */
  var legs = [];
  for (var i = 0; i < Math.min(3, races.length); i++) {
    var race = races[i];
    if (race && race.horses && race.horses[0]) {
      legs.push({ horse: race.horses[0], race: race });
    }
  }

  var allResultsIn = true;
  var patentHorses = [];

  legs.forEach(function(lp, i) {
    if (!results[i]) return;
    var res = results[i];
    if (!res.result) { allResultsIn = false; return; }
    if (res.result === 'PENDING') allResultsIn = false;

    if (res.result !== 'PENDING') {
      patentHorses.push({ odds: lp.horse.odds, result: res.result });
    }

    /* Find the visible card and append result panel */
    var prefix = containerId === 'jumpsContainer' ? 'jhcard' : 'hcard';
    var cardEl = document.getElementById(prefix + i);
    if (!cardEl) return;

    /* Remove existing result panel if any */
    var existing = cardEl.querySelector('.result-panel');
    if (existing) existing.remove();

    var isPending = res.result === 'PENDING';
    var ew = calcEWReturn(lp.horse.odds, res.result, 1.00);
    var col = res.result === 'WON' ? 'var(--green)' :
              res.result === 'PLACED' ? 'var(--gold)' :
              res.result === 'LOST' ? '#C8C8E0' :
              res.result === 'VOID' ? 'var(--muted2)' :
              'var(--gold)';
    var icon = res.result === 'WON' ? '🏆' :
               res.result === 'PLACED' ? '🟡' :
               res.result === 'LOST' ? '•' :
               res.result === 'VOID' ? '↩' :
               '⏳';
    var posStr = '';
    if (res.position &&
        res.position > 0 &&
        res.position < 40) {
      posStr = ordinal(res.position);
    }
    var resultLabel = res.result;
    if (res.result === 'WON') resultLabel = 'WON';
    if (res.result === 'PLACED') resultLabel = 'PLACED';
    if (res.result === 'LOST') resultLabel = posStr || 'UNPLACED';

    var panel = document.createElement('div');
    var resultClass = res.result === 'WON' ? 'result-win' :
                      res.result === 'PLACED' ? 'result-place' :
                      res.result === 'LOST' ? 'result-lost' :
                      isPending ? 'result-pending' : '';
    panel.className = 'result-panel ' + resultClass;
    panel.setAttribute('role', 'button');
    panel.setAttribute('tabindex', '0');
    var displayResult = resultLabel + ((res.result === 'WON' || res.result === 'PLACED') && posStr ? ' - ' + posStr.toUpperCase() : '');
    var pendingText = raceAwaitingOfficialResult(lp.race) ? 'Race run — awaiting official result' : 'Result pending';
    panel.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">' +
        '<div class="result-badge">' +
          '<span class="result-icon">' + icon + '</span>' +
          '<span>' + displayResult + '</span>' +
        '</div>' +
        (isPending ? '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0;text-align:right;max-width:130px;line-height:1.35">' + pendingText + '</div>' :
        '<div class="result-return">' +
          '<div class="result-return-amt">' + (ew.total > 0 ? '+£' + ew.total.toFixed(2) : '£0.00') + '</div>' +
          '<div class="result-return-lbl">£1 EW return</div>' +
        '</div>') +
      '</div>';
    cardEl.appendChild(panel);
  });

  /* Show full patent summary if all results are in */
  if (allResultsIn && patentHorses.length === 3) {
    var patent = calcPatentReturn(patentHorses, 1.00);
    var profCol = patent.profit >= 0 ? 'var(--green)' : 'var(--red)';
    var profSign = patent.profit >= 0 ? '+' : '';
    var container = document.getElementById(containerId);
    if (!container) return;

    /* Remove existing summary */
    var existingSummary = container.querySelector('.patent-summary');
    if (existingSummary) existingSummary.remove();

    var summary = document.createElement('div');
    summary.className = 'patent-summary';
    summary.style.cssText = 'background:linear-gradient(135deg,rgba(240,192,64,0.08),rgba(0,232,122,0.05));border:1px solid rgba(240,192,64,0.3);border-radius:14px;padding:16px;margin-top:8px';
    summary.innerHTML =
      '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px">&#x1F4B0; Today\'s Patent Each-Way Return</div>' +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">' +
        '<div>' +
          '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:36px;color:' + profCol + ';line-height:1">' + profSign + '£' + Math.abs(patent.profit).toFixed(2) + '</div>' +
          '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0">Profit from £' + patent.totalStake.toFixed(2) + ' staked (14 bet lines)</div>' +
        '</div>' +
        '<div style="text-align:right">' +
          '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:20px;color:var(--text)">£' + patent.totalReturn.toFixed(2) + '</div>' +
          '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0">Total returned</div>' +
        '</div>' +
      '</div>' +
      '<div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:8px 10px;margin-bottom:10px;font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;line-height:1.8">' +
        '£1 EW Patent = 14 bet lines &middot; £' + patent.totalStake.toFixed(2) + ' total stake<br>' +
        '3 singles + 3 doubles + 1 treble &middot; all each-way' +
      '</div>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">' +
        '<button onclick="shareDailyScorecard(' + patent.profit.toFixed(2) + ',' + patent.totalReturn.toFixed(2) + ',\'' + type + '\')" style="grid-column:1/-1;width:100%;padding:11px;background:linear-gradient(135deg,#f0c040,#e8a020);border:none;border-radius:9px;font-size:13px;font-weight:900;color:#050509;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:6px">Share Today\'s Result</button>' +
        '<button onclick="copyDailyScorecard(' + patent.profit.toFixed(2) + ',' + patent.totalReturn.toFixed(2) + ',\'' + type + '\')" style="padding:10px;border:1px solid var(--border);border-radius:9px;background:var(--bg4);color:#E0E0F0;font-size:11px;font-weight:800;cursor:pointer">Copy Result Text</button>' +
        '<button onclick="postDailyScorecardToX(' + patent.profit.toFixed(2) + ',' + patent.totalReturn.toFixed(2) + ',\'' + type + '\')" style="padding:10px;border:1px solid rgba(240,192,64,.22);border-radius:9px;background:rgba(240,192,64,.06);color:#f0c040;font-size:11px;font-weight:800;cursor:pointer">Post to X</button>' +
      '</div>';
    container.appendChild(summary);
  }
}

function ordinal(n) {
  var s = ['th','st','nd','rd'], v = n % 100;
  return n + (s[(v-20)%10] || s[v] || s[0]);
}

function safeText(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function displayReasonText(reason) {
  return String(reason || '')
    .replace(/^Radar watchlist:/i, 'Watchlist:')
    .replace(/,\s*form\s+[^.]+\.?$/i, '.')
    .replace(/\s+\./g, '.')
    .trim();
}

function radarResultPanelHtml(h, race) {
  var result = h.result || '';
  var txt = h.radarResult || '';
  if (!txt && h.position) txt = ordinal(parseInt(h.position, 10)).toUpperCase();
  if (!txt) return '';
  if (result === 'PENDING' && /race run/i.test(txt) && !raceAwaitingOfficialResult(race)) {
    txt = 'Result pending';
  } else if (result === 'PENDING' && /race run/i.test(txt)) {
    txt = 'Result being checked';
  }

  var cls = result === 'WON' ? 'result-win' :
            result === 'PLACED' ? 'result-place' :
            result === 'VOID' ? '' :
            result === 'PENDING' ? 'result-pending' :
            'result-lost';
  var icon = result === 'WON' ? '&#x1F3C6;' :
             result === 'PLACED' ? '&#x1F7E1;' :
             result === 'VOID' ? '&#x21A9;' :
             result === 'PENDING' ? '&#x23F3;' :
             '&bull;';
  return '' +
    '<div class="result-panel radar-result-panel ' + cls + '">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:10px">' +
        '<div class="result-badge">' +
          '<span class="result-icon">' + icon + '</span>' +
          '<span>' + txt + '</span>' +
        '</div>' +
        '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0;text-align:right;line-height:1.4">Watchlist only<br>not official</div>' +
      '</div>' +
    '</div>';
}

function openXPost(text) {
  var url = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(text);
  window.open(url, '_blank', 'noopener');
}

function copyPostText(text) {
  if (!navigator.clipboard) {
    window.prompt('Copy this text:', text);
    return;
  }
  navigator.clipboard.writeText(text).then(function(){
    showToast('Text copied');
  }).catch(function(){
    window.prompt('Copy this text:', text);
  });
}

function nativeShareText(title, text) {
  if (navigator.share) {
    navigator.share({
      title: title || 'Signal 75',
      text: text,
      url: SITE_URL
    }).catch(function(){});
    return;
  }
  copyPostText(text);
}

function pickResultLabel(race, index) {
  var horse = race && race.horses && race.horses[0] ? race.horses[0] : {};
  var result = horse.result || race.result || 'PENDING';
  var position = horse.position || race.position || 0;
  var posText = position && Number(position) > 0 && Number(position) < 40 ? ' - ' + ordinal(Number(position)).toUpperCase() : '';
  var name = horse.name || 'Pick ' + (index + 1);
  if (result === 'WON') return 'Pick ' + (index + 1) + ' - ' + name + ' - WON' + posText;
  if (result === 'PLACED') return 'Pick ' + (index + 1) + ' - ' + name + ' - PLACED' + posText;
  if (result === 'LOST') return 'Pick ' + (index + 1) + ' - ' + name + ' - LOST' + posText;
  if (result === 'VOID') return 'Pick ' + (index + 1) + ' - ' + name + ' - VOID';
  return 'Pick ' + (index + 1) + ' - ' + name + ' - Awaiting result';
}

function buildDailyScorecardText(profit, totalReturn, type) {
  var sign = profit >= 0 ? '+' : '';
  var picks = PICKS_DATA ? (type === 'flat' ? PICKS_DATA.flat : PICKS_DATA.jumps) : [];
  var results = [];
  picks.slice(0,3).forEach(function(race, index) {
    results.push(pickResultLabel(race, index));
  });
  var text = 'Signal 75 Daily Result\n\n';
  text += 'Official £1 each-way Patent\n';
  text += 'Stake: £14\n';
  text += 'Return: £' + Number(totalReturn || 0).toFixed(2) + '\n';
  text += 'Profit/Loss: ' + sign + '£' + Math.abs(profit).toFixed(2) + '\n';
  if (results.length) text += '\nResults:\n' + results.join('\n') + '\n';
  text += '\nEvery result recorded. No deleted losers.\n';
  text += '18+ Gamble responsibly.\n';
  text += SITE_URL;
  return text;
}

function shareDailyScorecard(profit, totalReturn, type) {
  nativeShareText('Signal 75 Daily Result', buildDailyScorecardText(profit, totalReturn, type));
}

function copyDailyScorecard(profit, totalReturn, type) {
  copyPostText(buildDailyScorecardText(profit, totalReturn, type));
}

function postDailyScorecardToX(profit, totalReturn, type) {
  openXPost(buildDailyScorecardText(profit, totalReturn, type));
}

function shareWinnings(profit, type) {
  shareDailyScorecard(profit, profit + 14, type);
}

function buildProofShareText() {
  var p = PERF_DATA || {};
  var stats = getOfficialProofStats(p);
  var days = Number(p.bettingDays || p.completeDays || 0);
  var profit = Number(p.totalProfit || 0);
  var roi = Number(p.roi || 0);
  var sign = profit >= 0 ? '+' : '';
  var text = 'Signal 75 Results\n\n';
  text += 'Official £1 each-way Patent model.\n';
  text += days + ' completed betting day' + (days === 1 ? '' : 's') + '\n';
  text += 'Winners: ' + stats.winners + '\n';
  text += 'Win rate: ' + stats.winRate + '%\n';
  text += 'Place rate: ' + stats.placeRate + '%\n';
  text += 'P/L: ' + sign + '£' + Math.abs(profit).toFixed(2) + '\n';
  text += 'ROI: ' + (roi >= 0 ? '+' : '') + roi + '%\n\n';
  text += 'Every result recorded. No deleted losers.\n';
  text += '18+ Gamble responsibly.\n';
  text += SITE_URL;
  return text;
}

function shareFullProof() {
  nativeShareText('Signal 75 Results', buildProofShareText());
}

function copyProofShareText() {
  copyPostText(buildProofShareText());
}

function postProofToX() {
  openXPost(buildProofShareText());
}

function shareFreePick() {
  var text = 'Today\'s free Signal 75 pick is live.\n\n';
  text += '3-horse £1 each-way Patent model.\n';
  text += 'Pick 1 free.\n';
  text += 'Results updated after racing.\n\n';
  text += '18+ Gamble responsibly.\n';
  text += SITE_URL;
  nativeShareText('Signal 75 Free Pick', text);
}

function insertFreePickShareButton(containerId) {
  var rc = document.getElementById(containerId);
  if (!rc || document.getElementById(containerId + 'ShareFreePick')) return;
  if (!rc.querySelector('.horse-card')) return;
  rc.insertAdjacentHTML('afterbegin',
    '<button id="' + containerId + 'ShareFreePick" onclick="shareFreePick()" style="width:100%;padding:11px;margin:0 0 10px;background:linear-gradient(135deg,#f0c040,#e8a020);border:none;border-radius:11px;color:#050509;font-size:12px;font-weight:900;cursor:pointer">Share Today\'s Pick</button>'
  );
}

/* ═══════════════════════════════════════════
   RENDER — CORE PICK CARDS
═══════════════════════════════════════════ */
function showSkeletons(containerId) {
  var rc = document.getElementById(containerId);
  if (!rc) return;
  rc.innerHTML = '<div class="skeleton-card"></div><div class="skeleton-card"></div><div class="skeleton-card"></div>';
}

function renderPickCards(containerId, groups) {
  var rc = document.getElementById(containerId);
  if (!rc) return;

  // DEFINITIVE FIX: empty groups = show message, never locked cards
  if (!groups || groups.length === 0) {
    var isJumps = (containerId === 'jumpsContainer');
    if (PICKS_MODE === 'topRatedOnly') {
      rc.innerHTML = '';
      if (isJumps) renderJumpsEmptyStateIfNeeded();
      return;
    }
    if (isJumps) {
      rc.innerHTML = '<div class="empty-state"><div class="empty-icon">&#x1F3C7;</div><div style="font-family:\'DM Mono\',monospace;font-size:10px;letter-spacing:.12em;color:#f0c040;text-transform:uppercase;margin-bottom:8px">' + signalDateLine() + '</div><div class="empty-title">No Jumps Card Today</div><div class="empty-sub">Nothing is broken. Today&apos;s Betfair feed does not include any hurdle, chase or bumper races for Signal 75 to score.<br><br><strong style="color:#f0c040;cursor:pointer" onclick="switchTab(&apos;today&apos;)">View today&apos;s Flat selections →</strong></div></div>';
    } else {
      rc.innerHTML = '<div class="empty-state"><div class="empty-icon">&#x1F40E;</div><div style="font-family:\'DM Mono\',monospace;font-size:10px;letter-spacing:.12em;color:#f0c040;text-transform:uppercase;margin-bottom:8px">' + signalDateLine() + '</div><div class="empty-title">No Flat Card Today</div><div class="empty-sub">Nothing is broken. Today&apos;s Betfair feed only has National Hunt racing, so there are no Flat runners for Signal 75 to score.<br><br><strong style="color:#f0c040;cursor:pointer" onclick="switchTab(&apos;jumps&apos;)">View today&apos;s Jumps selections →</strong></div></div>';
    }
    return;
  }

  var visible = freeHorsesPerRace();

  // Pull top horse from each of 3 best races
  var legs = [];
  for (var i = 0; i < Math.min(3, groups.length); i++) {
    var best = groups[i].horses[0];
    if (best) legs.push({horse:best, race:groups[i]});
  }
  // Only pad to 3 if we have at least 1 real pick
  if (legs.length > 0) {
    while (legs.length < 3) legs.push(null);
  }

  var radarMode = groups && groups.length && groups[0] && groups[0].isRadar;
  var legDef = radarMode ? [
    {accent:'var(--gold)',  dotColor:'#f0c040', label:'Watchlist 1 — Not an official pick', sharesTxt:'', locked:false},
    {accent:'var(--green)', dotColor:'#00e87a', label:'Watchlist 2 — Not an official pick', sharesTxt:'', locked:false},
    {accent:'var(--blue)',  dotColor:'#38bdf8', label:'Watchlist 3 — Not an official pick', sharesTxt:'', locked:false}
  ] : [
    {accent:'var(--gold)',  dotColor:'#f0c040', label:'Pick 1 — Free',    sharesTxt:'',          locked:false},
    {accent:'var(--green)', dotColor:'#00e87a', label:'Pick 2 — Locked',  sharesTxt:'Share once — free',   locked:true},
    {accent:'var(--blue)',  dotColor:'#38bdf8', label:'Pick 3 — Locked',  sharesTxt:'Share twice — free',  locked:true}
  ];

  var html = '';

  html += '<div style="text-align:center;margin:10px 0 14px">';
  html += '<a href="/how-it-works.html" style="display:inline-block;border:1px solid rgba(240,192,64,.35);border-radius:10px;padding:11px 15px;font-family:\'DM Mono\',monospace;font-size:10px;color:#f0c040;letter-spacing:.08em;text-transform:uppercase;background:rgba(240,192,64,.05)">How Signal 75 Works →</a>';
  html += '</div>';


  for (var i = 0; i < 3; i++) {
    var lp  = legs[i];
    var ld  = legDef[i];
    var isVis = i < visible;

    if (!lp) { continue; }

    var isRadarLeg = !!(lp && ((lp.race && lp.race.isRadar) || (lp.horse && lp.horse.isRadar)));
    if (isRadarLeg) {
      ld = {
        accent: i === 0 ? 'var(--gold)' : i === 1 ? 'var(--green)' : 'var(--blue)',
        dotColor: i === 0 ? '#f0c040' : i === 1 ? '#00e87a' : '#38bdf8',
        label: 'Watchlist ' + (i + 1) + ' — Not an official pick',
        sharesTxt: i === 1 ? 'Share once' : 'Share twice',
        locked: true
      };
    }

    if (isVis && lp) {
      // ── VISIBLE CARD ──
      var h     = lp.horse;
      var sc    = parseInt(h.score || h.signal_score || 0);
      if (!h.bd) h.bd = {os:sc||50,ts:50,fs:sc||50,fm:sc||50};
      h.bd.os = h.bd.os || 50; h.bd.ts = h.bd.ts || 50; h.bd.fs = h.bd.fs || 50; h.bd.fm = h.bd.fm || 50;
      var scCol = sCol(sc);
      var safeN = (h.name||'').replace(/['"<>]/g,'');
      var jockeyText = h.jockey || '';
      if (/radar/i.test(jockeyText)) jockeyText = 'Watchlist pick';
      var typCls = ({flat:'rt-flat',hurdle:'rt-hurdle',chase:'rt-chase'}[lp.race.type]) || 'rt-flat';

      html += '<div class="horse-card" id="'+(containerId==='jumpsContainer'?'jhcard':'hcard')+i+'">';

      // Leg bar
      html += '<div class="card-leg" style="color:'+ld.accent+'">';
      html += '<div class="card-leg-dot" style="background:'+ld.dotColor+'"></div>';
      html += ld.label + ' &nbsp;&middot;&nbsp; ' + lp.race.time + ' ' + lp.race.course;
      html += '</div>';

      // Main row — tappable
      html += '<div class="card-main" onclick="toggleExpand('+i+')">';
      html += '<div style="flex:1;min-width:0">';
      html += '<div class="card-name">'+h.name+'</div>';
      var displayReason = displayReasonText(h.reason);
      var whyWords = displayReason.split(' ').slice(0,8).join(' ');
      if (whyWords) html += '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;margin-top:3px">&#x26A1; '+safeText(whyWords)+'</div>';
      html += '<div style="font-family:\'DM Mono\',monospace;font-size:10px;color:#C8C8E0;margin-top:2px">'+jockeyText+'</div>';
      var formText = String(h.formStr || h.form || '').trim();
      if (formText) html += '<div class="card-form">Form: <strong>'+safeText(formText)+'</strong></div>';
      html += '</div>';
      html += '<div style="text-align:right;flex-shrink:0;display:flex;flex-direction:column;align-items:flex-end;gap:4px">';
      html += '<div class="card-score" style="color:'+scCol+'"><span>'+sc+'</span><span style="display:block;font-family:\'DM Mono\',monospace;font-size:9px;line-height:1;color:'+scCol+';letter-spacing:0">pts</span></div>';
      html += '<div class="card-odds">'+decToFrac(h.odds)+'</div>';
      html += '</div>';
      html += '</div>'; // end card-main

      // Score bar
      html += '<div class="card-bar">';
      html += '<div class="card-bar-track">';
      html += '<div class="card-bar-fill" style="width:'+sc+'%;background:linear-gradient(90deg,'+ld.dotColor+',var(--green))"></div>';
      html += '</div>';
      html += '<div class="card-bar-lbl">Signal 75: <strong style="color:'+scCol+'">'+sc+'/100</strong> &nbsp;&middot;&nbsp; '+signalStrengthLabel(sc)+'</div>';

      // Trust chips
      html += '<div class="card-trust score-trust">';
      var tipsterCount = parseInt(h.tipsters || 0);
      html += '<div class="trust-chip">&#x2714; '+tipsterCount+' '+(tipsterCount === 1 ? 'tipster' : 'tipsters')+'</div>';
      html += '<div class="trust-chip">&#x2714; Race fit</div>';
      if (isRadarLeg || h.isRadar) {
        html += '<div class="trust-chip">BSP: '+decToFrac(h.odds || h.bsp)+'</div>';
      } else if (h.bd.os >= 65) {
        html += '<div class="trust-chip">&#x2714; Price OK</div>';
      }
      if (h.formWarning) {
        html += '<div class="trust-chip warn">Form caution</div>';
      }
      html += '</div>';
      if (isRadarLeg || h.isRadar) {
        var rr = radarReason(h);
        html += '<div class="radar-reason" style="color:'+rr.colour+';font-size:10px;font-family:\'DM Mono\',monospace;margin-top:6px;padding:6px 8px;border-radius:6px;background:rgba(255,255,255,0.04);line-height:1.45">'+rr.label+'</div>';
      }
      html += weatherRiskHtml(lp.race, h);
      html += scoreBreakdownHtml(h, sc, isRadarLeg || h.isRadar);
      html += '</div>';

      // Expand panel
      html += '<div class="card-expand" id="exp'+i+'">';
      var bds = [['Value',h.bd.os,'var(--gold)'],['Tipsters',h.bd.ts,'var(--green)'],['Field',h.bd.fs,'var(--blue)'],['Form',h.bd.fm,'var(--muted)']];
      html += '<div class="expand-grid">';
      for (var bi=0; bi<bds.length; bi++) {
        html += '<div class="expand-cell">';
        html += '<div class="expand-val" style="color:'+sCol(bds[bi][1])+'">'+bds[bi][1]+'</div>';
        html += '<div class="expand-lbl">'+bds[bi][0]+'</div>';
        html += '</div>';
      }
      html += '</div>';
      html += '<div class="expand-reason">"'+safeText(displayReason || h.reason)+'"</div>';
      html += '<div class="expand-bets">';
      html += '<a href="https://www.bet365.com" target="_blank" rel="sponsored noopener" class="bet-btn bet-btn-365" onclick="event.stopPropagation()">Bet365</a>';
      html += '<a href="https://www.paddypower.com" target="_blank" rel="sponsored noopener" class="bet-btn bet-btn-pp" onclick="event.stopPropagation()">Paddy Power</a>';
      html += '</div>';
      html += '<div class="aff-note">&#x26A0; Affiliate links &middot; 18+ &middot; BeGambleAware.org</div>';
      html += '</div>'; // end expand

      if ((isRadarLeg || h.isRadar) && (h.radarResult || h.result || h.position)) {
        html += radarResultPanelHtml(h, lp.race);
      }

      html += '</div>'; // end horse-card

    } else {
      // ── LOCKED CARD — ZERO horse data in DOM ──
      if (!lp) { continue; }
      var shareTxt = ld.sharesTxt || '1 share';
      html += '<div class="locked-card" onclick="openUnlockModal()">';

      html += '<div class="card-leg" style="color:'+ld.accent+'">&#x1F512; '+ld.label+'</div>';

      html += '<div class="locked-top">';
      html += '<div class="locked-icon">&#x1F512;</div>';
      html += '<div class="locked-info">';
      html += '<div class="locked-leg-lbl" style="color:'+ld.accent+'">&#x2705; '+(isRadarLeg ? 'Watchlist horse' : 'Pick '+(i+1)+' selected')+'</div>';
      html += '<div class="locked-name-blur">XXXXXXX XXXXX</div>';
      html += '<div class="locked-sub">'+(isRadarLeg ? 'Not counted in results' : 'Tap to see the horse — free or £3')+'</div>';
      html += '</div>';
      html += '<div class="locked-score-blur">??</div>';
      html += '</div>';

      html += '<div class="locked-btns">';
      html += '<button class="unlock-btn unlock-share" onclick="openReferralModal();event.stopPropagation()">&#x1F517; '+shareTxt+' — free</button>';
      html += '<a href="'+COFFEE_URL+'" target="_blank" rel="noopener" class="unlock-btn unlock-coffee" onclick="onCoffeeClick();event.stopPropagation()">&#x2615; Coffee ~£3</a>';
      html += '</div>';

      html += '</div>'; // end locked-card
    }
  }

  if (!html || NO_BET_DAY) {
  }

  rc.innerHTML = html;
}

function buildJumpsDisplayGroups() {
  processRaces(MOCK_JUMPS || []);
  var jumpGroups = raceGroups.slice();
  var jumpsRadarSource = (TOP_RATED_JUMPS && TOP_RATED_JUMPS.length) ? TOP_RATED_JUMPS : [];

  if (jumpGroups.length < 3 && jumpsRadarSource && jumpsRadarSource.length) {
    var jumpsUsed = {};
    jumpGroups.forEach(function(g){
      if (g.horses && g.horses[0] && g.horses[0].name) {
        jumpsUsed[g.horses[0].name.toLowerCase()] = true;
      }
    });

    jumpsRadarSource.forEach(function(h) {
      if (jumpGroups.length >= 3) return;
      var raceStr = (h.race || h.race_type || h.type || '').toLowerCase();
      var isJumpsHorse = raceStr.indexOf('hrd') > -1 || raceStr.indexOf('hurdle') > -1 ||
                         raceStr.indexOf('chs') > -1 || raceStr.indexOf('chase') > -1 ||
                         raceStr.indexOf('nhf') > -1 || raceStr.indexOf('bumper') > -1 ||
                         ((h.race_type || h.type) && String(h.race_type || h.type).toLowerCase() !== 'flat');
      var key = (h.name || '').toLowerCase();
      if (!isJumpsHorse || !key || jumpsUsed[key]) return;

      jumpGroups.push({
        course: h.venue || h.course || '',
        time: h.time || '',
        type: 'jumps',
        distance: '',
        runners: h.runners || 8,
        isRadar: true,
        horses: [{
          name: h.name,
          signal_score: parseInt(h.signal_score || h.qualificationScore || 0),
          score: parseInt(h.signal_score || h.qualificationScore || 0),
          odds: parseFloat(h.odds) || 0,
          jockey: h.jockey || 'Watchlist pick',
          trainer: '',
          tipsters: h.tipsters || 0,
          formStr: h.form || '',
          reason: 'Strong Signal 75 score, but not an official pick under today\'s tipster/value rules.',
          badge: h.badge || 'Watchlist',
          isRadar: true,
          radarLabel: 'Next Best',
          radarResult: h.radarResult || '',
          result: h.result || '',
          position: h.position || 0,
          status: h.status || '',
          bd: {
            os: parseInt(h.signal_score || h.qualificationScore || 50),
            ts: 50,
            fs: parseInt(h.signal_score || h.qualificationScore || 50),
            fm: 50
          }
        }]
      });
      jumpsUsed[key] = true;
    });
  }

  return jumpGroups;
}

function buildFlatDisplayGroups() {
  processRaces(MOCK_RACES || []);
  var flatGroups = raceGroups.slice();
  var flatRadarSource = (TOP_RATED_FLAT && TOP_RATED_FLAT.length) ? TOP_RATED_FLAT : [];

  if (flatGroups.length < 3 && flatRadarSource.length) {
    var flatUsed = {};
    flatGroups.forEach(function(g){
      if (g.horses && g.horses[0] && g.horses[0].name) {
        flatUsed[g.horses[0].name.toLowerCase()] = true;
      }
    });

    flatRadarSource.forEach(function(h) {
      if (flatGroups.length >= 3) return;
      var raceStr = (h.race || h.race_type || h.type || '').toLowerCase();
      var typeStr = String(h.race_type || h.type || '').toLowerCase();
      var isKnownJumps = raceStr.indexOf('hrd') > -1 || raceStr.indexOf('hurdle') > -1 ||
                         raceStr.indexOf('chs') > -1 || raceStr.indexOf('chase') > -1 ||
                         raceStr.indexOf('nhf') > -1 || raceStr.indexOf('bumper') > -1 ||
                         typeStr.indexOf('hurdle') > -1 || typeStr.indexOf('chase') > -1 ||
                         typeStr.indexOf('jumps') > -1;
      var isFlatHorse = typeStr.indexOf('flat') > -1 || raceStr.indexOf('flat') > -1 || !isKnownJumps;
      var key = (h.name || '').toLowerCase();
      if (!isFlatHorse || !key || flatUsed[key]) return;

      flatGroups.push({
        course: h.venue || h.course || '',
        time: h.time || '',
        type: 'flat',
        distance: '',
        runners: h.runners || 8,
        isRadar: true,
        horses: [{
          name: h.name,
          signal_score: parseInt(h.signal_score || h.qualificationScore || 0),
          score: parseInt(h.signal_score || h.qualificationScore || 0),
          odds: parseFloat(h.odds) || 0,
          jockey: h.jockey || 'Watchlist pick',
          trainer: '',
          tipsters: h.tipsters || 0,
          formStr: h.form || '',
          reason: 'Strong Signal 75 score, but not an official pick under today\'s tipster/value rules.',
          badge: h.badge || 'Watchlist',
          isRadar: true,
          radarLabel: 'Next Best',
          radarResult: h.radarResult || '',
          result: h.result || '',
          position: h.position || 0,
          status: h.status || '',
          bd: {
            os: parseInt(h.signal_score || h.qualificationScore || 50),
            ts: 50,
            fs: parseInt(h.signal_score || h.qualificationScore || 50),
            fm: 50
          }
        }]
      });
      flatUsed[key] = true;
    });
  }

  return flatGroups;
}

function toggleExpand(i) {
  var el = document.getElementById('exp'+i);
  if (!el) return;
  el.classList.toggle('open');
}

/* ═══════════════════════════════════════════
   PROOF STRIP UPDATE
═══════════════════════════════════════════ */
function loadPerformance(silent) {
  silent = !!silent;
  fetch('performance.json?v=' + Date.now(), { cache: 'no-store' })
    .then(function(r) { return r.json(); })
    .then(function(p) {
      var signature = stableDataSignature(p);
      if (silent && signature === LAST_PERFORMANCE_SIGNATURE) return;
      LAST_PERFORMANCE_SIGNATURE = signature;

      p.bettingDays = p.bettingDays || p.completeDays || 0;
      p.profitableDays = p.profitableDays || 0;
      if (!p || p.bettingDays === 0) {
        // Clean empty state — no real results data yet
        var ss = document.getElementById('stripStrike');
        var sp = document.getElementById('stripProfit');
        var sb = document.getElementById('stripBetDays');
        var sr = document.getElementById('stripRoi');
        if (ss) ss.textContent = '0';
        if (sp) { sp.textContent = '£0'; sp.style.color = 'var(--green)'; }
        if (sb) sb.textContent = '0';
        if (sr) sr.textContent = '0%';
        var el = document.getElementById('proofHeroAmt');
        if (el) { el.textContent = '£0'; el.style.color = 'var(--green)'; el.dataset.live = '1'; }
        var ep = document.getElementById('proofHeroPeriod');
        if (ep) { ep.textContent = '0 betting days · 0 profitable · 0% ROI'; ep.dataset.live = '1'; }
        var label = document.querySelector('.proof-hero-label');
        if (label) label.textContent = '📊 Results start from 24 May 2026 value-band reset';
        var snapEl = document.getElementById('proofSnapshot');
        if (snapEl) snapEl.innerHTML =
          '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">0</div><div class="snap-lbl">Winners</div></div>' +
          '<div class="snap-cell"><div class="snap-val" style="color:var(--gold)">0%</div><div class="snap-lbl">Win Rate</div></div>' +
          '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">0%</div><div class="snap-lbl">Place Rate</div></div>';
        var bpEl = document.getElementById('statBestPatent');
        if (bpEl) { bpEl.textContent = '£0'; bpEl.style.color = 'var(--green)'; }
        var bpSub = document.getElementById('statBestPatentSub');
        if (bpSub) bpSub.textContent = 'No results yet';
        var roiEl2 = document.getElementById('statOverallRoi');
        if (roiEl2) roiEl2.textContent = '0%';
        var patentEl = document.getElementById('statPatentCount');
        if (patentEl) patentEl.textContent = '0 patents · £0 staked';
        var profitEl = document.getElementById('statTotalProfit');
        if (profitEl) profitEl.textContent = '£0 total profit';
        var canvas = document.getElementById('proofChart');
        if (canvas && window.proofChartInst) { window.proofChartInst.destroy(); window.proofChartInst = null; }
        var chartLbl = document.getElementById('proofChartLbl');
        if (chartLbl) chartLbl.textContent = 'awaiting first official result';
        var luEl = document.querySelector('.proof-last-updated');
        var allEls = document.querySelectorAll('[id*="lastUpdated"]');
        return;
      }
      // Update proof strip
      var ss = document.getElementById('stripStrike');
      var proofStats = getOfficialProofStats(p);
      if (ss) { ss.textContent = proofStats.winners; ss.dataset.live = '1'; }
      var sp = document.getElementById('stripProfit');
      if (sp) { sp.dataset.live = '1';
        sp.textContent = (p.totalProfit >= 0 ? '+' : '') + '£' + p.totalProfit.toFixed(0);
        sp.style.color = p.totalProfit >= 0 ? 'var(--green)' : 'var(--red,#ff4d6d)';
      }
      // Update ROI hardcoded element
      var roiEls = document.querySelectorAll('.proof-strip .strip-cell');
      // Update bet days
      var bdEl = document.getElementById('stripBetDays');
      if (bdEl) bdEl.textContent = p.bettingDays;
      var roiEl = document.getElementById('stripRoi');
      if (roiEl) { roiEl.textContent = p.roi + '%'; roiEl.style.color = p.roi >= 0 ? 'var(--gold)' : 'var(--red,#ff4d6d)'; }
      // Update proof hero
      var el = document.getElementById('proofHeroAmt');
      if (el) { el.dataset.live = '1';
        el.textContent = (p.totalProfit >= 0 ? '+' : '') + '£' + p.totalProfit.toFixed(0);
        el.style.color = p.totalProfit >= 0 ? 'var(--green)' : 'var(--red,#ff4d6d)';
      }
      PERF_DATA = p;
      renderLatestScorecardBlock();
      var ep = document.getElementById('proofHeroPeriod');
      if (ep) { ep.dataset.live = '1'; ep.textContent = p.bettingDays + ' betting days · ' + p.profitableDays + ' profitable · ' + p.roi + '% ROI'; }
      // Update proof hero label
      var label = document.querySelector('.proof-hero-label');
      if (label) {
        if (p.bettingDays >= 5) {
          label.textContent = '📊 Live Results — Official Qualified Picks Only';
        } else {
          label.textContent = '📊 Live Tracking — ' + p.bettingDays + ' completed days so far';
        }
      }
      // Update proof hero copy
      var copy = document.querySelector('.proof-hero-copy');
      if (copy && p.bettingDays > 0) {
        copy.textContent = 'Backing 3 official picks as a £1 each-way Patent';
      }
      // Update stat cards
      var bestPatentEl = document.querySelector('.proof-hero');
      // Update snapshot cards from real data
      var snapEl = document.getElementById('proofSnapshot');
      if (snapEl) {
        snapEl.innerHTML =
          '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">' + proofStats.winners + '</div><div class="snap-lbl">Winners</div></div>' +
          '<div class="snap-cell"><div class="snap-val" style="color:var(--gold)">' + proofStats.winRate + '%</div><div class="snap-lbl">Win Rate</div></div>' +
          '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">' + proofStats.placeRate + '%</div><div class="snap-lbl">Place Rate</div></div>';
      }

      // Refresh proof tab with real data now that PERF_DATA is set
      if (document.getElementById('panel-proof') && document.getElementById('panel-proof').classList.contains('active')) {
        renderProofTab();
      }

      // Update overall ROI card
      var roiEl2 = document.getElementById('statOverallRoi');
      if (roiEl2) roiEl2.textContent = (p.roi >= 0 ? '+' : '') + p.roi + '%';
      var patentEl = document.getElementById('statPatentCount');
      if (patentEl) patentEl.textContent = p.bettingDays + ' patents · £' + p.totalStaked.toFixed(0) + ' staked';
      var profitEl = document.getElementById('statTotalProfit');
      if (profitEl) profitEl.textContent = (p.totalProfit >= 0 ? '+' : '') + '£' + p.totalProfit.toFixed(2) + ' total profit';
      // Best patent
      if (p.bestDay) {
        var bpEl = document.getElementById('statBestPatent');
        if (bpEl) bpEl.textContent = (p.bestDay.profit >= 0 ? '+' : '') + '£' + p.bestDay.profit.toFixed(2);
        var bpSub = document.getElementById('statBestPatentSub');
        if (bpSub) {
          var bd = new Date(p.bestDay.date);
          var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
          bpSub.textContent = months[bd.getMonth()] + ' ' + bd.getFullYear();
        }
      }
    })
    .catch(function() {
      // performance.json not found — keep defaults
    });
}

function refreshLiveData(silent) {
  loadRaces(!!silent);
  loadPerformance(!!silent);
}

function startLiveRefresh() {
  if (LIVE_REFRESH_STARTED) return;
  LIVE_REFRESH_STARTED = true;

  setInterval(function() {
    refreshLiveData(true);
  }, 60000);

  window.addEventListener('focus', function() {
    refreshLiveData(true);
  });

  document.addEventListener('visibilitychange', function() {
    if (!document.hidden) refreshLiveData(true);
  });
}

function updateProofStrip() {
  var dot = document.querySelector('.topbar-dot');
  var aiLive = document.getElementById('aiLiveTap');
  if (PICKS_STALE) {
    if (dot) { dot.style.background = 'var(--gold)'; dot.style.boxShadow = '0 0 8px #f0c040, 0 0 16px #f0c040'; }
    if (aiLive) { aiLive.style.color = 'var(--gold)'; aiLive.textContent = 'UPDATING'; }
  } else if (PICKS_MODE === 'topRatedOnly' || NO_BET_DAY) {
    if (dot) { dot.style.background = 'var(--gold)'; dot.style.boxShadow = '0 0 8px #f0c040, 0 0 16px #f0c040'; }
    if (aiLive) { aiLive.style.color = 'var(--gold)'; aiLive.textContent = 'WATCHLIST'; }
    var picksSub = document.querySelector('.picks-sub');
    if (picksSub) picksSub.textContent = 'No official picks today — showing Watchlist horses. These scored well but did not meet every official pick rule. Not counted in proof.';
  } else if (NO_BET_DAY) {
    if (dot) { dot.style.background = '#ff4d6d'; dot.style.boxShadow = '0 0 8px #ff4d6d, 0 0 16px #ff4d6d'; }
    if (aiLive) { aiLive.style.color = '#ff4d6d'; aiLive.textContent = 'NO PICKS'; }
    var picksSub = document.querySelector('.picks-sub');
    if (picksSub) picksSub.textContent = 'No qualifying selections today — Watchlist horses shown below. Not counted in proof.';
  } else {
    if (dot) { dot.style.background = '#00F080'; dot.style.boxShadow = '0 0 8px #00F080, 0 0 16px #00F080'; }
    if (aiLive) { aiLive.style.color = '#00F080'; aiLive.textContent = 'AI LIVE'; }
  }
  var total = trackRecord.length;
  var allH = [];
  trackRecord.forEach(function(p){ p.horses.forEach(function(h){ allH.push(h); }); });
  var wins = allH.filter(function(h){ return h.result==='WON'; }).length;
  var profit = trackRecord.reduce(function(s,p){ return s+p.patentProfit; }, 0);
  var sp = document.getElementById('stripProfit');
  if (sp && !sp.dataset.live) { sp.textContent = '+£'+Math.round(profit); sp.style.color='var(--green)'; }
  var ss = document.getElementById('stripStrike');
  if (ss && !ss.dataset.live) ss.textContent = wins;
}

function getOfficialProofStats(perf) {
  var total = 0, winners = 0, placedOnly = 0;
  if (perf && perf.selectionStats) {
    total = Number(perf.selectionStats.total || 0);
    winners = Number(perf.selectionStats.winners || 0);
    placedOnly = Number(perf.selectionStats.placed || 0);
  } else if (perf && perf.selectionLog) {
    perf.selectionLog.forEach(function(day) {
      if (!day.complete || !day.selections) return;
      day.selections.forEach(function(sel) {
        total += 1;
        if (sel.result === 'WON') winners += 1;
        if (sel.result === 'PLACED') placedOnly += 1;
      });
    });
  }
  var placedIncludingWinners = winners + placedOnly;
  return {
    total: total,
    winners: winners,
    placed: placedIncludingWinners,
    winRate: total ? Number(((winners / total) * 100).toFixed(1)) : 0,
    placeRate: total ? Number(((placedIncludingWinners / total) * 100).toFixed(1)) : 0
  };
}

function loadLatestScorecard(silent) {
  if (LATEST_SCORECARD_LOADING) return;
  LATEST_SCORECARD_LOADING = true;
  fetch('data/public_scorecards/latest_scorecard.json?v=' + Date.now(), { cache: 'no-store' })
    .then(function(r) {
      if (!r.ok) throw new Error('No latest scorecard yet');
      return r.json();
    })
    .then(function(card) {
      LATEST_SCORECARD = card;
      LATEST_SCORECARD_LOADING = false;
      renderLatestScorecardBlock();
    })
    .catch(function() {
      LATEST_SCORECARD_LOADING = false;
      if (!silent) renderLatestScorecardBlock();
    });
}

function latestPerformanceScorecard() {
  if (!PERF_DATA || !Array.isArray(PERF_DATA.selectionLog)) return null;
  var day = null;
  for (var i = 0; i < PERF_DATA.selectionLog.length; i++) {
    if (PERF_DATA.selectionLog[i] && PERF_DATA.selectionLog[i].complete === true) {
      day = PERF_DATA.selectionLog[i];
      break;
    }
  }
  if (!day || !day.date) return null;
  var picks = Array.isArray(day.selections) ? day.selections : [];
  var winners = 0;
  var placed = 0;
  picks.forEach(function(p) {
    if (p.result === 'WON') {
      winners += 1;
      placed += 1;
    } else if (p.result === 'PLACED') {
      placed += 1;
    }
  });
  return {
    date: day.date,
    complete: true,
    no_bet_day: day.mode === 'topRatedOnly' || day.mode === 'noBetDay' || picks.length === 0,
    daily_stake: Number(day.totalStake || 14),
    return: Number(day.patentReturn || 0),
    profit: Number(day.patentProfit || 0),
    official_picks: picks.map(function(p, idx) {
      var position = Number(p.position || 0);
      var suffix = position === 1 ? 'ST' : position === 2 ? 'ND' : position === 3 ? 'RD' : 'TH';
      var result = p.result || 'PENDING';
      return {
        pick_number: idx + 1,
        horse: p.name || p.horse || '',
        display_result: result === 'WON' || result === 'PLACED' ? result + ' - ' + position + suffix : (position ? position + suffix : result),
        result: result
      };
    }),
    winners: winners,
    place_rate: picks.length ? Number(((placed / picks.length) * 100).toFixed(1)) : 0,
    radar: null
  };
}

function scorecardMoney(value) {
  value = Number(value || 0);
  if (value < 0) return '-£' + Math.abs(value).toFixed(2);
  if (value > 0) return '+£' + value.toFixed(2);
  return '£0.00';
}

function renderLatestScorecardBlock() {
  var el = document.getElementById('latestScorecardBlock');
  if (!el) return;
  var perfCard = latestPerformanceScorecard();
  var card = LATEST_SCORECARD;
  if (perfCard && (!card || !card.date || String(perfCard.date) > String(card.date))) {
    card = perfCard;
  }
  if (!card || !card.date) {
    el.innerHTML = '';
    return;
  }

  var profit = Number(card.profit || 0);
  var profitColor = profit >= 0 ? 'var(--green)' : 'var(--red,#ff4d6d)';
  var picks = (card.official_picks || []).slice(0, 3);
  var html = '';

  html += '<div style="background:linear-gradient(135deg,rgba(0,232,122,.06),rgba(240,192,64,.04));border:1px solid rgba(240,192,64,.22);border-radius:14px;padding:13px;margin-bottom:12px">';
  html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:9px">';
  html += '<div style="min-width:0">';
  html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0;text-transform:uppercase;letter-spacing:.12em">Latest Daily Result</div>';
  html += '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:20px;color:var(--text);letter-spacing:.7px;margin-top:2px">' + safeText(card.date) + '</div>';
  html += '</div>';
  html += '<div style="text-align:right;flex-shrink:0">';
  html += '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:24px;color:' + profitColor + ';line-height:1">' + scorecardMoney(card.profit) + '</div>';
  html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0;margin-top:3px">from £' + Number(card.daily_stake || 0).toFixed(0) + ' stake</div>';
  html += '</div></div>';

  if (card.no_bet_day) {
    html += '<div style="font-size:11px;color:#E8E8F8;line-height:1.6">No official Patent that day. No forced bet.</div>';
  } else {
    html += '<div style="display:grid;grid-template-columns:1fr;gap:6px">';
    picks.forEach(function(p, idx) {
      var result = p.display_result || p.result || 'PENDING';
      var resultUpper = String(result).toUpperCase();
      var color = resultUpper.indexOf('WON') >= 0 ? 'var(--green)' : resultUpper.indexOf('PLACED') >= 0 ? 'var(--gold)' : '#C8C8E0';
      html += '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;background:rgba(0,0,0,.16);border:1px solid rgba(255,255,255,.055);border-radius:10px;padding:8px 9px">';
      html += '<div style="min-width:0;font-size:11px;font-weight:800;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + (idx + 1) + '. ' + safeText(p.horse) + '</div>';
      html += '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:' + color + ';font-weight:900;white-space:nowrap">' + safeText(result) + '</div>';
      html += '</div>';
    });
    html += '</div>';
    html += '<div style="display:flex;justify-content:space-between;gap:8px;margin-top:9px;font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0">';
    html += '<span>' + Number(card.winners || 0) + ' winners</span>';
    html += '<span>' + Number(card.place_rate || 0).toFixed(1) + '% place rate</span>';
    html += '<span>Return £' + Number(card.return || 0).toFixed(2) + '</span>';
    html += '</div>';
  }

  if (card.radar && Number(card.radar.pick_count || 0) > 0) {
    html += '<div style="margin-top:8px;font-size:9px;color:#9090A8;line-height:1.5">Watchlist: ' + Number(card.radar.pick_count || 0) + ' horses shown separately. Watchlist horses are not counted in official results.</div>';
  }

  html += '</div>';
  el.innerHTML = html;
}

function renderProofHero(days) {
  var allH = [];
  trackRecord.forEach(function(p){ p.horses.forEach(function(h){ allH.push(h); }); });
  var wins = allH.filter(function(h){ return h.result==='WON'; }).length;
  var places = allH.filter(function(h){ return h.result==='WON' || h.result==='PLACED'; }).length;
  var winRate = allH.length ? Math.round((wins/allH.length)*100) : 0;
  var placeRate = allH.length ? Math.round((places/allH.length)*100) : 0;
  var profit = trackRecord.reduce(function(s,p){ return s+p.patentProfit; }, 0);
  var profPats = trackRecord.filter(function(p){ return p.patentProfit>0; }).length;
  var roi = trackRecord.length ? Math.round((profit/(trackRecord.length*14))*100) : 0;

  var el = document.getElementById('proofHeroAmt');
  if (el && !el.dataset.live) { el.textContent = '+£'+Math.round(profit); el.style.color='var(--green)'; }
  var ep = document.getElementById('proofHeroPeriod');
  if (ep && !ep.dataset.live) ep.textContent = trackRecord.length+' patents · '+profPats+' profitable · ROI '+roi+'%';
  var eb = document.getElementById('proofHeroBasis');
  if (eb) eb.textContent = allH.length+' horses · '+wins+' won · '+winRate+'% win rate · '+placeRate+'% place rate';
  updateProofStrip();
}

function renderProofSnapshot(days) {
  var el = document.getElementById('proofSnapshot');
  if (!el) return;
  if (PERF_DATA) {
    var stats = getOfficialProofStats(PERF_DATA);
    el.innerHTML =
      '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">' + stats.winners + '</div><div class="snap-lbl">Winners</div></div>' +
      '<div class="snap-cell"><div class="snap-val" style="color:var(--gold)">' + stats.winRate + '%</div><div class="snap-lbl">Win Rate</div></div>' +
      '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">' + stats.placeRate + '%</div><div class="snap-lbl">Place Rate</div></div>';
    return;
  }
  var ps = calcPerfStats(days);
  el.innerHTML =
    '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">' + ps.wins + '</div><div class="snap-lbl">Winners</div></div>' +
    '<div class="snap-cell"><div class="snap-val" style="color:var(--gold)">' + ps.strike + '%</div><div class="snap-lbl">Win Rate</div></div>' +
    '<div class="snap-cell"><div class="snap-val" style="color:var(--green)">0%</div><div class="snap-lbl">Place Rate</div></div>';
}

function drawSimpleProofChart(canvas, labels, data, labelText) {
  if (!canvas || !data || !data.length) return;
  var ratio = window.devicePixelRatio || 1;
  var width = canvas.clientWidth || 320;
  var height = canvas.clientHeight || 150;
  canvas.width = Math.max(1, Math.floor(width * ratio));
  canvas.height = Math.max(1, Math.floor(height * ratio));

  var ctx = canvas.getContext && canvas.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  var padL = 28, padR = 10, padT = 14, padB = 24;
  var min = Math.min.apply(null, data);
  var max = Math.max.apply(null, data);
  if (min === max) { min -= 1; max += 1; }
  var plotW = Math.max(1, width - padL - padR);
  var plotH = Math.max(1, height - padT - padB);

  function xAt(i) {
    return padL + (data.length === 1 ? plotW / 2 : (i / (data.length - 1)) * plotW);
  }
  function yAt(v) {
    return padT + (1 - ((v - min) / (max - min))) * plotH;
  }

  ctx.strokeStyle = 'rgba(255,255,255,0.07)';
  ctx.lineWidth = 1;
  for (var g = 0; g < 4; g++) {
    var gy = padT + (plotH / 3) * g;
    ctx.beginPath();
    ctx.moveTo(padL, gy);
    ctx.lineTo(width - padR, gy);
    ctx.stroke();
  }

  ctx.fillStyle = 'rgba(200,200,224,0.65)';
  ctx.font = '9px monospace';
  ctx.fillText('£' + max.toFixed(0), 2, padT + 4);
  ctx.fillText('£' + min.toFixed(0), 2, padT + plotH);

  var gradient = ctx.createLinearGradient(0, padT, 0, padT + plotH);
  gradient.addColorStop(0, 'rgba(0,232,122,0.25)');
  gradient.addColorStop(1, 'rgba(0,232,122,0.02)');
  ctx.beginPath();
  data.forEach(function(v, i) {
    var x = xAt(i), y = yAt(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(xAt(data.length - 1), padT + plotH);
  ctx.lineTo(xAt(0), padT + plotH);
  ctx.closePath();
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  data.forEach(function(v, i) {
    var x = xAt(i), y = yAt(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = '#00e87a';
  ctx.lineWidth = 2;
  ctx.stroke();

  data.forEach(function(v, i) {
    ctx.beginPath();
    ctx.arc(xAt(i), yAt(v), 3, 0, Math.PI * 2);
    ctx.fillStyle = '#00e87a';
    ctx.fill();
  });

  if (labels && labels.length) {
    ctx.fillStyle = 'rgba(200,200,224,0.55)';
    ctx.font = '9px monospace';
    ctx.fillText(labels[0], padL, height - 6);
    if (labels.length > 1) {
      var last = labels[labels.length - 1];
      ctx.fillText(last, Math.max(padL, width - padR - ctx.measureText(last).width), height - 6);
    }
  }

  var chartLbl = document.getElementById('proofChartLbl');
  if (chartLbl && labelText) chartLbl.textContent = labelText;
}

function renderProofChart(days) {
  var canvas = document.getElementById('proofChart');
  if (!canvas) return;
  if (proofChartInst && proofChartInst.destroy) { proofChartInst.destroy(); proofChartInst = null; }
  // Show empty state if no real results data
  if ((!PERF_DATA || !PERF_DATA.recentResults || PERF_DATA.recentResults.length === 0) && trackRecord.length === 0) {
    var wrap = canvas.parentElement;
    if (wrap) {
      canvas.style.display = 'none';
      var msg = wrap.querySelector('.chart-empty-msg');
      if (!msg) {
        msg = document.createElement('div');
        msg.className = 'chart-empty-msg';
        msg.style.cssText = 'text-align:center;padding:32px 16px;font-family:\'DM Mono\',monospace;font-size:11px;color:#6060a0';
        msg.textContent = 'Awaiting first official result';
        wrap.appendChild(msg);
      }
    }
    return;
  }
  canvas.style.display = '';
  var existingMsg = canvas.parentElement && canvas.parentElement.querySelector('.chart-empty-msg');
  if (existingMsg) existingMsg.remove();
  if (PERF_DATA && PERF_DATA.recentResults && PERF_DATA.recentResults.length > 0) {
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var labels = [], data = [], running = 0;
    var sorted2 = PERF_DATA.recentResults.slice().reverse();
    sorted2.forEach(function(r) {
      running += r.profit;
      var d = new Date(r.date);
      labels.push(months[d.getMonth()] + ' ' + d.getDate());
      data.push(+running.toFixed(2));
    });
    if (typeof Chart === 'undefined') {
      drawSimpleProofChart(canvas, labels, data, 'official £1 each-way results · ' + PERF_DATA.bettingDays + ' days');
      return;
    }
    proofChartInst = new Chart(canvas, {
      type:'line',
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){ return '£'+c.parsed.y.toFixed(2); }}}}},
        scales:{x:{ticks:{maxTicksLimit:8,font:{size:9}},grid:{color:'rgba(255,255,255,0.04)'}},
                y:{ticks:{callback:function(v){ return '£'+v; },font:{size:9}},grid:{color:'rgba(255,255,255,0.06)'}}},
      data:{labels:labels,datasets:[{data:data,borderColor:'#00e87a',backgroundColor:'rgba(0,232,122,0.08)',
        borderWidth:2,pointRadius:4,pointBackgroundColor:'#00e87a',fill:true,tension:0.3}]}
    });
    var chartLbl = document.getElementById('proofChartLbl');
    if (chartLbl) chartLbl.textContent = 'official £1 each-way results · ' + PERF_DATA.bettingDays + ' days';
    return;
  }
  var sorted = trackRecord.slice().sort(function(a,b){ return new Date(a.date)-new Date(b.date); });
  var running = 0;
  var labels = [], data = [];
  var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  sorted.forEach(function(p) {
    running += p.patentProfit;
    var d = new Date(p.date);
    labels.push(months[d.getMonth()]+' '+d.getFullYear().toString().slice(2));
    data.push(+running.toFixed(2));
  });
  if (typeof Chart === 'undefined') {
    drawSimpleProofChart(canvas, labels, data, 'official £1 each-way results · ' + trackRecord.length + ' days');
    return;
  }
  proofChartInst = new Chart(canvas, {
    type:'line',
    options:{responsive:true,maintainAspectRatio:false,
      layout:{padding:{left:0,right:0}},
      plugins:{legend:{display:false},tooltip:{callbacks:{label:function(c){ return '£'+c.parsed.y.toFixed(2); }}}},
      scales:{x:{ticks:{maxTicksLimit:8,font:{size:9}},grid:{color:'rgba(255,255,255,0.04)'}},
              y:{ticks:{callback:function(v){ return '£'+v; },font:{size:9}},grid:{color:'rgba(255,255,255,0.06)'}}}},
    data:{labels:labels,datasets:[{data:data,borderColor:'#00e87a',backgroundColor:'rgba(0,232,122,0.08)',
      borderWidth:2,pointRadius:3,pointBackgroundColor:'#00e87a',fill:true,tension:0.3}]}
  });
  var chartLbl = document.getElementById('proofChartLbl');
  if (chartLbl) chartLbl.textContent = 'official £1 each-way results · ' + trackRecord.length + ' days';
}


function s75ResultDateLabel(dateText) {
  if (!dateText) return '';
  var m = String(dateText).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return m[3] + '/' + m[2] + '/' + m[1];
  return String(dateText);
}

function s75PickCodeLabel(pick) {
  var raw = String((pick && (pick.code || pick.type || pick.race_type || pick.raceType || pick.category)) || '').toLowerCase();
  if (raw.indexOf('jump') >= 0 || raw.indexOf('hurdle') >= 0 || raw.indexOf('chase') >= 0) return 'JUMPS';
  if (raw.indexOf('flat') >= 0) return 'FLAT';

  var txt = [
    pick && pick.course,
    pick && pick.time,
    pick && pick.race_type,
    pick && pick.raceType,
    pick && pick.resultType
  ].join(' ').toLowerCase();

  if (txt.indexOf('hurdle') >= 0 || txt.indexOf('chase') >= 0 || txt.indexOf('nh') >= 0) return 'JUMPS';
  return 'FLAT';
}

function s75PickIsWatchlist(pick) {
  var txt = JSON.stringify(pick || {}).toLowerCase();
  return txt.indexOf('watchlist') >= 0 || txt.indexOf('radar') >= 0 || pick.watchlist === true || pick.isRadar === true;
}

function s75PickName(pick) {
  return safeText(
    pick.name ||
    pick.horse ||
    pick.horseName ||
    pick.selection ||
    'Unnamed horse'
  );
}

function s75PickResultText(pick) {
  var result = String(pick.result || pick.status || pick.radarResult || '').toUpperCase();
  var pos = pick.position || pick.finishing_position || pick.finishPosition || pick.pos || '';

  if (result.indexOf('WON') >= 0) return 'WON' + (pos ? ' - ' + ordinal(Number(pos)).toUpperCase() : '');
  if (result.indexOf('PLACED') >= 0) return 'PLACED' + (pos ? ' - ' + ordinal(Number(pos)).toUpperCase() : '');
  if (result.indexOf('LOST') >= 0) return pos ? ordinal(Number(pos)).toUpperCase() : 'LOST';
  if (result.indexOf('VOID') >= 0) return 'VOID';
  if (pos && Number(pos) > 0 && Number(pos) < 40) return ordinal(Number(pos)).toUpperCase();
  return result || 'PENDING';
}

function s75PickResultClass(pick) {
  var result = String(pick.result || pick.status || pick.radarResult || '').toUpperCase();
  var pos = Number(pick.position || pick.finishing_position || pick.finishPosition || 0);
  if (result.indexOf('WON') >= 0 || pos === 1) return 'result-win';
  if (result.indexOf('PLACED') >= 0 || pos === 2 || pos === 3) return 'result-place';
  if (result.indexOf('VOID') >= 0) return '';
  if (result.indexOf('PENDING') >= 0) return 'result-pending';
  return 'result-lost';
}

function s75ResultKeyHtml() {
  return '' +
    '<div style="font-family:\'DM Mono\',monospace;font-size:12px;color:#F5F5FF;line-height:1.6;margin:0 0 10px;padding:0 12px">' +
      'Result key: 🏆 won · 🟡 placed&nbsp;&nbsp;<span style="font-size:14px;line-height:0;color:#F5F5FF">●</span> unplaced' +
    '</div>';
}

function s75PickLineHtml(pick, label) {
  var cls = s75PickResultClass(pick);
  var resultText = s75PickResultText(pick);
  var resultIcon = cls === 'result-win' ? '🏆' : cls === 'result-place' ? '🟡' : '<span style="font-size:14px;color:#F5F5FF">●</span>';
  var resultWord = cls === 'result-win' ? 'Won' : cls === 'result-place' ? 'Placed' : 'Unplaced';

  var course = safeText(pick.course || '');
  var time = safeText(pick.time || '');
  var score = pick.score || pick.signal_score || '';
  var odds = pick.odds || pick.bsp || '';
  var tips = pick.tipsters || pick.tipster_count || pick.source_count || pick.tip_count || 0;
  var meta = [];

  if (course) meta.push(course);
  if (time) meta.push(time);
  if (score !== '') meta.push('score ' + safeText(score));
  if (odds !== '') meta.push('BSP ' + safeText(odds));
  meta.push(safeText(tips) + ' tipster' + (Number(tips) === 1 ? '' : 's'));

  var proofNote = label === 'Official Pick'
    ? 'Counts in proof'
    : 'Tracked only · not counted in proof';

  return '' +
    '<div class="s75-proof-pick-line">' +
      '<div class="s75-proof-pick-main">' +
        '<div class="s75-proof-pick-name">' + resultIcon + ' ' + s75PickName(pick) + ' <span style="font-family:\'DM Mono\',monospace;font-size:8px;color:#9090A8;font-weight:700">(' + resultWord + ')</span></div>' +
        '<div class="s75-proof-pick-meta">' + meta.join(' · ') + '</div>' +
      '</div>' +
      '<div class="s75-proof-pick-side">' +
        '<div class="s75-proof-result ' + cls + '">' + safeText(resultText) + '</div>' +
        '<div class="s75-proof-type">' + safeText(label) + '</div>' +
        '<div class="s75-proof-note">' + proofNote + '</div>' +
      '</div>' +
    '</div>';
}

function s75GetHistoryPicks(day, defaultType) {
  var out = [];

  function addPick(p, fallbackType) {
    if (!p) return;
    var copy = Object.assign({}, p);
    var finalType = defaultType || fallbackType;
    if (finalType && !copy.selection_type && !copy.typeLabel) copy.selection_type = finalType;
    out.push(copy);
  }

  ['picks','official','officialPicks','selections','horses'].forEach(function(key){
    if (Array.isArray(day[key])) {
      day[key].forEach(function(p){ addPick(p, 'Official Pick'); });
    }
  });

  ['watchlist','radar','radarPicks','topRated','topRatedFlat','topRatedJumps'].forEach(function(key){
    if (Array.isArray(day[key])) {
      day[key].forEach(function(p){ addPick(p, 'Watchlist'); });
    }
  });

  return out;
}

function s75RenderGroupedHistoryPicks(day, defaultType) {
  var picks = s75GetHistoryPicks(day, defaultType);
  if (!picks.length) return '';

  var groups = {
    FLAT: { official: [], watchlist: [] },
    JUMPS: { official: [], watchlist: [] }
  };

  picks.forEach(function(p) {
    var code = s75PickCodeLabel(p);
    var isWatch = s75PickIsWatchlist(p) || String(p.selection_type || p.typeLabel || '').toLowerCase().indexOf('watch') >= 0;
    groups[code][isWatch ? 'watchlist' : 'official'].push(p);
  });

  var html = '<div class="s75-proof-grouped-results">';
  html += s75ResultKeyHtml();

  ['FLAT','JUMPS'].forEach(function(code) {
    var g = groups[code];
    if (!g.official.length && !g.watchlist.length) return;

    html += '<div class="s75-proof-code-section">';
    html += '<div class="s75-proof-code-title">' + code + '</div>';

    if (g.official.length) {
      html += '<div class="s75-proof-subtitle">Official Picks</div>';
      g.official.forEach(function(p){ html += s75PickLineHtml(p, 'Official Pick'); });
    }

    if (g.watchlist.length) {
      html += '<div class="s75-proof-subtitle watch">Watchlist</div>';
      g.watchlist.forEach(function(p){ html += s75PickLineHtml(p, 'Watchlist'); });
    }

    html += '</div>';
  });

  html += '</div>';
  return html;
}

function s75HistoryDaySubtitle(day) {
  var picks = s75GetHistoryPicks(day);
  var official = picks.filter(function(p){ return !s75PickIsWatchlist(p) && String(p.selection_type || p.typeLabel || '').toLowerCase().indexOf('watch') < 0; }).length;
  var watch = picks.length - official;

  if (official && watch) return 'Official picks and watchlist · tap to view horses';
  if (official) return 'Official picks · tap to view horses';
  if (watch) return 'No official Patent picks · watchlist tracked only';
  return 'No results available';
}

function renderProofHistory(days) {
  var wrap = document.getElementById('proofHistTable');
  if (!wrap) return;

  var html = '';

  html += '<div style="background:rgba(240,192,64,0.06);border:1px solid rgba(240,192,64,0.22);border-radius:14px;padding:14px;margin-bottom:12px">';
  html += '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:22px;color:var(--gold);letter-spacing:1px;margin-bottom:6px">How Signal 75 Works</div>';
  html += '<div style="font-size:11px;color:#C8C8E0;line-height:1.8">';
  html += 'Signal 75 starts with professional racing consensus, then checks the horses against Betfair data and the Signal 75 score. ';
  html += 'Only official picks are used for the results. Watchlist horses are shown separately, but they do not count in the official record. ';
  html += 'Results use a £1 each-way Patent: 3 singles, 3 doubles and 1 treble, all each-way. That is 14 bet lines and £14 total stake.';
  html += '</div></div>';


  html += '<div style="text-align:center;margin:12px 0 12px">';
  html += '<a href="/how-it-works.html" style="display:inline-block;border:1px solid rgba(240,192,64,.35);border-radius:10px;padding:11px 15px;font-family:\'DM Mono\',monospace;font-size:10px;color:#f0c040;letter-spacing:.08em;text-transform:uppercase;background:rgba(240,192,64,.05)">How Signal 75 Works →</a>';
  html += '</div>';

  html += '<div style="background:rgba(240,192,64,0.06);border:1px solid rgba(240,192,64,0.25);border-radius:14px;padding:14px;margin-bottom:12px;text-align:center">';
  html += '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:20px;color:var(--text);letter-spacing:1px;margin-bottom:5px">Share Signal 75</div>';
  html += '<div style="font-size:10px;color:#C8C8E0;line-height:1.6;margin-bottom:10px">Share by WhatsApp, Messages, Facebook, email or copy. X is optional.</div>';
  html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">';
  html += '<button onclick="shareFullProof()" style="grid-column:1/-1;padding:11px;border:none;border-radius:10px;background:linear-gradient(135deg,#f0c040,#e8a020);color:#050509;font-size:12px;font-weight:900;cursor:pointer">Share Results Page</button>';
  html += '<button onclick="copyProofShareText()" style="padding:10px;border:1px solid var(--border);border-radius:10px;background:var(--bg4);color:#E0E0F0;font-size:11px;font-weight:800;cursor:pointer">Copy Results Message</button>';
  html += '<button onclick="postProofToX()" style="padding:10px;border:1px solid rgba(240,192,64,.22);border-radius:10px;background:rgba(240,192,64,.06);color:#f0c040;font-size:11px;font-weight:800;cursor:pointer">Post to X</button>';
  html += '</div>';
  html += '</div>';

  if (PERF_DATA && PERF_DATA.radarLog && PERF_DATA.radarLog.length > 0) {
    html += '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;text-transform:uppercase;letter-spacing:.12em;margin:12px 0 8px;padding-left:12px">Watchlist Results</div>';
    html += '<div style="font-size:11px;color:#F5F5FF;line-height:1.5;margin:-2px 0 8px;padding:0 12px">Watchlist horses tracked separately. They are not counted in the official results.</div>';
    html += s75ResultKeyHtml();
    PERF_DATA.radarLog.forEach(function(day, dayIndex) {
      var complete = day.complete === true;
      var headline = day.winners + ' won · ' + day.placed + ' placed';
      if (day.pending) headline += ' · ' + day.pending + ' pending';
      html += '<details '+(dayIndex === 0 ? 'open' : '')+' style="background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.22);border-radius:12px;margin-bottom:7px;overflow:hidden">';
      html += '<summary style="list-style:none;cursor:pointer;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;gap:10px">';
      html += '<div style="min-width:0"><div style="font-family:\'Bebas Neue\',sans-serif;font-size:16px;color:var(--text);letter-spacing:.5px">'+day.date+'</div>';
      html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0">' + s75HistoryDaySubtitle(day) + '</div></div>';
      html += '<div style="text-align:right;font-family:\'Bebas Neue\',sans-serif;font-size:17px;color:'+(complete?'var(--blue)':'var(--gold)')+';white-space:nowrap">'+headline+'</div>';
      html += '</summary>';
      html += '<div style="padding:0 12px 10px">';

      html += s75RenderGroupedHistoryPicks(day, 'Watchlist');
      html += '</div></details>';
    });
  }

  if (PERF_DATA && PERF_DATA.selectionLog && PERF_DATA.selectionLog.length > 0) {
    html += '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;text-transform:uppercase;letter-spacing:.12em;margin:10px 0 8px">Official Results</div>';

    PERF_DATA.selectionLog.forEach(function(day, dayIndex) {
      var complete = day.complete === true;
      var isRadar = day.mode === 'topRatedOnly' || day.mode === 'noBetDay';
      var profit = day.patentProfit || 0;
      var col = !complete ? 'var(--muted2)' : profit >= 0 ? 'var(--green)' : 'var(--red,#ff4d6d)';
      var label = isRadar ? 'No official Patent' : complete ? 'Official Patent Result' : 'Pending';

      html += '<details '+(dayIndex === 0 ? 'open' : '')+' style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;margin-bottom:7px;overflow:hidden">';
      html += '<summary style="list-style:none;cursor:pointer;padding:10px 12px;display:flex;justify-content:space-between;align-items:center;gap:10px">';
      html += '<div style="min-width:0"><div style="font-family:\'Bebas Neue\',sans-serif;font-size:16px;color:var(--text);letter-spacing:.5px">'+day.date+'</div>';
      html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0">'+label+' · tap to view</div></div>';
      html += '<div style="text-align:right;font-family:\'Bebas Neue\',sans-serif;font-size:20px;color:'+col+';white-space:nowrap">'+(complete ? ((profit>=0?'+':'')+'£'+Math.abs(profit).toFixed(2)) : 'Pending')+'</div>';
      html += '</summary>';
      html += '<div style="padding:0 12px 10px">';

      if (!day.selections || day.selections.length === 0) {
        html += '<div style="font-size:10px;color:#8080a0;line-height:1.6">No official picks were made that day. Nothing is missing from the results.</div>';
      } else {
        day.selections.slice(0, 6).forEach(function(sel) {
          var result = sel.result || 'PENDING';
          var pos = sel.position || 0;
          var icon = result === 'WON' ? '🏆' : result === 'PLACED' ? '🟡' : result === 'LOST' ? '<span style="font-size:14px;color:#F5F5FF">●</span>' : '⏳';
          var iconWord = result === 'WON' ? 'Won' : result === 'PLACED' ? 'Placed' : result === 'LOST' ? 'Unplaced' : 'Pending';
          var rcol = result === 'WON' ? 'var(--green)' : result === 'PLACED' ? 'var(--gold)' : result === 'LOST' ? '#C8C8E0' : 'var(--muted2)';
          var posTxt = pos && pos > 0 && pos < 40 ? ordinal(pos) : '';
          var resultTxt = result === 'LOST' ? (posTxt || 'Unplaced') : result;
          html += '<div style="display:flex;justify-content:space-between;align-items:center;border-top:1px solid rgba(255,255,255,0.05);padding-top:7px;margin-top:7px;gap:8px">';
          html += '<div style="min-width:0"><div style="font-size:11px;font-weight:800;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+icon+' '+sel.name+' <span style="font-family:\'DM Mono\',monospace;font-size:8px;color:#9090A8;font-weight:700">('+iconWord+')</span></div>';
          html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0">'+sel.course+' · '+sel.time+' · score '+sel.signal_score+' · BSP '+sel.odds+'</div></div>';
          html += '<div style="text-align:right;flex-shrink:0"><div style="font-family:\'Bebas Neue\',sans-serif;font-size:15px;color:'+rcol+'">'+resultTxt+((result === 'WON' || result === 'PLACED') && posTxt?' · '+posTxt:'')+'</div>';
          html += '<div style="font-family:\'DM Mono\',monospace;font-size:8px;color:#C8C8E0">BSP '+safeText(sel.odds || '')+' · return £'+Number(sel.totalReturn||0).toFixed(2)+'</div>';
          html += '</div>';
          html += '</div>';
        });
      }

      html += '</div></details>';
    });

    wrap.innerHTML = html;
    return;
  }

  html += '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:18px;text-align:center;color:#8080a0;font-size:11px;line-height:1.7">No official bet history yet.<br>Once completed Patent days are settled, they will appear here automatically.</div>';
  wrap.innerHTML = html;
}

function renderProofTab() {
  renderProofHero(proofPeriod);
  if (!LATEST_SCORECARD && !LATEST_SCORECARD_LOADING) loadLatestScorecard(true);
  renderLatestScorecardBlock();
  renderProofSnapshot(proofPeriod);
  renderProofChart(proofPeriod);
  renderProofHistory(proofPeriod);


}

function setProofPeriod(days, btn) {
  proofPeriod = days;
  document.querySelectorAll('.pf-btn').forEach(function(b){b.classList.remove('active');});
  if (btn) btn.classList.add('active');
  renderProofTab();
}

/* ═══════════════════════════════════════════
   SETTINGS
═══════════════════════════════════════════ */
function makeSettingRow(label, value, desc, color) {
  return '<div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:10px">'
    + '<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px">'
    + '<div style="font-size:12px;font-weight:700;color:var(--text)">' + label + '</div>'
    + '<div style="font-family:\'DM Mono\',monospace;font-size:11px;font-weight:700;color:' + color + '">' + value + '%</div>'
    + '</div>'
    + '<div style="height:6px;background:rgba(255,255,255,.07);border-radius:3px;overflow:hidden;margin-bottom:5px">'
    + '<div style="height:100%;width:' + value + '%;background:' + color + ';border-radius:3px"></div>'
    + '</div>'
    + '<div style="font-size:9px;color:#C8C8E0">' + desc + '</div>'
    + '</div>';
}

function devReset() {
  if (confirm('Reset all unlock state? This clears coffee and shares.')) {
    localStorage.removeItem('s75unlock');
    localStorage.removeItem('s75aff');
    localStorage.removeItem('s75pwa');
    unlockState = {coffeePaid:false, referrals:0, sharedAt:[]};
    loadUnlockState();
    renderPickCards('racesContainer', raceGroups);
    renderSettings();
    showToast('Reset done — now locked &#x1F512;');
  }
}

function mobileFilterHelpHtml() {
  return '' +
    '<div style="background:rgba(240,192,64,0.06);border:1px solid rgba(240,192,64,0.25);border-radius:14px;padding:14px;margin-bottom:12px">' +
      '<div style="font-family:\'Bebas Neue\',sans-serif;font-size:20px;color:var(--gold);letter-spacing:1px;margin-bottom:6px">18+ and mobile access</div>' +
      '<div style="font-size:11px;color:#E0E0F0;line-height:1.7">' +
        'Signal 75 is horse racing betting information for adults aged 18+. Some mobile networks and broadband providers block gambling-related websites when parental controls, content filters or age restrictions are switched on.<br><br>' +
        'If Signal 75 does not load on mobile data, check your network content settings or add <strong style="color:var(--text)">signal75.co.uk</strong> to your allowed websites. This is a filtering setting, not a Signal 75 technical fault.' +
      '</div>' +
      '<div style="font-family:\'DM Mono\',monospace;font-size:9px;color:#C8C8E0;line-height:1.6;margin-top:9px">18+ only · Gamble responsibly · BeGambleAware.org · National Gambling Helpline 0808 8020 133</div>' +
    '</div>';
}

function renderSettings() {
  var w = document.getElementById('settingsWrap');
  if (!w) return;
  var accessHelp = mobileFilterHelpHtml();
  if (!unlockState.coffeePaid && unlockState.referrals < 10) {
    w.innerHTML =
      accessHelp +
      '<div class="settings-gate">'+
      '<div class="sg-icon">&#x2699;&#xFE0F;</div>'+
      '<div class="sg-title">Settings — Premium</div>'+
      '<div class="sg-body">See exactly how Signal 75 scores each horse and what the AI is looking for — unlock to go behind the scenes.</div>'+
      '<div class="sg-price-box"><div class="sg-price">~£3</div><div class="sg-price-sub">One coffee = permanent access forever</div></div>'+
      '<a href="'+COFFEE_URL+'" target="_blank" rel="noopener" class="sg-coffee-btn" onclick="onCoffeeClick()">&#x2615; Buy a Coffee — Unlock Everything</a>'+
      '<div class="sg-divider"><div class="sg-divider-line"></div><div class="sg-divider-txt">or share 10 times</div><div class="sg-divider-line"></div></div>'+
      '<button class="sg-share-btn" onclick="openReferralModal()">&#x1F517; Share to Unlock Free</button>'+
      '<div class="sg-ref-count">'+unlockState.referrals+' / 10 shares so far</div>'+
      '</div>';
    return;
  }
  w.innerHTML = accessHelp + '<div class="settings-content"><div style="padding:20px;text-align:center;color:#E0E0F0;font-size:12px">Settings unlocked &#x2705;<br>Advanced controls coming soon.</div></div>';
}

/* ═══════════════════════════════════════════
   TAB SWITCHING
═══════════════════════════════════════════ */
function switchTab(name) {
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.nav-item,.bn-item').forEach(function(n){n.classList.remove('active');});
  var panel = document.getElementById('panel-'+name);
  if (panel) panel.classList.add('active');
  document.querySelectorAll('[data-panel="'+name+'"]').forEach(function(n){n.classList.add('active');});
  if (name === 'proof') renderProofTab();
  if (name === 'settings') renderSettings();
  if (name === 'jumps') {
    var jumpGroups = buildJumpsDisplayGroups();
    renderPickCards('jumpsContainer', jumpGroups);
    renderJumpsEmptyStateIfNeeded();
    if (PICKS_DATA && PICKS_DATA.results && PICKS_DATA.results.jumps) {
      renderResults('jumpsContainer', PICKS_DATA.jumps, PICKS_DATA.results.jumps, 'jumps');
    }
  }
  window.scrollTo(0,0);
}

/* ═══════════════════════════════════════════
   MODALS
═══════════════════════════════════════════ */
function openUnlockModal() {
  document.getElementById('unlockModal').classList.add('open');
}
function openReferralModal() {
  var sub = document.getElementById('refModalSub');
  var prog = document.getElementById('refProgress');
  var r = unlockState.referrals;
  if (sub) sub.textContent = r >= 1 ? 'You\'ve shared '+ r + ' time' + (r>1?'s':'') + '. Share '+(3-Math.min(r,3))+' more to unlock Pick #3.' : 'Share once to unlock Pick #2 — completely free.';
  if (prog) prog.textContent = r + ' / 2 shares used';
  document.getElementById('referralModal').classList.add('open');
}
function closeModal(id) {
  var el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

function doShare() {
  var url = window.location.href.split('?')[0] + '?ref=' + S75_USER_ID;
  var text = 'Signal 75 AI is giving me free horse picks — Leg 1 always free, unlock more by sharing. Worth a look: ' + url;

  /* Increment IMMEDIATELY on tap — do not wait for share callback */
  unlockState.referrals = Math.min(10, unlockState.referrals + 1);
  saveUnlockState();
  refreshCards();
  renderSettings();
  showToast('Pick ' + Math.min(freeHorsesPerRace(), 3) + ' unlocked!');
  setTimeout(function(){
    var w = document.getElementById('emailCaptureWrap');
    if (w) w.style.display = 'block';
  }, 400);

  if (navigator.share) {
    navigator.share({title:'Signal 75 AI Picks', text:text, url:url})
      .then(function(){
        closeModal('unlockModal');
        closeModal('referralModal');
      }).catch(function(){});
  } else {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(function(){
        showToast('Link copied!');
        setTimeout(function(){
          closeModal('unlockModal');
          closeModal('referralModal');
        }, 1500);
      });
    }
  }
}

function refreshCards() {
  /* On radar days, re-render from topRated arrays not raw flat/jumps */
  if (PICKS_MODE === 'topRatedOnly') {
    var radarFlat = []; TOP_RATED_FLAT.forEach(function(h){ radarFlat.push({course:h.venue||h.course||"TBC",time:h.time||"",type:h.race_type||h.type||"flat",runners:h.runners||8,horses:[Object.assign({},h,{score:parseInt(h.signal_score||0),signal_score:parseInt(h.signal_score||0),badge:h.badge||"Watchlist",tipsters:h.tipsters||0,jockey:h.jockey||"Watchlist pick",bd:{fs:parseInt(h.signal_score||50),os:parseInt(h.signal_score||50),ts:50,fm:parseInt(h.signal_score||50)}})],isRadar:true}); });
    var radarJumps = []; TOP_RATED_JUMPS.forEach(function(h){ radarJumps.push({course:h.venue||h.course||"TBC",time:h.time||"",type:h.race_type||h.type||"jumps",runners:h.runners||8,horses:[Object.assign({},h,{score:parseInt(h.signal_score||0),signal_score:parseInt(h.signal_score||0),badge:h.badge||"Watchlist",tipsters:h.tipsters||0,jockey:h.jockey||"Watchlist pick",bd:{fs:parseInt(h.signal_score||50),os:parseInt(h.signal_score||50),ts:50,fm:parseInt(h.signal_score||50)}})],isRadar:true}); });
    renderPickCards('racesContainer', radarFlat);
    renderPickCards('jumpsContainer', radarJumps);
    renderJumpsEmptyStateIfNeeded();
    return;
  }
  /* Re-render tabs using official/radar horses from their own race code only. */
  var flatGroups = buildFlatDisplayGroups();
  var jumpGroups = buildJumpsDisplayGroups();
  renderPickCards('racesContainer', flatGroups);
  renderPickCards('jumpsContainer', jumpGroups);
  renderJumpsEmptyStateIfNeeded();
  raceGroups = flatGroups.slice();
}

function onCoffeeClick() {
  // Open Buy Me A Coffee in new tab
  window.open('https://buymeacoffee.com/signal75', '_blank');
  // Close modal and show instructions
  closeModal('unlockModal');
  closeModal('referralModal');
  showToast('&#x2615; Opening Buy Me A Coffee... come back after paying!');
  // Show confirm button after 8 seconds
  setTimeout(function(){
    if (confirm('Have you completed your payment on Buy Me A Coffee?')) {
      unlockState.coffeePaid = true;
      saveUnlockState();
      showToast('All picks unlocked! &#x2615; Thank you!');
      refreshCards();
      renderSettings();
    }
  }, 8000);
}

/* ═══════════════════════════════════════════
   TOAST
═══════════════════════════════════════════ */
function showToast(msg) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.innerHTML = msg;
  t.classList.add('show');
  setTimeout(function(){t.classList.remove('show');}, 2500);
}

/* ═══════════════════════════════════════════
   INIT
═══════════════════════════════════════════ */
/* PWA */
var pwaPrompt = null;
function initPWA() {
  if (window.matchMedia('(display-mode: standalone)').matches) return;
  if (localStorage.getItem('s75pwa')) return;
  window.addEventListener('beforeinstallprompt', function(e) {
    e.preventDefault(); pwaPrompt = e;
    setTimeout(showPWABanner, 30000);
  });
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (isIOS && !window.navigator.standalone) setTimeout(showPWABanner, 30000);
}
function showPWABanner() {
  if (localStorage.getItem('s75pwa')) return;
  var b = document.getElementById('pwa-banner');
  if (b) b.style.display = 'flex';
}
function dismissPWA() {
  var b = document.getElementById('pwa-banner');
  if (b) b.style.display = 'none';
  localStorage.setItem('s75pwa', Date.now() + 604800000);
}
function installPWA() {
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  if (pwaPrompt) {
    pwaPrompt.prompt();
    pwaPrompt.userChoice.then(function(r) {
      if (r.outcome === 'accepted') { dismissPWA(); showToast('Signal 75 added! &#x1F40E;'); }
      pwaPrompt = null;
    });
  } else if (isIOS) {
    var b = document.getElementById('pwa-banner');
    if (b) b.innerHTML = '<div style="font-family:\'DM Mono\',monospace;font-size:11px;color:#C8C8E0;line-height:1.8">1. Tap the <strong style="color:var(--gold)">Share</strong> button &#x1F4E4;<br>2. Tap <strong style="color:var(--gold)">Add to Home Screen</strong><br>3. Tap <strong style="color:var(--gold)">Add</strong> &mdash; done!<br><br><button onclick="dismissPWA()" style="width:100%;padding:10px;background:var(--bg3);border:1px solid var(--border);border-radius:9px;font-size:12px;color:#E0E0F0;cursor:pointer">Got it &#x2714;</button></div>';
  }
}





(function(){
  try{var r=new URLSearchParams(window.location.search).get('ref');if(r)localStorage.setItem('s75referrer',r);}catch(e){}
})();

function updateNavDots() {
  var flatPicks = (document.querySelectorAll('#racesContainer .horse-card') || []).length;
  var jumpPicks = (document.querySelectorAll('#jumpsContainer .horse-card') || []).length;
  var fd = document.getElementById('nav-flat-dot');
  var jd = document.getElementById('nav-jumps-dot');
  if (fd) fd.style.background = flatPicks > 0 ? '#00e87a' : '#4a4a62';
  if (jd) jd.style.background = jumpPicks > 0 ? '#00e87a' : '#4a4a62';
}
function initSignal75App() {
  if (window.S75_APP_BOOTED) return;
  window.S75_APP_BOOTED = true;
  try {
    loadUnlockState();
    updateProofStrip();
    renderProofHero(7);
    loadLatestScorecard(true);
    loadPerformance(false);
    loadRaces(false);
    initPWA();
    startLiveRefresh();
    setTimeout(updateNavDots, 1100);
  } catch(e) {
    console.error('S75 init error:', e);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSignal75App);
} else {
  initSignal75App();
}


/* ============================================================
   Signal 75 share wording helper
   Frontend-only helper text. Does not change unlock/results logic.
   ============================================================ */
(function(){
  function normalise(txt) {
    return (txt || '').replace(/\s+/g, ' ').trim();
  }

  var helpers = [
    {
      match: 'Share Today’s Pick',
      help: 'Send today’s free pick to a friend by WhatsApp, text, Facebook or email.'
    },
    {
      match: 'Share Today’s Result',
      help: 'Send today’s result to a friend. This does not place a bet.'
    },
    {
      match: 'Copy Results Message',
      help: 'Copies a ready-made message you can paste into WhatsApp, Facebook, text or email.'
    },
    {
      match: 'Share Results Page',
      help: 'Send the public results page showing every pick, win, place and loss.'
    },
    {
      match: 'Share to Unlock Pick 2',
      help: 'Share Signal 75 to unlock the next pick on this device.'
    },
    {
      match: 'Share Again to Unlock Pick 3',
      help: 'Share again to unlock the full 3-horse Patent on this device.'
    },
    {
      match: 'Post to X',
      help: 'Optional: opens X with a ready-made post. Nothing is posted automatically.'
    }
  ];

  function addHelperAfter(el, helpText) {
    if (!el || !el.parentNode) return;

    var next = el.nextElementSibling;
    if (next && next.classList && next.classList.contains('s75-share-helper')) {
      next.textContent = helpText;
      return;
    }

    var div = document.createElement('div');
    div.className = 's75-share-helper';
    div.textContent = helpText;
    div.style.cssText = [
      'font-family:DM Mono,monospace',
      'font-size:9px',
      'line-height:1.45',
      'color:#9CA3AF',
      'margin:5px 0 10px',
      'text-align:center'
    ].join(';');

    el.parentNode.insertBefore(div, el.nextSibling);
  }

  function applyShareWording() {
    var els = document.querySelectorAll('button, a');
    els.forEach(function(el){
      var txt = normalise(el.textContent);

      helpers.forEach(function(item){
        if (txt === item.match || txt.indexOf(item.match) !== -1) {
          addHelperAfter(el, item.help);
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function(){
    applyShareWording();

    // Re-apply after dynamic tab rendering / unlock modals.
    var tries = 0;
    var timer = setInterval(function(){
      applyShareWording();
      tries += 1;
      if (tries > 20) clearInterval(timer);
    }, 500);
  });

  document.addEventListener('click', function(){
    setTimeout(applyShareWording, 150);
    setTimeout(applyShareWording, 600);
  });
})();


(function(){
  if (document.getElementById("s75-score-box-style")) return;
  var style = document.createElement("style");
  style.id = "s75-score-box-style";
  style.textContent = `
/* Compact Signal 75 score boxes */
.s75-score-box-wrap{
  margin:8px 0 7px;
  padding:8px;
  border:1px solid rgba(240,192,64,.22);
  border-radius:14px;
  background:rgba(255,255,255,.025);
}
.s75-score-box-title{
  font-family:'DM Mono',monospace;
  font-size:9px;
  letter-spacing:1.1px;
  color:var(--gold,#f0c040);
  margin-bottom:5px;
  text-align:center;
}
.s75-score-box-grid{
  display:grid;
  grid-template-columns:repeat(4,1fr);
  gap:6px;
}
.s75-score-box{
  border:1px solid rgba(240,192,64,.18);
  border-radius:10px;
  padding:5px 3px 4px;
  text-align:center;
  background:rgba(0,0,0,.20);
}
.s75-score-box-points{
  font-family:'DM Mono',monospace;
  font-size:14px;
  font-weight:800;
  color:#20e77a;
  line-height:1;
}
.s75-score-box-label{
  font-family:'DM Mono',monospace;
  font-size:8px;
  letter-spacing:.8px;
  text-transform:uppercase;
  color:#c9c9d8;
  margin-top:3px;
}
.s75-score-box-help{
  margin-top:2px;
  font-size:8px;
  line-height:1.15;
  color:#9090a8;
  min-height:14px;
}
.s75-score-box-total{
  margin-top:6px;
  font-family:'DM Mono',monospace;
  font-size:10px;
  color:#20e77a;
  text-align:center;
}
.s75-score-box-note{
  margin-top:3px;
  font-size:9px;
  line-height:1.2;
  color:#aaaabd;
  text-align:center;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
@media(max-width:600px){
  .s75-score-box-wrap{padding:7px;margin:7px 0 5px;}
  .s75-score-box-grid{gap:5px;}
  .s75-score-box{padding:5px 2px 4px;}
  .s75-score-box-points{font-size:12px;}
  .s75-score-box-help{font-size:7px;min-height:13px;}
  .s75-score-box-note{font-size:8px;}
}
`;
  document.head.appendChild(style);
})();


/* ============================================================
   Signal 75 UK date display formatter
   Frontend-only display fix.
   Converts visible YYYY-MM-DD dates to DD/MM/YYYY for users.
   Does not change JSON data, scoring, proof, picks or settlement.
   ============================================================ */
(function(){
  function formatUkDateString(text) {
    return String(text || '').replace(/\b(20\d{2})-(\d{2})-(\d{2})\b/g, function(match, yyyy, mm, dd) {
      return dd + '/' + mm + '/' + yyyy;
    });
  }

  function shouldSkipNode(node) {
    if (!node || !node.parentNode) return true;
    var tag = (node.parentNode.tagName || '').toUpperCase();
    return tag === 'SCRIPT' || tag === 'STYLE' || tag === 'TEXTAREA' || tag === 'INPUT';
  }

  function applyUkDateDisplay(root) {
    root = root || document.body;
    if (!root) return;

    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: function(node) {
        if (shouldSkipNode(node)) return NodeFilter.FILTER_REJECT;
        if (!/\b20\d{2}-\d{2}-\d{2}\b/.test(node.nodeValue || '')) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });

    var nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);

    nodes.forEach(function(node) {
      node.nodeValue = formatUkDateString(node.nodeValue);
    });
  }

  function runUkDateFormatter() {
    applyUkDateDisplay(document.body);
  }

  document.addEventListener('DOMContentLoaded', function(){
    runUkDateFormatter();

    var tries = 0;
    var timer = setInterval(function(){
      runUkDateFormatter();
      tries += 1;
      if (tries > 30) clearInterval(timer);
    }, 400);
  });

  document.addEventListener('click', function(){
    setTimeout(runUkDateFormatter, 150);
    setTimeout(runUkDateFormatter, 600);
  });
})();


(function(){
  if (document.getElementById("s75-proof-grouped-style")) return;
  var style = document.createElement("style");
  style.id = "s75-proof-grouped-style";
  style.textContent = `
/* Signal 75 proof history grouped results */
.s75-proof-grouped-results{
  margin-top:10px;
  display:grid;
  gap:10px;
}
.s75-proof-code-section{
  border:1px solid rgba(240,192,64,.16);
  border-radius:12px;
  padding:9px;
  background:rgba(255,255,255,.02);
}
.s75-proof-code-title{
  font-family:'DM Mono',monospace;
  font-size:10px;
  letter-spacing:.12em;
  color:var(--gold,#f0c040);
  margin-bottom:7px;
}
.s75-proof-subtitle{
  font-family:'DM Mono',monospace;
  font-size:8px;
  letter-spacing:.08em;
  color:#20e77a;
  text-transform:uppercase;
  margin:6px 0;
}
.s75-proof-subtitle.watch{
  color:#C8C8E0;
}
.s75-proof-pick-line{
  display:flex;
  justify-content:space-between;
  gap:10px;
  padding:8px 0;
  border-top:1px solid rgba(255,255,255,.07);
}
.s75-proof-pick-line:first-of-type{
  border-top:0;
}
.s75-proof-pick-name{
  font-size:12px;
  color:#F4F4FA;
  font-weight:800;
}
.s75-proof-pick-meta{
  font-size:10px;
  color:#9A9AB0;
  line-height:1.45;
  margin-top:2px;
}
.s75-proof-pick-side{
  min-width:92px;
  text-align:right;
}
.s75-proof-result{
  font-family:'DM Mono',monospace;
  font-size:10px;
  font-weight:900;
}
.s75-proof-type{
  font-family:'DM Mono',monospace;
  font-size:8px;
  color:#C8C8E0;
  margin-top:3px;
  text-transform:uppercase;
}
.s75-proof-note{
  font-size:8px;
  color:#8F8FA5;
  line-height:1.25;
  margin-top:2px;
}
@media(max-width:600px){
  .s75-proof-pick-line{
    align-items:flex-start;
  }
  .s75-proof-pick-side{
    min-width:82px;
  }
}
`;
  document.head.appendChild(style);
})();
