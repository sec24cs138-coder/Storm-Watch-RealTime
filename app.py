"""Storm Watch - AI-assisted flood response planning (SIMULATED hackathon prototype)."""
import sys
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
import requests
import folium
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.state_manager import ScenarioState          # noqa: E402
from src.advisory_engine import gemini_status, gemini_configured, _call_gemini  # noqa: E402
from src.map_view import render_map_svg              # noqa: E402

NAVY, ORANGE = "#0B1F3A", "#FF6A13"
# Streamlit renamed use_container_width -> width="stretch"; support both old and new versions.
try:
    _v = tuple(int(x) for x in st.__version__.split(".")[:2])
except Exception:
    _v = (1, 0)
S = {"width": "stretch"} if _v >= (1, 50) else {"use_container_width": True}
st.set_page_config(page_title="Storm Watch", page_icon="🌊", layout="wide")
st.markdown(f"""<style>
.block-container{{padding-top:1.2rem}}
.sw-header{{background:{NAVY};color:#fff;padding:14px 20px;border-radius:12px;display:flex;align-items:center;gap:16px}}
.sw-header h1{{margin:0;font-size:1.7rem;color:#fff}} .sw-header .sub{{color:#C9D6EA;font-size:.9rem}}
.sw-badge{{background:{ORANGE};color:#fff;padding:4px 12px;border-radius:999px;font-weight:700;font-size:.8rem;margin-left:auto;white-space:nowrap}}
.sw-banner{{padding:12px 18px;border-radius:10px;margin:10px 0;color:#fff;font-weight:600}}
.sw-card{{border:1px solid #D5DEEC;border-radius:10px;padding:10px 14px;margin-bottom:8px;background:#fff}}
.sw-step{{display:inline-block;padding:5px 10px;border-radius:8px;margin:2px;font-size:.82rem;font-weight:600}}
.sw-bar{{height:10px;border-radius:5px;background:#E6ECF5;overflow:hidden;display:flex}}
.sw-pill{{padding:2px 9px;border-radius:999px;color:#fff;font-size:.75rem;font-weight:700}}
</style>""", unsafe_allow_html=True)

if "sw" not in st.session_state:
    st.session_state.sw = ScenarioState()
    st.session_state.flash = None
sw: ScenarioState = st.session_state.sw


# ---------------- live weather data (Open-Meteo) ----------------
# Coordinates are real approximate neighborhood coordinates; shelter/road network below remains illustrative.
LIVE_PLACES = {
    "Velachery": {"lat": 12.9815, "lon": 80.2180},
    "Adyar": {"lat": 13.0067, "lon": 80.2570},
    "Taramani": {"lat": 12.9863, "lon": 80.2430},
    "Thiruvanmiyur": {"lat": 12.9830, "lon": 80.2594},
    "Guindy": {"lat": 13.0067, "lon": 80.2206},
    "Perungudi": {"lat": 12.9611, "lon": 80.2408},
}
WEATHER_LABELS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Drizzle",
    55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Rain showers",
    81: "Moderate rain showers", 82: "Violent rain showers", 95: "Thunderstorm",
    96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}

