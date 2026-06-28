# Signal 75 Learning System - Full Brief

Date: 28 June 2026  
Status: Strategy and learning brief only  
Live scoring impact: None unless a rule is deliberately promoted later  
Proof impact: None  

## 1. Plain English Purpose

Signal 75 should not just pick horses each morning and forget what happened.

The long-term goal is to build a living racing memory: the modern version of Grandad's old notebook. Every day the system should remember:

- which horses we picked;
- which horses we watched;
- which horses beat us;
- which horses won easily;
- which horses were heavily beaten;
- which tipsters were right or wrong;
- which race conditions mattered;
- which patterns keep repeating;
- which evidence genuinely improves ROI.

The system should become better because it keeps learning from every race, every runner and every result.

The learning layer must support the Signal 75 scoring engine. It must not silently rewrite proof history, settlement maths, or results. Any learning rule should only become part of live selection after evidence proves it helps.

## 2. The Grandad's Book Idea

Grandad's book was simple but powerful: when a horse ran well, won easily, loved a course, handled the ground, beat a good rival, or kept showing the same pattern, that note mattered the next time the horse appeared.

Signal 75 should do the same, but at scale.

Instead of one handwritten note, Signal 75 stores structured evidence:

- horse name;
- course;
- race time;
- race type;
- distance;
- going / surface where available;
- trainer and jockey;
- Signal 75 score;
- tipster support;
- odds / BSP;
- finishing position;
- beaten distance;
- winning margin;
- who beat who;
- whether the run was strong, weak, unlucky, clear, close, or poor.

The important point is not just “Horse A won”. The more valuable question is:

> Horse A beat Horse B, under these conditions, by this distance, and Horse B was a strong Signal 75 horse. What should we do next time Horse A or Horse B runs?

That is the real intelligence.

## 3. Current Evidence We Already Have

Current stored learning evidence includes:

- 5,956 head-to-head / rival evidence records checked.
- 648 horses currently marked as possible horses to follow.
- 60 strong lines where a horse beat a high-signal Signal 75 horse.
- 4 horses currently marked as be careful with from heavy/well-beaten evidence.
- 8 repeat rival patterns found.
- 22 learning days analysed.
- 31 official picks analysed.
- 58 watchlist horses analysed.
- 44 cases where “full criteria met and placed” has fired.

These numbers will grow automatically as daily racing continues.

## 4. Current Learning Storage

Signal 75 currently stores learning in several places:

### Horse Intelligence

Folder:

`data/horse_intelligence/`

Main purpose:

- horse memory;
- race memory;
- head-to-head memory;
- historic rivals;
- race result notes;
- collateral form;
- SQLite history database.

Important files:

- `head_to_head_master.jsonl`
- `head_to_head_profiles.json`
- `historic_rival_master.jsonl`
- `historic_rival_profiles.json`
- `race_result_notes_master.jsonl`
- `race_result_note_profiles.json`
- `race_memory_master.jsonl`
- `horse_memory_profiles.json`
- `signal75_history.sqlite`
- `collateral_form/collateral_form_all_history.json`

### Continuous Training

Folder:

`data/continuous_training/`

Main purpose:

- track recurring findings;
- estimate ROI improvement candidates;
- identify pattern alerts;
- keep daily learning logs;
- separate learning from live proof.

Important files:

- `cumulative_findings.json`
- `pattern_alerts.json`
- `roi_improvement_candidates.json`
- `master_learning_summary.json`
- `training_log_YYYY-MM-DD.json`

### Intelligence Reviews

Folder:

`data/intelligence_reviews/`

Main purpose:

- store strategic reviews;
- store end-of-test recommendations;
- compare rule ideas;
- record non-live future changes.

Important files:

- `uk_site_strategy_review_2026-06-28.txt`
- `scenario_roi_review_*.json`
- `june14_idea_lab_*.json`
- `review_YYYY-MM-DD.json`

## 5. Current Learning Categories

Signal 75 is already tracking these learning categories:

