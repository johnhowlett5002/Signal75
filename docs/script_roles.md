# Signal 75 Script Roles

This file keeps the system clean by giving each active script one clear job.
If a script starts doing the same job as another script, it should be merged,
renamed, or moved to `scripts/legacy_manual/`.

## Active Daily Pipeline

The preferred daily entry points are:

- Morning: `scripts/run_morning_pipeline.py`
- Nightly: `scripts/run_nightly_pipeline.py`

These wrappers do not replace the specialist scripts below. They call the
proven scripts in order, write one log/report per run, and stop if a critical
guard fails.

1. Morning controller
   - `scripts/run_morning_pipeline.py`
   - Runs automation/config/test pre-flight checks, integrity pre-check,
     official pick generation, diagnostics, quality audit, learning feeds and
     dashboard publish.
   - This is the script that should be scheduled for the morning run.

2. Morning picks
   - `scripts/generate-picks-betfair.py`
   - Creates the daily selections and watchlist.
   - This is the only active script that should generate picks.

3. Tipster evidence
   - `scripts/tipster_fetcher.py`
   - `scripts/daily_consensus_overlay.py`
   - Fetches and prepares tipster support.
   - Script-first data is used before any paid AI fallback.

4. Selection diagnostics
   - `scripts/selection-diagnostics.py`
   - Explains why the current selections were made.
   - Analysis only.

5. Nightly controller
   - `scripts/run_nightly_pipeline.py`
   - Settles official results, regenerates proof, runs self-learning, checks
     integrity, then republishes dashboard data.
   - This is the script that should be scheduled for the nightly run.

6. Results and performance
   - `scripts/update-results-mac.py`
   - `scripts/generate-performance.py`
   - `scripts/proof-consistency-check.py`
   - Settles results, updates performance, and checks proof consistency.
   - The local evening wrapper `~/signal75-run-results.sh` should then run:
     `scripts/settle-challenger-lab.py --date "$TODAY"`,
     `scripts/build-challenger-summary.py`, and
     `scripts/publish_dashboard_data.py --date "$TODAY"` before publishing
     live results. This keeps Challenger Lab settlement visible after official
     results finish.

7. Dashboard feed
   - `scripts/publish_dashboard_data.py`
   - Builds local dashboard data.
   - Read-only view of the system.

## Active Learning Pipeline

The nightly controller is:

- `scripts/self-learning-update.py`

It runs the learning scripts in order so we do not need separate overlapping
nightly jobs for each layer.

Learning stages:

1. `scripts/build-race-memory.py`
   Stores the daily race memory.

2. `scripts/build-tipster-memory.py`
   Stores tipster evidence and source counts.

3. `scripts/build-race-result-notes.py`
   Stores richer post-race notes such as beaten distances and comments.

4. `scripts/build-head-to-head-memory.py`
   Stores direct horse-vs-horse evidence.

5. `scripts/build-rival-intelligence.py`
   Stores historic rival evidence.

6. `scripts/build-field-relationship-memory.py`
   Builds horse relationship profiles from the memory layers.

7. `scripts/build-field-graph-intelligence.py`
   Checks today's field against relationship memory.

8. `scripts/build-intelligence-db.py`
   Builds the local SQLite intelligence database.

9. `scripts/post-race-diagnosis.py`
   Reviews what happened after results.

10. `scripts/continuous-training.py`
    Tracks repeated warning patterns.

11. `scripts/build-combined-learning.py`
    Joins the evidence layers into one learning view.

12. `scripts/collateral-form-review.py`
    Reviews horses that beat our high-signal horses.

13. `scripts/score-calibration-check.py`
    Checks whether score bands are behaving sensibly.

14. `scripts/feature-importance-tracker.py`
    Tracks which signals are proving useful.

15. `scripts/winner-intelligence.py`
    Learns from actual race winners.

16. `scripts/drift-detector.py`
    Watches for performance changes.

17. `scripts/shadow-promotion-tracker.py`
    Tracks possible future rule changes without changing live picks.

18. `scripts/master-learning-summary.py`
    Summarises learning outputs.

19. `scripts/generate-public-scorecard.py`
    Builds a public-facing scorecard.

20. `scripts/scenario-roi-review.py`
    Reviews ROI scenarios.

21. `scripts/pipeline-health-check.py`
    Checks whether the daily pipeline ran correctly.

22. `scripts/archive-learning-reports.py`
    Keeps old reports under control.

## Manual Or Special Tools

These are allowed to exist, but should not be treated as daily decision makers:

- `scripts/tipster-intelligence-engine.py`
  Manual pasted-text tipster analysis.

- `scripts/morning-learning-summary.py`
  Plain-English morning note for John.

- `scripts/morning-resolve-mac.py`
  Manual/backup result resolver.

- `scripts/late-market-watch.py`
  Shadow-only late market tracking.

- `scripts/early-results-refresh.py`
  Early result refresh before the main evening settlement.

- `scripts/snapshot-safe-state.py`
  Recovery snapshot tool.

- `scripts/restore-safe-state.py`
  Recovery restore tool.

## Legacy / Not Active

Legacy scripts are stored in:

- `scripts/legacy_manual/`

They are retained for safety and reference, but they should not be scheduled.
