# Signal 75 - July/August Learning Gap Memory

Date: 2026-07-01

Purpose: record Claude/Grok feedback on the current Signal 75 brief without
turning it into an immediate July live-system change.

## Current Decision

Do not implement these as live pick/scoring changes during the July run.

July should remain a clean observation period. The only July changes should be
dashboard clarity, data accuracy, automation health, cost control, and clear
bug fixes that protect proof/result accuracy.

These ideas should be reviewed for the end-of-July / August improvement cycle.

## Main Feedback To Preserve

1. Closed learning loop
   - Current system collects and diagnoses a lot of evidence.
   - Missing piece: a formal path from evidence to candidate rule, automatic
     backtest, shadow run, promotion candidate, human approval, and rollback.
   - This should be designed as a controlled improvement loop, not a fully
     automatic live-pick changer.

2. Better self-evaluation
   - Need stronger calibration checks, not just anecdotal review.
   - Add Brier score or similar probability/score calibration measure.
   - Add reliability curves by score band.
   - Add minimum sample sizes before treating any pattern as meaningful.

3. Tipster source grading
   - Tipster counts alone are not enough.
   - Track CLV: price when tipped versus BSP/settled market price.
   - Over time, grade sources by whether they beat the market, not just whether
     a horse won.
   - Add source decay so old good performance matters less over time.

4. Horse memory consolidation
   - Grandad's Book, head-to-head, field graph, and rival overlay should be
     described as one Horse Intelligence & Memory Layer.
   - Keep clear subsections:
     - direct rival record
     - margin / beaten-distance evidence
     - similar-condition evidence
     - transitive field graph evidence
     - guarded overlay into selection
   - This avoids duplication in the brief and dashboard.

5. Excuse flags
   - Add structured race-result excuses where available:
     - hampered
     - badly drawn
     - wrong going
     - slipped/stumbled
     - made mistake
     - pulled hard
     - not clear run
     - eased
   - Prevent poor learning from races where a horse had a genuine excuse.

6. Time decay on horses to follow
   - A horse that beat a strong Signal 75 horse should not stay important
     forever.
   - Recent evidence should matter more than old evidence.
   - Need decay rules for follow-horse, rival, and head-to-head evidence.

7. Survivorship-bias check
   - Test whether "beat a Signal 75 horse" is genuinely predictive.
   - Compare against a baseline of horses that beat any fancied/high-market
     horse.
   - Do not promote this evidence unless it beats the baseline.

8. Dashboard / public explanation
   - Keep the public version readable.
   - Use the detailed technical version for Codex/build work.
   - Avoid showing users too many overlapping names for the same memory layer.

## July Or August?

Likely July-safe:

- Record these ideas in memory.
- Improve dashboard wording if it reduces confusion.
- Add analysis-only reports if they do not affect picks.
- Track CLV as a passive metric if data already exists.

Likely August:

- Closed-loop promotion gate.
- Calibration/Brier score framework.
- Time-decay scoring inside memory overlay.
- Excuse flags affecting learning interpretation.
- Any change that affects live selection or official picks.

## Recommended End-Of-July Review Question

After the July run, ask:

"Which collected evidence would have improved ROI, place rate, and public
clarity without adding false confidence or breaking proof discipline?"

Only changes passing that test should be considered for August.
