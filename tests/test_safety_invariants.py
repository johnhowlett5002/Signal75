import glob
import importlib.util
import json
import re
import sqlite3
from pathlib import Path

import pytest

from conftest_helpers import REPO_ROOT, load_json


def _normalise_pick_key(row):
    return (
        re.sub(r"[^A-Z0-9]+", "", str(row.get("name", "")).upper()),
        re.sub(r"[^A-Z0-9]+", "", str(row.get("course", "")).upper()),
        str(row.get("time") or ""),
        str(round(float(row.get("odds") or 0), 2)),
        str(round(float(row.get("score") or 0), 1)),
    )


def _official_rows_from_picks(data):
    rows = []
    for section in ("flat", "jumps"):
        for race in data.get(section, []) or []:
            for horse in race.get("horses", []) or []:
                if not isinstance(horse, dict):
                    continue
                rows.append(
                    {
                        "name": horse.get("name"),
                        "course": race.get("course"),
                        "time": race.get("time"),
                        "odds": horse.get("odds"),
                        "score": horse.get("signal_score", horse.get("score")),
                    }
                )
    return rows


def _load_script_module(name, relative_path):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_picks_json_exists_and_is_valid_json():
    path = REPO_ROOT / "picks.json"
    assert path.exists(), "picks.json does not exist"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "picks.json is not a JSON object"


def test_performance_json_exists_and_is_valid_json():
    path = REPO_ROOT / "performance.json"
    assert path.exists(), "performance.json does not exist"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict), "performance.json is not a JSON object"


def test_performance_profit_maths_is_consistent():
    perf = load_json("performance.json")
    if not perf:
        pytest.skip("performance.json empty or missing")

    staked = float(perf.get("totalStaked", 0))
    returned = float(perf.get("totalReturn", 0))
    profit = float(perf.get("totalProfit", 0))

    if staked > 0:
        assert abs((returned - staked) - profit) < 0.02, (
            f"Proof maths broken: £{returned} return - £{staked} stake = "
            f"£{returned - staked:.2f}, but totalProfit shows £{profit}"
        )


def test_performance_total_stake_alias_matches_total_staked():
    perf = load_json("performance.json")
    if not perf:
        pytest.skip("performance.json empty or missing")

    assert "totalStake" in perf, "performance.json must expose totalStake for external proof checks"
    assert "totalStaked" in perf, "performance.json must keep totalStaked for existing dashboard code"
    assert abs(float(perf["totalStake"]) - float(perf["totalStaked"])) < 0.02


def test_dashboard_performance_export_matches_root_proof():
    perf = load_json("performance.json")
    dashboard_perf = load_json("dashboard/data/performance.json")
    if not perf or not dashboard_perf:
        pytest.skip("Performance proof files are missing")

    for key in (
        "bettingDays",
        "profitableDays",
        "totalStake",
        "totalStaked",
        "totalReturn",
        "totalProfit",
        "roi",
        "winRate",
    ):
        assert key in dashboard_perf, f"dashboard/data/performance.json missing {key}"
        assert abs(float(perf.get(key, 0) or 0) - float(dashboard_perf.get(key, 0) or 0)) < 0.21, (
            f"Dashboard performance export drifted from root proof for {key}: "
            f"root={perf.get(key)} dashboard={dashboard_perf.get(key)}"
        )


def test_each_way_patent_matches_bet365_settlement_example():
    update_results = _load_script_module("update_results_mac", "scripts/update-results-mac.py")
    results = []
    for odds, result in ((3.5, "LOST"), (3.0, "WON"), (3.5, "PLACED")):
        win_return, place_return, total_return = update_results.calculate_ew_return(
            odds,
            result,
            runners=8,
            place_frac=0.2,
        )
        results.append(
            {
                "winReturn": win_return,
                "placeReturn": place_return,
                "totalReturn": total_return,
            }
        )

    patent_return, patent_profit = update_results.calculate_patent_from_returns(results)

    assert patent_return == 10.02
    assert patent_profit == -3.98


def test_bookmaker_fractional_odds_parse_to_profit_odds():
    update_results = _load_script_module("update_results_mac", "scripts/update-results-mac.py")

    assert update_results.parse_fractional_odds("3/1") == 3.0
    assert update_results.parse_fractional_odds("7/2") == 3.5


def test_explicit_each_way_places_override_runner_count_rule():
    update_results = _load_script_module("update_results_mac", "scripts/update-results-mac.py")

    assert update_results.determine_result(4, "", 12) == "LOST"
    assert update_results.determine_result(4, "", 12, places_paid=3) == "LOST"
    assert update_results.determine_result(4, "", 12, places_paid=4) == "PLACED"


