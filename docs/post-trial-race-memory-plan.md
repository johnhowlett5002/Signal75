# Signal 75 Post-Trial Race Memory Plan

Date to review: 14 June 2026

Purpose: use the new race memory layer after the tipster-first live trial, without rewriting history or changing proof results.

## What We Built

- A daily race memory book in `data/horse_intelligence/race_memory_YYYY-MM-DD.json`.
- A master memory file in `data/horse_intelligence/race_memory_master.jsonl`.
- Horse profiles in `data/horse_intelligence/horse_memory_profiles.json`.
- The evening results job now tries to build this memory automatically after results and proof checks.
- This is logging only. It does not change picks, scoring, settlement, proof maths, unlock logic, or public JSON.

## Why It Matters

This is the modern version of the old racing notebook:

- remember horses that won or placed from the watchlist
- remember ordinary runners, not just official Signal 75 picks
- spot horses returning under similar conditions
- see which high-score horses keep failing
- see which trainer, jockey, course, price, and form patterns repeat
- separate useful evidence from noise before changing the system

## Review On 14 June

Look at the accumulated memory files and answer:

- Which watchlist horses won or placed after being tracked?
- Which high-score horses failed despite looking strong?
- Which horses are now repeat "book horses"?
- Which courses, trainers, jockeys, prices, and race types are repeating positively?
- Which tipster-source patterns are helping and which are not?
- Which evidence is clear enough to show as a public confidence note?
- Which evidence is strong enough to become a private overlay later?

## Safe First Overlay Ideas

Keep the first overlay informational only:

- "In the Signal 75 book"
- "Won/placed from watchlist before"
- "Returning under similar conditions"
- "Trainer/jockey pattern has been positive"
- "High score has failed before"
- "Market support has been reliable/unreliable"

Do not let this change official picks until it has been reviewed against proof and live-trial evidence.

## Future Data To Add

- full finishing position for every runner
- beaten distance
- official going/ground
- race class
- course history
- distance history
- morning price versus late price versus BSP
- tipster source performance history
- trainer/jockey combination history
