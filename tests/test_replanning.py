import os
import unittest
from pathlib import Path
from unittest import mock

from src import advisory_engine
from src.state_manager import ScenarioState, ROOT


def planned():
    s = ScenarioState()
    s.generate_alert("A1")
    s.create_plan()
    return s


class ReplanTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("GEMINI_API_KEY", None)

    def test_plan_requires_alert(self):
        self.assertEqual(ScenarioState().create_plan()[0], "error")

    def test_block_road_recalculates_route(self):
        s = planned()
        road = s.suggested_road()
        before = {(a["area_id"], a["shelter_id"], tuple(a["route"]["path"])) for a in s.plan["assignments"]}
        self.assertEqual(s.block_road(road)[0] in ("success", "warning"), True)
        after = {(a["area_id"], a["shelter_id"], tuple(a["route"]["path"])) for a in s.plan["assignments"]}
        self.assertNotEqual(before, after)
        self.assertTrue(all(road not in a["route"]["road_ids"] for a in s.plan["assignments"]))
        s.restore_road(road)
        self.assertIn(road, s.roads_in_plan() | {road})
        self.assertNotIn(road, s.blocked)

    def test_shelter_full_reassigns(self):
        s = planned()
        sid = s.suggested_shelter()
        s.mark_shelter_full(sid)
        self.assertTrue(all(a["shelter_id"] != sid for a in s.plan["assignments"]))
        s.reset_shelter(sid)
        self.assertTrue(any(a["shelter_id"] == sid for a in s.plan["assignments"]))

    def test_replan_invalidates_approval(self):
        s = planned()
        self.assertEqual(s.approve()[0], "success")
        self.assertEqual(s.approval_status(), "approved")
        s.block_road(s.suggested_road())
        self.assertEqual(s.approval_status(), "outdated")
        self.assertEqual(s.approve()[0], "success")
        self.assertEqual(s.approval_status(), "approved")

    def test_unchanged_replan_keeps_approval(self):
        s = planned()
        s.approve()
        s.replan()
        self.assertEqual(s.approval_status(), "approved")

    def test_reject_and_cannot_approve_without_plan(self):
        s = ScenarioState()
        self.assertEqual(s.approve()[0], "error")
        s = planned()
        s.reject()
        self.assertEqual(s.approval_status(), "rejected")

    def test_reset_restores_initial_state(self):
        s = planned()
        s.block_road("R1"); s.mark_shelter_full("shelter_hall"); s.approve()
        s.reset()
        self.assertEqual((s.blocked, s.full_shelters, s.plan, s.alert), (set(), set(), None, None))
        self.assertEqual(s.approval_status(), "none")

    def test_fallback_without_key(self):
        s = planned()
        self.assertEqual(s.advisories["en"]["source"], "template")
        self.assertIn("SIMULATED", s.advisories["en"]["text"])
        self.assertIn("உருவகப்படுத்த", s.advisories["ta"]["text"])

    def test_gemini_failure_falls_back(self):
        os.environ["GEMINI_API_KEY"] = "dummy-test-key"
        try:
            with mock.patch.object(advisory_engine, "_call_gemini", side_effect=RuntimeError("secret dummy-test-key")):
                s = planned()
            self.assertEqual(s.advisories["en"]["source"], "template")
            self.assertNotIn("dummy-test-key", s.advisories["en"]["note"])
            self.assertNotIn("dummy-test-key", " ".join(e["message"] for e in s.log))
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_gemini_output_with_invented_numbers_rejected(self):
        os.environ["GEMINI_API_KEY"] = "dummy-test-key"
        try:
            with mock.patch.object(advisory_engine, "_call_gemini", return_value="Simulated flood advisory: please move 9999 people now to somewhere safe and stay calm everyone."):
                s = planned()
            self.assertEqual(s.advisories["en"]["source"], "template")
            self.assertIn("rejected", s.advisories["en"]["note"])
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

    def test_good_gemini_output_accepted(self):
        os.environ["GEMINI_API_KEY"] = "dummy-test-key"
        try:
            s0 = planned()
            facts = advisory_engine.build_facts(s0.plan, s0.data, s0.plan_version, s0.alert["title"])
            good = advisory_engine.template_en(facts).replace("Flood advisory", "Simulated flood advisory")
            with mock.patch.object(advisory_engine, "_call_gemini", return_value=good):
                res = advisory_engine.generate_advisory(facts, "en")
            self.assertEqual(res["source"], "gemini")
        finally:
            os.environ.pop("GEMINI_API_KEY", None)


class ProjectFileTests(unittest.TestCase):
    def test_required_files_exist_and_no_secret(self):
        for f in ["app.py", "requirements.txt", ".env.example", "README.md", "run.bat", "run.sh", "assets/logo.svg",
                  "data/areas.json", "data/shelters.json", "data/roads.json", "data/volunteers.json", "data/sample_alerts.json"]:
            self.assertTrue((ROOT / f).exists(), f)
        env = (ROOT / ".env.example").read_text()
        self.assertTrue(any(l.strip() == "GEMINI_API_KEY=" for l in env.splitlines()))
        self.assertFalse((ROOT / ".env").exists())

    def test_scenario_meets_minimums(self):
        d = ScenarioState().data
        self.assertGreaterEqual(len(d["areas"]), 3)
        self.assertGreaterEqual(len(d["shelters"]), 3)
        self.assertGreaterEqual(len(d["roads"]["roads"]), 8)
        self.assertGreaterEqual(len(d["volunteers"]), 5)


if __name__ == "__main__":
    unittest.main()