def test_performance_roi_calculation_is_consistent():
    perf = load_json("performance.json")
    if not perf:
        pytest.skip("performance.json empty or missing")

    staked = float(perf.get("totalStaked", 0))
    if staked <= 0:
        pytest.skip("No stake recorded yet")

    profit = float(perf.get("totalProfit", 0))
    stored_roi = float(perf.get("roi", 0))
    calculated = round((profit / staked) * 100, 1)

    assert abs(stored_roi - calculated) < 0.6, (
        f"ROI mismatch: stored {stored_roi}%, calculated {calculated}%"
    )


def test_daily_results_do_not_undercount_patent_return():
    for path in sorted((REPO_ROOT / "data").glob("2026-*.json")):
        with open(path, encoding="utf-8") as f:
            day = json.load(f)

        results = day.get("results", {})
        if results.get("complete") is not True:
            continue

        total_return = float(results.get("totalReturn") or 0)
        patent_return = float(results.get("patentReturn") or 0)

        assert total_return + 0.02 >= patent_return, (
            f"{path.name}: totalReturn £{total_return:.2f} is lower than "
            f"patentReturn £{patent_return:.2f}. This would understate ROI."
        )


def test_completed_no_selection_days_have_zero_stake_and_zero_profit():
    for path in sorted((REPO_ROOT / "data").glob("2026-*.json")):
        with open(path, encoding="utf-8") as f:
            day = json.load(f)

        results = day.get("results", {})
        if results.get("complete") is not True:
            continue
        settled_rows = [
            row
            for section in ("flat", "jumps")
            for row in (results.get(section, []) or [])
            if isinstance(row, dict)
        ]
        if settled_rows:
            continue

        stake = float(results.get("totalStake") or 0)
        returned = float(results.get("totalReturn") or 0)
        profit = float(results.get("profit", results.get("totalProfit", 0)) or 0)
        assert stake == 0.0, f"{path.name}: completed no-selection day must not carry stake"
        assert returned == 0.0, f"{path.name}: completed no-selection day must not carry return"
        assert profit == 0.0, f"{path.name}: completed no-selection day must not carry profit/loss"


def test_no_two_official_picks_from_same_market():
    picks = load_json("picks.json")
    official = [p for p in picks.get("picks", []) if p.get("pickType") == "official"]

    if not official:
        groups = list(picks.get("flat", [])) + list(picks.get("jumps", []))
        official = [
            {
                "marketId": race.get("market_id") or race.get("marketId"),
                "name": ((race.get("horses") or [{}])[0]).get("name"),
            }
            for race in groups
            if race.get("horses")
        ]

    market_ids = [p.get("marketId") or p.get("market_id", "") for p in official]
    non_empty = [market_id for market_id in market_ids if market_id]

    assert len(non_empty) == len(set(non_empty)), (
        "Two official picks share the same marketId - one race rule violated"
    )


def test_current_official_picks_clear_display_score_gate():
    picks = load_json("picks.json")
    if not picks:
        pytest.skip("picks.json empty or missing")
    if picks.get("betType") == "no_bet":
        pytest.skip("No-bet day")

    official = []
    for section in ("flat", "jumps"):
        for race in picks.get(section, []) or []:
            for horse in race.get("horses", []) or []:
                if isinstance(horse, dict):
                    official.append(horse)

    if not official:
        pytest.skip("No official picks found")

    for horse in official:
        score = float(horse.get("signal_score") or horse.get("score") or 0)
        assert score >= 75, (
            f"{horse.get('name')}: official pick display score {score} is below 75"
        )


def test_radar_watchlist_cards_are_not_marked_official():
    picks = load_json("picks.json")
    if not picks:
        pytest.skip("picks.json empty or missing")

    assert picks.get("officialPickSources") == ["flat", "jumps"]
    assert picks.get("radarPickSources") == [
        "topRated",
        "topRatedFlat",
        "topRatedJumps",
    ]

    for section in ("topRated", "topRatedFlat", "topRatedJumps"):
        for horse in picks.get(section, []) or []:
            if not isinstance(horse, dict):
                continue
            assert horse.get("pickType") == "radar", (
                f"{section} horse {horse.get('name')} must be marked as radar/watchlist"
            )
            assert horse.get("official") is False, (
                f"{section} horse {horse.get('name')} must not be marked official"
            )
            assert horse.get("analysis_only") is True, (
                f"{section} horse {horse.get('name')} must be analysis-only"
            )


