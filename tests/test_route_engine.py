import unittest
from src.route_engine import build_graph, shortest_route
from src.state_manager import load_data


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.roads = load_data()["roads"]

    def test_basic_shortest_route(self):
        r = shortest_route(build_graph(self.roads), "velachery", "shelter_hall")
        self.assertEqual(r["road_ids"], ["R1"])
        self.assertEqual(r["cost"], 12.0)

    def test_blocked_road_excluded_and_cost_rises(self):
        r = shortest_route(build_graph(self.roads, {"R1"}), "velachery", "shelter_hall")
        self.assertNotIn("R1", r["road_ids"])
        self.assertGreater(r["cost"], 12.0)

    def test_no_route_returns_none(self):
        blocked = {"R1", "R2", "R11"}  # isolates Velachery
        self.assertIsNone(shortest_route(build_graph(self.roads, blocked), "velachery", "shelter_hall"))

    def test_unknown_node_returns_none(self):
        self.assertIsNone(shortest_route(build_graph(self.roads), "nowhere", "shelter_hall"))


if __name__ == "__main__":
    unittest.main()
