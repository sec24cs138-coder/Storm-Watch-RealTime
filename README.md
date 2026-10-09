# 🌊 Storm Watch — Live Weather + Flood Response Planning Demo

Storm Watch turns a flood *warning* into a prioritised *response plan*: it ranks affected areas, allocates shelters and
volunteers, plans evacuation routes (NetworkX / Dijkstra), drafts English + Tamil advisories, and **replans** when a road is
blocked or a shelter fills up. Every advisory needs **human approval**.

> ⚠️ **Mixed live/demo prototype.** The Live Weather & Map tab fetches current weather and hourly forecast values from Open-Meteo and shows real map tiles from OpenStreetMap. The response-planning dataset (populations, vulnerability, shelter capacities, volunteers, road network/closures and resulting routes) remains illustrative. This app is not an official alert system and must not be used as evacuation or safety guidance. It does not send alerts or contact emergency services.

## New citizen-facing features
- **Citizen Dashboard & Q&A:** plain-language answers for dashboard interpretation, flood/storm preparation, and safety basics; includes official IMD/SACHET links and Tamil guidance. Built-in FAQ mode works without an API key.
- **Year-round Prevention:** season-based checklist for all-year readiness, pre-monsoon preparation, monsoon response and post-monsoon review. Checklist progress is session-only.
- Existing Live Weather & Map, response-planning demo, shelters/routes, volunteers, advisory approval and activity log remain available.

Preparedness content is general guidance, not a substitute for local authorities. Do not use illustrative routes or shelters as real evacuation directions.

