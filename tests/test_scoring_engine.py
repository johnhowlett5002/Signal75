"""
Regression tests for scripts/scoring_engine.py

WHY THIS FILE EXISTS
---------------------
scoring_engine.py decides which horses become official Signal 75 picks.
It has many small multipliers that combine, plus hard gates (odds band,
score floor, form-risk block, field-size minimum) that decide whether a
qualifying score actually becomes a pick. A small, well-meant tweak to
any one of these can silently change which horses qualify.

These tests exist to make that visible immediately. If you (or Codex,
Grok, ChatGPT, an AI agent, anyone) change a rule, run:

    pytest tests/test_scoring_engine.py -v

Anything that goes red is a *deliberate* decision you're making about
behaviour, not a surprise you find out about after a losing week.

TWO STYLES OF TEST IN HERE
---------------------------
1. EXACT-VALUE tests for the small pure functions (score_form,
   score_field_size, etc). These are simple enough that the exact
   output is part of the spec, so we pin it precisely.

2. CHARACTERIZATION tests for score_runner() itself. Because score_runner
   multiplies eight-plus factors together, hand-computing the exact
   final score for every scenario is brittle (it breaks the moment you
   legitimately change an unrelated multiplier). Instead these tests
   assert relative, structural facts that should always hold regardless
   of exact tuning: "a Chester wide-draw penalty should reduce the score
   versus an identical non-Chester runner", "a runner priced outside the
   official band should never qualify", and so on.
"""
import pytest

from scoring_engine import (
    assign_badge,
    get_course_multiplier,
    get_odds_band,
    get_race_type_multiplier,
    normalise_combined_multiplier,
    parse_race_type,
    recency_weighted_form_penalty,
    recent_form_risk,
    score_days_since_last_run,
    score_field_size,
    score_form,
    score_market_confidence,
    score_runner,
    select_picks,
    volatile_win_form_penalty,
)

from conftest import make_race, make_runner


# ---------------------------------------------------------------------------
# score_form
# ---------------------------------------------------------------------------

class TestScoreForm:
    def test_no_form_returns_neutral(self):
        assert score_form("") == 1.0
        assert score_form(None) == 1.0

    def test_five_recent_wins_hits_the_cap(self):
        # weights sum to 1.0 when every run is a win -> 1.0 + 0.3, clipped to 1.20
        assert score_form("1-1-1-1-1") == 1.20

    def test_all_poor_runs_does_not_drop_below_neutral(self):
        # FINDING: this function only ever ADDS for 1/2/3/4 markers in the
        # last 5 chars — it never subtracts for bad ones. So all-poor form
        # lands at exactly 1.0 (neutral), not the documented 0.90 floor.
        # The floor is currently unreachable dead code given this logic.
        # That may be intentional (recency_weighted_form_penalty handles
        # the "punish bad form" side separately, in points rather than as
        # a multiplier) — but it's worth a deliberate decision rather than
        # an assumption. This test pins CURRENT behaviour either way.
        assert score_form("9-9-9-9-9") == 1.0

    def test_mixed_form_is_between_the_extremes(self):
        result = score_form("1-9-1-9-1")
        assert 0.90 < result < 1.20


# ---------------------------------------------------------------------------
# recent_form_risk — the hard "do not let this be an official pick" flag
# ---------------------------------------------------------------------------

class TestRecentFormRisk:
    def test_pulled_up_with_no_recent_place_is_flagged(self):
        risk = recent_form_risk("9-P-8")
        assert risk is not None
        assert "no recent place" in risk

    def test_pulled_up_but_recent_place_present_is_not_flagged(self):
        # has a bad marker (P) AND a recent placed run (1) -> should NOT
        # trip the "no recent place" rule
        risk = recent_form_risk("9-P-1")
        assert risk is None

    def test_clean_recent_form_is_not_flagged(self):
        assert recent_form_risk("1-2-1") is None

    def test_three_poor_finishes_is_flagged(self):
        risk = recent_form_risk("9-8-9")
        assert risk is not None
        assert "all poor" in risk

    def test_empty_form_is_not_flagged(self):
        assert recent_form_risk("") is None
        assert recent_form_risk(None) is None


# ---------------------------------------------------------------------------
# recency_weighted_form_penalty — the points-based penalty
# ---------------------------------------------------------------------------

