import importlib.util
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_readiness_module():
    path = ROOT / "scripts" / "check-ovh-cutover-readiness.py"
    spec = importlib.util.spec_from_file_location("ovh_cutover_readiness", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def build_release(root: Path, module) -> None:
    for relative in module.DATABASES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE proof (value TEXT)")
    for relative in module.RUNTIME_FILES:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test\n", encoding="utf-8")
    for relative in (
        "scripts/run-ovh-live-stage.py",
        "scripts/generate-picks-betfair.py",
        "scripts/update-results-mac.py",
        "scripts/self-learning-update.py",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# test\n", encoding="utf-8")


def test_readiness_accepts_writable_copies_with_disabled_timers(tmp_path, monkeypatch):
    module = load_readiness_module()
    build_release(tmp_path, module)
    monkeypatch.setattr(module, "systemctl", lambda action, unit: "disabled" if action == "is-enabled" else "inactive")
    original_exists = module.Path.exists

    def safe_exists(path):
        if str(path) in {"/srv/signal75/live", "/etc/signal75/live-pipeline-enabled"}:
            return False
        return original_exists(path)

    monkeypatch.setattr(module.Path, "exists", safe_exists)
    report = module.audit(tmp_path)
    assert report["status"] == "ready_for_controlled_cutover"
    assert report["production_activated"] is False
    assert all(
        details["write_probe"] == "ok"
        for details in report["checks"]["databases"].values()
    )


def test_readiness_rejects_database_symlink(tmp_path, monkeypatch):
    module = load_readiness_module()
    build_release(tmp_path, module)
    target = tmp_path / "source.sqlite"
    target.write_bytes((tmp_path / module.DATABASES[0]).read_bytes())
    path = tmp_path / module.DATABASES[0]
    path.unlink()
    path.symlink_to(target)
    monkeypatch.setattr(module, "systemctl", lambda action, unit: "disabled" if action == "is-enabled" else "inactive")
    monkeypatch.setattr(module.Path, "exists", lambda path: False if str(path) in {"/srv/signal75/live", "/etc/signal75/live-pipeline-enabled"} else Path.is_file(path) or Path.is_dir(path))
    report = module.audit(tmp_path)
    assert report["status"] == "blocked"
    assert any("writable release copy" in item for item in report["failures"])


def test_stage_script_never_creates_or_enables_production_live_path():
    source = (ROOT / "scripts" / "stage-ovh-prelive-release.sh").read_text(encoding="utf-8")
    assert "systemctl enable" not in source
    assert "live-pipeline-enabled" not in source
    assert "ln -sfn 'releases/$RELEASE_ID' '$REMOTE_ROOT/.current.new'" in source
    assert r'\"\$stage\" --dry-run' in source
    assert r'\"\$previous\"' in source
    assert "-name '*.sqlite-wal'" in source
    assert "-name '*.sqlite-shm'" in source


def test_prelive_switch_rehearsal_restores_original_release(tmp_path):
    path = ROOT / "scripts" / "rehearse-ovh-release-switch.py"
    spec = importlib.util.spec_from_file_location("ovh_release_switch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)

    release = tmp_path / "releases" / "release-a"
    release.mkdir(parents=True)
    (tmp_path / "current").symlink_to("releases/release-a")
    report = module.rehearse(tmp_path)

    assert report["probe_switch"] is True
    assert report["rollback"] is True
    assert report["production_changed"] is False
    assert (tmp_path / "current").resolve() == release.resolve()
    assert not list((tmp_path / "releases").glob("rollback-probe-*"))
