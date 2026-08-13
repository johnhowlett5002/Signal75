#!/usr/bin/env python3
"""Audit Signal 75 settlement estimates against verified bookmaker slips.

This report is deliberately an audit, not a correction engine. Verified
bookmaker returns are exact for the supplied slip. Unverified days remain
Signal 75 proof estimates until a verified slip or official settlement price is
available.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
OVERRIDES = DATA / "bookmaker_price_overrides.json"
OUT = DATA / "settlement_price_audit.json"
DASHBOARD_OUT = REPO / "dashboard" / "data" / "settlementPriceAudit.json"
MONEY_TOLERANCE = 0.02


def load_helpers():
    path = REPO / "scripts" / "update-results-mac.py"
    spec = importlib.util.spec_from_file_location("update_results_mac_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def estimate_before_verified(results: dict[str, Any]) -> tuple[float, str]:
    bet_summary = results.get("betSummary") if isinstance(results.get("betSummary"), dict) else {}
    candidates = (
        ("calculatedReturnBeforeVerifiedSlip", results.get("calculatedReturnBeforeVerifiedSlip")),
        ("betSummary.calculatedReturnBeforeVerifiedSlip", bet_summary.get("calculatedReturnBeforeVerifiedSlip")),
        ("lockedReturn", results.get("lockedReturn")),
        ("betSummary.lockedReturn", bet_summary.get("lockedReturn")),
        ("totalReturn", results.get("totalReturn")),
    )
    for source, value in candidates:
        if value not in (None, ""):
            return money(value), source
    return 0.0, "missing"


def audit() -> dict[str, Any]:
    helpers = load_helpers()
    overrides = read_json(OVERRIDES, {})
    rows: list[dict[str, Any]] = []
    errors: list[str] = []

    for date_text in sorted(overrides):
        path = DATA / f"{date_text}.json"
        day = read_json(path, {})
        results = day.get("results") if isinstance(day.get("results"), dict) else {}
        if not results:
            errors.append(f"{date_text}: daily result file missing results section")
            continue
        lookup = helpers.load_bookmaker_price_overrides(date_text)
        stake = money(results.get("totalStake"))
        verified = helpers.verified_proof_return_from_overrides(lookup, stake)
        if verified is None:
            continue
        stored = money(results.get("totalReturn", results.get("patentReturn", 0)))
        estimate, estimate_source = estimate_before_verified(results)
        diff = round(verified - estimate, 2)
        pct_diff = round((diff / estimate) * 100, 1) if estimate else None
        stored_diff = round(stored - verified, 2)
        if abs(stored_diff) > MONEY_TOLERANCE:
            errors.append(
                f"{date_text}: stored return {stored:.2f} does not match verified {verified:.2f}"
            )
        rows.append(
            {
                "date": date_text,
                "betType": results.get("betType", ""),
                "stake": stake,
                "signal75EstimatedReturn": estimate,
                "estimateSource": estimate_source,
                "verifiedBookmakerReturn": round(float(verified), 2),
                "storedReturn": stored,
                "differenceVsEstimate": diff,
                "percentageDifferenceVsEstimate": pct_diff,
                "storedMatchesVerified": abs(stored_diff) <= MONEY_TOLERANCE,
            }
        )

    diffs = [row["differenceVsEstimate"] for row in rows]
    abs_diffs = [abs(row["differenceVsEstimate"]) for row in rows]
    pct_diffs = [
        row["percentageDifferenceVsEstimate"]
        for row in rows
        if row["percentageDifferenceVsEstimate"] is not None
    ]
    max_row = max(rows, key=lambda row: abs(row["differenceVsEstimate"]), default={})

    return {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": "data/bookmaker_price_overrides.json",
        "verifiedDays": len(rows),
        "summary": {
            "averageMoneyDifference": round(mean(diffs), 2) if diffs else 0.0,
            "averageAbsoluteMoneyDifference": round(mean(abs_diffs), 2) if abs_diffs else 0.0,
            "averagePercentageDifference": round(mean(pct_diffs), 1) if pct_diffs else 0.0,
            "averageAbsolutePercentageDifference": round(mean([abs(v) for v in pct_diffs]), 1) if pct_diffs else 0.0,
            "largestAbsoluteDifference": max_row,
            "recommendation": (
                "Do not apply a blanket percentage correction. Verified slips show "
                "settlement drift is uneven, so exact verified returns should override "
                "estimates and unverified days should remain labelled as estimates."
            ),
        },
        "rows": rows,
        "errors": errors,
        "status": "ERROR" if errors else "OK",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit verified bookmaker return drift.")
    parser.add_argument("--no-dashboard-copy", action="store_true")
    args = parser.parse_args()

    payload = audit()
    write_json(OUT, payload)
    if not args.no_dashboard_copy:
        write_json(DASHBOARD_OUT, payload)

    summary = payload["summary"]
    print(f"Settlement price audit: {payload['status']}")
    print(f"Verified days: {payload['verifiedDays']}")
    print(f"Average money drift: {summary['averageMoneyDifference']:+.2f}")
    print(f"Average absolute money drift: {summary['averageAbsoluteMoneyDifference']:.2f}")
    print(f"Average percent drift: {summary['averagePercentageDifference']:+.1f}%")
    print(f"Average absolute percent drift: {summary['averageAbsolutePercentageDifference']:.1f}%")
    print(summary["recommendation"])
    for error in payload["errors"]:
        print(f"ERROR: {error}")
    return 2 if payload["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
