# Signal 75 Price Band Change - 1 September 2026

## Decision

The official morning exchange price band changed from 4.1-6.0 to 2.75-6.0.
The score gate, field-size gates, form checks, class checks, H2H handling and
maximum of three official selections did not change.

Prices below 2.75 still receive the short-price penalty and cannot qualify as
official selections. Historical results are not recalculated under the new
rule.

## Reason

The old automatic -10 adjustment excluded market leaders such as Divot at
2.86 even when their unadjusted score, tipster evidence and recent form were
competitive with the official horse in the same race. The new floor permits
those horses to compete on the remaining live evidence instead of rejecting
them solely for being below 4.1.

## First Controlled Run

The first production regeneration used the stored consensus overlay with paid
AI calls disabled. The official selections were Garden Oasis, His Finest Hour
at 2.78, and Bownder. Divot at 2.88 cleared the new price rule but remained on
the watchlist because Bownder had the higher final adjusted score in the same
race.

## Verification

- Local full suite: 268 passed, 11 skipped.
- Master post-pick preflight: passed with no warnings or errors.
- System integrity: passed with no warnings or errors.
- OVH focused suite: 98 passed.
- OVH remains read-only and is not the production writer.

## Rollback

The exact pre-change source and live state is stored in:

`backups/20260901-price-band-2_75-prechange/source-and-live-state.tgz`

The Git revision recorded alongside that archive is:

`3c0d77c0d81564e94048f0552225c65c3323af76`
