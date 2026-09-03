import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_runtime_snapshot_module():
    path = REPO_ROOT / "scripts" / "sync-ovh-runtime-snapshot.py"
    spec = importlib.util.spec_from_file_location("sync_ovh_runtime_snapshot", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_runtime_snapshot_contains_every_live_memory_input():
    module = load_runtime_snapshot_module()
    assert {path.name for path in module.ARTIFACTS.values()} == {
        "head_to_head_master.jsonl",
        "head_to_head_profiles.json",
        "historic_rival_profiles.json",
        "field_relationship_profiles.json",
    }


def test_runtime_snapshot_is_immutable_and_unpromoted():
    source = (REPO_ROOT / "scripts" / "sync-ovh-runtime-snapshot.py").read_text(encoding="utf-8")
    assert "ovh-unpromoted-read-only-runtime-snapshot" in source
    assert "sha256sum" in source
    assert "chmod 0440" in source
    assert "systemctl" not in source
    assert "crontab" not in source
    assert "publish" not in source
