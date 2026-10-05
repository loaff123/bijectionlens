"""Complete exact radius graph, independently enumerated in every case."""
from fractions import Fraction
import importlib
import math
import random
import unittest


def spatial():
    assert importlib.util.find_spec('bijectionlens.spatial') is not None, 'spatial module has not been implemented'
    return importlib.import_module('bijectionlens.spatial')


def make_budget(**kwargs):
    from bijectionlens.contract import Budget, Limits
    return Budget(Limits(**kwargs))


def dense(left, right, q):
    return tuple(tuple(j for j,b in enumerate(right)
                       if (a.real-b.real)**2+(a.imag-b.imag)**2 <= q)
                 for a in left)


class SpatialTests(unittest.TestCase):
    def assert_graph(self, actual, expected, atol):
        fn = spatial().radius_graph
        from bijectionlens.contract import normalize_points, normalize_atol
        left, right = normalize_points(actual), normalize_points(expected)
        q = normalize_atol(atol)**2
        observed = fn(left, right, q, make_budget())
        self.assertEqual(observed, dense(left, right, q))
        return observed

    def test_coincident_points_keep_every_occurrence(self):
        self.assertEqual(self.assert_graph([0]*12, [0]*13, 0), (tuple(range(13)),)*12)

    def test_vertical_clusters_and_boundary_circles(self):
        points = [complex(0,i/8) for i in range(-50,51)]
        self.assert_graph(points, list(reversed(points)), .375)
        self.assertEqual(self.assert_graph([0], [3+4j, -3-4j, 5j, 5], 5), ((0,1,2,3),))
        self.assertEqual(self.assert_graph([0], [3+4j], math.nextafter(5, 0)), ((),))

    def test_extreme_and_subnormal_coordinates(self):
        self.assert_graph([complex(1e308,1e308),complex(-1e308,-1e308),0],
                          [complex(1e308,1e308),complex(-1e308,-1e308),5e-324+5e-324j], 1e308)
        self.assertEqual(self.assert_graph([0], [5e-324+5e-324j], 5e-324), ((),))

    def test_seeded_indexed_graph_equals_complete_graph(self):
        rng = random.Random(831491)
        for _ in range(100):
            left = [complex(rng.randrange(-30,31)/8, rng.randrange(-30,31)/8) for _ in range(25)]
            right = [complex(rng.randrange(-30,31)/8, rng.randrange(-30,31)/8) for _ in range(31)]
            self.assert_graph(left, right, rng.choice([0,.25,.5,1,2]))

    def test_empty_sides(self):
        self.assertEqual(self.assert_graph([], [1], 0), ())
        self.assertEqual(self.assert_graph([1,2], [], 0), ((),()))

    def test_each_cap_stops_before_next_unit(self):
        fn = spatial().radius_graph
        from bijectionlens.contract import normalize_points, ResourceLimit
        points = normalize_points(list(range(16)))
        for phase in ('tree_build', 'tree_visits', 'edges'):
            with self.subTest(phase=phase):
                with self.assertRaises(ResourceLimit) as caught:
                    fn(points, points, Fraction(0), make_budget(**{'max_'+phase: 0}))
                self.assertEqual(caught.exception.phase, phase)
                self.assertEqual(caught.exception.used, 0)
                self.assertGreater(caught.exception.requested, 0)

    def test_exact_next_operation_boundaries(self):
        fn = spatial().radius_graph
        from bijectionlens.contract import normalize_points, ResourceLimit
        points = normalize_points(list(range(20)))
        b = make_budget()
        wanted = fn(points, points, Fraction(4), b)
        for phase in ('tree_build', 'tree_visits', 'edges'):
            count = dict(b.snapshot())[phase]
            self.assertEqual(fn(points, points, Fraction(4), make_budget(**{'max_'+phase:count})),wanted)
            with self.assertRaises(ResourceLimit):
                fn(points, points, Fraction(4), make_budget(**{'max_'+phase:count-1}))

    def test_equal_coordinate_sort_charges_each_scalar_comparison(self):
        fn = spatial().radius_graph
        from bijectionlens.contract import normalize_points
        b = make_budget()
        points = normalize_points([0]*9)
        self.assertEqual(fn(points[:1],points,Fraction(0),b),(tuple(range(9)),))
        # Root: 9 initial references, 8 sort calls * 3 scalar comparisons,
        # 9 child references, 9 leaf references, 28 leaf extrema, 4 merges.
        self.assertEqual(dict(b.snapshot())['tree_build'],83)
        # 3 tree nodes + 9 candidate checks + 8 order calls * 2 comparisons.
        self.assertEqual(dict(b.snapshot())['tree_visits'],28)
