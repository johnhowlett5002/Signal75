#!/usr/bin/env python3
"""Fail-closed behavioural canary for the live Signal 75 selection policy."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from config_loader import load_config


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the live official-selection policy contract.")
    parser.add_argument("--output", default=str(ROOT / "data" / "official_policy_canary_latest.json"))
    args = parser.parse_args()

    errors = []
    config = load_config()
    policy = config["official_selection_policy"]
    picks = load_module("official_policy_canary_picks", "generate-picks-betfair.py")
    scoring = load_module("official_policy_canary_scoring", "scoring_engine.py")

    expected_constants = {
        "OFFICIAL_POLICY_VERSION": policy["version"],
        "OFFICIAL_MIN_SCORE": float(policy["minimum_score"]),
        "OFFICIAL_MIN_ODDS": float(policy["minimum_odds"]),
        "OFFICIAL_MAX_ODDS": float(policy["maximum_odds"]),
        "OFFICIAL_MIN_FIELD_SIZE": int(policy["minimum_field_size"]),
        "OFFICIAL_MAX_FIELD_SIZE": int(policy["maximum_field_size"]),
        "OFFICIAL_H2H_CAP": int(policy["positive_h2h_cap"]),
        "OFFICIAL_QUICK_RETURN_DAYS": int(policy["quick_return_days"]),
        "OFFICIAL_QUICK_RETURN_PENALTY": int(policy["quick_return_penalty"]),
        "OFFICIAL_MAX_PICKS_PER_COURSE": int(policy["maximum_picks_per_course"]),
    }
    for name, expected in expected_constants.items():
        if getattr(picks, name, None) != expected:
            errors.append(f"generator {name} does not match system_config.json")

    if scoring.OFFICIAL_MIN_ODDS != policy["minimum_odds"]:
        errors.append("scoring engine minimum odds do not match the canonical policy")
    if scoring.OFFICIAL_MAX_ODDS != policy["maximum_odds"]:
        errors.append("scoring engine maximum odds do not match the canonical policy")

    guarded = {
        "name": "Policy Canary",
        "score": 100,
        "days_since": 2,
        "consensus": {"consensus_count": 0},
        "rival_memory_overlay": {"points": 8},
        "rich_context": {"statuses": {
            "course": "unknown", "distance": "unknown", "going": "unknown",
            "weight": "known", "draw": "known", "jockey": "known", "trainer": "known",
        }},
    }
    profile = picks._official_context_guard_profile(
        guarded,
        {"evidence_status": "unknown", "points": 0, "score_cap": None},
    )
    if profile.get("policy_version") != policy["version"]:
        errors.append("context guard did not record the canonical policy version")
    if profile.get("rival_points_allowed") != policy["positive_h2h_cap"]:
        errors.append("positive H2H cap is not active")
    penalties = {item.get("reason", ""): item.get("points") for item in profile.get("penalties", [])}
    if not any("positive H2H" in reason and points == 6 for reason, points in penalties.items()):
        errors.append("oversized H2H contribution was not removed")
    if not any("quick return" in reason and points == policy["quick_return_penalty"] for reason, points in penalties.items()):
        errors.append("quick-return penalty is not active")
    if profile.get("confidence_cap") != policy["unknown_context_score_cap"]:
        errors.append("unknown-context confidence cap is not active")

    candidates = [
        {"name": "One", "market_id": "1", "venue": "Same", "score": 90},
        {"name": "Two", "market_id": "2", "venue": "Same", "score": 89},
        {"name": "Three", "market_id": "3", "venue": "Same", "score": 88},
        {"name": "Four", "market_id": "4", "venue": "Other", "score": 87},
    ]
    selected = picks._pick_three(candidates, max_per_course=policy["maximum_picks_per_course"])
    if [row["name"] for row in selected] != ["One", "Two", "Four"]:
        errors.append("same-course concentration limit is not active")

    required_dimensions = set(policy["required_context_dimensions"])
    if required_dimensions != {
        "form", "class", "h2h", "distance", "going", "weight",
        "draw", "jockey", "trainer", "tipsters",
    }:
        errors.append("required context dimension list is incomplete")

    payload = {
        "runAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "error" if errors else "ok",
        "policyVersion": policy["version"],
        "checks": 7,
        "errors": errors,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
