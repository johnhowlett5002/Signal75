import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = REPO_ROOT / "scripts" / "generate-picks-betfair.py"


def test_generator_shadow_mode_is_environment_controlled_and_proof_safe():
    source = GENERATOR.read_text(encoding="utf-8")
    assert "SIGNAL75_TEST_MODE" in source
    assert source.count("with open(picks_output_path(), 'w')") >= 2
    assert "scoring_engine_module.ROI_TABLES" in source
    assert 'ODDS_SOURCE    = "betfair_exchange_morning"' in source


def test_generator_shadow_mode_resolves_test_output_without_running_main():
    command = [
        sys.executable,
        "-c",
        (
            "import runpy; "
            "d=runpy.run_path('scripts/generate-picks-betfair.py', run_name='shadow_import'); "
            "print(d['TEST_MODE']); print(d['picks_output_path']())"
        ),
    ]
    env = os.environ.copy()
    env["SIGNAL75_TEST_MODE"] = "1"
    result = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=True)
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "True"
    assert lines[1].endswith("/data/picks_test.json")
