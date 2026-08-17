#!/usr/bin/env python3
"""
Generate the real AI skin_in_game_v1 paper decision.

Analysis-only. Calls Anthropic only when ANTHROPIC_API_KEY, CLAUDE_API_KEY, or
the Signal 75 macOS Keychain item is available. If the API is unavailable,
writes an explicit skipped record rather than fabricating an AI decision.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(os.environ.get("SIGNAL75_REPO_ROOT", Path(__file__).resolve().parents[1]))
DATA = REPO_ROOT / "data"
CHALLENGER_DIR = DATA / "challenger_lab"
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("SKIN_IN_GAME_MAX_TOKENS", "2000"))
API_URL = "https://api.anthropic.com/v1/messages"
KEYCHAIN_ACCOUNT = "signal75"
KEYCHAIN_SERVICE = "anthropic-api-key"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_date() -> str:
    return date.today().isoformat()


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


def load_anthropic_api_key() -> str:
    key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY") or "").strip()
    if key:
        return key
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                KEYCHAIN_ACCOUNT,
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception:
        return ""
    return (result.stdout or "").strip()


def normalise(value: Any) -> str:
    text = str(value or "").lower().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def money(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def latest_bankroll_before(date_value: str) -> float:
    previous = []
    for path in CHALLENGER_DIR.glob("skin_in_game_2026-*.json"):
        if path.stem.replace("skin_in_game_", "") < date_value:
            previous.append(path)
    if not previous:
        return 100.0
    latest = read_json(sorted(previous)[-1], {})
    return money(latest.get("bankroll_after"), money(latest.get("bankroll_before"), 100.0))


def compact_briefing(briefing: Dict[str, Any]) -> Dict[str, Any]:
    local = briefing.get("local") or {}
    web = briefing.get("web") or {}
    compact_web = {}
    for key, row in web.items():
        compact_web[key] = {
            "ok": row.get("ok"),
            "status": row.get("status"),
            "title": row.get("title"),
            "field_horse_mentions": row.get("field_horse_mentions"),
            "text_excerpt": str(row.get("text_excerpt") or "")[:2500],
            "error": row.get("error"),
        }
    return {
        "date": briefing.get("date"),
        "collection_summary": briefing.get("collection_summary"),
        "independent_race_fields": local.get("independent_race_fields") or [],
        "recent_skin_in_game_context": local.get("recent_skin_in_game_context") or [],
        "signal75_official_picks_for_after_decision_comparison_only": local.get("signal75_official_picks_for_after_decision_comparison_only") or [],
        "web": compact_web,
    }


def build_prompts(briefing: Dict[str, Any], bankroll: float) -> Tuple[str, str]:
    system = (
        f"You are an experienced and disciplined horse racing punter with £{bankroll:.2f} "
        "of your own money on the line. This is real money to you — you feel every loss.\n\n"
        "You are completely independent. You may agree with Signal 75, disagree entirely, "
        "back different horses, change the stakes, or pass the day completely.\n\n"
        "Passing when not confident is the mark of a good punter. Do not force selections "
        "on weak days.\n\n"
        "You have access to today's race-field data, public web extracts and current market "
        "prices where collected.\n\n"
        "Important: make an independent decision. Do not use Signal 75 scores, Signal 75 "
        "tipster counts, Signal 75 warnings, or official-pick status as evidence for your "
        "selection. If Signal 75 official picks are present in the JSON, they are for "
        "after-decision comparison only.\n\n"
        "Your goal: find genuine value. Back horses where the evidence is compelling and "
        "the price is fair. Ignore horses where something feels wrong even if the market "
        "looks tempting.\n\nThink like a professional. Be selective. Be honest about doubt."
    )
    user = (
        f"Today is {briefing.get('date')}.\n\n"
        f"YOUR CURRENT BANKROLL: £{bankroll:.2f}\n"
        "(Started at £100. Track your running P&L.)\n\n"
        "Use the following independent JSON briefing. You can back any combination of horses each-way, "
        "at any total stake between £2 and £20 per horse. Or pass the day entirely. Win-only bets are "
        "not allowed in this experiment.\n\n"
        f"{json.dumps(compact_briefing(briefing), indent=2)[:65_000]}\n\n"
        "Selection rules:\n"
        "- Base your decision on public/external evidence, race setup, odds, field context, form, trainer/jockey clues and market value where available.\n"
        "- Do not cite Signal 75 score, Signal 75 tipster count, or Signal 75 official selection status as a reason.\n"
        "- Only return each-way selections. Do not return win-only bets or very short favourites unless they still make sense each-way.\n"
        "- If the independent evidence is too thin, pass the day with £0 stake.\n\n"
        "NOW MAKE YOUR DECISION.\n\n"
        "Respond only in valid JSON using this exact shape:\n"
        "{\n"
        '  "pass_day": false,\n'
        '  "bankroll_before": 86.50,\n'
        '  "reasoning": "Two to three plain-English sentences",\n'
        '  "what_convinced_me": "Specific evidence",\n'
        '  "what_worried_me": "Concerns and doubts",\n'
        '  "selections": [\n'
        '    {"horse": "NAME", "course": "Course", "time": "14:30", "odds": 4.5, "stake": 14.00, "bet_type": "each_way", "reason": "Why this horse"}\n'
        "  ],\n"
        '  "passed_on": [{"horse": "NAME", "reason": "Why not backed"}],\n'
        '  "spotted_outside_signal75": [{"horse": "NAME", "odds": 5.2, "reason": "Why noticed"}]\n'
        "}"
    )
    return system, user


def call_anthropic(system: str, user: str) -> Dict[str, Any]:
    key = load_anthropic_api_key()
    if not key:
        raise RuntimeError("Anthropic API key is not set in environment or macOS Keychain")
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def response_text(response: Dict[str, Any]) -> str:
    parts = []
    for block in response.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts).strip()


def parse_ai_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"(?s)\{.*\}", text)
    if not match:
        raise ValueError("Claude response did not contain a JSON object")
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except Exception:
        parsed = ast.literal_eval(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Claude response JSON parsed to non-object")
        return parsed


def sanitize_decision(decision: Dict[str, Any], date_value: str, bankroll_before: float, briefing: Dict[str, Any], raw_response: str = "", skip_reason: str | None = None) -> Dict[str, Any]:
    selections = []
    total_stake = 0.0
    if not skip_reason:
        for row in decision.get("selections") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("bet_type") or "each_way").lower().replace("-", "_") not in {"each_way", "ew", "e_w"}:
                continue
            stake = max(0.0, min(20.0, money(row.get("stake"))))
            if 0 < stake < 2.0:
                stake = 2.0
            if total_stake + stake > 100.0:
                continue
            total_stake = round(total_stake + stake, 2)
            selections.append(
                {
                    "horse": str(row.get("horse") or "").strip(),
                    "course": str(row.get("course") or "").strip(),
                    "time": str(row.get("time") or "").strip(),
                    "odds": money(row.get("odds")),
                    "stake": stake,
                    "bet_type": "each_way",
                    "reason": str(row.get("reason") or "").strip(),
                    "settled": False,
                    "result": None,
                    "return": 0.0,
                    "profit": 0.0,
                }
            )
    pass_day = bool(skip_reason or decision.get("pass_day") or not selections)
    data_sources = briefing.get("data_sources_used") or ["signal75_local"]
    return {
        "date": date_value,
        "generated_at": now_iso(),
        "analysis_only": True,
        "dashboard_only": True,
        "id": "skin_in_game_v1",
        "model": MODEL,
        "model_mode": "anthropic_api" if not skip_reason else "skipped_no_ai_decision",
        "api_cost_estimate": 0.02 if not skip_reason else 0.0,
        "status": "skipped" if skip_reason else "ok",
        "skip_reason": skip_reason,
        "bankroll_before": bankroll_before,
        "bankroll_after": round(bankroll_before - total_stake, 2),
        "pass_day": pass_day,
        "reasoning": str(decision.get("reasoning") or ("AI decision skipped: " + skip_reason if skip_reason else "")).strip(),
        "what_convinced_me": str(decision.get("what_convinced_me") or "").strip(),
        "what_worried_me": str(decision.get("what_worried_me") or "").strip(),
        "selections": selections,
        "passed_on": decision.get("passed_on") if isinstance(decision.get("passed_on"), list) else [],
        "spotted_outside_signal75": decision.get("spotted_outside_signal75") if isinstance(decision.get("spotted_outside_signal75"), list) else [],
        "data_sources_used": data_sources,
        "briefing_file": f"data/skin_in_game_briefing_{date_value}.json",
        "raw_ai_response": raw_response,
        "settled": False,
        "result": None,
        "return": 0.0,
        "profit": 0.0,
    }


def live_lookup(challenger_payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    lookup = {}
    for pick in (challenger_payload.get("live_system") or {}).get("official_picks") or []:
        lookup[normalise(pick.get("horse"))] = pick
    return lookup


def comparison_for(challenger_payload: Dict[str, Any], selections: List[Dict[str, Any]]) -> Dict[str, Any]:
    live = live_lookup(challenger_payload)
    selected = {normalise(row.get("horse")) for row in selections if row.get("horse")}
    live_names = set(live)
    return {
        "overlap_with_live": len(live_names & selected),
        "only_live": [row.get("horse", "") for row in (challenger_payload.get("live_system") or {}).get("official_picks") or [] if normalise(row.get("horse")) not in selected],
        "only_challenger": [row.get("horse", "") for row in selections if normalise(row.get("horse")) not in live_names],
        "both_picked": [row.get("horse", "") for row in selections if normalise(row.get("horse")) in live_names],
        "same_as_live": live_names == selected and len(live_names) == len(selected),
        "settled": False,
        "live_profit": None,
        "challenger_profit": None,
        "challenger_return": None,
        "delta_vs_live": None,
        "stake_model": "real_ai_variable_bankroll",
        "challenger_stake": round(sum(money(row.get("stake")) for row in selections), 2),
    }


def upsert_challenger_daily(date_value: str, decision: Dict[str, Any]) -> None:
    path = CHALLENGER_DIR / f"challenger_{date_value}.json"
    payload = read_json(path, {})
    if not payload:
        return
    picks = []
    for row in decision.get("selections") or []:
        stake = money(row.get("stake"))
        picks.append(
            {
                "horse": row.get("horse"),
                "course": row.get("course"),
                "time": row.get("time"),
                "odds": row.get("odds"),
                "base_score": None,
                "combined_score": None,
                "live_selected": normalise(row.get("horse")) in live_lookup(payload),
                "challenger_reason": row.get("reason"),
                "stake_total": stake,
                "win_stake": round(stake / 2, 2),
                "place_stake": round(stake / 2, 2),
                "pre_race_evidence": {
                    "reasoning": decision.get("reasoning"),
                    "what_convinced_me": decision.get("what_convinced_me"),
                    "what_worried_me": decision.get("what_worried_me"),
                    "data_sources_used": decision.get("data_sources_used") or [],
                    "model_mode": decision.get("model_mode"),
                },
                "post_race_result": {"settled": False, "position": None, "result": None, "bsp": None, "return": None, "profit": None},
            }
        )
    row = {
        "id": "skin_in_game_v1",
        "name": "AI Punter — Skin In Game",
        "version": "2.0",
        "status": "data_incomplete" if decision.get("status") == "skipped" else "collecting",
        "analysis_only": True,
        "scoringImpact": "none",
        "phase": "real_ai_shadow",
        "data_complete": decision.get("status") != "skipped",
        "data_incomplete_reason": decision.get("skip_reason"),
        "description": "Real AI paper bankroll decision using the Skin In Game briefing.",
        "input_files_used": [decision.get("briefing_file"), "picks.json", f"data/race_comparison_{date_value}.json"],
        "model": decision.get("model"),
        "model_mode": decision.get("model_mode"),
        "bankroll": {
            "starting_bankroll": 100.0,
            "bankroll_before": decision.get("bankroll_before"),
            "stake_selected": round(sum(money(p.get("stake")) for p in decision.get("selections") or []), 2),
            "cash_held_back": round(100.0 - sum(money(p.get("stake")) for p in decision.get("selections") or []), 2),
            "pass_today": decision.get("pass_day"),
            "pass_reason": decision.get("reasoning") if decision.get("pass_day") else None,
        },
        "reasoning": decision.get("reasoning"),
        "what_convinced_me": decision.get("what_convinced_me"),
        "what_worried_me": decision.get("what_worried_me"),
        "passed_on": decision.get("passed_on") or [],
        "spotted_outside_signal75": decision.get("spotted_outside_signal75") or [],
        "picks": picks,
        "comparison": comparison_for(payload, decision.get("selections") or []),
        "sample_warning": "Real AI paper test only. It cannot affect live picks.",
        "days_tested": 0,
        "settled_days": 0,
        "promotion_status": "COLLECTING",
        "manual_approval_required": True,
    }
    challengers = [c for c in payload.get("pre_race_challengers", []) or [] if c.get("id") != "skin_in_game_v1"]
    challengers.append(row)
    payload["pre_race_challengers"] = challengers
    write_json(path, payload)
    dashboard_path = REPO_ROOT / "dashboard" / "data" / "challenger_lab" / f"challenger_{date_value}.json"
    latest_path = REPO_ROOT / "dashboard" / "data" / "challenger_lab" / "challenger_latest.json"
    write_json(dashboard_path, payload)
    write_json(latest_path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real AI Skin In Game challenger decision.")
    parser.add_argument("--date", default=default_date())
    args = parser.parse_args()
    briefing_path = DATA / f"skin_in_game_briefing_{args.date}.json"
    briefing = read_json(briefing_path, {})
    bankroll = latest_bankroll_before(args.date)
    if not briefing:
        decision = sanitize_decision({}, args.date, bankroll, {}, skip_reason=f"Missing briefing file: {briefing_path.relative_to(REPO_ROOT)}")
        raw_text = ""
    else:
        system, user = build_prompts(briefing, bankroll)
        try:
            raw = call_anthropic(system, user)
            raw_text = response_text(raw)
            parsed = parse_ai_json(raw_text)
            decision = sanitize_decision(parsed, args.date, bankroll, briefing, raw_response=raw_text)
        except urllib.error.HTTPError as exc:
            raw_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
            decision = sanitize_decision({}, args.date, bankroll, briefing, raw_response=raw_text, skip_reason=f"Anthropic API HTTP error: {exc.code}")
        except Exception as exc:
            raw_text = str(exc)
            decision = sanitize_decision({}, args.date, bankroll, briefing, raw_response=raw_text, skip_reason=str(exc))

    out = CHALLENGER_DIR / f"skin_in_game_{args.date}.json"
    write_json(out, decision)
    upsert_challenger_daily(args.date, decision)
    print(f"Skin In Game decision written: {out.relative_to(REPO_ROOT)}")
    print(f"  status: {decision.get('status')}")
    print(f"  model: {decision.get('model')} ({decision.get('model_mode')})")
    print(f"  pass_day: {decision.get('pass_day')}")
    print(f"  selections: {len(decision.get('selections') or [])}")
    print(f"  stake: £{sum(money(row.get('stake')) for row in decision.get('selections') or []):.2f}")
    print("AI reasoning:")
    print(decision.get("reasoning") or "")
    if decision.get("raw_ai_response"):
        print("Raw AI response:")
        print(decision.get("raw_ai_response"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
