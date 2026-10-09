"""Shelter capacity rules. A shelter is never assigned more people than it has room for."""


def remaining_capacity(shelter, full_ids=(), allocated=0):
    if shelter["id"] in set(full_ids) or not shelter.get("available", True):
        return 0
    free = int(shelter["capacity"]) - int(shelter.get("initial_occupancy", 0)) - int(allocated)
    return max(0, free)


def current_occupancy(shelter, full_ids=()):
    if shelter["id"] in set(full_ids):
        return int(shelter["capacity"])
    return int(shelter.get("initial_occupancy", 0))


def allocate(people, candidates, remaining, allow_split=True):
    """candidates: [(shelter_id, travel_cost)]. remaining: {shelter_id: free places} (read-only).
    Returns ([(shelter_id, n_people)], people_left). Cheapest reachable shelter first."""
    ranked = sorted(candidates, key=lambda c: (c[1], -remaining.get(c[0], 0), c[0]))
    placed, left = [], int(people)
    for sid, _cost in ranked:
        free = remaining.get(sid, 0)
        if free <= 0 or left <= 0:
            continue
        if allow_split:
            n = min(free, left)
            placed.append((sid, n))
            left -= n
        elif free >= left:
            placed.append((sid, left))
            left = 0
            break
    return placed, left
