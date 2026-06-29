# Signal 75 July 1 Improvements Readiness Memory

Date created: 29 June 2026  
Target review date: Wednesday 1 July 2026  
Status: Memory and readiness checklist  
Live scoring impact: None  
Proof impact: None  

## 1. Purpose

This note preserves the Wednesday 1 July improvement checklist.

The goal is to confirm the learning and review system is ready in the background.

This is not a live scoring change.

No change should be made to:

- scoring;
- pick generation;
- proof history;
- settlement maths;
- unlock logic;
- app logic;
- public result maths.

## 2. Already Built / Running

These are already part of the learning pipeline or connected tooling.

1. Daily self-learning update
   - Runs the learning pipeline after results.
   - Does not change live picks, proof, scoring, unlock, or settlement.

2. Race memory
   - Stores race-level evidence.
   - Tracks runners, course, time, result context and race setup.

3. Tipster memory
   - Stores tipster/source evidence.
   - Tracks which horses had tipster support and which sources were involved.

4. Race result notes
   - Stores post-race notes.
   - Includes beaten-distance and margin intelligence where available.

5. Head-to-head memory
   - Tracks horses that met each other before.
   - Helps identify horse-against-horse patterns.

6. Historic rival memory
   - Tracks repeat rival evidence.
   - Supports the Grandad's book layer.

7. Local intelligence database
   - Builds or refreshes the local intelligence layer from stored memory.

8. Post-race diagnosis
   - Reviews what happened after races.
   - Looks for missed winners, bad picks, and useful warnings.

9. Continuous training diagnostics
   - Tracks recurring learning patterns.
   - Keeps learning separate from live proof.

10. Combined learning layer
   - Joins runner data, tipster data, Grandad memory, result notes and diagnostics.

11. Collateral form review
   - Tracks horses that beat high-signal Signal 75 horses.
   - Identifies horses-to-follow and caution horses.

12. Score calibration check
   - Checks whether score bands behave sensibly.

13. Feature importance tracker
   - Helps review which factors are actually useful.

14. Winner intelligence
   - Tracks winners that may have been missed.
   - Helps identify future horses to follow.

15. Drift detector
   - Watches for changed patterns, such as tipster support weakening or pick counts changing.

16. Shadow promotion tracker
   - Compares non-live challenger ideas against the current live method.

17. Scenario ROI review
   - Reviews alternative rule scenarios without changing live proof.

18. Report archive housekeeping
   - Stops the system creating endless loose daily files.
   - Keeps old learning files safely archived.

## 3. Planned / Background Improvements To Verify

These are not live scoring changes. They should be checked as learning/backtest/shadow improvements before any promotion.

1. Excuse flags
   - Future labels such as hampered, blocked, eased, mistake, wrong going, no excuse recorded.
   - Purpose: avoid wrongly punishing horses from raw beaten distance alone.

2. Combined evidence-richness factor
   - Collapse duplicated warnings like unproven course, going, trip, surface and thin form.
   - Purpose: avoid counting one weakness several times.

3. CLV for tipsters
   - Track whether a tipped horse shortened or drifted by BSP.
   - Purpose: judge tipsters faster than win rate alone.

4. Fixed review thresholds
   - Decide in advance what counts as enough evidence.
   - Purpose: avoid changing rules based on one emotional good or bad week.

5. Brier score / reliability charts
   - Check whether 90+ score horses really perform better than 75-84 horses.
   - Purpose: prove the score scale is honest.

6. Horses-to-follow control group
   - Compare Signal 75 horses-to-follow against ordinary winners.
   - Purpose: prove Grandad's book adds real edge.

7. Time decay on horse memory
   - Recent evidence counts more than old evidence.
   - Purpose: keep horse memory current.

8. Weekly retrain / backtest / shadow loop
   - Future challenger rules are generated and tested automatically.
   - Purpose: learning becomes structured rather than ad hoc.

9. Promotion gate
   - No challenger affects live picks until it proves itself.
   - Purpose: protect public selections and proof.

10. Future rollback monitor
   - If a promoted rule later misbehaves, revert to the previous method.
   - Purpose: circuit breaker for future changes.

11. Trainer/jockey 14/30-day windows
   - Planned future intelligence.
   - Purpose: track short-term stable/rider form.

12. Price-walk view
   - Planned dashboard/learning layer.
   - Purpose: see how price moved through the day, not just final BSP.

## 4. Wednesday 1 July Reminder Instruction

On Wednesday 1 July, confirm:

1. The learning pipeline is still running.
2. The background learning files are updating.
3. No learning job has changed live scoring, proof, settlement, unlock, app logic, or public result maths.
4. The planned improvements are either implemented as learning-only checks or still marked as future work.
5. Any future build should be tested in shadow before promotion.

## 5. End-Of-July Reminder

The end-of-July review still matters.

After the Wednesday 1 July readiness reminder fires, restore or recreate the end-of-July reminder to review:

- false consensus;
- trusted/independent tipster sources;
- condition confidence;
- poor recent form protection;
- thin form warnings;
- same-course clusters;
- large-field chaos;
- collateral form/rival winners;
- horses to follow;
- caution horses;
- beaten-distance evidence;
- ROI impact;
- Patent viability;
- mobile card clarity;
- whether any evidence is strong enough to promote into live selection rules without corrupting proof history.