1. False consensus
   - Tipster support that looks strong but is really duplicated, weak, or low-quality.

2. Full criteria met and placed
   - Horses that matched the important rules and still placed. This helps identify what works.

3. Surface data missing
   - Horses where the surface evidence is incomplete.

4. Unproven course
   - Horse has not yet proved itself at today’s course.

5. Unproven going
   - Horse has not yet proved itself on today’s ground.

6. Unproven trip
   - Horse has not yet proved itself at today’s distance.

7. Same-course cluster
   - Too many selections from the same meeting/course.

8. Thin form record
   - Horse looks interesting but has too little reliable evidence.

9. Large-field chaos risk
   - Big fields can create messy races where the best-scored horse may not get a clean run.

10. Poor recent form
   - Obvious recent poor form patterns that should protect the system from embarrassing selections.

11. Shadow rule beat live rule
   - A non-live test rule would have performed better than the live rule on that day.

12. Collateral form / rival evidence
   - Horses that beat our horses, especially high-signal horses, become horses to watch.

## 6. The Core Strategy: Find, Confirm, Protect, Learn, Review

The system should be simplified around five clear stages.

### Stage 1 - Find

Signal 75 scores and ranks every runner.

Evidence includes:

- price/value;
- odds band;
- field size;
- race type;
- course/race profile;
- market data;
- horse history;
- form profile;
- recent run timing;
- Betfair data.

Output:

- raw Signal 75 score;
- top candidates;
- possible official picks;
- watchlist horses.

### Stage 2 - Confirm

The system checks whether outside evidence supports the horse.

Evidence includes:

- trusted tipster support;
- named expert support;
- independent source count;
- market support;
- strong consensus;
- specialist source agreement.

Important rule:

A horse should not be treated as strong consensus just because one weak source repeats the same tip count. Independent trusted sources matter more than raw count.

### Stage 3 - Protect

The system looks for reasons not to trust a horse, even if it scores well.

Protection checks include:

- poor recent form;
- repeated pulled-up / non-completion patterns;
- weak or false tipster consensus;
- too short a price for value;
- too far outside value band;
- too many selections from same course/race;
- poor or missing condition evidence;
- big-field chaos risk;
- heavily beaten by today’s rival;
- serious rival warning.

This stage is about avoiding stupid bets, not finding every winner.

### Stage 4 - Learn

After racing, Signal 75 stores what actually happened.

It stores:

- result;
- finish position;
- return;
- BSP;
- beaten distance;
- winning margin;
- who beat whom;
- which winners we missed;
- which watchlist horses won;
- which official picks failed;
- which tipsters were right;
- which warnings were useful;
- which warnings were noise.

This is where Grandad’s book grows.

### Stage 5 - Review

At end of July, only promote evidence that has repeatedly helped.

A review rule should ask:

- Did this pattern fire often enough?
- Did it improve ROI?
- Did it reduce bad selections?
- Did it block winners accidentally?
- Was it understandable to users?
- Does it keep proof clean?

If not, keep it as learning only.

## 7. How The Point Overlays Should Work

The base Signal 75 score should remain the main engine.

Learning overlays should be small, controlled, and evidence-based.

Suggested future overlay ranges for review:

### Tipster / Expert Confirmation

- Elite independent consensus: +8 to +12 points candidate.
- Several independent trusted sources: +5 to +8 points candidate.
- Single named expert: +2 to +4 points candidate.
- Soft duplicated consensus: 0 points or warning.
- Untrusted source only: no boost.

### Condition Confidence

Course, distance, going and surface should become one combined condition confidence layer.

- Proven under very similar conditions: small positive support.
- Unknown conditions: note only.
- Failed repeatedly under same conditions: warning.
- Won easily under same conditions: stronger future support.

### Collateral Form / Rival Evidence

This is the Grandad layer.

- Beat a high-signal Signal 75 horse clearly: +3 to +8 points candidate.
- Beat multiple useful rivals: stronger follow flag.
- Same rival beaten repeatedly: stronger follow flag.
- Lost heavily to today’s rival: -5 to -12 points candidate.
- One old meeting only: note, not score change.

