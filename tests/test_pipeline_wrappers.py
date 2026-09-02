import importlib.util
import sys

from conftest_helpers import REPO_ROOT


def load_script(module_name, path):
    module_path = REPO_ROOT / path
    scripts_path = str(REPO_ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_morning_pipeline_order(monkeypatch, tmp_path):
    morning = load_script("run_morning_pipeline", "scripts/run_morning_pipeline.py")
    calls = []

    monkeypatch.setattr(morning, "LOCK_DIR", tmp_path / "morning.lock")
    monkeypatch.setattr(morning, "LOG_DIR", tmp_path)
    monkeypatch.setattr(morning, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_morning_pipeline.py", "--date", "2026-08-10", "--dry-run"])

    def fake_run(name, command, **kwargs):
        calls.append((name, command, kwargs.get("allow_warning_exit")))
        return {"name": name, "status": "would_run", "command": command}

    monkeypatch.setattr(morning, "run_command", fake_run)

    assert morning.main() == 0
    assert [call[0] for call in calls] == [
        "Dashboard automation reset",
        "System configuration check",
        "Regression tests",
        "Master preflight before picks",
        "Official pick generation",
        "Selection diagnostics",
        "Rich form daily racecard sync",
        "Pick quality audit",
        "Field graph intelligence",
        "Challenger Lab rebuild",
        "Challenger summary rebuild",
        "Dashboard publish",
        "Master preflight after picks",
    ]
    assert calls[3][2] == [1]
    assert calls[3][1][1] == "scripts/master-preflight.py"
    assert calls[4][1][1] == "scripts/generate-picks-betfair.py"


def test_morning_pipeline_stops_on_integrity_failure(monkeypatch, tmp_path):
    morning = load_script("run_morning_pipeline_stop", "scripts/run_morning_pipeline.py")
    calls = []

    monkeypatch.setattr(morning, "LOCK_DIR", tmp_path / "morning.lock")
    monkeypatch.setattr(morning, "LOG_DIR", tmp_path)
    monkeypatch.setattr(morning, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_morning_pipeline.py", "--date", "2026-08-10"])

    def fake_run(name, command, **kwargs):
        calls.append(name)
        if name == "Master preflight before picks":
            return {"name": name, "status": "failed", "command": command}
        return {"name": name, "status": "ok", "command": command}

    monkeypatch.setattr(morning, "run_command", fake_run)

    assert morning.main() == 1
    assert calls == [
        "Dashboard automation reset",
        "System configuration check",
        "Regression tests",
        "Master preflight before picks",
    ]


def test_morning_pipeline_stops_on_quality_audit_failure(monkeypatch, tmp_path):
    morning = load_script("run_morning_pipeline_quality_stop", "scripts/run_morning_pipeline.py")
    calls = []

    monkeypatch.setattr(morning, "LOCK_DIR", tmp_path / "morning.lock")
    monkeypatch.setattr(morning, "LOG_DIR", tmp_path)
    monkeypatch.setattr(morning, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_morning_pipeline.py", "--date", "2026-08-10", "--skip-tests"])

    def fake_run(name, command, **kwargs):
        calls.append(name)
        if name == "Pick quality audit":
            return {"name": name, "status": "failed", "command": command}
        return {"name": name, "status": "ok", "command": command}

    monkeypatch.setattr(morning, "run_command", fake_run)

    assert morning.main() == 1
    assert calls == [
        "Dashboard automation reset",
        "System configuration check",
        "Master preflight before picks",
        "Official pick generation",
        "Selection diagnostics",
        "Rich form daily racecard sync",
        "Pick quality audit",
    ]


def test_nightly_pipeline_order(monkeypatch, tmp_path):
    nightly = load_script("run_nightly_pipeline", "scripts/run_nightly_pipeline.py")
    calls = []

    monkeypatch.setattr(nightly, "LOCK_DIR", tmp_path / "nightly.lock")
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path)
    monkeypatch.setattr(nightly, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_nightly_pipeline.py", "--date", "2026-08-10", "--dry-run"])

    def fake_run(name, command, **kwargs):
        calls.append((name, command, kwargs.get("allow_warning_exit")))
        return {"name": name, "status": "would_run", "command": command}

    monkeypatch.setattr(nightly, "run_command", fake_run)

    assert nightly.main() == 0
    assert [call[0] for call in calls] == [
        "Official result settlement",
        "Performance and ROI proof",
        "Self-learning update",
        "Master post-race preflight",
        "Dashboard publish",
    ]
    assert calls[0][1][1] == "scripts/update-results-mac.py"
    assert calls[1][1][1] == "scripts/generate-performance.py"
    assert calls[2][1][1] == "scripts/self-learning-update.py"
    assert calls[3][2] == [1]


def test_nightly_pipeline_stops_when_master_preflight_fails(monkeypatch, tmp_path):
    nightly = load_script("run_nightly_pipeline_stop", "scripts/run_nightly_pipeline.py")
    calls = []

    monkeypatch.setattr(nightly, "LOCK_DIR", tmp_path / "nightly.lock")
    monkeypatch.setattr(nightly, "LOG_DIR", tmp_path)
    monkeypatch.setattr(nightly, "DATA", tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_nightly_pipeline.py", "--date", "2026-08-10"])

    def fake_run(name, command, **kwargs):
        calls.append(name)
        status = "failed" if name == "Master post-race preflight" else "ok"
        return {"name": name, "status": status, "command": command}

    monkeypatch.setattr(nightly, "run_command", fake_run)

    assert nightly.main() == 1
    assert calls[-1] == "Master post-race preflight"
    assert "Dashboard publish" not in calls


def test_finish_report_marks_warning_as_degraded(tmp_path):
    runner = load_script("pipeline_runner_degraded", "scripts/pipeline_runner.py")
    report = tmp_path / "report.json"
    status = runner.finish_report(
        name="nightly",
        date_text="2026-08-30",
        started_at="2026-08-30T23:10:00+01:00",
        steps=[{"name": "Self-learning update", "status": "warning"}],
        report_path=report,
    )

    payload = __import__("json").loads(report.read_text())
    assert status == 1
    assert payload["status"] == "degraded"
    assert payload["warningSteps"] == ["Self-learning update"]


def test_historical_learning_reuses_dated_race_memory():
    source = (REPO_ROOT / "scripts" / "self-learning-update.py").read_text(encoding="utf-8")

    assert 'race_memory_file.exists() and load_json(RUNNER_CACHE, {}).get("date") != date' in source
    assert '"status": "not_applicable"' in source
