import pytest
import importlib.util
import subprocess

from conftest_helpers import REPO_ROOT, load_fixture, load_json


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


def load_generate_performance_module():
    module_path = REPO_ROOT / "scripts" / "generate-performance.py"
    spec = importlib.util.spec_from_file_location("generate_performance", module_path)
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


def test_single_day_uses_fourteen_pound_proof_stake():
    picks = load_fixture("picks_partial_day.json")
    official = get_official_picks(picks)

    assert len(official) == 1
    assert picks.get("betType") == "each_way_single"
    assert picks.get("totalStake", 0) == 14.0


def test_double_day_uses_fourteen_pound_proof_stake():
    picks = load_fixture("picks_double_day.json")
    official = get_official_picks(picks)

    assert len(official) == 2
    assert picks.get("betType") == "each_way_double"
    assert picks.get("totalStake", 0) == 14.0


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


def test_top_rated_mode_with_official_cards_counts_as_bet_day():
    performance = load_generate_performance_module()
    day = {
        "mode": "topRatedOnly",
        "betType": "each_way_double",
        "noBetDay": False,
        "flat": [
            {"horses": [{"name": "Sale Shark"}]},
            {"horses": [{"name": "Gangsta Man"}]},
        ],
        "jumps": [],
        "results": {
            "flat": [
                {"result": "LOST"},
                {"result": "PENDING"},
            ],
            "jumps": [],
            "_note": "No official Signal 75 bet",
        },
    }

    assert performance.has_official_proof_picks(day) is True


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


def test_messy_recent_form_needs_stronger_proof_for_live_pick():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Sir Benedict Pattern",
        "score": 79.2,
        "bsp": 4.1,
        "field_size": 9,
        "form": "86254346",
        "consensus": {
            "consensus_count": 2,
            "source_count": 1,
            "overlay_points": 8,
        },
        "rivalMemoryOverlay": {
            "points": 2,
            "signals": ["FIELD_RELATIONSHIP_MEMORY"],
        },
    }

    assert generate_picks._official_candidate(runner) is False
    assert runner["form_confidence_block"] is True
    assert "messy recent form needs stronger proof" in runner["form_confidence_warning"]


def test_messy_recent_form_is_warning_with_strong_counter_evidence():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Messy But Proven",
        "score": 83,
        "bsp": 4.8,
        "field_size": 9,
        "form": "86254346",
        "consensus": {
            "consensus_count": 4,
            "source_count": 2,
            "overlay_points": 16,
        },
        "rivalMemoryOverlay": {
            "points": 8,
            "signals": ["FIELD_RELATIONSHIP_MEMORY"],
        },
    }

    assert generate_picks._official_candidate(runner) is True
    assert runner["formGateWarning"] is True
    assert runner["formGateCode"] == "FORM_GATE_MESSY_RECENT_FORM"


def test_form_gate_warns_zero_placed_last_four():
    """Zero placed runs in the recent form window is a warning, not a hard block."""
    generate_picks = load_generate_picks_module()

    for form in ("5768754", "0000", "45674589", "6070854"):
        review = generate_picks._form_gate_review(form)
        assert review["passes"] is True
        assert review["code"] == "FORM_GATE_ZERO_PLACED_LAST_4"


def test_form_gate_blocks_short_trio_style_recent_form():
    """REGRESSION: short 5th/7th-style recent form must not pass as official."""
    generate_picks = load_generate_picks_module()

    assert generate_picks._form_gate_passes("57") is False
    assert generate_picks._form_gate_passes("0157") is False
    assert generate_picks._form_gate_passes("40") is False
    assert generate_picks._form_gate_passes("04") is False


def test_form_gate_warns_recent_win_then_unplaced():
    """A 14-style profile is mixed form, not clean form."""
    generate_picks = load_generate_picks_module()

    review = generate_picks._form_gate_review("14")
    assert review["passes"] is True
    assert review["code"] == "FORM_GATE_RECENT_WIN_THEN_UNPLACED"


