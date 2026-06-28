"""
automation_status.py
Small helper for the Signal 75 Intelligence Dashboard's Automation Health
panel. Writes ONLY to dashboard/data/automation_status.json. Never touches
picks, scores, results, or proof.

HOW TO WIRE THIS IN (no new standalone script — call from the EXISTING jobs):

  from automation_status import reset_for_today, record_job

  # at the very start of the 10:00 morning pipeline, once:
  reset_for_today()

  # after each existing step in the 10:00 and 23:10 pipelines, one line each:
  record_job("config_check", "System config check", "ok")
  record_job("scoring_tests", "Scoring regression tests", "ok", detail="4 passed")
  record_job("picks_generator", "Picks generated", "ok")
  record_job("selection_diagnostics", "Selection diagnostics", "ok")
  record_job("deployment", "Site deployment", "ok")
  record_job("results_updater", "Results updater", "ok")
  record_job("combined_learning", "Nightly learning refresh", "ok")
  record_job("pipeline_health", "Pipeline health report", "ok")

  # if a step fails, record that instead of (or as well as) raising/logging:
  record_job("results_updater", "Results updater", "failed", detail=str(exc))

  # the GitHub Action test workflow can call this too (it has network access
  # to nothing on your Mac, so instead just have the Mac-side job record
  # "github_tests" the next time it runs, reading the latest workflow
  # conclusion via the GitHub API if you want this fully accurate; a static
  # "ok" is a fine placeholder to start with).
  record_job("github_tests", "GitHub regression check", "ok", time_label="on code change")

IMPORTANT: this file deliberately does NOT decide whether a failed test
should stop picks generation. That decision stays exactly where the
16:30 conversation said it should: a failed test/config check is recorded
as a clear warning here, but the calling pipeline is responsible for
choosing to continue generating picks regardless.
"""

import argparse
import json
import os
import tempfile
from datetime import datetime

# ---------------------------------------------------------------------------
# ADJUST THIS to wherever /dashboard/ actually lives on the server / Mac.
# ---------------------------------------------------------------------------
DASHBOARD_DATA_DIR = os.environ.get(
    "S75_DASHBOARD_DATA_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "data"),
)
STATUS_PATH = os.path.join(DASHBOARD_DATA_DIR, "automation_status.json")

# Every job the dashboard knows how to display, in display order, with its
# usual scheduled time. reset_for_today() seeds the file with all of these
# as "scheduled" / "pending" so the panel never shows a job as missing —
# only as not-yet-run.
JOB_DEFS = [
    ("config_check", "System config check", "10:00"),
    ("scoring_tests", "Scoring regression tests", "10:00"),
    ("picks_generator", "Picks generated", "10:02"),
    ("selection_diagnostics", "Selection diagnostics", "10:02"),
    ("deployment", "Site deployment", "10:05"),
    ("results_updater", "Results updater", "19:20"),
    ("combined_learning", "Nightly learning refresh", "23:10"),
    ("pipeline_health", "Pipeline health report", "23:10"),
    ("github_tests", "GitHub regression check", "on code change"),
]

MANUAL_BY_DESIGN = [
    "Recovery / restore tools",
    "Deployment trigger",
    "Outward-facing email / social posting",
    "One-off research and back-test tools",
    "Legacy duplicate result tools kept only for safety",
]


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _load():
    if os.path.exists(STATUS_PATH):
        try:
            with open(STATUS_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return None


def reset_for_today():
    """Call once at the very start of the 10:00 morning pipeline."""
    jobs = [
        {"name": name, "label": label, "status": "scheduled", "time": sched_time, "detail": None}
        for name, label, sched_time in JOB_DEFS
    ]
    data = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "jobs": jobs,
        "manualByDesign": MANUAL_BY_DESIGN,
    }
    _atomic_write(STATUS_PATH, data)
    return data


def record_job(name, label, status, detail=None, time_label=None):
    """
    status: one of "ok", "pending", "failed", "scheduled"
    detail: short human string, e.g. "4 passed" or an exception message
    time_label: override the default scheduled time with the actual run time,
                e.g. datetime.now().strftime('%H:%M')
    """
    data = _load()
    if data is None or data.get("date") != datetime.now().strftime("%Y-%m-%d"):
        data = reset_for_today()

    found = False
    for job in data["jobs"]:
        if job["name"] == name:
            job["label"] = label
            job["status"] = status
            job["detail"] = detail
            if time_label:
                job["time"] = time_label
            elif status == "ok":
                job["time"] = datetime.now().strftime("%H:%M")
            found = True
            break
    if not found:
        data["jobs"].append({
            "name": name, "label": label, "status": status,
            "time": time_label or datetime.now().strftime("%H:%M"), "detail": detail,
        })

    data["generated_at"] = datetime.now().isoformat(timespec="seconds")
    _atomic_write(STATUS_PATH, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update the local dashboard automation panel.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("reset", help="Start a new local dashboard status for today.")
    record = subparsers.add_parser("record", help="Record one pipeline step.")
    record.add_argument("name")
    record.add_argument("label")
    record.add_argument("status", choices=("ok", "pending", "failed", "scheduled"))
    record.add_argument("--detail")
    record.add_argument("--time")
    args = parser.parse_args()
    if args.command == "reset":
        reset_for_today()
    else:
        record_job(args.name, args.label, args.status, args.detail, args.time)
    print("Updated", STATUS_PATH)
