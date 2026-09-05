import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_publisher():
    path = ROOT / "scripts" / "publish-live-files.py"
    spec = importlib.util.spec_from_file_location("publish_live_files", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_late_market_publish_has_a_narrow_file_allowlist(tmp_path):
    publisher = load_publisher()
    source = (ROOT / "scripts" / "publish-live-files.py").read_text(encoding="utf-8")
    race_date = "2026-09-03"
    relative = Path("data") / f"late_value_shadow_{race_date}.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"date": race_date, "status": "shadow_only_not_live"}))

    publisher.validate_source(tmp_path, "late-market", race_date)

    assert publisher.optional_paths("late-market", race_date) == [str(relative)]
    assert "SIGNAL75_PUBLISH_GIT_REPO" in source
    assert 'git_repo = Path(args.git_repo).resolve()' in source
    assert '["git", "-C", str(git_repo), "fetch"' in source


def test_result_updater_delegates_git_changes_to_clean_publisher():
    source = (ROOT / "scripts" / "update-results-mac.py").read_text(encoding="utf-8")
    function = source.split("def push_to_github(race_date, picks):", 1)[1].split("\ndef main():", 1)[0]

    assert "publish-live-files.py" in function
    assert '"--kind",\n        "results"' in function
    assert '["git"' not in function
