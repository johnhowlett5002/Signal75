"""
Shared pytest fixtures for Signal 75 scoring tests.

This adds /scripts to sys.path so tests can `import scoring_engine`
without needing it installed as a package, and provides a "neutral"
roi_tables fixture so individual gates can be tested in isolation
without real ROI-table multipliers muddying the math.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def neutral_tables():
    """
    A roi_tables.json stand-in where every multiplier is 1.0.

    scoring_engine.py already falls back to 1.0 for any venue/race-type
    that isn't found in the real tables, so an empty dict is enough for
    race_types and courses. odds_bands needs one flat band so get_odds_band
    doesn't fall through to its 'unknown' default for every BSP we test.
    """
    return {
        "odds_bands": {
            "flat": {"lo": 0.0, "hi": 1000.0, "confidence_multiplier": 1.0},
        },
        "race_types": {},
        "courses": {},
        "horse_profiles": {},
    }


@pytest.fixture
def favorable_tables():
    """
    Same as neutral_tables, but with one real positive race-type multiplier.

    Why this exists: with EVERY multiplier neutral, a horse with maxed-out
    form/days-since/field-size still only scores ~68.9 (see
    test_scoring_engine.py for the full explanation) — below the 75
    qualifying bar. That means qualification only happens once the real
    roi_tables.json venue/race-type/history multipliers add real lift.
    This fixture gives one such multiplier so tests can exercise the
    "official qualifier" path without needing the real (excluded from
    this audit) roi_tables.json.
    """
    return {
        "odds_bands": {
            "flat": {"lo": 0.0, "hi": 1000.0, "confidence_multiplier": 1.0},
        },
        "race_types": {
            "Chase / Handicap": {"confidence_multiplier": 1.25},
        },
        "courses": {},
        "horse_profiles": {},
    }


def make_runner(**overrides):
    """Build a minimal valid runner dict, overriding only what a test cares about."""
    runner = {
        "name": "Test Horse",
        "best_back": 5.0,
        "form": "1-1-1-1-1",
        "days_since": "14",
        "stall_draw": 0,
        "total_matched": 0,
        "market_matched": 0,
        "jockey": "J Smith",
        "trainer": "T Jones",
    }
    runner.update(overrides)
    return runner


def make_race(**overrides):
    """Build a minimal valid race dict, overriding only what a test cares about."""
    race = {
        "venue": "Newbury",
        "race_name": "3m Hcap Chase",
        "race_time": "14:30",
        "market_id": "1.999999",
        "field_size": 10,
        "runners": [],
    }
    race.update(overrides)
    return race


@pytest.fixture
def runner_factory():
    return make_runner


@pytest.fixture
def race_factory():
    return make_race
