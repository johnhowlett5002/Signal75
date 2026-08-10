# Signal 75 Pipeline Consolidation

Signal 75 is now operated through two top-level scripts:

```bash
python3 scripts/run_morning_pipeline.py
python3 scripts/run_nightly_pipeline.py
```

The goal is simple operation without losing any intelligence.

## Morning Pipeline

`scripts/run_morning_pipeline.py`

Order:

1. `scripts/dashboard_automation_status.py reset`
   - Clears stale automation warning state before the new run.

2. `scripts/validate-system-config.py`
   - Checks local configuration before data is touched.

3. `python3 -m pytest tests/ -q`
   - Runs the regression suite before selections are created.
   - Can be skipped manually with `--skip-tests` in an emergency.

4. `scripts/validate_system_integrity.py`
   - Runs the safety and freshness guard.
   - Errors stop the morning run.
   - Warnings are logged but do not block picks.

5. `scripts/generate-picks-betfair.py`
   - The only script allowed to create official Signal 75 picks.
   - Keeps price, score, field-size, race-type and stale-data gates.
   - Also writes V1/Challenger analysis-only outputs where already wired.

6. `scripts/selection-diagnostics.py`
   - Explains why the selections passed or missed.
   - Analysis only.

7. `scripts/pick-quality-audit.py --fail-on-flagged`
   - Blocks publication if the daily selections fail the quality guard.

8. `scripts/build-field-graph-intelligence.py`
   - Updates field graph intelligence for the day.

9. `scripts/generate-challenger-lab.py`
   - Rebuilds analysis-only Challenger Lab selections.

10. `scripts/build-challenger-summary.py`
    - Refreshes the Challenger Lab summary.

11. `scripts/publish_dashboard_data.py`
   - Publishes small JSON files for the dashboard.
   - The browser never reads the large SQLite databases directly.

12. Optional: `scripts/publish-live-files.py`
    - Only runs when `--publish-live` is passed.
    - Commits and pushes public pick files after local checks have passed.

## Nightly Pipeline

`scripts/run_nightly_pipeline.py`

Order:

1. `scripts/update-results-mac.py`
   - Settles the official result file.

2. `scripts/generate-performance.py`
   - Rebuilds verified profit, ROI and proof.

3. `scripts/self-learning-update.py`
   - Runs the self-learning stack:
     race memory, head-to-head, rival evidence, field graph, V1/Challenger
     settlement, rich form validation, score calibration and learning reports.

4. `scripts/validate_system_integrity.py --post-race`
   - Checks proof/accountancy, data freshness and settlement quality.

5. `scripts/publish_dashboard_data.py`
   - Republishes dashboard data after settlement and learning.

## What Stays

This consolidation keeps:

- form intelligence
- H2H / who-beat-who memory
- race class movement
- distance / going / weight / draw / jockey / trainer context
- V1 field-relative analysis
- Challenger Lab
- accountancy and ROI guardrails
- central SQLite learning store

## What Changes

The specialist scripts remain in place, but cron and manual operation should
move to the two wrapper scripts. This reduces the chance of missing a step or
running scripts in the wrong order.

Use `--dry-run` to see the intended order without changing files:

```bash
python3 scripts/run_morning_pipeline.py --dry-run
python3 scripts/run_nightly_pipeline.py --dry-run
```
