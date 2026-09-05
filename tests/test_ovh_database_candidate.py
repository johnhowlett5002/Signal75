import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_candidate_builder_has_no_activation_or_pipeline_hooks():
    path = REPO_ROOT / "scripts" / "build-ovh-database-candidate.py"
    source = path.read_text(encoding="utf-8")

    assert '"promoted": False' in source
    assert "/srv/signal75/candidates" in source
    assert "/srv/signal75/database-current" not in source
    assert "crontab" not in source
    assert "systemctl" not in source
    assert "generate-picks" not in source
    assert "ANTHROPIC" not in source


def test_candidate_paths_match_signal75_database_layout():
    path = REPO_ROOT / "scripts" / "build-ovh-database-candidate.py"
    spec = importlib.util.spec_from_file_location("build_ovh_candidate", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    assert module.DATABASES["form_history"][1] == "data/horse_intelligence/form_history.sqlite"
    assert module.DATABASES["signal75_history"][1] == "data/horse_intelligence/signal75_history.sqlite"
    assert module.DATABASES["combined_learning"][1] == "data/combined_learning/signal75_learning.sqlite"


def test_shadow_workspace_builder_cannot_activate_or_copy_credentials():
    source = (REPO_ROOT / "scripts" / "build-ovh-shadow-workspace.sh").read_text(encoding="utf-8")

    assert "/srv/signal75/shadow-runs" in source
    assert "--exclude '.env*'" in source
    assert "--exclude '*.sqlite'" in source
    assert "/srv/signal75/database-current" not in source
    assert "crontab" not in source
    assert "systemctl" not in source
    assert "generate-picks" not in source
    assert "ANTHROPIC" not in source
    assert '"data/today_runners.json"' in source
    assert '"data/roi_tables.json"' in source
    assert "head_to_head_master.jsonl head_to_head_profiles.json" in source
    assert "historic_rival_profiles.json field_relationship_profiles.json" in source
    assert 'test -L \\"\\$source\\"' in source
    assert "-name '????-??-??.json'" in source
    assert "publish_dashboard_data.py' --date '$DATE_VALUE'" in source


def test_candidate_requires_verified_runtime_snapshot():
    candidate = (REPO_ROOT / "scripts" / "build-ovh-database-candidate.py").read_text(encoding="utf-8")
    prepare = (REPO_ROOT / "scripts" / "prepare-ovh-shadow-candidate.sh").read_text(encoding="utf-8")

    assert "A verified runtime snapshot is required" in candidate
    assert 'parser.add_argument("--runtime-snapshot", required=True' in candidate
    assert "sync-ovh-runtime-snapshot.py" in prepare
    assert '--runtime-snapshot "$RUNTIME_SNAPSHOT_ID"' in prepare
