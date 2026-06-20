"""Regression tests for the intended Signal 75 scoring behaviour."""
from scoring_engine import (
    recency_weighted_form_penalty,
    score_form,
    score_market_confidence,
    score_runner,
)


def test_all_poor_runs_leave_score_form_neutral():
    """Bad form is handled by the separate recency penalty, not score_form."""
    assert score_form("9-9-9-9-9") == 1.0
    penalty, warning = recency_weighted_form_penalty("9-9-9-9-9")
    assert penalty == 20
    assert warning.startswith("severe recent-form penalty")


def test_neutral_tables_alone_cannot_reach_qualifying_bar(
    neutral_tables, runner_factory, race_factory
):
    scored = score_runner(runner_factory(), race_factory(), neutral_tables)

    assert scored["score"] == 68.9
    assert scored["qualifies"] is False


def test_real_table_lift_can_reach_qualifying_bar(
    favorable_tables, runner_factory, race_factory
):
    scored = score_runner(runner_factory(), race_factory(), favorable_tables)

    assert scored["score"] == 78.0
    assert scored["qualifies"] is True


def test_exact_market_confidence_boundaries_are_stable():
    """Round-number volumes must not fall below their intended confidence band."""
    assert score_market_confidence(300, 1000, 10) == 1.08
    assert score_market_confidence(200, 1000, 10) == 1.05
    assert score_market_confidence(150, 1000, 10) == 1.02
    assert score_market_confidence(30, 1000, 10) == 0.95