@st.cache_data(ttl=600, show_spinner=False)
def fetch_live_weather(place_name, lat, lon):
    """Fetch current conditions and next-hourly forecasts from Open-Meteo. No simulated fallback."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,weather_code,wind_speed_10m,wind_direction_10m",
        "hourly": "precipitation_probability,precipitation,weather_code",
        "forecast_days": 1, "timezone": "Asia/Kolkata"
    }
    response = requests.get(url, params=params, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if "current" not in payload:
        raise ValueError("Weather provider did not return current conditions")
    return payload

# ---------------- citizen education / Q&A knowledge base ----------------
QA_KNOWLEDGE = [
    (("dashboard", "score", "risk score", "what does", "meaning"),
     "This dashboard combines live weather observations/forecasts with a separate response-planning demo. A risk score is a prioritisation aid, not an official flood forecast. Shelter capacities, population values and routes in the demo are illustrative."),
    (("before flood", "prevent flood", "prevention", "prepare", "drain", "monsoon"),
     "Before flood season: keep nearby drains clear through the responsible local body; report blocked drains and recurring waterlogging; keep documents/medicines in a waterproof bag; elevate electrical items where practical; identify higher ground and family meeting points; save official alert links; and check on older people and people with disabilities. Never enter a drain or floodwater to clear a blockage."),
    (("storm", "thunder", "lightning", "cyclone", "strong wind"),
     "For storm preparedness: secure loose outdoor items, stay indoors during lightning, avoid trees/open fields and metal structures, unplug sensitive equipment if safe, and stay away from damaged power lines. Follow IMD/NDMA/local-authority instructions. This app does not issue official warnings."),
    (("during flood", "floodwater", "water on road", "waterlogging", "stranded"),
     "If flooding is occurring: move away from flowing water and electrical hazards; do not walk or drive through floodwater; move to higher ground if safe; carry essential medicines/documents; and follow official evacuation directions. If there is immediate danger, contact local emergency services."),
    (("after flood", "cleanup", "return home", "re-enter"),
     "Return only when authorities say it is safe. Avoid downed wires and unstable structures; do not touch wet electrical equipment; use safe drinking water; and document damage only if it is safe. Report dangerous conditions to the local authority."),
    (("alert", "warning", "sachet", "imd", "official"),
     "Check official sources before acting: IMD Mausam https://mausam.imd.gov.in/ and NDMA SACHET https://sachet.ndma.gov.in/. Storm Watch is a companion prototype and does not replace official alerts."),
    (("shelter", "evacuation", "route", "where should i go"),
     "Shelter names, capacity, route costs and road-block scenarios shown in this prototype are demo data, not verified evacuation instructions. Use only routes and shelters confirmed by local authorities. Never follow a suggested route into floodwater."),
    (("data", "live weather", "real weather", "temperature", "rain probability", "map"),
     "The Live Weather & Map tab requests weather-provider data from Open-Meteo for approximate Chennai neighbourhood coordinates and displays OpenStreetMap tiles. Availability depends on your internet connection. These weather values are not direct flood-depth measurements or official warnings."),
    (("year round", "other months", "dry season", "off season", "all year"),
     "Storm and flood risk reduction is year-round: map repeat waterlogging spots, report blocked drains, maintain rainwater outlets, protect electrical systems, update emergency contacts, prepare go-bags, identify vulnerable neighbours, and review shelter readiness before monsoon. The Prevention tab has a seasonal checklist."),
    (("tamil", "தமிழ்"),
     "மழை அல்லது வெள்ள அபாயம் ஏற்பட்டால் அதிகாரப்பூர்வ IMD மற்றும் SACHET எச்சரிக்கைகளைப் பின்பற்றவும். வெள்ளநீரில் நடக்கவோ வாகனம் ஓட்டவோ வேண்டாம். பாதுகாப்பான உயரமான இடத்திற்குச் செல்லவும். இந்த Storm Watch செயலி உதவி தகவலுக்கான முன்மாதிரி மட்டுமே; அதிகாரப்பூர்வ எச்சரிக்கை அல்ல. IMD: https://mausam.imd.gov.in/ · SACHET: https://sachet.ndma.gov.in/"),
]

def answer_citizen_question(question: str) -> str:
    q = question.lower().strip()
    if not q:
        return "Ask me about weather data, dashboard scores, flood/storm prevention, shelters, or what to do before/during/after flooding."
    for keywords, answer in QA_KNOWLEDGE:
        if any(k in q for k in keywords):
            return answer
    if gemini_configured():
        try:
            prompt = ("You are Storm Watch's public preparedness Q&A assistant. Answer in simple language, preferably concise. "
                      "Use general flood/storm preparedness information only. Do not claim to know live warnings, flood depth, "
                      "safe roads, shelter availability, or local official decisions. Never invent phone numbers or emergency "
                      "contacts. For urgent/current conditions, direct the user to IMD Mausam https://mausam.imd.gov.in/ and "
                      "NDMA SACHET https://sachet.ndma.gov.in/. State that this app is not an official alert service. "
                      "If the question asks for an evacuation route or current safety decision, tell them to follow local authorities.\n\n"
                      "User question: " + question[:800])
            generated = _call_gemini(prompt).strip()
            if 20 <= len(generated) <= 1800:
                return generated + "\n\nFor current official warnings, verify IMD Mausam and NDMA SACHET. Storm Watch is not an official alert service."
        except Exception:
            pass
    return ("I can help explain the dashboard, live weather fields, flood and storm preparedness, or shelter/route demo. "
            "For current official warnings, check IMD Mausam (https://mausam.imd.gov.in/) and NDMA SACHET "
            "(https://sachet.ndma.gov.in/). I cannot verify real-time flood depth, road safety, or official evacuation routes.")

PREVENTION_TASKS = {
    "All year": [
        "Record recurring waterlogging locations and report them to the local body",
        "Keep emergency contacts and family meeting point updated",
        "Prepare a waterproof pouch for ID documents, medicines and essential numbers",
        "Check on older adults, children and neighbours who may need assistance",
        "Learn official warning channels and practise a family communication plan",
    ],
    "Pre-monsoon (Feb–May)": [
        "Ask the local authority to inspect and clear storm-water drains; never enter drains",
        "Check roof, balcony and yard drainage; secure loose outdoor objects",
        "Raise or protect electrical sockets, appliances and important documents where feasible",
        "Review local flood history and identify safe higher-ground meeting points",
        "Check first-aid kit, torch, batteries, power bank, drinking water and medicines",
    ],
    "Monsoon (Jun–Sep)": [
        "Monitor IMD and SACHET alerts each day and before travel",
        "Report blocked drains and new waterlogging without entering hazardous areas",
        "Avoid walking/driving through floodwater and do not touch wet electrical equipment",
        "Keep phones charged and essential items ready in case authorities advise evacuation",
        "Follow local-authority guidance and check on vulnerable neighbours when safe",
    ],
    "Post-monsoon (Oct–Jan)": [
        "Document recurring flood points and submit them to the local authority",
        "Inspect water-damaged wiring/buildings through qualified professionals before reuse",
        "Restock used emergency supplies and replace expired medicines/batteries",
        "Review what worked and update family/community preparedness plans",
        "Maintain gutters/outlets safely and arrange repairs before the next rainy season",
    ],
}

# ---------------- callbacks (run before the page re-renders) ----------------
def flash(res):
    st.session_state.flash = res


def sync_defaults():
    r, s = sw.suggested_road(), sw.suggested_shelter()
    if r:
        st.session_state["road_sel"] = r
    if s:
        st.session_state["shelter_sel"] = s


def cb_alert(): flash(sw.generate_alert(st.session_state.get("alert_sel")))
def cb_plan(): flash(sw.create_plan()); sync_defaults()
def cb_replan(): flash(sw.replan())
def cb_block(): flash(sw.block_road(st.session_state["road_sel"]))
def cb_restore(): flash(sw.restore_road(st.session_state["road_sel"]))
def cb_full(): flash(sw.mark_shelter_full(st.session_state["shelter_sel"]))
def cb_unfull(): flash(sw.reset_shelter(st.session_state["shelter_sel"]))
def cb_en(): flash(sw.generate_advisory("en"))
def cb_ta(): flash(sw.generate_advisory("ta"))
def cb_approve(): flash(sw.approve())
def cb_reject(): flash(sw.reject())


def cb_reset():
    sw.reset()
    for k in ("road_sel", "shelter_sel", "alert_sel"):
        st.session_state.pop(k, None)
    flash(("success", "Scenario reset to its initial state."))


# ---------------- sidebar controls ----------------
data = sw.data
with st.sidebar:
    st.markdown("### 🎛️ Control panel")
    st.caption("Live weather is shown in the Live Weather & Map tab. Response-planning controls still use illustrative demo data.")
    st.selectbox("Simulated alert", [a["id"] for a in data["alerts"]], key="alert_sel",
                 format_func=lambda i: next(a["title"] for a in data["alerts"] if a["id"] == i))
    st.button("⚠️ Generate Flood Alert", on_click=cb_alert, **S, key="b_alert")
    st.button("🗺️ Create Response Plan", on_click=cb_plan, **S, type="primary", key="b_plan")
    st.button("🔄 Replan Response", on_click=cb_replan, **S, key="b_replan")
    st.markdown("---")
    used = sw.roads_in_plan()
    st.selectbox("Road X", [r["id"] for r in data["roads"]["roads"]], key="road_sel",
                 format_func=lambda i: f"{i} · {sw.road_names[i]}" + (" ⛔ BLOCKED" if i in sw.blocked else "") + (" ★ on a planned route" if i in used else ""))
    c1, c2 = st.columns(2)
    c1.button("⛔ Block Road X", on_click=cb_block, **S, key="b_block")
    c2.button("✅ Restore Road X", on_click=cb_restore, **S, key="b_restore")
    st.selectbox("Shelter", [s["id"] for s in data["shelters"]], key="shelter_sel",
                 format_func=lambda i: sw.shelter_names[i] + (" 🔴 FULL" if i in sw.full_shelters else ""))
    c3, c4 = st.columns(2)
    c3.button("🏠 Mark Shelter Full", on_click=cb_full, **S, key="b_full")
    c4.button("♻️ Reset Capacity", on_click=cb_unfull, **S, key="b_unfull")
    st.markdown("---")
    c5, c6 = st.columns(2)
    c5.button("📝 English Advisory", on_click=cb_en, **S, key="b_en")
    c6.button("📝 Tamil Advisory", on_click=cb_ta, **S, key="b_ta")
    st.markdown("---")
    with st.expander("⚖️ Risk weights (configurable)"):
        w = sw.config["weights"]
        w["exposure"] = st.slider("Flood exposure", 0.0, 1.0, float(w["exposure"]), 0.05)
        w["population"] = st.slider("Population", 0.0, 1.0, float(w["population"]), 0.05)
        w["vulnerable"] = st.slider("Vulnerable residents", 0.0, 1.0, float(w["vulnerable"]), 0.05)
        st.caption("Weights are normalised. Click **Replan Response** to apply.")
    st.button("🧹 Reset Entire Scenario", on_click=cb_reset, **S, key="b_reset")
    st.caption(f"AI mode: {gemini_status()}")

# ---------------- header, banner, messages ----------------
st.markdown(f"""<div class="sw-header">{(ROOT / 'assets' / 'logo.svg').read_text(encoding='utf-8').replace('width="64" height="64"', 'width="52" height="52"')}
<div><h1>Storm Watch</h1><div class="sub">AI-Assisted Flood Response Planning · from warning to prioritised action</div></div>
<div class="sw-badge">LIVE WEATHER · DEMO RESPONSE DATA</div></div>""", unsafe_allow_html=True)

if sw.alert:
    colour = {"red": "#C1121F", "orange": "#E8590C"}.get(sw.alert["severity"], "#E8590C")
    st.markdown(f'<div class="sw-banner" style="background:{colour}">🚨 {escape(sw.alert["title"])} — issued {sw.alert["issued_at"]} (SIMULATED)<br>'
                f'<span style="font-weight:400">{escape(sw.alert["summary"])}</span></div>', unsafe_allow_html=True)
else:
    st.info("No active alert. Press **Generate Flood Alert** in the control panel to begin the simulated scenario.")

fl = st.session_state.get("flash")
if fl:
    getattr(st, {"success": "success", "warning": "warning", "error": "error"}.get(fl[0], "info"))(fl[1])
    st.session_state.flash = None

# workflow pipeline
ap = sw.approval_status()
steps = [("Alert Input", bool(sw.alert)), ("Risk Analysis", bool(sw.plan)), ("Shelter Allocation", bool(sw.plan)),
         ("Route Planning", bool(sw.plan)), ("Volunteer Assignment", bool(sw.plan)),
         ("Advisory Generation", bool(sw.advisories["en"])), ("Human Approval", ap == "approved")]
st.markdown(" ➜ ".join(f'<span class="sw-step" style="background:{"#0B1F3A" if ok else "#E6ECF5"};color:{"#fff" if ok else "#5C7AA6"}">{"✔ " if ok else ""}{n}</span>'
                        for n, ok in steps), unsafe_allow_html=True)

plan = sw.plan
if plan:
    total = sum(r["population"] for r in plan["risk"])
    unplaced = sum(u["people"] for u in plan["unserved"])
    m = st.columns(5)
    m[0].metric("Areas affected", len(plan["risk"]))
    m[1].metric("People to evacuate", total)
    m[2].metric("Placed in shelters", total - unplaced)
    m[3].metric("Unplaced", unplaced)
    m[4].metric("Plan version", f"v{sw.plan_version}")
    if ap == "approved":
        st.success(f"✅ Advisory APPROVED for plan v{sw.approval['approved_version']} at {sw.approval['timestamp']} (simulated status only).")
    elif ap == "outdated":
        st.warning(f"⚠️ Previously approved plan is OUTDATED. Plan v{sw.plan_version} needs renewed human approval.")
    elif ap == "rejected":
        st.error(f"❌ Advisory for plan v{sw.approval['plan_version']} was REJECTED at {sw.approval['timestamp']}.")
    elif ap == "pending":
        st.warning(f"⏳ Plan v{sw.plan_version} is awaiting officer approval (Advisory tab).")
    for wmsg in plan["warnings"]:
        st.error(wmsg)

tabs = st.tabs(["👤 Citizen Dashboard & Q&A", "🌦️ Live Weather & Map", "📊 Response Overview", "🏠 Shelters & Routes", "🧑‍🤝‍🧑 Volunteers", "📢 Advisory & Approval", "🧾 Activity Log", "📘 Method & Limits", "🛡️ Year-round Prevention"])
LEVEL_COLOR = {"CRITICAL": "#D7263D", "HIGH": "#FF6A13", "MODERATE": "#F2B134"}

with tabs[0]:
    st.title("Citizen Dashboard")
    st.write("A simple place to understand weather information, prepare year-round, and ask questions in plain language.")
    st.warning("Storm Watch is an informational prototype, not an official alert or emergency-dispatch service. Verify warnings with IMD/SACHET.")
    quick = st.columns(3)
    quick[0].metric("Live weather", "Open Weather tab", help="Current conditions are fetched when the Live Weather tab is opened.")
    quick[1].metric("Preparedness", "All year", help="Prevention checklist covers all seasons, not just rainy months.")
    quick[2].metric("Q&A assistant", "Available", help="Built-in answers work without an API key; Gemini is optional elsewhere in the app.")
    st.subheader("🌦️ Quick live weather check")
    wx_place = st.selectbox("Choose your Chennai-area location", list(LIVE_PLACES.keys()), key="citizen_weather_place")
    if st.button("Get current weather", key="citizen_get_weather", type="primary"):
        coords = LIVE_PLACES[wx_place]
        try:
            wx = fetch_live_weather(wx_place, coords["lat"], coords["lon"])
            cur = wx["current"]
            code = int(cur.get("weather_code", -1))
            st.session_state.citizen_weather_result = {"place": wx_place, "data": cur, "label": WEATHER_LABELS.get(code, f"Weather code {code}")}
        except Exception as exc:
            st.session_state.citizen_weather_result = {"error": type(exc).__name__}
    wx_result = st.session_state.get("citizen_weather_result")
    if wx_result:
        if wx_result.get("error"):
            st.warning("Live weather is unavailable right now. Check your internet and try again; no simulated weather is shown.")
        else:
            cur = wx_result["data"]
            st.caption(f"{wx_result['place']} · {wx_result['label']} · Provider time: {cur.get('time', '—')}")
            wm = st.columns(4)
            wm[0].metric("Temperature", f"{cur.get('temperature_2m', '—')} °C")
            wm[1].metric("Rain now", f"{cur.get('precipitation', '—')} mm")
            wm[2].metric("Humidity", f"{cur.get('relative_humidity_2m', '—')}%")
            wm[3].metric("Wind", f"{cur.get('wind_speed_10m', '—')} km/h")
            st.caption("Provider data is not an official warning or flood-depth measurement. Verify warnings with IMD/SACHET.")
    st.subheader("💬 Ask Storm Watch")
    st.caption("Try: ‘What does the risk score mean?’, ‘How can I prevent floods before monsoon?’, ‘What should I do during a storm?’, or ask in Tamil.")
    with st.form("citizen_qa_form", clear_on_submit=True):
        user_q = st.text_input("Your question", placeholder="How do I prepare my home before heavy rain?")
        submitted = st.form_submit_button("Ask assistant", type="primary")
    if "citizen_chat" not in st.session_state:
        st.session_state.citizen_chat = []
    if submitted and user_q.strip():
        st.session_state.citizen_chat.append({"q": user_q.strip(), "a": answer_citizen_question(user_q)})
    for item in reversed(st.session_state.citizen_chat[-8:]):
        with st.chat_message("user"):
            st.write(item["q"])
        with st.chat_message("assistant"):
            st.write(item["a"])
    if st.button("Clear Q&A history", key="clear_citizen_chat"):
        st.session_state.citizen_chat = []
        st.rerun()
    st.subheader("Quick help")
    qa_cols = st.columns(2)
    quick_questions = ["How do I prepare before a flood?", "What should I do during a storm?", "What does the dashboard risk score mean?", "How do I verify an official warning?"]
    for idx, q in enumerate(quick_questions):
        if qa_cols[idx % 2].button(q, key=f"quick_q_{idx}", **S):
            st.session_state.citizen_chat.append({"q": q, "a": answer_citizen_question(q)})
            st.rerun()
    st.markdown("**Official links:** [IMD Mausam](https://mausam.imd.gov.in/index_en.php) · [NDMA SACHET](https://sachet.ndma.gov.in/) · [Government flood safety guidance](https://dgfscdhg.gov.in/floods)")
    st.caption("Q&A mode: optional Gemini-assisted answers when GEMINI_API_KEY is configured; otherwise built-in safety FAQ answers are used. No API key is required for the main app.")
    st.subheader("📍 Community hazard note (local demo only)")
    st.caption("Record a waterlogging or blocked-drain observation for this browser session. This does not submit it to the government or emergency services.")
    with st.form("hazard_note_form", clear_on_submit=True):
        h1, h2 = st.columns(2)
        hazard_place = h1.selectbox("Area", list(LIVE_PLACES.keys()), key="hazard_place")
        hazard_type = h2.selectbox("Observation", ["Waterlogging", "Blocked drain", "Fallen tree", "Loose/damaged electrical wire", "Other hazard"], key="hazard_type")
        hazard_severity = st.select_slider("Observed concern", options=["Low", "Medium", "High"], value="Medium", key="hazard_severity")
        hazard_note = st.text_area("Short description (do not include names, phone numbers or private details)", max_chars=300, key="hazard_note")
        hazard_submit = st.form_submit_button("Save local note")
    if "hazard_notes" not in st.session_state:
        st.session_state.hazard_notes = []
    if hazard_submit:
        if hazard_note.strip():
            st.session_state.hazard_notes.append({"area": hazard_place, "type": hazard_type, "severity": hazard_severity, "note": hazard_note.strip()[:300]})
            st.success("Saved to this app session only. No external report was sent.")
        else:
            st.warning("Please add a short description before saving.")
    if st.session_state.hazard_notes:
        st.dataframe(st.session_state.hazard_notes, **S, hide_index=True)
        if st.button("Clear local hazard notes", key="clear_hazard_notes"):
            st.session_state.hazard_notes = []
            st.rerun()

with tabs[1]:
    st.subheader("Live weather across Chennai")
    st.caption("Live observations and forecasts from Open-Meteo. Map tiles © OpenStreetMap contributors. Weather data is not an official disaster warning; confirm warnings with IMD/SACHET.")
    wleft, wright = st.columns([1, 1.5])
    live_records = []
    with wleft:
        if st.button("🔄 Refresh live weather", key="refresh_live_weather", **S):
            fetch_live_weather.clear()
        for place, coords in LIVE_PLACES.items():
            try:
                payload = fetch_live_weather(place, coords["lat"], coords["lon"])
                cur = payload["current"]
                code = int(cur.get("weather_code", -1))
                label = WEATHER_LABELS.get(code, f"Weather code {code}")
                hourly = payload.get("hourly", {})
                times = hourly.get("time", [])
                probs = hourly.get("precipitation_probability", [])
                rain = hourly.get("precipitation", [])
                # Find the first forecast hour at or after current provider time.
                now = cur.get("time", "")
                next_i = next((i for i, t in enumerate(times) if t >= now), 0) if times else 0
                next_prob = probs[next_i] if next_i < len(probs) else None
                next_rain = rain[next_i] if next_i < len(rain) else None
                record = {"place": place, "lat": coords["lat"], "lon": coords["lon"], "current": cur,
                          "label": label, "time": now, "precip_prob": next_prob, "precip_next": next_rain}
                live_records.append(record)
                with st.container(border=True):
                    st.markdown(f"**{place}** · {label}")
                    a, b = st.columns(2)
                    a.metric("Temperature", f"{cur.get('temperature_2m', '—')} °C", help="Current provider observation/model value")
                    b.metric("Rain now", f"{cur.get('precipitation', '—')} mm")
                    c, d = st.columns(2)
                    c.metric("Humidity", f"{cur.get('relative_humidity_2m', '—')}%")
                    d.metric("Rain probability", f"{next_prob}%" if next_prob is not None else "—")
                    st.caption(f"Updated by provider: {now} · Wind {cur.get('wind_speed_10m', '—')} km/h · Next hourly precipitation: {next_rain if next_rain is not None else '—'} mm")
            except Exception as exc:
                st.warning(f"{place}: live weather unavailable right now ({type(exc).__name__}). No simulated value is substituted.")
    with wright:
        st.markdown("#### Real geographic map")
        center = [13.0, 80.24]
        fmap = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap", control_scale=True)
        if live_records:
            for rec in live_records:
                c = rec["current"]
                popup = (f"<b>{escape(rec['place'])}</b><br>{escape(rec['label'])}<br>"
                         f"Temperature: {c.get('temperature_2m', '—')} °C<br>"
                         f"Rain now: {c.get('precipitation', '—')} mm<br>"
                         f"Humidity: {c.get('relative_humidity_2m', '—')}%<br>"
                         f"Rain probability: {rec['precip_prob'] if rec['precip_prob'] is not None else '—'}%<br>"
                         f"Provider time: {escape(rec['time'])}")
                color = "red" if (rec["precip_prob"] is not None and rec["precip_prob"] >= 70) else "orange" if (rec["precip_prob"] is not None and rec["precip_prob"] >= 40) else "blue"
                folium.CircleMarker([rec["lat"], rec["lon"]], radius=9, color=color, fill=True, fill_opacity=0.85,
                                    tooltip=f"{rec['place']} · {rec['label']}", popup=folium.Popup(popup, max_width=260)).add_to(fmap)
            st_folium(fmap, height=620, use_container_width=True, returned_objects=[])
        else:
            st_folium(fmap, height=620, use_container_width=True, returned_objects=[])
            st.info("No live weather data loaded yet. Check internet access and press Refresh live weather.")
    st.info("Important: these are real weather-provider values at approximate neighborhood coordinates, not official flood-risk classifications. The shelter capacities, population figures, volunteer availability, and road closures in the response-planning tabs remain simulated. Routes are not verified evacuation guidance.")

with tabs[2]:
    left, right = st.columns([5, 6])
    with left:
        st.subheader("Affected-area risk ranking")
        if not plan:
            st.caption("Create a response plan to see the ranking.")
        for i, r in enumerate(plan["risk"] if plan else [], 1):
            f = r["factors"]
            seg = "".join(f'<div title="{k}: {f[k]["points"]}" style="width:{f[k]["points"]}%;background:{c}"></div>'
                          for k, c in (("exposure", "#0B1F3A"), ("population", "#4F6FA3"), ("vulnerable", "#FF6A13")))
            st.markdown(f'<div class="sw-card"><b>#{i} {escape(r["name"])}</b> <span class="sw-pill" style="background:{LEVEL_COLOR[r["level"]]}">{r["level"]}</span>'
                        f' <span style="float:right"><b>{r["score"]}</b> / 100</span><div class="sw-bar" style="margin:6px 0">{seg}</div>'
                        f'<small>exposure {f["exposure"]["points"]} · population {f["population"]["points"]} · vulnerable {f["vulnerable"]["points"]} '
                        f'(pop {r["population"]}, vulnerable {r["vulnerable"]})</small></div>', unsafe_allow_html=True)
        if plan and sw.explanation:
            with st.expander("Plain-language explanation (" + sw.explanation["source"] + ")"):
                st.text(sw.explanation["text"])
    with right:
        st.subheader("Scenario map")
        components.html(render_map_svg(sw), height=560)

with tabs[3]:
    st.subheader("Shelter occupancy & remaining capacity")
    if plan:
        cols = st.columns(len(plan["shelter_status"]))
        for col, s in zip(cols, plan["shelter_status"]):
            with col:
                st.markdown(f"**{s['name']}**" + (" 🔴 FULL" if s["marked_full"] else ""))
                used_now = s["occupancy"] + s["planned_additional"]
                st.progress(min(1.0, used_now / s["capacity"]))
                st.caption(f"{used_now}/{s['capacity']} after plan · now {s['occupancy']} · +{s['planned_additional']} planned · {max(0, s['remaining_after_plan'])} free")
    else:
        for s in data["shelters"]:
            st.write(f"**{s['name']}** — {s['initial_occupancy']}/{s['capacity']} occupied" + (" 🔴 FULL" if s["id"] in sw.full_shelters else ""))
    st.subheader("Recommended evacuation routes (Dijkstra)")
    if plan and plan["assignments"]:
        st.dataframe([{"Area": a["area_name"], "People": a["people"], "Shelter": a["shelter_name"],
                       "Route": " → ".join(a["route"]["path_names"]), "Roads": ", ".join(a["route"]["road_ids"]),
                       "Sim. travel (min)": a["route"]["cost"]} for a in plan["assignments"]], **S, hide_index=True)
    elif plan:
        st.error("No feasible route or shelter was found for any area.")
    for u in (plan or {"unserved": []})["unserved"]:
        st.error(f"{u['area_name']}: {u['people']} people unplaced — {u['reason']}")
    if sw.blocked:
        st.warning("Blocked roads: " + ", ".join(f"{i} ({sw.road_names[i]})" for i in sorted(sw.blocked)))

with tabs[4]:
    st.subheader("Volunteer assignments")
    if plan:
        by_id = {v["id"]: v for v in data["volunteers"]}
        st.dataframe([{"Volunteer": v["name"], "Area": next(r["name"] for r in plan["risk"] if r["area_id"] == v["area_id"]),
                       "Role needed": v["skill_needed"], "Skill match": "✔" if v["skill_matched"] else "✖ general support",
                       "Reason": v["reason"]} for v in plan["volunteers"]], **S, hide_index=True)
        for g in plan["volunteer_gaps"]:
            st.warning(f"Unfilled slot at {g['area_id']} ({g['skill']}): {g['reason']}")
        assigned = {v["volunteer_id"] for v in plan["volunteers"]}
        st.caption("Not assigned: " + (", ".join(f"{v['name']}" + ("" if v["available"] else " (unavailable)") for v in data["volunteers"] if v["id"] not in assigned) or "none"))
    else:
        st.dataframe([{"Volunteer": v["name"], "Skills": ", ".join(v["skills"]), "Available": "yes" if v["available"] else "no"} for v in data["volunteers"]],
                     **S, hide_index=True)

with tabs[5]:
    st.subheader("Advisory drafts & human approval")
    st.info("Every public-facing advisory needs officer approval. Approval only changes the simulated status — **no SMS, WhatsApp, email or alert is ever sent.**")
    ca, cb = st.columns(2)
    for col, key, label in ((ca, "en", "English"), (cb, "ta", "தமிழ் (Tamil)")):
        with col:
            adv = sw.advisories[key]
            st.markdown(f"**{label}**")
            if adv:
                st.text_area(label, adv["text"], height=330, disabled=True, label_visibility="collapsed")
                st.caption(f"Source: {adv['source']} · plan v{adv['plan_version']} · {adv['generated_at']} · {adv['note']}")
            else:
                st.caption("Not drafted yet.")
    st.markdown(f"**Plan ID:** `SW-{sw.alert['id'] if sw.alert else '-'}-v{sw.plan_version}` · **Status:** `{ap.upper()}`"
                + (f" · **Timestamp:** {sw.approval['timestamp']}" if sw.approval.get("timestamp") else ""))
    b1, b2, _ = st.columns([1, 1, 3])
    b1.button("✅ Approve Advisory", on_click=cb_approve, type="primary", **S, key="b_approve")
    b2.button("❌ Reject Advisory", on_click=cb_reject, **S, key="b_reject")
    if sw.changes:
        st.subheader("What changed and why")
        for c in reversed(sw.changes):
            with st.expander(f"v{c['version']} · {c['time']} · {c['trigger']}", expanded=c is sw.changes[-1]):
                for line in c["lines"]:
                    st.write("• " + line)

with tabs[6]:
    st.subheader("Agent activity log")
    icon = {"info": "🔹", "success": "🟢", "warning": "🟠", "error": "🔴"}
    for e in reversed(sw.log):
        st.markdown(f"{icon.get(e['level'], '🔹')} `{e['time']}` **{e['agent']}** — {e['message']}")

with tabs[7]:
    st.markdown("""
