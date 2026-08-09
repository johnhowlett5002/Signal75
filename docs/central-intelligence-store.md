# Signal 75 Central Intelligence Store

`data/horse_intelligence/signal75_history.sqlite` is the live Signal 75
intelligence store.

It is rebuilt by `scripts/build-intelligence-db.py` from the daily learning
JSONL files produced by the nightly self-learning pipeline. It is the source to
use for new selection, Challenger Lab and dashboard intelligence work.

## Live Tables

`race_memory` stores one runner/race memory row with the rich context needed for
future selection research:

- horse, course, date, race time and distance
- finishing position and known result
- pre-race price and Signal 75 score
- official pick / watchlist markers
- tipster count
- jockey and trainer
- recent form and days since last run
- field size
- draw bucket
- carried weight
- official rating and rating versus the field
- race class, previous race class and class movement

`head_to_head` stores field evidence:

- winner / loser
- winner key / loser key
- date, course, race time and race name
- source, confidence and evidence note

## Historical Archive

`data/horse_intelligence/form_history.sqlite` is different. It is an imported
historical archive for pattern research and dashboard context. It is not the
live source of truth unless its freshness status is current.

Any script that wants to use `form_history.sqlite` must treat it as
analysis-only unless the freshness guard marks it current.

## Guardrails

Use `scripts/signal75_intelligence_store.py` for new code. It exposes:

- `LIVE_DB`
- `FORM_ARCHIVE_DB`
- `connect_live()`
- `connect_form_archive(allow_stale=True)`
- `live_store_health()`
- `assert_live_store_ready()`

The freshness report is written to:

`data/horse_intelligence/data_freshness_status.json`

The integrity guard checks the central live store every morning and after
nightly learning. If the live store is stale or missing rich columns, it is an
error. If the historical archive is stale, it is a warning.