## Requirements
* Python **3.10 or newer** (https://www.python.org/downloads/ — on Windows tick *Add Python to PATH*)
* Internet on the first run only (to install dependencies). No API key is needed for Open-Meteo weather. Internet is required for live weather, map tiles, and first-time dependency installation.

## Run it
1. **Extract** `StormWatch.zip` (right-click → *Extract All…* on Windows). Don't run it from inside the zip.
2. **Windows:** double-click `run.bat` (it checks Python, creates `.venv`, installs dependencies, starts Streamlit).
   **Linux/macOS:** `chmod +x run.sh && ./run.sh`
3. Your browser opens at **http://localhost:8501**. Stop with `Ctrl+C` in the terminal window.

Manual alternative: `python -m venv .venv`, activate it, `pip install -r requirements.txt`, `streamlit run app.py`.

## Optional: Gemini
The app works fully **without** a key (template-based advisories and explanations).
1. Get a key from Google AI Studio.
2. Copy `.env.example` to `.env` and set `GEMINI_API_KEY=your_key` (or set it as an environment variable). Never commit `.env`.
3. Restart. The sidebar shows "Gemini enabled (with template fallback)".

Uses the official `google-genai` SDK (`from google import genai`). The default model is `gemini-3-flash-preview`;
if Google renames/retires it, set `GEMINI_MODEL=<model name>` in `.env`. Gemini only receives the already-calculated
facts and may only reword them; its output is validated (no invented numbers, all assigned shelters named, simulation
label present, correct language) and replaced by the template if validation or the API call fails. It never decides
routes, capacity or safety.

## Demo script (≈3 minutes)
1. Sidebar → **Generate Flood Alert** (Orange alert: Velachery, Adyar, Taramani) → **Create Response Plan**.
   Plan v1: Velachery 520 → Perungudi Community Hall (R1, 12 min); Adyar 450 → Govt School (R4); Taramani 380 → Engineering College (R7).
2. Open **Advisory & Approval**, read both drafts, press **Approve Advisory** (status APPROVED, timestamp, plan v1).
3. Sidebar → *Road X* is preselected as **R1** (★ on a planned route) → **Block Road X**.
   Replanning runs automatically: Velachery is split (480 → School via R11, 40 → Hall via R2+R10), Adyar moves to the Hall, advisories are regenerated, and the approval shows **OUTDATED — renewed approval required**. See *What changed and why* and the **Activity Log**.
4. *Shelter* is preselected as **Perungudi Community Hall** → **Mark Shelter Full**. The plan reassigns to the Engineering College where possible, and
   reports the people who cannot be placed ("No feasible shelter found") instead of overfilling anything.
5. Review and **Approve** (or **Reject**) the new advisory. **Restore Road X** / **Reset Capacity** undo the disruptions.
6. Choose the **Red alert** (4 areas) to see capacity run short. **Reset Entire Scenario** returns everything to the start.

## Project layout
```
app.py                 Streamlit dashboard
src/risk_engine.py     transparent risk scoring
src/route_engine.py    NetworkX graph + Dijkstra, blocked roads removed
src/shelter_engine.py  capacity rules and allocation
src/volunteer_engine.py skill/availability/workload assignment
src/planner.py         risk -> shelters -> routes -> volunteers, plan diffs
src/advisory_engine.py English/Tamil templates + optional validated Gemini
src/state_manager.py   scenario state, replanning, approval logic, activity log
src/map_view.py        schematic SVG scenario map for the illustrative planning model
Live Weather & Map tab  Open-Meteo live conditions + OpenStreetMap geography
data/*.json            simulated alerts, areas, roads, shelters, volunteers
tests/                 unittest/pytest tests
```

## Risk formula and limitations
`score = 100 × (w_exposure·exposure + w_population·pop/max_pop + w_vulnerable·vulnerable/max_vulnerable)`, weights normalised to sum to 1
(defaults 0.50 / 0.25 / 0.25; adjustable in the sidebar, click *Replan* to apply). Range 0–100; ≥70 CRITICAL, ≥50 HIGH, else MODERATE.
Vulnerable = elderly + children + people with disabilities (capped at population).
Limits: response-planning inputs are invented; live weather is not the same as flood observations or official warnings. Risk scores do not combine terrain, tide, drainage, river levels, or verified flood reports. Travel time remains a fixed simulated cost with no live traffic. The Live Weather & Map tab is geographic, but the original response-planning route map remains schematic and the displayed routes are not verified evacuation routes. Areas are handled in risk order; groups may be split across shelters.

## Troubleshooting
* **"Python not found"** — install Python 3.10+ and tick *Add Python to PATH*; reopen the window.
* **pip install fails** — check internet/proxy; run `run.bat` again.
* **Port 8501 busy** — `streamlit run app.py --server.port 8502` (inside the activated venv).
* **Gemini shows "template fallback used"** — key missing/invalid, model name changed (set `GEMINI_MODEL`), no internet, or the output failed validation. The app keeps working.
* **Tamil text looks like boxes** — use a current browser; Tamil drafts should also be reviewed by a fluent speaker before any real use.
* **venv error on Linux** — `sudo apt install python3-venv`.

## Test results (what was actually run before packaging)
Run: `python -m unittest discover -s tests -t .` (also compatible with `pytest`).
* 27 tests ran in the build environment, **all passed**: risk scores within 0–100 and factor points sum to the score; weight validation;
  blocked roads excluded and costs rise; no-route and unknown-node return `None`; capacity never exceeded and full shelters never assigned across
  every combination of up to 3 blocked roads × 3 shelter-full settings; all-shelters-full and unreachable-shelter cases report "No feasible shelter/route";
  placed + unplaced always equals population; block/restore/full/reset replanning; approval becomes OUTDATED after a changed plan and survives an unchanged one;
  no-key template fallback; simulated Gemini failure falls back and the key never appears in notes or logs; invented numbers in AI output are rejected; required files exist, `.env` absent.
* The dashboard code was exercised end-to-end (all 12 control buttons, approve/reject, reset) against a **stub** of Streamlit's API because
  Streamlit could not be installed in the build sandbox (no internet).
  **Not verified:** the app has not been launched in a real Streamlit/browser session; `run.bat` was syntax-checked only by inspection and
  `run.sh` with `bash -n`; real Gemini calls were never made (no key/network), so the default model name is untested; the visual layout is untested on real screens.
