# Signal 75 Recommendations And Roadmap Memory

Last updated: 2026-07-21

This file is the working memory for Signal 75 improvements. It merges the strongest useful ideas from multiple AI reviews plus John's decisions. Suggestions have been deduplicated, corrected against the real live system, and ordered by importance.

## Core Rule Before Any Development

Every change must be tested before it affects the public site.

No feature should change public picks, proof figures, settlement results, `picks.json`, `performance.json`, mobile rendering, GitHub deployment, or existing automation unless it has passed the relevant checks.

Minimum release checks:

1. Inspect the affected files.
2. Make the smallest safe change.
3. Run syntax checks.
4. Validate JSON.
5. Run a sample generation or settlement test where safe.
6. Run a backtest or shadow test where possible.
7. Visually check the site.
8. Review `git status` and `git diff`.
9. Have a rollback path.
10. Commit and push only the intended files.

Signal 75 must remain statistically honest.

Do not:

- overhype
- inflate results
- fabricate missing data
- backfill fake consensus
- rewrite settled proof history
- count radar or shadow tests in public proof

## Core Purpose

Signal 75 is a Betfair-driven UK racing intelligence engine.

The goal is not to pick every winner.

The goal is to eliminate structurally weak bets and focus only on repeatable edge.

No-bet days are acceptable. They are a feature, not a bug.

Every race, every runner, and every result should either:

- support a selection
- reject a weak selection
- improve future intelligence

Public principle:

> Every Race. Every Runner. Every Result.

## Current Important Locations

Live site:

- `https://signal75.co.uk`

GitHub repo:

- `johnhowlett5002/Signal75`

Live working repo:

- `/Users/johnhowlett/Signal75`

Main live files:

- `/Users/johnhowlett/Signal75/index.html`
- `/Users/johnhowlett/Signal75/app.js`
- `/Users/johnhowlett/Signal75/sw.js`
- `/Users/johnhowlett/Signal75/picks.json`
- `/Users/johnhowlett/Signal75/performance.json`
- `/Users/johnhowlett/Signal75/data`
- `/Users/johnhowlett/Signal75/scripts`

Main scripts:

- `/Users/johnhowlett/Signal75/scripts/generate-picks-betfair.py`
- `/Users/johnhowlett/Signal75/scripts/update-results-mac.py`
- `/Users/johnhowlett/Signal75/scripts/scoring_engine.py`
- `/Users/johnhowlett/Signal75/scripts/daily_consensus_overlay.py`
- `/Users/johnhowlett/Signal75/scripts/betfair_client.py`
- `/Users/johnhowlett/Signal75/scripts/runner_matcher.py`
- `/Users/johnhowlett/Signal75/scripts/generate-performance.py`

Engine and research folder:

- `/Users/johnhowlett/Desktop/Signal75-Engine`

Important research files:

- `backtest.py`
- `run_overnight_validation.py`
- `backtest_results`
- `betfair_uk_races_master.csv`
- `betfair_uk_races_full_v2.csv`
- `betfair_uk_races_full_v4.csv`
- `betfair_uk_races_full_v5.csv`
- `roi_tables.json`
- `build_v4_from_streams.py`
- `build_v5_settled.py`

Raw Betfair stream archives:

- `/Users/johnhowlett/Desktop/Signal75-Engine/BASIC 1`
- `/Users/johnhowlett/Desktop/Signal75-Engine/BASIC 2`
- `/Users/johnhowlett/Desktop/Signal75-Engine/BASIC 3`
- `/Users/johnhowlett/Desktop/Signal75-Engine/BASIC 4`

Do not delete the `BASIC 1-4` folders.

## Current Live System

Hosting:

- GitHub Pages serves the current public site.

Automation:

- Morning resolve: `09:00`
- Morning picks: `10:00`
- Late-market shadow checks: `11:30`, `13:30`, `15:30`
- Evening results/proof: `19:00`, `20:30`, `21:30`, `22:15`

The multiple evening runs are deliberate. Some races finish after 7pm, so later runs fill pending results without overwriting settled ones.

