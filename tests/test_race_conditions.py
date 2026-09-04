import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("race_conditions_test", ROOT / "scripts" / "race_conditions.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sporting_life_payload(races):
    import json

    payload = {"props": {"pageProps": {"meetings": [{"races": races}]}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'


def test_extracts_structured_conditions_from_daily_racecard():
    module = load_module()
    raw = sporting_life_payload([{
        "course_name": "Hamilton",
        "date": "2026-09-02",
        "time": "16:50",
        "race_class": "5",
        "going": "Soft",
        "distance": "1m 5f 16y",
        "race_summary_reference": {"id": 936184},
    }])

    assert module.extract_daily_races(raw) == [{
        "date": "2026-09-02",
        "course_key": "hamilton",
        "time_utc": "16:50",
        "race_class": "Class 5",
        "going": "Soft",
        "distance": "1m 5f 16y",
        "race_id": "936184",
    }]


def test_enriches_only_plausible_official_races_without_making_failures_fatal():
    module = load_module()
    races = [
        {
            "venue": "Hamilton 2nd Sep",
            "race_time": "2026-09-02 16:50:00+00:00",
            "field_size": 12,
            "runners": [{"best_back": 3.9}],
        },
        {
            "venue": "Bath 2nd Sep",
            "race_time": "2026-09-02 13:00:00+00:00",
            "field_size": 5,
            "runners": [{"best_back": 4.2}],
        },
    ]

    result = module.enrich_race_conditions(
        races,
        "2026-09-02",
        2.75,
        6.0,
        fetcher=lambda url: sporting_life_payload([{
            "course_name": "Hamilton",
            "date": "2026-09-02",
            "time": "16:50",
            "race_class": "5",
            "going": "Good To Soft",
            "distance": "1m 5f 16y",
            "race_summary_reference": {"id": 936184},
        }]),
    )

    assert result == {"checked": 1, "enriched": 1, "failed": 0}
    assert races[0]["race_class"] == "Class 5"
    assert races[0]["going"] == "Good To Soft"
    assert races[0]["distance"] == "1m 5f 16y"
    assert races[0]["raceConditionsUrl"].endswith("/2026-09-02")
    assert "race_class" not in races[1]


def test_rejects_conditions_returned_for_a_different_date():
    module = load_module()
    races = [{
        "venue": "Hamilton",
        "race_time": "2026-09-02 16:50:00+00:00",
        "field_size": 12,
        "runners": [{"best_back": 3.9}],
    }]
    wrong_day = sporting_life_payload([{
        "course_name": "Hamilton",
        "date": "2026-09-03",
        "time": "16:50",
        "race_class": "5",
        "going": "Soft",
    }])

    result = module.enrich_race_conditions(
        races, "2026-09-02", 2.75, 6.0, fetcher=lambda url: wrong_day
    )

    assert result == {"checked": 1, "enriched": 0, "failed": 1}
    assert "race_class" not in races[0]
