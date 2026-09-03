import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prune-ovh-shadow-artifacts.py"
SPEC = importlib.util.spec_from_file_location("prune_ovh_shadow_artifacts", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_retention_deletes_only_old_paired_shadow_artifacts():
    candidates = [f"candidate-shadow-2026080{day}-100000" for day in range(1, 8)] + ["candidate-live"]
    snapshots = [f"shadow-input-2026080{day}-100000" for day in range(1, 8)] + ["20260831-0908"]
    runtime_snapshots = [f"runtime-input-2026080{day}-100000" for day in range(1, 8)]

    old_candidates, old_snapshots, old_runtime = MODULE.paired_deletions(
        candidates, snapshots, runtime_snapshots, keep=5
    )

    assert old_candidates == [
        "candidate-shadow-20260801-100000",
        "candidate-shadow-20260802-100000",
    ]
    assert old_snapshots == [
        "shadow-input-20260801-100000",
        "shadow-input-20260802-100000",
    ]
    assert old_runtime == [
        "runtime-input-20260801-100000",
        "runtime-input-20260802-100000",
    ]
    assert "candidate-live" not in old_candidates
    assert "20260831-0908" not in old_snapshots


def test_retention_ignores_orphan_and_non_shadow_snapshots():
    candidates = ["candidate-shadow-20260807-100000"]
    snapshots = ["shadow-input-20260801-100000", "20260831-0908"]

    assert MODULE.paired_deletions(candidates, snapshots, [], keep=1) == ([], [], [])


def test_remote_delete_rejects_name_outside_strict_pattern():
    with pytest.raises(ValueError, match="unsafe"):
        MODULE.delete_remote("unused", "/srv/signal75/candidates", ["../app"], MODULE.CANDIDATE_RE)


def test_keep_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        MODULE.retained_and_old([], MODULE.RUN_RE, keep=0)
