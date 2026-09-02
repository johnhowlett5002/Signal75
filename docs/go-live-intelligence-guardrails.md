# Signal 75 Go-Live Intelligence Guardrails

Review this file before promoting any dashboard or Challenger Lab rule into live selection logic.

## Combined-context rule

No single signal may be promoted in isolation. Review these together:

- recent form and days since last run
- current race class, previous class and evidence at the new level
- direct head-to-head evidence against runners in today's field
- distance, going, weight and draw context
- jockey and trainer evidence
- independent tipster support
- same-course concentration across the proposed bet
- late market movement as analysis-only evidence

Unknown evidence must stay labelled `unknown`; it must not be converted to a proven zero or a positive claim.

## Promotion gate

- Analysis-only for at least 30 settled betting days.
- Positive delta versus the live system must be repeatable, not driven by one day.
- Review Flat and Jumps separately.
- Require manual approval from John before changing live picks.
- Preserve a recovery snapshot and run the full test suite before deployment.
- Never change proof, historical results or `performance.json` to improve a challenger result.

## Current combined test

`context_guard_v1` tests H2H restraint, quick-return caution, missing-context confidence caps and a maximum of two selections at one course. It is paper-only and has no live scoring impact.
