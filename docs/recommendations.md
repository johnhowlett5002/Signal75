# Signal 75 Recommendations And Roadmap Memory

Last updated: 2026-05-26

This file is the working memory for Signal 75 improvements. It merges the strongest ideas from Codex, Claude, GPT, Grok, Gemini-style reviews, and John's own decisions. The order below is the order we should work through unless live proof exposes a more urgent fault.

## Core Purpose

Signal 75 is a fully automated UK horse-racing selection, validation, and learning system.

The goal is not to pick every winner.

The goal is to identify repeatable structural edges using Betfair historical and live data, filter out weak bets, and maintain a transparent public record.

Operating principle:

> Remove structurally weak bets and focus only on repeatable edge.

Public principle:

> Every Race. Every Runner. Every Result.

## Current Live System

Live site:

- `https://signal75.co.uk`

GitHub repo:

- `johnhowlett5002/Signal75`

Local repo:

- `/Users/johnhowlett/Signal75`

Engine/data folder:

- `/Users/johnhowlett/Desktop/Signal75-Engine`

Hosting:

- GitHub Pages serves the current public site.

Automation:

- Morning resolve: `09:00`
- Morning picks: `10:00`
- Late-market shadow checks: `11:30`, `13:30`, `15:30`
- Evening results/proof: `19:00`, `20:30`, `21:30`, `22:15`

The multiple evening runs are deliberate. Some races finish after 7pm, so later runs fill pending results without overwriting already settled ones.

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
- No-bet days are valid and should be treated as a feature, not a bug.

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
- 50p each-way = £7 total stake

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

### 1. Engine Integrity And Reliability

This is the highest priority.

1. Keep the live site stable.
2. Ensure morning picks generate for the correct date.
3. Ensure Flat and Jumps tabs never borrow from each other.
4. Ensure no-bet days still show useful radar.
5. Ensure evening result runs settle late races across `19:00`, `20:30`, `21:30`, and `22:15`.
6. Ensure morning resolve fills any remaining unsettled positions.
7. Ensure GitHub push/token automation keeps working.
8. Keep service worker cache versions bumped whenever public JS/HTML changes.

Reason:

No scoring upgrade matters if the live system looks broken.

### 2. Tipster Consensus Quality

Strengthen tipster capture before changing scoring too much.

Tasks:

1. Count named tipsters separately, not just websites.
2. Expand source coverage for Racing Post, Sporting Life, Timeform, At The Races, Newsboy, Robin Goodfellow, Newmarket, Farringdon, myracing, GG, and newspaper naps.
3. Store tipster names and sources in daily overlay files.
4. Track tipster-only alert horses.
5. Build source/tipster performance profiles over time.
6. Avoid fabricated consensus. Unknown must remain unknown.

Reason:

John believes people in the know matter. The system should test that seriously, but without letting weak public favourites damage proof.

### 3. Shadow Test Stronger Tipster Weighting

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

### 4. Decision Audit Layer

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

### 5. Post-Race Intelligence Database

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

### 6. Clean Backtest And Walk-Forward Validation

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

Reason:

Avoid overfitting and avoid fake confidence.

### 7. Value Band Testing

Current official live band:

- `4.1-6.0`

Suggested test bands:

- `4.1-6.0` current benchmark
- `4.1-8.0` broader candidate
- `3.5-6.0` to include well-backed tipster horses like Happy Chandler-type cases
- `4.1-8.0` only when tipster count is `2+`
- `4.1-8.0` only when score is `82+`

Do not widen live proof until shadow tests support it.

Reason:

The wider band may catch more winners, but may also increase weak each-way exposure.

### 8. Field Size And Each-Way Safety

Current official rule:

- field size `8+`

Recommended tests:

- official field size `8-14`
- penalise `15+`
- radar only for `5-7`
- stronger caution for small-field jumps

Reason:

Each-way value weakens in small fields, while very large fields introduce chaos.

### 9. Late Market Movement Layer

Keep as shadow first.

Track:

