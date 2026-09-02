import importlib.util
import json
import sys

import pytest

from conftest_helpers import REPO_ROOT


def load_master_preflight():
    module_path = REPO_ROOT / "scripts" / "master-preflight.py"
    spec = importlib.util.spec_from_file_location("master_preflight", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def valid_performance():
    return {
        "bettingDays": 10,
        "totalStake": 140.0,
        "totalReturn": 175.0,
        "totalProfit": 35.0,
        "roi": 25.0,
    }


def valid_picks():
    return {
        "date": "2026-08-29",
        "mode": "qualified",
        "betType": "each_way_single",
        "totalStake": 14.0,
        "officialSelectionPolicy": {"version": "2026-09-02-context-guard-v1"},
        "flat": [{
            "course": "Test",
            "time": "14:00",
            "runners": 10,
            "horses": [{
                "name": "Example",
                "odds": 5.0,
                "signal_score": 80,
                "formStr": "1231",
                "tipsters": 2,
                "rivalMemoryOverlay": None,
                "contextEvidence": {"class": "proven"},
                "richContext": {"statuses": {
                    "course": "proven", "distance": "proven", "going": "proven",
                    "weight": "known", "draw": "known", "jockey": "known", "trainer": "known",
                }},
                "officialContextGuard": {
                    "policy_version": "2026-09-02-context-guard-v1",
                    "rival_points_allowed": 0,
                    "days_since_last_run": 10,
                    "confidence_cap": None,
                    "penalties": [],
                },
            }],
        }],
        "jumps": [],
        "topRated": [{"name": "Radar only", "odds": 3.0, "score": 99}],
    }


def test_load_json_rejects_conflict_markers(tmp_path):
    module = load_master_preflight()
    path = tmp_path / "broken.json"
    path.write_text('{"roi": <<<<<<< HEAD\n0\n=======\n50\n>>>>>>> branch}', encoding="utf-8")

    payload, issue = module.load_json(path)

    assert payload is None
    assert issue == "contains Git conflict markers"


def test_performance_guard_rejects_zeroed_proof(monkeypatch, tmp_path):
    module = load_master_preflight()
    (tmp_path / "dashboard" / "data").mkdir(parents=True)
    (tmp_path / "performance.json").write_text('{"bettingDays":0,"totalStake":0}', encoding="utf-8")
    (tmp_path / "dashboard" / "data" / "performance.json").write_text('{}', encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "DASHBOARD_DATA", tmp_path / "dashboard" / "data")
    check = module.Preflight("pre-pick", "2026-08-29", None, False)

    check.validate_performance()

    assert any("zeroed proof record" in error for error in check.errors)


def test_picks_guard_ignores_radar_and_validates_official(monkeypatch, tmp_path):
    module = load_master_preflight()
    (tmp_path / "picks.json").write_text(module.json.dumps(valid_picks()), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    check = module.Preflight("post-pick", "2026-08-29", None, False)

    payload = check.validate_picks()

    assert payload is not None
    assert check.errors == []
    assert "1 pick(s)" in check.passed[0]


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("odds", 2.74, "outside the official 2.75-6.0 band"),
        ("odds", 6.1, "outside the official 2.75-6.0 band"),
        ("signal_score", 74, "below the official 75 gate"),
    ],
)
def test_picks_guard_blocks_selection_rule_breaks(monkeypatch, tmp_path, field, value, expected):
    module = load_master_preflight()
    payload = valid_picks()
    payload["flat"][0]["horses"][0][field] = value
    (tmp_path / "picks.json").write_text(module.json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    check = module.Preflight("post-pick", "2026-08-29", None, False)

    check.validate_picks()

    assert any(expected in error for error in check.errors)


def test_picks_guard_rejects_missing_official_policy(monkeypatch, tmp_path):
    module = load_master_preflight()
    payload = valid_picks()
    payload.pop("officialSelectionPolicy")
    (tmp_path / "picks.json").write_text(module.json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    check = module.Preflight("post-pick", "2026-08-29", None, False)

    check.validate_picks()

    assert any("does not carry the live official-selection policy" in error for error in check.errors)


def test_picks_guard_blocks_unproven_multi_level_class_rise(monkeypatch, tmp_path):
    module = load_master_preflight()
    payload = valid_picks()
    payload["flat"][0]["horses"][0]["classContext"] = {
        "evidence_status": "unproven_multi_level_rise",
        "score_cap": 74,
    }
    (tmp_path / "picks.json").write_text(module.json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    check = module.Preflight("post-pick", "2026-08-29", None, False)

    check.validate_picks()

    assert any("unproven multi-level class rise" in error for error in check.errors)


def test_picks_guard_enforces_one_level_class_cap(monkeypatch, tmp_path):
    module = load_master_preflight()
    payload = valid_picks()
    payload["flat"][0]["horses"][0]["signal_score"] = 82
    payload["flat"][0]["horses"][0]["classContext"] = {
        "evidence_status": "unproven_one_level_rise",
        "score_cap": 79,
    }
    (tmp_path / "picks.json").write_text(module.json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    check = module.Preflight("post-pick", "2026-08-29", None, False)

    check.validate_picks()

    assert any("escaped the 79-point confidence cap" in error for error in check.errors)


def test_source_conflict_is_never_auto_repaired(monkeypatch, tmp_path):
    module = load_master_preflight()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "unmerged_paths", lambda: ["scripts/scoring_engine.py"])
    check = module.Preflight("post-pick", "2026-08-29", None, True)

    check.repair_generated_conflicts(valid_picks())

    assert check.repairs == []
    assert check.errors == ["Source-code conflict requires manual review: scripts/scoring_engine.py"]


def test_stash_conflict_does_not_guess_a_generated_side(monkeypatch, tmp_path):
    module = load_master_preflight()
    path = tmp_path / "data" / "challenger_lab" / "sample.json"
    path.parent.mkdir(parents=True)
    path.write_text("<<<<<<< Updated upstream\n{}\n=======\n{}\n>>>>>>> Stashed changes\n", encoding="utf-8")
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "unmerged_paths", lambda: ["data/challenger_lab/sample.json"])
    monkeypatch.setattr(module, "merge_or_rebase_in_progress", lambda: False)
    check = module.Preflight("post-pick", "2026-08-29", None, True)

    check.repair_generated_conflicts(valid_picks())

    assert check.repairs == []
    assert any("Unresolved generated-file conflict" in error for error in check.errors)


def test_post_pick_repairs_stale_challenger_latest(monkeypatch, tmp_path):
    module = load_master_preflight()
    dashboard = tmp_path / "dashboard" / "data"
    folder = dashboard / "challenger_lab"
    folder.mkdir(parents=True)
    (folder / "challenger_latest.json").write_text(
        json.dumps({"date": "2026-08-26", "marker": "stale"}), encoding="utf-8"
    )
    (folder / "challenger_2026-08-29.json").write_text(
        json.dumps({"date": "2026-08-29", "marker": "today"}), encoding="utf-8"
    )
    monkeypatch.setattr(module, "DASHBOARD_DATA", dashboard)
    check = module.Preflight("post-pick", "2026-08-29", None, True)

    check.validate_challenger_latest()

    repaired = json.loads((folder / "challenger_latest.json").read_text(encoding="utf-8"))
    assert repaired["marker"] == "today"
    assert check.errors == []
    assert check.repairs == ["Restored challenger_latest.json from today's dated feed"]
