"""Road graph + Dijkstra routing with NetworkX. Blocked roads are removed from the graph."""
import networkx as nx


def build_graph(roads, blocked=()):
    blocked = set(blocked)
    G = nx.Graph()
    for n in roads.get("junctions", []):
        G.add_node(n["id"])
    for r in roads["roads"]:
        if r["id"] in blocked:
            continue
        a, b, w = r["from"], r["to"], float(r["minutes"])
        if G.has_edge(a, b) and G[a][b]["weight"] <= w:
            continue  # keep the cheaper of parallel roads
        G.add_edge(a, b, weight=w, road_id=r["id"])
    return G


def add_nodes(G, node_ids):
    for n in node_ids:
        G.add_node(n)


def dijkstra_from(G, source):
    """Return (distances, paths) from source. Unreachable nodes are absent."""
    if source not in G:
        return {}, {}
    return nx.single_source_dijkstra(G, source, weight="weight")


def route_info(G, path, cost, names=None):
    names = names or {}
    road_ids = [G[u][v]["road_id"] for u, v in zip(path, path[1:])]
    return {"path": list(path), "path_names": [names.get(n, n) for n in path],
            "road_ids": road_ids, "cost": round(float(cost), 1)}


def shortest_route(G, source, target, names=None):
    """Single route or None when no valid route exists."""
    if source not in G or target not in G:
        return None
    try:
        cost, path = nx.single_source_dijkstra(G, source, target, weight="weight")
    except nx.NetworkXNoPath:
        return None
    return route_info(G, path, cost, names)
