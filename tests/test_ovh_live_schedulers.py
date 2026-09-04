import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-ovh-live-stage.py"
SPEC = importlib.util.spec_from_file_location("run_ovh_live_stage", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_live_stage_requires_both_activation_guards(tmp_path, monkeypatch):
    marker = tmp_path / "enabled"
    with pytest.raises(RuntimeError, match="not explicitly enabled"):
        MODULE.assert_activated(marker)
    marker.write_text(MODULE.ENABLE_TOKEN + "\n")
    monkeypatch.delenv("SIGNAL75_OVH_ROLE", raising=False)
    with pytest.raises(RuntimeError, match="not primary"):
        MODULE.assert_activated(marker)
    monkeypatch.setenv("SIGNAL75_OVH_ROLE", "primary")
    MODULE.assert_activated(marker)


def test_stage_commands_preserve_pipeline_order():
    morning = MODULE.commands("morning", "2026-09-01")
    results = MODULE.commands("results", "2026-09-01")
    learning = MODULE.commands("learning", "2026-09-01")
    assert "run_morning_pipeline.py" in morning[0][1]
    assert morning[0][-1] == "--publish-live"
    assert [Path(command[1]).name for command in results] == [
        "update-results-mac.py",
        "generate-performance.py",
        "master-preflight.py",
        "publish-live-files.py",
    ]
    assert "run_nightly_pipeline.py" in learning[0][1]


def test_systemd_units_use_shared_lock_guards_and_london_time():
    service = (ROOT / "deploy/systemd/signal75-live@.service").read_text()
    assert "ConditionPathExists=/etc/signal75/live-pipeline-enabled" in service
    assert "SIGNAL75_OVH_ROLE=primary" in service
    assert "/run/lock/signal75-live-pipeline.lock" in service
    assert "OnFailure=signal75-live-failure@%i.service" in service
    for name in ("morning", "results", "learning"):
        timer = (ROOT / f"deploy/systemd/signal75-{name}.timer").read_text()
        assert "Europe/London" in timer


def test_results_schedule_matches_mac_refresh_times():
    timer = (ROOT / "deploy/systemd/signal75-results.timer").read_text()
    for time in ("19:00:00", "20:30:00", "21:30:00", "22:15:00"):
        assert time in timer


def test_installer_refuses_existing_activation_and_enables_only_health():
    installer = (ROOT / "scripts/install-ovh-disabled-schedulers.sh").read_text()
    assert "live-pipeline-enabled" in installer
    assert "production.env" in installer
    assert "enable --now ovh-readonly-health.timer" in installer
    assert "enable --now signal75" not in installer
    assert "systemctl is-enabled" in installer
    assert "systemctl is-active" in installer
