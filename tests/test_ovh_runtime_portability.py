from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_live_pipeline_scripts_do_not_assume_mac_home_checkout():
    active_scripts = (
        "scripts/generate-picks-betfair.py",
        "scripts/update-results-mac.py",
        "scripts/self-learning-update.py",
        "scripts/scenario-roi-review.py",
    )
    forbidden = (
        "/Users/johnhowlett/Signal75",
        'expanduser("~/Signal75")',
        "expanduser('~/Signal75')",
    )

    for relative_path in active_scripts:
        content = source(relative_path)
        for fragment in forbidden:
            assert fragment not in content, f"{relative_path} contains {fragment}"


def test_live_pipeline_children_use_current_python_environment():
    updater = source("scripts/update-results-mac.py")
    learning = source("scripts/self-learning-update.py")
    generator = source("scripts/generate-picks-betfair.py")

    assert "/usr/bin/python3" not in updater
    assert "/usr/bin/python3" not in learning
    assert "/usr/bin/python3" not in generator
    assert "PYTHON_BIN = sys.executable" in updater
    assert "PYTHON_BIN = sys.executable" in learning
    assert "[sys.executable, 'scripts/validate_system_integrity.py']" in generator


def test_scenario_review_resolves_repo_from_its_script_location():
    content = source("scripts/scenario-roi-review.py")
    assert "REPO = Path(__file__).resolve().parents[1]" in content


def test_shadow_retention_can_remove_read_only_verified_artifacts():
    content = source("scripts/prune-ovh-shadow-artifacts.py")
    assert "for q in [p,*p.rglob('*')]" in content
    assert "st_mode | 0o700" in content
