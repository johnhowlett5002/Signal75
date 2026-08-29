#!/usr/bin/env python3
"""Phase-aware safety gate for the Signal 75 daily pipelines.

This script coordinates existing integrity checks and adds hard guards for the
recurring operational failures that are unsafe to leave to individual jobs:
unresolved Git conflicts, invalid proof JSON, stale/missing pick comparison
feeds, dashboard export drift, and incomplete post-race settlement.

Only reproducible generated files are repaired automatically. Source code,
configuration, tests and historical result records always require a person.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT / "data"
DASHBOARD_DATA = REPO_ROOT / "dashboard" / "data"
FINAL_RESULTS = {"WON", "PLACED", "LOST", "VOID"}
BET_DETAILS = {
    0: ("no_bet", 0.0),
    1: ("each_way_single", 14.0),
    2: ("each_way_double", 14.0),
    3: ("each_way_patent", 14.0),
}
SOURCE_PREFIXES = ("scripts/", "tests/", "dashboard/")
SOURCE_FILES = {"app.js", "index.html", "sw.js", ".gitignore"}
ANALYSIS_ONLY_GENERATED = (
    "data/challenger_lab/",
    "data/late_value_shadow_",
    "data/consensus_shadow_",
    "data/selection_diagnostics/",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(command: List[str], *, check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "command failed")
    return result


def load_json(path: Path) -> Tuple[Optional[Any], Optional[str]]:
    if not path.exists():
        return None, "missing"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, str(exc)
    if any(marker in text for marker in ("<<<<<<<", "=======", ">>>>>>>")):
        return None, "contains Git conflict markers"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON at line {exc.lineno}: {exc.msg}"


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def normal_name(value: Any) -> str:
    return " ".join(str(value or "").upper().split())


def official_picks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    picks: List[Dict[str, Any]] = []
    for section in ("flat", "jumps"):
        for race in payload.get(section, []) or []:
            if not isinstance(race, dict):
                continue
            for horse in race.get("horses", []) or []:
                if not isinstance(horse, dict):
                    continue
                row = dict(horse)
                row.setdefault("course", race.get("course"))
                row.setdefault("time", race.get("time"))
                row.setdefault("runners", race.get("runners", race.get("field_size")))
                row.setdefault("market_id", race.get("market_id", race.get("marketId")))
                row["section"] = section
                picks.append(row)
    return picks


def unmerged_paths() -> List[str]:
    result = run(["git", "diff", "--name-only", "--diff-filter=U"])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_source_path(path: str) -> bool:
    return path in SOURCE_FILES or path.startswith(SOURCE_PREFIXES) or path.endswith(
        (".py", ".sh", ".toml", ".yaml", ".yml", ".ini")
    )


def is_historical_result(path: str) -> bool:
    if not path.startswith("data/") or not path.endswith(".json"):
        return False
    stem = Path(path).stem
    return len(stem) == 10 and stem[4] == "-" and stem[7] == "-"


def merge_or_rebase_in_progress() -> bool:
    git_dir = REPO_ROOT / ".git"
    return any(
        path.exists()
        for path in (git_dir / "MERGE_HEAD", git_dir / "rebase-merge", git_dir / "rebase-apply")
    )


class Preflight:
    def __init__(self, phase: str, race_date: str, kind: Optional[str], repair_safe: bool):
        self.phase = phase
        self.race_date = race_date
        self.kind = kind
        self.repair_safe = repair_safe
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []
        self.repairs: List[str] = []

    def pass_(self, message: str) -> None:
        self.passed.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def regenerate_performance(self) -> bool:
        if not self.repair_safe:
            return False
        result = run([sys.executable, "scripts/generate-performance.py"])
        if result.returncode:
            self.error(
                "Safe repair failed: generate-performance.py returned "
                f"{result.returncode}: {(result.stderr or result.stdout).strip()[-500:]}"
            )
            return False
        self.repairs.append("Regenerated performance.json and its dashboard export from settled proof files")
        return True

    def validate_performance(self) -> None:
        path = REPO_ROOT / "performance.json"
        payload, issue = load_json(path)
        if issue and self.regenerate_performance():
            payload, issue = load_json(path)
        if issue or not isinstance(payload, dict):
            self.error(f"performance.json is {issue or 'not an object'}")
            return

        betting_days = int(payload.get("bettingDays") or 0)
        stake = money(payload.get("totalStake", payload.get("totalStaked")))
        returned = money(payload.get("totalReturn"))
        profit = money(payload.get("totalProfit"))
        roi = money(payload.get("roi"))
        if betting_days <= 0 or stake <= 0:
            self.error("performance.json contains a zeroed proof record despite stored history")
            return
        expected_profit = round(returned - stake, 2)
        expected_roi = round((profit / stake) * 100, 1)
        if abs(profit - expected_profit) > 0.011:
            self.error(
                f"Performance accounting mismatch: return {returned} - stake {stake} "
                f"is {expected_profit}, not profit {profit}"
            )
        if abs(roi - expected_roi) > 0.11:
            self.error(f"Performance ROI mismatch: expected {expected_roi}, found {roi}")

        dashboard, dashboard_issue = load_json(DASHBOARD_DATA / "performance.json")
        comparable = ("bettingDays", "totalStake", "totalReturn", "totalProfit", "roi")
        if dashboard_issue or not isinstance(dashboard, dict) or any(
            money(dashboard.get(key)) != money(payload.get(key)) for key in comparable
        ):
            if self.regenerate_performance():
                dashboard, dashboard_issue = load_json(DASHBOARD_DATA / "performance.json")
        if dashboard_issue or not isinstance(dashboard, dict):
            self.error(f"Dashboard performance export is {dashboard_issue or 'not an object'}")
        elif any(money(dashboard.get(key)) != money(payload.get(key)) for key in comparable):
            self.error("Dashboard performance totals do not match performance.json")
        else:
            self.pass_(f"Proof accounting valid: {betting_days} betting days, {roi}% ROI, profit £{profit:.2f}")

    def validate_picks(self) -> Optional[Dict[str, Any]]:
        payload, issue = load_json(REPO_ROOT / "picks.json")
        if issue or not isinstance(payload, dict):
            self.error(f"picks.json is {issue or 'not an object'}")
            return None
        if payload.get("date") != self.race_date:
            self.error(f"picks.json date {payload.get('date')!r} does not match {self.race_date!r}")
            return payload

        picks = official_picks(payload)
        names = [normal_name(row.get("name")) for row in picks]
        if any(not name for name in names):
            self.error("An official pick has no horse name")
        if len(names) != len(set(names)):
            self.error("The same horse appears more than once in official picks")
        if len(picks) > 3:
            self.error(f"Official pick count is {len(picks)}; maximum is 3")

        expected_type, expected_stake = BET_DETAILS.get(len(picks), ("invalid", -1.0))
        actual_type = str(payload.get("betType") or "").lower()
        actual_stake = money(payload.get("totalStake"))
        if len(picks) == 0:
            if not payload.get("noBetDay") and payload.get("mode") not in ("noBet", "noBetDay"):
                self.error("No official picks are stored but the day is not labelled no-bet")
            if actual_stake != 0:
                self.error(f"No-bet day has a non-zero stake of £{actual_stake:.2f}")
        else:
            if actual_type != expected_type:
                self.error(f"{len(picks)} picks require {expected_type}, found {actual_type or 'blank'}")
            if actual_stake != expected_stake:
                self.error(f"Official proof stake should be £{expected_stake:.2f}, found £{actual_stake:.2f}")

        for row in picks:
            name = normal_name(row.get("name")) or "unnamed horse"
            odds = money(row.get("odds"))
            score = money(row.get("score", row.get("signal_score")))
            runners = int(row.get("runners") or 0)
            if not 4.1 <= odds <= 6.0:
                self.error(f"{name} odds {odds} are outside the official 4.1-6.0 band")
            if score < 75:
                self.error(f"{name} score {score} is below the official 75 gate")
            if runners > 14:
                self.error(f"{name} field size {runners} exceeds the official maximum of 14")

        if not self.errors:
            self.pass_(f"Today's official selections valid: {len(picks)} pick(s), {expected_type}")
        return payload

    def validate_race_comparison(self, picks_payload: Optional[Dict[str, Any]]) -> None:
        path = DATA / f"race_comparison_{self.race_date}.json"
        comparison, issue = load_json(path)
        if issue or not isinstance(comparison, dict):
            self.error(f"{path.name} is {issue or 'not an object'}; View All Runners would fail")
            return
        races = comparison.get("races") or []
        if comparison.get("date") != self.race_date or not races:
            self.error(f"{path.name} has the wrong date or contains no races")
            return
        available = {
            normal_name(runner.get("name"))
            for race in races if isinstance(race, dict)
            for runner in race.get("runners", []) or [] if isinstance(runner, dict)
        }
        wanted = {normal_name(row.get("name")) for row in official_picks(picks_payload or {})}
        missing = sorted(wanted - available)
        if missing:
            self.error("Race comparison is missing official pick(s): " + ", ".join(missing))
        else:
            self.pass_(f"View All Runners feed valid: {len(races)} races")

    def validate_dashboard_picks(self, picks_payload: Optional[Dict[str, Any]]) -> None:
        exported, issue = load_json(DASHBOARD_DATA / "officialPicks.json")
        if issue or not isinstance(exported, list):
            self.error(f"Dashboard official picks export is {issue or 'not a list'}")
            return
        source_names = {normal_name(row.get("name")) for row in official_picks(picks_payload or {})}
        export_names = {normal_name(row.get("name")) for row in exported if isinstance(row, dict)}
        if source_names != export_names:
            self.error(
                "Dashboard official picks differ from picks.json: "
                f"source={sorted(source_names)}, dashboard={sorted(export_names)}"
            )
        else:
            self.pass_("Dashboard official picks match picks.json")

    def validate_challenger_latest(self) -> None:
        folder = DASHBOARD_DATA / "challenger_lab"
        latest_path = folder / "challenger_latest.json"
        dated_path = folder / f"challenger_{self.race_date}.json"
        latest, latest_issue = load_json(latest_path)
        dated, dated_issue = load_json(dated_path)
        if dated_issue or not isinstance(dated, dict):
            self.error(f"Today's Challenger Lab feed is {dated_issue or 'not an object'}")
            return
        if latest_issue or not isinstance(latest, dict) or latest.get("date") != self.race_date:
            if self.repair_safe:
                write_json(latest_path, dated)
                self.repairs.append("Restored challenger_latest.json from today's dated feed")
                latest = dated
            else:
                self.error(
                    f"Challenger Lab latest feed is dated {(latest or {}).get('date')!r}, "
                    f"expected {self.race_date!r}"
                )
                return
        self.pass_("Challenger Lab latest feed matches today's dated feed")

    def validate_daily_settlement(self) -> None:
        path = DATA / f"{self.race_date}.json"
        payload, issue = load_json(path)
        if issue or not isinstance(payload, dict):
            self.error(f"Post-race file {path.name} is {issue or 'not an object'}")
            return
        picks = official_picks(payload)
        results = payload.get("results") or {}
        rows = list(results.get("flat") or []) + list(results.get("jumps") or [])
        if picks and len(rows) < len(picks):
            self.error(f"Only {len(rows)} result rows exist for {len(picks)} official picks")
        unsettled = [str(row.get("horse") or row.get("name") or "unknown") for row in rows
                     if str(row.get("result") or "PENDING").upper() not in FINAL_RESULTS]
        if unsettled:
            self.error("Post-race settlement is incomplete for: " + ", ".join(unsettled))
        complete = results.get("complete") is True
        if rows and not complete:
            self.error("Result rows exist but results.complete is not true")
        if not unsettled:
            self.pass_(f"Post-race settlement complete: {len(rows)} result row(s)")

    def repair_generated_conflicts(self, picks_payload: Optional[Dict[str, Any]]) -> None:
        conflicts = unmerged_paths()
        if not conflicts:
            self.pass_("No unresolved Git conflicts")
            return
        for rel in conflicts:
            if is_source_path(rel):
                self.error(f"Source-code conflict requires manual review: {rel}")
                continue
            if is_historical_result(rel):
                self.error(f"Historical result conflict requires proof review: {rel}")
                continue
            path = REPO_ROOT / rel
            payload, issue = load_json(path)
            safe = False
            if rel == "performance.json":
                safe = isinstance(payload, dict) and int(payload.get("bettingDays") or 0) > 0
            elif rel == "picks.json":
                if self.phase == "pre-pick":
                    self.warn("picks.json has a generated conflict and will be rebuilt by pick generation")
                    continue
                safe = (
                    self.phase in ("post-pick", "pre-publish")
                    and isinstance(picks_payload, dict)
                    and picks_payload.get("date") == self.race_date
                    and not any("official" in item.lower() or "picks.json" in item for item in self.errors)
                )
            elif rel.startswith("data/") and rel.endswith(".json"):
                safe = issue is None and isinstance(payload, (dict, list))

            if (
                self.repair_safe
                and not safe
                and issue
                and rel.startswith(ANALYSIS_ONLY_GENERATED)
                and merge_or_rebase_in_progress()
            ):
                ours = run(["git", "show", f":2:{rel}"])
                try:
                    recovered = json.loads(ours.stdout) if ours.returncode == 0 else None
                except json.JSONDecodeError:
                    recovered = None
                if isinstance(recovered, (dict, list)):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(recovered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                    safe = True
                    self.repairs.append(f"Recovered local analysis-only generated version: {rel}")

            if self.repair_safe and safe:
                result = run(["git", "add", "--", rel])
                if result.returncode:
                    self.error(f"Could not clear validated generated conflict {rel}: {result.stderr.strip()}")
                else:
                    self.repairs.append(f"Cleared generated-file conflict after validating working copy: {rel}")
            else:
                detail = issue or "not safely reproducible in this phase"
                self.error(f"Unresolved generated-file conflict: {rel} ({detail})")

    def run_existing_integrity(self) -> None:
        command = [sys.executable, "scripts/validate_system_integrity.py"]
        if self.phase == "post-race":
            command.append("--post-race")
        result = run(command)
        tail = (result.stdout or result.stderr).strip().splitlines()
        summary = tail[0] if tail else f"exit {result.returncode}"
        if result.returncode == 2:
            self.error(f"Existing integrity suite failed: {summary}")
        elif result.returncode == 1:
            self.warn(f"Existing integrity suite reported warnings: {summary}")
        else:
            self.pass_("Existing integrity suite passed")

    def check_ai_cost_switches(self) -> None:
        enabled = [name for name in ("SIGNAL75_ENABLE_SKIN_IN_GAME", "SIGNAL75_ENABLE_ANTHROPIC_FALLBACK")
                   if os.environ.get(name, "").strip() == "1"]
        if enabled:
            self.error("Paid Anthropic switch enabled: " + ", ".join(enabled))
        else:
            self.pass_("Paid Anthropic features are disabled")

    def execute(self) -> Dict[str, Any]:
        self.check_ai_cost_switches()
        self.validate_performance()

        picks_payload: Optional[Dict[str, Any]] = None
        needs_picks = self.phase == "post-pick" or (
            self.phase == "pre-publish" and self.kind == "picks"
        )
        if needs_picks:
            picks_payload = self.validate_picks()
            self.validate_race_comparison(picks_payload)
            if self.phase == "post-pick":
                self.validate_dashboard_picks(picks_payload)
                self.validate_challenger_latest()
        if self.phase == "post-race":
            self.validate_daily_settlement()

        self.repair_generated_conflicts(picks_payload)
        self.run_existing_integrity()
        status = "ERROR" if self.errors else ("WARNING" if self.warnings else "OK")
        return {
            "date": self.race_date,
            "runAt": now_iso(),
            "phase": self.phase,
            "kind": self.kind,
            "repairSafe": self.repair_safe,
            "status": status,
            "passed": len(self.passed),
            "warnings": len(self.warnings),
            "errors": len(self.errors),
            "passedChecks": self.passed,
            "warningList": self.warnings,
            "errorList": self.errors,
            "repairs": self.repairs,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Signal 75 master safety preflight.")
    parser.add_argument("--phase", choices=("pre-pick", "post-pick", "post-race", "pre-publish"), required=True)
    parser.add_argument("--kind", choices=("picks", "results"))
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--repair-safe", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    if args.phase == "pre-publish" and not args.kind:
        parser.error("--kind is required for pre-publish")

    payload = Preflight(args.phase, args.date, args.kind, args.repair_safe).execute()
    output = Path(args.output) if args.output else DATA / f"master_preflight_{args.date}_{args.phase}.json"
    write_json(output, payload)
    print(
        f"Master preflight {args.phase}: {payload['status']} | "
        f"passed {payload['passed']} | warnings {payload['warnings']} | errors {payload['errors']}"
    )
    for item in payload["repairs"]:
        print(f"REPAIRED: {item}")
    for item in payload["warningList"]:
        print(f"WARNING: {item}")
    for item in payload["errorList"]:
        print(f"ERROR: {item}")
    return 2 if payload["errors"] else (1 if payload["warnings"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
