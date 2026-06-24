# Signal 75 Post-14-June End-Of-Test Review Protocol

Created: 24 June 2026

Purpose: make the end-of-test decision evidence-led. This document does not
change picks, scoring, proof, settlement, or public results.

## Fixed Review Point

- Hold the scheduled review at the end of the current 14-day post-14-June
  trial.
- Do not promote a new scoring or selection rule unless there are at least
  40 settled official legs and at least 10 completed three-horse Patent days.
- If either threshold is not reached, keep the current live rule unchanged and
  extend evidence collection until both thresholds are met.
- No result after this document was created can be used to move the review
  point early or to claim that the trial has succeeded or failed early.

## Required End-Of-Test Report

Every report must show both measures below. A Patent can be lumpy because a
strong day with multiple winners has doubles and trebles as well as singles.

1. All completed Patent days: stake, return, profit, ROI, winners and place
   rate.
2. The same figures with the single best profit day removed. This is a stress
   check, not a replacement headline result.
3. A daily table showing the three official horses, whether the day was a full
   Patent, a partial/no-bet day, the stake actually included in proof, return,
   and profit.
4. Void/non-runner handling shown separately so it cannot look like a win,
   loss, or unplaced horse.

## Counting Rules To Reconcile Before Any Decision

- `Official legs` means every official horse, including horses published on a
  partial day that did not form a full three-horse Patent.
- `Patent days` means only days with three official horses and a real GBP14
  each-way Patent proof stake.
- `No-bet days` means no full Patent proof stake. They can still contain an
  official single horse or watchlist/radar evidence for learning.
- Reports must never divide a Patent return by all official legs, or a leg
  place rate by Patent days.

This specifically explains why the first post-14-June summary can show five
full Patent days (15 Patent legs) and 17 official legs: two additional
official horses were logged on partial/no-bet days and are useful for learning,
but were not staked as a full Patent.

## Evidence Checks Before Promoting A Rule

### 1. Avoid Double Counting

Show overlap tables before treating two findings as separate evidence. For
example, a Flat result inside the 4.1-6.0 price band belongs to both groups,
so it is not two independent confirmations.

Required overlap checks:

- price band versus race type
- price band versus tipster-source tier
- score range versus price band
- late-market signal versus price band
- same-course cluster versus race type

### 2. Do Not Promote Score-Band Shapes Yet

Do not use the current 75-84 / 85-94 / 95+ results to alter scoring. The
groups are too small and the apparent shape may be ordinary randomness. Keep
the existing principle instead: a high score never bypasses price, field,
form-risk, or evidence-quality checks.

### 3. Test False-Consensus Protection In Shadow First

The direction is approved for testing, not for immediate live use:

- Count each independent named source once.
- Deduplicate aliases, copied lists, aggregators and repeated mentions of the
  same source.
- Store raw tip count separately from independent trusted-source count.
- Keep two or three genuinely independent Tier 1 or Tier 2 sources as strong
  support; do not punish a horse merely because it has fewer sources.
- Flag only the specific problem case: a high raw tip total with weak or
  duplicated independent-source evidence.

Before any live promotion, backtest and shadow-test this against the full
available window. Report the effect on winners, places, missed winners,
official-leg ROI, Patent ROI, number of no-bet days, and source coverage.

### 4. Keep These As Warnings Until Proven

- missing course, going, surface or distance records
- same-course clustering
- late market movement
- Jumps versus Flat differences
- thin form records

Missing history is not proof that a horse is unsuitable. Improve the data
coverage first, then test whether the warning predicts poorer outcomes.

## Current Direction To Preserve Unless Evidence Contradicts It

- Signal 75 remains the base selection engine.
- Tipsters remain supporting evidence, not an automatic override.
- Keep the core 4.1-6.0 value band under review; do not widen it from this
  short sample.
- Keep deliberate no-bet days and do not force a weak third Patent leg.
- Keep watchlist, shadow and learning results outside public proof.

## End-Of-Test Decision Outcomes

For each candidate change, record one of these decisions:

- `PROMOTE`: enough independent evidence and a clean shadow/backtest result.
- `SHADOW LONGER`: promising but below the fixed sample threshold.
- `DATA FIRST`: the pattern is mostly caused by missing/incomplete data.
- `REJECT`: no repeatable improvement or it damages coverage unnecessarily.

No decision may rewrite historic proof or settled results.