## Rich Form Archive Memory

The local rich form archive is a dashboard and research layer, not a live pick rule yet.

Use it where possible to improve confidence checks before trusting an official pick:

- Compare today's recent form string with historic form patterns.
- Show how often horses with similar form won and placed next time.
- Treat poor similar-form win/place rates as a pre-pick warning.
- Treat strong similar-form win/place rates as supporting evidence, not proof by itself.
- Use sample size so small pattern groups do not get overtrusted.
- Use it in Challenger Lab before any scoring or gate change.
- Use it to explain picks more clearly on the dashboard for John and Deb.

Promotion rule:

- Do not let rich form data change official picks until it has been tested as a challenger/shadow layer and reviewed manually.
- Minimum review target: 14 settled days before even considering a live gate or score adjustment.
- Prefer a confidence warning or small adjustment before any hard block.

## Current Scoring System

Every runner starts at base score `60`.

The score is adjusted by:

- odds band
- race type
- course profile
- horse historical profile
- recent form
- days since last run
- field size
- Betfair market confidence
- Chester draw penalty where relevant

Scores are normalised so they remain in a sensible range rather than exploding into 130-150.

Approximate score meaning:

- `65+` = radar/watchlist possible
- `75+` = official consideration
- `82+` = strong
- `88+` = banker-level score

Current historical data base:

- about `3.49m` settled Betfair runner records
- about `296,977` horse profiles
- `482` course profiles
- `22` race type categories
- `8` odds bands

## Current Official Pick Rules

Official public picks must pass all of these:

- Signal 75 score at least `75`
- odds between `4.1` and `6.0`
- field size at least `8`
- named tipster support required
- one horse per race
- maximum three official picks per day

Tipster-first gate:

1. Try horses with `3+` named tipsters.
2. If none qualify, try horses with `2+` named tipsters.
3. If none qualify, try horses with `1+` named tipster.
4. If none pass the Signal 75 gates, publish no official picks and show radar/watchlist only.

Important:

- Tipster support alone does not create an official pick.
- A horse still needs to pass score, odds band, field-size, and race separation rules.
- No-bet days are valid.

## Radar / Watchlist Rules

Radar is not official proof.

Radar can include:

- score at least `65`
- odds between `2.1` and `12.0`
- tipped horses that fail official gates
- strong Signal 75 horses without enough tipster support
- horses that may become interesting later through market movement

Radar must show post-race positions where possible.

Radar should explain why a horse missed official status, for example:

- outside value band
- too few runners
- no/low tipster support
- weak field-size fit
- market drift
- same race already used

## Proof Rules

Only official public picks count toward proof.

Do not count:

- radar horses
- shadow consensus horses
- late-market shadow horses
- rejected-by-gate horses
- tipster-only alert horses

Do not mark unresolved races as lost. Keep unresolved races pending until a later result run or morning resolve can settle them.

Each official day is designed around a 3-horse each-way Patent:

- 3 singles
- 3 doubles
- 1 treble
- each-way doubles this to 14 bet lines
- £1 each-way = £14 total stake

Proof should show honest metrics:

- winners
- win rate
- place rate
- patent profit
- ROI

Do not show `100% strike` unless all official selections won.

## Performance Targets

These are research targets, not public promises.

Useful targets to monitor:

- place rate target: `84-87%`
- win rate target: `39-47%`
- profit factor target: `1.90-2.40`
- 90-day Sharpe target: `2.2+`
- expectancy target: `+0.18` units per bet or better
- max drawdown target: ideally under `20-27%`
- edge stability score target: `85/100`

Important:

- ROI targets such as `98-140%` are aspirational research numbers, not public claims.
- Live proof matters more than headline backtest ROI.
- Bankroll protection matters more than forcing daily action.

## Ordered Roadmap

### 1. Proof Page Metrics Fix

Purpose:

Make the public proof page mathematically correct for a UK each-way Patent.

Problem:

Wording such as `2 winners` and `100% strike` is misleading if there were 3 official selections and only 2 won.

