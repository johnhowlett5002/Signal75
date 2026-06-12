#!/usr/bin/env python3
"""Shared helpers for Signal 75 analysis-only learning scripts."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
COMBINED_DIR = DATA_DIR / "combined_learning"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def pct(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def combined_path(date: str) -> Path:
    return COMBINED_DIR / f"combined_learning_{date}.json"


def combined_rows(date: str) -> List[Dict[str, Any]]:
    payload = load_json(combined_path(date), {})
    return payload.get("records", []) if isinstance(payload, dict) else []


def available_combined_dates() -> List[str]:
    dates = []
    for path in COMBINED_DIR.glob("combined_learning_*.json"):
        stem = path.stem.replace("combined_learning_", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stem):
            dates.append(stem)
    return sorted(set(dates))


def known_result(row: Dict[str, Any]) -> bool:
    result = str(row.get("result") or "").upper()
    return result not in {"", "UNKNOWN", "PENDING", "VOID"}


def placed(row: Dict[str, Any]) -> bool:
    return bool(row.get("placed")) or str(row.get("result") or "").upper() in {"WON", "PLACED"}


def won(row: Dict[str, Any]) -> bool:
    return bool(row.get("won")) or str(row.get("result") or "").upper() == "WON" or safe_int(row.get("position")) == 1


def score_band(score: Any) -> str:
    value = safe_float(score)
    if value is None:
        return "missing"
    if value < 65:
        return "below_65"
    for low, high in ((65, 69), (70, 74), (75, 79), (80, 84), (85, 89), (90, 94), (95, 100)):
        if low <= value <= high:
            return f"{low}-{high}"
    return "95-100" if value > 100 else "missing"


def scored_known_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if known_result(row) and safe_float(row.get("signal_score")) is not None]
