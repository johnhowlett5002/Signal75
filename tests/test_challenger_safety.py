import pytest

from conftest_helpers import load_json


def test_challenger_summary_has_three_challengers():
    summary = load_json("data/challenger_lab/challenger_summary.json")
    if not summary:
        pytest.skip("No challenger summary yet")

    ids = [c["id"] for c in summary.get("pre_race_challengers", [])]

    assert "consensus_quality_v1" in ids
    assert "field_graph_v1" in ids
    assert "rival_evidence_v1" in ids


def test_promotion_status_values_are_valid():
    valid_statuses = {
        "COLLECTING",
        "TOO_EARLY",
        "WATCHING",
        "PROMISING",
        "RISKY",
        "PROMOTION_CANDIDATE",
        "REJECTED",
        "TESTED_AND_REJECTED",
        "INCONCLUSIVE_AT_30_DAYS",
        "APPROVED_BY_JOHN",
        "PROMOTED_LIVE",
    }
    summary = load_json("data/challenger_lab/challenger_summary.json")
    if not summary:
        pytest.skip("No challenger summary yet")

    for challenger in summary.get("pre_race_challengers", []):
        status = challenger.get("promotion_status", "COLLECTING")
        assert status in valid_statuses, (
            f"Challenger {challenger['id']} has invalid promotion_status: {status}"
        )