Correct display:

- Winners = winning selections
- Win Rate = winners / official selections
- Place Rate = WON or PLACED / official selections
- Patent Profit = total return minus stake
- ROI = patent profit / stake x 100

Implementation:

- Update display logic only.
- Do not change settlement logic.
- Do not change `picks.json` structure.
- Do not change `performance.json` structure.
- Official picks only.
- Radar/shadow excluded.

Reason:

Proof trust is more important than any engine upgrade.

### 2. Proof / History Rebuild From Real Archives Only

Purpose:

Ensure `performance.json` can be rebuilt from genuine archived results only.

Use:

- `/Users/johnhowlett/Signal75/data/YYYY-MM-DD.json`

Rules:

- Do not fabricate missing days.
- Do not fill the holiday gap unless real archive files exist.
- Exclude radar horses.
- Exclude shadow variants.
- Log incomplete days separately.

Reason:

Public proof must be auditable and honest.

### 3. Daily Pipeline Health Check Logging

Purpose:

Stop silent failures such as stale picks.

Create:

- `/Users/johnhowlett/Signal75/data/pipeline_health_YYYY-MM-DD.json`

Include:

- generator started
- generator completed
- Betfair runner count
- matched runner count
- scored runner count
- official pick count
- radar count
- consensus overlay status
- `picks.json` written
- Git push status if available
- settlement completed
- `performance.json` updated
- errors

Reason:

This is one of the best new suggestions. It would make problems visible before users spot them.

### 4. Service Worker / Cache Safety

Purpose:

Prevent mobile/Safari cache problems and stale picks.

Rules:

- `picks.json` and `performance.json` must be network-first.
- cache-busting must remain active.
- `sw.js` must not block page loading.
- broken service worker must not return null responses.

Options:

- simplify `sw.js`
- or disable service worker until the core site is stable

Reason:

Stale public display damages trust even when the engine worked correctly.

### 5. Engine Integrity And Reliability

Keep the live site stable.

Tasks:

1. Ensure morning picks generate for the correct date.
2. Ensure Flat and Jumps tabs never borrow from each other.
3. Ensure no-bet days still show useful radar.
4. Ensure evening result runs settle late races across `19:00`, `20:30`, `21:30`, and `22:15`.
5. Ensure morning resolve fills any remaining unsettled positions.
6. Ensure GitHub push/token automation keeps working.
7. Keep service worker cache versions bumped whenever public JS/HTML changes.

Reason:

No scoring upgrade matters if the live system looks broken.

### 6. Tipster Consensus Quality

Strengthen tipster capture before changing scoring too much.

Tasks:

1. Count named tipsters separately, not just websites.
2. Expand source coverage for Racing Post, Sporting Life, Timeform, At The Races, Newsboy, Robin Goodfellow, Newmarket, Farringdon, myracing, GG, and newspaper naps.
3. Store tipster names and sources in daily overlay files.
4. Track tipster-only alert horses.
5. Build source/tipster performance profiles over time.
6. Avoid fabricated consensus. Unknown must remain unknown.

Reason:

John believes people in the know matter. The system should test that seriously without letting weak public favourites damage proof.

### 7. Shadow Test Stronger Tipster Weighting

Do not put stronger tipster scoring live immediately.

Shadow-test variants first:

Variant A:

- 1-2 named tipsters = `+1` ranking point
- 3-5 named tipsters = `+3`
- 6+ named tipsters = `+6`

Variant B:

- 2 named tipsters = `+1`
- 3-5 named tipsters = `+2`
- 6+ named tipsters = `+4`

Variant C:

- 3+ tipsters required for official consideration
- if no 3+ horse qualifies, no official pick instead of dropping to 2/1

Guardrails:

- Consensus must not drag in poor outsiders.
- Consensus must not bypass minimum score.
- Consensus must not bypass field-size safety.
- Any live change must beat the current rule in shadow or live validation.

### 8. Decision Audit Layer

For each race, save a decision audit.

Record:

- winner
- official pick, if any
- radar pick, if any
- highest Signal 75 score
- highest tipped horse
- why the winner was not picked
- whether the rejection was correct under current rules
- whether an alternative rule would have selected the winner

Reason:

This will show whether the system is missing winners for good reasons or bad reasons.

### 9. Post-Race Intelligence Database

Continue building persistent horse memory.

Record all meaningful horses:

- official picks
- radar horses
- shadow consensus picks
- late-market shadow horses
- rejected-by-gate horses
- tipster-only alert horses

Store:

- date
- horse
- course
- race time
- race type
- score
- odds/BSP
- tipster count
- tipster names
- sources
- selection type
- result
- finishing position
- returns
- whether Signal 75 was right
- whether tipsters were right
- whether market support helped

Do not let this change live picks until enough data exists.

### 10. Horse Profile Builder

Build rolling horse-level memory from the intelligence database.

Track:

- total Signal 75 appearances
- official pick appearances
- radar appearances
- wins
- places
- losses
- win rate
- place rate
- average Signal 75 score
- average BSP
- course records
- last run date
- last result
- trend: IMPROVING / DECLINING / STABLE / UNKNOWN

Do not use profiles for scoring until the profile builder has enough clean data.

### 11. Loss Reason / Result Interpretation Tags

Learn from failures, not just winners.

Possible labels:

- CONFIRMED_MODEL
- OUTRAN_SCORE
- UNDERPERFORMED
- MARKET_WAS_RIGHT
- MODEL_WAS_RIGHT
- TIPSTERS_RIGHT
- TIPSTERS_WRONG
- POOR_GOING_FIT
- STRONG_GOING_FIT
- BAD_DRAW
- PACE_COLLAPSE
- WEAK_FINISH
- RACE_CHAOS
- UNKNOWN

Rules:

- Labels must be separate from raw result data.
- Do not invent beaten distance.
- Do not invent pace claims.
- Use UNKNOWN where evidence is missing.

### 12. Consensus Shadow Validation

Purpose:

Test consensus honestly from today forward.

Reason:

Historical Betfair data does not contain historical public tips, so true old consensus backtesting is not honest without a historical tips archive.

Current/possible files:

- `/Users/johnhowlett/Signal75/data/consensus_shadow_YYYY-MM-DD.json`
- `/Users/johnhowlett/Signal75/data/consensus_overlay_YYYY-MM-DD.json`

Variants:

- `baseline_live_rule`
- `consensus_rank_v1`
- `consensus_prefer_tipped_v1`
- `consensus_strict_tipped_v1`
- future `consensus_strong_rank_v1`

Rules:

- Public picks unchanged until proven.
- Proof unchanged.
- Shadow variants settled separately.
- Compare after meaningful live sample.

### 13. Tipster-Only Alert Tracking

If several public tipsters back a horse that Signal 75 does not select, log it as intelligence.

Use category:

- `TIPSTER_ONLY_ALERT`

Track:

- horse
- sources
- source_count
- Signal 75 score
- why Signal 75 rejected it
- result
- whether Signal 75 was right to reject it

Do not automatically add these to public picks.

### 14. Value Divergence / Market Conflict Logging

Track where Signal 75 and the market disagree.

Examples:

- high Signal 75 score at bigger odds = VALUE ALERT
- low/moderate Signal 75 score at short odds = MARKET CONFLICT
- tipsters love horse but Signal rejects = PUBLIC DISAGREEMENT
- Signal loves horse but tipsters ignore = HIDDEN VALUE

Logging only first.

### 15. Clean Backtest And Walk-Forward Validation

The old `+73.6%` backtest is not reliable because it used leaked ROI tables and forced betting days.

Required validation method:

1. Train only on past data.
2. Test only on future unseen data.
3. Enforce all live gates.
4. Record no-bet days.
5. Compare Flat and Jumps separately.
6. Compare odds bands separately.
7. Track drawdowns and worst periods.
8. Compare every change against the current live benchmark.

Potential split:

- train: `2015-2021`
- test: `2022-2026`