class TestRecencyWeightedFormPenalty:
    def test_six_zeros_hits_the_penalty_cap(self):
        penalty, warning = recency_weighted_form_penalty("0-0-0-0-0-0")
        assert penalty == 20  # capped at 20 regardless of how bad the raw total is
        assert "severe" in warning

    def test_six_wins_has_no_penalty(self):
        penalty, warning = recency_weighted_form_penalty("1-1-1-1-1-1")
        assert penalty == 0
        assert warning is None

    def test_empty_form_has_no_penalty(self):
        penalty, warning = recency_weighted_form_penalty("")
        assert penalty == 0
        assert warning is None

    def test_penalty_severity_labels_match_thresholds(self):
        # one pulled-up run in the most recent (2x weighted) slot only:
        # 6.0 * 2.0 = 12 -> should land exactly on the "severe" boundary
        penalty, warning = recency_weighted_form_penalty("1-1-1-1-1-P")
        assert penalty == 12
        assert "severe" in warning


# ---------------------------------------------------------------------------
# volatile_win_form_penalty — "won last time but the form before it was bad"
# ---------------------------------------------------------------------------

class TestVolatileWinFormPenalty:
    def test_win_after_string_of_poor_runs_is_penalised(self):
        mult, warning = volatile_win_form_penalty("9-9-9-9-1")
        assert mult == 0.90
        assert warning is not None

    def test_win_after_clean_form_is_not_penalised(self):
        mult, warning = volatile_win_form_penalty("1-1-1-1-1")
        assert mult == 1.0
        assert warning is None

    def test_non_win_last_time_is_not_penalised(self):
        mult, warning = volatile_win_form_penalty("1-1-1-1-2")
        assert mult == 1.0
        assert warning is None

    def test_short_form_is_not_penalised(self):
        # fewer than 5 characters -> function should not crash, just no-op
        mult, warning = volatile_win_form_penalty("1")
        assert mult == 1.0
        assert warning is None


# ---------------------------------------------------------------------------
# score_days_since_last_run
# ---------------------------------------------------------------------------

class TestScoreDaysSinceLastRun:
    @pytest.mark.parametrize(
        "days,expected",
        [
            ("1", 1.05),
            ("14", 1.05),
            ("15", 1.02),
            ("30", 1.02),
            ("31", 0.98),
            ("60", 0.98),
            ("61", 0.95),
            ("120", 0.95),
            ("121", 0.90),
        ],
    )
    def test_boundaries(self, days, expected):
        assert score_days_since_last_run(days) == expected

    def test_garbage_input_does_not_crash(self):
        assert score_days_since_last_run("unknown") == 1.0
        assert score_days_since_last_run(None) == 1.0


# ---------------------------------------------------------------------------
# score_field_size
# ---------------------------------------------------------------------------

class TestScoreFieldSize:
    @pytest.mark.parametrize(
        "field_size,expected",
        [
            (5, 0.88),
            (6, 0.92),
            (7, 0.92),
            (8, 1.05),
            (10, 1.05),
            (12, 1.05),
            (13, 0.97),
            (16, 0.97),
            (17, 0.88),
            (19, 0.88),
            (20, 0.82),
            (30, 0.82),
        ],
    )
    def test_boundaries(self, field_size, expected):
        assert score_field_size(field_size) == expected


# ---------------------------------------------------------------------------
# score_market_confidence
# ---------------------------------------------------------------------------

class TestScoreMarketConfidence:
    def test_no_volume_data_is_neutral(self):
        assert score_market_confidence(0, 0, 10) == 1.0
        assert score_market_confidence(None, None, 10) == 1.0

    def test_heavily_backed_runner_gets_top_multiplier(self):
        # share=0.4, expected=1/10=0.1, ratio=4.0 -> clearly top band
        assert score_market_confidence(400, 1000, 10) == 1.08

    def test_market_ignoring_runner_gets_penalised(self):
        # share=0.002, expected=0.1, ratio=0.02 -> bottom band
        assert score_market_confidence(2, 1000, 10) == 0.95

    def test_roughly_expected_share_is_neutral(self):
        # share == expected -> ratio == 1.0 -> neutral
        assert score_market_confidence(100, 1000, 10) == 1.0

    def test_exact_3x_boundary_returns_correct_confidence_band(self):
        # The floating-point fix in commit de327f1 ensures that a runner
        # backed at exactly 3x its expected market share now lands in the
        # correct top confidence band (1.08) rather than the band below
        # it (1.05). This test is a regression guard on that fix staying
        # in place.
        assert score_market_confidence(300, 1000, 10) == 1.08


# ---------------------------------------------------------------------------
# normalise_combined_multiplier
# ---------------------------------------------------------------------------

