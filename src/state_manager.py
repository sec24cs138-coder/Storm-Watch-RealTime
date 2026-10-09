"""Scenario state + actions used by the dashboard. Every action returns (level, message)."""
import json
from datetime import datetime
from pathlib import Path

from .planner import build_plan, diff_plans, plan_signature, default_config
from .advisory_engine import build_facts, generate_advisory, explain_plan

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_data(data_dir=DATA_DIR):
    d = Path(data_dir)
    load = lambda n: json.loads((d / n).read_text(encoding="utf-8"))
    return {"areas": load("areas.json"), "shelters": load("shelters.json"), "roads": load("roads.json"),
            "volunteers": load("volunteers.json"), "alerts": load("sample_alerts.json")}


def _now():
    return datetime.now().strftime("%H:%M:%S")


class ScenarioState:
    def __init__(self, data=None, use_ai=True):
        self.data = data or load_data()
        self.use_ai = use_ai
        self.config = default_config()
        self.log = []
        self.reset(log=False)

    # ----- helpers -----
    def _log(self, agent, msg, level="info"):
        self.log.append({"time": _now(), "agent": agent, "message": msg, "level": level})

    def reset(self, log=True):
        self.alert = None
        self.blocked = set()
        self.full_shelters = set()
        self.plan = None
        self.plan_version = 0
        self.advisories = {"en": None, "ta": None}
        self.explanation = None
        self.changes = []
        self.approval = {"status": "none", "plan_version": None, "timestamp": None, "approved_version": None}
        self.log = []
        if log:
            self._log("Operator", "Entire scenario reset to its initial state.", "success")
        else:
            self._log("System", "Storm Watch ready. All data is SIMULATED.")
        self.config = default_config()

    @property
    def road_names(self):
        return {r["id"]: r["name"] for r in self.data["roads"]["roads"]}

    @property
    def shelter_names(self):
        return {s["id"]: s["name"] for s in self.data["shelters"]}

    def approval_status(self):
        a = self.approval
        if a["status"] == "approved" and a["approved_version"] != self.plan_version:
            return "outdated"
        return a["status"]

    def suggested_road(self):
        if not self.plan or not self.plan["assignments"]:
            return None
        first = self.plan["assignments"][0]
        return first["route"]["road_ids"][0] if first["route"]["road_ids"] else None

    def suggested_shelter(self):
        if not self.plan or not self.plan["assignments"]:
            return None
        tot = {}
        for a in self.plan["assignments"]:
            tot[a["shelter_id"]] = tot.get(a["shelter_id"], 0) + a["people"]
        return max(sorted(tot), key=lambda k: tot[k])

    def roads_in_plan(self):
        return {r for a in (self.plan or {"assignments": []})["assignments"] for r in a["route"]["road_ids"]}

    # ----- alert -----
    def generate_alert(self, alert_id=None):
        alerts = self.data["alerts"]
        alert = next((a for a in alerts if a["id"] == alert_id), alerts[0])
        self.alert = {**alert, "issued_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "source": "SIMULATED"}
        self.plan, self.plan_version, self.explanation, self.changes = None, 0, None, []
        self.advisories = {"en": None, "ta": None}
        self.approval = {"status": "none", "plan_version": None, "timestamp": None, "approved_version": None}
        self._log("Alert Input", f"Simulated alert received: {alert['title']} covering {len(alert['area_ids'])} areas.", "warning")
        return "warning", f"Simulated flood alert generated: {alert['title']}"

    # ----- planning -----
    def create_plan(self):
        if not self.alert:
            return "error", "Generate a flood alert first - there is nothing to plan yet."
        return self._apply_plan("Initial plan requested by operator")

    def replan(self):
        if not self.plan:
            return "error", "No plan exists yet. Create a response plan first."
        return self._apply_plan("Operator requested replanning")

    def _apply_plan(self, trigger):
        try:
            new = build_plan(self.data, self.alert["area_ids"], self.blocked, self.full_shelters, self.config)
        except ValueError as exc:
            self._log("Risk Analysis", f"Planning failed: {exc}", "error")
            return "error", f"Planning failed: {exc}"
        old, first = self.plan, self.plan is None
        changed = first or plan_signature(old) != plan_signature(new)
        self.plan = new
        top = new["risk"][0]
        self._log("Risk Analysis", f"{len(new['risk'])} areas scored; highest: {top['name']} ({top['score']}, {top['level']}).")
        for a in new["assignments"]:
            self._log("Shelter Allocation", f"{a['people']} from {a['area_name']} -> {a['shelter_name']}.")
        for u in new["unserved"]:
            self._log("Shelter Allocation", f"{u['area_name']}: {u['people']} unplaced. {u['reason']}", "error")
        for a in new["assignments"]:
            self._log("Route Planning", f"{a['area_name']} -> {a['shelter_name']}: {' > '.join(a['route']['path_names'])} ({a['route']['cost']:g} min, Dijkstra).")
        for v in new["volunteers"]:
            self._log("Volunteer Assignment", f"{v['name']} -> {v['area_id']}: {v['reason']}")
        for g in new["volunteer_gaps"]:
            self._log("Volunteer Assignment", f"Unfilled slot ({g['skill']}) at {g['area_id']}.", "warning")
        if not changed:
            self._log("Human Approval", "Replan produced an identical plan; existing approval status unchanged.", "info")
            return "info", f"{trigger}: plan recalculated - no change to routes, shelters or volunteers."
        self.plan_version += 1
        lines = diff_plans(old, new)
        self.changes.append({"time": _now(), "trigger": trigger, "version": self.plan_version, "lines": lines or ["Initial plan created."]})
        if not first:
            self._log("Replanning", f"{trigger}. Plan v{self.plan_version}: " + (" | ".join(lines) if lines else "volunteer-level changes only"), "warning")
        self.generate_advisory("en"); self.generate_advisory("ta")
        self.explanation = explain_plan(new, self.data, self.use_ai)
        st = self.approval["status"]
        if st == "approved":
            self.approval = {**self.approval, "status": "outdated", "plan_version": self.plan_version}
            self._log("Human Approval", f"Previously approved plan is now OUTDATED. Plan v{self.plan_version} requires renewed approval.", "warning")
        else:
            self.approval = {"status": "pending", "plan_version": self.plan_version, "timestamp": None, "approved_version": None}
            self._log("Human Approval", f"Plan v{self.plan_version} awaiting officer approval.")
        if new["warnings"]:
            return "warning", f"Plan v{self.plan_version} ready with {len(new['warnings'])} warning(s) - see the shelter and volunteer tabs."
        return "success", f"Plan v{self.plan_version} ready - {len(new['assignments'])} route(s) planned. Awaiting approval."

    # ----- disruptions -----
    def block_road(self, road_id):
        if road_id not in self.road_names:
            return "error", "Unknown road."
        if road_id in self.blocked:
            return "warning", f"{road_id} is already blocked."
        self.blocked.add(road_id)
        self._log("Operator", f"Road {road_id} ({self.road_names[road_id]}) marked BLOCKED.", "warning")
        if self.plan:
            return self._apply_plan(f"Road {road_id} blocked")
        return "warning", f"Road {road_id} blocked. It will be excluded when the plan is created."

    def restore_road(self, road_id):
        if road_id not in self.blocked:
            return "warning", f"{road_id} is not blocked."
        self.blocked.discard(road_id)
        self._log("Operator", f"Road {road_id} restored.", "success")
        if self.plan:
            return self._apply_plan(f"Road {road_id} restored")
        return "success", f"Road {road_id} restored."

    def mark_shelter_full(self, shelter_id):
        if shelter_id not in self.shelter_names:
            return "error", "Unknown shelter."
        if shelter_id in self.full_shelters:
            return "warning", "That shelter is already marked full."
        self.full_shelters.add(shelter_id)
        self._log("Operator", f"{self.shelter_names[shelter_id]} marked FULL.", "warning")
        if self.plan:
            return self._apply_plan(f"{self.shelter_names[shelter_id]} marked full")
        return "warning", "Shelter marked full. It will be skipped when the plan is created."

    def reset_shelter(self, shelter_id):
        if shelter_id not in self.full_shelters:
            return "warning", "That shelter is not marked full."
        self.full_shelters.discard(shelter_id)
        self._log("Operator", f"{self.shelter_names[shelter_id]} capacity reset.", "success")
        if self.plan:
            return self._apply_plan(f"{self.shelter_names[shelter_id]} capacity reset")
        return "success", "Shelter capacity reset."

    # ----- advisories & approval -----
    def generate_advisory(self, lang):
        if not self.plan:
            return "error", "Create a response plan before drafting an advisory."
        facts = build_facts(self.plan, self.data, self.plan_version, self.alert["title"])
        res = generate_advisory(facts, lang, self.use_ai)
        self.advisories[lang] = {**res, "plan_version": self.plan_version, "generated_at": _now()}
        label = "English" if lang == "en" else "Tamil"
        self._log("Advisory Generation", f"{label} advisory drafted for plan v{self.plan_version} ({res['source']}). {res['note']}",
                  "warning" if res["source"] == "template" and "unavailable" in res["note"] or "rejected" in res["note"] else "info")
        return "success", f"{label} advisory drafted ({res['source']})."

    def _reviewable(self):
        if not self.plan:
            return "No plan to review."
        if not (self.advisories["en"] and self.advisories["ta"]):
            return "Generate both advisories before review."
        if any(self.advisories[k]["plan_version"] != self.plan_version for k in ("en", "ta")):
            return "Advisory is out of date; regenerate it first."
        return None

    def approve(self):
        problem = self._reviewable()
        if problem:
            return "error", problem
        if self.approval_status() == "approved":
            return "warning", "This plan version is already approved."
        self.approval = {"status": "approved", "plan_version": self.plan_version, "approved_version": self.plan_version,
                         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self._log("Human Approval", f"Advisory for plan v{self.plan_version} APPROVED (simulated - nothing was sent).", "success")
        return "success", f"Plan v{self.plan_version} approved. SIMULATION: no message was sent."

    def reject(self):
        problem = self._reviewable()
        if problem:
            return "error", problem
        self.approval = {"status": "rejected", "plan_version": self.plan_version, "approved_version": None,
                         "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self._log("Human Approval", f"Advisory for plan v{self.plan_version} REJECTED.", "warning")
        return "warning", f"Plan v{self.plan_version} rejected. Adjust the scenario and replan, or regenerate."
