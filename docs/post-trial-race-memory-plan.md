# Signal 75 Post-Trial Race Memory Plan

Date to review: 14 June 2026

Purpose: use the new race memory layer after the tipster-first live trial, without rewriting history or changing proof results.

## What We Built

- A daily race memory book in `data/horse_intelligence/race_memory_YYYY-MM-DD.json`.
- A master memory file in `data/horse_intelligence/race_memory_master.jsonl`.
- Horse profiles in `data/horse_intelligence/horse_memory_profiles.json`.
- A head-to-head book in `data/horse_intelligence/head_to_head_YYYY-MM-DD.json`.
- A master head-to-head file in `data/horse_intelligence/head_to_head_master.jsonl`.
- Head-to-head profiles in `data/horse_intelligence/head_to_head_profiles.json`.
- A historic rival intelligence file in `data/horse_intelligence/historic_rivals_YYYY-MM-DD.json`.
- A historic rival master file in `data/horse_intelligence/historic_rival_master.jsonl`.
- Historic rival profiles in `data/horse_intelligence/historic_rival_profiles.json`.
- The evening results job now tries to build this memory automatically after results and proof checks.
- This is logging only. It does not change picks, scoring, settlement, proof maths, unlock logic, or public JSON.

## Why It Matters

This is the modern version of the old racing notebook:

- remember horses that won or placed from the watchlist
- remember ordinary runners, not just official Signal 75 picks
- remember when one horse has already beaten another horse
- use the large historic Betfair engine file to spot previous rival meetings
- spot horses returning under similar conditions
- see which high-score horses keep failing
- see which trainer, jockey, course, price, and form patterns repeat
- separate useful evidence from noise before changing the system

## Findings Already Seen

- On 5 June 2026, Signal 75 selected Ice Max at Epsom.
- Persica had already beaten Ice Max before at Epsom on 7 June 2025.
- Persica beat Ice Max again on 5 June 2026.
- This is strong evidence that previous rival meetings matter and should be visible before selection review.
- The Persica/Ice Max example is exactly why this layer matters: Ice Max looked strong on score, course fit, and tipster support, but a direct rival had already shown stronger Epsom evidence.
- On 5 June 2026, Thundering On beat Amelia Earhart in the same Epsom race where Amelia Earhart was the official pick.
- On 5 June 2026, Silca Bay beat Asteverdi in the Goodwood race where Asteverdi was the official pick.
- The 5 June review also showed that one-tipster official picks were weak: 0 winners from 3 official picks, with only Asteverdi placed.
- Shadow/radar evidence found stronger same-race alternatives on that day, especially Seagulls Eleven, Persica, Thundering On, and Legacy Link.

Conclusion: Signal 75 should not only ask "does this horse score well?" It should also ask "has a rival in this race already proved stronger?"

## Adjustments From Review

- Treat this as a relationship graph between horses, not just a history file for individual horses.
- One previous meeting is a note, not a rule.
- Two or more meetings with the same horse ahead becomes useful evidence.
- Four or more meetings with one horse repeatedly ahead becomes a serious warning or confidence candidate.
- Recent evidence matters more than old evidence. Meetings inside the last 12 months should carry much more weight than older meetings.
- Old evidence should be downgraded if the race type, class, distance, or conditions are very different.
- Race type, subtype, course, race name, and distance should be kept with the evidence so we can tell whether the old meeting is genuinely comparable.
- The evening job collecting memory is only half the loop. Before any scoring change after 14 June, the morning picks generator must read these memory files before finalising picks.
- The 14 June test should ask: when a head-to-head warning fired, how often did the warned-against horse underperform?
- If that warning rate is clearly useful, for example above 60%, it can be considered for a small private overlay. If it is noisy, it stays as information only.

## Review On 14 June

Look at the accumulated memory files and answer:

- How did the two-week tipster-first trial perform for profit, ROI, win rate, place rate, no-bet days, watchlist results, 0/1/2/3+ tipster outcomes, and late drift?
- Which watchlist horses won or placed after being tracked?
- Which selected horses had negative head-to-head evidence against rivals?
- Which rivals had already beaten our selection before?
- Which historic rival records would have warned us off a weak pick or highlighted a stronger rival?
- Which head-to-head warnings were based on only one meeting, and which were based on repeated dominance?
- Which warnings were recent, within 12 months?
- Which warnings came from similar race type, distance, course, or class?
- What percentage of warned-against horses underperformed?
- Which high-score horses failed despite looking strong?
- Which horses are now repeat "book horses"?
- Which courses, trainers, jockeys, prices, and race types are repeating positively?
- Which tipster-source patterns are helping and which are not?
- Which evidence is clear enough to show as a public confidence note?
- Which evidence is strong enough to become a private overlay later?

## How To Use These New Settings

Use the new intelligence layers in this order:

- Keep Signal 75 score as the base horse-strength measure.
- Use strongest tipster consensus as external support, not as the whole decision.
- Use race memory to check whether the horse has been useful before: won, placed, failed, watched, official, or high-score loser.
- Use head-to-head memory to check whether a horse has already beaten another horse in the same race.
- Use historic rival intelligence to check the large Betfair engine history for previous meetings between today's runners.
- Use negative rival evidence as a warning first, not an automatic rejection.
- Use positive rival evidence as a confidence note first, not an automatic selection.
- Only promote any of this into scoring after it has been tested against proof and shadow results.

Possible overlay after review:

- Add a small positive overlay when a horse has repeatedly beaten today's rivals, especially within 12 months.
- Add a small warning overlay when today's rival has repeatedly beaten our horse.
- Add a stronger warning when the same rival beat our horse at the same course or similar race type.
- Do not treat a single old head-to-head result as a major penalty.
- Add a confidence note when a watchlist horse returns after beating useful rivals.
- Add a caution note when a high-scoring horse keeps losing to the same type of rival.

Evidence strength rules to test:

- `minor_note`: one recent meeting, useful to show but not to score.
- `useful_pattern`: at least two meetings where one horse has a clear edge.
- `strong_pattern`: at least four meetings, at least 75% dominance, and at least two meetings inside the last 12 months.
- `archive_only`: old or thin evidence, kept for history but not used for decisions.

Do not use this to rewrite historic proof. Use it only for future decision support after testing.

## Deferred Work To Remember

These ideas were agreed as useful, but should not be treated as live rule changes until reviewed:

- Add clearer 18+ responsible gambling wording and plain mobile/content-filter guidance.
- Continue Cloudflare delivery testing separately before changing live hosting.
- Test stronger tipster weighting in shadow only: small boost for 1-2 tipsters, bigger boost for 3-5, strongest for 6+.
- Add a decision-audit layer: why Signal 75 picked its horse, why the winner was missed, and whether another rule would have found it.
- Expand post-race intelligence beyond official picks to watchlist, rejected horses, and tipster-only horses.
- Do not trust the old +73.6% backtest until changes pass clean train/test walk-forward validation.
- Test value bands in shadow, especially 4.1-6.0 versus 4.1-8.0.
- Investigate going, ground, trainer, jockey, and draw-bias layers only when the data is reliable enough.
- Revisit growth and promotion automation: scorecards, social posts, email capture, weekly summaries, and "what we learned" content.
- Convert historic rival evidence into a tested overlay only after review; do not let it rewrite proof history.

## Safe First Overlay Ideas

Keep the first overlay informational only:

- "In the Signal 75 book"
- "Won/placed from watchlist before"
- "Has beaten today's rival before"
- "Today's rival has beaten this horse before"
- "Previous head-to-head warning"
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
- historic rival strength and previous head-to-head dominance
