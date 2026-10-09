import unittest
from src.risk_engine import score_areas, normalise_weights, vulnerable_count
from src.state_manager import load_data


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.areas = load_data()["areas"]

    def test_scores_in_documented_range(self):
        for w in ({"exposure": 1, "population": 0, "vulnerable": 0}, {"exposure": 5, "population": 5, "vulnerable": 90},
                  {"exposure": 0.5, "population": 0.25, "vulnerable": 0.25}):
            for r in score_areas(self.areas, w):
                self.assertGreaterEqual(r["score"], 0)
                self.assertLessEqual(r["score"], 100)

    def test_sorted_and_factor_points_sum_to_score(self):
        r = score_areas(self.areas)
        self.assertEqual([x["score"] for x in r], sorted((x["score"] for x in r), reverse=True))
        for x in r:
            self.assertAlmostEqual(sum(f["points"] for f in x["factors"].values()), x["score"], delta=0.2)

    def test_weights_normalised_and_invalid_rejected(self):
        self.assertAlmostEqual(sum(normalise_weights({"exposure": 2, "population": 1, "vulnerable": 1}).values()), 1.0)
        with self.assertRaises(ValueError):
            normalise_weights({"exposure": 0, "population": 0, "vulnerable": 0})

    def test_vulnerable_capped_by_population(self):
        self.assertEqual(vulnerable_count({"population": 10, "vulnerable": {"elderly": 50}}), 10)

    def test_empty_input(self):
        self.assertEqual(score_areas([]), [])


if __name__ == "__main__":
    unittest.main()
