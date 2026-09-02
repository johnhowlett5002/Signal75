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

## Official safety promotion - 2 September 2026

John explicitly approved a limited official safety promotion after reviewing the late-August losing streak. This is not a wholesale promotion of `context_guard_v1`, whose wider evidence remains mixed and below the normal 30-settled-day gate.

The official selector now applies only these four controls:

- positive H2H score credit is capped at 2 points
- a return within 3 days receives a 5-point caution
- zero tipster support with at least 3 unknown class/course/distance/going areas caps confidence at 79
- no more than 2 official selections may come from one course

Raw scores and evidence remain stored for analysis. Existing class-rise, form, price and field-size rules remain in force. Historical proof and results are unchanged.

The six-day pre-race replay had 5 replayable settled days: live profit `-£61.84`, guarded paper profit `-£26.94`, delta `+£34.90`. This short adverse-period result supports a safety trial but does not prove future profitability. Continue to monitor Flat and Jumps separately and retain `context_guard_v1` as a paper comparator.
