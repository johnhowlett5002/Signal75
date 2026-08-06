import glob
import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest_helpers import REPO_ROOT, load_json


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


def test_proof_roi_guard_runs_without_errors():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/proof-roi-guard.py"),
            "--check-only",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode in (0, 1), (
        "Proof ROI guard reported a hard error:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "Current proof:" in result.stdout


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
