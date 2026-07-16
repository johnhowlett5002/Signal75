#!/usr/bin/env python3
"""
Build aggregate Challenger Lab summaries.

Analysis-only. Reads data/challenger_lab/challenger_*.json and writes summary
files only inside challenger_lab output folders.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
CHALLENGER_DIR = REPO_ROOT / "data" / "challenger_lab"
DASHBOARD_CHALLENGER_DIR = REPO_ROOT / "dashboard" / "data" / "challenger_lab"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def money(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def daily_files() -> List[Path]:
    return sorted(p for p in CHALLENGER_DIR.glob("challenger_*.json") if p.name != "challenger_summary.json")


def promotion_status(days: int, picks: int, delta: float, one_big_day: bool) -> str:
    if days < 14:
        return "COLLECTING"
    if picks < 50:
        return "NEEDS_MORE_DATA"
    if delta <= 0 or one_big_day:
        return "RISKY"
    if days < 30:
        return "PROMISING"
    return "PROMOTION_CANDIDATE"


def archived_reason(verdict: str, days: int, delta_roi: float, negative_days: int) -> str:
    if verdict == "TESTED_AND_REJECTED":
        return (
            f"Archived after {negative_days} consecutive settled negative days. "
            "The challenger was making paper results worse than the live system."
        )
    return (
        f"Archived after {days} settled days with delta vs live ROI within +/-5% "
        f"({delta_roi:.1f}%). No clear winner emerged."
    )


def auto_archive_status(
    summary: Dict[str, Any],
    previous: Dict[str, Any],
    negative_days: int,
    delta_roi: float,
) -> Dict[str, Any]:
    previous_status = previous.get("promotion_status")
    if previous_status in {"TESTED_AND_REJECTED", "INCONCLUSIVE_AT_30_DAYS"}:
        summary["promotion_status"] = previous_status
        summary["archived_at"] = previous.get("archived_at") or now_iso()
        summary["archived_reason"] = previous.get("archived_reason") or "This challenger was previously archived."
        summary["archived"] = True
        return summary

    settled_days = int(summary.get("settled_days") or 0)
    verdict = None
    if negative_days >= 7:
        verdict = "TESTED_AND_REJECTED"
    elif settled_days >= 30 and abs(delta_roi) <= 5:
        verdict = "INCONCLUSIVE_AT_30_DAYS"

    if verdict:
        summary["promotion_status"] = verdict
        summary["archived_at"] = now_iso()
        summary["archived_reason"] = archived_reason(verdict, settled_days, delta_roi, negative_days)
        summary["archived"] = True
    else:
        summary["archived"] = False
    return summary


def build_summary() -> Dict[str, Any]:
    files = daily_files()
    previous_summary = read_json(CHALLENGER_DIR / "challenger_summary.json", {})
    previous_by_id = {
        row.get("id"): row
        for row in previous_summary.get("pre_race_challengers", []) or []
        if row.get("id")
    }
    records = [read_json(path, {}) for path in files]
    records = [r for r in records if isinstance(r, dict) and r.get("date")]
    dates = [r.get("date") for r in records]
    live_profit = sum(money((r.get("live_system") or {}).get("profit")) for r in records if (r.get("live_system") or {}).get("settled"))
    live_days = sum(1 for r in records if (r.get("live_system") or {}).get("settled"))

    by_id: Dict[str, Dict[str, Any]] = {}
    field_aware_vs_old = {
        "days_compared": 0,
        "days_field_aware_better": 0,
        "days_old_better": 0,
        "days_same": 0,
        "known_wins_field_aware": [],
        "known_wins_old": [],
        "dates": [],
    }
    for record in records:
        for challenger in record.get("pre_race_challengers", []) or []:
            cid = challenger.get("id")
            if not cid:
                continue
            if cid == "rival_evidence_v1":
                comparison = challenger.get("old_overlay_comparison") or {}
                if comparison:
                    record_date = record.get("date")
                    field_aware_vs_old["days_compared"] += 1
                    verdict = challenger.get("verdict") or (challenger.get("comparison") or {}).get("verdict")
                    if verdict == "FIELD_AWARE_BETTER":
                        field_aware_vs_old["days_field_aware_better"] += 1
                        field_aware_vs_old["known_wins_field_aware"].append(record_date)
                    elif verdict == "OLD_OVERLAY_BETTER":
                        field_aware_vs_old["days_old_better"] += 1
                        field_aware_vs_old["known_wins_old"].append(record_date)
                    else:
                        field_aware_vs_old["days_same"] += 1
                    field_aware_vs_old["dates"].append(
                        {
                            "date": record_date,
                            "verdict": verdict or "COLLECTING",
                            "old_overlay": comparison,
                            "picks": challenger.get("picks") or [],
                            "comparison": challenger.get("comparison") or {},
                        }
                    )
            row = by_id.setdefault(
                cid,
                {
                    "id": cid,
                    "name": challenger.get("name", cid),
                    "version": challenger.get("version", "1.0"),
                    "days_tested": 0,
                    "settled_days": 0,
                    "total_picks": 0,
                    "total_stake": 0.0,
                    "total_return": 0.0,
                    "total_profit": 0.0,
                    "delta_vs_live_profit": 0.0,
                    "winning_days": 0,
                    "losing_days": 0,
                    "daily_profits": [],
                    "daily_deltas": [],
                    "same_pick_days": 0,
                    "different_pick_days": 0,
                    "overlaps": [],
                    "seed_cases": [],
                },
            )
            row["days_tested"] += 1
            row["total_picks"] += len(challenger.get("picks") or [])
            for pick in challenger.get("picks") or []:
                evidence = pick.get("pre_race_evidence") or {}
                for seed_case in evidence.get("known_cases") or []:
                    if seed_case not in row["seed_cases"]:
                        row["seed_cases"].append(seed_case)
            comparison = challenger.get("comparison") or {}
            row["overlaps"].append(comparison.get("overlap_with_live", 0))
            if comparison.get("same_as_live"):
                row["same_pick_days"] += 1
            else:
                row["different_pick_days"] += 1
            if comparison.get("settled"):
                profit = money(comparison.get("challenger_profit"))
                ret = money(comparison.get("challenger_return"))
                live = money(comparison.get("live_profit"))
                delta = profit - live
                row["settled_days"] += 1
                row["total_stake"] += 14.0
                row["total_return"] += ret
                row["total_profit"] += profit
                row["delta_vs_live_profit"] += delta
                row["daily_profits"].append(profit)
                row["daily_deltas"].append(delta)
                if profit >= 0:
                    row["winning_days"] += 1
                else:
                    row["losing_days"] += 1

    challenger_summaries: List[Dict[str, Any]] = []
    promotion_candidates: List[Dict[str, Any]] = []
    for row in by_id.values():
        profits = row.pop("daily_profits")
        daily_deltas = row.pop("daily_deltas")
        overlaps = row.pop("overlaps")
        best = max(profits) if profits else None
        worst = min(profits) if profits else None
        best_removed_delta = row["delta_vs_live_profit"] - (best or 0)
        one_big_day = bool(best is not None and row["delta_vs_live_profit"] > 0 and best_removed_delta <= 0)
        roi = round((row["total_profit"] / row["total_stake"]) * 100, 1) if row["total_stake"] else 0.0
        delta_roi = round((row["delta_vs_live_profit"] / row["total_stake"]) * 100, 1) if row["total_stake"] else 0.0
        status = promotion_status(row["settled_days"], row["total_picks"], row["delta_vs_live_profit"], one_big_day)
        consecutive_negative_days = 0
        for delta in reversed(daily_deltas):
            if delta < 0:
                consecutive_negative_days += 1
            else:
                break
        summary = {
            **row,
            "analysis_only": True,
            "scoringImpact": "none",
            "overlap_with_live_avg_pct": round((sum(overlaps) / (len(overlaps) * 3)) * 100, 1) if overlaps else 0.0,
            "total_stake": round(row["total_stake"], 2),
            "total_return": round(row["total_return"], 2),
            "total_profit": round(row["total_profit"], 2),
            "roi": roi,
            "delta_vs_live_profit": round(row["delta_vs_live_profit"], 2),
            "delta_vs_live_roi": delta_roi,
            "best_day_profit": best,
            "worst_day_profit": worst,
            "max_drawdown": None,
            "consecutive_negative_days": consecutive_negative_days,
            "daily_delta": [round(v, 2) for v in daily_deltas[-14:]],
            "daily_profit": [round(v, 2) for v in profits[-14:]],
            "one_big_winner_distorting": one_big_day,
            "sample_warning": "Too early" if row["settled_days"] < 14 else "Review sample carefully",
            "promotion_status": status,
            "promotion_criteria": {
                "min_settled_days_early_review": 14,
                "min_settled_days_serious_review": 30,
                "min_total_picks": 50,
                "positive_delta_required": True,
                "no_data_leakage_confirmed": True,
                "john_approval_required": True,
            },
        }
        summary = auto_archive_status(
            summary,
            previous_by_id.get(row["id"], {}),
            consecutive_negative_days,
            delta_roi,
        )
        challenger_summaries.append(summary)
        if summary.get("promotion_status") == "PROMOTION_CANDIDATE":
            promotion_candidates.append(summary)

    payload = {
        "generated_at": now_iso(),
        "date_range": {"start": min(dates) if dates else None, "end": max(dates) if dates else None},
        "live": {
            "days": len(records),
            "betting_days": live_days,
            "total_stake": round(live_days * 14.0, 2),
            "total_return": round(live_profit + live_days * 14.0, 2) if live_days else 0.0,
            "total_profit": round(live_profit, 2),
            "roi": round((live_profit / (live_days * 14.0)) * 100, 1) if live_days else 0.0,
        },
        "pre_race_challengers": sorted(challenger_summaries, key=lambda r: r["id"]),
        "field_aware_vs_old_overlay": field_aware_vs_old,
        "promotion_candidates": promotion_candidates,
        "future_challengers_planned": [
            "strict_value_band_v1",
            "no_consensus_score_first_v1",
            "clv_tipster_v1",
            "wider_price_band_v1",
        ],
        "safety": {"analysis_only": True, "no_live_changes": True},
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Signal 75 Challenger Lab summary.")
    parser.parse_args()
    summary = build_summary()
    candidates = {
        "generated_at": summary["generated_at"],
        "promotion_candidates": summary["promotion_candidates"],
        "manual_approval_required": True,
    }
    promotion_log = {
        "generated_at": summary["generated_at"],
        "events": [],
        "note": "Promotion cannot be automatic. John approval and a separate implementation brief are required.",
    }
    for folder in (CHALLENGER_DIR, DASHBOARD_CHALLENGER_DIR):
        write_json(folder / "challenger_summary.json", summary)
        write_json(folder / "promotion_candidates.json", candidates)
    write_json(CHALLENGER_DIR / "promotion_log.json", promotion_log)
    print("Challenger Lab summary built")
    print(f"  challengers: {len(summary['pre_race_challengers'])}")
    print(f"  promotion candidates: {len(summary['promotion_candidates'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
