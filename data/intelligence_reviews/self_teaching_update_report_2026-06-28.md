# Signal 75 Self-Teaching Update Report

Date: 28 June 2026  
Status: Learning and strategy update only  
Live scoring impact: None  
Proof impact: None  

## 1. What Was Added To The Learning Brief

The useful part of the new self-teaching architecture has been added to the full Signal 75 learning brief.

The main update is this:

Signal 75 should keep learning automatically every night, but it should not let a new idea change public picks until that idea has proved itself.

This gives us the best of both worlds:

- automatic learning from every race;
- no uncontrolled live changes;
- proper evidence before changing strategy;
- cleaner end-of-month review;
- safer future automation.

## 2. Useful Ideas Taken From The New Architecture

### Champion And Challenger

Used.

This is important because it gives Signal 75 a simple structure:

- the live selection method is the champion;
- new ideas become challengers;
- challengers run in shadow first;
- only proven challengers can be promoted.

This stops us jumping from one idea to another after one bad or good day.

### Fully Automatic Nightly Learning

Used.

This fits the horse logging system perfectly.

Every night the system should keep updating:

- horses that beat our selections;
- horses that won easily;
- horses that were heavily beaten;
- head-to-head evidence;
- rival evidence;
- tipster accuracy;
- warning accuracy;
- market and condition notes;
- horses to follow;
- caution horses.

This is the modern Grandad’s book.

### Scheduled Retraining

Used as a future direction.

The system can eventually rebuild candidate weights for:

- tipster quality;
- condition confidence;
- rival evidence;
- horses-to-follow;
- caution horses;
- market support;
- false consensus.

These should become shadow challengers first, not live changes.

### Drift Detection

Used.

This means Signal 75 should notice when patterns change, for example:

- tipsters become less useful;
- one source creates false consensus;
- course/weather patterns change;
- large-field races become unreliable;
- a rule starts producing too many or too few picks.

When that happens, the system should trigger a review or retrain.

### Promotion Gate

Used.

This is the key safety rule.

A challenger should only become live when it has enough evidence and beats the current live method properly.

At first this should need manual approval.

Later it could become a 48-hour veto window, where the system says a change is ready and John can stop it if it looks wrong.

### Automatic Rollback

Used as a future requirement.

If a new rule is promoted later and starts performing badly during a probation period, Signal 75 should be able to revert to the previous live method and flag the issue.

This is not needed today because no live rule has been promoted by this update.

## 3. What Was Not Used Yet And Why

### Full Automatic Live Promotion

Not used yet.

Reason:

Public picks affect real betting decisions. The system can learn automatically, but switching live selection logic should stay gated.

### Self-Play Style AI Learning

Not used.

Reason:

Horse racing cannot be simulated like chess or Go. We cannot create millions of perfect fake races and learn from them safely.

### Immediate Automatic Scoring Weight Changes

Not used yet.

Reason:

Any new weights must first run in shadow and prove they improve results without creating confusing picks.

### Rollback Code

Not implemented today.

Reason:

Rollback is only needed once rules are promoted automatically or semi-automatically. The brief now records it as a future requirement.

## 4. How This Improves The Horse Logging System

The horse logging system should now be treated as more than storage.

Each logged event becomes evidence for a future rule.

Examples:

- A horse beats a high-score Signal 75 horse: possible horse-to-follow evidence.
- A horse wins easily: positive future evidence.
- A horse is heavily beaten: caution evidence.
- A horse repeatedly beats the same rival: stronger rival evidence.
- A horse only wins when conditions match: condition-confidence evidence.
- A horse has fake tipster support: false-consensus evidence.

The important change is that these notes should feed challenger rules.

That means we do not just remember the horse. We test whether remembering that type of horse improves Signal 75.

## 5. How I See This Working

Daily:

1. Signal 75 makes picks using the current live method.
2. The system records all race results.
3. It logs who beat us, who won easily, who was heavily beaten, and what warnings fired.
4. It updates horse memory, tipster memory, rival memory and dashboard data.
5. It runs shadow challenger ideas without changing public picks.

Weekly or scheduled:

1. The system reviews accumulated evidence.
2. It creates candidate rule changes.
3. It tests them against old data and recent data.
4. It keeps only candidates that look genuinely useful.
5. It reports which challengers deserve review.

End of review period:

1. Compare champion versus challengers.
2. Check ROI, place rate, pick count, no-bet days and user clarity.
3. Promote only what is clearly better.
4. Keep everything else as learning.

## 6. Plain English Summary

The new architecture makes Signal 75 more professional.

It says:

- learn every night;
- test new ideas quietly;
- do not change live picks on a whim;
- promote only proven improvements;
- roll back future changes if they misbehave.

This is exactly how the Grandad’s book idea becomes a serious intelligence system rather than a pile of notes.
