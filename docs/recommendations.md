# Signal75 Recommendations

Last updated: 2026-05-24

## Testing Standard

No performance change should go live just because it sounds sensible or improves one backtest.

Required path:

1. Define the change and the problem it is meant to solve.
2. Run a quick test.
3. Compare against the current live benchmark: `value_band_4_6_v1`.
4. Run the larger rolling validation where historical data supports the test.
5. Check yearly stability, flat vs jumps, odds bands, no-bet days, drawdowns, and worst periods.
6. If historical testing is not possible, run the idea in shadow mode.
7. Only go live after the change improves real selection quality.
8. Reset proof from the release date and monitor live behaviour.

## Current Live Benchmark

Current benchmark rule: `value_band_4_6_v1`

Rule:

- Score at least 75.
- BSP/odds between 4.1 and 6.0.
- Field size at least 8.
- One pick per race.
- Maximum 3 official picks per day.

Latest full validation:

- Profit: +GBP 4,959.79
- ROI: 77.1%
- Betting days: 919
- Selections: 2,757
- Win/place: 55.4%

This remains the rule to beat before anything goes live.

## Consensus Gate

Consensus Gate should stay in shadow mode until it proves itself on live days.

Reason:

- Betfair historical data does not contain old public tips.
- A full historical test of true consensus is not honest without a historical tips archive.
- The correct method is live paper testing.

Current shadow variants:

- `baseline_live_rule`: current live value-band rule, no consensus.
- `consensus_rank_v1`: soft consensus ranking boost.
- `consensus_prefer_tipped_v1`: prefer tipped horses first, then fill with value-band picks.
- `consensus_strict_tipped_v1`: only value-band horses with at least one consensus source.

Recommended next addition:

- `consensus_strong_rank_v1`

Proposed stronger consensus nudge:

- 1-2 sources: +1 ranking point.
- 3-5 sources: +3 ranking points.
- 6+ sources: +6 ranking points.

Important guardrail:

- Consensus should not drag in poor outsiders or weak field horses.
- A horse should still need to pass basic value-band eligibility before consensus can promote it.

## Confidence Decay

Do not put broad confidence decay live yet.

The first version was too blunt and risked punishing proven horses with older but still useful profiles.

If revisited, use protected decay only:

- Do not punish horses with strong/proven history.
- Protect horses with 30-50+ historical runs.
- Use decay mainly as a ranking/tie-breaker.
- Be stricter only on thin, stale, low-sample profiles.

Current recommendation:

- Keep out of live picks until it beats `value_band_4_6_v1` on quality and stability.

## Going Intelligence

Going Intelligence remains a promising future layer, but only if reliable going/ground data can be captured.

Do not add it from guesswork.

Test requirement:

- Need a dependable source of going data.
- Need to compare horse performance by going where data exists.
- Run as shadow or historical test depending on data quality.

## Market Confidence

Market Confidence has been activated as a small live scoring signal.

Recommendation:

- Keep it modest.
- Monitor whether market-backed selections perform better.
- Do not allow market movement alone to overpower the core value-band rule.

## Proof And Public Reporting

Keep proof conservative and transparent.

Rules:

- Proof should reset from meaningful release dates.
- Do not rewrite old proof.
- Radar/watchlist horses are not official proof picks.
- Historical validation should be clearly labelled as simulation, not live profit.
- Live proof should be separated from backtest claims.

## Operating Principle

Signal75 should focus on removing structurally weak bets, not chasing every possible winner.

Core phrase:

"Remove structurally weak bets and focus only on repeatable edge."
