"""Advisory drafting. Deterministic templates always work; Gemini (optional) only rephrases
the already-calculated facts, and its output is validated before use."""
import json
import os
import re

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass

DISCLAIMER_EN = "SIMULATED DRAFT - NOT SENT"
DISCLAIMER_TA = "உருவகப்படுத்தப்பட்ட வரைவு"


def gemini_configured():
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def gemini_status():
    return "Gemini enabled (with template fallback)" if gemini_configured() else "No API key - using template fallback"


# ---------- facts passed to the AI / templates (calculated values only) ----------
def build_facts(plan, data, version, alert_title):
    tamil = {a["id"]: a.get("tamil_name", a["name"]) for a in data["areas"]}
    road_names = {r["id"]: r["name"] for r in data["roads"]["roads"]}
    shelter_names = {s["id"]: s["name"] for s in data["shelters"]}
    areas = []
    for r in plan["risk"]:
        placements = [{"shelter": a["shelter_name"], "people": a["people"],
                       "route": " > ".join(a["route"]["path_names"]), "minutes": a["route"]["cost"]}
                      for a in plan["assignments"] if a["area_id"] == r["area_id"]]
        un = next((u for u in plan["unserved"] if u["area_id"] == r["area_id"]), None)
        areas.append({"name": r["name"], "tamil_name": tamil[r["area_id"]], "placements": placements,
                      "unplaced": un["people"] if un else 0})
    return {"plan_version": version, "alert": alert_title, "areas": areas,
            "blocked_roads": [road_names[i] for i in plan["blocked_roads"]],
            "full_shelters": [shelter_names[i] for i in plan["full_shelters"]]}


# ---------- deterministic templates ----------
def template_en(f):
    L = [f"[{DISCLAIMER_EN}] Flood advisory - Plan v{f['plan_version']}", f"Alert: {f['alert']}"]
    for a in f["areas"]:
        for p in a["placements"]:
            L.append(f"- {a['name']}: {p['people']} residents go to {p['shelter']} via {p['route']} (about {p['minutes']:g} min).")
        if a["unplaced"]:
            L.append(f"- {a['name']}: {a['unplaced']} residents not yet placed in a shelter; alternatives are being arranged.")
    if f["blocked_roads"]:
        L.append("Avoid blocked roads: " + ", ".join(f["blocked_roads"]) + ".")
    if f["full_shelters"]:
        L.append("Shelters currently full: " + ", ".join(f["full_shelters"]) + ".")
    L.append("Follow instructions from local officials. This draft needs officer approval before any release.")
    return "\n".join(L)


def template_ta(f):
    L = [f"[{DISCLAIMER_TA} - அனுப்பப்படவில்லை] வெள்ள அறிவிப்பு - திட்டம் v{f['plan_version']}"]
    for a in f["areas"]:
        for p in a["placements"]:
            L.append(f"- {a['tamil_name']} ({p['people']} பேர்): '{p['shelter']}' தங்குமிடத்திற்குச் செல்லவும். வழி: {p['route']} (சுமார் {p['minutes']:g} நிமிடம்).")
        if a["unplaced"]:
            L.append(f"- {a['tamil_name']}: {a['unplaced']} பேருக்கு இன்னும் தங்குமிடம் ஒதுக்கப்படவில்லை; மாற்று ஏற்பாடுகள் செய்யப்படுகின்றன.")
    if f["blocked_roads"]:
        L.append("மூடப்பட்ட சாலைகளைத் தவிர்க்கவும்: " + ", ".join(f["blocked_roads"]) + ".")
    if f["full_shelters"]:
        L.append("நிரம்பிய தங்குமிடங்கள்: " + ", ".join(f["full_shelters"]) + ".")
    L.append("உள்ளூர் அதிகாரிகளின் அறிவுறுத்தல்களைப் பின்பற்றவும். இந்த வரைவு அதிகாரி ஒப்புதலுக்குப் பிறகே வெளியிடப்படும்.")
    return "\n".join(L)


