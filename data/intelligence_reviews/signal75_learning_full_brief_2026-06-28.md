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

## 16. Self-Teaching Architecture

The new self-teaching architecture should be used because it explains how Signal 75 can keep improving without becoming reckless.

Important distinction:

- Signal 75 cannot learn by self-play like a board-game AI. Horse races cannot be simulated perfectly millions of times.
- Signal 75 can learn from real-world feedback: every settled race, every missed winner, every beaten favourite, every useful tipster signal, every horse that beat us, and every watchlist result.

That is the correct model for racing.

### Champion And Challenger

Signal 75 should use a champion/challenger system.

- Champion: the current live selection method.
- Challenger: a possible improved method running in shadow.
- Promotion: challenger becomes live only after it beats the champion on proper evidence.

This fits the way Signal 75 already works:

- current live picks are the champion;
- shadow reviews are challengers;
- late value and consensus reviews are challenger evidence;
- continuous training files are the learning feed;
- manual review protects public picks and proof.

### Fully Automatic Nightly Learning

These jobs should run automatically without changing live picks:

1. Ingest settled results.
2. Record finishing positions, BSP, returns, winning margins and beaten distances.
3. Record who beat whom, especially horses that beat high-signal Signal 75 horses.
4. Update horse memory, rival memory, tipster memory and condition memory.
5. Update caution horses and horses to follow.
6. Run shadow rules against the same races.
7. Compare challenger rules against the live champion.
8. Detect drift, such as changed race patterns, changed field sizes, or a tipster source becoming weaker.
9. Produce dashboard and morning learning summaries.
10. Archive older reports so the system does not create thousands of loose files.

This is the part that should be fully automatic.

### Weekly Or Scheduled Retraining

On a schedule, probably weekly to begin with, Signal 75 can build challenger settings from accumulated data.

Examples:

- better tipster source weights;
- better warning weights;
- better condition-confidence weights;
- better horse-to-follow scoring;
- better caution-horse scoring;
- better collateral-form/rival evidence values.

These retrained settings should not go straight into live picks.

They should become challenger rules first.

### Drift Detection

The system should watch for the world changing.

Examples:

- tipster consensus becomes less reliable;
- one source starts duplicating weak tips;
- course conditions change results;
- large-field races become more chaotic;
- market behaviour changes;
- a new rule starts producing too many selections or too few.

If drift is detected, Signal 75 should trigger an early review or retrain rather than waiting until the next scheduled review.

### Promotion Gate

The one step that must stay controlled is live promotion.

A challenger should only become the live method when:

- it has enough examples;
- it beats the current live method;
- it does not only win because of one lucky day;
- it improves ROI or avoids bad selections;
- it does not damage public clarity;
- it keeps proof clean;
- it is understandable enough to explain.

At first, promotion should need manual approval.

Later, if the tests become trustworthy, this can become a veto window: Signal 75 says “this challenger has passed and will go live in 48 hours unless stopped”.

The gate should never disappear completely because public selections affect real betting decisions.

### Automatic Rollback

If a new rule is promoted later, Signal 75 should monitor it during a probation period.

Rollback should happen if:

- pick count becomes abnormal;
- ROI falls far outside expected range;
- place rate collapses;
- warning rules fail repeatedly;
- the new rule creates confusing or poor public picks.

Rollback means reverting to the previous live champion and flagging the issue for review.

This is not needed today because this brief does not promote a new live rule. It should be part of the future architecture before any automated promotion is allowed.

### How This Helps Horse Logging

The horse logging system should not just store interesting notes.

It should label every note as evidence for a possible future challenger rule.

Examples:

- Horse beat a high-signal Signal 75 horse.
- Horse won clearly.
- Horse was heavily beaten.
- Horse beat the same rival more than once.
- Horse improved when conditions matched.
- Horse failed when conditions changed.
- Tipster support was real and independent.
- Tipster support was false or duplicated.
- Market support helped or misled.

This turns Grandad’s book from a diary into a tested intelligence system.

## 17. What We Are Not Using Yet

These ideas from the self-teaching architecture should not be switched on as live behaviour yet:

1. No automatic live promotion today.
   - Reason: the live picks and proof must stay trusted. Learning can run automatically, but changing public selection logic needs a gate.

2. No self-play simulation.
   - Reason: racing is real-world and cannot be simulated accurately enough to create fake training races.

3. No automatic retrained scoring weights in live picks yet.
   - Reason: the retrained settings must first run as challengers and prove they help on real results.

4. No rollback implementation needed today.
   - Reason: rollback only matters once a challenger is promoted. It should be built before future automatic or semi-automatic promotion.

5. No change to proof history.
   - Reason: learning improves future decisions only. It must never rewrite old results.

## 18. Closed-Loop Improvements To Add To The Plan

The improved closed-loop brief adds useful controls that should be added to the learning plan before any future live promotion.

These are planning items only unless separately built, tested and promoted.

### 1. Collapse Duplicate Weak-Evidence Warnings

Current risk:

- unproven course;
- unproven going;
- unproven trip;
- thin form record;
- surface missing.

These often describe the same underlying issue: the system does not know enough about the horse under today’s exact conditions.

If they are treated as separate heavy warnings, Signal 75 can over-punish one horse for the same weakness several times.

Future fix:

Create one combined evidence-richness factor.

It should answer:

- do we have enough useful evidence?
- is evidence missing because the horse is lightly raced?
- is evidence missing because the horse has failed under similar conditions?
- did similar missing-evidence horses actually underperform historically?

Missing data should be treated as unknown first, not automatically bad.

### 2. Add Excuse Flags To Race Result Notes

A horse can be beaten badly for a valid reason.

