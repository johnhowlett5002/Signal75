import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name, filename):
    path = REPO_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RESULT_HTML = """
<h2 id="14:15">Test Course 14:15 Result</h2>
<li>Race Status: WeighedIn</li>
<li class="results-table-row" data-oddsdecimal="3.5">
  <span class="number position"><span class='position-highlight'>1st</span></span>
  <span class="dist-title"></span>
  <a class="runner-title">Alpha</a>
</li>
<li class="results-table-row" data-oddsdecimal="5.0">
  <span class="number position">2nd</span>
  <span class="dist-title">1 ½</span>
  <a class="runner-title">Beta</a>
</li>
<li class="results-table-row" data-oddsdecimal="99999">
  <span class="number position">NR</span>
  <span class="dist-title"></span>
  <a class="runner-title">Gamma</a>
</li>
"""


def test_result_page_parser_captures_positions_sp_and_non_runners():
    module = load_script("collect_full_field_results_parser", "collect-full-field-results.py")
    races = module.parse_result_page(RESULT_HTML, "Test Course", "https://example.test/results")

    assert len(races) == 1
    assert races[0]["settled"] is True
    rows = races[0]["runners"]
    assert [row["position"] for row in rows] == [1, 2, None]
    assert rows[1]["sp_decimal"] == 5.0
    assert rows[1]["beaten_by"] == 1.5
    assert rows[1]["distance_from_winner"] == 1.5
    assert rows[2]["status"] == "NON_RUNNER"


def test_collector_requires_every_expected_runner_to_resolve(tmp_path, monkeypatch):
    module = load_script("collect_full_field_results_complete", "collect-full-field-results.py")
    module.DATA = tmp_path
    comparison = {
        "date": "2026-08-30",
        "races": [
            {
                "market_id": "1.2",
                "course": "Test Course",
                "time": "14:15",
                "race_name": "Test Race",
                "runners": [
                    {"number": 1, "name": "Alpha"},
                    {"number": 2, "name": "Beta"},
                    {"number": 3, "name": "Gamma"},
                ],
            }
        ],
    }
    (tmp_path / "race_comparison_2026-08-30.json").write_text(json.dumps(comparison))

    payload = module.collect("2026-08-30", fetcher=lambda _url: RESULT_HTML)

    assert payload["complete"] is True
    assert payload["summary"]["expectedRunners"] == 3
    assert payload["summary"]["positionedRunners"] == 2
    assert payload["summary"]["nonRunners"] == 1


def test_collector_excludes_unsupported_arabian_races_from_completeness(tmp_path):
    module = load_script("collect_full_field_results_unsupported", "collect-full-field-results.py")
    module.DATA = tmp_path
    comparison = {
        "races": [
            {
                "market_id": "1.2",
                "course": "Test Course",
                "time": "14:15",
                "race_name": "Test Race",
                "runners": [
                    {"number": 1, "name": "Alpha"},
                    {"number": 2, "name": "Beta"},
                    {"number": 3, "name": "Gamma"},
                ],
            },
            {
                "market_id": "1.3",
                "course": "Test Course",
                "time": "17:55",
                "race_name": "1m Arab Stks",
                "runners": [{"number": 1, "name": "Unsupported Runner"}],
            },
        ]
    }
    (tmp_path / "race_comparison_2026-08-30.json").write_text(json.dumps(comparison))

    payload = module.collect("2026-08-30", fetcher=lambda _url: RESULT_HTML)

    assert payload["complete"] is True
    assert payload["summary"]["cardRaces"] == 2
    assert payload["summary"]["expectedRaces"] == 1
    assert payload["summary"]["settledRaces"] == 1
    assert payload["summary"]["expectedRunners"] == 3
    assert payload["summary"]["missingRaces"] == []
    assert payload["summary"]["excludedRaces"][0]["raceTime"] == "17:55"


def test_race_memory_loads_only_complete_full_field_feed(tmp_path):
    module = load_script("build_race_memory_full_results", "build-race-memory.py")
    module.INTEL_DIR = tmp_path
    path = tmp_path / "full_field_results_2026-08-30.json"
    path.write_text(
        json.dumps(
            {
                "complete": True,
                "records": [
                    {"market_id": "1.2", "horse_name": "Alpha", "position": 1}
                ],
            }
        )
    )
    assert module.full_field_result_lookup("2026-08-30")[("1.2", "ALPHA")]["position"] == 1

    path.write_text(json.dumps({"complete": False, "records": []}))
    assert module.full_field_result_lookup("2026-08-30") == {}