class TestNormaliseCombinedMultiplier:
    def test_no_change_stays_unchanged(self):
        assert normalise_combined_multiplier(1.0) == 1.0

    def test_extreme_high_combined_is_capped(self):
        assert normalise_combined_multiplier(10.0) == 1.6667

    def test_extreme_low_combined_is_floored(self):
        assert normalise_combined_multiplier(0.0) == 0.54  # 1.0 + (0-1)*0.46
        assert normalise_combined_multiplier(-10.0) == 0.50  # hits the explicit floor


# ---------------------------------------------------------------------------
# assign_badge
# ---------------------------------------------------------------------------

class TestAssignBadge:
    def test_banker(self):
        assert assign_badge(90, 5.0) == "Banker"

    def test_strong_from_high_score_band(self):
        assert assign_badge(85, 5.0) == "Strong"

    def test_each_way_badge_needs_qualifying_score_and_bsp(self):
        assert assign_badge(78, 6.5) == "Each Way"

    def test_value_badge_needs_qualifying_score_and_bsp(self):
        assert assign_badge(78, 4.5) == "Value"

    def test_qualifying_score_but_low_bsp_falls_back_to_strong(self):
        assert assign_badge(78, 3.0) == "Strong"

    def test_below_threshold_has_no_badge(self):
        assert assign_badge(60, 5.0) is None

    def test_there_is_no_risky_badge(self):
        # explicit design rule in the docstring: no Risky badge should ever
        # be produced, across the whole plausible score/bsp space
        for score in range(0, 101, 5):
            for bsp in (1.5, 2.0, 4.0, 6.0, 10.0, 20.0, None):
                assert assign_badge(score, bsp) != "Risky"


# ---------------------------------------------------------------------------
# parse_race_type
# ---------------------------------------------------------------------------

class TestParseRaceType:
    @pytest.mark.parametrize(
        "race_name,expected_type,expected_subtype",
        [
            ("3m4f Hcap Chase", "Chase", "Handicap"),
            ("2m Mdn Hrd", "Hurdle", "Maiden"),
            ("Listed Flat Stks", "Flat", "Listed"),
            ("Nov Hrd", "Hurdle", "Novice"),
            ("NHF Bumper", "Bumper", "Other"),
            ("Grp 1 Stks", "Flat", "Group"),
        ],
    )
    def test_parsing(self, race_name, expected_type, expected_subtype):
        race_type, subtype = parse_race_type(race_name)
        assert race_type == expected_type
        assert subtype == expected_subtype


# ---------------------------------------------------------------------------
# Table lookups fall back to neutral when the venue/race-type is unknown
# ---------------------------------------------------------------------------

class TestTableFallbacks:
    def test_unknown_venue_is_neutral(self, neutral_tables):
        mult, personality = get_course_multiplier("Some New Track", neutral_tables)
        assert mult == 1.0
        assert personality == "unknown"

    def test_unknown_race_type_is_neutral(self, neutral_tables):
        mult, key = get_race_type_multiplier("Flat", "Other", neutral_tables)
        assert mult == 1.0

    def test_bsp_in_flat_band_uses_that_multiplier(self, neutral_tables):
        mult, band = get_odds_band(5.0, neutral_tables)
        assert mult == 1.0
        assert band == "flat"


# ---------------------------------------------------------------------------
# score_runner — the hard gates that decide if a horse CAN qualify
#
# These are characterization tests: they pin down behaviour that should
# hold regardless of how individual multipliers get retuned later.
# ---------------------------------------------------------------------------