- horses moving into value band after morning publication
- horses drifting badly after selection
- tipped horses with strong late support
- same-race alternatives that overtake the official/radar horse

Do not automatically swap public picks late in the day yet.

Reason:

Late movement may improve quality, but public trust is damaged if picks appear to change without a clear product rule.

### 10. Confidence Decay

Do not put broad confidence decay live yet.

The first version was too blunt and risked punishing proven horses.

If revisited:

- protect horses with strong history
- protect horses with 30-50+ historical runs
- apply stricter decay only to thin, stale, low-sample profiles
- use decay as a ranking/tie-breaker before using as a hard gate

### 11. Horse Quality vs Race Environment Split

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

### 12. Trainer/Jockey Layer

Add only after reliable data is available.

Test:

- trainer 14-day form
- jockey 14-day form
- trainer/jockey combination
- course-specific trainer/jockey performance

Use as small scoring nudges first.

### 13. Going And Ground Intelligence

Promising but not ready unless reliable going data is captured.

Rules:

- never guess going
- store unknown as null
- only score going if source is reliable
- test historically where data exists

### 14. Draw Bias

Useful for biased Flat tracks.

Candidate courses:

- Chester
- other tight/known draw-biased tracks after evidence

Current Chester penalty exists.

Next step:

- formalise draw-bias table and test it.

### 15. Ensemble Validation

Shadow-test only.

Possible ensemble:

- current ROI-table scorer
- tipster-consensus scorer
- market-movement scorer

Require agreement before official picks only if it improves quality.

Do not create a black box.

### 16. Expectancy Gate

Research only until proper expected-value calculation exists.

Potential future gate:

- official picks require expected value above a threshold such as `+0.18` units.

Do not fake expectancy from score alone.

### 17. Bankroll And Risk Layer

Do not change public staking yet.

The public proof remains:

- 50p each-way Patent
- £7 daily stake

Research future tools:

- bankroll simulator
- drawdown tracker
- volatility warnings
- paused/reduced-stake mode after poor runs

Avoid complex staking claims until live proof is mature.

### 18. Public Product And Trust

Improve the public site only after engine reliability is stable.

Tasks:

- "How Signal 75 Works" page must match real rules.
- Proof page must separate live proof from simulations.
- Radar must say "not counted in proof".
- Tipster Alert should say "not official pick".
- Remove or clearly label demo charts.
- Add "why missed" and "why selected" explanations.

### 19. Growth

Only after live stability improves.

Options:

- Pick 1 always free
- Pick 2 unlock by share
- Pick 3 unlock by second share or coffee
- email capture on unlock
- Brevo daily email
- X/Twitter result posts
- Betfair affiliate links

Do not invite friends or wider users until live data and reliability are stronger.

## Ideas To Be Careful With

These sound useful but can create overfitting or public-trust problems:

- claiming `98-140%` ROI as expected
- changing public picks late in the day without a clear rule
- letting tipsters override all data gates
- using going data from unreliable sources
- using user feedback such as "felt good/bad" for scoring
- complex staking too early
- ML/AI black-box picks before enough clean data exists

## Week-By-Week Working Order

Week 1:

1. Stabilise live automation and result settlement.
2. Make sure no-bet/radar days look professional.
3. Confirm GitHub/token/push reliability.

Week 2:

4. Improve tipster capture and named-tipster counting.
5. Add decision audit output for each race.
6. Add "why missed" reasons for radar/rejected horses.

Week 3:

7. Run stronger tipster-weight shadow variants.
8. Compare current rule vs stronger consensus variants.
9. Keep proof unchanged unless evidence is strong.

Week 4:

10. Run value-band shadow tests.
11. Compare `4.1-6.0`, `4.1-8.0`, and conditional wider bands.
12. Review Flat vs Jumps separately.

Week 5:

13. Expand post-race intelligence profiles.
14. Add source/tipster performance profiles.
15. Start measuring radar horses against official picks.

Week 6:

16. Walk-forward validation framework.
17. Test field-size and draw-bias variants.
18. Decide whether any scoring change deserves live release.