### Winning Margin / Beaten Distance

- Won clearly: positive future note.
- Won narrowly: positive but softer note.
- Close-up defeat: not a harsh negative.
- Well beaten: caution.
- Heavily beaten: stronger caution.
- No response / weakened badly: warning.

### Protection Rules

- Embarrassing recent form: hard block or heavy penalty.
- Repeated pulled-up / unseated / tailed-off pattern: hard warning.
- Thin form record: warning until more evidence.
- Big-field chaos: small warning unless strongly confirmed.
- Same-course cluster: warning if too many picks rely on the same meeting.

## 8. How Horses To Follow Should Work

A horse should become a horse to follow when:

- it beats one of our high-score horses;
- it beats several useful rivals;
- it wins easily;
- it wins despite a difficult race setup;
- it improves sharply under certain conditions;
- it keeps beating the same rivals;
- it runs well in a strong race;
- it finishes close despite not winning.

But the system must avoid blindly following every winner.

A horse should be followed more strongly when the next race is similar:

- same/similar distance;
- same/similar going;
- same/similar course type;
- similar race class;
- same jockey/trainer pattern;
- similar field size;
- price remains reasonable.

A horse should only get a meaningful boost when the evidence matches today’s race.

Example:

If Samuel Spade beat My Bobby Dazzler by 22 lengths at Worcester, Samuel Spade should go into the horse-to-follow memory. But next time, Signal 75 should still ask:

- Is the distance similar?
- Is the going similar?
- Is the class similar?
- Is the price acceptable?
- Was that win a one-off?
- Did the beaten horse run badly for another reason?

This keeps the Grandad layer intelligent rather than emotional.

## 9. How Caution Horses Should Work

A horse should become a caution horse when:

- it was heavily beaten;
- it failed to respond;
- it weakened badly;
- it was beaten clearly by today’s rival before;
- it repeatedly loses to the same rival;
- it has poor recent form;
- it has unreliable or thin evidence;
- it is being boosted only by false consensus.

Caution does not always mean block.

It should mean:

- reduce confidence;
- show warning in dashboard;
- possibly apply a penalty later;
- require stronger confirmation before official selection.

## 10. Tipster Intelligence

Tipster support should improve in three ways.

### 1. Source Quality

Named proven experts should count more than generic duplicated lists.

Examples of high-value named or trusted sources to keep reviewing:

- Racing Post NAPs / Pricewise / Tom Segal;
- Paul Jacobs;
- Hugh Taylor / At The Races;
- Sporting Life / Ben Linfoot;
- Timeform;
- Templegate;
- Robin Goodfellow;
- Newsboy;
- Marlborough;
- GG;
- Oddschecker;
- OLBG;
- myracing;
- HorseRacing.net;
- RacingTips;
- Punters Lounge;
- Tipstrr.

### 2. Independence

Six tips from six independent sources is much stronger than six tips copied from one source.

### 3. Accuracy Over Time

The system should track:

- which sources tipped winners;
- which sources tipped placed horses;
- which sources repeatedly missed;
- which sources perform better on flat/jumps;
- which sources perform better at certain odds.

Long-term aim:

A tipster source earns weight from performance, not reputation alone.

## 11. Market Intelligence

Market data should confirm or warn, not cause panic.

Useful market evidence:

- horse is in top three of market;
- horse is strongly supported;
- horse drifts badly;
- horse remains in value band;
- horse is too short for each-way value;
- late weakness repeats across similar horses.

Rule of thumb:

Market confidence should support the selection but should not create confusing last-minute public switches.

## 12. Watchlist Role

The watchlist must not confuse users.

Internally, the watchlist is very valuable.

It tells us:

- which high-score horses nearly qualified;
- which non-official horses won;
- which rules blocked winners;
- whether the official gate is too strict;
- which horses should be followed next time.

Publicly, watchlist must be simpler:

- official picks are the betting/proof selections;
- watchlist is learning/tracking only;
- horses to follow are future intelligence, not proof.

## 13. Dashboard Role

The dashboard should explain the system visually and simply.

Recommended dashboard layout:

1. Today overview
   - picks generated;
   - official picks;
   - watchlist tracked;
   - learning status;
   - proof unchanged.

2. Find
   - top scored runners;
   - score breakdown;
   - price/race/form/tipster components.

3. Confirm
   - tipster evidence;
   - source quality;
   - independent source count;
   - market support.

4. Protect
   - warnings;
   - poor form;
   - false consensus;
   - race condition risk;
   - large-field risk.

5. Learn
   - winners;
   - beaten distances;
   - horses to follow;
   - caution horses;
   - head-to-head evidence.

6. Results
   - official proof;
   - watchlist comparison;
   - weekly / 14-day / all-time performance.

The dashboard should use charts, colour and plain English. It should not look like raw data dumped on a screen.

## 14. How We Want The System To Work Eventually

Morning:

1. Load all runners.
2. Score every runner with Signal 75.
3. Match horses against database history.
4. Add tipster and expert evidence.
5. Check condition confidence.
6. Check collateral form.
7. Check protection warnings.
8. Select official picks only if they pass the gates.
9. Track watchlist and horses to follow separately.

After racing:

1. Fetch/settle results.
2. Record finishing positions.
3. Record BSP/return.
4. Record winning margins and beaten distances.
5. Record who beat whom.
6. Update horse memory.
7. Update tipster memory.
8. Update collateral form.
9. Update warning accuracy.
10. Update dashboard.

End of review period:

1. Check which learning rules genuinely improved ROI.
2. Check which warnings blocked too many winners.
3. Check which tipster sources are reliable.
4. Promote only proven rules.
5. Keep weak/noisy rules as learning only.

## 15. How I Think It Should Work

My recommendation is to keep Signal 75 as a disciplined layered system:

1. Signal 75 score finds the candidate.
2. Tipsters and market confirm or question it.
3. Protection rules stop obvious bad bets.
4. Grandad memory adds real racing intelligence.
5. Proof stays clean and honest.

The biggest opportunity is not simply adding more points. The biggest opportunity is avoiding weak selections and recognising strong horses earlier next time.

The best future version is not “AI guesses a winner”.

The best future version is:

- Signal 75 knows the field;
- remembers what happened before;
- understands who beat whom;
- knows which tipsters matter;
- sees when conditions match;
- avoids bad repeat patterns;
- learns every night;
- explains the decision simply.

## 16. End-of-July Review Questions

At end of July, ask:

1. Did false consensus hurt results?
2. Did condition confidence help avoid poor selections?
3. Did poor recent form warnings save money?
4. Did thin form warnings matter?
5. Did same-course clusters reduce reliability?
6. Did large-field chaos matter?
7. Did horses-to-follow win or place next time?
8. Did caution horses underperform next time?
9. Did strong collateral form improve future picks?
10. Which tipster sources genuinely added value?
11. Which learning rules should become live scoring overlays?
12. Which should stay as dashboard-only notes?

## 17. Rules Not To Break

Do not change automatically without review:

- proof history;
- result settlement maths;
- public ROI maths;
- unlock logic;
- Buy Me A Coffee logic;
- old published results;
- data structures users rely on.

Learning should improve the future without rewriting the past.

## 18. Final Summary

Signal 75 is becoming more than a daily picker.

It is becoming a racing memory engine.

The system should learn like Grandad did, but with much more data:

- remember winners;
- remember losers;
- remember easy wins;
- remember heavy defeats;
- remember horses that beat us;
- remember horses we should follow;
- remember weak consensus;
- remember reliable tipsters;
- remember dangerous race conditions;
- use that memory carefully next time.

The strategy is simple:

Find the horse.  
Confirm the evidence.  
Protect against risk.  
Learn from the result.  
Review before changing live rules.  

That is the long-term edge.
