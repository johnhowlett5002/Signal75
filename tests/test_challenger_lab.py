"""Safety and regression tests for the Challenger Lab shadow pipeline."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def digest(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def configure_module(module, root: Path) -> None:
    module.REPO_ROOT = root
    module.DATA_DIR = root / "data"
    module.CHALLENGER_DIR = root / "data" / "challenger_lab"
    module.DASHBOARD_CHALLENGER_DIR = root / "dashboard" / "data" / "challenger_lab"


def minimal_race_comparison():
    return {
        "date": "2026-07-07",
        "races": [
            {
                "market_id": "1.1",
                "course": "Testcourse",
                "time": "14:30",
                "race_name": "Test Hcap",
                "race_type": "Flat",
                "field_size": 10,
                "runners": [
                    {
                        "name": "Quality Horse",
                        "score": 82,
                        "status": "watchlist",
                        "odds": 5.0,
                        "tipsters": 4,
                        "warnings": [],
                    },
                    {
                        "name": "Weak Price",
                        "score": 90,
                        "status": "watchlist",
                        "odds": 2.0,
                        "warnings": [],
                    },
                ],
            }
        ],
    }


def minimal_script_overlay():
    return {
        "status": "ok",
        "matched_to_betfair": [
            {
                "horse": "Quality Horse",
                "betfair_name": "Quality Horse",
                "course": "Testcourse",
                "time": "14:30",
                "source_count": 2,
                "tip_count": 2,
                "source_tiers": {"1": 1, "2": 1},
                "tier1_count": 1,
                "tier2_count": 1,
                "tier3_count": 0,
                "tier4_count": 0,
                "sources": ["RacingPost", "DailyMirror"],
            }
        ],
    }


def minimal_picks():
    return {
        "date": "2026-07-07",
        "flat": [
            {
                "market_id": "1.1",
                "course": "Testcourse",
                "time": "14:30",
                "horses": [{"name": "Live Horse", "odds": 5.0, "signal_score": 80}],
            }
        ],
        "jumps": [],
        "results": {"complete": False, "patentReturn": 0, "patentProfit": 0},
    }


def seed_generation_files(root: Path) -> None:
    write_json(root / "picks.json", minimal_picks())
    write_json(root / "performance.json", {"proof": "protected"})
    write_json(root / "data" / "race_comparison_2026-07-07.json", minimal_race_comparison())
    write_json(root / "data" / "script_tipster_overlay_2026-07-07.json", minimal_script_overlay())


def test_challenger_does_not_write_to_picks_json(tmp_path):
    generate = load_script("generate_challenger_lab", "generate-challenger-lab.py")
    configure_module(generate, tmp_path)
    seed_generation_files(tmp_path)
    before_mtime = (tmp_path / "picks.json").stat().st_mtime_ns
    before_md5 = digest(tmp_path / "picks.json")

    payload = generate.build_daily_payload("2026-07-07")
    generate.write_daily_outputs("2026-07-07", payload)

    assert (tmp_path / "picks.json").stat().st_mtime_ns == before_mtime
    assert digest(tmp_path / "picks.json") == before_md5


def test_challenger_does_not_write_to_performance_json(tmp_path):
    generate = load_script("generate_challenger_lab_perf", "generate-challenger-lab.py")
    settle = load_script("settle_challenger_lab_perf", "settle-challenger-lab.py")
    configure_module(generate, tmp_path)
    configure_module(settle, tmp_path)
    seed_generation_files(tmp_path)
    payload = generate.build_daily_payload("2026-07-07")
    generate.write_daily_outputs("2026-07-07", payload)
    write_json(
        tmp_path / "data" / "2026-07-07.json",
        {
            **minimal_picks(),
            "results": {"complete": True, "patentReturn": 0, "patentProfit": -14},
        },
    )
    before_mtime = (tmp_path / "performance.json").stat().st_mtime_ns
    before_md5 = digest(tmp_path / "performance.json")

    settled = settle.settle_payload("2026-07-07")
    settle.write_outputs("2026-07-07", settled)

    assert (tmp_path / "performance.json").stat().st_mtime_ns == before_mtime
    assert digest(tmp_path / "performance.json") == before_md5


def test_challenger_settlement_does_not_affect_proof(tmp_path):
    generate = load_script("generate_challenger_lab_proof", "generate-challenger-lab.py")
    settle = load_script("settle_challenger_lab_proof", "settle-challenger-lab.py")
    configure_module(generate, tmp_path)
    configure_module(settle, tmp_path)
    seed_generation_files(tmp_path)
    proof_file = tmp_path / "data" / "proof_checks" / "check_2026-07-07.json"
    write_json(proof_file, {"protected": True})
    before_mtime = proof_file.stat().st_mtime_ns
    before_md5 = digest(proof_file)
    payload = generate.build_daily_payload("2026-07-07")
    generate.write_daily_outputs("2026-07-07", payload)
    write_json(tmp_path / "data" / "2026-07-07.json", minimal_picks())

    settled = settle.settle_payload("2026-07-07")
    settle.write_outputs("2026-07-07", settled)

    assert proof_file.stat().st_mtime_ns == before_mtime
    assert digest(proof_file) == before_md5


def test_pre_race_section_contains_no_post_race_fields(tmp_path):
    generate = load_script("generate_challenger_lab_pre_race", "generate-challenger-lab.py")
    configure_module(generate, tmp_path)
    seed_generation_files(tmp_path)
    payload = generate.build_daily_payload("2026-07-07")
    banned = {
        "position",
        "result",
        "bsp",
        "return",
        "profit",
        "finishing_position",
        "beaten_distance",
        "race_comment",
        "settlement_odds",
        "winner",
    }
    for challenger in payload["pre_race_challengers"]:
        for pick in challenger["picks"]:
            assert banned.isdisjoint(set((pick.get("pre_race_evidence") or {}).keys()))


def test_missing_input_file_marks_data_incomplete(tmp_path):
    generate = load_script("generate_challenger_lab_missing_graph", "generate-challenger-lab.py")
    configure_module(generate, tmp_path)
    seed_generation_files(tmp_path)

    payload = generate.build_daily_payload("2026-07-07")
    field_graph = next(c for c in payload["pre_race_challengers"] if c["id"] == "field_graph_v1")

    assert field_graph["data_complete"] is False
    assert field_graph["picks"] == []
    assert field_graph["status"] == "data_incomplete"


def test_promotion_status_never_auto_sets_approved_or_promoted(tmp_path):
    generate = load_script("generate_challenger_lab_promotion", "generate-challenger-lab.py")
    configure_module(generate, tmp_path)
    seed_generation_files(tmp_path)

    payload = generate.build_daily_payload("2026-07-07")
    statuses = {c["promotion_status"] for c in payload["pre_race_challengers"]}

    assert "APPROVED_BY_JOHN" not in statuses
    assert "PROMOTED_LIVE" not in statuses


def test_summary_does_not_include_challenger_in_official_roi(tmp_path):
    summary_module = load_script("build_challenger_summary", "build-challenger-summary.py")
    configure_module(summary_module, tmp_path)
    write_json(
        tmp_path / "data" / "challenger_lab" / "challenger_2026-07-07.json",
        {
            "date": "2026-07-07",
            "live_system": {"settled": True, "profit": 10},
            "pre_race_challengers": [
                {
                    "id": "consensus_quality_v1",
                    "name": "Consensus Quality Challenger",
                    "version": "1.0",
                    "picks": [{"horse": "A"}, {"horse": "B"}, {"horse": "C"}],
                    "comparison": {
                        "settled": True,
                        "challenger_profit": 20,
                        "challenger_return": 34,
                        "live_profit": 10,
                        "overlap_with_live": 1,
                    },
                }
            ],
        },
    )

    payload = summary_module.build_summary()

    assert payload["live"]["total_profit"] == 10
    assert payload["pre_race_challengers"][0]["total_profit"] == 20
    assert payload["live"]["total_profit"] != 30


def test_summary_includes_unsettled_wider_price_band_with_seed_cases(tmp_path):
    summary_module = load_script("build_challenger_summary_wider", "build-challenger-summary.py")
    configure_module(summary_module, tmp_path)
    seed_cases = [
        {"date": "2026-07-11", "horse": "Venetian Sun", "odds": 6.8, "score": 94, "result": "PLACED"},
        {"date": "2026-07-12", "horse": "Basilette", "odds": 6.6, "score": 100, "result": "WON"},
    ]
    write_json(
        tmp_path / "data" / "challenger_lab" / "challenger_2026-07-16.json",
        {
            "date": "2026-07-16",
            "live_system": {"settled": False, "profit": 0},
            "pre_race_challengers": [
                {
                    "id": "wider_price_band_v1",
                    "name": "Wider Price Band",
                    "version": "1.0",
                    "picks": [
                        {
                            "horse": "Mr Rafiki",
                            "pre_race_evidence": {"known_cases": seed_cases},
                        }
                    ],
                    "comparison": {"settled": False, "overlap_with_live": 0},
                }
            ],
        },
    )

    payload = summary_module.build_summary()
    rows = {row["id"]: row for row in payload["pre_race_challengers"]}

    assert "wider_price_band_v1" in rows
    assert rows["wider_price_band_v1"]["days_tested"] == 1
    assert rows["wider_price_band_v1"]["seed_cases"] == seed_cases


def test_skin_in_game_challenger_records_bankroll_decision(tmp_path):
    generate = load_script("generate_challenger_lab_skin", "generate-challenger-lab.py")
    configure_module(generate, tmp_path)
    seed_generation_files(tmp_path)
    write_json(
        tmp_path / "data" / "challenger_lab" / "skin_in_game_2026-07-07.json",
        {
            "date": "2026-07-07",
            "status": "ok",
            "model": "claude-sonnet-4-6",
            "model_mode": "anthropic_api",
            "bankroll_before": 100,
            "bankroll_after": 86,
            "pass_day": False,
            "reasoning": "The AI liked one horse and held the rest back.",
            "what_convinced_me": "Strong local and external evidence.",
            "what_worried_me": "Limited sample.",
            "data_sources_used": ["signal75_local"],
            "selections": [
                {
                    "horse": "Quality Horse",
                    "course": "Testcourse",
                    "time": "14:30",
                    "odds": 5.0,
                    "stake": 14.0,
                    "reason": "Enough evidence to risk a small each-way stake.",
                }
            ],
        },
    )

    payload = generate.build_daily_payload("2026-07-07")
    challenger = next(c for c in payload["pre_race_challengers"] if c["id"] == "skin_in_game_v1")

    assert challenger["analysis_only"] is True
    assert challenger["model_mode"] == "anthropic_api"
    assert challenger["bankroll"]["starting_bankroll"] == 100.0
    assert challenger["bankroll"]["stake_selected"] <= 100.0
    assert challenger["comparison"]["stake_model"] == "real_ai_variable_bankroll"
    assert challenger["picks"]
    assert challenger["picks"][0]["stake_total"] > 0
    assert challenger["picks"][0]["reasoning"]


def test_skin_in_game_pass_day_settles_as_zero_stake_decision(tmp_path):
    generate = load_script("generate_challenger_lab_skin_pass", "generate-challenger-lab.py")
    settle = load_script("settle_challenger_lab_skin_pass", "settle-challenger-lab.py")
    configure_module(generate, tmp_path)
    configure_module(settle, tmp_path)
    seed_generation_files(tmp_path)
    write_json(
        tmp_path / "data" / "challenger_lab" / "skin_in_game_2026-07-07.json",
        {
            "date": "2026-07-07",
            "status": "ok",
            "model": "claude-sonnet-4-6",
            "model_mode": "anthropic_api",
            "bankroll_before": 100,
            "bankroll_after": 100,
            "pass_day": True,
            "reasoning": "The AI passed because the evidence was not strong enough.",
            "selections": [],
            "data_sources_used": ["signal75_local"],
        },
    )

    payload = generate.build_daily_payload("2026-07-07")
    generate.write_daily_outputs("2026-07-07", payload)
    write_json(
        tmp_path / "data" / "2026-07-07.json",
        {
            **minimal_picks(),
            "results": {"complete": True, "patentReturn": 0, "patentProfit": -14},
        },
    )

    settled = settle.settle_payload("2026-07-07")
    challenger = next(c for c in settled["pre_race_challengers"] if c["id"] == "skin_in_game_v1")

    assert challenger["picks"] == []
    assert challenger["comparison"]["settled"] is True
    assert challenger["comparison"]["challenger_stake"] == 0.0
    assert challenger["comparison"]["challenger_profit"] == 0.0
