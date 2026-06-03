#!/usr/bin/env python3
"""Validate Signal 75's shared system config before making risky changes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config_loader import DEFAULT_CONFIG_PATH, load_config


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG_PATH
    try:
        config = load_config(path)
    except Exception as exc:
        print(f"CONFIG INVALID: {exc}")
        return 1

    summary = {
        "status": "ok",
        "config_path": str(path),
        "proof_basis": config["proof_basis"],
        "daily_stake": config["daily_stake"],
        "live_odds_gate": [
            config["live_odds_gate_low"],
            config["live_odds_gate_high"],
        ],
        "strict_value_band": [
            config["odds_gate_strict_low"],
            config["odds_gate_strict_high"],
        ],
        "strict_value_band_status": config.get("strict_value_band_status"),
        "score_gate": config["score_gate"],
        "min_tipsters_consensus": config["min_tipsters_consensus"],
        "radar_counts_in_proof": config["radar_counts_in_proof"],
        "shadow_counts_in_proof": config["shadow_counts_in_proof"],
        "radar_counts_in_results": config["radar_counts_in_results"],
        "shadow_counts_in_results": config["shadow_counts_in_results"],
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
