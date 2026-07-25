import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "select-field-relative-daily.py"


def load_selector():
    spec = importlib.util.spec_from_file_location("select_field_relative_daily", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_form_pattern_lookup_uses_rich_form_stats():
    selector = load_selector()

    strong = selector.form_place_rate_from_db("111")
    avoid = selector.form_place_rate_from_db("000")

    assert strong["place_rate"] >= 0.45
    assert selector.form_strength_from_place_rate(strong["place_rate"]) == "STRONG"
    assert selector.form_score_bonus(strong["place_rate"]) > 0

    assert avoid["place_rate"] < 0.20
    assert selector.form_strength_from_place_rate(avoid["place_rate"]) == "AVOID"
    assert selector.form_score_bonus(avoid["place_rate"]) < 0


def test_v1_daily_rejects_avoid_form_patterns():
    selector = load_selector()

    row = {
        "name": "All Unplaced",
        "odds": 5.0,
        "field_score": 100,
        "form": "000",
        "tipsters": 8,
        "h2h_beaten": 4,
    }

    assert not selector.qualifies(row)


def test_v1_daily_weak_form_needs_extra_support():
    selector = load_selector()

    row = {
        "name": "Weak Pattern",
        "odds": 5.0,
        "field_score": 90,
        "form": "809",
        "tipsters": 2,
        "h2h_beaten": 1,
    }
    selector.form_place_rate_from_db = lambda form: {
        "pattern": "809",
        "pattern_length": 3,
        "starts": 100,
        "place_rate": 0.24,
        "source": "test",
    }

    assert not selector.qualifies(row)

    row["tipsters"] = 3
    assert selector.qualifies(row)

    row["tipsters"] = 0
    row["h2h_beaten"] = 2
    assert selector.qualifies(row)