**Risk score (0–100)** = 100 × (w_exposure × exposure + w_population × population ÷ max_population + w_vulnerable × vulnerable ÷ max_vulnerable),
with weights normalised to sum to 1. Levels: ≥70 CRITICAL, ≥50 HIGH, otherwise MODERATE.

**Shelters:** areas are handled in risk order; each takes the lowest-cost reachable shelter with free places, splitting groups across shelters if needed. Capacity is never exceeded.
**Routes:** NetworkX Dijkstra on simulated travel minutes; blocked roads are removed from the graph. **Volunteers:** skill match first, then nearest; one task each.

**Limitations:** live weather comes from Open-Meteo and the Live Weather tab uses real map tiles; response-planning data and routes remain illustrative. Travel times ignore traffic, depth of water and vehicle type; scores are relative, not absolute;
Gemini (if enabled) only rewords calculated facts and is validated, with template fallback. Not for real emergency use. Tamil drafts should be reviewed by a fluent speaker.
""")


with tabs[8]:
    st.title("Year-round Flood & Storm Prevention")
    st.write("Preparedness matters outside the rainy season too. Use this checklist for community readiness; actions involving drains, electricity or buildings should be handled by qualified people or local authorities.")
    season = st.selectbox("Choose a planning period", list(PREVENTION_TASKS.keys()), index=0, key="prevention_season")
    tasks = PREVENTION_TASKS[season]
    st.caption(f"{len(tasks)} recommended preparation actions · check items as you complete them; checks are kept for this app session only.")
    done_key = "prevention_done_" + season
    if done_key not in st.session_state:
        st.session_state[done_key] = []
    completed = []
    for i, task in enumerate(tasks):
        checked = st.checkbox(task, value=i in st.session_state[done_key], key=f"{done_key}_{i}")
        if checked:
            completed.append(i)
    st.session_state[done_key] = completed
    st.progress(len(completed) / max(1, len(tasks)))
    st.write(f"**Progress:** {len(completed)} of {len(tasks)} tasks completed")
    if st.button("Reset this checklist", key="reset_prevention_checklist"):
        st.session_state[done_key] = []
        for i in range(len(tasks)):
            st.session_state.pop(f"{done_key}_{i}", None)
        st.rerun()
    st.subheader("Suggested annual rhythm")
    st.markdown("- **All year:** document recurring waterlogging, update contacts, build awareness and check on neighbours.\n- **Before monsoon:** request drain inspections, check drainage and prepare supplies.\n- **During monsoon:** monitor official warnings, report hazards and avoid floodwater.\n- **After monsoon:** review incidents, restock kits and plan repairs.")
    st.info("Prevention actions reduce avoidable exposure but cannot guarantee that flooding or storms will be prevented. Do not enter drains, touch electrical equipment in wet areas, or use this prototype to choose a real evacuation route.")
    st.markdown("**Guidance:** [NDMA flood management guidelines](https://nidm.gov.in/PDF/guidelines/floods.pdf) · [Government flood safety advice](https://dgfscdhg.gov.in/floods) · [IMD Mausam](https://mausam.imd.gov.in/index_en.php) · [SACHET alerts](https://sachet.ndma.gov.in/)")
