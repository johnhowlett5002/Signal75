from conftest_helpers import load_fixture


def test_full_patent_day_has_three_official_picks():
    picks = load_fixture("picks_full_patent.json")
    official = [p for p in picks["picks"] if p["pickType"] == "official"]
    assert len(official) == 3


def test_full_patent_day_all_odds_in_valid_range():
    picks = load_fixture("picks_full_patent.json")
    for pick in picks["picks"]:
        if pick["pickType"] == "official":
            assert 2.1 <= pick["odds"] <= 12.0, (
                f"{pick['name']} odds {pick['odds']} outside range"
            )


def test_full_patent_day_all_scores_above_gate():
    picks = load_fixture("picks_full_patent.json")
    for pick in picks["picks"]:
        if pick["pickType"] == "official":
            assert pick["score"] >= 75, (
                f"{pick['name']} score {pick['score']} below 75 gate"
            )


def test_no_bet_day_has_zero_official_picks():
    picks = load_fixture("picks_no_bet.json")
    official = [p for p in picks["picks"] if p.get("pickType") == "official"]
    assert len(official) == 0


def test_performance_fixture_maths_correct():
    perf = load_fixture("performance_valid.json")
    staked = perf["totalStaked"]
    returned = perf["totalReturn"]
    profit = perf["totalProfit"]
    assert abs((returned - staked) - profit) < 0.02
    assert perf["bettingDays"] + perf["noBetDays"] == perf["totalDays"]
