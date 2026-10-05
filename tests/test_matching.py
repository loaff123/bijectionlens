"""Graph-level matching tests; small oracle never calls the production matcher."""
import importlib
import itertools
import sys

import unittest


def solver():
    assert importlib.util.find_spec('bijectionlens.matching') is not None, 'matching module has not been implemented'
    return importlib.import_module('bijectionlens.matching')


def budget(**kwargs):
    from bijectionlens.contract import Budget, Limits
    return Budget(Limits(**kwargs))


def brute_cardinality(graph, right_size):
    reachable = {0: 0}
    for row in graph:
        following = dict(reachable)
        for occupied, count in reachable.items():
            for v in row:
                if not occupied & (1 << v):
                    mask = occupied | (1 << v)
                    following[mask] = max(following.get(mask, 0), count + 1)
        reachable = following
    return max(reachable.values(), default=0)



class MatchingTests(unittest.TestCase):

    def test_reassignment_produces_perfect_matching(self):
        m = solver().maximum_matching(((0, 1), (0,)), 2, budget())
        assert m.left == (1, 0)
        assert m.right == (1, 0)
        assert m.cardinality == 2
        assert m.pairs == ((0, 1), (1, 0))


    def test_hall_contains_all_neighbors_for_duplicate_shortage(self):
        s = solver()
        graph = ((0,), (0,), (1, 2))
        m = s.maximum_matching(graph, 3, budget())
        h = s.hall_shortage(graph, m, budget())
        assert h.left_indices == (0, 1)
        assert h.neighbor_indices == (0,)
        assert h.deficiency == 1 == len(graph) - m.cardinality


    def test_empty_and_rectangular_graphs(self):
        s = solver()
        assert s.maximum_matching((), 3, budget()).right == (-1, -1, -1)
        m = s.maximum_matching(((), ()), 0, budget())
        assert m.left == (-1, -1)
        assert s.hall_shortage(((), ()), m, budget()).deficiency == 2


    def test_augmenting_path_longer_than_python_recursion_limit(self):
        n = sys.getrecursionlimit() + 101
        graph = tuple((i, i + 1) for i in range(n - 1)) + ((0,),)
        m = solver().maximum_matching(graph, n, budget())
        assert m.cardinality == n
        assert m.left[-1] == 0
        assert m.left[:-1] == tuple(range(1, n))


    def test_every_graph_up_to_three_by_three_matches_independent_oracle(self):
        s = solver()
        for n in range(4):
            for mask in range(1 << (n*n)):
                graph = tuple(tuple(j for j in range(n) if mask & (1 << (i*n+j))) for i in range(n))
                m = s.maximum_matching(graph, n, budget())
                assert m.cardinality == brute_cardinality(graph, n)
                if m.cardinality < n:
                    h = s.hall_shortage(graph, m, budget())
                    neighbors = set().union(*(set(graph[i]) for i in h.left_indices))
                    assert neighbors == set(h.neighbor_indices)
                    assert h.deficiency == n-m.cardinality


    def test_matching_cap_charged_before_next_operation(self):
        solver()
        from bijectionlens.contract import ResourceLimit
        with self.assertRaises(ResourceLimit) as caught:
            solver().maximum_matching(((0,),), 1, budget(max_matching_scans=0))
        assert caught.exception.phase == 'matching_scans'
        assert caught.exception.used == 0
        assert caught.exception.requested == 1


    def test_matching_exact_work_boundary(self):
        s = solver()
        b = budget()
        expected = s.maximum_matching(((0, 1), (0,)), 2, b)
        count = dict(b.snapshot())['matching_scans']
        assert s.maximum_matching(((0, 1), (0,)), 2, budget(max_matching_scans=count)) == expected
        from bijectionlens.contract import ResourceLimit
        with self.assertRaises(ResourceLimit):
            s.maximum_matching(((0, 1), (0,)), 2, budget(max_matching_scans=count-1))
