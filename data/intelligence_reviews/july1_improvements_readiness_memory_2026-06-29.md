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

7. Field relationship memory
   - Already built and connected as a guarded memory layer.
   - Builds a richer Grandad's book profile for each horse.
   - Tracks rivals beaten, rivals lost to, repeated dominance, decisive margins, high-signal horses beaten, and condition/race-type evidence where available.
   - Feeds the existing memory overlay only when normal Signal 75 gates still pass.
   - This should not remain as a pending July 1 improvement; it is now an implemented background layer to monitor.

8. Field graph intelligence
   - Already built and added to the nightly self-learning sequence.
   - Checks the actual race field and asks:
     - which horses have beaten today's rivals before;
     - which horses have lost to today's rivals before;
     - whether there is a short indirect chain, such as Horse A beat Horse B and Horse B beat today's rival.
   - Writes `field_graph_YYYY-MM-DD.json` and `field_graph_profiles.json`.
   - The dashboard now shows this under Confirm and Learn.
   - Current use: learning/support evidence only. It is not a standalone pick method and does not alter proof.

9. Local intelligence database
   - Builds or refreshes the local intelligence layer from stored memory.

10. Post-race diagnosis
   - Reviews what happened after races.
   - Looks for missed winners, bad picks, and useful warnings.

11. Continuous training diagnostics
   - Tracks recurring learning patterns.
   - Keeps learning separate from live proof.

12. Combined learning layer
   - Joins runner data, tipster data, Grandad memory, result notes and diagnostics.

13. Collateral form review
   - Tracks horses that beat high-signal Signal 75 horses.
   - Identifies horses-to-follow and caution horses.

14. Score calibration check
   - Checks whether score bands behave sensibly.

15. Feature importance tracker
   - Helps review which factors are actually useful.

16. Winner intelligence
   - Tracks winners that may have been missed.
   - Helps identify future horses to follow.

17. Drift detector
   - Watches for changed patterns, such as tipster support weakening or pick counts changing.

18. Shadow promotion tracker
   - Compares non-live challenger ideas against the current live method.

19. Scenario ROI review
   - Reviews alternative rule scenarios without changing live proof.

20. Report archive housekeeping
   - Stops the system creating endless loose daily files.
   - Keeps old learning files safely archived.

## 2A. Duplicate / Overlap Check

Checked on 29 June 2026.

The learning system has several layers that sound similar, but they now have separate jobs:

1. Race memory
   - Stores what happened in each race and each runner's daily context.
   - This is the raw daily notebook.

2. Head-to-head memory
   - Stores direct same-race outcomes: Horse A beat Horse B.
   - This is the direct rival evidence.

3. Historic rival memory
   - Looks back through stored historical records to find previous meetings between today's runners.
   - This is the older-race rival lookup.

4. Field relationship memory
   - Builds a rolling horse profile from repeated rival evidence, margins, decisive wins and high-signal victims.
   - This is the horse-level Grandad profile.

5. Field graph intelligence
   - Looks at today's actual race field and ranks direct edges, warning edges and short indirect chains.
   - This is the field-level relationship view.

6. Combined learning layer
   - Joins the above evidence into one review table.
   - This should combine evidence, not create another competing pick method.

7. Dashboard
   - Shows the evidence in four simple stages: Find, Confirm, Protect, Learn.
   - It must not become another calculation engine.

Current conclusion:

- No exact duplicate automated job was found.
- Duplicate-looking ideas have been renamed or grouped by purpose.
- The main rule is now: collect many evidence layers, but keep only one live selection process.
- New learning layers should either feed an existing evidence category or stay marked as future/shadow work.

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

13. Statistical horse strength model
   - Future shadow-only model using the Plackett-Luce family.
   - Important data caveat: the large Betfair history has WINNER/LOSER/REMOVED, not full finishing order, so the correct first version is winner-vs-field conditional logit, not full finishing-order Plackett-Luce.
   - Purpose: estimate a separate true-strength probability for each runner and compare it with Signal 75 scores.
   - This could strengthen the world-class horse profiler later, but it should not affect July 1 live picks.
   - Required first checks: predicted probabilities must sum to 1.0 per race, calibration must be reported by probability band, and output must stay in shadow tables until reviewed.
   - This should use the field graph and horse-memory evidence as inputs later, not duplicate the graph layer.

14. Full finishing-order model later
   - True multi-position Plackett-Luce becomes possible only if we capture full 1st/2nd/3rd/4th finishing order at scale.
   - Purpose: eventually learn more from places and beaten runners, not just winners.
   - Current status: future work, not July 1 readiness.

## 4. Wednesday 1 July Reminder Instruction

On Wednesday 1 July, confirm:

### Practical Readiness Check

1. Picks generated normally.
2. `self-learning-update.py` is ready to run after results.
3. Dashboard still shows learning-only / no proof change.
4. Dashboard shows field graph evidence under Confirm and Learn.
5. No scoring, proof, result, app, unlock or settlement files were unintentionally changed.
6. July 1 planned items are either background-tested or clearly marked as future work.

### Learning Readiness Check

1. The learning pipeline is still running.
2. The background learning files are updating.
3. No learning job has changed live scoring, proof, settlement, unlock, app logic, or public result maths.
4. The planned improvements are either implemented as learning-only checks or still marked as future work.
5. Duplicate-looking layers are still separated by purpose and not acting as competing pick methods.
6. Any future build should be tested in shadow before promotion.

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