Examples:

- hampered;
- blocked;
- wide throughout;
- eased late;
- mistake at a fence;
- wrong going;
- returning from a break;
- jockey stopped riding when chance was gone;
- no excuse recorded.

Future fix:

Add `excuse_flags` to race result notes and horse memory.

This protects the Grandad layer from drawing the wrong conclusion from a raw margin.

Example:

“Beaten 22 lengths” is much more serious if there was no excuse. It is less reliable if the horse was badly hampered or eased when beaten.

### 3. Check Horses To Follow Against A Control Group

Current risk:

A horse that beats one of our high-score horses feels important, but we need to prove it is more useful than a normal winner or placed horse.

Future fix:

Compare horses-to-follow against a control group:

- horses that beat Signal 75 horses;
- ordinary winners at similar prices;
- ordinary placed horses;
- similar-score horses that did not beat one of ours.

Only treat the horse-to-follow label as a real edge if it performs better than the control group.

### 4. Add Time Decay To Horse Memory

Old evidence should not carry full weight forever.

Future fix:

Horse memory should reduce in strength over time unless confirmed again.

Examples:

- very recent evidence: strongest;
- 1-3 months old: useful;
- 3-6 months old: weaker;
- older than 6 months: note only unless repeated;
- old evidence under very different conditions: low value.

This keeps the Grandad book current.

### 5. Treat Overlay Points As Phase 1 Priors

Current overlay numbers are sensible starting points, not proven truth.

Examples:

- consensus boost;
- rival evidence boost;
- caution penalty;
- condition confidence boost;
- false-consensus warning.

Future fix:

Label these as Phase 1 priors.

They should be refitted from data once enough evidence exists, then tested as challenger rules before promotion.

### 6. Add CLV To Tipster Grading

Tipster win rate is noisy.

Future fix:

Track Closing Line Value for tipster mentions.

Plain English:

Did the market move in the same direction after the tip?

This is useful because a good tipster may not win every race, but over time their selections should often beat the later market price.

Useful fields:

- tipster/source;
- horse;
- race;
- price when captured;
- BSP;
- whether the price shortened or drifted;
- result.

### 7. Add Brier Score And Reliability Curves

ROI matters to users, but it is noisy over small samples.

Future fix:

Track whether Signal 75 scores are honest.

Plain English:

If horses scored 90-100 are meant to be strong, do they win/place more often than horses scored 75-84?

This should be measured with:

- score bands;
- actual win/place rate;
- Brier score;
- reliability chart;
- confidence bands.

This will show whether the scoring scale itself is calibrated.

### 8. Pre-Commit The Review Evidence Threshold

A review is weaker if we decide the rules after seeing the results.

Future fix:

Before the next major review, define:

- minimum number of examples;
- minimum number of days;
- minimum ROI/place-rate improvement;
- maximum acceptable missed-winner damage;
- whether one lucky day is allowed to dominate the result;
- which challenger rules are being tested.

This protects the review from emotion after a good or bad week.

### 9. Trainer/Jockey Form Windows And Price-Walk View

Useful future additions:

- trainer form over 14 and 30 days;
- jockey form over 14 and 30 days;
- trainer/jockey combination form;
- price movement through the day rather than only final BSP.

These are strong dashboard and learning features, but should not create public last-minute pick changes.

### 10. Sectional Timing And Proprietary Speed Figures

These may be valuable later, but they are not near-term builds.

Reason:

They usually need paid data access and licensing. This is a business decision, not a coding gap.

## 19. Prioritised Future Build List

Highest value first:

1. Add excuse flags to result notes.
   - Prevents wrong horse-memory conclusions from raw margins.

2. Collapse duplicated weak-evidence warnings into one evidence-richness factor.
   - Stops one missing-data problem being counted several times.

3. Add CLV logging for tipster mentions.
   - Measures tipster quality faster than win rate alone.

4. Define fixed evidence thresholds before the next review.
   - Makes promotion decisions cleaner and less emotional.

5. Add Brier score and reliability charts.
   - Shows whether Signal 75 scores are properly calibrated.

6. Backtest Confirm-stage blends against historical data.
   - Lets the data set tipster/market/Signal weighting rather than guessing.

7. Test horses-to-follow against a control group.
   - Proves whether Grandad-style flags add real edge.

8. Formalise weekly retrain, backtest and shadow challenger loop.
   - Turns learning from reports into a controlled pipeline.

9. Add future probation and rollback monitoring for promoted rules.
   - Protects against a promoted rule going bad.

10. Add trainer/jockey short-form windows and price-walk view.
   - Useful intelligence layer, not a public pick switch.

## 20. End-of-July Review Questions

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
13. Which challenger rules beat the champion?
14. Did any challenger only look good because of one lucky day?
15. Is there enough evidence to promote anything, or should it keep learning?
16. Would a promoted challenger need a probation/rollback rule?
17. Did duplicated weak-evidence warnings overstate risk?
18. Did missing data act like a genuine negative or mostly neutral uncertainty?
19. Did horses-to-follow outperform a fair control group?
20. Did any beaten-distance conclusion need an excuse flag?
21. Did tipster CLV identify better sources faster than win/place rate?
22. Are Signal 75 score bands calibrated honestly?

## 21. Rules Not To Break

Do not change automatically without review:

- proof history;
- result settlement maths;
- public ROI maths;
- unlock logic;
- Buy Me A Coffee logic;
- old published results;
- data structures users rely on.

Learning should improve the future without rewriting the past.

## 22. Final Summary

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

The self-teaching architecture adds one more important rule:

Let the system learn automatically, but only let proven challengers change the live method.

That is the long-term edge.
