import importlib.util

from conftest_helpers import REPO_ROOT


def load_settlement():
    path = REPO_ROOT / "scripts" / "settle-challenger-lab.py"
    spec = importlib.util.spec_from_file_location("settle_challenger_lab", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def load_summary_builder():
    path = REPO_ROOT / "scripts" / "build-challenger-summary.py"
    spec = importlib.util.spec_from_file_location("build_challenger_summary", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_each_way_place_return_uses_fractional_part_of_decimal_odds():
    module = load_settlement()

    win_return, place_return, total = module.calculate_ew_return(5.0, "PLACED", 10)

    assert win_return == 0.0
    assert place_return == 2.0
    assert total == 2.0


def test_one_pick_uses_fourteen_pound_each_way_single():
    module = load_settlement()
    rows = [{"winReturn": 5.0, "placeReturn": 2.0}]

    returned, profit, bet_type = module.calculate_standard_proof_bet(rows)

    assert (returned, profit, bet_type) == (49.0, 35.0, "each_way_single")


def test_two_picks_use_fourteen_pound_each_way_double():
    module = load_settlement()
    rows = [
        {"winReturn": 0.0, "placeReturn": 2.0},
        {"winReturn": 0.0, "placeReturn": 1.75},
    ]

    returned, profit, bet_type = module.calculate_standard_proof_bet(rows)

    assert (returned, profit, bet_type) == (24.5, 10.5, "each_way_double")


def test_three_picks_keep_fourteen_pound_each_way_patent():
    module = load_settlement()
    rows = [
        {"winReturn": 0.0, "placeReturn": 2.0},
        {"winReturn": 0.0, "placeReturn": 1.75},
        {"winReturn": 0.0, "placeReturn": 2.25},
    ]

    returned, profit, bet_type = module.calculate_standard_proof_bet(rows)

    assert returned == 25.81
    assert profit == 11.81
    assert bet_type == "each_way_patent"


def test_retrospective_field_aware_seed_is_not_forward_evidence():
    module = load_summary_builder()

    assert module.is_retrospective_seed(
        {"date": "2026-07-09"}, {"id": "rival_evidence_v1"}
    )
    assert not module.is_retrospective_seed(
        {"date": "2026-07-18"}, {"id": "rival_evidence_v1"}
    )
