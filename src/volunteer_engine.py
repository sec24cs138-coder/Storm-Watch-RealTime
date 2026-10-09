"""Rule-based volunteer assignment (skills, availability, workload). No double assignment."""
import math

DEFAULT_RULES = {"max_tasks": 1, "two_volunteer_score": 70.0,
                 "medical_vulnerable_ratio": 0.35, "boat_exposure": 0.75}


def required_skills(risk_rec, rules):
    if risk_rec["vulnerable_ratio"] >= rules["medical_vulnerable_ratio"]:
        primary = "medical"
    elif risk_rec["flood_exposure"] >= rules["boat_exposure"]:
        primary = "boat_rescue"
    else:
        primary = "logistics"
    slots = [primary]
    if risk_rec["score"] >= rules["two_volunteer_score"]:
        slots.append("logistics")
    return slots


def assign_volunteers(risk, areas_by_id, volunteers, rules=None):
    rules = {**DEFAULT_RULES, **(rules or {})}
    load = {v["id"]: 0 for v in volunteers}
    out, gaps = [], []
    slot_lists = [(r, required_skills(r, rules)) for r in risk]
    passes = max((len(s) for _, s in slot_lists), default=0)
    for p in range(passes):  # first slot of every area (by priority) before any second slot
        for r, slots in slot_lists:
            if p >= len(slots):
                continue
            skill, area = slots[p], areas_by_id[r["area_id"]]
            cands = [v for v in volunteers if v.get("available", True) and load[v["id"]] < rules["max_tasks"]]
            if not cands:
                gaps.append({"area_id": r["area_id"], "skill": skill,
                             "reason": "No available volunteer with spare capacity"})
                continue

            def key(v):
                d = math.hypot(v["x"] - area["x"], v["y"] - area["y"])
                return (0 if skill in v["skills"] else 1, d, v["id"])
            best = min(cands, key=key)
            matched = skill in best["skills"]
            dist = round(math.hypot(best["x"] - area["x"], best["y"] - area["y"]), 1)
            reason = (f"Has '{skill}' skill; nearest matching available volunteer (map distance {dist})."
                      if matched else
                      f"No free volunteer with '{skill}'; nearest available volunteer assigned as general support (distance {dist}).")
            load[best["id"]] += 1
            out.append({"volunteer_id": best["id"], "name": best["name"], "area_id": r["area_id"],
                        "skill_needed": skill, "skill_matched": matched, "reason": reason})
    return out, gaps