def test_recent_win_then_unplaced_needs_stronger_counter_evidence():
    generate_picks = load_generate_picks_module()
    weak = {
        "name": "Weak Counter Evidence",
        "score": 80,
        "bsp": 5.3,
        "field_size": 10,
        "form": "14",
        "consensus": {"consensus_count": 1, "source_count": 1, "overlay_points": 4},
        "rivalMemoryOverlay": None,
    }
    strong = {
        "name": "Dark Issue Pattern",
        "score": 98,
        "bsp": 5.3,
        "field_size": 10,
        "form": "14",
        "consensus": {"consensus_count": 4, "source_count": 4, "overlay_points": 16},
        "rivalMemoryOverlay": None,
    }

    assert generate_picks._official_candidate(weak) is False
    assert weak["form_confidence_block"] is True
    assert "Recent form caution" in weak["form_confidence_warning"]

    assert generate_picks._official_candidate(strong) is True
    assert strong["formGateWarning"] is True
    assert strong["formGateCode"] == "FORM_GATE_RECENT_WIN_THEN_UNPLACED"


def test_form_gate_warns_messy_emperor_caradoc_style_form():
    """A mostly messy run of form must carry a visible confidence warning."""
    generate_picks = load_generate_picks_module()

    for form in ("0-4013562", "4013652"):
        review = generate_picks._form_gate_review(form)
        assert review["passes"] is True
        assert review["code"] == "FORM_GATE_MESSY_RECENT_FORM"


def test_form_gate_passes_good_or_unknown_form():
    generate_picks = load_generate_picks_module()

    for form in ("32/705-121", "331/70-122", "222", "112", "P12", "54321", "", None):
        assert generate_picks._form_gate_passes(form) is True


def test_form_gate_blocks_consecutive_non_completion():
    generate_picks = load_generate_picks_module()

    assert generate_picks._form_gate_passes("PP234") is False
    assert generate_picks._form_gate_passes("PF123") is False


def test_form_gate_warns_live_official_candidate():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Emperor Pattern",
        "score": 96,
        "bsp": 4.2,
        "field_size": 8,
        "form": "0-4013562",
        "consensus": {
            "consensus_count": 6,
            "source_count": 3,
            "overlay_points": 20,
        },
        "rivalMemoryOverlay": {
            "points": 8,
            "signals": ["FIELD_RELATIONSHIP_MEMORY"],
        },
    }

    assert generate_picks._official_candidate(runner) is True
    assert runner["formGateWarning"] is True
    assert runner["formGateCode"] == "FORM_GATE_MESSY_RECENT_FORM"


def test_field_graph_rival_threat_penalty_blocks_only_if_score_falls_below_gate():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Threatened Pick",
        "score": 78,
        "bsp": 4.8,
        "field_size": 10,
        "form": "111-22",
        "consensus": {
            "consensus_count": 6,
            "overlay_points": 20,
        },
        "field_graph_rival_threat": {
            "points": 14,
            "rivals": ["Danger Rival"],
            "negative_edges": [
                {"rival": "Danger Rival", "meetings": 1, "points": 14},
            ],
        },
    }

    assert generate_picks._official_candidate(runner) is False
    assert runner["rival_threat_penalty"]["points"] == 4
    assert runner["rival_threat_penalty"]["adjusted_score"] == 74
    assert runner["rival_threat_block"] is True
    assert "Rival threat penalty -4" in runner["rival_threat_warning"]


