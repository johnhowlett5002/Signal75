import pytest
import importlib.util
import subprocess

from conftest_helpers import REPO_ROOT, load_fixture


def load_generate_picks_module():
    module_path = REPO_ROOT / "scripts" / "generate-picks-betfair.py"
    spec = importlib.util.spec_from_file_location("generate_picks_betfair", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_pick_quality_audit_module():
    module_path = REPO_ROOT / "scripts" / "pick-quality-audit.py"
    spec = importlib.util.spec_from_file_location("pick_quality_audit", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_official_picks(picks_data):
    return [
        pick for pick in picks_data.get("picks", [])
        if pick.get("pickType") == "official"
    ]


def get_watchlist_picks(picks_data):
    return [
        pick for pick in picks_data.get("picks", [])
        if pick.get("pickType") in ("watchlist", "radar")
    ]


def test_partial_day_official_pick_is_not_suppressed():
    """Regression guard for the 10 July 2026 Gonna Fly display bug."""
    picks = load_fixture("picks_partial_day.json")

    assert picks["mode"] == "topRatedOnly"
    official = get_official_picks(picks)

    assert len(official) == 1, (
        "Partial day with topRatedOnly mode should still have 1 official pick visible"
    )
    assert official[0]["name"] == "Gonna Fly"
    assert official[0]["pickType"] == "official"


def test_partial_day_watchlist_not_promoted_to_official():
    picks = load_fixture("picks_partial_day.json")
    watchlist = get_watchlist_picks(picks)

    for horse in watchlist:
        assert horse.get("pickType") != "official", (
            f"Watchlist horse {horse['name']} incorrectly marked as official"
        )


def test_no_bet_day_shows_zero_official_picks():
    picks = load_fixture("picks_no_bet.json")
    assert len(get_official_picks(picks)) == 0
    assert picks["mode"] == "noBet"


def test_full_patent_shows_three_official_picks():
    picks = load_fixture("picks_full_patent.json")
    assert len(get_official_picks(picks)) == 3
    assert picks["mode"] == "qualified"


def test_single_day_stakes_two_pounds():
    picks = load_fixture("picks_partial_day.json")
    official = get_official_picks(picks)

    assert len(official) == 1
    assert picks.get("betType") == "each_way_single"
    assert picks.get("totalStake", 0) == 2.0


def test_double_day_stakes_six_pounds():
    picks = load_fixture("picks_double_day.json")
    official = get_official_picks(picks)

    assert len(official) == 2
    assert picks.get("betType") == "each_way_double"
    assert picks.get("totalStake", 0) == 6.0


def test_patent_day_stakes_fourteen_pounds():
    picks = load_fixture("picks_full_patent.json")
    official = get_official_picks(picks)

    assert len(official) == 3
    assert picks.get("betType") == "each_way_patent"
    assert picks.get("totalStake", 0) == 14.0


def test_official_picks_have_all_required_fields():
    picks = load_fixture("picks_full_patent.json")
    required = ["name", "pickType", "course", "time", "marketId", "odds", "score"]

    for pick in get_official_picks(picks):
        for field in required:
            assert field in pick, (
                f"Official pick {pick.get('name')} missing required field: {field}"
            )


def test_app_js_contains_partial_day_guard():
    app_js_path = REPO_ROOT / "app.js"
    if not app_js_path.exists():
        pytest.skip("app.js not found")

    content = app_js_path.read_text(encoding="utf-8")

    assert "currentOfficialPickCount" in content
    assert "topRatedOnly" in content
    assert "currentOfficialPickCount() === 0" in content


def test_public_score_parts_zero_tips_when_no_consensus():
    """
    REGRESSION: Myal 11 July 2026 showed TIPS: +17 despite
    zero tipsters. This permanently keeps the public display honest.
    """
    generate_picks = load_generate_picks_module()
    parts = generate_picks._public_score_parts(85, {
        'overlay_points': 0,
        'count': 0,
        'tip_count': 0,
        'source_count': 0,
        'consensus_level': 'none',
        'consensus_count': 0
    })
    assert parts.get('tips', 0) == 0, (
        "Horse with zero tipster evidence should show 0 in tips"
    )
    total = parts.get('price',0) + parts.get('tips',0) + \
            parts.get('race',0) + parts.get('form',0)
    assert total == 85


def test_pick_quality_audit_flags_myal_pattern():
    audit = load_pick_quality_audit_module().build("2026-07-11")
    myal = next(pick for pick in audit["picks"] if pick["name"].upper() == "MYAL")

    assert myal["quality_rating"] == "FLAGGED"
    assert myal["myal_pattern"] is True
    assert myal["scoringImpact"] == "none"
    assert "No tipster support" in myal["plain_english"]
    assert "no rival evidence" in myal["plain_english"]


def test_recent_unplaced_form_penalty_is_analysis_only():
    module = load_pick_quality_audit_module()
    penalty = module.recent_unplaced_form_confidence_penalty(
        "6613-3357",
        tipsters=4,
        rival_points=0,
        score=78,
    )

    assert penalty["code"] == "RECENT_UNPLACED_FORM_CONFIDENCE_PENALTY"
    assert penalty["analysis_only"] is True
    assert penalty["points"] == 7
    assert penalty["adjusted_score"] == 71
    assert penalty["would_clear_live_gate"] is False
    assert penalty["last_two_completed"] == [5, 7]


def test_recent_unplaced_form_penalty_does_not_hit_clean_form():
    module = load_pick_quality_audit_module()
    penalty = module.recent_unplaced_form_confidence_penalty(
        "111-231",
        tipsters=2,
        rival_points=8,
        score=84,
    )

    assert penalty["points"] == 0
    assert penalty["adjusted_score"] == 84
    assert penalty["would_clear_live_gate"] is True


def test_recent_unplaced_form_penalty_blocks_live_official_gate():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Trio Shape",
        "score": 78,
        "bsp": 4.6,
        "field_size": 9,
        "form": "6613-3357",
        "consensus": {
            "consensus_count": 4,
            "overlay_points": 16,
        },
        "rivalMemoryOverlay": None,
    }

    assert generate_picks._official_candidate(runner) is False
    penalty = runner["recent_unplaced_form_penalty"]
    assert penalty["points"] == 7
    assert penalty["adjusted_score"] == 71
    assert penalty["would_clear_live_gate"] is False
    assert runner["form_confidence_block"] is True
    assert "Recent form confidence penalty" in runner["form_confidence_warning"]


def test_recent_unplaced_form_penalty_keeps_clean_form_live():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Clean Form",
        "score": 78,
        "bsp": 4.6,
        "field_size": 9,
        "form": "111-231",
        "consensus": {
            "consensus_count": 4,
            "overlay_points": 16,
        },
        "rivalMemoryOverlay": None,
    }

    assert generate_picks._official_candidate(runner) is True
    penalty = runner["recent_unplaced_form_penalty"]
    assert penalty["points"] == 0
    assert penalty["adjusted_score"] == 78


def test_pick_quality_audit_marks_trio_form_pattern_as_caution():
    audit = load_pick_quality_audit_module().build("2026-07-16")
    trio = next(pick for pick in audit["picks"] if pick["name"].upper() == "TRIO")

    penalty = trio["recent_unplaced_form_penalty"]
    assert trio["quality_rating"] == "MODERATE"
    assert trio["quality_colour"] == "amber"
    assert trio["dimensions"]["recent_form_confidence"] == "WARNING"
    assert penalty["points"] == 7
    assert penalty["adjusted_score"] == 71
    assert penalty["would_clear_live_gate"] is False
    assert trio["scoringImpact"] == "none"
    assert trio["analysis_only"] is True
    assert "analysis-only form check" in trio["plain_english"]


def test_pick_quality_audit_is_non_blocking_for_flagged_public_push():
    result = subprocess.run(
        [
            "python3",
            str(REPO_ROOT / "scripts" / "pick-quality-audit.py"),
            "--date",
            "2026-07-11",
            "--fail-on-flagged",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "NON-BLOCKING WARNING" in result.stdout
    assert "MYAL" in result.stdout
