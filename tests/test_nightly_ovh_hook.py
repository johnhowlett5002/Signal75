from pathlib import Path

import pytest


WRAPPER = Path.home() / "signal75-run-self-learning.sh"


@pytest.mark.skipif(not WRAPPER.exists(), reason="Mac LaunchAgent wrapper is not installed")
def test_ovh_comparison_runs_only_after_successful_nightly_learning():
    source = WRAPPER.read_text(encoding="utf-8")

    pipeline = source.index('PIPELINE_STATUS=$?')
    failure_branch = source.index('if [ $PIPELINE_STATUS -ne 0 ]; then')
    success_branch = source.index('else\n  echo "$LOG_PREFIX Nightly learning completed"')
    preview = source.index('if "$REPO/scripts/sync-ovh-dashboard-preview.sh"; then')
    audit = source.index('if "$REPO/scripts/compare-ovh-state.sh"; then')

    assert pipeline < failure_branch < success_branch < preview < audit
    assert "sync-ovh-dashboard-preview.sh" not in source[failure_branch:success_branch]
    assert source.count('sync-ovh-dashboard-preview.sh') == 1
    assert source.count('compare-ovh-state.sh') == 1
    assert 'record deployment "OVH private preview and state comparison" failed' in source


def test_ovh_comparison_script_has_overlap_lock():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "scripts" / "compare-ovh-state.sh").read_text(encoding="utf-8")

    assert "signal75-ovh-state-audit.lock" in source
    assert 'if ! mkdir "$LOCK_DIR"' in source
    assert "trap cleanup EXIT" in source


def test_ovh_preview_sync_is_versioned_and_does_not_run_pipelines():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "scripts" / "sync-ovh-dashboard-preview.sh").read_text(encoding="utf-8")

    assert "signal75-preview-releases" in source
    assert "preview-upload-" in source
    assert "mv -Tf" in source
    assert "signal75-ovh-preview-sync.lock" in source
    assert "generate-picks" not in source
    assert "run_nightly_pipeline" not in source
    assert "ANTHROPIC" not in source