# ---------- Gemini (optional) ----------
def _call_gemini(prompt):
    """Isolated so tests can monkeypatch it. Never logs or returns the key."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip(),
                          http_options=types.HttpOptions(timeout=20000))
    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3-flash-preview"
    resp = client.models.generate_content(model=model, contents=prompt)
    return resp.text or ""


def _numbers(text):
    return {f"{float(n):g}" for n in re.findall(r"\d+(?:\.\d+)?", text)}


def validate_advisory(text, facts, lang):
    """Return (ok, reason). Rejects invented numbers, missing shelters/areas, wrong language."""
    if not text or not (40 <= len(text) <= 2500):
        return False, "empty or wrong length"
    allowed = _numbers(json.dumps(facts, ensure_ascii=False)) | {str(i) for i in range(0, 11)}
    extra = _numbers(text) - allowed
    if extra:
        return False, "contains numbers not in the calculated plan"
    for a in facts["areas"]:
        if a["placements"] and not (a["name"] in text or a["tamil_name"] in text):
            return False, "missing an affected area"
        for p in a["placements"]:
            if p["shelter"] not in text:
                return False, "missing an assigned shelter name"
    if lang == "ta":
        tamil_chars = len(re.findall(r"[\u0B80-\u0BFF]", text))
        if tamil_chars < 0.3 * len(re.findall(r"\w", text)):
            return False, "not Tamil"
        if "உருவகப்படுத்த" not in text:
            return False, "missing simulation label"
    elif "simulat" not in text.lower():
        return False, "missing simulation label"
    return True, "ok"


def _prompt(facts, lang):
    language = "Tamil (use ASCII digits; keep shelter and road names exactly as written in English)" if lang == "ta" else "English"
    return ("You draft a SHORT public flood advisory for a SIMULATED hackathon demo. Write in " + language + ". "
            "Use ONLY the facts below. Do not add numbers, places, routes, advice about road safety, or promises. "
            "Do not change which shelter an area is sent to. Begin with the label that this is a simulated draft.\n"
            "FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False))


def generate_advisory(facts, lang, use_ai=True):
    """Returns {'text','source','note'}. Always succeeds (template fallback)."""
    fallback = template_ta(facts) if lang == "ta" else template_en(facts)
    if not (use_ai and gemini_configured()):
        return {"text": fallback, "source": "template", "note": "Template fallback (no Gemini key configured)."}
    try:
        text = _call_gemini(_prompt(facts, lang)).strip()
    except Exception as exc:  # never include exc text: it could echo request details
        return {"text": fallback, "source": "template", "note": f"Gemini unavailable ({type(exc).__name__}); template fallback used."}
    ok, why = validate_advisory(text, facts, lang)
    if not ok:
        return {"text": fallback, "source": "template", "note": f"Gemini output rejected ({why}); template fallback used."}
    return {"text": text, "source": "gemini", "note": "Drafted by Gemini from calculated facts; validated."}


# ---------- plain-language explanation ----------
def explain_template(plan, data):
    names = {s["id"]: s["name"] for s in data["shelters"]}
    lines = []
    for r in plan["risk"]:
        f = r["factors"]
        lines.append(f"{r['name']} ranks {r['level']} (score {r['score']}): exposure {f['exposure']['points']}, "
                     f"population {f['population']['points']}, vulnerable residents {f['vulnerable']['points']} points.")
    for a in plan["assignments"]:
        lines.append(f"{a['people']} people from {a['area_name']} go to {a['shelter_name']}: lowest-cost reachable shelter with free places "
                     f"({a['route']['cost']:g} min).")
    for u in plan["unserved"]:
        lines.append(f"{u['area_name']}: {u['people']} people unplaced - {u['reason']}")
    return "\n".join(lines)


def explain_plan(plan, data, use_ai=True):
    base = explain_template(plan, data)
    if not (use_ai and gemini_configured()):
        return {"text": base, "source": "template"}
    try:
        text = _call_gemini("Explain this calculated flood response plan in 4 plain sentences for an emergency officer. "
                            "Use only these facts and add no new numbers or advice:\n" + base).strip()
        if text and _numbers(text) <= _numbers(base) | {str(i) for i in range(0, 11)}:
            return {"text": text, "source": "gemini"}
    except Exception:
        pass
    return {"text": base, "source": "template"}
