import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    path = ROOT / "scripts" / "data-freshness-status.py"
    spec = importlib.util.spec_from_file_location("data_freshness_portability", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_inaccessible_mac_archive_is_reported_as_unavailable(monkeypatch, tmp_path):
    module = load_module()
    original_exists = Path.exists

    def guarded_exists(path):
        if "archive (1)" in str(path):
            raise PermissionError(path)
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", guarded_exists)
    status = module.source_archive_latest(tmp_path / "archive (1)")

    assert status["resultArchiveExists"] is False
    assert status["sourceLatestResultDate"] is None
    assert status["sourceRacecardFiles"] == 0