class TestScoreRunnerGates:
    def test_bsp_below_customer_safe_floor_returns_none(self, neutral_tables):
        runner = make_runner(best_back=2.0)  # below the 2.1 floor
        race = make_race()
        assert score_runner(runner, race, neutral_tables) is None

    def test_bsp_above_customer_safe_ceiling_returns_none(self, neutral_tables):
        runner = make_runner(best_back=12.5)  # above the 12.0 ceiling
        race = make_race()
        assert score_runner(runner, race, neutral_tables) is None

    def test_bsp_at_the_safe_floor_is_scored_not_blocked(self, neutral_tables):
        runner = make_runner(best_back=2.1)
        race = make_race()
        result = score_runner(runner, race, neutral_tables)
        assert result is not None

    def test_neutral_tables_alone_cannot_reach_the_qualifying_bar(self, neutral_tables):
        # FINDING: this is the most important test in this file. With every
        # table multiplier neutral, even a "perfect" runner — max form
        # bonus (1.20), optimal field size (1.05), fresh off a short
        # break (1.05) — only reaches 60 * normalise(1.20*1.05*1.05) = 68.9.
        # That's BELOW the 75 official-pick bar. In other words: no horse
        # can ever become an official pick on form/days/field-size alone.
        # Qualification only happens once the real roi_tables.json
        # venue/race-type/history multipliers add real lift on top. That
        # table wasn't included in this audit, so it's worth confirming
        # this is the intended design (course/race-type carries most of
        # the signal) rather than an accident of how heavily
        # normalise_combined_multiplier damps everything (it multiplies
        # the combined effect by 0.46).
        runner = make_runner(best_back=5.0, form="1-1-1-1-1")
        race = make_race(field_size=10)
        result = score_runner(runner, race, neutral_tables)
        assert result["score"] == 68.9
        assert result["qualifies"] is False

    def test_clean_runner_qualifies_once_a_table_multiplier_adds_real_lift(
        self, favorable_tables
    ):
        runner = make_runner(best_back=5.0, form="1-1-1-1-1")
        race = make_race(field_size=10)  # "3m Hcap Chase" -> Chase / Handicap
        result = score_runner(runner, race, favorable_tables)
        assert result["score"] >= 75
        assert result["qualifies"] is True

    def test_market_leader_at_2_86_can_qualify(self, favorable_tables):
        runner = make_runner(best_back=2.86, form="1-1-1-1-1")
        result = score_runner(runner, make_race(field_size=10), favorable_tables)
        assert result["score"] >= 75
        assert result["qualifies"] is True

    def test_price_below_new_2_75_floor_cannot_qualify(self, favorable_tables):
        runner = make_runner(best_back=2.74, form="1-1-1-1-1")
        result = score_runner(runner, make_race(field_size=10), favorable_tables)
        assert result["score"] >= 75
        assert result["qualifies"] is False

    def test_good_score_outside_official_bsp_band_does_not_qualify(
        self, favorable_tables
    ):
        # 7.0 is outside the strict 2.75-6.0 official band, even though it's
        # inside the wider 2.1-12.0 customer-safe range used for Radar
        runner = make_runner(best_back=7.0, form="1-1-1-1-1")
        race = make_race(field_size=10)
        result = score_runner(runner, race, favorable_tables)
        assert result is not None
        assert result["score"] >= 75  # the raw score still qualifies on points
        assert result["qualifies"] is False  # but the BSP gate blocks it

    def test_form_risk_blocks_qualification_even_at_high_score(self, neutral_tables):
        # pulled up most recently with no recent place -> hard form-risk block
        runner = make_runner(best_back=5.0, form="9-P-8")
        race = make_race(field_size=10)
        result = score_runner(runner, race, neutral_tables)
        assert result is not None
        assert result["form_risk"] is not None
        assert result["qualifies"] is False

    def test_severe_recency_penalty_blocks_qualification(self, neutral_tables):
        runner = make_runner(best_back=5.0, form="0-0-0-0-0-0")
        race = make_race(field_size=10)
        result = score_runner(runner, race, neutral_tables)
        assert result is not None
        assert result["recency_form_penalty"] >= 12
        assert result["qualifies"] is False

    def test_score_below_50_is_radar_only(self, neutral_tables):
        # very poor everything: weak form, long absence, terrible recent runs
        runner = make_runner(
            best_back=5.0,
            form="0-0-0-0-0-0",
            days_since="400",
        )
        race = make_race(field_size=10)
        result = score_runner(runner, race, neutral_tables)
        if result["score"] < 50:
            assert result["qualifies"] is False