def test_dashboard_official_picks_match_picks_json():
    picks = load_json("picks.json")
    if not picks:
        pytest.skip("picks.json empty or missing")

    dashboard_path = REPO_ROOT / "dashboard/data/officialPicks.json"
    ready_path = REPO_ROOT / "dashboard/data/dashboard_ready.json"
    if not dashboard_path.exists():
        pytest.skip("Dashboard official picks export missing")

    dashboard_rows = load_json("dashboard/data/officialPicks.json")
    if not isinstance(dashboard_rows, list):
        pytest.fail("dashboard/data/officialPicks.json is not a list")

    if ready_path.exists():
        ready = load_json("dashboard/data/dashboard_ready.json")
        if isinstance(ready, dict) and ready.get("date"):
            assert ready.get("date") == picks.get("date"), (
                "Dashboard export date does not match picks.json date"
            )

    expected = {_normalise_pick_key(row) for row in _official_rows_from_picks(picks)}
    actual = {
        _normalise_pick_key(row)
        for row in dashboard_rows
        if isinstance(row, dict)
    }

    assert actual == expected, (
        "Dashboard official picks are stale or different from picks.json"
    )


def test_field_graph_ignores_same_day_head_to_head_evidence(monkeypatch, tmp_path):
    graph = _load_script_module(
        "build_field_graph_intelligence",
        "scripts/build-field-graph-intelligence.py",
    )
    master = tmp_path / "head_to_head_master.jsonl"
    master.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": "2026-08-07",
                        "winner": "Fifty Nifty",
                        "winner_key": "FIFTYNIFTY",
                        "loser": "Spring Bloom",
                        "loser_key": "SPRINGBLOOM",
                        "course": "Newmarket",
                    }
                ),
                json.dumps(
                    {
                        "date": "2026-08-06",
                        "winner": "Older Edge",
                        "winner_key": "OLDEREDGE",
                        "loser": "Spring Bloom",
                        "loser_key": "SPRINGBLOOM",
                        "course": "Newmarket",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "HEAD_TO_HEAD_MASTER", master)
    monkeypatch.setattr(graph, "HISTORIC_RIVAL_MASTER", tmp_path / "missing.jsonl")

    edges = graph.build_edges("2026-08-07")

    assert ("FIFTYNIFTY", "SPRINGBLOOM") not in edges
    assert ("OLDEREDGE", "SPRINGBLOOM") in edges


def test_field_relative_h2h_uses_only_evidence_before_reference_date(tmp_path):
    v1 = _load_script_module(
        "select_field_relative_v1",
        "scripts/select-field-relative-v1.py",
    )
    db_path = tmp_path / "h2h.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE head_to_head (date TEXT, winner_key TEXT, loser_key TEXT)"
    )
    conn.execute(
        "INSERT INTO head_to_head VALUES ('2026-08-07', 'FIFTYNIFTY', 'SPRINGBLOOM')"
    )
    conn.execute(
        "INSERT INTO head_to_head VALUES ('2026-08-06', 'OLDEREDGE', 'SPRINGBLOOM')"
    )
    conn.commit()

    beaten, lost_to = v1.h2h_edge(
        conn,
        "SPRINGBLOOM",
        ["FIFTYNIFTY", "OLDEREDGE"],
        v1.date.fromisoformat("2026-08-07"),
    )

    assert beaten == 0
    assert lost_to == 1
    conn.close()


