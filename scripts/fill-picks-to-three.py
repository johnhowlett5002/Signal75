import json
from pathlib import Path
from datetime import datetime

P = Path("/Users/johnhowlett/Signal75/picks.json")
d = json.load(open(P))

def norm(x):
    return str(x or "").strip().upper()

def existing_names(groups):
    names=set()
    for r in groups:
        for h in r.get("horses", []):
            names.add(norm(h.get("name")))
    return names

def make_group(h, race_type):
    score = int(float(h.get("signal_score") or h.get("qualificationScore") or h.get("score") or 0))
    return {
        "course": h.get("venue") or h.get("course") or "TBC",
        "time": h.get("time") or h.get("race_time") or "",
        "type": h.get("race_type") or h.get("type") or race_type,
        "runners": h.get("runners") or h.get("runner_count") or 8,
        "isRadar": True,
        "horses": [{
            **h,
            "name": h.get("name") or h.get("horse_name"),
            "signal_score": score,
            "score": score,
            "badge": "Radar",
            "tipsters": h.get("tipsters", 0),
            "jockey": h.get("jockey") or "Radar pick",
            "reason": h.get("reason") or "Radar qualifier added to complete today’s shortlist."
        }]
    }

def fill(group_name, radar_key, race_type):
    groups = d.get(group_name, []) or []
    used = existing_names(groups)
    radar = d.get(radar_key, []) or []

    for h in radar:
        if len(groups) >= 3:
            break
        name = norm(h.get("name") or h.get("horse_name"))
        if not name or name in used:
            continue
        groups.append(make_group(h, race_type))
        used.add(name)

    d[group_name] = groups
    print(group_name, "now has", len(groups), "cards")

fill("flat", "topRatedFlat", "flat")
fill("jumps", "topRatedJumps", "jumps")

P.write_text(json.dumps(d, indent=2))
print("✅ Filled Flat/Jumps to 3 where radar exists")
