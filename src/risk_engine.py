"""Transparent flood-risk scoring.

score = 100 * ( w_exposure * exposure
              + w_population * population / max_population
              + w_vulnerable * vulnerable / max_vulnerable )

Weights are normalised to sum to 1, so the score is always within 0..100.
All inputs are SIMULATED. See README for limitations.
"""

DEFAULT_WEIGHTS = {"exposure": 0.50, "population": 0.25, "vulnerable": 0.25}
DEFAULT_LEVELS = {"critical": 70.0, "high": 50.0}


def normalise_weights(weights):
    cleaned = {k: max(0.0, float(weights.get(k, 0.0))) for k in DEFAULT_WEIGHTS}
    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("At least one risk weight must be greater than zero.")
    return {k: v / total for k, v in cleaned.items()}


def vulnerable_count(area):
    v = sum(max(0, int(n)) for n in area.get("vulnerable", {}).values())
    return min(v, int(area.get("population", 0)))


def risk_level(score, levels=None):
    levels = levels or DEFAULT_LEVELS
    if score >= levels["critical"]:
        return "CRITICAL"
    if score >= levels["high"]:
        return "HIGH"
    return "MODERATE"


def score_areas(areas, weights=None, levels=None):
    """Return risk records sorted by score (highest first)."""
    if not areas:
        return []
    w = normalise_weights(weights or DEFAULT_WEIGHTS)
    max_pop = max(int(a.get("population", 0)) for a in areas) or 1
    max_vul = max(vulnerable_count(a) for a in areas) or 1
    out = []
    for a in areas:
        exposure = min(1.0, max(0.0, float(a.get("flood_exposure", 0))))
        pop = int(a.get("population", 0))
        vul = vulnerable_count(a)
        norm = {"exposure": exposure, "population": pop / max_pop, "vulnerable": vul / max_vul}
        raw = {"exposure": exposure, "population": pop, "vulnerable": vul}
        factors = {k: {"raw": raw[k], "normalised": round(norm[k], 3), "weight": round(w[k], 3),
                       "points": round(100 * w[k] * norm[k], 1)} for k in w}
        score = round(min(100.0, max(0.0, sum(100 * w[k] * norm[k] for k in w))), 1)
        out.append({"area_id": a["id"], "name": a["name"], "score": score,
                    "level": risk_level(score, levels), "factors": factors,
                    "population": pop, "vulnerable": vul,
                    "vulnerable_ratio": round(vul / pop, 3) if pop else 0.0,
                    "flood_exposure": exposure})
    out.sort(key=lambda r: (-r["score"], r["area_id"]))
    return out
