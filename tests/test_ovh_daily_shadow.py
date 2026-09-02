from pathlib import Path
import plistlib


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_preparation_is_atomic_and_uses_all_databases():
    source = (ROOT / "scripts" / "prepare-ovh-shadow-candidate.sh").read_text(encoding="utf-8")

    assert "signal75-ovh-candidate.lock" in source
    assert source.count("--database ") == 3
    assert "--database combined_learning" in source
    assert "--database form_history" in source
    assert "--database signal75_history" in source
    assert 'mv "$temporary" "$CURRENT_FILE"' in source


def test_daily_shadow_refuses_stale_mac_picks_and_never_publishes():
    source = (ROOT / "scripts" / "run-ovh-daily-shadow.sh").read_text(encoding="utf-8")

    assert "signal75-ovh-daily-shadow.lock" in source
    assert 'payload.get("date") != expected' in source
    assert "run-ovh-real-feed-shadow.sh" in source
    assert "publish-live-files.py" not in source
    assert '"livePublishing": "disabled"' in source
    assert '"macRemainsPrimary": True' in source


def test_launch_agent_runs_after_morning_with_guarded_watchdog_retry():
    path = ROOT / "deploy" / "launchd" / "co.signal75.ovh-shadow.plist"
    with path.open("rb") as handle:
        payload = plistlib.load(handle)

    assert payload["Label"] == "co.signal75.ovh-shadow"
    assert payload["StartCalendarInterval"] == [
        {"Hour": 10, "Minute": 40},
        {"Hour": 11, "Minute": 15},
    ]
    assert payload["ProgramArguments"][-1].endswith("run-ovh-daily-shadow.sh")
    assert "RunAtLoad" not in payload
    assert "KeepAlive" not in payload


def test_daily_shadow_skips_retry_after_comparable_result():
    source = (ROOT / "scripts" / "run-ovh-daily-shadow.sh").read_text(encoding="utf-8")

    assert 'payload.get("status") in {"match", "different"}' in source
    assert "comparable shadow already completed" in source
