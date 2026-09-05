import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = REPO_ROOT / "scripts" / "run-ovh-offline-replay.py"
    spec = importlib.util.spec_from_file_location("run_ovh_offline_replay", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_digest_detects_file_changes(tmp_path):
    module = load_script()
    path = tmp_path / "proof.json"
    path.write_text("before", encoding="utf-8")
    before = module.digest(path)
    path.write_text("after", encoding="utf-8")
    assert module.digest(path) != before


def test_replay_has_no_live_generation_or_publish_command():
    source = (REPO_ROOT / "scripts" / "run-ovh-offline-replay.py").read_text(encoding="utf-8")
    assert '"scripts/generate-picks-betfair.py"' not in source
    assert '"scripts/publish-live-files.py"' not in source
    assert '"Official pick generation",\n                "status": "skipped_offline"' in source


def test_replayed_scripts_resolve_their_repository_from_file_location():
    for filename in ("generate-performance.py", "selection-diagnostics.py"):
        source = (REPO_ROOT / "scripts" / filename).read_text(encoding="utf-8")
        assert 'expanduser("~/Signal75")' not in source
        assert "os.path.abspath(__file__)" in source

    diagnostics = (REPO_ROOT / "scripts" / "selection-diagnostics.py").read_text(encoding="utf-8")
    assert 'scoring_engine_module.ROI_TABLES = os.path.join(DATA_DIR, "roi_tables.json")' in diagnostics
