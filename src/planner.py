"""Deterministic response planner: risk -> shelters -> routes -> volunteers."""
import copy
from .risk_engine import score_areas, DEFAULT_WEIGHTS, DEFAULT_LEVELS
from .route_engine import build_graph, dijkstra_from, route_info
from .shelter_engine import remaining_capacity, current_occupancy, allocate
from .volunteer_engine import assign_volunteers, DEFAULT_RULES

DEFAULT_CONFIG = {"weights": dict(DEFAULT_WEIGHTS), "risk_levels": dict(DEFAULT_LEVELS),
                  "allow_split": True, "volunteer_rules": dict(DEFAULT_RULES)}


def default_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def node_names(data):
    n = {a["id"]: a["name"] for a in data["areas"]}
    n.update({s["id"]: s["name"] for s in data["shelters"]})
    n.update({j["id"]: j["name"] for j in data["roads"].get("junctions", [])})
    return n


def build_plan(data, area_ids, blocked=(), full_shelters=(), config=None):
    cfg = config or default_config()
    names = node_names(data)
    areas = [a for a in data["areas"] if a["id"] in set(area_ids)]
    areas_by_id = {a["id"]: a for a in areas}
    risk = score_areas(areas, cfg["weights"], cfg["risk_levels"])
    G = build_graph(data["roads"], blocked)
    for n in list(names):
        G.add_node(n)
    remaining = {s["id"]: remaining_capacity(s, full_shelters) for s in data["shelters"]}
    assignments, unserved, warnings = [], [], []

    for r in risk:
        need = areas_by_id[r["area_id"]]["population"]
        dist, paths = dijkstra_from(G, r["area_id"])
        any_room = any(v > 0 for v in remaining.values())
        cands = [(s["id"], dist[s["id"]]) for s in data["shelters"] if remaining[s["id"]] > 0 and s["id"] in dist]
        placed, left = allocate(need, cands, remaining, cfg["allow_split"])
        for sid, n in placed:
            remaining[sid] -= n
            assignments.append({"area_id": r["area_id"], "area_name": r["name"], "shelter_id": sid,
                                "shelter_name": names[sid], "people": n,
                                "route": route_info(G, paths[sid], dist[sid], names)})
        if left > 0:
            if not any_room:
                reason = "No feasible shelter found: no shelter has remaining capacity."
            elif not cands:
                reason = "No feasible route found: every shelter with free capacity is unreachable (blocked roads excluded)."
            elif not cfg["allow_split"]:
                reason = "No feasible shelter found: no single reachable shelter can take the whole group."
            else:
                reason = "Reachable shelters are full; remaining people could not be placed."
            unserved.append({"area_id": r["area_id"], "area_name": r["name"], "people": left, "reason": reason})
            warnings.append(f"{r['name']}: {left} people unplaced. {reason}")

    areas_idx = {a["id"]: a for a in areas}
    vols, gaps = assign_volunteers(risk, areas_idx, data["volunteers"], cfg["volunteer_rules"])
    for g in gaps:
        warnings.append(f"{names[g['area_id']]}: volunteer slot ({g['skill']}) unfilled. {g['reason']}")

    placed_by_shelter = {}
    for a in assignments:
        placed_by_shelter[a["shelter_id"]] = placed_by_shelter.get(a["shelter_id"], 0) + a["people"]
    shelter_status = []
    for s in data["shelters"]:
        occ = current_occupancy(s, full_shelters)
        add = placed_by_shelter.get(s["id"], 0)
        shelter_status.append({"shelter_id": s["id"], "name": s["name"], "capacity": s["capacity"],
                               "occupancy": occ, "planned_additional": add,
                               "remaining_after_plan": s["capacity"] - occ - add,
                               "marked_full": s["id"] in set(full_shelters),
                               "available": s.get("available", True)})
    return {"area_ids": [r["area_id"] for r in risk], "risk": risk, "assignments": assignments,
            "unserved": unserved, "volunteers": vols, "volunteer_gaps": gaps,
            "shelter_status": shelter_status, "warnings": warnings,
            "blocked_roads": sorted(set(blocked)), "full_shelters": sorted(set(full_shelters))}


def plan_signature(plan):
    a = tuple(sorted((x["area_id"], x["shelter_id"], x["people"], tuple(x["route"]["path"])) for x in plan["assignments"]))
    u = tuple(sorted((x["area_id"], x["people"]) for x in plan["unserved"]))
    v = tuple(sorted((x["volunteer_id"], x["area_id"]) for x in plan["volunteers"]))
    return (a, u, v)


def _fmt(assigns, unserved):
    parts = [f"{x['people']} -> {x['shelter_name']} via {' > '.join(x['route']['path_names'])} ({x['route']['cost']:g} min)"
             for x in assigns]
    if unserved:
        parts.append(f"{unserved['people']} unplaced")
    return "; ".join(parts) or "nothing planned"


def diff_plans(old, new):
    if old is None:
        return []
    lines = []
    for aid in new["area_ids"]:
        name = next(r["name"] for r in new["risk"] if r["area_id"] == aid)
        o = _fmt([x for x in old["assignments"] if x["area_id"] == aid], next((x for x in old["unserved"] if x["area_id"] == aid), None))
        n = _fmt([x for x in new["assignments"] if x["area_id"] == aid], next((x for x in new["unserved"] if x["area_id"] == aid), None))
        if o != n:
            lines.append(f"{name}: was [{o}] -> now [{n}]")
    ov = {v["volunteer_id"]: v for v in old["volunteers"]}
    nv = {v["volunteer_id"]: v for v in new["volunteers"]}
    for vid in sorted(set(ov) | set(nv)):
        a, b = ov.get(vid), nv.get(vid)
        if (a and a["area_id"]) != (b and b["area_id"]):
            nm = (a or b)["name"]
            lines.append(f"Volunteer {nm}: {a['area_id'] if a else 'unassigned'} -> {b['area_id'] if b else 'unassigned'}")
    return lines
