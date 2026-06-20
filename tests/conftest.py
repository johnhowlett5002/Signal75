"""Shared pytest fixtures for Signal 75 scoring tests."""
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def neutral_tables():
    """ROI-table stand-in where every multiplier is neutral."""
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
    """Neutral tables with one positive race-type multiplier."""
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
    """Build a minimal valid runner dict for a scoring test."""
    runner = {
        "name": "Test Horse",
        "best_back": 5.0,
        "form": "1-1-1-1-1",
        "days_since": "14",
        "stall_draw": 0,
        "total_matched": 0,
        "market_matched": 0,
        "history": None,
        "jockey": "J Smith",
        "trainer": "T Jones",
    }
    runner.update(overrides)
    return runner


def make_race(**overrides):
    """Build a minimal valid race dict for a scoring test."""
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
