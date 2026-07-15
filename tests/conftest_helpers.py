import json
import os
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_json(path):
    full = REPO_ROOT / path
    if not full.exists():
        return {}
    with open(full, encoding="utf-8") as f:
        return json.load(f)


def load_fixture(name):
    path = FIXTURES / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def today_str():
    return date.today().strftime("%Y-%m-%d")


def daily_health_enabled():
    return os.environ.get("SIGNAL75_DAILY_HEALTH") == "1"
