import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_reporter():
    path = REPO_ROOT / "scripts" / "write-ovh-real-feed-report.py"
    spec = importlib.util.spec_from_file_location("ovh_real_feed_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_real_feed_runner_is_test_only_and_has_no_scheduler_or_secret_file():
    source = (REPO_ROOT / "scripts" / "run-ovh-real-feed-shadow.sh").read_text(encoding="utf-8")
    assert "SIGNAL75_TEST_MODE=1" in source
    assert "unset ANTHROPIC_API_KEY" in source
    assert "publish-live-files.py" not in source
    assert "systemctl" not in source
    assert "crontab" not in source
    assert ".env" not in source.replace("test ! -e .env", "")
    assert "security find-generic-password" in source
    assert "SIGNAL75_FROZEN_FEED_PATH" in source
    assert "picks_test_frozen.json" in source
    assert "mac-vs-ovh-frozen-current.json" in source


def test_shadow_workspace_uses_current_mac_scripts_without_updating_ovh_app():
    builder = (REPO_ROOT / "scripts" / "build-ovh-shadow-workspace.sh").read_text(encoding="utf-8")
    runner = (REPO_ROOT / "scripts" / "run-ovh-real-feed-shadow.sh").read_text(encoding="utf-8")

    assert '"$BASE_DIR/scripts/" "$REMOTE_HOST:$STAGE/scripts/"' in builder
    assert "--delete" in builder
    assert "/srv/signal75/app/scripts/generate-picks-betfair.py" not in runner


def test_shadow_workspace_includes_every_live_rival_memory_input():
    builder = (REPO_ROOT / "scripts" / "build-ovh-shadow-workspace.sh").read_text(encoding="utf-8")
    required = (
        "head_to_head_master.jsonl",
        "head_to_head_profiles.json",
        "historic_rival_profiles.json",
        "field_relationship_profiles.json",
    )
    for filename in required:
        assert filename in builder
    assert 'test -L \\"\\$source\\"' in builder
    assert '"data/consensus_overlay_$DATE_VALUE.json"' in builder
    assert '"data/script_tipster_overlay_$DATE_VALUE.json"' in builder
    assert '"data/tipster_intelligence/tipster_intelligence_$DATE_VALUE.json"' in builder


def test_report_helpers_extract_counts_and_hash_changes(tmp_path):
    module = load_reporter()
    text = "  30 UK WIN markets\n  241 runners across 30 races\n"
    assert module.integer_from_log(text, r"^\s*(\d+) UK WIN markets") == 30
    assert module.integer_from_log(text, r"^\s*(\d+) runners across") == 241
    path = tmp_path / "picks.json"
    path.write_text(json.dumps({"date": "2026-09-01"}), encoding="utf-8")
    before = module.digest(path)
    path.write_text("{}", encoding="utf-8")
    assert module.digest(path) != before


def test_comparison_marks_zero_market_trial_not_comparable(tmp_path):
    path = REPO_ROOT / "scripts" / "compare-ovh-shadow-picks.py"
    spec = importlib.util.spec_from_file_location("compare_ovh_shadow_picks", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    assert module.selections({"flat": [], "jumps": []}) == []
    assert module.horse_key("Horse's Name") == "HORSESNAME"
    mac = {"date": "2026-09-01", "generatedAt": "2026-09-01T09:42:00+00:00"}
    ovh = {"date": "2026-09-01", "generatedAt": "2026-09-01T09:47:00+00:00"}
    reasons = module.comparability_reasons(mac, ovh, {"status": "ok", "markets": 0})
    assert reasons == ["OVH trial had no markets"]


def test_comparison_rejects_late_same_day_rerun():
    path = REPO_ROOT / "scripts" / "compare-ovh-shadow-picks.py"
    spec = importlib.util.spec_from_file_location("compare_ovh_shadow_picks_late", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    mac = {"date": "2026-09-01", "generatedAt": "2026-09-01T09:42:00+00:00"}
    ovh = {"date": "2026-09-01", "generatedAt": "2026-09-01T13:20:00+00:00"}
    reasons = module.comparability_reasons(mac, ovh, {"status": "ok", "markets": 28})
    assert reasons == ["generation times differ by 218.0 minutes; maximum is 20"]
    assert module.comparability_reasons(
        mac,
        ovh,
        {"status": "ok", "markets": 28},
        require_time_proximity=False,
    ) == []
