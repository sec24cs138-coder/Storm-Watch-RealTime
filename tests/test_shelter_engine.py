import itertools
import unittest
from src.planner import build_plan
from src.shelter_engine import remaining_capacity, allocate
from src.state_manager import load_data

AREAS = ["velachery", "adyar", "taramani", "thiruvanmiyur"]


class ShelterTests(unittest.TestCase):
    def setUp(self):
        self.d = load_data()

    def test_capacity_never_exceeded_over_many_scenarios(self):
        roads = [r["id"] for r in self.d["roads"]["roads"]]
        shelters = [s["id"] for s in self.d["shelters"]]
        cap = {s["id"]: remaining_capacity(s) for s in self.d["shelters"]}
        for k in range(0, 4):
            for blocked in itertools.combinations(roads, k):
                for full in ([], shelters[:1], shelters[1:]):
                    p = build_plan(self.d, AREAS, blocked, full)
                    used = {}
                    for a in p["assignments"]:
                        used[a["shelter_id"]] = used.get(a["shelter_id"], 0) + a["people"]
                        self.assertNotIn(a["shelter_id"], full)
                        self.assertFalse(set(a["route"]["road_ids"]) & set(blocked))
                    for sid, n in used.items():
                        self.assertLessEqual(n, cap[sid])
                    for area in self.d["areas"]:
                        placed = sum(a["people"] for a in p["assignments"] if a["area_id"] == area["id"])
                        left = sum(u["people"] for u in p["unserved"] if u["area_id"] == area["id"])
                        self.assertEqual(placed + left, area["population"])

    def test_all_shelters_full_reports_no_feasible_shelter(self):
        p = build_plan(self.d, AREAS, (), [s["id"] for s in self.d["shelters"]])
        self.assertEqual(p["assignments"], [])
        self.assertEqual(len(p["unserved"]), 4)
        self.assertIn("No feasible shelter", p["unserved"][0]["reason"])

    def test_unreachable_shelters_report_no_feasible_route(self):
        p = build_plan(self.d, ["velachery"], {"R1", "R2", "R11"}, ())
        self.assertEqual(p["assignments"], [])
        self.assertIn("No feasible route", p["unserved"][0]["reason"])

    def test_unavailable_shelter_has_zero_capacity(self):
        s = dict(self.d["shelters"][0], available=False)
        self.assertEqual(remaining_capacity(s), 0)

    def test_allocate_without_splitting(self):
        self.assertEqual(allocate(100, [("a", 1)], {"a": 50}, allow_split=False), ([], 100))
        self.assertEqual(allocate(100, [("a", 1), ("b", 2)], {"a": 60, "b": 60}, allow_split=True), ([("a", 60), ("b", 40)], 0))


if __name__ == "__main__":
    unittest.main()