def test_race_memory_indexes_dashboard_scoring_context(tmp_path):
    module = load_script("build_race_memory_comparison", "build-race-memory.py")
    module.DATA_DIR = tmp_path
    (tmp_path / "race_comparison_2026-08-30.json").write_text(
        json.dumps(
            {
                "races": [
                    {
                        "market_id": "1.2",
                        "runners": [
                            {"name": "Alpha", "score": 81, "scored": True, "status": "watchlist"}
                        ],
                    }
                ]
            }
        )
    )

    row = module.race_comparison_lookup("2026-08-30")[("1.2", "ALPHA")]
    assert row["score"] == 81
    assert row["status"] == "watchlist"


def test_post_race_preflight_checks_both_sqlite_position_counts(tmp_path):
    module = load_script("master_preflight_full_results", "master-preflight.py")
    module.DATA = tmp_path / "data"
    intel = module.DATA / "horse_intelligence"
    intel.mkdir(parents=True)
    payload = {
        "complete": True,
        "summary": {
            "expectedRaces": 1,
            "settledRaces": 1,
            "expectedRunners": 3,
            "matchedRunners": 3,
            "positionedRunners": 2,
            "nonRunners": 1,
        },
    }
    (intel / "full_field_results_2026-08-30.json").write_text(json.dumps(payload))
    with sqlite3.connect(intel / "form_history.sqlite") as conn:
        conn.execute("CREATE TABLE form_results (date TEXT, position INTEGER)")
        conn.executemany("INSERT INTO form_results VALUES (?, ?)", [("2026-08-30", 1), ("2026-08-30", 2)])
    with sqlite3.connect(intel / "signal75_history.sqlite") as conn:
        conn.execute("CREATE TABLE race_memory (date TEXT, finishing_position INTEGER)")
        conn.executemany("INSERT INTO race_memory VALUES (?, ?)", [("2026-08-30", 1), ("2026-08-30", 2)])

    check = module.Preflight("post-race", "2026-08-30", None, False)
    check.validate_full_field_settlement()

    assert check.errors == []
    assert any("2 finishing positions stored" in item for item in check.passed)


def test_field_relative_settlement_uses_full_field_results(tmp_path):
    module = load_script("settle_field_relative_full_results", "settle-field-relative-archive.py")
    module.REPO_ROOT = tmp_path
    module.DATA = tmp_path
    (tmp_path / "horse_intelligence").mkdir()
    (tmp_path / "field_relative_archive_2026-08-30.json").write_text(
        json.dumps({"picks": [{"name": "Alpha", "odds": 5.0}, {"name": "Beta", "odds": 6.0}]})
    )
    (tmp_path / "2026-08-30.json").write_text(json.dumps({"results": {"flat": [], "jumps": []}}))
    (tmp_path / "horse_intelligence" / "full_field_results_2026-08-30.json").write_text(
        json.dumps(
            {
                "complete": True,
                "races": [
                    {
                        "market_id": "1.2",
                        "expected_runner_count": 10,
                        "runners": [{"horse_name": "Alpha"}, {"horse_name": "Beta"}],
                    }
                ],
                "records": [
                    {
                        "market_id": "1.2",
                        "horse_name": "Alpha",
                        "position": 1,
                        "status": "FINISHED",
                        "sp_decimal": 4.0,
                    },
                    {
                        "market_id": "1.2",
                        "horse_name": "Beta",
                        "position": 4,
                        "status": "FINISHED",
                        "sp_decimal": 6.0,
                    },
                ],
            }
        )
    )

    payload = module.settle("2026-08-30")

    assert payload["summary"]["matched_results"] == 2
    assert payload["summary"]["winners"] == 1
    assert payload["picks"][0]["live_result"] == "WON"
    assert payload["picks"][0]["win_return"] == 5.0
    assert payload["picks"][0]["place_return"] == 2.0
    assert payload["picks"][0]["return"] == 7.0
    assert payload["picks"][0]["profit_loss"] == 5.0
    assert payload["picks"][1]["live_result"] == "LOST"
    assert payload["picks"][1]["return"] == 0.0


def test_field_relative_paper_return_handles_placed_and_void():
    module = load_script("settle_field_relative_returns", "settle-field-relative-archive.py")

    assert module.calculate_ew_return(5.0, "PLACED", 10) == (0.0, 2.0, 2.0)
    assert module.calculate_ew_return(5.0, "VOID", 10) == (1.0, 1.0, 2.0)
    assert module.calculate_ew_return(5.0, "LOST", 10) == (0.0, 0.0, 0.0)
