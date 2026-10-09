"""Lightweight offline SVG map of the (illustrative) scenario. Not a real geographic map."""
from html import escape

LEVEL_COLOR = {"CRITICAL": "#D7263D", "HIGH": "#FF6A13", "MODERATE": "#F2B134", None: "#5C7AA6"}


def render_map_svg(state):
    d = state.data
    pos = {a["id"]: (a["x"], a["y"]) for a in d["areas"]}
    pos.update({s["id"]: (s["x"], s["y"]) for s in d["shelters"]})
    pos.update({j["id"]: (j["x"], j["y"]) for j in d["roads"].get("junctions", [])})
    level = {r["area_id"]: r["level"] for r in (state.plan or {"risk": []})["risk"]}
    in_alert = set(state.alert["area_ids"]) if state.alert else set()
    route_edges = set()
    for a in (state.plan or {"assignments": []})["assignments"]:
        p = a["route"]["path"]
        route_edges.update(frozenset(e) for e in zip(p, p[1:]))
    s = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" style="width:100%;height:100%;background:#F4F7FC;border-radius:10px;font-family:Segoe UI,Arial,sans-serif">']
    s.append('<text x="2" y="4.5" font-size="2.6" fill="#0B1F3A" font-weight="700">SIMULATED SCENARIO MAP - illustrative, not geographic</text>')
    for r in d["roads"]["roads"]:
        (x1, y1), (x2, y2) = pos[r["from"]], pos[r["to"]]
        blocked = r["id"] in state.blocked
        planned = frozenset((r["from"], r["to"])) in route_edges and not blocked
        stroke, w, dash = ("#D7263D", 0.9, "2,1.4") if blocked else (("#FF6A13", 1.5, "") if planned else ("#9FB0C8", 0.6, ""))
        s.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{w}" stroke-dasharray="{dash}" stroke-linecap="round"/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        s.append(f'<text x="{mx}" y="{my - 0.8}" font-size="2" fill="{"#D7263D" if blocked else "#5C7AA6"}" text-anchor="middle">{r["id"]}{" X" if blocked else ""}</text>')
    for j in d["roads"].get("junctions", []):
        x, y = pos[j["id"]]
        s.append(f'<circle cx="{x}" cy="{y}" r="1.3" fill="#5C7AA6"/><text x="{x}" y="{y + 3.4}" font-size="2" text-anchor="middle" fill="#0B1F3A">Junction</text>')
    status = {x["shelter_id"]: x for x in (state.plan or {"shelter_status": []})["shelter_status"]}
    for sh in d["shelters"]:
        x, y = sh["x"], sh["y"]
        full = sh["id"] in state.full_shelters
        st = status.get(sh["id"])
        occ = sh["capacity"] if full else sh["initial_occupancy"]
        add = st["planned_additional"] if st else 0
        txt = "FULL" if full else f'{occ + add}/{sh["capacity"]}'
        s.append(f'<rect x="{x - 2.4}" y="{y - 2.4}" width="4.8" height="4.8" rx="0.8" fill="{"#7A869A" if full else "#0B1F3A"}"/>')
        s.append(f'<text x="{x}" y="{y + 0.9}" font-size="2.6" fill="#fff" text-anchor="middle">H</text>')
        s.append(f'<text x="{x}" y="{y + 5.4}" font-size="2.1" text-anchor="middle" fill="#0B1F3A">{escape(sh["name"])}</text>')
        s.append(f'<text x="{x}" y="{y + 7.7}" font-size="2" text-anchor="middle" fill="{"#D7263D" if full else "#0B1F3A"}" font-weight="700">{txt}</text>')
    for a in d["areas"]:
        x, y = a["x"], a["y"]
        active = a["id"] in in_alert
        col = LEVEL_COLOR.get(level.get(a["id"]), "#5C7AA6") if active else "#C5CFDE"
        s.append(f'<circle cx="{x}" cy="{y}" r="3.3" fill="{col}" stroke="#0B1F3A" stroke-width="0.4"/>')
        s.append(f'<text x="{x}" y="{y - 4.6}" font-size="2.5" text-anchor="middle" fill="#0B1F3A" font-weight="700">{escape(a["name"])}</text>')
        if a["id"] in level:
            s.append(f'<text x="{x}" y="{y + 0.9}" font-size="2.3" text-anchor="middle" fill="#fff" font-weight="700">{level[a["id"]][0]}</text>')
    s.append('<g font-size="2" fill="#0B1F3A"><rect x="2" y="90" width="3" height="1" fill="#FF6A13"/><text x="6" y="91">planned route</text>'
             '<rect x="22" y="90" width="3" height="1" fill="#D7263D"/><text x="26" y="91">blocked road</text>'
             '<circle cx="45" cy="90.5" r="1" fill="#D7263D"/><text x="47" y="91">C/H/M risk</text>'
             '<rect x="62" y="89.6" width="1.8" height="1.8" fill="#0B1F3A"/><text x="65" y="91">shelter (occupancy/capacity)</text></g>')
    s.append('</svg>')
    return "".join(s)