def test_field_graph_rival_threat_penalty_keeps_strong_pick_live():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Minor Threat",
        "score": 82,
        "bsp": 4.8,
        "field_size": 10,
        "form": "111-22",
        "consensus": {
            "consensus_count": 4,
            "overlay_points": 16,
        },
        "field_graph_rival_threat": {
            "points": 12,
            "rivals": ["Small Edge Rival"],
            "negative_edges": [
                {"rival": "Small Edge Rival", "meetings": 1, "points": 12},
            ],
        },
    }

    assert generate_picks._official_candidate(runner) is True
    assert runner["rival_threat_penalty"]["points"] == 2
    assert runner["rival_threat_penalty"]["adjusted_score"] == 80
    assert "rival_threat_block" not in runner


def test_legacy_rival_memory_warning_penalises_live_official_gate():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Old Memory Threat",
        "score": 90,
        "bsp": 5.2,
        "field_size": 10,
        "form": "112-23",
        "consensus": {
            "consensus_count": 5,
            "overlay_points": 18,
        },
        "rivalMemoryOverlay": {
            "points": -8,
            "signals": ["DOMINATED_BY_RIVAL_MEMORY"],
            "scoringImpact": "relationship_warning",
            "rivals": ["Old Rival"],
        },
    }

    assert generate_picks._official_candidate(runner) is True
    assert runner["rival_threat_penalty"]["points"] == 6
    assert runner["rival_threat_penalty"]["adjusted_score"] == 84
    assert "Old Rival has beaten this horse before" in runner["rival_threat_warning"]


def test_zero_tipsters_plus_rival_warning_blocks_live_official_gate():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Matoury Shape",
        "score": 92,
        "bsp": 5.2,
        "field_size": 9,
        "form": "8437P-311",
        "consensus": {
            "consensus_count": 0,
            "tip_count": 0,
            "source_count": 0,
            "overlay_points": 0,
            "consensus_level": "none",
        },
        "rivalMemoryOverlay": {
            "points": -5,
            "signals": [
                "DOMINATED_BY_RIVAL_MEMORY",
                "FIELD_RELATIONSHIP_MEMORY",
            ],
            "scoringImpact": "relationship_warning",
            "rivals": ["Zuul"],
        },
    }

    assert generate_picks._official_candidate(runner) is False
    assert runner["zero_validation_rival_warning_block"] is True
    assert "Zero external validation plus a rival warning" in runner["zero_validation_rival_warning"]


def test_field_graph_positive_overlay_rewards_horse_that_has_beaten_today_rivals():
    generate_picks = load_generate_picks_module()
    runner = {
        "name": "Proven Rival Winner",
        "market_id": "m1",
        "score": 72,
        "bsp": 4.8,
        "field_size": 10,
        "form": "112-23",
        "consensus": {
            "consensus_count": 4,
            "overlay_points": 16,
        },
    }
    graph_runner = {
        "horse_name": "Proven Rival Winner",
        "market_id": "m1",
        "relationship_score": 30,
        "direct_edges": [
            {"rival": "Rival One", "rival_key": "RIVALONE"},
            {"rival": "Rival Two", "rival_key": "RIVALTWO"},
            {"rival": "Rival Three", "rival_key": "RIVALTHREE"},
        ],
    }

    assert generate_picks.field_graph_positive_overlay_points(graph_runner) == 6
    runner["field_graph_positive_overlay"] = {
        "points": generate_picks.field_graph_positive_overlay_points(graph_runner),
        "direct_field_wins": 3,
    }
    runner["score"] += runner["field_graph_positive_overlay"]["points"]

    assert runner["score"] == 78
    assert generate_picks._official_candidate(runner) is True


def test_trio_form_pattern_is_blocked_from_live_official_pick():
    comparison = load_json("data/race_comparison_2026-07-16.json")
    runners = [
        runner
        for race in comparison.get("races", [])
        for runner in race.get("runners", [])
        if runner.get("name", "").upper() == "TRIO"
    ]

    assert runners, "Trio should remain visible in race comparison for review"
    trio = runners[0]
    assert trio["status"] != "official"
    assert any(
        "Recent form confidence penalty -7" in warning
        for warning in trio.get("warnings", [])
    )


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