def test_pick_generator_rival_memory_ignores_same_day_master_rows(monkeypatch, tmp_path):
    generate = _load_script_module(
        "generate_picks_betfair_safety",
        "scripts/generate-picks-betfair.py",
    )
    today = generate.get_today()
    older = "2026-01-01"
    master = tmp_path / "head_to_head_master.jsonl"
    master.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "date": today,
                        "winner": "Today Leak",
                        "loser": "Strong Pick",
                        "loser_signal_score": 85,
                    }
                ),
                json.dumps(
                    {
                        "date": older,
                        "winner": "Older Memory",
                        "loser": "Strong Pick",
                        "loser_signal_score": 85,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(generate, "HEAD_TO_HEAD_MASTER", str(master))
    monkeypatch.setattr(generate, "HEAD_TO_HEAD_PROFILES", str(tmp_path / "missing_h2h.json"))
    monkeypatch.setattr(generate, "HISTORIC_RIVAL_PROFILES", str(tmp_path / "missing_rivals.json"))
    monkeypatch.setattr(generate, "FIELD_RELATIONSHIP_PROFILES", str(tmp_path / "missing_field.json"))

    support = generate.load_rival_memory_support([])

    assert "todayleak" not in support
    assert "oldermemory" in support


def test_no_challenger_promoted_without_approval():
    summary = load_json("data/challenger_lab/challenger_summary.json")
    if not summary:
        return

    for challenger in summary.get("pre_race_challengers", []):
        status = challenger.get("promotion_status", "")
        assert status != "PROMOTED_LIVE", (
            f"Challenger {challenger['id']} is PROMOTED_LIVE - was this manually approved?"
        )


def test_challenger_files_have_analysis_only_true():
    files = sorted(
        filepath for filepath in glob.glob(str(REPO_ROOT / "data/challenger_lab/challenger_*.json"))
        if Path(filepath).stem.replace("challenger_", "").count("-") == 2
    )

    for filepath in files[-3:]:
        data = load_json(str(Path(filepath).relative_to(REPO_ROOT)))
        assert data.get("analysis_only") is True, (
            f"{filepath} missing analysis_only: true"
        )
        for challenger in data.get("pre_race_challengers", []):
            assert challenger.get("analysis_only") is True, (
                f"Challenger {challenger.get('id')} in {filepath} missing analysis_only: true"
            )


def test_bookmaker_rule4_patent_accountancy_matches_bet365_slip():
    updater = _load_script_module(
        "update_results_accountancy",
        "scripts/update-results-mac.py",
    )

    bayside_odds = updater.parse_fractional_odds("9/4")
    farandaway_before_rule4 = updater.parse_fractional_odds("10/3")
    farandaway_odds = updater.apply_rule4_to_profit_odds(farandaway_before_rule4, 0.15)
    sail_odds = updater.parse_fractional_odds("5/2")

    rows = [
        {
            "name": "BAYSIDE VIEW",
            "result": "PLACED",
            "winReturn": 0.0,
            "placeReturn": updater.calculate_ew_return(bayside_odds, "PLACED", 8, 0.2)[1],
            "totalReturn": updater.calculate_ew_return(bayside_odds, "PLACED", 8, 0.2)[2],
            "winReturnExact": updater.calculate_ew_return_exact(bayside_odds, "PLACED", 8, 0.2)[0],
            "placeReturnExact": updater.calculate_ew_return_exact(bayside_odds, "PLACED", 8, 0.2)[1],
        },
        {
            "name": "FARANDAWAY",
            "result": "PLACED",
            "winReturn": 0.0,
            "placeReturn": updater.calculate_ew_return(farandaway_odds, "PLACED", 8, 0.2)[1],
            "totalReturn": updater.calculate_ew_return(farandaway_odds, "PLACED", 8, 0.2)[2],
            "winReturnExact": updater.calculate_ew_return_exact(farandaway_odds, "PLACED", 8, 0.2)[0],
            "placeReturnExact": updater.calculate_ew_return_exact(farandaway_odds, "PLACED", 8, 0.2)[1],
        },
        {
            "name": "SAIL ON SAILOR",
            "result": "LOST",
            "winReturn": 0.0,
            "placeReturn": 0.0,
            "totalReturn": updater.calculate_ew_return(sail_odds, "LOST", 8, 0.2)[2],
            "winReturnExact": updater.calculate_ew_return_exact(sail_odds, "LOST", 8, 0.2)[0],
            "placeReturnExact": updater.calculate_ew_return_exact(sail_odds, "LOST", 8, 0.2)[1],
        },
    ]

    summary = updater.sectioned_bet_summary(rows, [])

    assert updater.parse_rule4_deduction("15") == pytest.approx(0.15)
    assert summary["totalStake"] == 14.0
    assert summary["totalReturn"] == pytest.approx(5.29, abs=0.01)
    assert summary["totalProfit"] == pytest.approx(-8.71, abs=0.01)


def test_august_10_verified_bet365_patent_overrides_calculated_estimate():
    updater = _load_script_module(
        "update_results_august_10_accountancy",
        "scripts/update-results-mac.py",
    )

    rows = []
    for odds, result, runners, place_fraction in (
        (updater.parse_fractional_odds("6/1"), "PLACED", 8, 0.2),
        (updater.parse_fractional_odds("3/1"), "WON", 8, 0.2),
        (updater.parse_fractional_odds("7/2"), "WON", 8, 0.2),
    ):
        win_exact, place_exact, total_exact = updater.calculate_ew_return_exact(
            odds,
            result,
            runners,
            place_fraction,
        )
        rows.append(
            {
                "winReturnExact": win_exact,
                "placeReturnExact": place_exact,
                "totalReturnExact": total_exact,
            }
        )

    calculated = updater.sectioned_bet_summary(rows, [])
    verified = updater.apply_verified_slip_return(calculated, 47.97)

    assert calculated["totalReturn"] == pytest.approx(47.96, abs=0.01)
    assert verified["totalReturn"] == 47.97
    assert verified["totalProfit"] == 33.97
    assert verified["calculatedReturnBeforeVerifiedSlip"] == pytest.approx(47.96, abs=0.01)
