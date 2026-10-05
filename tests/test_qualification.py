"""Tests for the qualification oracle, kept independent of production internals."""
from fractions import Fraction
import importlib.util
import math
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qualify.py"


class QualificationOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SCRIPT.exists():
            spec = importlib.util.spec_from_file_location("qualification_oracle", SCRIPT)
            cls.q = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.q)
        else:
            cls.q = None

    def oracle(self):
        self.assertIsNotNone(self.q, "independent qualification script must exist")
        return self.q

    def test_integer_cross_product_exact_boundaries(self):
        q = self.oracle()
        self.assertTrue(q.exact_edge(3 + 4j, 0, 5.0))
        self.assertFalse(q.exact_edge(3 + 4j, 0, math.nextafter(5.0, 0.0)))
        self.assertFalse(q.exact_edge(complex(5e-324, 5e-324), 0, 5e-324))
        self.assertTrue(q.exact_edge(1e308, 0, 1e308))
        self.assertFalse(q.exact_edge(1e308 + 1e308j, -1e308 - 1e308j, 1e308))
        self.assertEqual(Fraction(*q.distance_ratio(3 + 4j, 0)), 25)

    def test_subset_oracle_reassigns_and_preserves_multiplicity(self):
        q = self.oracle()
        self.assertEqual(q.oracle_cardinality(((0, 1), (0,))), 2)
        self.assertEqual(q.oracle_cardinality(((0,), (0,), (1, 2))), 2)
        self.assertEqual(q.oracle_cardinality(()), 0)
        self.assertEqual(q.oracle_cardinality(((), ())), 0)

    def test_permutation_bottleneck_uses_maximum_not_sum(self):
        q = self.oracle()
        self.assertEqual(q.oracle_bottleneck([0, 3], [0, -1 + 2.5j]), 9)
        self.assertEqual(q.oracle_bottleneck([0], [1 + 1j]), 2)
        self.assertEqual(q.oracle_bottleneck([], []), 0)

    def test_pair_and_hall_oracle_rejects_omitted_neighbors(self):
        q = self.oracle()
        graph = ((0,), (0,), (1, 2))
        q.check_graph_certificate(graph, 3, ((0, 0), (2, 1)), ((0, 1), (0,), 1))
        with self.assertRaises(AssertionError):
            q.check_graph_certificate(graph, 3, ((0, 0), (2, 1)), ((0, 1, 2), (0, 1), 1))
        with self.assertRaises(AssertionError):
            q.check_graph_certificate(graph, 3, ((0, 0), (1, 0)), ((0, 1), (0,), 1))
        with self.assertRaises(AssertionError):
            q.check_graph_certificate(graph, 3, ((0, 2),), ((0, 1), (0,), 1))

    def test_frozen_case_counts_and_identities(self):
        q = self.oracle()
        cases = list(q.frozen_cases())
        self.assertEqual(len(cases), 600)
        self.assertEqual(cases[0][0], "random-000")
        self.assertEqual(len(list(q.permutation_cases())), 36)
        self.assertEqual(len(list(q.boundary_cases())), 16)
        self.assertEqual(len(list(q.frozen_bottleneck_cases())), 80)
        additional = list(q.additional_bottleneck_cases())
        self.assertEqual(len(additional), 500)
        self.assertEqual(max(len(a) for _, a, _ in additional), 7)
        self.assertGreater(sum(len(a) == 7 for _, a, _ in additional), 0)
        self.assertEqual(list(q.frozen_cases()), cases)

    def test_five_baselines_preserve_positive_and_negative_controls(self):
        q = self.oracle()
        fixtures = list(q.utility_cases())
        self.assertEqual(len(fixtures), 5)
        by_id = {name: (a, b, tol) for name, a, b, tol in fixtures}
        self.assertFalse(q.sorting_baseline(*by_id["complex-sort"]))
        self.assertFalse(q.first_fit_baseline(*by_id["first-fit-overlap"]))
        self.assertTrue(q.sorting_baseline(*by_id["all-baselines-work"]))
        self.assertTrue(q.first_fit_baseline(*by_id["all-baselines-work"]))
        a, b, tol = by_id["hall-duplicate-shortage"]
        graph = q.oracle_graph(a, b, tol)
        self.assertTrue(all(graph))
        self.assertEqual(q.oracle_cardinality(graph), 2)

    def test_capacity_profiles_are_explicit_and_bounded(self):
        q = self.oracle()
        self.assertTrue(hasattr(q, "capacity_case_spec"), "capacity profiles must be defined")
        sparse = q.capacity_case_spec("sparse-10000")
        self.assertEqual(len(sparse["actual"]), 10000)
        self.assertEqual(len(sparse["expected"]), 10000)
        self.assertEqual(sparse["atol"], .25)
        self.assertEqual(sparse["expected"][:3], [0j, 1j, 2j])
        self.assertEqual(sparse["expected"][-1], 99 + 99j)
        dense = q.capacity_case_spec("dense-400")
        self.assertEqual(len(dense["actual"]), 400)
        self.assertEqual(dense["limits"], {"max_edges": 20000})
        extreme = q.capacity_case_spec("extreme-bottleneck-250")
        self.assertEqual(len(extreme["actual"]) * len(extreme["expected"]), 62500)
        over = q.capacity_case_spec("extreme-bottleneck-500")
        self.assertEqual(len(over["actual"]) * len(over["expected"]), 250000)
        self.assertEqual(extreme["kind"], "bottleneck")
        with self.assertRaises(ValueError):
            q.capacity_case_spec("not-a-profile")

    def test_least_binary64_tolerance_oracle(self):
        q = self.oracle()
        q.check_binary64_ceiling(Fraction(0), 0.0)
        q.check_binary64_ceiling(Fraction(2), math.sqrt(2))
        with self.assertRaises(AssertionError):
            q.check_binary64_ceiling(Fraction(2), math.nextafter(math.sqrt(2), 0))
        with self.assertRaises(AssertionError):
            q.check_binary64_ceiling(Fraction(0), -0.0)
        with self.assertRaises(AssertionError):
            q.check_binary64_ceiling(Fraction(2), None)


if __name__ == "__main__":
    unittest.main()
