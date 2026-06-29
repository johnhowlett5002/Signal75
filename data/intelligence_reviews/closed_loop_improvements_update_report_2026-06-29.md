# Signal 75 Closed-Loop Improvements Update Report

Date: 29 June 2026  
Status: Planning and learning update only  
Live scoring impact: None  
Proof impact: None  

## 1. What I Used From The Updated Brief

The updated brief is useful. I have folded the important parts into the full Signal 75 learning brief.

Nothing in this update changes picks, scoring, proof, settlement, unlock logic or public results.

## 2. Useful Items Added

### 1. Collapse Duplicate Weak-Evidence Warnings

Used.

Reason:

Unproven course, unproven going, unproven trip, missing surface data and thin form often mean the same thing: we do not yet have enough evidence.

Counting them separately can make one weakness look like four separate problems.

Future direction:

Create one evidence-richness factor and backtest whether it genuinely predicts poor performance.

### 2. Excuse Flags

Used.

Reason:

Raw beaten distance can mislead the system.

A horse beaten 22 lengths with no excuse is a serious warning. A horse beaten 22 lengths after being hampered, eased or unsuited by sudden ground change is less clear.

Future fields to capture:

- hampered;
- blocked;
- wide throughout;
- eased late;
- mistake;
- wrong going;
- returning from a break;
- no excuse recorded.

This is a high-value addition for horse logging.

### 3. Horses-To-Follow Control Group

Used.

Reason:

We need to prove that “beat one of our high-score horses” is better than simply “won a race”.

Future direction:

Compare horses-to-follow against ordinary winners and similar runners. Only promote it if it beats the control group.

### 4. Time Decay On Horse Memory

Used.

Reason:

A horse that looked important months ago should not carry the same weight forever.

Future direction:

Recent evidence should count more than old evidence. Old evidence should become a note unless repeated or supported by current form.

### 5. Phase 1 Priors

Used.

Reason:

Current overlay values are starting assumptions, not proven truth.

Examples:

- tipster boost;
- rival boost;
- caution penalty;
- false consensus warning;
- condition confidence.

Future direction:

Refit them from evidence, test as challengers, then review before live promotion.

### 6. CLV For Tipsters

Used.

Reason:

Win rate alone is noisy. Closing Line Value helps show whether a tipster consistently points to horses the market later respects.

Plain English:

If a tipster backs a horse at 6/1 and it later starts at 4/1, that is useful information even if the horse loses that day.

### 7. Brier Score And Reliability Charts

Used.

Reason:

ROI matters, but it can be distorted by one big return.

Score calibration asks a different question:

Do horses scored 90-100 actually behave better than horses scored 75-84?

This helps prove whether the Signal 75 score scale is honest.

### 8. Fixed Evidence Thresholds Before Review

Used.

Reason:

We should define what counts as enough proof before judging the next batch of results.

This avoids changing strategy because of one emotional good or bad week.

### 9. Trainer/Jockey Short-Form Windows

Used as a future learning item.

Reason:

Trainer and jockey 14/30-day form is a useful public racing signal and should be captured when available.

### 10. Price-Walk View

Used as a future dashboard/learning item.

Reason:

The path of a price through the day can be more useful than only looking at BSP.

It should be learning/dashboard information first, not a last-minute public pick switch.

## 3. What I Did Not Use Yet

### 1. Immediate Live Scoring Changes

Not used.

Reason:

The brief itself says these changes require backtesting or promotion gates first.

### 2. Gradient-Boosted Model As A Live Replacement

Not used.

Reason:

It may be useful later to validate overlays, but Signal 75 still needs explainable public logic. A black-box replacement would be premature.

### 3. Kelly Staking

Not used for live staking.

Reason:

Signal 75 proof is based on a fixed each-way Patent structure. Changing stakes would damage comparability. It can only be a dashboard-only confidence note later.

### 4. Sectional Timing And Proprietary Speed Figures

Not used now.

Reason:

These likely require paid data and licensing. That is a business decision, not a safe immediate build.

### 5. Automatic Promotion Without Review

Not used.

Reason:

Public picks affect betting decisions. Learning can be automatic. Live promotion needs a gate.

## 4. How This Improves The Horse Logging System

The horse logging system now has a clearer job.

It should not only remember facts. It should decide what type of evidence each fact is.

Examples:

- “Horse beat our selection” becomes rival evidence.
- “Horse won easily” becomes follow evidence.
- “Horse was beaten badly” becomes caution evidence.
- “Horse had an excuse” stops a bad conclusion.
- “Horse keeps repeating the same pattern” becomes stronger evidence.
- “Horse evidence is missing” becomes uncertainty, not automatic failure.

This makes the Grandad book safer and more useful.

## 5. How I See This Working

Daily:

1. Picks run as normal.
2. Results settle.
3. Horse, rival, margin, tipster and warning evidence is logged.
4. Excuse flags are added where available.
5. Horses-to-follow and caution horses are updated.
6. Shadow challengers compare against the live method.

Weekly or scheduled:

1. Evidence is reviewed automatically.
2. Tipster CLV and source quality are updated.
3. Score calibration is checked.
4. Challenger rules are backtested.
5. Anything promising stays in shadow until enough evidence exists.

Review point:

1. Compare champion against challengers.
2. Check whether evidence thresholds were met.
3. Check whether one lucky result distorted the answer.
4. Promote only clear improvements.

## 6. Practical Build Priority

The order I would use:

1. Excuse flags.
2. Combined evidence-richness factor.
3. CLV logging for tipsters.
4. Fixed review thresholds.
5. Brier/reliability score tracking.
6. Horses-to-follow control-group test.
7. Weekly retrain/backtest/shadow loop.
8. Probation and rollback for future promoted rules.
9. Trainer/jockey short-form windows.
10. Price-walk dashboard view.

## 7. Final View

This updated brief is stronger than the previous one because it deals with the main risk in learning systems: false confidence.

The system should still learn automatically.

But it should also ask:

- is this new evidence genuinely different?
- are we double-counting the same weakness?
- did the horse have a valid excuse?
- is this pattern better than a fair control group?
- is the score scale honest?
- has the challenger proved itself before changing live picks?

That is the right direction for Signal 75.