class TestScoreRunnerRelativeBehaviour:
    """
    These tests don't pin exact numbers — they pin the *direction* of an
    effect, which is far less brittle when unrelated multipliers change
    later, while still catching the bug class that matters: "this penalty
    stopped doing anything" or "this penalty now helps instead of hurts."
    """

    def test_chester_wide_draw_penalty_reduces_score(self, neutral_tables):
        base_runner = make_runner(best_back=5.0, stall_draw=2)
        wide_draw_runner = make_runner(best_back=5.0, stall_draw=12)
        race = make_race(venue="Chester", field_size=14)

        base_result = score_runner(base_runner, race, neutral_tables)
        wide_result = score_runner(wide_draw_runner, race, neutral_tables)

        assert wide_result["breakdown"]["chester_penalty"] < 1.0
        assert base_result["breakdown"]["chester_penalty"] == 1.0
        assert wide_result["score"] < base_result["score"]

    def test_chester_penalty_does_not_apply_at_other_venues(self, neutral_tables):
        runner = make_runner(best_back=5.0, stall_draw=12)
        race = make_race(venue="Newbury", field_size=14)
        result = score_runner(runner, race, neutral_tables)
        assert result["breakdown"]["chester_penalty"] == 1.0

    def test_worse_recent_form_never_scores_higher_than_better_form(self, neutral_tables):
        race = make_race(field_size=10)
        strong_form = score_runner(
            make_runner(best_back=5.0, form="1-1-1-1-1"), race, neutral_tables
        )
        weak_form = score_runner(
            make_runner(best_back=5.0, form="9-9-9-9-9"), race, neutral_tables
        )
        assert weak_form["score"] < strong_form["score"]

    def test_long_absence_never_scores_higher_than_recent_run(self, neutral_tables):
        race = make_race(field_size=10)
        fresh = score_runner(
            make_runner(best_back=5.0, days_since="10"), race, neutral_tables
        )
        rusty = score_runner(
            make_runner(best_back=5.0, days_since="400"), race, neutral_tables
        )
        assert rusty["score"] < fresh["score"]


# ---------------------------------------------------------------------------
# select_picks — the layer that turns scored runners into Official / Radar
# ---------------------------------------------------------------------------

class TestSelectPicks:
    def _scored(self, **overrides):
        """A pre-scored runner dict, as score_runner() would return it."""
        base = {
            "name": "Test Horse",
            "market_id": "1.1",
            "score": 80,
            "bsp": 5.0,
            "field_size": 10,
            "qualifies": True,
        }
        base.update(overrides)
        return base

    def test_clean_official_qualifier_is_selected(self):
        runners = [self._scored()]
        picks, radar = select_picks(runners)
        assert len(picks) == 1
        assert picks[0]["name"] == "Test Horse"

    def test_field_size_below_eight_blocks_official_even_if_qualifies_true(self):
        # this is the layered-gate case: score_runner said qualifies=True,
        # but select_picks applies its OWN field-size>=8 requirement on top
        runners = [self._scored(field_size=6, qualifies=True, score=85)]
        picks, radar = select_picks(runners)
        assert picks == []

    def test_bsp_outside_official_band_blocks_official(self):
        runners = [self._scored(bsp=7.0)]
        picks, radar = select_picks(runners)
        assert picks == []

    def test_qualifies_false_blocks_official_even_with_high_score(self):
        runners = [self._scored(qualifies=False, score=95)]
        picks, radar = select_picks(runners)
        assert picks == []

    def test_only_one_official_pick_per_market(self):
        runners = [
            self._scored(name="Horse A", market_id="1.1", score=90),
            self._scored(name="Horse B", market_id="1.1", score=85),
        ]
        picks, radar = select_picks(runners, max_picks=3)
        assert len(picks) == 1
        assert picks[0]["name"] == "Horse A"  # higher score, same market

    def test_max_picks_is_respected(self):
        runners = [
            self._scored(name=f"Horse {i}", market_id=f"1.{i}", score=90 - i)
            for i in range(5)
        ]
        picks, radar = select_picks(runners, max_picks=3)
        assert len(picks) == 3

    def test_radar_does_not_duplicate_an_official_pick(self):
        runners = [
            self._scored(name="Official Horse", market_id="1.1", score=90),
            self._scored(
                name="Radar Horse", market_id="1.2", score=68, bsp=8.0, qualifies=False
            ),
        ]
        picks, radar = select_picks(runners)
        official_names = {p["name"] for p in picks}
        radar_names = {r["name"] for r in radar}
        assert official_names.isdisjoint(radar_names)

    def test_radar_requires_minimum_score(self):
        runners = [
            self._scored(
                name="Too Weak", market_id="1.1", score=50, bsp=8.0, qualifies=False
            )
        ]
        picks, radar = select_picks(runners, min_radar_score=65)
        assert radar == []

    def test_radar_bsp_ceiling_is_wider_than_official(self):
        # 12.0 fails the official band but should still be eligible for radar
        # (radar's own ceiling is 12.0 inclusive per the current rule)
        runners = [
            self._scored(
                name="Wide Radar", market_id="1.1", score=70, bsp=12.0, qualifies=False
            )
        ]
        picks, radar = select_picks(runners, min_radar_score=65)
        assert len(radar) == 1