Better method:

- rolling walk-forward windows.

### 16. Value Band Testing

Current official live band:

- `4.1-6.0`

Suggested test bands:

- `4.1-6.0` current benchmark
- `4.1-8.0` broader candidate
- `3.5-6.0` to include well-backed tipster horses like Happy Chandler-type cases
- `4.1-8.0` only when tipster count is `2+`
- `4.1-8.0` only when score is `82+`

Do not widen live proof until shadow tests support it.

### 17. Field Size And Each-Way Safety

Current official rule:

- field size `8+`

Recommended tests:

- official field size `8-14`
- penalise `15+`
- radar only for `5-7`
- stronger caution for small-field jumps

Reason:

Each-way value weakens in small fields, while very large fields introduce chaos.

### 18. Late Market Movement Layer

Keep as shadow first.

Track:

- horses moving into value band after morning publication
- horses drifting badly after selection
- tipped horses with strong late support
- same-race alternatives that overtake the official/radar horse

Do not automatically swap public picks late in the day yet.

### 19. Confidence Decay

Do not put broad confidence decay live yet.

The first version was too blunt and risked punishing proven horses.

Suggested future decay signals:

- very few runs
- course debut
- distance debut
- long layoff
- first run of season
- sharp class rise
- first-time headgear
- stale form

If revisited:

- protect horses with strong history
- protect horses with 30-50+ historical runs
- apply stricter decay only to thin, stale, low-sample profiles
- use decay as a ranking/tie-breaker before using as a hard gate
- cap total decay so it cannot destroy a horse for one weak flag

### 20. Horse Quality vs Race Environment Split

Create two visible/internal scores:

- Horse Quality Score
- Race Environment Score

Horse Quality can include:

- horse history
- recent form
- days since run
- trainer/jockey context

Race Environment can include:

- course
- race type
- field size
- odds band
- draw/going where available

Reason:

This helps show whether a good horse is in a bad race setup, or an average horse is in an excellent setup.

### 21. Trainer/Jockey Layer

Add only after reliable data is available.

Test:

- trainer 14-day form
- jockey 14-day form
- trainer/jockey combination
- course-specific trainer/jockey performance

Use as small scoring nudges first.

### 22. Going And Ground Intelligence

Promising but not ready unless reliable going data is captured.

Rules:

- never guess going
- store unknown as null
- only score going if source is reliable
- test historically where data exists

### 23. Draw Bias And Course Profile Layer

Useful for biased Flat tracks.

Candidate courses:

- Chester
- Beverley
- York
- Ascot straight
- Kempton
- Southwell
- other tight/known draw-biased tracks after evidence

Current Chester penalty exists.

Next step:

- formalise draw-bias table
- test by course, distance, and field size

### 24. Real-Time Drift Detector

Logging first.

Track:

- morning price
- late price
- percentage drift
- percentage steam/shortening
- result

Possible future signals:

- drift over `50%` = warning
- drift over `100%` = possible downgrade
- shortening over `30%` = market support

Do not remove public picks until proven in shadow.

### 25. Market Confidence Engine

Use Betfair exchange behaviour as a possible long-term edge.

Inputs:

- steam/drift
- traded volume
- liquidity
- price stability
- late support
- favourite weakness

Keep as shadow until proven.

### 26. Liquidity / Execution Filter

Purpose:

Ensure selections are realistically bettable.

Track:

- matched volume
- available liquidity
- price stability
- slippage risk

Do not filter live until enough evidence exists.

### 27. Pace Map / Race Shape Intelligence

Research only at first.

Track:

- too many front runners
- no pace
- possible pace collapse
- hold-up disadvantage
- lone leader advantage

Start as labels only.

### 28. Anti-Pattern Filter

Identify setups that repeatedly lose despite good scores.

Examples:

- course/race type combinations
- chaotic field sizes
- poor draw/pace combinations
- weak high-score patterns

Only create hard no-bet rules after meaningful sample size and unseen validation.

### 29. Historical Pattern DNA

Use the large Betfair historical dataset to answer:

> What historically wins this kind of race?

Inputs:

- venue
- race type
- odds band
- field size
- runner profile
- market movement
- score band

Walk-forward only. No future leakage.

### 30. Ensemble Validation

Shadow-test only.

Possible ensemble:

- current ROI-table scorer
- tipster-consensus scorer
- market-movement scorer

Require agreement before official picks only if it improves quality.

Do not create a black box.

### 31. Expectancy Gate

Research only until proper expected-value calculation exists.

Potential future gate:

- official picks require expected value above a threshold such as `+0.18` units.

Do not fake expectancy from score alone.

### 32. Bankroll And Risk Layer

Do not change public staking yet.

The public proof remains:

- £1 each-way Patent
- £14 daily stake

Research future tools:

- bankroll simulator
- drawdown tracker
- volatility warnings
- paused/reduced-stake mode after poor runs

Avoid complex staking claims until live proof is mature.

### 33. Public Product And Trust

Improve the public site only after engine reliability is stable.

Tasks:

- "How Signal 75 Works" page must match real rules.
- Explain what a Patent is.
- Explain why Radar is not proof.
- Explain why no-bet days happen.
- Proof page must separate live proof from simulations.
- Radar must say "not counted in proof".
- Tipster Alert should say "not official pick".
- Remove or clearly label demo charts.
- Add "why missed" and "why selected" explanations.
- Keep responsible gambling visible.

### 34. Email Capture And Daily Email

Growth only after stability.

Daily email should include:

- yesterday's results
- today's free pick or no-bet/radar note
- unlock CTA
- honest losing days

Small internal list first.

### 35. Social / X Automation

Growth only after stability.

Post:

- free pick
- yesterday result
- proof chart
- honest record

Manual approval first.

### 36. Premium / Gold Tier

Do not build until:

- stable proof
- stable live operation
- confidence in edge
- enough live data

Potential premium:

- full unlocks
- early email
- drift alerts
- market confidence flags
- historical intelligence summaries

### 37. Edge-Based Staking

Research only.

Caution:

Can increase drawdown.

Do not deploy until:

- live edge proven
- drawdown known
- model stable

Compare flat staking vs tiered staking in paper mode first.

### 38. Performance Learning Loop

Controlled review only.

Rules:

- no daily self-modifying AI
- no automatic live changes
- only adjust after enough data
- small changes only
- always backtest/shadow test before deployment

### 39. Machine Learning Experiments

Long-term research only.

Rules:

- no black-box live model
- must outperform baseline across unseen data
- must remain explainable
- no live use until proven

## Ideas To Be Careful With

These sound useful but can create overfitting or public-trust problems:

- claiming `98-140%` ROI as expected
- changing public picks late in the day without a clear rule
- letting tipsters override every data gate
- using going data from unreliable sources
- using user feedback such as "felt good/bad" for scoring
- complex staking too early
- ML/AI black-box picks before enough clean data exists
- adding a large agent architecture before the simple system is stable

## Week-By-Week Working Order

Week 1:

1. Fix proof page metric labels.
2. Add/review proof rebuild from real archives only.
3. Add daily pipeline health logging.
4. Fix or simplify service worker/cache behaviour.
5. Stabilise live automation and result settlement.

Week 2:

6. Improve tipster capture and named-tipster counting.
7. Add decision audit output for each race.
8. Add "why missed" reasons for radar/rejected horses.

Week 3:

9. Expand post-race intelligence profiles.
10. Add horse profile builder.
11. Add loss reason / interpretation labels.

Week 4:

12. Run stronger tipster-weight shadow variants.
13. Compare current rule vs stronger consensus variants.
14. Keep proof unchanged unless evidence is strong.

Week 5:

15. Run value-band shadow tests.
16. Compare `4.1-6.0`, `4.1-8.0`, and conditional wider bands.
17. Review Flat vs Jumps separately.

Week 6:

18. Walk-forward validation framework.
19. Test field-size and draw-bias variants.
20. Decide whether any scoring change deserves live release.
