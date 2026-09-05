#!/usr/bin/env python3
"""Small shared config loader for Signal 75 reporting scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "data" / "system_config.json"

DEFAULT_OFFICIAL_SELECTION_POLICY: Dict[str, Any] = {
    "version": "2026-09-02-context-guard-v1",
    "status": "live",
    "minimum_score": 75,
    "minimum_odds": 2.75,
    "maximum_odds": 6.0,
    "minimum_field_size": 8,
    "maximum_field_size": 14,
    "positive_h2h_cap": 2,
    "quick_return_days": 3,
    "quick_return_penalty": 5,
    "unknown_context_threshold": 3,
    "unknown_context_score_cap": 79,
    "maximum_picks_per_course": 2,
    "required_context_dimensions": [
        "form", "class", "h2h", "distance", "going", "weight",
        "draw", "jockey", "trainer", "tipsters",
    ],
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "project": "Signal 75",
    "site_url": "https://signal75.co.uk",
    "proof_basis": "£1 each-way Patent",
    "stake_per_line": 1.0,
    "patent_bets": 7,
    "patent_lines": 14,
    "each_way": True,
    "total_bet_lines": 14,
    "daily_stake": 14.0,
    "official_pick_count": 3,
    "results_start_date": "2026-05-24",
    "live_odds_gate_low": 2.75,
    "live_odds_gate_high": 8.0,
    "score_gate": 70,
    "min_tipsters_consensus": 1,
    "score_gate_strict": 75,
    "odds_gate_strict_low": 2.75,
    "odds_gate_strict_high": 6.0,
    "strict_value_band_status": "live",
    "official_selection_policy": DEFAULT_OFFICIAL_SELECTION_POLICY,
    "radar_counts_in_proof": False,
    "shadow_counts_in_proof": False,
    "radar_counts_in_results": False,
    "shadow_counts_in_results": False,
}


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a normalised config or raise ValueError with plain failures."""
    errors = []

    def number(key: str, minimum: Optional[float] = None) -> float:
        try:
            value = float(config.get(key))
        except (TypeError, ValueError):
            errors.append(f"{key} must be a number")
            return 0.0
        if minimum is not None and value < minimum:
            errors.append(f"{key} must be at least {minimum:g}")
        return value

    stake = number("stake_per_line", 0.01)
    patent_lines = number("patent_lines", 1)
    total_lines = number("total_bet_lines", 1)
    daily_stake = number("daily_stake", 0)
    live_low = number("live_odds_gate_low", 1.01)
    live_high = number("live_odds_gate_high", 1.01)
    strict_low = number("odds_gate_strict_low", 1.01)
    strict_high = number("odds_gate_strict_high", 1.01)
    score_gate = number("score_gate", 0)
    strict_score_gate = number("score_gate_strict", 0)
    min_tipsters = number("min_tipsters_consensus", 0)

    if live_low >= live_high:
        errors.append("live_odds_gate_low must be lower than live_odds_gate_high")
    if strict_low >= strict_high:
        errors.append("odds_gate_strict_low must be lower than odds_gate_strict_high")
    if not 0 <= score_gate <= 100:
        errors.append("score_gate must be between 0 and 100")
    if not 0 <= strict_score_gate <= 100:
        errors.append("score_gate_strict must be between 0 and 100")
    if int(min_tipsters) != min_tipsters:
        errors.append("min_tipsters_consensus must be a whole number")

    expected_stake = round(stake * total_lines, 2)
    if daily_stake and abs(daily_stake - expected_stake) > 0.01:
        errors.append(
            f"daily_stake should equal stake_per_line x total_bet_lines "
            f"({stake:g} x {int(total_lines)} = {expected_stake:g})"
        )
    if patent_lines != total_lines:
        errors.append("patent_lines and total_bet_lines should match for public proof reporting")

    status = str(config.get("strict_value_band_status", "")).strip()
    if status not in {"shadow_only", "live", "retired"}:
        errors.append("strict_value_band_status must be shadow_only, live, or retired")

    if config.get("radar_counts_in_results") is not False:
        errors.append("radar_counts_in_results must be false")
    if config.get("shadow_counts_in_results") is not False:
        errors.append("shadow_counts_in_results must be false")
    if config.get("radar_counts_in_proof") is not False:
        errors.append("radar_counts_in_proof must be false")
    if config.get("shadow_counts_in_proof") is not False:
        errors.append("shadow_counts_in_proof must be false")

    policy = config.get("official_selection_policy")
    if not isinstance(policy, dict):
        errors.append("official_selection_policy must be an object")
        policy = {}
    required_policy = DEFAULT_OFFICIAL_SELECTION_POLICY
    if str(policy.get("version") or "").strip() != required_policy["version"]:
        errors.append(f"official_selection_policy.version must be {required_policy['version']}")
    if policy.get("status") != "live":
        errors.append("official_selection_policy.status must be live")
    for key, required_value in required_policy.items():
        if key in {"version", "status", "required_context_dimensions"}:
            continue
        if policy.get(key) != required_value:
            errors.append(f"official_selection_policy.{key} must be {required_value}")
    dimensions = policy.get("required_context_dimensions")
    if not isinstance(dimensions, list) or set(dimensions) != set(required_policy["required_context_dimensions"]):
        errors.append("official_selection_policy.required_context_dimensions is incomplete")
    if policy.get("minimum_score") != strict_score_gate:
        errors.append("official selection policy minimum_score must match score_gate_strict")
    if policy.get("minimum_odds") != strict_low or policy.get("maximum_odds") != strict_high:
        errors.append("official selection policy odds must match the strict value band")

    if errors:
        raise ValueError("; ".join(errors))
    return config


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load system_config.json with safe defaults for future scripts."""
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config = dict(DEFAULT_CONFIG)
    config["official_selection_policy"] = dict(DEFAULT_OFFICIAL_SELECTION_POLICY)

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError(f"{config_path} must contain a JSON object")
        config.update(loaded)

    stake = float(config.get("stake_per_line", 1.0))
    patent_bets = int(config.get("patent_bets", 7))
    fallback_lines = patent_bets * 2 if config.get("each_way", True) else patent_bets
    total_lines = int(config.get("total_bet_lines") or config.get("patent_lines") or fallback_lines)
    config["total_bet_lines"] = total_lines
    config["daily_stake"] = round(float(config.get("daily_stake") or stake * total_lines), 2)
    return validate_config(config)


if __name__ == "__main__":
    print(json.dumps(load_config(), indent=2, ensure_ascii=False))
