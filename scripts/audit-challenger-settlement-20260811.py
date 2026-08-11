#!/usr/bin/env python3
"""
Read-only audit for Challenger Lab settlement / performance place-rate issues.

Does NOT modify:
- picks.json
- performance.json
- scoring_engine.py
- challenger files
- proof/results

It only prints what is wrong and where.
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHAL = DATA / "challenger_lab"

print("=" * 100)
print("SIGNAL 75 — CHALLENGER SETTLEMENT / PERFORMANCE AUDIT")
print("=" * 100)
print(f"Repo: {ROOT}")
print()

def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR reading {path}: {e}")
        return None


def pick_result_block(pick):
    """Return the current settlement block, supporting old and new schemas."""
    if not isinstance(pick, dict):
        return {}
    post = pick.get("post_race_result")
    return post if isinstance(post, dict) else pick


def settled_result(pick):
    block = pick_result_block(pick)
    result = block.get("result")
    ret = block.get("return", block.get("returns", block.get("returned")))
    is_settled = bool(
        block.get("settled") is True
        or result not in (None, "", "unsettled", "UNSETTLED")
        or (ret not in (None, "", 0, 0.0, "0", "0.0"))
    )
    return result, ret, is_settled, block

# ---------------------------------------------------------------------
# 1. Find settlement-related scripts
# ---------------------------------------------------------------------
print("1) SETTLEMENT-RELATED SCRIPTS")
print("-" * 100)

for path in sorted((ROOT / "scripts").glob("*.py")):
    txt = path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"settle.*challenger|challenger.*settle|settled", txt, re.I):
        print(f"FOUND: {path.relative_to(ROOT)}")

print()

# ---------------------------------------------------------------------
# 2. Check nightly pipeline calls settlement
# ---------------------------------------------------------------------
print("2) NIGHTLY PIPELINE SETTLEMENT CALL CHECK")
print("-" * 100)

pipeline = ROOT / "scripts" / "run_nightly_pipeline.py"
wrapper = Path.home() / "signal75-run-results.sh"
if not pipeline.exists() and not wrapper.exists():
    print("MISSING: scripts/run_nightly_pipeline.py")
    print("MISSING: ~/signal75-run-results.sh")
else:
    if pipeline.exists():
        txt = pipeline.read_text(encoding="utf-8", errors="ignore")
        hits = []
        for i, line in enumerate(txt.splitlines(), start=1):
            if re.search(r"settle.*challenger|challenger.*settle|build-challenger-summary|challenger-summary", line, re.I):
                hits.append((i, line.strip()))
        if hits:
            print(f"CHECKING: {pipeline.relative_to(ROOT)}")
            for i, line in hits:
                print(f"LINE {i}: {line}")
        else:
            print("WARNING: No obvious challenger settlement/build summary call found in run_nightly_pipeline.py")
    if wrapper.exists():
        txt = wrapper.read_text(encoding="utf-8", errors="ignore")
        hits = []
        for i, line in enumerate(txt.splitlines(), start=1):
            if re.search(r"settle.*challenger|challenger.*settle|build-challenger-summary|publish_dashboard_data", line, re.I):
                hits.append((i, line.strip()))
        if hits:
            print("CHECKING: ~/signal75-run-results.sh")
            for i, line in hits:
                print(f"LINE {i}: {line}")
        else:
            print("WARNING: No challenger settlement/build/publish call found in ~/signal75-run-results.sh")

print()

# ---------------------------------------------------------------------
# 3. Check latest challenger files and settled pick counts
# ---------------------------------------------------------------------
print("3) CHALLENGER FILE SETTLEMENT STATUS")
print("-" * 100)

files = sorted(CHAL.glob("challenger_20*.json")) if CHAL.exists() else []
files = [f for f in files if "summary" not in f.name.lower()]

print(f"Challenger files found: {len(files)}")
for f in files[-10:]:
    d = read_json(f)
    if not isinstance(d, dict):
        continue

    pre = d.get("pre_race_challengers") or d.get("challengers") or []
    total_picks = 0
    settled = 0
    unsettled = 0
    returns = 0.0

    for c in pre:
        if not isinstance(c, dict):
            continue
        for p in c.get("picks", []) or []:
            if not isinstance(p, dict):
                continue
            total_picks += 1
            _result, ret, is_settled, _block = settled_result(p)
            if is_settled:
                settled += 1
            else:
                unsettled += 1
            try:
                returns += float(ret or 0)
            except Exception:
                pass

    print(f"{f.name}: challengers={len(pre)} picks={total_picks} settled={settled} unsettled={unsettled} returns=£{returns:.2f}")

print()

# ---------------------------------------------------------------------
# 4. Show latest file sample
# ---------------------------------------------------------------------
print("4) LATEST CHALLENGER PICK SAMPLE")
print("-" * 100)

if files:
    latest = files[-1]
    print(f"Latest: {latest.relative_to(ROOT)}")
    d = read_json(latest)
    if isinstance(d, dict):
        pre = d.get("pre_race_challengers") or d.get("challengers") or []
        shown = 0
        for c in pre:
            if not isinstance(c, dict):
                continue
            cid = c.get("id") or c.get("name")
            for p in (c.get("picks") or [])[:3]:
                if not isinstance(p, dict):
                    continue
                result, ret, _is_settled, block = settled_result(p)
                print(
                    cid,
                    "|", p.get("name") or p.get("horse") or p.get("horse_name"),
                    "| result:", result,
                    "| return:", ret,
                    "| settled:", block.get("settled"),
                    "| schema:", "post_race_result" if block is not p else "top_level",
                )
                shown += 1
            if shown >= 12:
                break
else:
    print("No challenger files found.")

print()

# ---------------------------------------------------------------------
# 5. Check performance.json place-rate fields
# ---------------------------------------------------------------------
print("5) PERFORMANCE.JSON PLACE/RATE FIELDS")
print("-" * 100)

perf = ROOT / "performance.json"
if not perf.exists():
    print("MISSING performance.json")
else:
    p = read_json(perf)
    if isinstance(p, dict):
        for k, v in p.items():
            if "place" in k.lower() or "rate" in k.lower() or "roi" in k.lower() or "profit" in k.lower() or "return" in k.lower() or "stake" in k.lower():
                print(f"{k}: {v}")

print()

# ---------------------------------------------------------------------
# 6. Check generate-performance.py place-rate logic
# ---------------------------------------------------------------------
print("6) GENERATE-PERFORMANCE PLACE-RATE LOGIC")
print("-" * 100)

gp = ROOT / "scripts" / "generate-performance.py"
if not gp.exists():
    print("MISSING scripts/generate-performance.py")
else:
    txt = gp.read_text(encoding="utf-8", errors="ignore")
    for i, line in enumerate(txt.splitlines(), start=1):
        if re.search(r"placeRate|place_rate|placed|place", line, re.I):
            print(f"LINE {i}: {line.strip()}")

print()

# ---------------------------------------------------------------------
# 7. Challenger summary delta sanity
# ---------------------------------------------------------------------
print("7) CHALLENGER SUMMARY / DELTA CHECK")
print("-" * 100)

summary_candidates = sorted(CHAL.glob("*summary*.json")) if CHAL.exists() else []
for f in summary_candidates:
    d = read_json(f)
    if not isinstance(d, dict):
        continue
    print(f"SUMMARY: {f.relative_to(ROOT)}")

    rows = d.get("challengers") or d.get("pre_race_challengers") or d.get("rows") or []
    if isinstance(rows, dict):
        rows = list(rows.values())

    for c in rows:
        if not isinstance(c, dict):
            continue
        cid = c.get("id") or c.get("name")
        delta = (
            c.get("delta_vs_live_profit")
            if c.get("delta_vs_live_profit") is not None
            else c.get("delta")
            or c.get("profit_delta")
            or c.get("roi_delta")
            or c.get("delta_profit")
        )
        settled_days = (
            c.get("settled_days")
            if c.get("settled_days") is not None
            else c.get("days_settled")
            or c.get("days")
        )
        picks = c.get("total_picks") or c.get("picks") or c.get("settled_picks")
        place_rate = c.get("different_pick_place_rate") or c.get("place_rate") or c.get("placeRate")
        if cid:
            print(f"  {cid}: delta={delta} settled_days={settled_days} picks={picks} place_rate={place_rate}")

print()

# ---------------------------------------------------------------------
# 8. Check suspicious identical challenger figures
# ---------------------------------------------------------------------
print("8) IDENTICAL CHALLENGER FIGURE CHECK")
print("-" * 100)

for f in summary_candidates:
    d = read_json(f)
    if not isinstance(d, dict):
        continue

    rows = d.get("challengers") or d.get("pre_race_challengers") or d.get("rows") or []
    if isinstance(rows, dict):
        rows = list(rows.values())

    target = {}
    for c in rows:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or c.get("name") or "")
        if any(x in cid.lower() for x in ["form_soft", "freshness", "large_field"]):
            target[cid] = {
                "delta": c.get("delta") or c.get("profit_delta") or c.get("delta_profit"),
                "delta_vs_live_profit": c.get("delta_vs_live_profit"),
                "days": c.get("settled_days") if c.get("settled_days") is not None else c.get("days_settled") or c.get("days"),
                "picks": c.get("total_picks") or c.get("picks") or c.get("settled_picks"),
                "place_rate": c.get("different_pick_place_rate") or c.get("place_rate") or c.get("placeRate"),
            }

    if target:
        print(f"From {f.name}:")
        for cid, vals in target.items():
            print(f"  {cid}: {vals}")

print()

# ---------------------------------------------------------------------
# 9. Git status protection check
# ---------------------------------------------------------------------
print("9) CURRENT GIT STATUS")
print("-" * 100)
os.system("git status --short")

print()
print("=" * 100)
print("AUDIT COMPLETE — READ ONLY")
print("=" * 100)
