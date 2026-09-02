import importlib.util
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("rich_context_test", ROOT / "scripts" / "rich_context.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE form_results (
            date TEXT, course TEXT, race_id TEXT, off_time TEXT, race_name TEXT,
            race_type TEXT, race_class TEXT, distance TEXT, going TEXT, runners INTEGER,
            position INTEGER, draw INTEGER, horse_name TEXT, horse_key TEXT,
            weight_lbs INTEGER, jockey TEXT, trainer TEXT, official_rating INTEGER,
            rpr INTEGER, topspeed INTEGER
        );
        CREATE TABLE racecards (
            date TEXT, course TEXT, horse_name TEXT, horse_key TEXT, distance TEXT,
            going TEXT, draw INTEGER, weight_lbs INTEGER, jockey TEXT, trainer TEXT,
            rpr INTEGER, trainer_rtf INTEGER
        );
        CREATE INDEX idx_form_horse_date ON form_results (horse_key, date);
        CREATE INDEX idx_card_horse_date ON racecards (horse_key, date);
        """
    )
    rows = [
        ("2026-08-01", "Ripon", "1", "12:00", "Class 5 Handicap", "Flat", "Class 5", "1m2f", "Good", 10, 1, 2, "Merry (GB)", "MERRYGB", 130, "J One", "T One", 70, 80, 60),
        ("2026-08-02", "Ripon", "2", "12:30", "Other", "Flat", "Class 5", "1m2f", "Good", 10, 1, 3, "Merry Blacksmith (IRE)", "MERRYBLACKSMITHIRE", 130, "J Two", "T Two", 70, 80, 60),
        ("2026-09-01", "Ripon", "3", "13:00", "Future", "Flat", "Class 4", "1m2f", "Good", 10, 1, 1, "Merry (GB)", "MERRYGB", 130, "J One", "T One", 70, 90, 70),
    ]
    connection.executemany("INSERT INTO form_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    connection.execute(
        "INSERT INTO racecards VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-09-01", "Ripon 1st Sep", "Merry", "MERRY", "1m2f", "Good", 4, 132, "J One", "T One", 88, 75),
    )
    connection.commit()
    connection.close()


def test_country_suffix_match_excludes_prefix_collisions_and_future_rows(tmp_path):
    module = load_module()
    database = tmp_path / "form.sqlite"
    seed_database(database)

    rows = module.historical_rows(database, "Merry", "2026-09-01")

    assert len(rows) == 1
    assert rows[0]["horse_name"] == "Merry (GB)"
    assert rows[0]["date"] == "2026-08-01"


def test_context_uses_real_history_and_current_card(tmp_path):
    module = load_module()
    database = tmp_path / "form.sqlite"
    seed_database(database)

    context = module.build_runner_context(
        database,
        {"name": "Merry", "venue": "Ripon", "race_name": "1m2f Hcap"},
        "2026-09-01",
    )

    assert context["historyRuns"] == 1
    assert context["courseRuns"] == 1
    assert context["courseWins"] == 1
    assert context["distanceRuns"] == 1
    assert context["distanceWins"] == 1
    assert context["goingRuns"] == 1
    assert context["goingWins"] == 1
    assert context["draw"] == 4
    assert context["weightLbs"] == 132
    assert context["rpr"] == 88
    assert context["statuses"]["course"] == "proven"


def test_unknown_going_stays_unknown_not_zero(tmp_path):
    module = load_module()
    database = tmp_path / "form.sqlite"
    seed_database(database)
    connection = sqlite3.connect(database)
    connection.execute("UPDATE racecards SET going = ''")
    connection.commit()
    connection.close()

    context = module.build_runner_context(
        database,
        {"name": "Merry", "venue": "Ripon", "race_name": "1m2f Hcap"},
        "2026-09-01",
    )

    assert context["goingRuns"] is None
    assert context["goingWins"] is None
    assert context["statuses"]["going"] == "unknown"


def test_generator_no_longer_hardcodes_missing_rich_context_as_zero():
    source = (ROOT / "scripts" / "generate-picks-betfair.py").read_text()

    assert "'goingWins': 0" not in source
    assert "'courseWins': 0" not in source
    assert "'distanceWins': 0" not in source
    assert "'trainerInForm': False" not in source
    assert "'rpr': 0" not in source
